"""Project journeys, scoped shared changes and truthful session reports."""
import copy
import unittest
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))

import coordination


class CoordinationTests(unittest.TestCase):
    def setUp(self):self.state=coordination.initial()

    def apply(self,op,**fields):
        self.state=coordination.apply(self.state,{'op':op,**fields},now='2026-09-24T12:00:00+00:00')
        return self.state

    def item(self,identifier,group=None,thread=None):
        value={'id':identifier,'title':'作品 '+identifier,'work_id':'work-'+identifier,
               'group_id':group,'summary':'承担本条的完整视频制作','directory':'works/'+identifier}
        if thread:value['thread_id']=thread
        return self.apply('upsert_item',item=value)

    def directive(self,identifier,text,item_ids):
        return self.apply('upsert_directive',directive={'id':identifier,'text':text,'item_ids':item_ids})

    def report(self,identifier,item,version=1,status='applied',**extra):
        return self.apply('report',directive_id=identifier,item_id=item,version=version,status=status,
                          thread_id='thread-'+item,summary='已同步本次共用要求并回读目标节点',
                          **({'evidence':'works/'+item+'/分镜阅览.md；节点回读已核对'} if status=='applied' else {}),**extra)

    def test_default_single_can_work_section_by_section_without_sessions(self):
        self.item('A');self.item('B')
        display=coordination.view(self.state,'示例项目')
        self.assertEqual(display['mode'],'single');self.assertIsNone(display['controller'])
        self.assertEqual([i['assignment_status'] for i in display['items']],['unassigned','unassigned'])
        self.assertEqual(display['controller_title'],'总控｜示例项目')
        self.assertEqual(display['pending_count'],0)
        self.assertTrue(all(i['group_id'] is None for i in display['items']))

    def test_project_controller_preserves_related_and_independent_works(self):
        self.item('A','arrival','thread-A');self.item('B','arrival','thread-B');self.item('C',thread='thread-C')
        self.apply('set_mode',mode='coordinated')
        self.apply('set_controller',controller={'thread_id':'controller-actual','host_id':'local'})
        self.directive('COMMON','人物和迎宾动作沿用共用角色资产。',['A','B'])
        self.directive('C-ONLY','独立短片保持自己的内容与声音方案。',['C'])
        display=coordination.view(self.state,'项目')
        self.assertEqual(display['controller']['thread_id'],'controller-actual')
        self.assertEqual([i['work_id'] for i in display['items']],['work-A','work-B','work-C'])
        self.assertEqual([i['group_id'] for i in display['items']],['arrival','arrival',None])
        self.assertEqual(display['pending_count'],3)
        self.assertEqual(display['items'][2]['pending_directive_ids'],['C-ONLY'])
        self.assertNotIn('sound_policy',display)

    def test_sent_is_not_applied_and_unassigned_is_not_a_created_session(self):
        self.item('A');self.directive('LOOK','保持采用的暖色布景。',['A'])
        display=coordination.view(self.state)
        self.assertEqual(display['directives'][0]['targets'][0]['status'],'unassigned')
        with self.assertRaisesRegex(ValueError,'已登记'):self.report('LOOK','A')
        self.apply('upsert_item',item={'id':'A','thread_id':'thread-A'})
        self.report('LOOK','A',status='sent')
        self.assertEqual(coordination.view(self.state)['pending_count'],1)
        self.assertEqual(coordination.view(self.state)['directives'][0]['targets'][0]['status'],'sent')
        self.report('LOOK','A')
        self.assertEqual(coordination.view(self.state)['pending_count'],0)
        with self.assertRaisesRegex(ValueError,'发送回执'):self.report('LOOK','A',status='sent')

    def test_shared_revision_invalidates_only_its_recipients_and_rejects_old_report(self):
        for name in ('A','B','C'):self.item(name,thread='thread-'+name)
        self.directive('LOOK','布景采用暖色。',['A','B']);self.directive('OTHER','独立条目保持原方案。',['C'])
        self.report('LOOK','A');self.report('LOOK','B');self.report('OTHER','C')
        self.apply('upsert_item',item={'id':'A','status':'working'})
        independent=copy.deepcopy(self.state['directives'][1])
        self.directive('LOOK','布景改为已确认的冷色，保留其他动作和当前阶段。',['A','B'])
        display=coordination.view(self.state)
        self.assertEqual(display['pending_count'],2)
        self.assertEqual(display['items'][0]['status'],'working')
        self.assertEqual(self.state['directives'][1],independent)
        self.assertEqual(self.state['directives'][0]['receipts']['A']['version'],1)
        before=copy.deepcopy(self.state)
        with self.assertRaisesRegex(ValueError,'旧回报'):self.report('LOOK','A',version=1)
        self.assertEqual(self.state,before)
        self.report('LOOK','A',version=2)
        self.assertEqual(coordination.view(self.state)['pending_count'],1)

    def test_scope_only_extension_does_not_reask_unchanged_recipient(self):
        self.item('A',thread='thread-A');self.item('B',thread='thread-B')
        self.directive('LOOK','沿用同一角色资产。',['A']);self.report('LOOK','A')
        receipt=copy.deepcopy(self.state['directives'][0]['receipts']['A'])
        self.directive('LOOK','沿用同一角色资产。',['A','B'])
        self.assertEqual(self.state['directives'][0]['version'],1)
        self.assertEqual(self.state['directives'][0]['receipts']['A'],receipt)
        self.assertEqual([t['status'] for t in coordination.view(self.state)['directives'][0]['targets']],['applied','pending'])
        self.directive('LOOK','沿用同一角色资产。',['B'])
        self.assertIn('A',self.state['directives'][0]['receipts'])
        with self.assertRaisesRegex(ValueError,'范围'):self.report('LOOK','A')

    def test_reassigned_thread_requires_a_new_real_report(self):
        self.item('A',thread='thread-A');self.directive('LOOK','沿用角色。',['A']);self.report('LOOK','A')
        self.apply('upsert_item',item={'id':'A','thread_id':'replacement'})
        self.assertEqual(coordination.view(self.state)['pending_count'],1)
        with self.assertRaisesRegex(ValueError,'执行会话'):self.report('LOOK','A')
        self.apply('report',directive_id='LOOK',item_id='A',version=1,status='blocked',
                   thread_id='replacement',summary='缺少目标平台节点地址。')
        self.assertEqual(coordination.view(self.state)['items'][0]['directive_status']['LOOK'],'blocked')

    def test_report_requires_real_evidence_and_exact_version(self):
        self.item('A',thread='thread-A');self.directive('LOOK','沿用角色。',['A'])
        base={'op':'report','directive_id':'LOOK','item_id':'A','version':1,'status':'applied',
              'thread_id':'thread-A','summary':'已完成'}
        for patch in ({},{'evidence':' '},{'evidence':'file','version':True},{'evidence':'file','version':2},{'evidence':'file','status':[]}):
            with self.subTest(patch=patch),self.assertRaises(ValueError):coordination.apply(self.state,{**base,**patch})

    def test_identity_and_instruction_conflicts_leave_input_untouched(self):
        self.item('A');self.directive('LOOK','沿用角色。',['A'])
        before=copy.deepcopy(self.state)
        commands=[{'op':'upsert_item','item':{'id':'A','work_id':'other-work'}},
                  {'op':'upsert_directive','directive':{'id':'LOOK','text':'改版'},'expected_version':0},
                  {'op':'upsert_directive','directive':{'id':'LOOK','version':99}},
                  {'op':'upsert_directive','directive':{'id':'LOOK','item_ids':['missing']}},
                  {'op':'upsert_directive','directive':{'id':'LOOK','item_ids':['A','A']}},
                  {'op':'set_controller'}, {'op':'create_thread'}, {'op':'set_mode','mode':'parallel'}]
        for command in commands:
            with self.subTest(command=command),self.assertRaises(ValueError):coordination.apply(self.state,command)
            self.assertEqual(self.state,before)

    def test_malformed_state_is_rejected(self):
        self.item('A');self.directive('LOOK','沿用角色。',['A'])
        cases=[]
        duplicate=copy.deepcopy(self.state);duplicate['work_items'].append(copy.deepcopy(duplicate['work_items'][0]));cases.append(duplicate)
        duplicate=copy.deepcopy(self.state);duplicate['directives'].append(copy.deepcopy(duplicate['directives'][0]));cases.append(duplicate)
        dirty=copy.deepcopy(self.state);dirty['work_items'][0]['status']=[];cases.append(dirty)
        dirty=copy.deepcopy(self.state);dirty['directives'][0]['receipts']={'ghost':{}};cases.append(dirty)
        dirty=copy.deepcopy(self.state);dirty['extra']=float('nan');cases.append(dirty)
        dirty=copy.deepcopy(self.state);dirty['schema_version']=True;cases.append(dirty)
        for state in cases:
            with self.subTest(state=state),self.assertRaises(ValueError):coordination.validate(state)

    def test_unrelated_extension_data_and_prior_progress_are_preserved(self):
        self.item('A',thread='thread-A');self.directive('LOOK','沿用角色。',['A']);self.report('LOOK','A')
        self.state['future_metadata']={'keep':True};self.state['work_items'][0]['creative_phase']='video'
        original=copy.deepcopy(self.state)
        new=coordination.apply(self.state,{'op':'set_mode','mode':'coordinated'})
        self.assertEqual(self.state,original);self.assertEqual(new['future_metadata'],{'keep':True})
        self.assertEqual(new['work_items'][0]['creative_phase'],'video')
        new['future_metadata']['keep']=False
        self.assertTrue(self.state['future_metadata']['keep'])
        display=coordination.view(self.state);display['items'][0]['summary']='UI copy'
        self.assertNotEqual(self.state['work_items'][0]['summary'],'UI copy')
        self.apply('set_mode',mode='single')
        self.assertEqual(coordination.view(self.state)['pending_count'],0)


if __name__=='__main__':unittest.main()
