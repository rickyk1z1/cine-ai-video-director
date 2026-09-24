"""Read-only static sequence rehearsal and evidence binding; no generated verdicts."""
import copy
import math

import production
import prompt_guard

LIMITS = ('结构与指纹校验不能证明整段叙事成立。助手须按实际图序和时长观看并记录判断；'
          '静帧计时不能证明真实运动、口型、声音或生成结果。')


def _text(value):
    return isinstance(value, str) and bool(value.strip())


def _key(a, b):
    # JSON hashing would hide the pair from reviewers; IDs cannot contain this separator.
    return a + '→' + b


def _binding(order, fingerprints, scope):
    return production.digest({'shot_ids': order, 'fingerprints': fingerprints, 'scope': scope})


def manifest(doc, root, section_ids=None, shot_ids=None):
    """Return the current adopted sequence in document order, with no semantic pass."""
    with production.evaluation():
        return _manifest(doc, root, section_ids, shot_ids)


def _manifest(doc, root, section_ids, shot_ids):
    issues = []
    selected_sections = None if section_ids is None else set(section_ids)
    selected_shots = None if shot_ids is None else set(shot_ids)
    cancelled = production.cancelled_sections(doc)
    rows = {row['shot_id']: row for row in production.preview_rows(doc, root)}
    records = {r['id']: r for r in production.active_records(doc)}
    frames, fingerprints = [], {'shots': {}, 'joins': {}}
    elapsed = 0
    known_sections, known_shots = set(), set()
    source = {'brief': doc.get('brief', ''), 'source_text': doc.get('source_text', '')}
    for section in doc['sections']:
        known_sections.add(section['id'])
        for group in section['groups']:
            for shot in group['shots']:
                sid = shot['id']
                known_shots.add(sid)
                if (section['id'] in cancelled
                        or selected_sections is not None and section['id'] not in selected_sections
                        or selected_shots is not None and sid not in selected_shots):
                    continue
                row = rows.get(sid, {})
                images = []
                for item in row.get('images', []):
                    if item.get('review_status') != 'adopted':
                        continue
                    image = copy.deepcopy(item)
                    try:
                        image['sha256'] = production.file_digest(root, item['path'])
                    except (ValueError, OSError) as exc:
                        issues.append(sid + '：' + str(exc))
                        continue
                    file = records[item['record_id']]['files'][item['file_index']]
                    image['sequence_order'] = file.get('sequence_order')
                    images.append(image)
                if not images:
                    issues.append(sid + '：没有当前有效的采用分镜图')
                # Share display order; sorting does not resolve missing evidence.
                if len(images) > 1:
                    images, explicit_order = production.ordered_state_images(images)
                    if not explicit_order and len({i['record_id'] for i in images}) > 1:
                        issues.append(sid + '：多条记录的采用图状态顺序不明确；助手补充唯一 sequence_order 或明确首尾状态')
                duration = shot.get('duration')
                valid_duration = type(duration) in (int, float) and math.isfinite(duration) and duration > 0
                if not valid_duration:
                    issues.append(sid + '：缺少有效预计时长，不能用默认秒数替代实际节奏')
                frame = {key: copy.deepcopy(shot.get(key, '')) for key in
                         ('number', 'content', 'framing', 'camera', 'sound', 'start', 'end', 'transition', 'assets', 'reason', 'notes')}
                frame.update(shot_id=sid, section_id=section['id'], section=section['title'],
                             duration=duration, images=images, timeline_start=elapsed,
                             timeline_end=elapsed + duration if elapsed is not None and valid_duration else None)
                # Number/title are display metadata. Notes and source are shared dependencies.
                material = {key: value for key, value in frame.items()
                            if key not in ('number', 'section', 'timeline_start', 'timeline_end')}
                material['images'] = [{key: i.get(key) for key in
                                       ('path', 'sha256', 'moment', 'box', 'size', 'sequence_order')} for i in images]
                material['source'] = source
                material['section_notes'] = section.get('notes', '')
                material['group_notes'] = group.get('notes', '')
                fingerprints['shots'][sid] = production.digest(material)
                frame['fingerprint'] = fingerprints['shots'][sid]
                frames.append(frame)
                elapsed = frame['timeline_end']
    if selected_sections is not None and selected_sections - known_sections:
        issues.append('预演范围包含不存在的段落：' + ', '.join(sorted(selected_sections - known_sections)))
    if selected_shots is not None:
        actual = {frame['shot_id'] for frame in frames}
        if selected_shots - actual:
            issues.append('预演范围包含不存在、已取消或不属于所选段落的镜头：' + ', '.join(sorted(selected_shots - actual)))
    order = [frame['shot_id'] for frame in frames]
    if not order:
        issues.append('预演范围为空')
    adjacent = []
    for a, b in zip(frames, frames[1:]):
        key = _key(a['shot_id'], b['shot_id'])
        fingerprint = production.digest([a['shot_id'], a['fingerprint'], b['shot_id'], b['fingerprint']])
        fingerprints['joins'][key] = fingerprint
        adjacent.append({'from': a['shot_id'], 'to': b['shot_id'], 'fingerprint': fingerprint,
                         'end': a['end'], 'start': b['start'], 'transition': a['transition']})
    scope = {'section_ids': list(section_ids) if section_ids is not None else None,
             'shot_ids': list(shot_ids) if shot_ids is not None else None}
    return {'version': 1, 'scope': scope, 'source_fingerprint': production.digest(source), 'shot_ids': order, 'frames': frames, 'adjacent_pairs': adjacent,
            'fingerprints': fingerprints, 'fingerprint': _binding(order, fingerprints, scope),
            'total_duration': elapsed, 'issues': issues, 'limits': LIMITS}


