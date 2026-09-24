"""Unified workbench actions preserve drafts, scope and actual content timing."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import storyboard
import production
import test_store as fixtures

class WorkspaceIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.store=storyboard.Store(self.tmp.name);self.doc=self.store.create('test',fixtures.fixture())
        self.shots=self.doc['sections'][0]['groups'][0]['shots'];self.ids=[s['id'] for s in self.shots]
    def command(self,area,command):
        return self.store.workspace_action({'area':area,'command':command},self.store.read()['revision'])
    def test_reference_request_and_user_choice_do_not_start_a_new_production_stage(self):
        doc=self.command('references',{'action':'request','query':'连续穿过物体进入新空间'})
        self.assertEqual(doc['_references']['current']['status'],'request')
        self.assertIsNone(doc['_references']['current']['started_at'])
        self.assertEqual(doc['_workflow']['phase'],0)
        self.command('references',{'action':'begin'})
        doc=self.command('references',{'action':'add_candidate','candidate':{'title':'参考线索','source_url':'https://eyecannndy.com/technique/pass-through','match_reason':'同一连续前进','difference':'主体不同','reuse_note':'只取穿越空间的方式','observation':'unverified'}})
        candidate=doc['_references']['current']['candidates'][0]
        doc=self.command('references',{'action':'choose','candidate_id':candidate['id'],'adoption_note':'用户在原站观看后只取空间穿越'})
        self.assertEqual(doc['_references']['current']['status'],'ready')
        self.assertEqual(doc['_references']['current']['candidates'][0]['observation'],'unverified')
        self.assertEqual(doc['_references']['valid_count'],0)
        self.assertEqual(doc['_workflow']['phase'],0)
    def test_plain_autosave_preserves_pending_coordination_and_reference_requests(self):
        base=self.store.read();local=copy.deepcopy(base);local['sections'][0]['groups'][0]['shots'][0]['content']='保留正在输入的改稿'
        remote=self.command('coordination',{'op':'set_mode','mode':'coordinated'})
        merged=self.store.update(local,base['revision'],base)
        self.assertEqual(merged['workspace']['coordination']['mode'],'coordinated')
        self.assertEqual(merged['sections'][0]['groups'][0]['shots'][0]['content'],'保留正在输入的改稿')
        changed=copy.deepcopy(merged);changed['workspace']={'coordination':{'mode':'single'}}
        out=self.store.update(changed,merged['revision'])
        self.assertEqual(out['workspace'],merged['workspace'])
    def test_transaction_cannot_clear_coordination_state(self):
        doc=self.command('coordination',{'op':'set_mode','mode':'coordinated'})
        incoming=copy.deepcopy(doc);incoming.pop('workspace')
        out=self.store.transact({'document':incoming},doc['revision'])
        self.assertEqual(out['workspace']['coordination']['mode'],'coordinated')
    def test_invalid_workspace_command_keeps_entire_saved_document(self):
        before=self.store.path.read_bytes()
        with self.assertRaises(ValueError):self.command('coordination',{'op':'upsert_item','item':{'id':'invalid'}})
        self.assertEqual(self.store.path.read_bytes(),before)
    def test_style_choice_is_saved_without_fake_asset_adoption(self):
        choice={'base_id':'clay','world_id':None,'tones':['温暖治愈'],'brief':'黏土质感；人物保持正常比例','project_notes':'品牌色保持蓝绿色'}
        doc=self.store.workspace_action({'area':'style','choice':choice},self.store.read()['revision'])
        self.assertEqual(doc['workspace']['style_choice']['project_notes'],choice['project_notes'])
        self.assertEqual(doc.get('production',{}).get('confirmations',{}),{})
        self.assertEqual(doc['_workflow']['phase'],0)
    def test_pacing_updates_current_timing_and_marks_old_derived_text_stale(self):
        helper=fixtures.StoreTests();helper.setUp();self.addCleanup(helper.doCleanups)
        derived=helper.add_derived();shots=derived['sections'][0]['groups'][0]['shots'];before=copy.deepcopy(derived['production']) if 'production' in derived else None
        result=helper.store.workspace_action({'area':'pacing','plan':{'evidence':'正常动作和相机移动同时发生','shots':[{'shot_id':shots[0]['id'],'duration':2,'basis':'同一抬头过程不重复计时','changes':{'content':'停笔时抬眼看向灯光。'}}]}},derived['revision'])
        self.assertTrue(result['prompts'][0]['stale']);self.assertTrue(result['suggestions'][0]['stale'])
        self.assertFalse(result['prompts'][1]['stale'])
        self.assertEqual(result['prompts'][0]['text'],derived['prompts'][0]['text'])
        self.assertEqual(result['_pacing']['known_duration_seconds'],2)
        self.assertIsNone(result['_pacing']['content_duration_seconds'])
        self.assertTrue(any(r['data'].get('decision_type')=='pacing_calibration' for r in result['production']['records']))
    def timed_record(self):
        doc=copy.deepcopy(self.doc);doc['sections'][0]['groups'][0]['shots'][0]['duration']=6;doc['sections'][0]['groups'][0]['shots'][1]['duration']=7.5
        record={'shot_ids':self.ids,'data':{'timeline':[{'shot_id':self.ids[0],'start':0,'end':6},{'shot_id':self.ids[1],'start':6,'end':13.5}]}}
        return doc,record
    def test_20_second_generation_cannot_silently_replace_13_5_second_content(self):
        doc,record=self.timed_record();record['data']['timeline'][0]['end']=10;record['data']['timeline'][1].update(start=10,end=20)
        self.assertTrue(production.timing_issues(doc,record))
    def test_fixed_platform_slot_uses_explicit_handle_without_stretching_shots(self):
        doc,record=self.timed_record();record['data']['timeline'][1]['end']=15
        self.assertTrue(production.timing_issues(doc,record))
        record['data']['generation_handles']={'tail_seconds':1.5,'evidence':'测试入口只能选15秒，末尾余量用于裁切'}
        self.assertEqual(production.timing_issues(doc,record),[])
        record['data']['content_timeline']=[{'shot_id':self.ids[0],'start':0,'end':6},{'shot_id':self.ids[1],'start':6,'end':13.5}]
        self.assertEqual(production.timing_issues(doc,record),[])
        record['data']['content_timeline'][1]['end']=20
        self.assertTrue(production.timing_issues(doc,record))
    def test_handoff_hash_binds_extra_timing_fields(self):
        doc,record=self.timed_record();record.update(depends_on=[]);record['data'].update(references=[],parameters={'duration':15},generation_handles={'tail_seconds':1.5,'evidence':'平台档位'})
        first=production.digest(production.delivery_input(doc,record,Path(self.tmp.name)))
        record['data']['generation_handles']['tail_seconds']=2
        self.assertNotEqual(first,production.digest(production.delivery_input(doc,record,Path(self.tmp.name))))

if __name__=='__main__':unittest.main()
