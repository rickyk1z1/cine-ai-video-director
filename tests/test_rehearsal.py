import copy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from test_store import fixture, new_shot
import production
import rehearsal


class RehearsalTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.doc = fixture()
        self.doc['production'] = {'records': [], 'confirmations': {}, 'export_hash': None}
        shots = self.doc['sections'][0]['groups'][0]['shots']
        shots.append(new_shot())
        self.ids = [s['id'] for s in shots]
        self.rows = []
        for i, shot in enumerate(shots):
            shot['duration'] = i + 2
            shot['content'] = '实际内容' + str(i)
            path = str(i) + '.png'
            (self.root / path).write_bytes(b'actual-frame' + bytes([i]))
            record = {'id': 'asset' + str(i), 'kind': 'asset', 'data': {}, 'files': [{'path': path}]}
            self.doc['production']['records'].append(record)
            self.rows.append({'shot_id': shot['id'], 'images': [
                {'record_id': record['id'], 'file_index': 0, 'path': path, 'review_status': 'adopted', 'moment': ''}]})
        self.patch = patch.object(production, 'preview_rows', side_effect=lambda *args: copy.deepcopy(self.rows))
        self.patch.start()
        self.addCleanup(self.patch.stop)

    def manifest(self, **kwargs):
        return rehearsal.manifest(self.doc, self.root, **kwargs)

    def review(self, **kwargs):
        m = self.manifest(**kwargs)
        order = m['shot_ids']
        return {'kind': 'decision', 'shot_ids': order,
                'data': {'decision_type': 'sequence_review', 'review_version': 3, 'result': 'ready',
                         'summary': '按实际图序计时看完，开灯原因可见，最后留给观众辨认陶碗。',
                         'manifest': {key: m[key] for key in ('scope', 'shot_ids', 'fingerprint', 'fingerprints')},
                         'continuity_review': {
                             'units': [{'id': sid, 'shot_id': sid} for sid in order],
                             'joins': [{'from': a, 'to': b, 'type': 'action_cut', 'audience_bridge': '同一人继续动作',
                                        'evidence': '实际首尾图保持杯碟与手位', 'budget_check': '辨认与动作各留时间',
                                        'status': 'resolved'} for a, b in zip(order, order[1:])]}}}

    def check(self, record, ids=None):
        return rehearsal.validate_review(self.doc, record, self.root, shot_ids=ids)

    def test_manifest_uses_actual_order_and_bytes_without_verdict(self):
        m = self.manifest(shot_ids=list(reversed(self.ids)))
        self.assertEqual(m['shot_ids'], self.ids)
        self.assertEqual(m['total_duration'], 9)
        self.assertEqual(m['frames'][1]['timeline_start'], 2)
        self.assertEqual(m['issues'], [])
        self.assertNotIn('ready', m)
        self.assertEqual(m['frames'][0]['images'][0]['sha256'], production.file_digest(self.root, '0.png'))

    def test_current_complete_review_valid(self):
        result = self.check(self.review())
        self.assertTrue(result['ok'], result['issues'])
        self.assertIn('不能证明', result['limits'])

    def test_file_change_invalidates_affected_shot_and_join(self):
        r = self.review()
        (self.root / '1.png').write_bytes(b'replaced')
        result = self.check(r)
        self.assertFalse(result['ok'])
        self.assertIn('当前接点', '\n'.join(result['issues']))
        self.assertTrue(self.check(r, [self.ids[0]])['ok'])

    def test_unrelated_shot_change_does_not_block_unchanged_package(self):
        r = self.review()
        self.doc['sections'][0]['groups'][0]['shots'][2]['duration'] = 10
        self.assertFalse(self.check(r)['ok'])
        self.assertTrue(self.check(r, self.ids[:2])['ok'])

    def test_new_cut_cannot_reuse_removed_middle_shot_join(self):
        r = self.review()
        result = self.check(r, [self.ids[0], self.ids[2]])
        self.assertFalse(result['ok'])
        self.assertIn('当前接点', '\n'.join(result['issues']))

    def test_new_shot_in_full_scope_requires_review(self):
        r = self.review()
        s = new_shot()
        s['duration'] = 2
        self.doc['sections'][0]['groups'][0]['shots'].insert(1, s)
        self.assertFalse(self.check(r)['ok'])
        self.assertTrue(self.check(r, [self.ids[0]])['ok'])

    def test_reorder_requires_actual_new_pair(self):
        r = self.review()
        self.doc['sections'][0]['groups'][0]['shots'].reverse()
        self.assertFalse(self.check(r)['ok'])
        self.assertFalse(self.check(r, self.ids[:2])['ok'])

    def test_missing_duration_returns_images_and_cannot_pass(self):
        self.doc['sections'][0]['groups'][0]['shots'][0]['duration'] = None
        m = self.manifest()
        self.assertTrue(m['frames'][0]['images'])
        self.assertIsNone(m['total_duration'])
        self.assertFalse(self.check(self.review())['ok'])

    def test_candidate_and_missing_file_cannot_enter_rehearsal(self):
        self.rows[0]['images'][0]['review_status'] = 'candidate'
        (self.root / '1.png').unlink()
        m = self.manifest()
        self.assertEqual(m['frames'][0]['images'], [])
        self.assertEqual(m['frames'][1]['images'], [])
        self.assertGreaterEqual(len(m['issues']), 2)

    def test_multiple_states_use_endpoint_order_or_explicit_order(self):
        end = self.rows[0]['images'][0]
        end['moment'] = 'state_end'
        start = copy.deepcopy(end)
        start.update(moment='state_start', file_index=1)
        record = self.doc['production']['records'][0]
        record['files'].append({'path': '0.png'})
        self.rows[0]['images'].append(start)
        m = self.manifest()
        self.assertEqual([i['moment'] for i in m['frames'][0]['images']], ['state_start', 'state_end'])
        end['moment'] = 'later'
        start['moment'] = 'earlier'
        self.assertFalse(self.manifest()['issues'])  # Existing file-list order is usable.
        record['files'][0]['sequence_order'] = 2
        record['files'][1]['sequence_order'] = 1
        self.assertEqual(self.manifest()['frames'][0]['images'][0]['moment'], 'earlier')
        self.assertFalse(self.manifest()['issues'])

    def test_cross_record_ambiguous_order_reports_actionable_gap(self):
        image = copy.deepcopy(self.rows[0]['images'][0])
        image.update(record_id='another', path='1.png')
        self.rows[0]['images'].append(image)
        self.doc['production']['records'].append({'id': 'another', 'kind': 'asset', 'data': {}, 'files': [{'path': '1.png'}]})
        m = self.manifest()
        self.assertEqual(len(m['frames'][0]['images']), 2)
        self.assertIn('多条记录', '\n'.join(m['issues']))

    def test_real_preview_consumer_selects_only_current_adopted_files(self):
        from test_store import Store
        self.patch.stop()
        store = Store(self.root)
        doc = fixture()
        for shot in doc['sections'][0]['groups'][0]['shots']:
            shot['duration'] = 2
        doc = store.create('', doc)
        section = doc['sections'][0]
        doc = store.confirm(section['id'], doc['revision'], '用户确认本段文字')
        for i, shot in enumerate(section['groups'][0]['shots']):
            record = {'id': 'real' + str(i), 'kind': 'asset', 'title': '实际采用图', 'body': '',
                      'section_ids': [section['id']], 'shot_ids': [shot['id']], 'depends_on': [],
                      'files': [{'path': str(i) + '.png', 'role': 'storyboard_frame'}],
                      'data': {'asset_role': 'storyboard_frame', 'adoption_evidence': '用户已采用'}}
            doc = store.record(record, doc['revision'])
        m = rehearsal.manifest(doc, self.root)
        self.assertFalse(m['issues'], m['issues'])
        self.assertEqual(len(m['frames']), 2)
        self.assertEqual(m['frames'][1]['images'][0]['record_id'], 'real1')

    def test_required_authored_judgment_and_actual_unit_coverage(self):
        for mutation in ('summary', 'result', 'coverage', 'join', 'fingerprint'):
            with self.subTest(mutation=mutation):
                r = self.review()
                d = r['data']
                if mutation == 'summary': d['summary'] = ''
                if mutation == 'result': d['result'] = 'revise'
                if mutation == 'coverage': d['continuity_review']['units'][0]['shot_id'] = 'OTHER'
                if mutation == 'join': d['continuity_review']['joins'].pop()
                if mutation == 'fingerprint': d['manifest']['fingerprint'] = 'stale'
                self.assertFalse(self.check(r)['ok'])

    def test_design_gap_fails_but_unverified_dynamics_remain_explicit(self):
        r = self.review()
        r['data']['continuity_review']['joins'][0]['status'] = 'design_gap'
        self.assertFalse(self.check(r)['ok'])
        r['data']['continuity_review']['joins'][0]['status'] = 'unverified'
        result = self.check(r)
        self.assertTrue(result['ok'], result['issues'])
        self.assertEqual(len(result['unverified_joins']), 1)

    def test_review_never_mutates_document_or_record(self):
        r = self.review()
        original_doc, original_record = copy.deepcopy(self.doc), copy.deepcopy(r)
        self.check(r)
        self.assertEqual(self.doc, original_doc)
        self.assertEqual(r, original_record)

    def test_digest_cache_does_not_survive_next_read(self):
        first = self.manifest()['fingerprint']
        (self.root / '0.png').write_bytes(b'new-image')
        self.assertNotEqual(first, self.manifest()['fingerprint'])

    def test_local_update_retains_first_summary_and_explicitly_resolves_readiness(self):
        r = self.review()
        r['data']['result'] = 'revise'
        self.doc['sections'][0]['groups'][0]['shots'][1]['duration'] = 5
        before = copy.deepcopy(r)
        updated = rehearsal.update_review(self.doc, r, self.root, [self.ids[1]], {
            'summary': '延长辨认时间后，实际看过本镜与前后接点，原问题已解决。',
            'continuity_review': r['data']['continuity_review'], 'result': 'ready'})
        self.assertEqual(r, before)
        self.assertEqual(updated['data']['summary'], before['data']['summary'])
        self.assertEqual(updated['data']['local_updates'][0]['previous_result'], 'revise')
        self.assertTrue(self.check(updated)['ok'])
        self.assertEqual(updated['data']['result'], 'ready')

    def test_local_update_does_not_infer_ready(self):
        r = self.review()
        r['data']['result'] = 'revise'
        updated = rehearsal.update_review(self.doc, r, self.root, [self.ids[1]], {
            'summary': '实际核对图序，部分建议仍待落实。', 'continuity_review': r['data']['continuity_review']})
        self.assertEqual(updated['data']['result'], 'revise')
        self.assertFalse(self.check(updated)['ok'])

    def test_local_insertion_extends_same_review_with_new_joins(self):
        r = self.review()
        shot = new_shot()
        shot['duration'] = 1
        self.doc['sections'][0]['groups'][0]['shots'].insert(1, shot)
        row = copy.deepcopy(self.rows[0])
        row['shot_id'] = shot['id']
        self.rows.append(row)
        table = self.review()['data']['continuity_review']
        updated = rehearsal.update_review(self.doc, r, self.root, [shot['id']], {
            'summary': '实际看过新增的反应镜头及两端接点，动机现在可见。', 'continuity_review': table})
        self.assertTrue(self.check(updated)['ok'])
        self.assertEqual(updated['data']['summary'], r['data']['summary'])
        self.assertIn(shot['id'], updated['shot_ids'])

    def test_local_removal_checks_the_new_bridge(self):
        r = self.review()
        self.doc['sections'][0]['groups'][0]['shots'].pop(1)
        table = self.review()['data']['continuity_review']
        updated = rehearsal.update_review(self.doc, r, self.root, [self.ids[1]], {
            'summary': '删除重复镜后看过实际新切点，原信息完整保留。', 'continuity_review': table})
        self.assertTrue(self.check(updated)['ok'])
        self.assertNotIn(self.ids[1], updated['shot_ids'])

    def test_local_update_cannot_silently_rewrite_unrelated_evidence(self):
        r = self.review()
        table = copy.deepcopy(r['data']['continuity_review'])
        table['joins'][1]['evidence'] = '未经核对的新说法'
        with self.assertRaisesRegex(ValueError, '未受影响'):
            rehearsal.update_review(self.doc, r, self.root, [self.ids[0]], {
                'summary': '只看了第一镜及其接点', 'continuity_review': table})

    def test_local_update_requires_real_authored_evidence(self):
        with self.assertRaisesRegex(ValueError, '实际核对依据'):
            rehearsal.update_review(self.doc, self.review(), self.root, [self.ids[0]], {})

    def test_bad_scope_and_empty_scope_fail(self):
        self.assertTrue(self.manifest(shot_ids=[])['issues'])
        self.assertTrue(self.manifest(shot_ids=['missing'])['issues'])
        self.assertTrue(self.manifest(section_ids=['missing'])['issues'])


if __name__ == '__main__':
    unittest.main()
