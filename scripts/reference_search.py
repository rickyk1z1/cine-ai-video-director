"""Bounded reference-search bookkeeping. No crawler, network calls or media downloads."""
import copy
from datetime import datetime, timezone
import ipaddress
import json
import math
from pathlib import Path
import time
from urllib.parse import urlsplit, urlunsplit
import uuid

LIMIT_SECONDS = 240
MAX_MATCHES = 3
SOURCES = json.loads((Path(__file__).resolve().parent.parent / 'assets' / 'reference-sources.json').read_text())
LIMITS = ('计时限制新的检索意图，不会中断外部工具，也不能核实其实际启动时间。'
          '显式收尾可记录已取得或正在处理的结果；观察时间未知不证明预算内完成。'
          'viewed 是助手实际观看后的记录，程序不能代替观看或判断相似性。')


def _text(value, name):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(name + '不能为空')
    return value.strip()


def _clock(value=None):
    if value is None:
        return time.time()
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value.replace('Z', '+00:00'))
        except ValueError as exc:
            raise ValueError('时间须为 Unix 秒或带时区的 ISO 时间') from exc
    if isinstance(value, datetime):
        if value.tzinfo is None:
            raise ValueError('时间须包含时区')
        value = value.timestamp()
    if type(value) not in (int, float) or not math.isfinite(value):
        raise ValueError('时间须为有限 Unix 秒或带时区的 ISO 时间')
    return float(value)


def _stamp(value):
    return datetime.fromtimestamp(value, timezone.utc).isoformat().replace('+00:00', 'Z')


def _copy(sessions):
    validate(sessions)
    return copy.deepcopy(sessions)


def _url(value, name):
    value = _text(value, name)
    if any(c.isspace() or ord(c) < 32 for c in value) or '\\' in value:
        raise ValueError(name + '格式错误')
    try:
        parts = urlsplit(value)
        host = (parts.hostname or '').lower().rstrip('.')
        if (parts.scheme != 'https' or not host or parts.username is not None
                or parts.password is not None or parts.port not in (None, 443)):
            raise ValueError(name + '须为无凭据的 HTTPS 地址')
    except ValueError as exc:
        raise ValueError(name + '须为无凭据的 HTTPS 地址') from exc
    if host == 'localhost' or host.endswith(('.localhost', '.local')):
        raise ValueError(name + '须为公开地址')
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        address = None
    if address is not None and not address.is_global:
        raise ValueError(name + '须为公开地址')
    return value, host, parts


def source_for_url(url):
    """Validate the original page's authority, allowing its official subdomains."""
    _, host, _ = _url(url, '来源页面')
    for source in SOURCES:
        if host == source['domain'] or host.endswith('.' + source['domain']):
            return copy.deepcopy(source)
    raise ValueError('来源页面必须属于参考来源目录；外部媒体不能代替来源页面')


def _valid(session):
    return [c for c in session.get('candidates', [])
            if c.get('matched') is True and c.get('observation') == 'viewed']


def _reference_key(item):
    parts = urlsplit(item['source_url'])
    host = parts.hostname.lower().rstrip('.').removeprefix('www.')
    return (urlunsplit((parts.scheme, host, parts.path.rstrip('/'), parts.query, '')),
            item.get('watch_range', '').strip())


