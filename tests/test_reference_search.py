import copy
import unittest

import reference_search as refs


class ReferenceSearchTests(unittest.TestCase):
    def pending(self):
        return refs.request([], '穿过门洞进入画中空间', {'shot_ids': ['s1']}, now=1000)

    def started(self):
        return refs.apply(self.pending(), {'action': 'begin'}, now=1100)

    def candidate(self, number=1, **changes):
        item = {'title': '实际参考' + str(number),
                'source_url': 'https://eyecannndy.com/technique/pass-through',
                'watch_range': '示例' + str(number), 'match_reason': '镜头连续穿过前景开口',
                'difference': '原片是现代空间，本场为明代水岸',
                'reuse_note': '只借鉴遮挡后连续前进的空间揭示', 'observation': 'viewed'}
        item.update(changes)
        return item

    def add(self, sessions, number=1, now=1101, **changes):
        return refs.apply(sessions, {'action': 'add_candidate', 'candidate': self.candidate(number, **changes)}, now)

    def test_pending_does_not_spend_budget_and_begin_is_idempotent(self):
        pending = self.pending()
        self.assertEqual(refs.view(pending, 10000)['remaining_seconds'], 240)
        started = refs.apply(pending, {'action': 'begin'}, 10000)
        again = refs.apply(started, {'action': 'begin'}, 10050)
        self.assertEqual(again[-1]['started_at'], started[-1]['started_at'])
        self.assertEqual(refs.view(again, 10050)['remaining_seconds'], 190)

    def test_repeated_request_does_not_make_new_round_or_restart(self):
        done = refs.apply(self.started(), {'action': 'stop'}, 1110)
        again = refs.request(done, '穿过门洞进入画中空间', {'shot_ids': ['s1']}, 2000)
        self.assertEqual(again, done)
        with self.assertRaises(ValueError):
            refs.apply(done, {'action': 'begin'}, 2000)

    def test_three_matching_viewed_examples_stop_and_no_fourth(self):
        sessions = self.started()
        for i in range(1, 4):
            sessions = self.add(sessions, i, 1100 + i)
        state = refs.view(sessions, 1104)
        self.assertEqual(state['current']['status'], 'ready')
        self.assertEqual(state['valid_count'], 3)
        self.assertFalse(state['can_search'])
        with self.assertRaises(ValueError):
            self.add(sessions, 4, 1104)

    def test_unverified_and_unmatched_do_not_count(self):
        sessions = self.add(self.started(), 1, observation='unverified')
        sessions = self.add(sessions, 2, matched=False)
        self.assertEqual(refs.view(sessions, 1105)['valid_count'], 0)
        self.assertTrue(refs.view(sessions, 1105)['can_search'])

    def test_timeout_with_zero_or_partial_results_finishes_without_padding(self):
        for sessions in (self.started(), self.add(self.started())):
            state = refs.view(sessions, 1340)
            self.assertEqual(state['current']['status'], 'exhausted')
            self.assertEqual(state['current']['stop_reason'], 'time_budget')
            self.assertEqual(state['remaining_seconds'], 0)
            self.assertFalse(state['can_search'])
            with self.assertRaises(ValueError):
                self.add(sessions, 2, 1340)

    def test_timeout_can_record_existing_observation_but_not_new_search(self):
        sessions = refs.apply(self.started(), {'action': 'add_candidate', 'record_existing': True,
                              'candidate': self.candidate(observed_at=1339)}, now=1500)
        self.assertEqual(sessions[-1]['status'], 'exhausted')
        self.assertEqual(refs.view(sessions, 1500)['valid_count'], 1)
        for observed in (1099, 1340.1, 1501):
            with self.assertRaises(ValueError):
                refs.apply(self.started(), {'action': 'add_candidate', 'record_existing': True,
                           'candidate': self.candidate(observed_at=observed)}, now=1500)
        at_deadline = refs.apply(self.started(), {'action': 'add_candidate', 'record_existing': True,
                                'candidate': self.candidate(observed_at=1340)}, now=1500)
        self.assertEqual(at_deadline[-1]['candidates'][0]['observed_at'], refs._stamp(1340))

    def test_late_existing_results_without_exact_time_are_presented_honestly(self):
        sessions = self.started()
        original_start = sessions[-1]['started_at']
        for number in (1, 2):
            sessions = refs.apply(sessions, {'action': 'add_candidate', 'record_existing': True,
                                  'candidate': self.candidate(number)}, now=1500 + number)
        state = refs.view(sessions, 1600)
        self.assertEqual(state['valid_count'], 2)
        self.assertEqual(state['current']['status'], 'exhausted')
        self.assertFalse(state['can_search'])
        self.assertEqual(state['elapsed_seconds'], 240)
        self.assertEqual(sessions[-1]['started_at'], original_start)
        for number, item in enumerate(sessions[-1]['candidates'], 1):
            self.assertIsNone(item['observed_at'])
            self.assertEqual(item['recorded_at'], refs._stamp(1500 + number))
            self.assertIs(item['late_completion'], True)
        with self.assertRaises(ValueError):
            refs.apply(sessions, {'action': 'begin'}, now=1600)
        with self.assertRaises(ValueError):
            self.add(sessions, 3, now=1600)

    def test_explicit_unknown_time_wrapup_still_stops_at_three(self):
        sessions = self.started()
        for number in (1, 2, 3):
            sessions = refs.apply(sessions, {'action': 'add_candidate', 'record_existing': True,
                                  'candidate': self.candidate(number, observed_at=None)}, now=1500 + number)
        self.assertEqual(sessions[-1]['status'], 'ready')
        self.assertEqual(sessions[-1]['stopped_at'], refs._stamp(1340))
        self.assertEqual(refs.view(sessions, 1600)['valid_count'], 3)
        with self.assertRaises(ValueError):
            refs.apply(sessions, {'action': 'add_candidate', 'record_existing': True,
                       'candidate': self.candidate(4)}, now=1600)

    def test_unknown_time_lead_can_be_observed_later_without_inventing_initial_time(self):
        sessions = refs.apply(self.started(), {'action': 'add_candidate', 'record_existing': True,
                              'candidate': self.candidate(observation='unverified')}, now=1500)
        cid = sessions[-1]['candidates'][0]['id']
        sessions = refs.apply(sessions, {'action': 'observe', 'candidate_id': cid,
                              'observation_note': '收尾查看已打开片段'}, now=1510)
        self.assertIsNone(sessions[-1]['candidates'][0]['observed_at'])
        self.assertEqual(sessions[-1]['candidates'][0]['viewed_at'], refs._stamp(1510))
        refs.validate(sessions)

    def test_manual_stop_only_accepts_observations_before_that_stop(self):
        sessions = refs.apply(self.started(), {'action': 'stop', 'reason': '平台访问受限'}, 1120)
        with self.assertRaises(ValueError):
            refs.apply(sessions, {'action': 'add_candidate', 'record_existing': True,
                       'candidate': self.candidate(observed_at=1121)}, 1130)
        sessions = refs.apply(sessions, {'action': 'add_candidate', 'record_existing': True,
                              'candidate': self.candidate(observed_at=1119)}, 1130)
        self.assertEqual(len(sessions[-1]['candidates']), 1)

    def test_catalog_sources_are_accepted_and_spoofs_or_other_sources_are_rejected(self):
        self.assertEqual(len({s['id'] for s in refs.SOURCES}), len(refs.SOURCES))
        for source in refs.SOURCES:
            with self.subTest(source=source['id']):
                sessions = self.add(self.started(), source_url=source['url'])
                self.assertEqual(sessions[-1]['candidates'][0]['source_id'], source['id'])
                with self.assertRaises(ValueError):
                    self.add(self.started(), source_url='https://' + source['domain'] + '.attacker.example/')
        self.assertEqual(refs.source_for_url('https://site.frameset.app/')['id'], 'frameset')
        for url in ('https://flim.ai/', 'https://youtube.com/watch?v=x',
                    'https://eyecannndy.com.attacker.example/',
                    'https://attacker.example/?next=https://eyecannndy.com/',
                    'https://attacker@eyecannndy.com/', 'http://eyecannndy.com/',
                    'https://eyecannndy.com:444/', 'https://eyecannndy.com\\@example.com/'):
            with self.subTest(url=url), self.assertRaises(ValueError):
                self.add(self.started(), source_url=url)

    def test_observed_external_https_media_is_optional_not_source_authority(self):
        sessions = self.add(self.started(), preview_url='https://cdn.example.com/seen.mp4', preview_kind='video')
        self.assertEqual(sessions[-1]['candidates'][0]['preview_kind'], 'video')
        for url in ('javascript:alert(1)', 'http://cdn.example.com/a.gif', 'https://localhost/a',
                    'https://127.0.0.1/a', 'https://10.1.1.1/a', 'https://u:p@cdn.example.com/a'):
            with self.subTest(url=url), self.assertRaises(ValueError):
                self.add(self.started(), preview_url=url, preview_kind='gif')

    def test_same_source_can_show_distinct_identified_examples_without_duplicates(self):
        sessions = self.add(self.started())
        with self.assertRaises(ValueError):
            self.add(sessions, source_url='https://eyecannndy.com/technique/pass-through#same')
        sessions = self.add(sessions, 2)
        self.assertEqual(len(sessions[-1]['candidates']), 2)

    def test_observe_existing_lead_after_timeout_is_wrapup_not_new_search(self):
        sessions = self.add(self.started(), observation='unverified')
        candidate_id = sessions[-1]['candidates'][0]['id']
        sessions = refs.apply(sessions, {'action': 'observe', 'candidate_id': candidate_id,
                              'observation_note': '实际看过第二个GIF，前景遮挡后仍连续前移'}, 1500)
        self.assertEqual(refs.view(sessions, 1500)['valid_count'], 1)
        self.assertFalse(refs.view(sessions, 1500)['can_search'])

    def test_choose_needs_viewed_match_and_specific_adoption_note(self):
        sessions = self.add(self.started(), observation='unverified')
        candidate_id = sessions[-1]['candidates'][0]['id']
        with self.assertRaises(ValueError):
            refs.apply(sessions, {'action': 'choose', 'candidate_id': candidate_id,
                                 'adoption_note': '借鉴遮挡转场', 'selection_by': 'assistant'}, 1105)
        sessions = refs.apply(sessions, {'action': 'observe', 'candidate_id': candidate_id,
                              'observation_note': '看过实际遮挡段落'}, 1105)
        with self.assertRaises(ValueError):
            refs.apply(sessions, {'action': 'choose', 'candidate_id': candidate_id}, 1106)
        sessions = refs.apply(sessions, {'action': 'choose', 'candidate_id': candidate_id,
                              'adoption_note': '只采用前景遮挡后进入画中的动态关系'}, 1106)
        self.assertEqual(sessions[-1]['chosen_candidate_id'], candidate_id)
        self.assertFalse(refs.view(sessions, 1106)['can_search'])

    def test_user_can_choose_unverified_without_fabricating_assistant_observation(self):
        sessions = self.add(self.started(), observation='unverified')
        candidate_id = sessions[-1]['candidates'][0]['id']
        sessions = refs.apply(sessions, {'action': 'choose', 'candidate_id': candidate_id,
                              'adoption_note': '用户选择原站第二个案例的遮挡进入效果'}, 1105)
        self.assertEqual(sessions[-1]['status'], 'ready')
        self.assertEqual(sessions[-1]['selection_by'], 'user')
        self.assertEqual(sessions[-1]['candidates'][0]['observation'], 'unverified')
        self.assertEqual(refs.view(sessions, 1105)['valid_count'], 0)

    def test_validate_rejects_malformed_persisted_state_with_value_error(self):
        for bad in (None, {}, [None], [{}], [{'id': 'x', 'status': 'searching'}]):
            with self.subTest(value=bad), self.assertRaises(ValueError):
                refs.validate(bad)
        mutations = [('started_at', None), ('requested_at', 'bad'), ('status', 'unknown'),
                     ('candidates', {}), ('restrictions', [None]), ('adoption_note', 3)]
        for key, value in mutations:
            sessions = self.started()
            sessions[-1][key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                refs.view(sessions, 1120)
        sessions = self.add(self.started())
        sessions[-1]['candidates'][0]['source_url'] = 'https://flim.ai/'
        with self.assertRaises(ValueError):
            refs.validate(sessions)

    def test_validate_rejects_ids_times_and_selection_drift(self):
        sessions = self.add(self.started())
        for key, value in [('source_id', 'stash'), ('matched', 'yes'), ('observed_at', None),
                           ('recorded_at', '1970-01-01T00:01:00Z')]:
            changed = copy.deepcopy(sessions)
            changed[-1]['candidates'][0][key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                refs.validate(changed)
        changed = copy.deepcopy(sessions)
        changed[-1]['candidates'].append(copy.deepcopy(changed[-1]['candidates'][0]))
        with self.assertRaises(ValueError):
            refs.validate(changed)
        changed[-1]['candidates'][1]['id'] = 'new-id-same-example'
        with self.assertRaises(ValueError):
            refs.validate(changed)
        changed = copy.deepcopy(sessions)
        changed[-1]['restrictions'] = [{'source_id': []}]
        with self.assertRaises(ValueError):
            refs.validate(changed)
        changed = copy.deepcopy(sessions)
        changed[-1]['chosen_candidate_id'] = 'missing'
        with self.assertRaises(ValueError):
            refs.validate(changed)

    def test_reject_requires_feedback_and_new_round_waits_for_begin(self):
        sessions = self.add(self.started())
        with self.assertRaises(ValueError):
            refs.apply(sessions, {'action': 'reject'}, 1110)
        new = refs.apply(sessions, {'action': 'reject', 'feedback': '要平缓穿入，不要突然加速'}, 1110)
        self.assertEqual(len(new), 2)
        self.assertEqual(new[-1]['status'], 'request')
        self.assertIsNone(new[-1]['started_at'])
        self.assertEqual(new[-1]['request_feedback'], '要平缓穿入，不要突然加速')
        self.assertEqual(refs.view(new, 9999)['remaining_seconds'], 240)
        with self.assertRaises(ValueError):
            refs.apply(new, {'action': 'begin', 'session_id': sessions[-1]['id']}, 1111)

    def test_restrictions_are_plain_data_and_not_personal_entitlements(self):
        sessions = refs.apply(self.started(), {'action': 'record_restriction', 'source_id': 'stash',
                              'capability': '完整馆藏播放', 'reason': '当前页面要求会员',
                              'value': '可比较更多动态图形作品'}, 1110)
        self.assertEqual(sessions[-1]['restrictions'][0]['source_id'], 'stash')
        self.assertNotIn('account', refs.SOURCES[1])
        self.assertEqual(refs.view(sessions, 1110)['current']['status'], 'searching')

    def test_operations_and_derived_timeout_do_not_mutate_inputs(self):
        sessions = self.started()
        original = copy.deepcopy(sessions)
        refs.view(sessions, 2000)
        self.add(sessions)
        self.assertEqual(sessions, original)
        with self.assertRaises(ValueError):
            self.add(sessions, source_url='https://example.com/')
        self.assertEqual(sessions, original)

    def test_clock_is_explicit_and_validated(self):
        sessions = refs.request([], '参考', now='2026-09-24T01:00:00Z')
        sessions = refs.apply(sessions, {'action': 'begin'}, now='2026-09-24T02:00:00+01:00')
        self.assertEqual(refs.view(sessions, now='2026-09-24T01:01:00Z')['remaining_seconds'], 180)
        for bad in (True, float('nan'), float('inf'), '2026-09-24T01:00:00'):
            with self.subTest(now=bad), self.assertRaises(ValueError):
                refs.view(sessions, bad)
        with self.assertRaises(ValueError):
            refs.view(self.started(), 1099)


if __name__ == '__main__':
    unittest.main()
