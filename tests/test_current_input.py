"""Compact reads and partial package updates must preserve source truth and guards."""
import copy
import json
from pathlib import Path
import subprocess
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import storyboard
import test_v3_workflow as fixtures


class CurrentInputTests(unittest.TestCase):
    def setUp(self):
        self.fixture=fixtures.WorkflowV3Tests();self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.t=self.fixture.t;self.store=self.t.store

    def prepare(self):
        package=self.fixture.v3_package()
        return self.store.prepare(package,self.store.read()['revision'])

    def test_current_is_read_only_and_retains_pending_and_stale(self):
        self.fixture.picture('PENDING',status='candidate')
        self.fixture.picture('SELECTED')
        doc=self.store.read();doc['sections'][0]['groups'][0]['shots'][0]['content']='新的动作'
        self.store.update(doc,doc['revision']);full=self.store.read()
        before=self.store.path.read_bytes();current=self.store.current(self.t.sid)
        self.assertEqual(before,self.store.path.read_bytes())
        self.assertEqual(current['sections'],[full['sections'][0]])
        self.assertEqual(current['workflow']['scopes'],[full['_workflow']['scopes'][0]])
        indexed={r['id']:r for r in current['records']}
        for rid in ('PENDING','SELECTED'):
            self.assertEqual(indexed[rid]['state'],full['_record_states'][rid])
        self.assertTrue(indexed['SELECTED']['state']['stale'])
        self.assertNotIn('history',indexed['SELECTED'])
        with self.assertRaises(ValueError):self.store.current('missing')

    def test_single_record_is_editable_without_history_and_keeps_version(self):
        self.prepare();original=self.store.read()
        result=self.store.read_record('P')
        self.assertEqual(result['revision'],original['revision'])
        self.assertNotIn('history',result['record'])
        self.assertEqual(result['record']['data'],next(r for r in original['production']['records'] if r['id']=='P')['data'])
        with self.assertRaises(ValueError):self.store.read_record('missing')

    def test_current_excludes_retired_but_keeps_referenced_outside_scope(self):
        other=self.store.read()['sections'][1]['id']
        record=self.t.base('OLD','decision');self.t.record(record)
        record=self.t.base('NEW','decision');record['data']={'supersedes':['OLD']};self.t.record(record)
        record=self.t.base('SHARED','style',[]);record['section_ids']=[other];self.t.record(record)
        record=self.t.base('USES','decision');record['depends_on']=['SHARED'];self.t.record(record)
        indexed={r['id']:r for r in self.store.current(self.t.sid)['records']}
        self.assertNotIn('OLD',indexed);self.assertIn('NEW',indexed);self.assertIn('SHARED',indexed)

    def test_partial_prepare_preserves_inputs_and_exact_review(self):
        prepared=self.prepare();old=prepared['record'];before=self.store.read()
        prompt=old['data']['prompt']+'\n镜头运动平稳。'
        changed=self.store.prepare({'body':'本轮补充平稳摄影','data':{'prompt':prompt,'prompt_review':{'prompt':prompt}}},before['revision'],record_id='P')
        self.assertEqual(changed['issues'],[])
        for field in ('references','sound_plan','timeline','parameters','production_path_decision_id'):
            self.assertEqual(changed['record']['data'].get(field),old['data'].get(field))
        self.assertEqual(changed['record']['data']['prompt_review']['continuity_review'],old['data']['prompt_review']['continuity_review'])
        self.assertEqual(changed['record']['data']['prompt_review']['input_sha256'],changed['input_sha256'])
        self.assertNotEqual(prepared['input_sha256'],changed['input_sha256'])
        self.assertEqual(changed['record']['history'][-1]['data']['prompt'],old['data']['prompt'])
        self.assertEqual(self.store.read()['_workflow'],before['_workflow'])

    def test_bad_changes_and_revision_conflict_do_not_write(self):
        prepared=self.prepare();revision=self.store.read()['revision'];before=self.store.path.read_bytes()
        bad=[{'data':{'prompt':'未经复核的新正文'}}, {'id':'different'}, {'unknown':True},
             {'data':{'prompt_review':{'reference_policy':[]}}}, {'data':{'references':[]}},
             {'data':{'timeline':[]}}, {'data':{'prompt':'不同正文','prompt_review':{'prompt':'另一份'}}}]
        for patch in bad:
            with self.subTest(patch=patch),self.assertRaises((ValueError,storyboard.Conflict)):
                self.store.prepare(patch,revision,record_id='P')
            self.assertEqual(before,self.store.path.read_bytes())
        with self.assertRaises(storyboard.Conflict):self.store.prepare({'title':'改名'},revision-1,record_id='P')
        self.assertEqual(before,self.store.path.read_bytes())

    def test_cli_current_and_record_read(self):
        self.prepare();cli=str(storyboard.ROOT/'scripts/storyboard.py')
        current=json.loads(subprocess.check_output([sys.executable,cli,'current','--directory',str(self.t.root),'--section-id',self.t.sid]))
        record=json.loads(subprocess.check_output([sys.executable,cli,'read','--directory',str(self.t.root),'--record-id','P']))
        self.assertEqual(current['revision'],record['revision']);self.assertEqual(record['record']['id'],'P')
        full=json.loads(subprocess.check_output([sys.executable,cli,'read','--directory',str(self.t.root)]))
        self.assertIn('production',full);self.assertIn('_record_states',full)
        compact=json.loads(subprocess.check_output([sys.executable,cli,'package','--directory',str(self.t.root),'--record-id','P','--compact']))
        self.assertEqual(compact['issues'],[]);self.assertNotIn('record',compact);self.assertNotIn('review_input',compact)
        self.assertEqual(compact['input_sha256'],self.store.package('P')['input_sha256'])
        patch=self.t.root/'package-change.json';patch.write_text(json.dumps({'title':'局部更新标题'}))
        updated=json.loads(subprocess.check_output([sys.executable,cli,'prepare','--directory',str(self.t.root),
            '--record-id','P','--input',str(patch),'--expected-revision',str(record['revision']),'--compact']))
        self.assertEqual(updated['issues'],[]);self.assertNotIn('record',updated)
        self.assertEqual(self.store.read_record('P')['record']['title'],'局部更新标题')
        self.assertEqual(updated['input_sha256'],compact['input_sha256'])

if __name__=='__main__':unittest.main()