def validate(sessions):
    """Validate persisted structure and provenance; no semantic or viewing verdict."""
    if not isinstance(sessions, list) or any(not isinstance(s, dict) for s in sessions):
        raise ValueError('reference_sessions 必须是轮次列表')
    seen, last_requested = set(), None
    for index, session in enumerate(sessions):
        sid = _text(session.get('id'), '参考轮次 ID')
        if sid in seen:
            raise ValueError('参考轮次 ID 重复')
        seen.add(sid)
        _text(session.get('query'), '参考需求')
        if session.get('scope') is not None and not isinstance(session['scope'], (str, dict)):
            raise ValueError('参考范围格式错误')
        status = session.get('status')
        if status not in ('request', 'searching', 'ready', 'exhausted'):
            raise ValueError('参考状态格式错误')
        if index < len(sessions) - 1 and status in ('request', 'searching'):
            raise ValueError('历史参考轮次须已结束')
        for key in ('requested_at', 'started_at', 'stopped_at', 'candidates', 'restrictions',
                    'chosen_candidate_id', 'adoption_note', 'feedback', 'stop_reason'):
            if key not in session:
                raise ValueError('参考轮次缺少 ' + key)
        requested = _clock(_text(session['requested_at'], '请求时间'))
        started = _clock(session['started_at']) if session['started_at'] is not None else None
        stopped = _clock(session['stopped_at']) if session['stopped_at'] is not None else None
        if last_requested is not None and requested < last_requested:
            raise ValueError('参考轮次请求时间顺序错误')
        last_requested = requested
        if started is not None and started < requested or stopped is not None and stopped < (started if started is not None else requested):
            raise ValueError('参考轮次时间顺序错误')
        if status == 'request' and (started is not None or stopped is not None):
            raise ValueError('待检索轮次不能已有开始或结束时间')
        if status == 'searching' and (started is None or stopped is not None):
            raise ValueError('检索中轮次须有开始时间且尚未结束')
        if status in ('ready', 'exhausted') and stopped is None:
            raise ValueError('结束轮次缺少停止时间')
        if not isinstance(session['candidates'], list) or not isinstance(session['restrictions'], list):
            raise ValueError('参考候选和限制必须是列表')
        if session['stop_reason'] is not None and not isinstance(session['stop_reason'], str):
            raise ValueError('停止原因须为文字或空值')
        candidates, page_ranges = {}, set()
        for item in session['candidates']:
            if not isinstance(item, dict):
                raise ValueError('参考候选必须是对象')
            cid = _text(item.get('id'), '候选 ID')
            if cid in candidates:
                raise ValueError('参考候选 ID 重复')
            candidates[cid] = item
            for key in ('title', 'source_url', 'match_reason', 'difference', 'reuse_note'):
                _text(item.get(key), key)
            source = source_for_url(item['source_url'])
            if item.get('source_id') != source['id']:
                raise ValueError('参考来源 ID 与页面不一致')
            if item.get('observation') not in ('viewed', 'unverified') or type(item.get('matched')) is not bool:
                raise ValueError('参考观察状态或匹配标记格式错误')
            for key in ('watch_range', 'observation_note'):
                if key in item:
                    _text(item[key], key)
            page_range = _reference_key(item)
            if page_range in page_ranges:
                raise ValueError('同轮来源片段重复')
            page_ranges.add(page_range)
            if item.get('preview_url'):
                _url(item['preview_url'], '预览媒体')
                if item.get('preview_kind') not in ('image', 'gif', 'video'):
                    raise ValueError('参考预览类型错误')
            elif item.get('preview_kind') != 'none':
                raise ValueError('参考预览类型与地址不一致')
            recorded = _clock(_text(item.get('recorded_at'), '记录时间'))
            if 'observed_at' not in item or type(item.get('late_completion', False)) is not bool:
                raise ValueError('观察时间与收尾标记格式错误')
            observed = _clock(_text(item['observed_at'], '观察时间')) if item['observed_at'] is not None else None
            if started is None or recorded < started:
                raise ValueError('参考记录须在本轮检索开始之后')
            if observed is None:
                if item.get('late_completion') is not True:
                    raise ValueError('观察时间未知只能作为显式收尾记录')
            elif not started <= observed <= started + LIMIT_SECONDS or recorded < observed:
                raise ValueError('已知观察时间须在本轮预算内，且记录不得早于观察')
            elif stopped is not None and observed > stopped:
                raise ValueError('参考观察时间晚于本轮停止')
            if 'viewed_at' in item and _clock(item['viewed_at']) < (observed if observed is not None else started):
                raise ValueError('实际观看时间早于线索发现')
        if len(_valid(session)) > MAX_MATCHES:
            raise ValueError('同轮最多三个已观看且匹配的案例')
        for row in session['restrictions']:
            if not isinstance(row, dict) or row.get('source_id') not in [s['id'] for s in SOURCES]:
                raise ValueError('访问限制必须属于参考来源目录')
            for key in ('capability', 'reason', 'value'):
                _text(row.get(key), key)
        for key in ('adoption_note', 'feedback'):
            if not isinstance(session[key], str):
                raise ValueError(key + '须为文字')
        chosen = session['chosen_candidate_id']
        if chosen is not None:
            if not isinstance(chosen, str) or chosen not in candidates or not candidates[chosen]['matched']:
                raise ValueError('采用参考须属于本轮匹配候选')
            _text(session['adoption_note'], '采用特征')
            if session.get('selection_by') not in ('user', 'assistant'):
                raise ValueError('采用参考缺少选择者依据')
            if session['selection_by'] == 'assistant' and candidates[chosen]['observation'] != 'viewed':
                raise ValueError('助手选择须有实际观看记录')
        if status == 'ready' and chosen is None and len(_valid(session)) < MAX_MATCHES:
            raise ValueError('ready 轮次须有三个有效案例或明确选择')


