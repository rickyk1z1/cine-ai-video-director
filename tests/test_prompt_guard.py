import copy
import hashlib
import importlib.util
from pathlib import Path
import unittest
spec=importlib.util.spec_from_file_location('prompt_guard',Path(__file__).resolve().parents[1]/'scripts/prompt_guard.py')
guard=importlib.util.module_from_spec(spec);spec.loader.exec_module(guard)
class PromptGuardTests(unittest.TestCase):
 def bundle(self):
  prompt=guard.POLICY+'\n<node-asset>ref1</node-asset>只提供人物身份。接稳杯碟后切到同一人品茶。'
  b={'prompt':prompt,'reference_policy':[{'id':'ref1','type':'image','use':'人物身份','not_required':'精确姿势','mode':'reference'}], 'semantic_review':{'prompt_sha256':hashlib.sha256(prompt.encode()).hexdigest(),'event_vs_frame':'接杯后品茶是事件，姿势非逐帧锁定','reference_scope_consistency':'身份图不控制背景','motion_conflicts':'可省略抬杯，不要求瞬移'},'continuity_review':{'units':['receive','sip'],'joins':[{'from':'receive','to':'sip','type':'action_ellipsis','audience_bridge':'同人同杯，接稳后饮茶','evidence':'已声明同杯碟与衣袖','budget_check':'仅轻饮，不重复抬杯','status':'resolved'}]}}
  b['positive_review']={'counterfactual':{'status':'clear','evidence':'正文只用人物身份，接杯品茶是事件，不指向图片构图'},'references':[{'id':'ref1','necessity':'保持身份','positive_role':'人物身份','implied_endpoint':False,'exception_evidence':''}],'events':[],'control_budget':'只保留接杯品茶与身份；无图间演变要求'}
  b['model_scope_review']={'status':'clear','evidence':'正文仅含接杯品茶画面','generation_scope':'接杯与品茶两个镜头组成的一次生成','instruction_relevance':'每句控制本次可见动作或人物身份','context_completeness':'同人同杯及动作关系均在正文与参考中给出'}
  return b
 def test_valid_ellipsis_does_not_require_extra_shot(self):self.assertTrue(guard.inspect(self.bundle())['ok'])
 def test_edited_prompt_requires_new_review(self):
  b=self.bundle();b['prompt']+='再改正文';self.assertFalse(guard.inspect(b)['ok'])
 def test_missing_join_fails(self):
  b=self.bundle();b['continuity_review']['joins']=[];self.assertFalse(guard.inspect(b)['ok'])
 def test_missing_causal_basis_fails(self):
  b=self.bundle();b['continuity_review']['joins'][0]['audience_bridge']='';self.assertFalse(guard.inspect(b)['ok'])
 def test_unresolved_design_gap_fails(self):
  b=self.bundle();b['continuity_review']['joins'][0]['status']='design_gap';self.assertFalse(guard.inspect(b)['ok'])
 def test_unknown_dynamic_is_not_silently_passed(self):
  b=self.bundle();b['continuity_review']['joins'][0]['status']='unverified';r=guard.inspect(b);self.assertTrue(r['ok']);self.assertEqual(len(r['unverified_joins']),1)
 def test_strict_exception_needs_evidence(self):
  b=self.bundle();b['reference_policy'][0]['mode']='strict_boundary';self.assertFalse(guard.inspect(b)['ok']);b['reference_policy'][0].update(scope='首帧构图',evidence='测试：用户指定且真实首帧入口绑定');self.assertTrue(guard.inspect(b)['ok'])
 def test_missing_positive_review_fails(self):
  b=self.bundle();del b['positive_review'];self.assertFalse(guard.inspect(b)['ok'])
 def test_disclaimer_cannot_override_acknowledged_conflict(self):
  b=self.bundle();b['positive_review']['counterfactual']['status']='conflict';self.assertFalse(guard.inspect(b)['ok'])
 def test_ordinary_reference_cannot_be_implied_endpoint(self):
  b=self.bundle();b['positive_review']['references'][0]['implied_endpoint']=True;self.assertFalse(guard.inspect(b)['ok'])
 def test_clock_only_event_fails(self):
  b=self.bundle();b['positive_review']['events']=[{'event':'反馈','observable_trigger':'时间到','before_trigger':'无反馈','timing_basis':'clock'}];self.assertFalse(guard.inspect(b)['ok'])
 def test_event_based_feedback_passes(self):
  b=self.bundle();b['positive_review']['events']=[{'event':'接收成功','observable_trigger':'接收方已承重且交出方松手','before_trigger':'不显示成功','timing_basis':'event_with_budget'}];self.assertTrue(guard.inspect(b)['ok'])
 def test_authorized_endpoint_passes(self):
  b=self.bundle();b['reference_policy'][0].update(mode='strict_boundary',scope='首帧',evidence='用户指定及真实首帧接口');b['positive_review']['references'][0].update(implied_endpoint=True,exception_evidence='用户指定首帧');self.assertTrue(guard.inspect(b)['ok'])
 def test_task_specific_short_boundary_passes(self):
  b=self.bundle();short='图仅供外观参考，不锁整图。';b['prompt']=b['prompt'].replace(guard.POLICY,short);b['delivery_contract']={'reference_boundary':short};b['semantic_review']['prompt_sha256']=hashlib.sha256(b['prompt'].encode()).hexdigest();self.assertTrue(guard.inspect(b)['ok'])
 def test_declared_boundary_must_be_in_actual_prompt(self):
  b=self.bundle();b['delivery_contract']={'reference_boundary':'未写入正文的边界'};self.assertFalse(guard.inspect(b)['ok'])
 def test_scope_requires_relevance_and_self_contained_context(self):
  b=self.bundle();del b['model_scope_review']['context_completeness'];self.assertFalse(guard.inspect(b)['ok'])
  b=self.bundle();b['model_scope_review']['status']='conflict';self.assertFalse(guard.inspect(b)['ok'])
 def test_words_do_not_decide_generation_relevance(self):
  b=self.bundle();b['prompt']+='角色在教室展示PPT，镜头切近屏幕。';b['semantic_review']['prompt_sha256']=hashlib.sha256(b['prompt'].encode()).hexdigest();b['model_scope_review'].update(generation_scope='本次包含角色展示课件及屏幕近景',instruction_relevance='PPT是本次可见道具，切近是本次镜头',context_completeness='屏幕近景在本次生成范围内，有明确对象');self.assertTrue(guard.inspect(b)['ok'])
 def test_audio_minimum_uses_real_file(self):
  import tempfile,wave
  with tempfile.TemporaryDirectory() as tmp:
   path=Path(tmp)/'a.wav'
   with wave.open(str(path),'wb') as f:f.setnchannels(1);f.setsampwidth(2);f.setframerate(8000);f.writeframes(bytes(16000))
   b=self.bundle();ref=b['reference_policy'][0];ref['type']='audio';ref['audio_contract']={'platform':'test','model':'test','mode':'reference','evidence':'测试入口规范','checked_at':'2026-09-21','file':str(path),'usage':'原声','duration_limits':{'min_seconds':5}}
   self.assertFalse(guard.inspect(b)['ok']);ref['audio_contract']['duration_limits']['min_seconds']=0.5;self.assertTrue(guard.inspect(b)['ok'])
   ref['audio_contract']['duration_limits']['max_seconds']=0.8;self.assertFalse(guard.inspect(b)['ok'])
if __name__=='__main__':unittest.main()
