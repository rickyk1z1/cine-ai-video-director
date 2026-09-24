import copy
import json
import struct
import zlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import test_prompt_guard as guard_tests
import hashlib
from test_store import fixture,Store,uid,new_shot,new_document,Conflict
import production
import storyboard

class ProductionTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.store=Store(self.root)
        d=fixture();other=copy.deepcopy(d['sections'][0]);other['id']=uid();other['title']='第二段'
        for g in other['groups']:
            g['id']=uid()
            for s in g['shots']:s['id']=uid();s['content']='第二段待确认内容'
        d['sections'].append(other);self.doc=self.store.create('',d)
        self.sid=self.doc['sections'][0]['id'];self.ids=production.shot_ids(self.doc['sections'][0])
    def confirm(self):
        d=self.store.read();return self.store.confirm(self.sid,d['revision'],'已查看并确认第一段')
    def record(self,r):
        if r.get('kind')=='package' and r.get('data',{}).get('prompt'):
            self.bind_review(r)
        return self.store.record(r,self.store.read()['revision'])
    def bind_review(self,r):
        b=guard_tests.PromptGuardTests().bundle();d=r['data'];b['prompt']=d['prompt']
        b['semantic_review']['prompt_sha256']=hashlib.sha256(b['prompt'].encode()).hexdigest()
        refs=d.get('references',[])
        b['reference_policy']=[{'id':x['label'],'type':'image','use':x['purpose'],'not_required':'测试参考不锁整图','mode':'reference'} for x in refs]
        for ref,policy in zip(refs,b['reference_policy']):
            ext=Path(ref['file_path']).suffix.lower()
            if ext=='.mp4':policy['type']='video'
            if ext=='.wav':
                policy['type']='audio';policy['audio_contract']={'platform':'test','model':'offline','mode':'reference','checked_at':'2026-09-22','evidence':'离线音频规格测试','file':str(self.root/ref['file_path']),'usage':'原声','duration_limits':{'min_seconds':0}}
        b['delivery_contract']={'reference_boundary':'全画幅'}
        b['positive_review']['references']=[{'id':x['label'],'necessity':'离线结构测试','positive_role':x['purpose'],'implied_endpoint':False} for x in refs]
        b['continuity_review']={'units':list(r['shot_ids']),'joins':[{'from':a,'to':z,'type':'cut','audience_bridge':'同一动作的顺接','evidence':'本测试相邻画格','budget_check':'镜头预算覆盖','status':'resolved'} for a,z in zip(r['shot_ids'],r['shot_ids'][1:])]}
        b['input_sha256']=production.digest(production.delivery_input(self.store.read(),r,self.root))
        d['prompt_review']=b

    def base(self,rid,kind,ids=None):
        return dict(id=rid,kind=kind,title=rid,body='说明 '+rid,section_ids=[self.sid],shot_ids=self.ids if ids is None else ids,depends_on=[],files=[],data={})
    def frame(self):
        def chunk(kind,data):return struct.pack('>I',len(data))+kind+data+struct.pack('>I',zlib.crc32(kind+data))
        image=b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',2,1,8,2,0,0,0))+chunk(b'IDAT',zlib.compress(b'\x00\xff\x00\x00\x00\x00\xff'))+chunk(b'IEND',b'')
        (self.root/'frame.png').write_bytes(image)
        r=self.base('G','grid');r['files']=[dict(path='frame.png',role='storyboard_grid')]
        r['data']={'cells':[{'shot_id':s,'box':[i,0,i+1,1]} for i,s in enumerate(self.ids)],'adoption_evidence':'用户采用组图'}
        self.record(r)
    def path_decision(self,path='direct_platform',assignments=None):
        r=self.base('PATH','decision')
        r['data']={'decision_type':'production_path','invocation_id':'call-1','batch_id':'batch-1',
                   'output_scope':{'video_count':2,'evidence':'本批分别生成两条素材'},'recommended_path':'previs_reference' if path in ('previs_reference','blender_previs','hybrid') else 'direct_platform','path':path,'platform':'test-only','selection_evidence':'用户明确选择本批制作路径',
                   'assignments':assignments or [{'path':path,'shot_ids':self.ids}]}
        self.record(r);return r
    def test_path_choice_requires_recommendation_and_explicit_selection(self):
        self.confirm()
        r=self.base('PATH','decision')
        r['data']={'decision_type':'production_path','invocation_id':'call-1','batch_id':'batch-1',
                   'path':'direct_platform','platform':'test-only','selection_evidence':'用户选择直接平台生成',
                   'assignments':[{'path':'direct_platform','shot_ids':self.ids}]}
        self.record(r)  # A direct user choice does not require an invented recommendation.
        r['data']['recommended_path']='direct_platform';r['data']['selection_evidence']='继续'
        self.record(r)  # The recorded concrete choice supplies the context; words are not a password.
        r['data']['selection_evidence']='按这个做'
        self.record(r)  # The recorded concrete choice supplies the context; words are not a password.
        r['data']['selection_evidence']='用户明确选择直接平台生成'
        self.record(r)
    def test_image_stage_entry_needs_explicit_scope_and_evidence(self):
        self.confirm()
        r=self.base('IMAGE-STAGE','decision')
        r['data']={'decision_type':'image_stage_entry','batch_id':'batch-1','selection_evidence':'下一步'}
        self.record(r)
        r['data']['selection_evidence']='用户明确同意进入本批图片资产及分镜图制作'
        self.record(r)
        r['shot_ids']=[]
        with self.assertRaisesRegex(ValueError,'实际镜头'):self.record(r)
    def test_actual_input_change_marks_new_record_stale(self):
        self.confirm()
        image=self.root/'source.png';image.write_bytes(b'first')
        r=self.base('BOARD','decision');r['data']={'actual_inputs':[{'path':'source.png','purpose':'空间参考'}]}
        self.record(r)
        saved=next(x for x in self.store.read()['production']['records'] if x['id']=='BOARD')
        self.assertFalse(production.is_stale(self.store.read(),saved,self.root))
        image.write_bytes(b'second')
        self.assertTrue(production.is_stale(self.store.read(),saved,self.root))
    def test_new_image_batch_waits_for_adopted_storyboard_before_route(self):
        self.confirm()
        r=self.base('IMAGE-STAGE','decision')
        r['data']={'decision_type':'image_stage_entry','batch_id':'batch-1','selection_evidence':'用户明确同意进入图片资产与分镜图制作'}
        self.record(r)
        self.path_decision()  # A decision may be recorded before its inputs are ready.
        self.frame()
        self.path_decision()
    def test_multiple_adopted_states_complete_one_shot(self):
        self.confirm()
        sid=self.ids[0]
        entry=self.base('IMAGE-STAGE','decision',[sid])
        entry['data']={'decision_type':'image_stage_entry','batch_id':'batch-1','selection_evidence':'用户明确同意制作这一镜的多张分镜状态图'}
        self.record(entry)
        for name in ('start.png','end.png'):(self.root/name).write_bytes(name.encode())
        frames=self.base('FRAMES','asset',[sid])
        frames['files']=[{'path':'start.png','role':'state_start'},{'path':'end.png','role':'state_end'}]
        frames['data']={'asset_role':'storyboard_frame','status':'candidate','review_status':'pending'}
        self.record(frames)
        self.assertEqual(production.preview_rows(self.store.read(),self.root)[0]['status'],'candidate')
        path=self.base('PATH','decision',[sid])
        path['data']={'decision_type':'production_path','invocation_id':'call-1','batch_id':'batch-1',
                      'output_scope':{'video_count':1,'evidence':'单镜一条视频'},'recommended_path':'direct_platform',
                      'path':'direct_platform','platform':'test-only','selection_evidence':'用户明确选择这一镜直接平台生成',
                      'assignments':[{'path':'direct_platform','shot_ids':[sid]}]}
        self.record(path)
        frames['data'].update(status='adopted',review_status='adopted',adoption_evidence='用户采用此镜的起止两张状态图')
        self.record(frames)
        row=production.preview_rows(self.store.read(),self.root)[0]
        self.assertEqual(row['status'],'adopted')
        self.assertEqual(len(row['images']),2)
        self.record(path)
    def package(self):
        if not any(x['id']=='PATH' for x in self.store.read().get('production',{}).get('records',[])):self.path_decision()
        r=self.base('P','package');r['depends_on']=['G','PATH'];r['data']={
            'output_scope':{'video_count':2,'evidence':'本批分别生成两条素材'},'sound_plan':{'policy':'effects_only','tracks':[]},'platform':'test-only','mode':'reference','model':'offline','route':'grid','speech':'none',
            'production_path_decision_id':'PATH','production_invocation_id':'call-1','production_batch_id':'batch-1',
            'selection_evidence':'用户确认本批','capability_evidence':'离线结构测试，不代表真实平台',
            'grouping_reason':'连续两镜','grid_full_frame_instruction':'视频全画幅，不保留网格',
            'parameters':{'duration':6,'ratio':'16:9','resolution':'1080p'},
            'timeline':[{'shot_id':self.ids[0],'start':0,'end':3},{'shot_id':self.ids[1],'start':3,'end':6}],
            'references':[{'record_id':'G','file_path':'frame.png','label':'计划图片1','purpose':'构图与切镜'}],
            'prompt':'按采用两镜切换，全画幅输出。'}
        self.record(r);return r

    def test_package_requires_current_batch_path_selection(self):
        self.confirm();self.frame();r=self.package()
        r['data'].pop('production_path_decision_id');self.record(r)
        self.assertTrue(any('本批' in x for x in self.store.package('P')['issues']))

    def test_project_platform_decision_cannot_replace_batch_path(self):
        self.confirm();self.frame()
        note=self.base('PLATFORM','decision');note['data']={'platform':'小云雀','scope':'project'};self.record(note)
        r=self.base('P','package');r['depends_on']=['G','PLATFORM'];r['data']={
            'platform':'小云雀','mode':'reference','model':'offline','route':'grid','speech':'none',
            'selection_evidence':'项目长期平台','capability_evidence':'测试','grouping_reason':'相邻镜头',
            'parameters':{'duration':6,'ratio':'16:9','resolution':'1080p'},
            'timeline':[{'shot_id':self.ids[0],'start':0,'end':3},{'shot_id':self.ids[1],'start':3,'end':6}],
            'references':[{'record_id':'G','file_path':'frame.png','label':'图片1','purpose':'构图'}],
            'prompt':'测试'}
        self.record(r)
        self.assertTrue(any('本批' in x for x in self.store.package('P')['issues']))

    def test_path_decision_must_cover_batch_once(self):
        self.confirm()
        with self.assertRaises(ValueError):
            self.path_decision('hybrid',[{'path':'direct_platform','shot_ids':self.ids},
                                         {'path':'blender_previs','shot_ids':[self.ids[0]]}])

    def test_hybrid_package_must_stay_inside_one_assignment(self):
        self.confirm();self.frame()
        self.path_decision('hybrid',[{'path':'direct_platform','shot_ids':[self.ids[0]]},
                                     {'path':'blender_previs','shot_ids':[self.ids[1]]}])
        r=self.package()
        self.assertTrue(any('hybrid投产包' in x for x in self.store.package('P')['issues']))

    def test_path_binding_must_match_invocation_and_route(self):
        self.confirm();self.frame();r=self.package()
        r['data']['production_invocation_id']='another-call';self.record(r)
        self.assertEqual(self.store.package('P')['issues'],[])
        r['data']['production_invocation_id']='call-1';r['data']['route']='previs';self.record(r)
        self.assertTrue(any('直投镜头' in x for x in self.store.package('P')['issues']))
    def test_no_draft_export_and_partial_confirmation(self):
        with self.assertRaises(Conflict):self.store.export()
        self.confirm();md=(self.root/'分镜阅览.md').read_text()
        self.assertIn('SH01',md);self.assertIn('第二段待确认内容',md);self.assertIn('待确认',md)
    def test_read_and_update_cannot_forge_confirmations(self):
        d=self.store.read();d['production']={'confirmations':{'fake':{}},'records':[]}
        self.store.update(d,d['revision']);self.assertNotIn('production',self.store.read())
        self.assertFalse((self.root/'分镜阅览.md').exists())
        with self.assertRaises(ValueError):Store(self.root/'other').create('',d)
    def test_confirm_conflicts_and_invalid_input(self):
        self.confirm()
        with self.assertRaises(Conflict):self.store.confirm(self.sid,0,'陈旧确认')
        with self.assertRaises(ValueError):self.store.confirm(self.sid,self.store.read()['revision'],'')
    def test_draft_change_keeps_snapshot_then_reconfirm_preserves_records(self):
        self.confirm();r=self.base('D','decision');r['body']='用户选择先做资产';self.record(r)
        d=self.store.read();d['sections'][0]['groups'][0]['shots'][0]['content']='尚未确认的新剧情'
        d=self.store.update(d,d['revision']);md=(self.root/'分镜阅览.md').read_text()
        self.assertEqual(d['_section_status'][self.sid],'changed');self.assertIn('尚未确认的新剧情',md);self.assertIn('待确认',md)
        self.assertNotIn('尚未确认的新剧情',(self.root/'制作记录.md').read_text())
        self.assertIn('用户选择先做资产',md);self.confirm()
        self.assertIn('尚未确认的新剧情',(self.root/'分镜阅览.md').read_text())
        self.assertEqual(len(self.store.read()['production']['confirmations'][self.sid]['history']),1)
    def test_superseded_records_only_in_history_and_repeated_export(self):
        self.confirm();old=self.base('OLD','decision');old['body']='弃用喷泉镜头';self.record(old)
        new=self.base('NEW','decision');new['body']='当前纸艺首镜';new['data']={'supersedes':['OLD']};self.record(new)
        self.store.export();self.store.export()
        main=(self.root/'分镜阅览.md').read_text();history=(self.root/'制作记录.md').read_text()
        self.assertNotIn('弃用喷泉镜头',main);self.assertIn('当前纸艺首镜',main)
        self.assertIn('弃用喷泉镜头',history)
        self.assertEqual(len(self.store.read()['production']['records']),2)
    def test_verified_file_relocation_and_replacement_rejected(self):
        import hashlib
        target=self.root/'history'/'file.txt';target.parent.mkdir();target.write_bytes(b'original')
        folder=self.root/'过程记录';folder.mkdir()
        (folder/'文件迁移.json').write_text(json.dumps({'files':[{'old_path':str(self.root/'file.txt'),'new_path':str(target),'sha256':hashlib.sha256(b'original').hexdigest()}]}))
        self.assertEqual(production.local_file(self.root,'file.txt'),target)
        target.write_bytes(b'changed')
        with self.assertRaises(ValueError):production.local_file(self.root,'file.txt')

    def test_manual_history_edit_is_preserved(self):
        self.confirm();path=self.root/'制作记录.md';path.write_text('人工历史补充')
        d=self.record(self.base('D','decision'))
        self.assertTrue(d['_export_warning']);self.assertEqual(path.read_text(),'人工历史补充')

    def test_external_markdown_preserved(self):
        self.confirm();path=self.root/'分镜阅览.md';path.write_text('人工独有正文')
        r=self.base('D','decision');d=self.record(r)
        self.assertTrue(d['_export_warning']);self.assertEqual(path.read_text(),'人工独有正文')
        self.assertEqual(self.store.read()['production']['records'][0]['id'],'D')
        with self.assertRaises(Conflict):self.store.export()
    def test_legacy_read_only_and_safe_upgrade(self):
        path=self.root/'分镜阅览.md';path.write_text(storyboard.markdown(self.doc));before=path.read_bytes()
        self.store.read();self.assertEqual(path.read_bytes(),before)
        d=self.confirm();self.assertFalse(d['_export_warning']);self.assertIn('素材制作文档',path.read_text())
    def test_unknown_legacy_markdown_preserved(self):
        path=self.root/'分镜阅览.md';path.write_text('旧文件含手工补充')
        d=self.confirm();self.assertTrue(d['_export_warning']);self.assertEqual(path.read_text(),'旧文件含手工补充')
    def test_export_failure_is_recoverable(self):
        original=storyboard.atomic
        def fail(path,text):
            if path.name=='分镜阅览.md':raise OSError('模拟磁盘错误')
            return original(path,text)
        with patch.object(storyboard,'atomic',fail):d=self.confirm()
        self.assertIn('模拟',d['_export_warning']);self.assertEqual(d['_section_status'][self.sid],'confirmed')
        self.store.export();self.assertTrue((self.root/'分镜阅览.md').exists())
    def test_dependencies_and_file_changes(self):
        self.confirm();self.frame();self.package();self.assertEqual(self.store.package('P')['issues'],[])
        (self.root/'frame.png').write_bytes(b'changed');self.assertTrue(self.store.package('P')['issues'])
    def test_unrelated_section_edit_does_not_stale_package(self):
        self.confirm();self.frame();self.package()
        d=self.store.read();d['sections'][1]['groups'][0]['shots'][0]['content']='别段新内容';self.store.update(d,d['revision'])
        self.assertEqual(self.store.package('P')['issues'],[])
    def test_style_update_stales_package(self):
        self.confirm();r=self.base('S','style',[]);self.record(r);self.frame();self.package()
        r['body']='改为纪实风格';self.record(r);self.assertTrue(self.store.package('P')['issues'])
    def test_grid_order_and_gaps(self):
        self.confirm();r=self.base('G','grid');r['data']={'cells':[{'shot_id':s} for s in reversed(self.ids)]}
        with self.assertRaises(ValueError):self.record(r)
    def test_frames_missing_and_timeline_invalid(self):
        self.confirm();self.frame();r=self.package();r['data']['timeline'][1]['start']=2;self.record(r)
        self.assertTrue(any('交叠' in x for x in self.store.package('P')['issues']))
        r['data']['references']=[];r['depends_on'].remove('G');self.record(r)
        self.assertTrue(any('分镜图' in x for x in self.store.package('P')['issues']))
    def test_audio_reference_is_not_native_lipsync(self):
        self.confirm();self.frame();r=self.package();r['data']['speech']='dialogue';self.record(r)
        self.assertTrue(any('音频' in x for x in self.store.package('P')['issues']))
        import wave
        with wave.open(str(self.root/'line.wav'),'wb') as f:
            f.setnchannels(1);f.setsampwidth(2);f.setframerate(8000);f.writeframes(bytes(48000))
        v=self.base('V','voice');v['files']=[{'path':'line.wav','role':'dialogue'}];v['data']={'voice_id':'fixture','text':'你好','duration_seconds':3,'adoption_evidence':'用户试听采用'};self.record(v)
        r['depends_on'].append('V');r['data']['references'].append({'record_id':'V','file_path':'line.wav','label':'音频1','purpose':'完整对白'})
        r['data']['audio_capability']={'preserves_recording':True,'evidence':'仅音频参考'};self.record(r)
        self.assertTrue(any('口型' in x for x in self.store.package('P')['issues']))
        r['data']['audio_capability']['native_lipsync']=True;self.record(r)
        self.assertEqual(self.store.package('P')['issues'],[])
        v['data'].pop('voice_id');v['data']['source_evidence']='已选合成来源未提供声线ID';self.record(v)
        self.record(r)
        self.assertEqual(self.store.package('P')['issues'],[])
    def test_previs_requires_approvals_and_video_reference(self):
        self.confirm();self.frame();self.path_decision('blender_previs');r=self.package();r['data']['route']='previs';self.record(r)
        self.assertTrue(any('预演' in x for x in self.store.package('P')['issues']))
    def test_previs_pending_object_cannot_authorize_export(self):
        self.confirm();self.frame();self.path_decision('blender_previs');pkg=self.package()
        (self.root/'previs.mp4').write_bytes(b'offline-fixture-not-media')
        pre=self.base('PRE','previs');pre['files']=[{'path':'previs.mp4','role':'reference_video'}]
        good={'status':'adopted','evidence':'用户看过本版并采用'}
        cases=[({'status':'pending','evidence':''},False),
               ({'status':'proceed_authorized','evidence':'继续制作'},False),
               ({'status':'adopted','evidence':'  '},False),
               (True,False),('pending',False),(good,True)]
        for value,allowed in cases:
            with self.subTest(value=value):
                pre['data']={'static_adoption':good,'dynamic_adoption':value,'adoption_evidence':'记录的总体说明'}
                self.record(pre)
                pkg['depends_on']=['G','PATH','PRE'];pkg['data']['route']='previs'
                pkg['data']['references']=[pkg['data']['references'][0],{'record_id':'PRE','file_path':'previs.mp4','label':'白模1','purpose':'机位与运动'}]
                self.record(pkg)
                issues=self.store.package('P')['issues']
                self.assertEqual(not any('预演' in i for i in issues),allowed)
                if not allowed:
                    with self.assertRaises(Conflict):self.store.package('P',self.root/'rejected')
                    self.assertFalse((self.root/'rejected').exists())
                else:self.assertEqual(issues,[])
    def test_shared_record_body_rendered_once_and_linked(self):
        self.confirm();other=self.doc['sections'][1]['id']
        self.store.confirm(other,self.store.read()['revision'],'确认第二段')
        r=self.base('SHARED','decision',[]);r['section_ids']=[self.sid,other];r['body']='唯一的共用说明正文'
        self.record(r);md=(self.root/'分镜阅览.md').read_text()
        self.assertEqual(md.count('唯一的共用说明正文'),1)
        self.assertIn('#record-',md)
    def test_manual_automatic_same_package_dedup_and_history(self):
        self.confirm();self.frame();r=self.package()
        r['data']['references'].append({**r['data']['references'][0],'label':'图片2'});self.record(r)
        out=self.root/'handoff';self.store.package('P',out)
        manifest=json.loads((out/'manifest.json').read_text())
        self.assertEqual(manifest['record']['data']['parameters'],r['data']['parameters'])
        self.assertEqual(len(list(out.glob('*.png'))),1)
        self.assertEqual((out/'提示词.txt').read_text().strip(),r['data']['prompt'])
        with self.assertRaises(Conflict):self.store.package('P',out)
        task=self.base('T','task');task['data']={'package_id':'P','package_version':1,'status':'submitted','thread_id':'offline-fixture'};self.record(task)
        d=self.store.read();d['sections'][0]['groups'][0]['shots'][0]['content']='新稿';self.store.update(d,d['revision'])
        result=self.base('R','result');result['data']={'package_id':'P','package_version':1,'origin':'manual','feedback':'用户报告，尚未实际观看'};self.record(result)
        self.assertTrue(any(x['id']=='R' for x in self.store.read()['production']['records']))
    def test_deleted_shot_and_section_still_accept_historical_result(self):
        self.confirm();self.frame();self.package()
        d=self.store.read();d['sections'].pop(0);self.store.update(d,d['revision'])
        r=self.base('R','result');r['data']={'package_id':'P','package_version':1,'origin':'manual'}
        self.record(r)
        self.assertTrue(any(x['id']=='R' for x in self.store.read()['production']['records']))
        r['shot_ids']=['invented']
        with self.assertRaises(ValueError):self.record(r)
    def test_duplicate_out_of_bounds_and_missing_grid_box_block_handoff(self):
        self.confirm();self.frame();self.package()
        g=copy.deepcopy(self.store.read()['production']['records'][0])
        for box in ([0,0,1,1],[1,0,3,1],None):
            g['data']['cells'][1]['box']=box;self.record(g);self.package()
            self.assertTrue(any('画格' in x for x in self.store.package('P')['issues']))
    def test_dependency_cycles_rejected(self):
        self.confirm();a=self.base('A','decision');self.record(a);b=self.base('B','decision');b['depends_on']=['A'];self.record(b)
        a['depends_on']=['B']
        with self.assertRaises(ValueError):self.record(a)
    def test_incomplete_package_not_exported(self):
        self.confirm();r=self.base('P','package');self.record(r)
        with self.assertRaises(Conflict):self.store.package('P',self.root/'must-not-exist')
        self.assertFalse((self.root/'must-not-exist').exists())

if __name__=='__main__':unittest.main()
