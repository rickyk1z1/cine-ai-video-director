import copy
import unittest
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import production
import test_production as fixtures


class RecommendationBasisTests(unittest.TestCase):
    def setUp(self):
        self.t = fixtures.ProductionTests()
        self.t.setUp()
        self.addCleanup(self.t.doCleanups)

    def plan(self):
        r = self.t.base('COMPARE', 'decision')
        option = dict(id='a', path='direct_platform', recommended=True,
                      model='fixture A v1', platform='fixture entrance', input_mode='text',
                      reason='Both support the required duration; existing inputs fit A.',
                      inputs='existing reference', limits='motion not tested')
        r['data'] = dict(decision_type='generation_recommendation', planning_version=1,
                         options=[option, dict(option, id='b', model='fixture B v1', recommended=False)],
                         method_evidence=dict(status='unavailable', summary='Offline fixture; no performance comparison.'))
        r['data']['selection_basis'] = dict(status='provisional',
            priorities=['continuous camera movement', 'reuse existing inputs'],
            comparison='Both are feasible; no demonstrated quality advantage. A reuses the available inputs.',
            cost='No new asset preparation; price and retry cost unknown.',
            uncertainty='Character stability and final motion remain untested.')
        return r

    def test_provisional_basis_survives_selection_current_and_export_without_permission(self):
        r = self.plan(); self.t.record(r)
        d = self.t.store.choose_route('COMPARE', 'direct_platform', self.t.store.read()['revision'], 'b')
        self.assertEqual(d['_workflow']['scopes'][0]['phase'], 0)
        self.assertEqual(production.permission_shots(d), set())
        self.assertEqual(d['_current_routes'][self.t.ids[0]]['option_id'], 'b')
        current = self.t.store.current(self.t.sid)
        self.assertEqual(current['generation_plans'][0]['data']['selection_basis'], r['data']['selection_basis'])
        exported = self.t.store.text(self.t.confirm())
        self.assertIn('暂定推荐依据', exported)
        for key in ('comparison', 'cost', 'uncertainty'):
            self.assertIn(r['data']['selection_basis'][key], exported)

    def test_unknown_cost_and_no_comparative_source_do_not_block_selection(self):
        r = self.plan(); self.t.record(r)
        self.t.store.choose_route('COMPARE', 'direct_platform', self.t.store.read()['revision'], 'a')
        self.assertEqual(self.t.store.current(self.t.sid)['routes'][self.t.ids[0]]['option_id'], 'a')

    def test_malformed_basis_rejected_without_partial_write(self):
        original = self.t.store.read()
        for change in [dict(status='winner'), dict(priorities='not a list'), dict(priorities=[]),
                       dict(comparison=''), dict(cost=3), dict(uncertainty='')]:
            with self.subTest(change=change):
                r = self.plan(); r['data']['selection_basis'].update(change)
                with self.assertRaisesRegex(ValueError, '推荐依据'):
                    self.t.record(r)
                self.assertEqual(self.t.store.read()['revision'], original['revision'])
                self.assertFalse(self.t.store.current(self.t.sid)['generation_plans'])

    def test_legacy_record_needs_no_new_basis_or_gate(self):
        r = self.plan(); del r['data']['selection_basis']; self.t.record(r)
        d = self.t.store.choose_route('COMPARE', 'direct_platform', self.t.store.read()['revision'], 'a')
        self.assertEqual(d['_workflow']['scopes'][0]['phase'], 0)
        self.assertNotIn('selection_basis', self.t.store.current(self.t.sid)['generation_plans'][0]['data'])

    def test_source_kind_and_local_result_reference_roundtrip(self):
        r = self.plan()
        sources = [dict(kind=k, url='record:checked-fixture-result' if k=='observed_result' else 'https://example.com/fixture',
                        checked_at='2026-09-27', model_version='fixture v1', platform='fixture entrance',
                        applied='supports only this stated observation', limits='does not prove superiority')
                   for k in ['official', 'case', 'observed_result', 'user_report']]
        r['data']['method_evidence'] = dict(status='reused', summary='Four kinds of fixture evidence.', sources=sources)
        self.t.record(r)
        actual = self.t.store.current(self.t.sid)['generation_plans'][0]
        self.assertEqual(actual['data']['method_evidence']['sources'], sources)
        broken = copy.deepcopy(r); broken['data']['method_evidence']['sources'][0]['kind'] = 'ranking_guarantee'
        with self.assertRaisesRegex(ValueError, '依据类型'): self.t.record(broken)
        self.assertEqual(self.t.store.current(self.t.sid)['generation_plans'][0]['data']['method_evidence']['sources'], sources)

    def test_comparison_update_keeps_existing_route_and_phase(self):
        self.t.confirm(); self.t.path_decision(); r=self.plan(); self.t.record(r)
        self.t.store.choose_route('COMPARE','direct_platform',self.t.store.read()['revision'],'a')
        before=self.t.store.read()
        r['data']['selection_basis']['cost']='Preparation unchanged; account price still unknown.'
        self.t.record(r); after=self.t.store.read()
        self.assertEqual(after['_workflow']['scopes'][0]['phase'],before['_workflow']['scopes'][0]['phase'])
        self.assertEqual(after['_current_routes'][self.t.ids[0]]['option_id'],'a')
        self.assertEqual(after['production']['confirmations'],before['production']['confirmations'])
