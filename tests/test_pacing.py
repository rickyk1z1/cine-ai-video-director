"""Explicit timing edits, dependency boundaries and atomic failure; no media claims."""
import copy
import tempfile
import unittest
from pathlib import Path

from test_store import Store, new_document, new_shot, uid
import pacing
import production


def document():
    doc = new_document('离线校准：车票收纳夹')
    shots = []
    for index, content in enumerate(('车票靠近收纳夹', '车票滑入透明夹层',
                                     '手翻到下一页', '夹内车票与出行小物同框')):
        shot = new_shot()
        shot.update(number='S'+str(index+1), content=content, duration=5)
        shots.append(shot)
    doc['sections'] = [{'id': uid(), 'title': '桌面产品', 'notes': '', 'groups': [
        {'id': uid(), 'title': '归位', 'notes': '', 'shots': shots}]}]
    return doc


def plan(doc):
    ids = production.shot_ids(doc['sections'][0])
    reasons = ['手与相机同时靠近，不另加建立停顿', '连续滑入，保持读取插入关系的时间',
               '承接翻页后半段，不重复起手动作', '只保留有用途的结果辨认，其他空等移除']
    return {'evidence': '离线方法夹具：依据逐镜正常速度想象试读给暂估，非实测或创意正确性证明。',
            'source_revision': doc['revision'], 'shots': [
                {'shot_id': sid, 'duration': seconds, 'basis': reason,
                 'duration_range': [seconds-.25, seconds+.25]}
                for sid, seconds, reason in zip(ids, [2.5, 4, 3, 4], reasons)]}


