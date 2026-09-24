"""Production regression cases: real temporary stores/files, never user projects."""
import copy,hashlib,json,shutil,subprocess,wave
import unittest
import test_production as production_tests
import test_prompt_guard as guard_tests
guard=guard_tests.guard
import production
from storyboard import Conflict

class BoundaryTests(unittest.TestCase):
 def setUp(self):
  self.t=production_tests.ProductionTests();self.t.setUp();self.addCleanup(self.t.doCleanups)
  self.t.confirm();self.t.frame();self.t.package()
 def pkg(self):return copy.deepcopy(next(r for r in self.t.store.read()['production']['records'] if r['id']=='P'))
 def issues(self):return self.t.store.package('P')['issues']
 def raw(self,r):return self.t.store.record(r,self.t.store.read()['revision'])
 def sound(self,count,tracks,**scope_extra):
  t=self.t;scope={'video_count':count,'evidence':'本次用户要求',**scope_extra}
  decision=copy.deepcopy(next(r for r in t.store.read()['production']['records'] if r['id']=='PATH'))
  decision['data']['output_scope']=scope;t.record(decision)
  r=self.pkg();r['data']['output_scope']=scope;r['data']['sound_plan']={'policy':'effects_only' if count>1 or scope_extra.get('part_of_multi_video') else 'single_video','tracks':tracks}
  r['data']['audio_capability']={'native_music':True,'evidence':'离线入口能力声明'};t.record(r)
 def test_cancel_blocks_confirm_record_and_export_but_preserves_history(self):
  t=self.t;r=t.base('C','decision');r['data']={'decision_type':'scope_cancellation','production_required':False};t.record(r)
  with self.assertRaises(ValueError):t.confirm()
  with self.assertRaises(ValueError):t.record(self.pkg())
  with self.assertRaises(Conflict):t.store.package('P',t.root/'no-export')
  self.assertFalse((t.root/'no-export').exists());self.assertIn('无需制作',(t.root/'分镜阅览.md').read_text())
 def test_static_adoption_is_not_video_adoption(self):
  t=self.t;g=copy.deepcopy(t.store.read()['production']['records'][0]);g['data']['status']='adopted';t.record(g)
  self.assertNotIn('本段视频素材已采用',(t.root/'分镜阅览.md').read_text())
 def test_video_adoption_is_bound_to_actual_design(self):
  t=self.t;(t.root/'result.mp4').write_bytes(b'fixture only, not a media-quality test')
  r=t.base('R','result');r['files']=[{'path':'result.mp4','role':'video'}];r['data']={'package_id':'P','package_version':1,'status':'adopted','adoption_evidence':'测试用户采用'};t.record(r)
  self.assertIn('本段视频素材已采用',(t.root/'分镜阅览.md').read_text())
  d=t.store.read();d['sections'][0]['groups'][0]['shots'][0]['content']='new action';t.store.update(d,d['revision'])
  self.assertNotIn('本段视频素材已采用',(t.root/'分镜阅览.md').read_text())
 def test_reviewed_grid_need_not_be_uploaded(self):
  r=self.pkg();r['data']['references']=[];self.t.record(r);self.assertEqual(self.issues(),[])
 def test_missing_review_and_changed_inputs_rejected(self):
  r=self.pkg();r['data'].pop('prompt_review');self.raw(r);self.assertTrue(any('出稿' in i for i in self.issues()))
  self.t.record(r);r=self.pkg();r['data']['parameters']['resolution']='720p';self.raw(r)
  self.assertTrue(any('绑定' in i for i in self.issues()))
  with self.assertRaises(Conflict):self.t.store.package('P',self.t.root/'bad')
 def test_reference_order_is_part_of_review(self):
  r=self.pkg();r['data']['references'].append({**r['data']['references'][0],'label':'second'});self.t.record(r)
  r=self.pkg();r['data']['references'].reverse();self.raw(r)
  self.assertTrue(any('顺序' in i or '绑定' in i for i in self.issues()))
 def test_same_batch_new_invocation_and_title_do_not_stale(self):
  r=self.pkg();r['data']['production_invocation_id']='continued';self.t.record(r)
  d=self.t.store.read();d['title']='new title';d['sections'][0]['title']='renamed section';d['sections'][0]['groups'][0]['title']='renamed group';self.t.store.update(d,d['revision'])
  self.assertEqual(self.issues(),[])
 def test_legacy_title_only_uses_historical_snapshot(self):
  t=self.t;d=t.store.read();r=copy.deepcopy(next(x for x in d['production']['records'] if x['id']=='PATH'));r.pop('_binding_version');r['_dependency']=production.fingerprint(d,r,t.root)
  d['title']='new';d['sections'][0]['title']='new section';d['sections'][0]['groups'][0]['title']='new group'
  self.assertFalse(production.is_stale(d,r,t.root))
  d['sections'][0]['groups'][0]['shots'][0]['content']='different action';self.assertFalse(production.is_stale(d,r,t.root))  # A scoped route choice survives creative revisions.
 def test_one_video_multiple_shots_allows_native_music(self):
  self.sound(1,[{'role':'music','implementation':'native','description':'器乐配乐'}]);self.assertEqual(self.issues(),[])
 def test_one_complete_video_does_not_require_music(self):
  self.sound(1,[{'role':'sfx','implementation':'native','description':'动作音效'}]);self.assertEqual(self.issues(),[])
 def test_multiple_outputs_disallow_music_and_ambience(self):
  for role in ('music','ambience'):
   self.sound(3,[{'role':role,'implementation':'native','description':'铺底'}]);self.assertTrue(any('多条' in i for i in self.issues()))
 def test_multiple_outputs_keep_specific_event_sound(self):
  self.sound(3,[{'role':'sfx','implementation':'native','description':'开门与脚步声'}]);self.assertEqual(self.issues(),[])
 def test_one_call_in_multiple_video_batch_is_not_exception(self):
  self.sound(1,[{'role':'music','implementation':'native','description':'音乐'}],part_of_multi_video=True)
  self.assertTrue(any('多条' in i for i in self.issues()))
 def test_partial_result_adopts_only_named_good_shot(self):
  t=self.t;(t.root/'result.mp4').write_bytes(b'historical test result')
  r=t.base('PARTIAL','result');r['files']=[{'path':'result.mp4','role':'video'}]
  r['data']={'package_id':'P','package_version':1,'status':'partially_adopted','adopted_shot_ids':[t.ids[0]],'adoption_evidence':'用户确认第一镜可保留'}
  t.record(r)
  self.assertEqual(production.video_adopted_shots(t.store.read(),t.root),{t.ids[0]})
  self.assertIn('部分镜头视频素材已采用',(t.root/'分镜阅览.md').read_text())
  r['data']['adopted_shot_ids']=['outside']
  with self.assertRaises(ValueError):t.record(r)
 def test_one_video_can_mix_local_previs_with_direct_shot(self):
  t=self.t;scope={'video_count':1,'evidence':'一次生成整段两镜视频'}
  path=copy.deepcopy(next(r for r in t.store.read()['production']['records'] if r['id']=='PATH'))
  path['data'].update(path='hybrid',output_scope=scope,assignments=[{'path':'direct_platform','shot_ids':[t.ids[0]]},{'path':'blender_previs','shot_ids':[t.ids[1]]}]);t.record(path)
  (t.root/'previs.mp4').write_bytes(b'white model reference fixture')
  pre=t.base('PRE','previs',[t.ids[1]]);pre['files']=[{'path':'previs.mp4','role':'reference_video'}]
  pre['data']={'adoption_evidence':'用户采用第二镜白模依据','static_adoption':{'status':'adopted','evidence':'已审静态空间'},'dynamic_adoption':{'status':'adopted','evidence':'已审路径'}};t.record(pre)
  p=self.pkg();p['depends_on'].append('PRE');p['data'].update(route='hybrid',output_scope=scope,sound_plan={'policy':'single_video','tracks':[{'role':'music','implementation':'native','description':'整段配乐'}]},audio_capability={'native_music':True,'evidence':'离线能力样例'})
  p['data']['references'].append({'record_id':'PRE','file_path':'previs.mp4','label':'白模路径','purpose':'仅第二镜的空间与运镜'});t.record(p)
  self.assertEqual(self.issues(),[])
  out=t.root/'mixed';t.store.package('P',out)
  self.assertEqual(len(json.loads((out/'manifest.json').read_text())['references']),2)
  p=self.pkg();p['data']['references'].pop();t.record(p)
  self.assertTrue(any('预演镜头' in i for i in self.issues()))
 def test_other_previs_tool_can_supply_one_shot_in_mixed_video(self):
  t=self.t;scope={'video_count':1,'evidence':'本次生成一个含两镜的视频'}
  path=copy.deepcopy(next(r for r in t.store.read()['production']['records'] if r['id']=='PATH'))
  path['data'].update(path='hybrid',output_scope=scope,assignments=[{'path':'direct_platform','shot_ids':[t.ids[0]]},{'path':'previs_reference','tool':'selected 3D editor','shot_ids':[t.ids[1]]}]);t.record(path)
  (t.root/'previs.mp4').write_bytes(b'previsualization reference fixture')
  pre=t.base('PRE','previs',[t.ids[1]]);pre['files']=[{'path':'previs.mp4','role':'reference_video'}]
  pre['data']={'adoption_evidence':'用户采用预演参考','static_adoption':{'status':'adopted','evidence':'空间已审'},'dynamic_adoption':{'status':'adopted','evidence':'运动已审'}};t.record(pre)
  p=self.pkg();p['depends_on'].append('PRE');p['data'].update(route='hybrid',output_scope=scope,sound_plan={'policy':'single_video','tracks':[]})
  p['data']['references'].append({'record_id':'PRE','file_path':'previs.mp4','label':'预演参考','purpose':'第二镜空间与运镜'});t.record(p)
  self.assertEqual(self.issues(),[])
  path['data']['assignments'][1].pop('tool')
  with self.assertRaises(ValueError):t.record(path)
 def test_native_generated_dialogue_needs_real_capability_evidence(self):
  p=self.pkg();p['data']['speech']='dialogue';p['data']['audio_uses']=[{'implementation':'native_generation','text':'你好。','speaker':'访客'}]
  p['data']['prompt']='按采用两镜切换，全画幅输出。访客说“你好。”，画面与口型同步。'
  p['data']['sound_plan']['tracks']=[{'role':'dialogue','implementation':'native','description':'访客的原生对白'}]
  p['data']['audio_capability']={'native_speech':True,'native_lipsync':True,'evidence':'本次入口能力依据'};self.t.record(p)
  self.assertEqual(self.issues(),[])
  p['data']['audio_capability']['native_lipsync']=False;self.t.record(p)
  self.assertTrue(any('口型' in i for i in self.issues()))
  p['data']['audio_capability']['native_lipsync']=True;p['data']['prompt']='只按采用两镜切换。';self.t.record(p)
  self.assertTrue(any('实际投喂正文' in i for i in self.issues()))
 def repair_fixture(self):
  t=self.t
  if not shutil.which('ffmpeg'):self.skipTest('ffmpeg unavailable')
  subprocess.run(['ffmpeg','-loglevel','error','-y','-f','lavfi','-i','color=c=red:s=64x36:d=2:r=10','-f','lavfi','-i','color=c=blue:s=64x36:d=2:r=10','-f','lavfi','-i','color=c=green:s=64x36:d=2:r=10','-filter_complex','[0:v][1:v][2:v]concat=n=3:v=1:a=0[v]','-map','[v]','-c:v','mpeg4',str(t.root/'source.mp4')],check=True)
  src=t.base('SRC','result');src['files']=[{'path':'source.mp4','role':'video'}];src['data']={'package_id':'P','package_version':1,'status':'candidate'};t.record(src)
  scope={'video_count':1,'evidence':'只为原片第二镜生成替换素材'}
  path=t.base('FIXPATH','decision',[t.ids[1]]);path['data']={'decision_type':'production_path','invocation_id':'repair-1','batch_id':'repair-batch-1','output_scope':scope,'recommended_path':'direct_platform','path':'direct_platform','platform':'test-only','selection_evidence':'用户选择单镜直投','assignments':[{'path':'direct_platform','shot_ids':[t.ids[1]]}]};t.record(path)
  p=t.base('FIX','package',[t.ids[1]]);p['depends_on']=['G','SRC','FIXPATH'];p['data']=copy.deepcopy(self.pkg()['data'])
  p['data'].update(output_scope=scope,sound_plan={'policy':'effects_only','tracks':[{'role':'sfx','implementation':'native','description':'该镜动作声'}]},route='direct',production_path_decision_id='FIXPATH',production_invocation_id='repair-1',production_batch_id='repair-batch-1',references=[],parameters={'duration':2,'ratio':'16:9','resolution':'720p'},timeline=[{'shot_id':t.ids[1],'start':0,'end':2}],prompt='只重做第二镜，保留两端实际剪点关系和该镜动作音效。')
  p['data']['repair_context']={'source_result_id':'SRC','source_result_version':1,'source_file_path':'source.mp4','source_sha256':production.file_digest(t.root,'source.mp4'),'reported_range':[2.2,3.8],'cut_range':[2,4],'isolation':'separable','cut_evidence':'实际画面在2秒和4秒硬切','left_join':'核对前镜末态','right_join':'核对后镜首态','target_duration':2,'method':'independent_clip','selection_evidence':'用户选择只重做第二镜'}
  t.record(p);return p
 def test_repair_candidate_source_and_effects_only_export(self):
  p=self.repair_fixture();self.assertEqual(self.t.store.package('FIX')['issues'],[])
  out=self.t.root/'repair';self.t.store.package('FIX',out)
  manifest=json.loads((out/'manifest.json').read_text())
  self.assertEqual(manifest['record']['data']['repair_context']['source_result_id'],'SRC')
  self.assertEqual(manifest['repair_source']['absolute_source_path'],str((self.t.root/'source.mp4').resolve()))
  p['data']['sound_plan']['tracks'].append({'role':'music','implementation':'native','description':'新音乐'})
  self.t.record(p);self.assertTrue(any('局部替换' in i for i in self.t.store.package('FIX')['issues']))
 def test_repair_rejects_changed_source_and_continuous_shot(self):
  p=self.repair_fixture()
  p['data']['repair_context']['cut_range']=[2,10];self.t.record(p)
  self.assertTrue(any('实际剪点' in i for i in self.t.store.package('FIX')['issues']))
  p['data']['repair_context'].update(cut_range=[2,4],reported_range=[0,1]);self.t.record(p)
  self.assertTrue(any('不相交' in i for i in self.t.store.package('FIX')['issues']))
  p['data']['repair_context']['reported_range']=[2.2,3.8]
  p['data']['repair_context'].update(cut_range=[2,4],isolation='continuous');self.t.record(p)
  self.assertTrue(any('独立拆出' in i for i in self.t.store.package('FIX')['issues']))
  p['data']['repair_context']['isolation']='separable';self.t.record(p)
  (self.t.root/'source.mp4').write_bytes(b'changed')
  self.assertTrue(any('来源视频文件已变化' in i for i in self.t.store.package('FIX')['issues']))
 def test_repair_cut_change_invalidates_exact_review(self):
  p=self.repair_fixture();p['data']['repair_context']['cut_range']=[2.1,3.9]
  self.t.store.record(p,self.t.store.read()['revision'])
  self.assertTrue(any('复核未绑定' in i for i in self.t.store.package('FIX')['issues']))
 def test_native_retake_requires_actual_source_reference(self):
  p=self.repair_fixture();p['data']['repair_context']['method']='native_retake';self.t.record(p)
  self.assertTrue(any('真实来源视频' in i for i in self.t.store.package('FIX')['issues']))
  p['data']['references']=[{'record_id':'SRC','file_path':'source.mp4','label':'源片','purpose':'局部重拍第二镜'}];self.t.record(p)
  self.assertEqual(self.t.store.package('FIX')['issues'],[])
 def test_native_retake_can_bind_historical_source_version(self):
  p=self.repair_fixture();t=self.t
  shutil.copy2(t.root/'source.mp4',t.root/'source2.mp4')
  src=copy.deepcopy(next(x for x in t.store.read()['production']['records'] if x['id']=='SRC'))
  src['files']=[{'path':'source2.mp4','role':'video'}];t.record(src)
  p['data']['repair_context']['method']='native_retake'
  p['data']['references']=[{'record_id':'SRC','file_path':'source.mp4','label':'旧源片','purpose':'第二镜局部重拍'}];t.record(p)
  result=t.store.package('FIX')
  self.assertEqual(result['issues'],[])
  self.assertEqual(result['review_input']['references'][0]['version'],1)
 def test_cannot_reduce_scope_in_package_alone(self):
  r=self.pkg();r['data']['output_scope']={'video_count':1,'evidence':'只提交本包'};r['data']['sound_plan']={'policy':'single_video','tracks':[],'music_exception':'静音'};self.t.record(r)
  self.assertTrue(any('本批投产决定' in i for i in self.issues()))
 def test_text_only_review_does_not_invent_images(self):
  r=self.pkg();r['depends_on'].remove('G');r['data']['references']=[];r['data']['review_basis']='text_only';r['data']['review_basis_evidence']='用户明确只以文字方案文生';r['data']['route']='direct';self.t.record(r)
  self.assertEqual(self.issues(),[])
 def audio(self):
  t=self.t
  with wave.open(str(t.root/'voice.wav'),'wb') as f:f.setnchannels(1);f.setsampwidth(2);f.setframerate(8000);f.writeframes(bytes(12*16000))
  v=t.base('VOICE','voice');v['files']=[{'path':'voice.wav','role':'narration'}];v['data']={'source_type':'recorded','source_duration':12,'text':'真人原话','source_evidence':'用户提供','adoption_evidence':'用户采用'};t.record(v)
  r=self.pkg();r['depends_on'].append('VOICE');r['data']['speech']='offscreen';r['data']['audio_uses']=[{'record_id':'VOICE','source_in':2,'source_out':5,'start':0,'implementation':'external_overlay','handoff':'片内0–3秒保留原声','authorization_evidence':'用户已授权贴原声'}];t.record(r);return r
 def test_real_recording_excerpt_exported_as_handoff_not_upload(self):
  self.audio();self.assertEqual(self.issues(),[])
  out=self.t.root/'handoff';self.t.store.package('P',out);m=json.loads((out/'manifest.json').read_text())
  self.assertEqual(len(m['audio_handoff']),1);self.assertFalse(any(x['record_id']=='VOICE' for x in m['references']))
  self.assertTrue((out/m['audio_handoff'][0]['package_path']).exists())
 def test_audio_interval_and_real_duration_enforced(self):
  r=self.audio();r['data']['audio_uses'][0]['source_out']=13;self.t.record(r);self.assertTrue(any('区间' in i for i in self.issues()))
  r['data']['audio_uses'][0]['source_out']=10;self.t.record(r);self.assertTrue(any('播放窗口' in i for i in self.issues()))
 def test_dialogue_overlay_does_not_claim_lipsync(self):
  r=self.audio();r['data']['speech']='dialogue';self.t.record(r);self.assertTrue(any('口型' in i for i in self.issues()))
  r['data']['audio_uses'][0]['implementation']='post_lipsync';self.t.record(r);self.assertEqual(self.issues(),[])
 def test_preview_uses_shot_order_and_grid_cells(self):
  rows=self.t.store.read()['_preview_rows'];self.assertEqual([x['shot_id'] for x in rows[:2]],self.t.ids)
  self.assertEqual(rows[0]['images'][0]['box'],[0,0,1,1]);self.assertEqual(rows[1]['images'][0]['box'],[1,0,2,1])
  d=self.t.store.read();d['sections'][0]['groups'][0]['shots'].reverse();self.t.store.update(d,d['revision'])
  rows=self.t.store.read()['_preview_rows'];self.assertEqual(rows[0]['shot_id'],self.t.ids[1]);self.assertEqual(rows[0]['status'],'needs_review')
 def test_preview_shows_pending_frame_then_conversation_adoption(self):
  t=production_tests.ProductionTests();t.setUp();self.addCleanup(t.doCleanups);t.confirm()
  (t.root/'near.png').write_bytes(b'pending image fixture')
  (t.root/'wrong.png').write_bytes(b'process image fixture')
  draft=t.base('LOOK','decision',[t.ids[0]])
  draft['files']=[{'path':'near.png','role':'candidate_start_state'},{'path':'wrong.png','role':'process_wrong_geometry'}]
  draft['data']={'decision_type':'static_exploration','review_status':'pending','adoption_evidence':None}
  t.record(draft)
  rows=t.store.read()['_preview_rows']
  self.assertEqual(rows[0]['status'],'candidate')
  self.assertEqual([(x['path'],x['review_status']) for x in rows[0]['images']],[('near.png','candidate')])
  self.assertEqual(rows[1]['status'],'missing')
  accepted=t.base('SELECTED','asset',[t.ids[0]])
  accepted['files']=[{'path':'near.png','role':'storyboard_frame'}]
  accepted['data']={'asset_role':'storyboard_frame','review_status':'adopted','adoption_evidence':'用户在对话中选用第一镜这张图'}
  t.record(accepted)
  rows=t.store.read()['_preview_rows']
  self.assertEqual(rows[0]['status'],'adopted')
  self.assertEqual([(x['path'],x['review_status']) for x in rows[0]['images']],[('near.png','adopted')])
  d=t.store.read();d['sections'][0]['groups'][0]['shots'][0]['content']='不同的镜头内容';t.store.update(d,d['revision'])
  self.assertEqual(t.store.read()['_preview_rows'][0]['status'],'needs_review')
 def test_timed_and_music_triggers_pass_but_early_success_does_not(self):
  for kind,basis in [('timed','clock'),('music','beat'),('edit','edit')]:
   b=guard_tests.PromptGuardTests().bundle();b['positive_review']['events']=[{'kind':kind,'event':'图形出现','observable_trigger':'实际时基','before_trigger':'尚未出现','timing_basis':basis,'timing_evidence':'已采用节奏参考'}];self.assertTrue(guard.inspect(b)['ok'])
  b['positive_review']['events'][0]['kind']='completion';self.assertFalse(guard.inspect(b)['ok'])
 def test_strict_frame_does_not_require_opposing_disclaimer(self):
  b=guard_tests.PromptGuardTests().bundle();b['prompt']=b['prompt'].replace(guard.POLICY,'');b['semantic_review']['prompt_sha256']=hashlib.sha256(b['prompt'].encode()).hexdigest();b['reference_policy'][0].update(mode='strict_boundary',scope='首帧',evidence='真实首帧输入')
  self.assertTrue(guard.inspect(b)['ok'])

if __name__=='__main__':unittest.main()