def validate_review(doc, record, root, shot_ids=None):
    """Check whether historical evidence covers this sequence; never a new review gate.

    A ready result is the assistant's authored judgment, not a programmatic finding.
    A mismatch describes coverage, not a requirement to review a human revision again.
    This validator never changes the document, adoption, or permissions.
    """
    issues, unverified = [], []
    if not isinstance(record, dict):
        return {'ok': False, 'issues': ['整段审查记录格式错误'], 'unverified_joins': [], 'limits': LIMITS}
    data = record.get('data', {})
    if not isinstance(data, dict):
        data = {}
    if record.get('kind') != 'decision' or data.get('decision_type') != 'sequence_review':
        issues.append('记录不是整段图序审查')
    if data.get('review_version') != 3:
        issues.append('整段图序审查须使用 v3 连续单位')
    if data.get('result') != 'ready':
        issues.append('该次结论仍为建议修订，或缺少实际审查结论；这不表示整段审查未完成')
    if not _text(data.get('summary')):
        issues.append('缺少实际观看发现与整段判断')
    saved = data.get('manifest', {})
    if not isinstance(saved, dict):
        saved = {}
    old_order = saved.get('shot_ids')
    if not isinstance(old_order, list) or not old_order or any(not _text(s) for s in old_order) or len(old_order) != len(set(old_order)):
        issues.append('审查缺少唯一有序的实际镜头范围')
        old_order = []
    binding = saved.get('fingerprints', {})
    if not isinstance(binding, dict):
        binding = {}
    old_shots, old_joins = binding.get('shots', {}), binding.get('joins', {})
    if not isinstance(old_shots, dict) or not isinstance(old_joins, dict):
        issues.append('审查缺少逐镜与相邻接点指纹')
        old_shots, old_joins = {}, {}
    scope = copy.deepcopy(saved.get('scope'))
    if not isinstance(scope, dict) or set(scope) != {'section_ids', 'shot_ids'}:
        issues.append('审查缺少实际范围选择方式')
        scope = {'section_ids': None, 'shot_ids': old_order}
    for key in ('section_ids', 'shot_ids'):
        ids = scope.get(key)
        if ids is not None and (not isinstance(ids, list) or any(not _text(s) for s in ids)):
            issues.append('审查范围选择格式错误')
            scope[key] = []
    if saved.get('fingerprint') != _binding(old_order, binding, scope):
        issues.append('审查范围指纹不完整或被改变')
    record_scope = record.get('shot_ids', [])
    if not isinstance(record_scope, list) or any(not _text(s) for s in record_scope) or set(record_scope) != set(old_order):
        issues.append('审查记录范围与实际预演范围不一致')
    wanted = old_order if shot_ids is None else list(shot_ids)
    if not wanted or any(not _text(s) for s in wanted) or len(wanted) != len(set(wanted)):
        issues.append('本次验证须指定唯一有效镜头范围')
        wanted = []
    current = manifest(doc, root, **scope) if shot_ids is None else manifest(doc, root, shot_ids=wanted)
    issues.extend(current['issues'])
    current_order = current['shot_ids']
    if shot_ids is None and current_order != old_order:
        issues.append('镜头顺序已变化，原判断不覆盖新顺序；整段审查完成事实保留')
    for sid in current_order:
        if sid not in old_order or old_shots.get(sid) != current['fingerprints']['shots'][sid]:
            issues.append(sid + '：镜头文字、节奏、采用图或来源已变化；原判断不覆盖新版本')
    for pair in current['adjacent_pairs']:
        if old_joins.get(_key(pair['from'], pair['to'])) != pair['fingerprint']:
            issues.append(pair['from'] + ' → ' + pair['to'] + '：当前接点不在原审查依据内')
    continuity = data.get('continuity_review', {})
    # Validate the authored historical coverage first, then inspect statuses only in scope.
    structural = copy.deepcopy(continuity) if isinstance(continuity, dict) else {}
    joins = structural.get('joins', [])
    if isinstance(joins, list):
        for join in joins:
            if isinstance(join, dict) and join.get('status') in ('resolved', 'unverified', 'design_gap'):
                join['status'] = 'resolved'
    prompt_guard._continuity_errors({'continuity_review': structural}, issues, True, old_order)
    units = continuity.get('units', []) if isinstance(continuity, dict) else []
    units = units if isinstance(units, list) else []
    by_unit = {u.get('id'): u.get('shot_id') for u in units if isinstance(u, dict) and _text(u.get('id'))}
    joins = continuity.get('joins', []) if isinstance(continuity, dict) else []
    for join in joins if isinstance(joins, list) else []:
        if not isinstance(join, dict):
            continue
        if not _text(join.get('from')) or not _text(join.get('to')):
            continue
        a, b = by_unit.get(join.get('from')), by_unit.get(join.get('to'))
        relevant = a in current_order and b in current_order and (a == b or _key(a, b) in current['fingerprints']['joins'])
        if relevant and join.get('status') == 'design_gap':
            issues.append(str(join.get('from')) + ' → ' + str(join.get('to')) + '：仍有未解决设计缺口')
        if relevant and join.get('status') == 'unverified':
            unverified.append(copy.deepcopy(join))
    return {'ok': not issues, 'issues': issues, 'unverified_joins': unverified, 'limits': LIMITS}