def _settle(session, now):
    if session['status'] != 'searching':
        return
    started = _clock(session['started_at'])
    if now < started:
        raise ValueError('当前时间早于检索开始时间')
    if len(_valid(session)) >= MAX_MATCHES:
        session.update(status='ready', stop_reason='three_matches', stopped_at=_stamp(now))
    elif now >= started + LIMIT_SECONDS:
        session.update(status='exhausted', stop_reason='time_budget',
                       stopped_at=_stamp(started + LIMIT_SECONDS))


def _new(query, scope, now):
    if scope is not None and not isinstance(scope, (dict, str)):
        raise ValueError('参考范围须为对象、文字或空值')
    return {'id': 'refs-' + uuid.uuid4().hex[:12], 'query': _text(query, '参考需求'),
            'scope': copy.deepcopy(scope), 'status': 'request',
            'requested_at': _stamp(now), 'started_at': None, 'stopped_at': None,
            'stop_reason': None, 'candidates': [], 'restrictions': [],
            'chosen_candidate_id': None, 'adoption_note': '', 'feedback': ''}


def request(sessions, query, scope=None, now=None):
    """Queue a distinct need; repeated requests never silently restart a round."""
    result, clock = _copy(sessions), _clock(now)
    query = _text(query, '参考需求')
    if result:
        current = result[-1]
        _settle(current, clock)
        if current['query'] == query and current.get('scope') == scope:
            return result
        if current['status'] in ('request', 'searching'):
            raise ValueError('已有待处理参考轮次；先结束，或用明确反馈 reject 换一组')
    result.append(_new(query, scope, clock))
    validate(result)
    return result


def _candidate(data, now, late_completion=False):
    if not isinstance(data, dict):
        raise ValueError('candidate 必须是对象')
    item = {key: _text(data.get(key), key) for key in
            ('title', 'source_url', 'match_reason', 'difference', 'reuse_note')}
    item['source_id'] = source_for_url(item['source_url'])['id']
    if data.get('observation') not in ('viewed', 'unverified'):
        raise ValueError('observation 须为 viewed 或 unverified')
    item['observation'] = data['observation']
    matched = data.get('matched', True)
    if type(matched) is not bool:
        raise ValueError('matched 必须是布尔值')
    item['matched'] = matched
    item['id'] = 'ref-' + uuid.uuid4().hex[:12]
    for key in ('watch_range', 'observation_note'):
        if data.get(key) is not None:
            item[key] = _text(data[key], key)
    if data.get('preview_url'):
        item['preview_url'] = _url(data['preview_url'], '预览媒体')[0]
        if data.get('preview_kind') not in ('image', 'gif', 'video'):
            raise ValueError('有预览媒体时 preview_kind 须为 image、gif 或 video')
        item['preview_kind'] = data['preview_kind']
    else:
        if data.get('preview_kind') not in (None, '', 'none'):
            raise ValueError('preview_kind 需要相应预览地址')
        item['preview_kind'] = 'none'
    raw_observed = data.get('observed_at')
    observed = _clock(raw_observed) if raw_observed is not None else (None if late_completion else now)
    if observed is not None and observed > now:
        raise ValueError('观察时间不能在未来')
    item.update(observed_at=_stamp(observed) if observed is not None else None, recorded_at=_stamp(now))
    if late_completion:
        item['late_completion'] = True
    return item