class PacingTests(unittest.TestCase):
    def setUp(self):
        self.doc = document()

    def test_explicit_twenty_to_thirteen_point_five_changes_current_content(self):
        proposal = plan(self.doc)
        proposal['shots'][0]['changes'] = {
            'content': '手把车票移到夹层入口，相机同时轻推靠近。',
            'camera': '随手部靠近，停止时入口已可辨，不另等一次机位停稳。',
            'sound': '纸张摩擦声跟随滑动，不另加提示音等待。',
            'transition': '滑入动作中硬切到近景，后镜接着完成。'}
        before, original_plan = copy.deepcopy(self.doc), copy.deepcopy(proposal)
        updated = pacing.apply(self.doc, proposal)
        self.assertEqual(pacing.summary(before)['content_duration_seconds'], 20)
        self.assertEqual(pacing.summary(updated)['content_duration_seconds'], 13.5)
        shots = updated['sections'][0]['groups'][0]['shots']
        self.assertEqual([s['duration'] for s in shots], [2.5, 4, 3, 4])
        self.assertEqual(shots[0]['camera'], proposal['shots'][0]['changes']['camera'])
        self.assertEqual(self.doc, before)
        self.assertEqual(proposal, original_plan)
        self.assertEqual(updated['revision'], before['revision'])

    def test_parallel_beats_are_not_summed_or_used_to_score_quality(self):
        proposal = plan(self.doc)
        proposal['shots'][1]['beats'] = [
            {'description': '车票滑入', 'start': 0, 'end': 4},
            {'description': '相机轻推与动作并行', 'start': 0, 'end': 4}]
        updated = pacing.apply(self.doc, proposal)
        self.assertEqual(updated['sections'][0]['groups'][0]['shots'][1]['duration'], 4)
        self.assertEqual(pacing.summary(updated)['content_duration_seconds'], 13.5)

    def test_late_invalid_entry_leaves_all_original_content_unchanged(self):
        proposal = plan(self.doc); proposal['shots'][-1]['duration'] = -1
        before = copy.deepcopy(self.doc)
        with self.assertRaises(ValueError):
            pacing.apply(self.doc, proposal)
        self.assertEqual(self.doc, before)

    def test_unknown_duration_is_reported_and_can_receive_an_explicit_estimate(self):
        shots = self.doc['sections'][0]['groups'][0]['shots']
        shots[0]['duration'] = None; shots[1]['duration'] = 0
        report = pacing.summary(self.doc)
        self.assertIsNone(report['content_duration_seconds'])
        self.assertEqual(report['known_duration_seconds'], 10)
        self.assertEqual(report['unknown_shot_ids'], [shots[0]['id'], shots[1]['id']])
        self.assertEqual(pacing.summary(pacing.apply(self.doc, plan(self.doc)))['content_duration_seconds'], 13.5)

    def test_partial_scope_does_not_modify_other_shots(self):
        proposal = plan(self.doc); proposal['shots'] = proposal['shots'][1:2]
        updated = pacing.apply(self.doc, proposal)
        self.assertEqual([s['duration'] for s in updated['sections'][0]['groups'][0]['shots']], [5, 4, 5, 5])
        self.assertEqual(pacing.summary(updated, [proposal['shots'][0]['shot_id']])['content_duration_seconds'], 4)

    def test_invalid_numbers_evidence_scope_and_unsupported_mutations_are_rejected(self):
        mutations = [
            lambda p: p.update(evidence=''), lambda p: p.update(shots=[]),
            lambda p: p.update(source_revision=99), lambda p: p.update(source_revision=True),
            lambda p: p['shots'].append(copy.deepcopy(p['shots'][0])),
            lambda p: p['shots'][0].update(shot_id='missing'),
            lambda p: p['shots'][0].update(basis=' '),
            lambda p: p['shots'][0].update(changes={'number': 'S99'}),
            lambda p: p['shots'][0].update(changes={'sound': 3}),
            lambda p: p.update(parameters={'duration': 15}),
            lambda p: p['shots'][0].update(duration_range=[4, 2]),
            lambda p: p['shots'][0].update(duration_range=[3, 4]),
            lambda p: p['shots'][0].update(beats=[{'description': '越界', 'start': 0, 'end': 9}]),
            lambda p: p['shots'][0].update(beats=[{'description': '', 'start': 0, 'end': 1}]),
        ]
        for value in (None, True, 0, -1, '2', float('nan'), float('inf')):
            mutations.append(lambda p, value=value: p['shots'][0].update(duration=value))
        for mutate in mutations:
            proposal = plan(self.doc); mutate(proposal)
            with self.subTest(proposal=proposal), self.assertRaises(ValueError):
                pacing.apply(self.doc, proposal)

    def test_unknown_selection_and_invalid_stored_numbers_are_not_silently_totalled(self):
        for ids in ([], ['missing'], ['same', 'same']):
            with self.assertRaises(ValueError):pacing.summary(self.doc, ids)
        for value in (True, -1, float('nan'), float('inf')):
            self.doc['sections'][0]['groups'][0]['shots'][0]['duration'] = value
            with self.assertRaises(ValueError):pacing.summary(self.doc)

    def test_timing_only_keeps_adopted_stills_but_invalidates_current_package(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Store(directory); doc = store.create('', self.doc)
            sid = doc['sections'][0]['id']; ids = production.shot_ids(doc['sections'][0])
            doc = store.confirm(sid, doc['revision'], 'OFFLINE fixture confirmation')
            Path(directory, 'frame.png').write_bytes(b'offline non-rendered reference fixture')
            doc = store.record({'id': 'IMAGE', 'kind': 'asset', 'title': 'Fixture frame',
                'section_ids': [sid], 'shot_ids': [ids[0]],
                'files': [{'path': 'frame.png', 'role': 'storyboard_frame'}],
                'data': {'asset_role': 'storyboard_frame', 'adoption_evidence': 'OFFLINE fixture adoption'}}, doc['revision'])
            doc = store.record({'id': 'PKG', 'kind': 'package', 'title': 'Historical input fixture',
                'section_ids': [sid], 'shot_ids': ids,
                'data': {'parameters': {'duration': 20}, 'prompt': 'OFFLINE original 20 second input'}}, doc['revision'])
            doc = store.record({'id': 'TASK', 'kind': 'task', 'title': 'Historical submission fixture',
                'section_ids': [sid], 'shot_ids': ids,
                'data': {'package_id': 'PKG', 'package_version': 1, 'status': 'submitted',
                         'task_id': 'OFFLINE-no-real-submission', 'submittedPrompt': 'OFFLINE original 20 second input'}}, doc['revision'])
            original = copy.deepcopy(doc['production'])
            updated = pacing.apply(doc, plan(doc))
            self.assertEqual(updated['production'], original)
            records = {r['id']: r for r in updated['production']['records']}
            self.assertFalse(production.is_stale(updated, records['IMAGE'], directory))
            self.assertEqual(production.record_review_status(records['IMAGE']), 'adopted')
            self.assertTrue(production.is_stale(updated, records['PKG'], directory))
            saved = store.transact({'document': updated}, doc['revision'])
            self.assertEqual(saved['production']['records'], original['records'])
            self.assertEqual(saved['production']['confirmations'], original['confirmations'])
            self.assertEqual(pacing.summary(saved)['content_duration_seconds'], 13.5)

    def test_deliberate_slow_shot_can_be_longer_and_dialogue_window_is_protected(self):
        proposal = plan(self.doc); proposal['shots'] = [proposal['shots'][0]]
        proposal['shots'][0].update(duration=6.4, duration_range=[6.4, 7],
            basis='测试夹具给定6.4秒录音窗口；必须保留听者反应，不能因整体想变短删掉声音。')
        updated = pacing.apply(self.doc, proposal)
        self.assertEqual(updated['sections'][0]['groups'][0]['shots'][0]['duration'], 6.4)
        proposal['shots'][0]['duration'] = 4
        with self.assertRaises(ValueError):pacing.apply(self.doc, proposal)

    def test_second_genre_compacts_entry_while_retaining_meaningful_slow_observation(self):
        doc = document(); doc['title'] = '离线纸面暂估：搬家前的空屋'
        shots = doc['sections'][0]['groups'][0]['shots'][:3]
        doc['sections'][0]['groups'][0]['shots'] = shots
        for shot, duration, content in zip(shots, [7, 7, 6],
                ['摸索拿稳并取下最后的合照', '凝视墙面留下的浅印', '离开房间并关灯']):
            shot.update(duration=duration, content=content)
        proposal = {'evidence': '虚构方法夹具，正常速度的纸面暂估；不是实测，保留有意情绪停留。',
            'shots': [
                {'shot_id': shots[0]['id'], 'duration': 3, 'duration_range': [2.5, 3.5],
                 'basis': '入口改为已经扶住相框，取下与相机拉开并行，去掉重复建立空屋。',
                 'changes': {'start': '手已扶住相框两侧。', 'content': '取下最后一张合照。',
                             'camera': '随取下动作轻拉开，同时显露墙面浅印。'}},
                {'shot_id': shots[1]['id'], 'duration': 6, 'duration_range': [5.5, 6.5],
                 'basis': '浅印承载离开感，6秒观察具有叙事作用，不能跟第一镜同比压缩。'},
                {'shot_id': shots[2]['id'], 'duration': 5, 'duration_range': [4.5, 5.5],
                 'basis': '离门与摄影跟随并行，灯灭便结束，不再附加空镜。',
                 'changes': {'end': '人物离门，关灯，画面暗下即结束。'}}]}
        updated = pacing.apply(doc, proposal)
        self.assertEqual(pacing.summary(doc)['content_duration_seconds'], 20)
        self.assertEqual(pacing.summary(updated)['content_duration_seconds'], 14)
        self.assertEqual([s['duration'] for s in updated['sections'][0]['groups'][0]['shots']], [3, 6, 5])


if __name__ == '__main__':
    unittest.main()
