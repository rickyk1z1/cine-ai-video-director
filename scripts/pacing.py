"""Apply an evidence-backed timing edit; never infer creative pacing or permissions.

Persistence, revision conflicts and recording the plan belong to Store.transact.
This module does not modify production records, submitted inputs or platform settings.
"""
import copy
import math


TEXT_CHANGES = {'content', 'framing', 'camera', 'sound', 'start', 'end',
                'transition', 'reason', 'notes'}


def _number(value, label, *, zero=False):
    if (type(value) not in (int, float) or not math.isfinite(value)
            or value < 0 or (not zero and value == 0)):
        raise ValueError(label + '须为' + ('非负' if zero else '正') + '有限秒数')
    return value


def _text(value, label):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(label + '须为非空文字')


def _shots(doc):
    result = {}
    for section in doc['sections']:
        for group in section['groups']:
            for shot in group['shots']:
                sid = shot.get('id')
                if not isinstance(sid, str) or not sid or sid in result:
                    raise ValueError('镜头ID缺失或重复')
                result[sid] = shot
    return result


def summary(doc, shot_ids=None):
    """Report current content time, not generated duration or a quality score.

    Legacy zero durations, like None, mean no usable timing has been assigned.
    """
    shots = _shots(doc)
    if shot_ids is not None:
        if (not isinstance(shot_ids, list) or not shot_ids
                or any(not isinstance(sid, str) or sid not in shots for sid in shot_ids)
                or len(set(shot_ids)) != len(shot_ids)):
            raise ValueError('须选择非空、不重复且存在的镜头ID')
        selected = set(shot_ids)
        shots = {sid: shot for sid, shot in shots.items() if sid in selected}
    durations, unknown = [], []
    for sid, shot in shots.items():
        value = shot.get('duration')
        if value is None:
            unknown.append(sid)
            continue
        _number(value, '当前镜头时长', zero=True)
        if value == 0:
            unknown.append(sid)
        else:
            durations.append(value)
    known = math.fsum(durations)
    return {'content_duration_seconds': None if unknown else known,
            'known_duration_seconds': known, 'unknown_shot_ids': unknown,
            'shot_count': len(shots)}


def apply(doc, plan):
    """Return a new document after validating every proposed edit.

    plan = {evidence: str, source_revision?: int, shots: [
        {shot_id: str, duration: number, basis: str,
         duration_range?: [low, high], changes?: {text_field: str},
         beats?: [{description: str, start: number, end: number}]}]}

    Overlapping beats are allowed: action, speech and camera can share time.
    Their intervals are evidence, never added together to determine duration.
    """
    if not isinstance(plan, dict) or set(plan) - {'evidence', 'source_revision', 'shots'}:
        raise ValueError('时长计划只接受evidence、source_revision与shots')
    _text(plan.get('evidence'), '整段校准依据')
    if 'source_revision' in plan:
        revision = plan['source_revision']
        if type(revision) is not int or revision < 0 or revision != doc.get('revision'):
            raise ValueError('时长计划依据的修订已变化，请按当前分镜核对')
    entries = plan.get('shots')
    if not isinstance(entries, list) or not entries:
        raise ValueError('时长计划须包含实际镜头修改')
    shots, seen = _shots(doc), set()
    for entry in entries:
        if not isinstance(entry, dict) or set(entry) - {
                'shot_id', 'duration', 'basis', 'duration_range', 'changes', 'beats'}:
            raise ValueError('镜头校准项含未知字段')
        sid = entry.get('shot_id')
        if not isinstance(sid, str) or sid not in shots or sid in seen:
            raise ValueError('校准镜头不存在或重复')
        seen.add(sid)
        duration = _number(entry.get('duration'), '选定镜头时长')
        _text(entry.get('basis'), '逐镜校准理由')
        if 'duration_range' in entry:
            bounds = entry['duration_range']
            if not isinstance(bounds, list) or len(bounds) != 2:
                raise ValueError('合理时长区间须为[下限,上限]')
            low, high = (_number(v, '区间边界') for v in bounds)
            if not low <= duration <= high:
                raise ValueError('选定时长不在有依据的区间内')
        changes = entry.get('changes', {})
        if (not isinstance(changes, dict) or set(changes) - TEXT_CHANGES
                or any(not isinstance(value, str) for value in changes.values())):
            raise ValueError('changes只接受动作、摄影、声音、首尾、切点及说明文字')
        beats = entry.get('beats', [])
        if not isinstance(beats, list):
            raise ValueError('beats须为可选事件列表')
        for beat in beats:
            if not isinstance(beat, dict) or set(beat) != {'description', 'start', 'end'}:
                raise ValueError('事件须说明description及start/end秒区间')
            _text(beat['description'], '事件说明')
            start = _number(beat['start'], '事件起点', zero=True)
            end = _number(beat['end'], '事件终点')
            if not start < end <= duration:
                raise ValueError('事件区间须位于选定镜头时长内')
    updated = copy.deepcopy(doc)
    targets = _shots(updated)
    for entry in entries:
        targets[entry['shot_id']]['duration'] = entry['duration']
        targets[entry['shot_id']].update(copy.deepcopy(entry.get('changes', {})))
    return updated