def update_review(doc, record, root, shot_ids, evidence):
    """Return a locally amended review, preserving the first whole-sequence judgment.

    ``evidence`` supplies an actual local summary and the existing continuity table
    with affected units/joins amended. An optional explicit result changes readiness;
    the function never infers ready. This optional helper is not required after a human
    revision; nothing is persisted by this function.
    """
    if (not isinstance(evidence, dict) or not _text(evidence.get('summary'))
            or not isinstance(evidence.get('continuity_review'), dict)):
        raise ValueError('局部更新须提供实际核对依据及沿用的连续接点表')
    if 'result' in evidence and evidence['result'] not in ('ready', 'revise'):
        raise ValueError('局部核对结论须明确为 ready 或 revise')
    if not isinstance(shot_ids, (list, tuple)) or not shot_ids or any(not _text(s) for s in shot_ids) or len(shot_ids) != len(set(shot_ids)):
        raise ValueError('局部更新须指定唯一实际镜头范围')
    result = copy.deepcopy(record)
    data = result.get('data', {})
    if result.get('kind') != 'decision' or data.get('decision_type') != 'sequence_review' or data.get('review_version') != 3:
        raise ValueError('局部更新须沿用已有 v3 整段图序审查记录')
    saved = data.get('manifest', {})
    if not isinstance(saved, dict) or not isinstance(saved.get('scope'), dict):
        raise ValueError('已有审查缺少实际范围，不能直接补写指纹')
    old_order = saved.get('shot_ids', [])
    fingerprints = saved.get('fingerprints', {})
    if saved.get('fingerprint') != _binding(old_order, fingerprints, saved['scope']):
        raise ValueError('已有审查范围指纹无效，不能直接补写指纹')
    requested = set(shot_ids)
    active_ids = {s['id'] for sec in doc['sections'] if sec['id'] not in production.cancelled_sections(doc)
                  for g in sec['groups'] for s in g['shots']}
    if requested - (set(old_order) | active_ids):
        raise ValueError('局部更新包含无法识别的镜头')
    scope = copy.deepcopy(saved['scope'])
    if scope.get('shot_ids') is not None:
        # A local insertion/removal expands this existing batch, not a new review.
        scope['shot_ids'] = [sid for sid in scope['shot_ids'] if sid in active_ids]
        scope['shot_ids'] += [sid for sid in shot_ids if sid in active_ids and sid not in scope['shot_ids']]
    current = manifest(doc, root, **scope)
    order = current['shot_ids']
    if requested - (set(old_order) | set(order)):
        raise ValueError('新增镜头不在本批实际范围内')
    if [s for s in old_order if s not in requested] != [s for s in order if s not in requested]:
        raise ValueError('镜头增删或重排超出所列局部，请包含其受影响镜头；已有整段完成事实保留')
    old_continuity = data.get('continuity_review', {})
    new_continuity = copy.deepcopy(evidence['continuity_review'])
    old_units = old_continuity.get('units', [])
    new_units = new_continuity.get('units', [])
    if not isinstance(new_units, list) or any(not isinstance(u, dict) for u in new_units):
        raise ValueError('局部连续单位格式错误')
    if [u for u in old_units if u.get('shot_id') not in requested] != [u for u in new_units if u.get('shot_id') not in requested]:
        raise ValueError('局部更新不能改写未受影响的连续单位')
    old_unit_shots = {u['id']: u['shot_id'] for u in old_units}
    old_joins = {(j['from'], j['to']): j for j in old_continuity.get('joins', [])}
    new_joins = {(j.get('from'), j.get('to')): j for j in new_continuity.get('joins', []) if isinstance(j, dict)}
    for pair, join in old_joins.items():
        a, b = old_unit_shots.get(pair[0]), old_unit_shots.get(pair[1])
        crosses_local = (a in order and b in order and any(
            sid in requested for sid in order[min(order.index(a), order.index(b)) + 1:max(order.index(a), order.index(b))]))
        if a not in requested and b not in requested and not crosses_local:
            if new_joins.get(pair) != join:
                raise ValueError('局部更新不能改写未受影响的接点依据')
    updated = copy.deepcopy(fingerprints)
    for sid in requested:
        if sid in current['fingerprints']['shots']:
            updated['shots'][sid] = current['fingerprints']['shots'][sid]
        else:
            updated['shots'].pop(sid, None)
    checked = requested & set(order)
    for pair in current['adjacent_pairs']:
        key = _key(pair['from'], pair['to'])
        if pair['from'] in requested or pair['to'] in requested or key not in updated['joins']:
            updated['joins'][key] = pair['fingerprint']
            checked.update((pair['from'], pair['to']))
    updated['joins'] = {key: value for key, value in updated['joins'].items() if key in current['fingerprints']['joins']}
    updated_manifest = copy.deepcopy(current)
    updated_manifest['fingerprints'] = updated
    updated_manifest['fingerprint'] = _binding(order, updated, scope)
    # Store only the binding contract, not a second media inventory.
    data['manifest'] = {key: updated_manifest[key] for key in ('scope', 'shot_ids', 'fingerprint', 'fingerprints')}
    data['continuity_review'] = new_continuity
    previous_result = data.get('result')
    if 'result' in evidence:
        data['result'] = evidence['result']
    result['shot_ids'] = order
    # Validate the supplied local design even when readiness intentionally stays revise.
    structural = copy.deepcopy(result)
    structural['data']['result'] = 'ready'
    check = validate_review(doc, structural, root, shot_ids=[sid for sid in order if sid in checked])
    if not check['ok']:
        raise ValueError('局部核对尚有缺口：' + '；'.join(check['issues']))
    data.setdefault('local_updates', []).append({
        'shot_ids': [sid for sid in old_order if sid in requested and sid not in order] + [sid for sid in order if sid in checked],
        'summary': evidence['summary'], 'before_fingerprint': saved['fingerprint'],
        'after_fingerprint': data['manifest']['fingerprint'],
        'previous_result': previous_result, 'result': data.get('result')})
    return result
