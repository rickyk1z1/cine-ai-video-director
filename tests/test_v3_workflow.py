"""User journeys from the independent audit. Isolated stores, no paid generation."""
import copy
import json
import unittest
import wave
import shutil
import subprocess
import threading
from pathlib import Path
from unittest.mock import patch
import production
import rehearsal
import storyboard
import test_production as fixtures

class WorkflowV3Tests(unittest.TestCase):
    def setUp(self):
        self.t=fixtures.ProductionTests();self.t.setUp();self.addCleanup(self.t.doCleanups)
        doc=self.t.store.read()
        for shot in doc["sections"][0]["groups"][0]["shots"]:shot["duration"]=3
        self.t.store.update(doc,doc["revision"])
        self.t.confirm()
    def entry(self):
        r=self.t.base('ENTRY','decision');r['data']={'decision_type':'image_stage_entry','batch_id':'batch','selection_evidence':'好','selection_context':'是否开始本批图片制作？'}
        self.t.record(r)
    def picture(self, rid='FRAME', sid=None, status='adopted'):
        t=self.t;sid=sid or t.ids[0]
        (t.root/(rid+'.png')).write_bytes(b'nonempty structural file fixture; not a media quality claim')
        r=t.base(rid,'asset',[sid]);r['files']=[{'path':rid+'.png','role':'storyboard_frame'}]
        r['data']={'asset_role':'storyboard_frame','status':status}
        if status=='adopted':r['data']['adoption_evidence']='用户采用这张图'
        t.record(r);return r
    def sequence(self, result='ready'):
        t=self.t;doc=t.store.read();m=rehearsal.manifest(doc,t.root,section_ids=[t.sid]);r=t.base('SEQUENCE','decision')
        r['data']={'decision_type':'sequence_review','review_version':3,'manifest':m,'summary':'两镜从递接到使用，人物对象及观看目的清楚。','result':result,
                   'continuity_review':{'units':[{'id':sid,'shot_id':sid} for sid in t.ids], 'joins':[{'from':t.ids[0],'to':t.ids[1],'type':'action_cut','audience_bridge':'同一对象','evidence':'本次两格图','budget_check':'两镜各三秒','status':'resolved'}]}}
        t.store.record(r,doc['revision']);return r
    def v3_package(self):
        t=self.t;t.frame();r=t.package();self.sequence()
        data=r['data'];data['prompt']='保留动作音效，不生成音乐。参考图仅提供指定属性，不按图片顺序演变，不强制复现整幅构图。\n\n按两镜的交接动作顺接，全画幅呈现。'
        data['prompt_review']={'review_version':3,'prompt':data['prompt'],
            'reference_policy':[{'id':'计划图片1','type':'image','use':'两镜空间与身份','not_required':'整幅构图和状态定格','mode':'reference'}],
            'requirements':[], 'continuity_review':{'units':[{'id':sid,'shot_id':sid} for sid in t.ids],
            'joins':[{'from':t.ids[0],'to':t.ids[1],'type':'cut','audience_bridge':'同一动作','evidence':'本批相邻图','budget_check':'各三秒','status':'unverified'}]}}
        return r
    def test_revise_adds_shot_without_reconfirming_or_resetting_phase(self):
        t=self.t;self.entry();self.picture()
        d=t.store.read();shot=storyboard.new_shot();shot.update(number='new',content='新增的反应镜头',duration=2);d['sections'][0]['groups'][0]['shots'].append(shot)
        out=t.store.transact({'document':d,'evidence':'图稿阶段增加一个反应镜头，文字与图一起改'},d['revision'],revise=True)
        self.assertEqual(out['_section_status'][t.sid],'changed');self.assertEqual(out['_workflow']['scopes'][0]['phase'],1)
        self.picture('NEW',shot['id'],'candidate')
        self.assertEqual(t.store.read()['_preview_rows'][2]['status'],'candidate')
        self.assertEqual(len(t.store.read()['production']['confirmations'][t.sid]['history']),0)
    def test_uniform_route_survives_and_extends_to_new_shot(self):
        t=self.t;self.entry();t.path_decision()
        d=t.store.read();shot=storyboard.new_shot();shot.update(number='third',content='补充交代',duration=2);d['sections'][0]['groups'][0]['shots'].append(shot)
        out=t.store.transact({'document':d,'evidence':'本批补一个镜头，仍按刚才直投路线'},d['revision'],revise=True)
        route=next(r for r in out['production']['records'] if r['id']=='PATH')
        self.assertIn(shot['id'],route['shot_ids']);self.assertEqual(out['_workflow']['scopes'][0]['phase'],2)
        self.assertEqual(route['data']['selection_evidence'],'用户明确选择本批制作路径')
    def test_untouched_sibling_record_not_blocked_by_local_edit(self):
        t=self.t;r=self.picture(sid=t.ids[1]);d=t.store.read();d['sections'][0]['groups'][0]['shots'][0]['content']='修改另一镜';t.store.update(d,d['revision'])
        self.assertFalse(production.is_stale(t.store.read(),next(x for x in t.store.read()['production']['records'] if x['id']==r['id']),t.root))
        r['body']='补充未改镜头说明';t.record(r)
    def test_image_timing_change_not_visual_change(self):
        t=self.t;r=self.picture();d=t.store.read();d['sections'][0]['groups'][0]['shots'][0]['duration']=10;t.store.update(d,d['revision'])
        self.assertEqual(t.store.read()['_preview_rows'][0]['status'],'adopted')
        d=t.store.read();d['sections'][0]['groups'][0]['shots'][0]['content']='完全不同动作';t.store.update(d,d['revision'])
        row=t.store.read()['_preview_rows'][0];self.assertEqual(row['status'],'needs_review');self.assertEqual(len(row['images']),1)
    def test_candidate_option_does_not_cancel_selected_frame(self):
        self.picture();self.picture('OPTION',status='candidate')
        row=self.t.store.read()['_preview_rows'][0];self.assertEqual(row['status'],'adopted');self.assertEqual(len(row['images']),2)
    def test_old_adoption_evidence_cannot_override_revise_or_excluded(self):
        r=self.picture();r['data']['review_status']='revise';self.t.record(r)
        self.assertNotEqual(self.t.store.read()['_preview_rows'][0]['status'],'adopted')
        r['data']['status']='excluded';self.t.record(r)
        self.assertEqual(self.t.store.read()['_preview_rows'][0]['images'],[])
    def test_same_file_can_represent_two_explicit_moments(self):
        t=self.t;r=self.picture();r['files']=[{'path':'FRAME.png','role':'state_start'},{'path':'FRAME.png','role':'state_end'}];t.record(r)
        self.assertEqual(len(t.store.read()['_preview_rows'][0]['images']),2)
    def test_preview_and_rehearsal_share_multistate_order(self):
        t=self.t;r=self.picture()
        cases=[
            # Reversed files must not reverse the storyboard preview.
            ([('end','state_end',3),('middle','storyboard_frame',2),('start','state_start',1)],['start','middle','end']),
            # Explicit numeric order takes precedence even over endpoint labels.
            ([('end','state_end',1),('middle','storyboard_frame',2),('start','state_start',3)],['end','middle','start']),
            ([('end','end_frame',None),('middle','storyboard_frame',None),('start','start_frame',None)],['start','middle','end']),
            # No order declaration: preserve every file and its original order.
            ([('third','storyboard_frame',None),('first','storyboard_frame',None),('second','storyboard_frame',None)],['third','first','second']),
        ]
        for files,expected in cases:
            with self.subTest(expected=expected):
                r['files']=[]
                for name,role,order in files:
                    path=name+'.png';(t.root/path).write_bytes(name.encode())
                    r['files'].append({'path':path,'role':role,**({'sequence_order':order} if order is not None else {})})
                t.record(r);doc=t.store.read()
                preview=doc['_preview_rows'][0]['images']
                manifest=rehearsal.manifest(doc,t.root,shot_ids=[t.ids[0]])
                self.assertEqual([Path(i['path']).stem for i in preview],expected)
                self.assertEqual([i['path'] for i in preview],[i['path'] for i in manifest['frames'][0]['images']])
                self.assertEqual(len(preview),len(files));self.assertEqual(manifest['issues'],[])
                self.assertTrue(all(i['review_status']=='adopted' for i in preview))
    def test_state_order_does_not_adopt_candidates_or_hide_ambiguity(self):
        t=self.t
        for name,role,status in [('END','state_end','adopted'),('MIDDLE','storyboard_frame','adopted'),('START','state_start','adopted'),('OPTION','storyboard_frame','candidate')]:
            r=self.picture(name,status=status);r['files'][0]['role']=role;t.record(r)
        doc=t.store.read();preview=doc['_preview_rows'][0]['images']
        self.assertEqual([i['record_id'] for i in preview],['START','MIDDLE','OPTION','END'])
        self.assertEqual(next(i for i in preview if i['record_id']=='OPTION')['review_status'],'candidate')
        manifest=rehearsal.manifest(doc,t.root,shot_ids=[t.ids[0]])
        self.assertEqual([i['record_id'] for i in manifest['frames'][0]['images']],['START','MIDDLE','END'])
        self.assertTrue(any('顺序不明确' in issue for issue in manifest['issues']))
    def test_unplaced_candidate_does_not_reverse_numbered_adopted_states(self):
        t=self.t
        for name,order,status in [('THIRD',3,'adopted'),('OPTION',None,'candidate'),('FIRST',1,'adopted'),('SECOND',2,'adopted')]:
            r=self.picture(name,status=status)
            if order is not None:r['files'][0]['sequence_order']=order
            t.record(r)
        doc=t.store.read();preview=doc['_preview_rows'][0]['images']
        self.assertEqual([i['record_id'] for i in preview],['FIRST','OPTION','SECOND','THIRD'])
        manifest=rehearsal.manifest(doc,t.root,shot_ids=[t.ids[0]])
        self.assertEqual([i['record_id'] for i in manifest['frames'][0]['images']],['FIRST','SECOND','THIRD'])
        self.assertEqual(manifest['issues'],[])
        self.assertEqual(preview[1]['review_status'],'candidate')
    def test_auto_merge_disjoint_edits_and_keep_overlap_conflict(self):
        store=self.t.store;base=store.read();a=copy.deepcopy(base);a['sections'][0]['groups'][0]['shots'][0]['content']='另一页的改动';store.update(a,base['revision'])
        b=copy.deepcopy(base);b['sections'][0]['groups'][0]['shots'][1]['content']='本页不同镜头';merged=store.update(b,base['revision'],base)
        self.assertEqual(merged['sections'][0]['groups'][0]['shots'][0]['content'],'另一页的改动')
        b['sections'][0]['groups'][0]['shots'][0]['content']='同字段冲突'
        with self.assertRaises(storyboard.Conflict):store.update(b,base['revision'],base)
    def test_transaction_failure_is_atomic(self):
        t=self.t;before=t.store.path.read_bytes();d=t.store.read();d['title']='不能部分提交';r=t.base('BROKEN','asset');r['files']=[{'path':'missing.png','role':'image'}]
        with self.assertRaises(ValueError):t.store.transact({'document':d,'records':[r]},d['revision'])
        self.assertEqual(t.store.path.read_bytes(),before)
    def test_prepare_binds_exact_input_in_one_call_and_keeps_warnings(self):
        t=self.t;r=self.v3_package();r['data'].pop('production_batch_id');r['depends_on']=[]
        result=t.store.prepare(r,t.store.read()['revision'])
        self.assertEqual(result['issues'],[]);self.assertTrue(any(w.get('kind')=='unverified_join' for w in result['warnings']))
        self.assertEqual(result['input_sha256'],result['record']['data']['prompt_review']['input_sha256'])
        self.assertEqual(result['record']['data']['sequence_review_id'],'SEQUENCE')
    def test_review_happens_once_then_user_revision_continues(self):
        t=self.t;r=self.v3_package();doc=t.store.read();review=next(x for x in doc['production']['records'] if x['id']=='SEQUENCE');review['data']['result']='revise';t.store.record(review,doc['revision'])
        self.entry();doc=t.store.read();doc['sections'][0]['groups'][0]['shots'][0]['notes']='用户决定保留此方案';t.store.transact({'document':doc,'evidence':'按我人工修改的版本继续'},doc['revision'],revise=True)
        receipt=production.sequence_receipt(t.store.read(),r)
        self.assertEqual(receipt['id'],'SEQUENCE');self.assertEqual(receipt['data']['result'],'revise')
        self.assertEqual(len([x for x in t.store.read()['production']['records'] if x['data'].get('decision_type')=='sequence_review']),1)
        self.assertGreaterEqual(t.store.read()['_workflow']['scopes'][0]['phase'],1)
    def test_unrelated_unit_cannot_pass_actual_package_coverage(self):
        t=self.t;t.frame();t.package();r=next(x for x in t.store.read()['production']['records'] if x['id']=='P');r['data']['prompt_review']['continuity_review']={'units':['unrelated'],'joins':[]};t.store.record(r,t.store.read()['revision'])
        self.assertTrue(t.store.package('P')['issues'])
    def test_sound_does_not_turn_unplanned_voice_into_silence(self):
        scope={'video_count':1,'evidence':'本次一整条'};doc={'production':{'records':[{'id':'D','data':{'output_scope':scope}}]}}
        r={'data':{'output_scope':scope,'production_path_decision_id':'D','sound_plan':{'policy':'single_video','tracks':[]},'prompt':'视频静音，无配音、音乐和音效。'}}
        self.assertTrue(production.sound_issues(doc,r))
        r['data']['sound_plan']['silence_evidence']='用户明确采用无声表现';self.assertEqual(production.sound_issues(doc,r),[])
        r['data']['sound_plan']['tracks']=[{'role':'sfx','implementation':'native','description':'脚步声'}]
        self.assertTrue(production.sound_issues(doc,r))
        r['data']['prompt']='无音乐，保留脚步音效。';self.assertEqual(production.sound_issues(doc,r),[])
    def test_choice_and_generated_advice_are_distinct(self):
        t=self.t;self.entry();r=t.base('PLAN','decision');r['data']={'decision_type':'generation_recommendation','groups':[{'shot_ids':t.ids,'input_mode':'首帧图生','reason':'单一起点足够'}],
            'options':[{'path':'direct_platform','label':'直接生成','recommended':True},{'path':'previs_reference','label':'先Blender预演','tool':'Blender'}]}
        t.record(r);self.assertFalse(production.permission_shots(t.store.read(),'production_path'))
        out=t.store.choose_route('PLAN','previs_reference',t.store.read()['revision']);choice=next(x for x in out['production']['records'] if x['id']=='route-PLAN')
        self.assertEqual(choice['data']['path'],'previs_reference');self.assertEqual(choice['data']['recommended_path'],'direct_platform')
        self.assertNotIn('platform',choice['data'])
    def test_one_read_does_not_rehash_shared_file_for_every_dependency(self):
        t=self.t;self.picture();r=t.base('D','decision');r['depends_on']=['FRAME'];t.record(r)
        with patch.object(production.Path,'open',autospec=True,side_effect=Path.open) as opened:
            with production.evaluation():
                production.preview_rows(t.store.read(),t.root)
                production.preview_rows(t.store.read(),t.root)
            calls=[c for c in opened.call_args_list if str(c.args[0]).endswith('FRAME.png')]
        self.assertLessEqual(len(calls),2)

    def test_visual_asset_and_group_instructions_invalidate_frames(self):
        t=self.t;self.picture();d=t.store.read();d['sections'][0]['groups'][0]['shots'][0]['assets']='改用另一人物和参考图';t.store.update(d,d['revision'])
        self.assertEqual(t.store.read()['_preview_rows'][0]['status'],'needs_review')
        self.entry();self.picture();d=t.store.read();d['sections'][0]['groups'][0]['notes']='本组改为深夜暴雨';t.store.update(d,d['revision'])
        self.assertEqual(t.store.read()['_preview_rows'][0]['status'],'needs_review')
    def test_revise_does_not_resurrect_an_older_route(self):
        t=self.t;self.entry();first=t.path_decision();second=copy.deepcopy(first);second['id']='PATH2';second['data'].update(path='previs_reference',assignments=[{'path':'previs_reference','tool':'Blender','shot_ids':t.ids}]);t.record(second)
        t.record(first);before=t.store.read();self.assertEqual(production.current_routes(before)[t.ids[0]]['id'],'PATH')
        d=copy.deepcopy(before);sh=storyboard.new_shot();sh.update(content='新增同范围镜头',duration=2);d['sections'][0]['groups'][0]['shots'].append(sh)
        out=t.store.transact({'document':d,'evidence':'当前作品补这一镜，沿用刚才路线'},d['revision'],revise=True)
        self.assertEqual(production.current_routes(out)[sh['id']]['id'],'PATH')
        self.assertEqual(next(r for r in out['production']['records'] if r['id']=='PATH2')['version'],1)
    def test_first_sequence_review_requires_actual_adopted_inputs(self):
        t=self.t;d=t.store.read();m=rehearsal.manifest(d,t.root,section_ids=[t.sid]);r=t.base('EMPTY-REVIEW','decision');r['data']={'decision_type':'sequence_review','manifest':m,'result':'ready','summary':'无图不能冒充已看过'}
        with self.assertRaisesRegex(ValueError,'输入尚不完整'):t.store.record(r,d['revision'])
    def test_partial_and_excluded_sequence_are_not_whole_receipts(self):
        t=self.t;self.picture();d=t.store.read();m=rehearsal.manifest(d,t.root,shot_ids=[t.ids[0]]);r=t.base('PARTIAL','decision',[t.ids[0]]);r['data']={'decision_type':'sequence_review','manifest':m,'result':'ready','summary':'只看第一镜'};t.record(r)
        plan=t.base('PLAN','decision');plan['data']={'decision_type':'generation_recommendation'};t.record(plan)
        self.assertIsNone(production.sequence_receipt(t.store.read(),t.base('P','package')))
        self.assertNotIn('PLAN',t.store.read()['_sequence_receipts'])
        # Keep one unambiguous adopted state per shot. Adding the grid here would
        # overlap FRAME for the first shot and invalidate the review fixture.
        self.picture('SECOND',t.ids[1]);self.sequence()
        self.assertEqual(t.store.read()['_sequence_receipts']['PLAN'],'SEQUENCE')
        d=t.store.read();r=next(r for r in d['production']['records'] if r['id']=='SEQUENCE');r['data']['status']='excluded';t.record(r)
        self.assertIsNone(production.sequence_receipt(t.store.read(),t.base('P','package')))
        self.assertNotIn('PLAN',t.store.read()['_sequence_receipts'])
    def test_external_audio_exclusion_is_enforced(self):
        t=self.t;t.frame();r=t.package()
        with wave.open(str(t.root/'external.wav'),'wb') as f:f.setnchannels(1);f.setsampwidth(2);f.setframerate(8000);f.writeframes(bytes(3*16000))
        voice=t.base('VOICE','voice');voice['files']=[{'path':'external.wav','role':'narration'}];voice['data']={'source_type':'recorded','source_duration':3,'source_evidence':'隔离测试录音','text':'测试台词','status':'adopted','review_status':'excluded','adoption_evidence':'旧采用记录'};t.record(voice)
        r['depends_on'].append('VOICE');r['data'].update(speech='offscreen',audio_uses=[{'record_id':'VOICE','source_in':0,'source_out':3,'start':0,'implementation':'external_overlay','handoff':'后续贴音','authorization_evidence':'已选后续贴音'}]);t.record(r)
        self.assertTrue(any('声音' in x and '采用' in x for x in t.store.package('P')['issues']))
    @unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'),'需要已有媒体探测工具')
    def test_external_result_needs_no_invented_package_and_obeys_review_state(self):
        t=self.t;target=t.root/'external.mp4';subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','color=c=black:s=32x32:r=24:d=1','-c:v','mpeg4',str(target)],check=True)
        r=t.base('EXTERNAL','result');r['files']=[{'path':'external.mp4','role':'video'}];r['data']={'source_type':'external','source_evidence':'用户提供的既有片段','status':'adopted','adoption_evidence':'用户采用当前片段'};t.record(r)
        self.assertEqual(production.video_adopted_shots(t.store.read(),t.root),set(t.ids))
        r['data']['review_status']='revise';t.record(r);self.assertEqual(production.video_adopted_shots(t.store.read(),t.root),set())
        r['data'].update(status='partially_adopted',adopted_shot_ids=['unknown']);
        with self.assertRaises(ValueError):t.record(r)
    def test_prepare_uses_its_locked_snapshot(self):
        t=self.t;r=self.v3_package();seen=[];original=t.store.package
        attempted=threading.Event();finished=threading.Event();errors=[];threads=[]
        def capture(*args,**kwargs):
            snapshot=kwargs.get('_snapshot');seen.append(snapshot)
            newer=copy.deepcopy(next(x for x in snapshot['production']['records'] if x['id']==r['id']))
            newer['data']['prompt']+=' 另一窗口的新版本。'
            newer['data']['prompt_review']['prompt']=newer['data']['prompt']
            def write_newer():
                attempted.set()
                try:storyboard.Store(t.root).prepare(newer,snapshot['revision'])
                except Exception as exc:errors.append(exc)
                finally:finished.set()
            worker=threading.Thread(target=write_newer,daemon=True);threads.append(worker);worker.start()
            self.assertTrue(attempted.wait(2))
            self.assertFalse(finished.wait(.1),'A second writer must wait until this handoff is complete')
            return original(*args,**kwargs)
        try:
            with patch.object(t.store,'package',side_effect=capture):result=t.store.prepare(r,t.store.read()['revision'])
        finally:
            for worker in threads:worker.join(5)
        self.assertTrue(finished.is_set());self.assertEqual(errors,[])
        self.assertIsNotNone(seen[0]);self.assertEqual(result['revision'],seen[0]['revision']);self.assertEqual(result['record']['data']['prompt'],r['data']['prompt'])
        self.assertEqual(result['input_sha256'],result['record']['data']['prompt_review']['input_sha256'])
        self.assertEqual(t.store.read()['revision'],result['revision']+1)
        self.assertNotEqual(t.store.package(r['id'])['record']['data']['prompt'],result['record']['data']['prompt'])

if __name__=='__main__':unittest.main()