def apply(sessions, command, now=None):
    """Apply one action to the latest round, returning a copy or raising ValueError."""
    if not isinstance(command, dict):
        raise ValueError('参考命令必须是对象')
    action, clock = command.get('action'), _clock(now)
    if action == 'request':
        return request(sessions, command.get('query'), command.get('scope'), clock)
    result = _copy(sessions)
    if not result:
        raise ValueError('请先请求参考轮次')
    current = result[-1]
    if command.get('session_id', current['id']) != current['id']:
        raise ValueError('参考轮次已变化，请读取当前轮次')
    _settle(current, clock)
    if action == 'begin':
        if current['status'] == 'searching':
            return result  # Repeated begin cannot reset the timer.
        if current['status'] != 'request':
            raise ValueError('本轮已结束；只有明确反馈换一组才重新开始')
        if clock < _clock(current['requested_at']):
            raise ValueError('开始时间早于请求时间')
        current.update(status='searching', started_at=_stamp(clock))
    elif action == 'add_candidate':
        existing = command.get('record_existing') is True
        if current['status'] != 'searching' and not (
                existing and current['status'] == 'exhausted' and current.get('started_at')):
            raise ValueError('本轮不能新增检索候选；超时后只可显式收尾记录已取得或正在处理的结果')
        data = command.get('candidate')
        item = _candidate(data, clock, late_completion=existing and current['status'] != 'searching')
        started = _clock(current['started_at'])
        observed = _clock(item['observed_at']) if item['observed_at'] is not None else None
        cutoff = min(started + LIMIT_SECONDS, _clock(current['stopped_at'])) if current['stopped_at'] else started + LIMIT_SECONDS
        if observed is not None and not started <= observed <= cutoff:
            raise ValueError('已知观察时间须在本轮检索开始至截止之间')
        for old in current['candidates']:
            if _reference_key(item) == _reference_key(old):
                raise ValueError('同一来源片段已记录；同页不同示例须明确 watch_range，线索可用 observe 补看')
        current['candidates'].append(item)
        if len(_valid(current)) >= MAX_MATCHES:
            current.update(status='ready', stop_reason='three_matches', stopped_at=current['stopped_at'] or _stamp(clock))
    elif action == 'observe':
        # Mark an already discovered lead as viewed; never create another search result.
        item = next((c for c in current['candidates'] if c['id'] == command.get('candidate_id')), None)
        if item is None:
            raise ValueError('找不到本轮参考')
        if item['observation'] == 'viewed':
            return result
        if len(_valid(current)) >= MAX_MATCHES:
            raise ValueError('已有三个贴近且已观看的参考，本轮停止')
        item['observation_note'] = _text(command.get('observation_note'), '实际观看说明')
        item['observation'] = 'viewed'
        item['viewed_at'] = _stamp(clock)
        if 'matched' in command:
            if type(command['matched']) is not bool:
                raise ValueError('matched 必须是布尔值')
            item['matched'] = command['matched']
        if len(_valid(current)) >= MAX_MATCHES:
            current.update(status='ready', stop_reason='three_matches', stopped_at=current['stopped_at'] or _stamp(clock))
    elif action == 'record_restriction':
        platform = command.get('source_id')
        if platform not in [s['id'] for s in SOURCES]:
            raise ValueError('限制平台须来自参考来源目录')
        row = {'source_id': platform, 'capability': _text(command.get('capability'), '受限能力'),
               'value': _text(command.get('value'), '可考虑价值'),
               'reason': _text(command.get('reason'), '限制原因')}
        if row not in current['restrictions']:
            current['restrictions'].append(row)
    elif action == 'stop':
        if current['status'] in ('request', 'searching'):
            current.update(status='ready' if len(_valid(current)) >= MAX_MATCHES else 'exhausted',
                           stop_reason=_text(command.get('reason', 'stopped'), '停止原因'), stopped_at=_stamp(clock))
    elif action == 'choose':
        selection_by = command.get('selection_by', 'user')
        if selection_by not in ('user', 'assistant'):
            raise ValueError('selection_by 须为 user 或 assistant')
        item = next((c for c in current['candidates'] if c['id'] == command.get('candidate_id')
                     and c['matched'] and (selection_by == 'user' or c['observation'] == 'viewed')), None)
        if item is None:
            raise ValueError('只能选择本轮匹配的参考；助手选择还须有实际观看记录')
        current.update(chosen_candidate_id=item['id'], adoption_note=_text(command.get('adoption_note'), '采用特征'),
                       selection_by=selection_by, status='ready', stop_reason='chosen',
                       stopped_at=current['stopped_at'] or _stamp(clock))
    elif action == 'reject':
        feedback = _text(command.get('feedback'), '换一组的明确反馈')
        current.update(feedback=feedback, stopped_at=current['stopped_at'] or _stamp(clock))
        if current['status'] in ('request', 'searching'):
            current.update(status='exhausted', stop_reason='rejected')
        fresh = _new(command.get('query', current['query']), command.get('scope', current.get('scope')), clock)
        fresh.update(previous_session_id=current['id'], request_feedback=feedback)
        result.append(fresh)
    else:
        raise ValueError('未知参考操作：' + str(action))
    validate(result)
    return result


def view(sessions, now=None):
    """Derived display state; elapsed time does not mutate stored sessions."""
    result, clock = _copy(sessions), _clock(now)
    current = result[-1] if result else None
    elapsed, remaining = 0, LIMIT_SECONDS
    if current:
        _settle(current, clock)
        if current.get('started_at'):
            end = _clock(current['stopped_at']) if current.get('stopped_at') else clock
            elapsed = max(0, end - _clock(current['started_at']))
            remaining = max(0, LIMIT_SECONDS - elapsed)
    return {'sessions': result, 'current': current, 'sources': copy.deepcopy(SOURCES),
            'limit_seconds': LIMIT_SECONDS, 'max_matches': MAX_MATCHES,
            'elapsed_seconds': elapsed, 'remaining_seconds': remaining,
            'valid_count': len(_valid(current)) if current else 0,
            'can_search': bool(current and current['status'] == 'searching'),
            'needs_search': bool(current and current['status'] == 'request'), 'limits': LIMITS}
