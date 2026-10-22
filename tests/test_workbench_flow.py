"""UI requests, assistant continuation and production consume the same saved decisions."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from test_store import Store, fixture
import production

class WorkbenchFlowTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.store=Store(self.tmp.name);self.doc=self.store.create('离线验收：纸鸟科普',fixture())
        self.sec=self.doc['sections'][0]['id'];self.shot=self.doc['sections'][0]['groups'][0]['shots'][0]['id']
    def act(self,area,command):
        return self.store.workspace_action({'area':area,'command':command},self.store.read()['revision'])
    def codes(self):return [a['code'] for a in self.store.current()['workflow']['next_actions']]
    def choose(self):
        self.act('references',{'action':'request','query':'纸鸟连贯展开','scope':{'section_id':self.sec}})
        self.act('references',{'action':'begin'})
        d=self.act('references',{'action':'add_candidate','candidate':{'title':'OFFLINE test lead','source_url':'https://eyecannndy.com/technique/pass-through','match_reason':'连续转场','difference':'主体不同','reuse_note':'采用连续展开的节奏','observation':'unverified'}})
        c=d['_references']['current']['candidates'][0]
        return self.act('references',{'action':'choose','candidate_id':c['id'],'adoption_note':'只取连续展开的节奏'})['_references']['current']
    def application(self,session):
        return {'id':'REF-APPLY','kind':'decision','title':'落实所选展开方式','body':'第一镜改为纸层连续展开，人物和故事保持当前稿。',
            'section_ids':[self.sec],'shot_ids':[self.shot],
            'data':{'decision_type':'creative_reference_application','reference_session_id':session['id'],'candidate_id':session['chosen_candidate_id'],
                    'adoption_note':session['adoption_note'],'application_evidence':'已更新第一镜camera字段并回读保存稿'}}
    def test_explicit_single_is_distinct_from_default(self):
        self.assertFalse(self.store.current()['workspace']['coordination']['mode_selected'])
        self.act('coordination',{'op':'set_mode','mode':'single','selection_evidence':'OFFLINE explicit user choice'})
        c=self.store.current()['workspace']['coordination']
        self.assertTrue(c['mode_selected']);self.assertIn('explicit',c['mode_selection']['evidence'])
    def test_request_is_in_the_same_action_list_shown_to_the_assistant(self):
        d=self.act('references',{'action':'request','query':'连续变形'})
        self.assertEqual(d['_workflow']['next_actions'],self.store.current()['workflow']['next_actions'])
        self.assertIn('reference_search',self.codes())
        self.act('references',{'action':'stop','reason':'OFFLINE no matching source'})
        self.assertNotIn('reference_search',self.codes())
    def test_chosen_reference_requires_real_scoped_application_and_flows_to_packages(self):
        session=self.choose();self.assertIn('reference_apply',self.codes())
        before=self.store.path.read_bytes();bad=self.application(session);bad['data']['candidate_id']='wrong'
        with self.assertRaisesRegex(ValueError,'参考落实'):self.store.record(bad,self.store.read()['revision'])
        self.assertEqual(self.store.path.read_bytes(),before)
        d=self.store.read();d['sections'][0]['groups'][0]['shots'][0]['camera']='随纸层连续展开，保持前进方向。'
        d=self.store.transact({'document':d,'records':[self.application(session)]},d['revision'])
        self.assertEqual(d['_references']['applications'][0]['status'],'applied')
        self.assertNotIn('reference_apply',self.codes())
        d=self.store.confirm(self.sec,d['revision'],'OFFLINE fixture content acceptance')
        package={'id':'INPUT','kind':'package','title':'OFFLINE package dependency test','section_ids':[self.sec],'shot_ids':[self.shot],'data':{}}
        d=self.store.record(package,d['revision']);pack=next(r for r in d['production']['records'] if r['id']=='INPUT')
        self.assertIn('REF-APPLY',pack['depends_on'])
        self.act('references',{'action':'choose','candidate_id':session['chosen_candidate_id'],'adoption_note':'改为只取停顿节奏'})
        d=self.store.read();self.assertTrue(d['_record_states']['REF-APPLY']['stale']);self.assertTrue(d['_record_states']['INPUT']['stale'])
        self.assertIn('reference_apply',self.codes())
        self.assertTrue(any('参考尚未落实' in issue for issue in production.package_issues(d,pack,Path(self.tmp.name))))
    def test_scoped_request_is_not_another_sections_next_step(self):
        doc=self.store.read();other=copy.deepcopy(doc['sections'][0]);other['id']='SECOND'
        for group in other['groups']:
            group['id']='OTHER-'+group['id']
            for shot in group['shots']:shot['id']='OTHER-'+shot['id']
        doc['sections'].append(other);self.store.update(doc,doc['revision']);second=other['id']
        self.act('references',{'action':'request','query':'只给第一段找例子','scope':{'section_ids':[self.sec]}})
        self.assertIn('reference_search',self.codes())
        self.assertNotIn('reference_search',[a['code'] for a in self.store.current(second)['workflow']['next_actions']])
    def test_single_session_shared_requirement_is_also_actionable(self):
        self.act('coordination',{'op':'set_mode','mode':'single'})
        self.act('coordination',{'op':'upsert_item','item':{'id':'LOCAL','title':'当前纸鸟','work_id':'local','summary':'本会话完整制作','directory':'offline/local'}})
        self.act('coordination',{'op':'upsert_directive','directive':{'id':'LOCAL-LOOK','text':'保留纸张折痕','item_ids':['LOCAL']}})
        pending=self.store.current()['workflow']['next_actions']
        self.assertTrue(any(a.get('directive_id')=='LOCAL-LOOK' and a['code']=='coordination_local_apply' for a in pending))

    def test_sent_coordination_remains_pending_until_actual_report(self):
        self.act('coordination',{'op':'set_mode','mode':'coordinated'})
        self.assertIn('coordination_controller',self.codes())
        self.act('coordination',{'op':'set_controller','controller':{'thread_id':'OFFLINE-controller'}})
        self.act('coordination',{'op':'upsert_item','item':{'id':'A','title':'纸鸟','work_id':'work-a','summary':'完整制作','directory':'offline/a','thread_id':'OFFLINE-A'}})
        self.act('coordination',{'op':'upsert_directive','directive':{'id':'LOOK','text':'沿用现行纸艺风格','item_ids':['A']}})
        self.assertIn('coordination_pending',self.codes())
        base={'op':'report','directive_id':'LOOK','item_id':'A','version':1,'thread_id':'OFFLINE-A','summary':'OFFLINE test receipt'}
        self.act('coordination',{**base,'status':'sent'})
        self.assertIn('coordination_sent',self.codes())
        self.act('coordination',{**base,'status':'applied','evidence':'OFFLINE fixture saved and read back'})
        self.assertFalse(any(c.startswith('coordination_') for c in self.codes()))

if __name__=='__main__':unittest.main()
