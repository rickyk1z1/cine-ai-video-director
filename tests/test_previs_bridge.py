import copy
import json
from pathlib import Path
import tempfile
import unittest
from test_store import Store,fixture,new_shot
from previs_bridge import prepare,check
import production

class BridgeTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.store=Store(self.tmp.name);d=fixture();d['sections'][0]['groups'][0]['shots'][1]['duration']=0.15
        d['sections'][0]['groups'][0]['shots'][0]['duration']=0.15
        self.d=self.store.create('',d);self.sid=d['sections'][0]['id']
        self.sample=json.loads((Path(__file__).resolve().parents[1]/'references/production-detail/minimal-scene-spec.json').read_text())
        self.e={'scene_id':'ROOM','fps':24,'assets':[{'id':'CHR_X','role':'subject'}],
            'cameras':{sh['id']:{'id':'CAM_'+str(i),'lens_mm':35+i*15,'focus_target':'CHR_X'} for i,sh in enumerate(d['sections'][0]['groups'][0]['shots'])},
            'budgets':self.sample['budgets'],'performance':self.sample['performance']}
    def adopt(self):self.d=self.store.confirm(self.sid,self.store.read()['revision'],'OFFLINE FIXTURE confirmed')
    def test_requires_confirmed_shots(self):
        with self.assertRaises(ValueError):prepare(self.d,self.sid,self.e)
    def test_cumulative_frames_and_identity(self):
        self.adopt();s=prepare(self.d,self.sid,self.e)
        self.assertEqual([x['frame_range'] for x in s['shots']],[[1,4],[5,7]])
        self.assertEqual([x['id'] for x in s['shots']],production.shot_ids(self.d['sections'][0]))
        self.assertEqual(check(self.d,s,self.tmp.name)['errors'],[])
        self.assertIsNone(s['performance']['viewport_fps'])
    def test_missing_engineering_not_fabricated(self):
        self.adopt();self.e['cameras']={}
        with self.assertRaises(ValueError):prepare(self.d,self.sid,self.e)
    def test_changed_draft_and_reconfirmed_shots_reject_old_spec(self):
        self.adopt();s=prepare(self.d,self.sid,self.e)
        d=self.store.read();d['sections'][0]['groups'][0]['shots'][0]['content']='changed'
        self.store.update(d,d['revision']);self.assertTrue(check(self.store.read(),s,self.tmp.name)['errors'])
        self.adopt();self.assertTrue(check(self.d,s,self.tmp.name)['errors'])
    def test_engineering_cannot_silently_retime_or_rewrite(self):
        self.adopt();s=prepare(self.d,self.sid,self.e)
        s['shots'][0]['storyboard']['sound']='new line'
        self.assertIn('STORYBOARD_CONTENT_DRIFT',{x['code'] for x in check(self.d,s,self.tmp.name)['errors']})
        s=prepare(self.d,self.sid,self.e);s['shots'][0]['frame_range'][1]+=1
        self.assertIn('STORYBOARD_TIMING_DRIFT',{x['code'] for x in check(self.d,s,self.tmp.name)['errors']})
    def test_consumer_fields_cannot_diverge(self):
        self.adopt()
        for field in ('number','shot_size','dramatic_intent'):
            spec=prepare(self.d,self.sid,self.e);spec['shots'][0][field]='opposite'
            self.assertIn('STORYBOARD_CONSUMER_FIELD_DRIFT',{x['code'] for x in check(self.d,spec,self.tmp.name)['errors']})
    def test_engineering_extensions_retained(self):
        self.adopt();self.e.update(directing={'beats':[{'id':'B','trigger':'声音'}]},assumptions=['尺寸估计'],source_refs=['原文'],sequence={'pacing_profile':{'mode':'slow'}},future_field={'keep':'yes'})
        spec=prepare(self.d,self.sid,self.e)
        self.assertEqual(spec['directing'],self.e['directing']);self.assertEqual(spec['assumptions'],self.e['assumptions'])
        self.assertEqual(spec['sequence']['pacing_profile'],self.e['sequence']['pacing_profile'])
        self.assertEqual(spec['unmapped_engineering']['future_field'],{'keep':'yes'})
        self.e['sequence']['camera_cuts']=[]
        with self.assertRaises(ValueError):prepare(self.d,self.sid,self.e)
    def test_single_shot_scope_preserves_source_timing(self):
        self.adopt();ids=production.shot_ids(self.d['sections'][0]);self.e['shot_ids']=[ids[1]]
        self.e['cameras'].pop(ids[0]);spec=prepare(self.d,self.sid,self.e)
        self.assertEqual([s['id'] for s in spec['shots']],[ids[1]])
        self.assertEqual(spec['shots'][0]['source_frame_range'],[5,7])
        self.assertEqual(spec['shots'][0]['frame_range'],[1,3])
        self.assertEqual(check(self.d,spec,self.tmp.name)['errors'],[])
        spec['shots'][0]['source_frame_range']=[1,3]
        self.assertIn('STORYBOARD_SOURCE_TIMING_DRIFT',{e['code'] for e in check(self.d,spec,self.tmp.name)['errors']})
    def test_single_first_shot_does_not_require_later_unknown_duration(self):
        doc=self.store.read();doc['sections'][0]['groups'][0]['shots'][1]['duration']=None
        self.store.update(doc,doc['revision']);self.adopt()
        ids=production.shot_ids(self.d['sections'][0]);self.e['shot_ids']=[ids[0]]
        self.e['cameras'].pop(ids[1]);spec=prepare(self.d,self.sid,self.e)
        self.assertEqual(check(self.d,spec,self.tmp.name)['errors'],[])
    def test_scope_rejects_invalid_selection(self):
        self.adopt();ids=production.shot_ids(self.d['sections'][0])
        for selection in ([],[ids[0],ids[0]],['unknown'],ids[::-1],'all'):
            with self.subTest(selection=selection):
                self.e['shot_ids']=selection
                with self.assertRaises(ValueError):prepare(self.d,self.sid,self.e)
    def test_record_updates_do_not_invalidate_confirmed_source(self):
        self.adopt();s=prepare(self.d,self.sid,self.e)
        d=self.store.record({'id':'D','kind':'decision','title':'Note','section_ids':[self.sid],'body':'technical note'},self.d['revision'])
        self.assertEqual(check(d,s,self.tmp.name)['errors'],[])

    def authorize(self,ids=None):
        self.d=self.store.record({'id':'IMAGE','kind':'decision','title':'继续制作',
            'section_ids':[self.sid],'shot_ids':ids or production.shot_ids(self.store.read()['sections'][0]),
            'data':{'decision_type':'image_stage_entry','batch_id':'offline',
                    'selection_evidence':'用户要求本范围继续图稿协同修改'}},self.store.read()['revision'])

    def test_authorized_revision_uses_current_text_without_fabricating_confirmation(self):
        self.adopt();self.authorize();old=prepare(self.d,self.sid,self.e)
        doc=self.store.read();doc['sections'][0]['groups'][0]['shots'][0]['content']='按反馈修订动作'
        self.d=self.store.transact({'document':doc,'evidence':'用户要求同步修改动作'},doc['revision'],revise=True)
        self.assertEqual(production.confirmation_status(self.d,self.sid),'changed')
        spec=prepare(self.d,self.sid,self.e)
        self.assertEqual(spec['shots'][0]['storyboard']['content'],'按反馈修订动作')
        self.assertEqual(check(self.d,spec,self.tmp.name)['errors'],[])
        self.assertIn('STORYBOARD_BINDING_STALE',{e['code'] for e in check(self.d,old,self.tmp.name)['errors']})

    def test_authorized_added_shot_continues_and_unauthorized_addition_does_not(self):
        self.adopt();self.authorize()
        doc=self.store.read();added=new_shot();added.update(number='SH03',content='补充反应',duration=0.2)
        doc['sections'][0]['groups'][0]['shots'].append(added)
        self.e['cameras'][added['id']]={'id':'CAM_NEW','lens_mm':50,'focus_target':'CHR_X'}
        self.d=self.store.update(doc,doc['revision'])
        with self.assertRaises(ValueError):prepare(self.d,self.sid,self.e)
        self.d=self.store.transact({'section_ids':[self.sid],'evidence':'用户明确补镜并继续本段制作'},self.d['revision'],revise=True)
        spec=prepare(self.d,self.sid,self.e)
        self.assertEqual(spec['shots'][-1]['id'],added['id'])
        self.assertFalse(production.shot_confirmed(self.d,added['id']))
        self.assertEqual(check(self.d,spec,self.tmp.name)['errors'],[])

    def test_unrelated_changed_shot_does_not_block_scoped_preparation_or_check(self):
        self.adopt();ids=production.shot_ids(self.d['sections'][0]);self.e['shot_ids']=[ids[1]]
        spec=prepare(self.d,self.sid,self.e)
        doc=self.store.read();doc['sections'][0]['groups'][0]['shots'][0]['content']='前镜仅改文字'
        self.d=self.store.update(doc,doc['revision'])
        self.assertEqual(check(self.d,spec,self.tmp.name)['errors'],[])
        self.assertEqual(check(self.d,prepare(self.d,self.sid,self.e),self.tmp.name)['errors'],[])
        self.e['shot_ids']=[ids[0]]
        with self.assertRaises(ValueError):prepare(self.d,self.sid,self.e)

    def test_local_timebase_needs_no_preceding_duration_and_claims_no_source_frames(self):
        self.adopt();ids=production.shot_ids(self.d['sections'][0]);self.e['shot_ids']=[ids[1]]
        doc=self.store.read();doc['sections'][0]['groups'][0]['shots'][0]['duration']=None
        self.d=self.store.update(doc,doc['revision'])
        with self.assertRaises(ValueError):prepare(self.d,self.sid,self.e)
        self.e['source_timebase']='local';spec=prepare(self.d,self.sid,self.e)
        self.assertEqual(spec['shots'][0]['frame_range'],[1,4])
        self.assertNotIn('source_frame_range',spec['shots'][0])
        self.assertEqual(check(self.d,spec,self.tmp.name)['errors'],[])
        spec['shots'][0]['source_frame_range']=[1,4]
        self.assertIn('STORYBOARD_SOURCE_TIMING_DRIFT',{e['code'] for e in check(self.d,spec,self.tmp.name)['errors']})

    def test_section_timing_drift_is_relevant_but_local_reference_is_independent(self):
        self.adopt();self.e['shot_ids']=[production.shot_ids(self.d['sections'][0])[1]]
        section_spec=prepare(self.d,self.sid,self.e)
        self.e['source_timebase']='local';local_spec=prepare(self.d,self.sid,self.e)
        doc=self.store.read();doc['sections'][0]['groups'][0]['shots'][0]['duration']=0.3
        self.d=self.store.update(doc,doc['revision'])
        self.assertIn('STORYBOARD_SOURCE_TIMING_DRIFT',{e['code'] for e in check(self.d,section_spec,self.tmp.name)['errors']})
        self.assertEqual(check(self.d,local_spec,self.tmp.name)['errors'],[])

    def test_legacy_binding_still_reads_and_limits_staleness_to_scope(self):
        self.adopt();self.e['shot_ids']=[production.shot_ids(self.d['sections'][0])[1]]
        spec=prepare(self.d,self.sid,self.e);c=production.state(self.d)['confirmations'][self.sid]
        spec['source_binding']={'document_id':self.d['id'],'section_id':self.sid,
            'fingerprint':c['fingerprint'],'source_revision':c['source_revision'],'shot_ids':self.e['shot_ids']}
        self.assertEqual(check(self.d,spec,self.tmp.name)['errors'],[])
        doc=self.store.read();doc['sections'][0]['groups'][0]['shots'][0]['content']='无关文字改动'
        self.d=self.store.update(doc,doc['revision'])
        self.assertEqual(check(self.d,spec,self.tmp.name)['errors'],[])
        self.authorize();doc=self.store.read();doc['sections'][0]['groups'][0]['shots'][1]['content']='相关改动'
        self.d=self.store.update(doc,doc['revision'])
        self.assertIn('STORYBOARD_BINDING_STALE',{e['code'] for e in check(self.d,spec,self.tmp.name)['errors']})

    def test_legacy_whole_section_binding_reads_without_rewriting(self):
        self.adopt();spec=prepare(self.d,self.sid,self.e);c=production.state(self.d)['confirmations'][self.sid]
        spec['source_binding']={'document_id':self.d['id'],'section_id':self.sid,
            'fingerprint':c['fingerprint'],'source_revision':c['source_revision']}
        original=copy.deepcopy(spec)
        self.assertEqual(check(self.d,spec,self.tmp.name)['errors'],[])
        self.assertEqual(spec,original)

    def test_relevant_direction_notes_invalidate_current_source(self):
        self.adopt();self.authorize();spec=prepare(self.d,self.sid,self.e)
        doc=self.store.read();doc['sections'][0]['groups'][0]['notes']='改为急促节奏'
        self.d=self.store.update(doc,doc['revision'])
        self.assertIn('STORYBOARD_BINDING_STALE',{e['code'] for e in check(self.d,spec,self.tmp.name)['errors']})
        self.assertEqual(check(self.d,prepare(self.d,self.sid,self.e),self.tmp.name)['errors'],[])

    def test_permission_cannot_be_inferred_from_draft_or_revoked_record(self):
        self.authorize([production.shot_ids(self.d['sections'][0])[0]])
        with self.assertRaises(ValueError):prepare(self.d,self.sid,self.e)
        self.e['shot_ids']=[production.shot_ids(self.d['sections'][0])[0]]
        spec=prepare(self.d,self.sid,self.e)
        self.assertEqual(check(self.d,spec,self.tmp.name)['errors'],[])
        record=next(r for r in self.d['production']['records'] if r['id']=='IMAGE')
        record['data']['status']='revoked';self.d=self.store.record(record,self.d['revision'])
        with self.assertRaises(ValueError):prepare(self.d,self.sid,self.e)

    def test_unknown_binding_version_and_changed_source_are_not_accepted(self):
        self.adopt();self.authorize();spec=prepare(self.d,self.sid,self.e)
        damaged=copy.deepcopy(spec);damaged['source_binding']['scope_version']=99
        self.assertIn('STORYBOARD_BINDING_STALE',{e['code'] for e in check(self.d,damaged,self.tmp.name)['errors']})
        doc=self.store.read();doc['source_text']='更改来源原文';self.d=self.store.update(doc,doc['revision'])
        self.assertIn('STORYBOARD_BINDING_STALE',{e['code'] for e in check(self.d,spec,self.tmp.name)['errors']})

if __name__=='__main__':unittest.main()
