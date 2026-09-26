import copy
import io
import json
import unittest
from urllib.error import URLError
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
import production
import storyboard
import method_cases
import test_production as fixtures
import test_prompt_v3 as prompt_fixtures

class PlanningTests(unittest.TestCase):
    def setUp(self):
        self.t=fixtures.ProductionTests();self.t.setUp();self.addCleanup(self.t.doCleanups)
    def plan(self):
        r=self.t.base('PLAN31','decision')
        option={'id':'h3','path':'direct_platform','recommended':True,'model':'H3','platform':'fixture-A','input_mode':'text-to-video','reason':'不锁身份的抽象动态图','inputs':'无需新增图片','limits':'身份不固定'}
        r['data']={'decision_type':'generation_recommendation','planning_version':1,
            'method_evidence':{'status':'unavailable','summary':'离线测试；使用用户指定路线，不伪造查阅'},
            'options':[option,{**option,'id':'other','model':'fixture-model','platform':'fixture-B','recommended':False}]}
        self.t.record(r);return r
    def test_early_selection_disambiguates_providers_and_keeps_stage(self):
        self.plan();s=self.t.store
        with self.assertRaisesRegex(ValueError,'option_id'):s.choose_route('PLAN31','direct_platform',s.read()['revision'])
        d=s.choose_route('PLAN31','direct_platform',s.read()['revision'],'other')
        self.assertEqual(d['_workflow']['scopes'][0]['phase'],0)
        self.assertEqual(d['_current_routes'][self.t.ids[0]]['model'],'fixture-model')
        self.assertEqual(production.permission_shots(d),set())
        current=s.current(self.t.sid)
        self.assertEqual(current['generation_plans'][0]['id'],'PLAN31')
        self.assertTrue(current['workflow']['scopes'][0]['next_actions'])
        self.assertIn('fixture-B',s.text(self.t.confirm()))
        self.assertNotIn(self.t.doc['sections'][1]['id'],[x['section_id'] for x in current['workflow']['scopes']])
    def test_mixed_scope_selection_does_not_advance_unstarted_section(self):
        t=self.t;t.confirm();t.path_decision();r=self.plan();other=t.doc['sections'][1]
        r['section_ids'].append(other['id']);r['shot_ids']+=production.shot_ids(other);t.record(r)
        d=t.store.choose_route('PLAN31','direct_platform',t.store.read()['revision'],'h3')
        phases={s['section_id']:s['phase'] for s in d['_workflow']['scopes']}
        self.assertEqual(phases[t.sid],2);self.assertEqual(phases[other['id']],0)

    def test_reuse_source_cannot_be_empty(self):
        r=self.plan();r['data']['method_evidence']['status']='reused'
        with self.assertRaisesRegex(ValueError,'来源'):self.t.record(r)
    def test_new_shot_not_silently_assigned_previous_model(self):
        t=self.t;t.confirm();t.path_decision();d=t.store.read();sh=storyboard.new_shot();sh['content']='新增音频驱动片段'
        d['sections'][0]['groups'][0]['shots'].append(sh)
        out=t.store.transact({'document':d,'evidence':'增加这一镜'},d['revision'],revise=True)
        self.assertNotIn(sh['id'],production.current_routes(out));self.assertEqual(out['_workflow']['scopes'][0]['phase'],2)
        self.assertTrue(any(a['code']=='assess_route' for a in out['_workflow']['scopes'][0]['next_actions']))
    def test_large_revision_keeps_progress_and_does_not_adopt_new_art(self):
        t=self.t;t.confirm();t.path_decision();t.frame();d=t.store.read()
        before=copy.deepcopy(d['production']['confirmations'])
        for sh in d['sections'][0]['groups'][0]['shots']:sh.update(content='用户要求完全改变这段内容',start='新起点',end='新终点')
        out=t.store.transact({'document':d,'evidence':'整段文字改成这个，图片都换掉'},d['revision'],revise=True)
        self.assertEqual(out['_workflow']['scopes'][0]['phase'],2)
        self.assertEqual(out['production']['confirmations'],before)
        self.assertTrue(out['_preview_rows'][0]['images'])
        self.assertEqual(out['_preview_rows'][0]['status'],'needs_review')
        self.assertTrue(production.can_prepare(out,t.base('NEW','asset')))
    def test_package_checks_model_and_input_mode(self):
        t=self.t;t.confirm();route=t.path_decision();route['data'].update(model='H3',input_mode='first_frame');t.record(route)
        d=t.store.read();r=t.base('P','package');r['depends_on']=['PATH'];r['data']={'production_path_decision_id':'PATH','production_batch_id':'batch-1','platform':'test-only','model':'different','input_mode':'text','route':'direct'}
        issues=production.package_path_issues(d,r,t.root,{x['id']:x for x in production.state(d)['records']})
        self.assertTrue(any('model' in x for x in issues));self.assertTrue(any('input_mode' in x for x in issues))

class TagTests(unittest.TestCase):
    def test_attributes_and_malformed_tags(self):
        t=prompt_fixtures.PromptV3Tests()
        for tag,valid in [('<node-asset label="角色 > 侧面">ref1</node-asset>',True),("<pippit-asset-id label='人物' class='ref'>ref1</pippit-asset-id>",True),('<node-asset label="人">missing</node-asset>',False),('<node-asset label="人">ref1</pippit-asset-id>',False),('<node-asset label="人">ref1',False),('<node-asset/>',False)]:
            with self.subTest(tag=tag):
                b=t.bundle();b['prompt']=b['prompt'].replace('<node-asset>ref1</node-asset>',tag)
                self.assertEqual(t.check(b)['ok'],valid,t.check(b))
        b=t.bundle();b['prompt']='<node-asset label="人">ref1</node-asset>'+b['prompt']
        self.assertFalse(t.check(b)['ok'])

class CaseTests(unittest.TestCase):
    def test_bounded_results_and_failure(self):
        def opener(req,timeout):return io.BytesIO(json.dumps({'items':[{'slug':str(n),'promptFull':'large','title':'case'} for n in range(8)]}).encode())
        result=method_cases.lookup('search','motion',take=2,opener=opener)
        self.assertEqual(len(result['items']),2);self.assertNotIn('promptFull',result['items'][0])
        def fail(req,timeout):raise URLError('offline')
        self.assertEqual(method_cases.lookup('search','motion',opener=fail)['status'],'unavailable')
        self.assertEqual(method_cases.lookup('search','motion',opener=lambda r,timeout:io.BytesIO(b'{"items":[]}'))['status'],'no_match')
        with self.assertRaises(ValueError):method_cases.lookup('detail',slug='../private')
