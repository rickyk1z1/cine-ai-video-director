import copy
import hashlib
import unittest

import test_prompt_guard as legacy_tests

guard = legacy_tests.guard


class PromptV3Tests(unittest.TestCase):
    def bundle(self):
        boundary = '普通参考图片仅供身份与结构参考，不要求依次到达或完整复现参考图构图。'
        sound = '保留接杯与杯碟轻碰的动作声，不生成音乐。'
        action = '接稳杯碟后交出方松手，硬切到同一人品茶。'
        return {
            'review_version': 3,
            'prompt': f'{sound}\n{boundary}\n\n<node-asset>ref1</node-asset>提供人物身份。{action}',
            'reference_policy': [{'id': 'ref1', 'type': 'image', 'use': '人物身份',
                                  'mode': 'reference', 'not_required': '完整构图与展示姿态'}],
            'delivery_contract': {'reference_boundary': boundary},
            'requirements': [
                {'requirement': '保留已定动作声与禁音乐要求', 'source': '本批声音计划',
                 'clause': sound, 'placement': 'opening'},
                {'requirement': '接稳之后松手', 'source': '已定交接动作', 'clause': action},
            ],
            'continuity_review': {
                'units': [{'id': 'receive', 'shot_id': 'SH01'}, {'id': 'sip', 'shot_id': 'SH02'}],
                'joins': [self.join('receive', 'sip')],
            },
        }

    def join(self, start, end, status='resolved'):
        return {'from': start, 'to': end, 'type': 'action_ellipsis',
                'audience_bridge': '同人同杯，接稳后品茶',
                'evidence': '本批相邻镜头保持同一杯碟与衣袖',
                'budget_check': '直接轻饮，不重复抬杯', 'status': status}

    def check(self, bundle):
        return guard.inspect(bundle, expected_shot_ids=['SH01', 'SH02'])

    def test_v3_requires_no_long_self_review_forms(self):
        result = self.check(self.bundle())
        self.assertTrue(result['ok'], result['errors'])
        self.assertFalse(result['legacy_review'])
        self.assertEqual(result['review_signals'], [])
        self.assertIn('不能证明', result['limits'])

    def test_boundary_moved_to_end_fails_even_with_same_words(self):
        bundle = self.bundle()
        boundary = bundle['delivery_contract']['reference_boundary']
        bundle['prompt'] = bundle['prompt'].replace(boundary, '') + '\n' + boundary
        self.assertIn('普通参考总边界', '\n'.join(self.check(bundle)['errors']))

    def test_boundary_after_first_tag_in_opening_block_fails(self):
        bundle = self.bundle()
        bundle['prompt'] = '<node-asset>ref1</node-asset>提供身份。\n' + bundle['prompt']
        self.assertFalse(self.check(bundle)['ok'])

    def test_custom_boundary_after_initial_title_passes(self):
        bundle = self.bundle()
        bundle['prompt'] = '# 本次视频\n\n' + bundle['prompt']
        self.assertTrue(self.check(bundle)['ok'])

    def test_boundary_is_not_allowed_in_later_paragraph_without_tags(self):
        bundle = self.bundle()
        bundle['requirements'] = []
        bundle['prompt'] = '连续接杯。\n\n' + bundle['delivery_contract']['reference_boundary']
        self.assertFalse(self.check(bundle)['ok'])

    def test_actual_asset_syntax_limits_opening(self):
        for tag in ('<pippit-asset-id>ref1</pippit-asset-id>', '@图1', '<Picture 1>'):
            with self.subTest(tag=tag):
                bundle = self.bundle()
                bundle['prompt'] = tag + '提供身份。' + bundle['prompt']
                self.assertFalse(self.check(bundle)['ok'])

    def test_lost_action_clause_fails(self):
        bundle = self.bundle()
        bundle['prompt'] = bundle['prompt'].replace(bundle['requirements'][1]['clause'], '自然完成交接。')
        self.assertIn('正文缺少已定约束原句', '\n'.join(self.check(bundle)['errors']))

    def test_opening_sound_cannot_move_after_references(self):
        bundle = self.bundle()
        sound = bundle['requirements'][0]['clause']
        bundle['prompt'] = bundle['prompt'].replace(sound, '') + '\n' + sound
        self.assertIn('已定约束未放在开头', '\n'.join(self.check(bundle)['errors']))

    def test_requirement_needs_source_and_exact_clause(self):
        for field in ('requirement', 'source', 'clause'):
            with self.subTest(field=field):
                bundle = self.bundle()
                del bundle['requirements'][0][field]
                self.assertFalse(self.check(bundle)['ok'])

    def test_empty_requirements_allowed_when_no_extra_decisions(self):
        bundle = self.bundle()
        bundle['requirements'] = []
        self.assertTrue(self.check(bundle)['ok'])

    def test_undeclared_requirement_list_is_not_silently_invented(self):
        bundle = self.bundle()
        del bundle['requirements']
        self.assertFalse(self.check(bundle)['ok'])

    def test_unrelated_unit_cannot_stand_for_two_real_shots(self):
        bundle = self.bundle()
        bundle['continuity_review'] = {'units': [{'id': 'unrelated', 'shot_id': 'OTHER'}], 'joins': []}
        self.assertIn('精确覆盖实际包镜头', '\n'.join(self.check(bundle)['errors']))

    def test_missing_extra_reordered_and_revisited_shots_fail(self):
        for shots in (['SH01'], ['SH01', 'SH02', 'EXTRA'], ['SH02', 'SH01'], ['SH01', 'SH02', 'SH01']):
            with self.subTest(shots=shots):
                bundle = self.bundle()
                ids = [f'phase{i}' for i in range(len(shots))]
                bundle['continuity_review'] = {
                    'units': [{'id': uid, 'shot_id': sid} for uid, sid in zip(ids, shots)],
                    'joins': [self.join(a, b) for a, b in zip(ids, ids[1:])],
                }
                self.assertFalse(self.check(bundle)['ok'])

    def test_multiple_phases_share_one_shot_without_inventing_a_cut(self):
        bundle = self.bundle()
        bundle['continuity_review'] = {
            'units': [{'id': 'reach', 'shot_id': 'SH01'}, {'id': 'receive', 'shot_id': 'SH01'},
                      {'id': 'sip', 'shot_id': 'SH02'}],
            'joins': [self.join('reach', 'receive'), self.join('receive', 'sip')],
        }
        self.assertTrue(self.check(bundle)['ok'])
        bundle['continuity_review']['joins'].pop(0)
        self.assertFalse(self.check(bundle)['ok'])

    def test_duplicate_unit_id_and_missing_shot_id_fail(self):
        bundle = self.bundle()
        bundle['continuity_review']['units'][1]['id'] = 'receive'
        self.assertFalse(self.check(bundle)['ok'])
        bundle = self.bundle()
        del bundle['continuity_review']['units'][0]['shot_id']
        self.assertFalse(self.check(bundle)['ok'])

    def test_unverified_dynamic_is_exposed_but_design_gap_blocks(self):
        bundle = self.bundle()
        bundle['continuity_review']['joins'][0]['status'] = 'unverified'
        result = self.check(bundle)
        self.assertTrue(result['ok'])
        self.assertEqual(len(result['unverified_joins']), 1)
        bundle['continuity_review']['joins'][0]['status'] = 'design_gap'
        self.assertFalse(self.check(bundle)['ok'])

    def test_strict_boundary_requires_evidence_and_does_not_require_ordinary_disclaimer(self):
        bundle = self.bundle()
        bundle['prompt'] = bundle['prompt'].replace(bundle['delivery_contract']['reference_boundary'], '')
        bundle['reference_policy'][0]['mode'] = 'strict_boundary'
        self.assertFalse(self.check(bundle)['ok'])
        bundle['reference_policy'][0].update(scope='首帧人物构图', evidence='本批用户选择首帧；真实入口已绑定')
        self.assertTrue(self.check(bundle)['ok'])

    def test_mixed_strict_and_ordinary_references_keep_ordinary_boundary(self):
        bundle = self.bundle()
        bundle['reference_policy'].append({'id': 'frame1', 'type': 'image', 'use': '首帧构图',
                                           'mode': 'strict_boundary', 'scope': '仅首帧',
                                           'evidence': '用户明确选定，实际首帧接口绑定'})
        self.assertTrue(self.check(bundle)['ok'])
        bundle['prompt'] = bundle['prompt'].replace(bundle['delivery_contract']['reference_boundary'], '')
        self.assertFalse(self.check(bundle)['ok'])

    def test_unmapped_real_attachment_tag_fails(self):
        bundle = self.bundle()
        bundle['prompt'] += '<pippit-asset-id>missing</pippit-asset-id>'
        self.assertFalse(self.check(bundle)['ok'])

    def test_prompt_hash_tracks_exact_body(self):
        bundle = self.bundle()
        before = self.check(bundle)['prompt_sha256']
        bundle['prompt'] += '\n必要的后续动作。'
        after = self.check(bundle)['prompt_sha256']
        self.assertNotEqual(before, after)
        self.assertEqual(after, hashlib.sha256(bundle['prompt'].encode()).hexdigest())

    def test_no_keyword_blacklist_pretends_to_judge_context(self):
        bundle = self.bundle()
        bundle['prompt'] += '角色在教室用PPT展示名为后期制作的页面，随后切到屏幕。'
        self.assertTrue(self.check(bundle)['ok'])

    def test_missing_real_shot_ids_is_reported_as_unverified(self):
        result = guard.inspect(self.bundle())
        self.assertTrue(result['ok'])
        self.assertIn('shot_coverage_unverified', [s['code'] for s in result['review_signals']])

    def test_legacy_remains_readable_and_explicitly_marked(self):
        bundle = legacy_tests.PromptGuardTests().bundle()
        before = copy.deepcopy(bundle)
        result = guard.inspect(bundle)
        self.assertTrue(result['ok'])
        self.assertTrue(result['legacy_review'])
        self.assertIn('legacy_review', [s['code'] for s in result['review_signals']])
        self.assertEqual(bundle, before)

    def test_legacy_cannot_hide_unrelated_units_when_real_shots_are_known(self):
        bundle = legacy_tests.PromptGuardTests().bundle()
        self.assertFalse(self.check(bundle)['ok'])
        bundle['continuity_review']['unit_shots'] = {'receive': 'SH01', 'sip': 'SH02'}
        self.assertTrue(self.check(bundle)['ok'])
        bundle['continuity_review']['unit_shots']['sip'] = 'OTHER'
        self.assertFalse(self.check(bundle)['ok'])

    def test_legacy_unit_ids_that_are_real_shot_ids_need_no_mapping(self):
        bundle = legacy_tests.PromptGuardTests().bundle()
        bundle['continuity_review']['units'] = ['SH01', 'SH02']
        bundle['continuity_review']['joins'] = [self.join('SH01', 'SH02')]
        self.assertTrue(self.check(bundle)['ok'])

    def test_unknown_version_does_not_silently_use_legacy(self):
        bundle = self.bundle()
        bundle['review_version'] = 99
        self.assertFalse(self.check(bundle)['ok'])

    def test_malformed_v3_returns_errors_instead_of_crashing(self):
        for key, value in (('reference_policy', [{'id': [], 'type': 'image'}]),
                           ('continuity_review', None), ('delivery_contract', None),
                           ('requirements', [None]), ('prompt', None)):
            with self.subTest(key=key):
                bundle = self.bundle()
                bundle[key] = value
                self.assertFalse(self.check(bundle)['ok'])


if __name__ == '__main__':
    unittest.main()
