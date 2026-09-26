#!/usr/bin/env python3
"""Check exact handoff text and declared contracts, not semantic truth or video quality."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import re
import subprocess
import sys

POLICY = '参考图仅提供指定属性，不按图片顺序演变，不强制复现整幅构图。'
# These are attachment syntaxes, not natural-language rules for judging a prompt.
# Quoted attributes may contain >; consume the entire tag before checking its ID.
NODE_TAG = re.compile(r"<(?P<tag>node-asset|pippit-asset-id)(?:\s+[\w:-]+\s*=\s*(?:\"[^\"]*\"|'[^']*'))*\s*>([^<>]+)</(?P=tag)\s*>")
NODE_START = re.compile(r'</?(?:node-asset|pippit-asset-id)\b', re.I)
ASSET_TAG = re.compile(r'<(?:node-asset|pippit-asset-id)\b|<Picture\s+\d+>|@(?:图片|图像|视频|音频|图|Image|Video|Audio)\s*\d+', re.I)
LIMITS = ('仅核验声明结构、正文原句及位置、参考职责和镜头覆盖；不能证明要求完整、'
          '语义等价、来源真实、参考必要或模型服从。声音与动态效果须检查实际结果。')


def _text(value):
    return isinstance(value, str) and bool(value.strip())


def _number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _opening(prompt):
    """First non-heading paragraph, ending before the first real attachment tag."""
    offset = 0
    started = False
    start = end = len(prompt)
    for line in prompt.splitlines(keepends=True):
        stripped = line.strip()
        if not started:
            if not stripped or re.match(r'^#{1,6}\s', stripped):
                offset += len(line)
                continue
            start = offset
            started = True
        elif not stripped or re.match(r'^#{1,6}\s', stripped):
            end = offset
            break
        offset += len(line)
    tag = ASSET_TAG.search(prompt)
    if tag:
        end = min(end, tag.start())
    return prompt[start:end]


def _audio_errors(ref, errors):
    rid = ref.get('id')
    contract = ref.get('audio_contract')
    if not isinstance(contract, dict):
        errors.append('音频参考缺少audio_contract：' + str(rid))
        return
    if not all(_text(contract.get(k)) for k in ('platform', 'model', 'mode', 'evidence', 'checked_at', 'file', 'usage')):
        errors.append('音频参考缺少入口、规格依据、本地文件或使用职责')
    limits = contract.get('duration_limits')
    limits = limits if isinstance(limits, dict) else {}
    low, high = limits.get('min_seconds'), limits.get('max_seconds')
    if not _number(low) or low < 0:
        errors.append('音频参考缺少有依据的时长下限（无下限需明确0）')
    if high is not None and (not _number(high) or high < 0):
        errors.append('音频参考时长上限无效')
    if _number(low) and _number(high) and high < low:
        errors.append('音频参考时长上下限矛盾')
    try:
        result = subprocess.run(
            ['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'json', str(contract.get('file', ''))],
            capture_output=True, text=True, check=True, timeout=15)
        duration = float(json.loads(result.stdout)['format']['duration'])
        if not math.isfinite(duration) or duration <= 0:
            raise ValueError('无有效时长')
        if _number(low) and duration < low:
            errors.append('音频参考低于当前入口时长下限：' + str(rid))
        if _number(high) and duration > high:
            errors.append('音频参考超过当前入口时长上限：' + str(rid))
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError):
        errors.append('音频参考文件无法实测时长：' + str(rid))


def _reference_errors(bundle, prompt, errors, v3):
    refs = bundle.get('reference_policy', [])
    if not isinstance(refs, list):
        refs = []
        errors.append('reference_policy须为列表')
    valid_refs = []
    ids = []
    for ref in refs:
        if not isinstance(ref, dict):
            errors.append('无效素材职责项')
            continue
        valid_refs.append(ref)
        rid = ref.get('id')
        if _text(rid):
            ids.append(rid)
        if ref.get('type') not in ('image', 'audio', 'video', 'other'):
            errors.append('每份参考须声明真实媒体type')
        if ref.get('type') == 'audio':
            _audio_errors(ref, errors)
        if not _text(rid) or not _text(ref.get('use')):
            errors.append('每个素材须声明非空id/use')
        if ref.get('mode') not in ('reference', 'strict_boundary'):
            errors.append('素材mode须为reference或strict_boundary')
        if ref.get('type') == 'image' and ref.get('mode') == 'reference' and not _text(ref.get('not_required')):
            errors.append('普通图片参考须声明not_required')
        if ref.get('mode') == 'strict_boundary' and not all(_text(ref.get(k)) for k in ('scope', 'evidence')):
            errors.append('严格边界须有范围和用户/真实入口依据')
    matches = list(NODE_TAG.finditer(prompt))
    tags = {match.group(2).strip() for match in matches}
    remaining = NODE_TAG.sub('', prompt)
    if NODE_START.search(remaining):
        errors.append('素材节点标签格式无法识别或未闭合，须核对实际平台语法')
    if any(not match.group(2).strip() for match in matches):
        errors.append('素材节点标签ID不能为空')
    if tags - set(ids):
        errors.append('正文中的实际节点标签未逐项分配参考职责')
    if len(ids) != len(set(ids)):
        errors.append('参考职责ID重复')
    contract = bundle.get('delivery_contract', {})
    if not isinstance(contract, dict):
        contract = {}
        errors.append('delivery_contract须为对象')
    boundary = contract.get('reference_boundary', POLICY)
    ordinary = any(r.get('type') == 'image' and r.get('mode') == 'reference' for r in valid_refs)
    if ordinary:
        if not _text(boundary) or boundary not in prompt:
            errors.append('正文缺少本次声明的简短参考边界')
        elif v3 and boundary not in _opening(prompt):
            errors.append('普通参考总边界须在开头文本块且在首个素材标签之前')
    return valid_refs


def _requirement_errors(bundle, prompt, errors):
    requirements = bundle.get('requirements')
    if not isinstance(requirements, list):
        errors.append('requirements须为列表；仅列本批真正已定约束，无额外条目可为空')
        return
    opening = _opening(prompt)
    for index, item in enumerate(requirements, 1):
        if not isinstance(item, dict) or not all(_text(item.get(k)) for k in ('requirement', 'source', 'clause')):
            errors.append('已定约束须有requirement/source/准确正文clause：' + str(index))
            continue
        clause = item['clause']
        if clause not in prompt:
            errors.append('正文缺少已定约束原句：' + item['requirement'])
        placement = item.get('placement')
        if placement is not None and placement != 'opening':
            errors.append('约束placement仅支持opening或省略：' + item['requirement'])
        elif placement == 'opening' and clause not in opening:
            errors.append('已定约束未放在开头文本块/首个素材标签之前：' + item['requirement'])


def _continuity_errors(bundle, errors, v3, expected_shot_ids):
    continuity = bundle.get('continuity_review', {})
    if not isinstance(continuity, dict):
        continuity = {}
    units, joins = continuity.get('units'), continuity.get('joins')
    unit_ids, shot_ids = [], []
    if not isinstance(units, list) or not units:
        errors.append('缺少唯一有序镜头/连续阶段列表')
    else:
        for unit in units:
            if v3:
                if not isinstance(unit, dict) or not all(_text(unit.get(k)) for k in ('id', 'shot_id')):
                    errors.append('v3连续单位须有id与实际shot_id')
                    continue
                unit_ids.append(unit['id'])
                shot_ids.append(unit['shot_id'])
            elif _text(unit):
                unit_ids.append(unit)
                mapping = continuity.get('unit_shots', {})
                shot_ids.append(mapping.get(unit, unit) if isinstance(mapping, dict) else unit)
            else:
                errors.append('旧版连续单位须为非空ID')
        if len(unit_ids) != len(set(unit_ids)):
            errors.append('连续单位ID重复')
    if expected_shot_ids is not None:
        if (not isinstance(expected_shot_ids, (list, tuple)) or not expected_shot_ids
                or any(not _text(s) for s in expected_shot_ids)
                or len(expected_shot_ids) != len(set(expected_shot_ids))):
            errors.append('实际包expected_shot_ids须为唯一有序镜头ID列表')
        else:
            collapsed = [sid for i, sid in enumerate(shot_ids) if i == 0 or sid != shot_ids[i - 1]]
            if collapsed != list(expected_shot_ids):
                errors.append('连续单位shot_id未依序精确覆盖实际包镜头')
    if not isinstance(joins, list):
        joins = []
        errors.append('joins须为列表')
    pairs, unverified = [], []
    for join in joins:
        if not isinstance(join, dict):
            errors.append('无效接点记录')
            continue
        pair = (join.get('from'), join.get('to'))
        pairs.append(pair)
        for field in ('type', 'audience_bridge', 'evidence', 'budget_check'):
            if not _text(join.get(field)):
                errors.append('接点缺少' + field)
        status = join.get('status')
        if status == 'design_gap':
            errors.append('接点仍有未解决设计缺口：' + str(pair))
        elif status == 'unverified':
            unverified.append({'from': pair[0], 'to': pair[1], 'reason': join.get('budget_check')})
        elif status != 'resolved':
            errors.append('接点状态须为resolved/unverified/design_gap')
    if pairs != list(zip(unit_ids, unit_ids[1:])):
        errors.append('接点表未依序覆盖全部相邻镜头/关键阶段')
    return unverified


def _legacy_review_errors(bundle, digest, refs, errors):
    # Preserve the historical reader; v3 does not synthesize or require these self-reviews.
    ids = [r.get('id') for r in refs if _text(r.get('id'))]
    scope=bundle.get('model_scope_review',{})
    if not isinstance(scope,dict):scope={}
    if scope.get('status')!='clear' or not scope.get('evidence'):
     errors.append('缺少模型职责审查：核对本次任务所需信息、已提供的背景及镜头衔接')
    for field in ('generation_scope','instruction_relevance','context_completeness'):
     if not isinstance(scope.get(field),str) or not scope[field].strip():
      errors.append('缺少本次生成范围与信息相关性审查：'+field)
    review=bundle.get('semantic_review',{})
    if not isinstance(review,dict):review={}
    if review.get('prompt_sha256')!=digest:errors.append('语义复核没有绑定当前正文哈希，修改后须重审')
    for field in ['event_vs_frame','reference_scope_consistency','motion_conflicts']:
     if not isinstance(review.get(field),str) or not review[field].strip():errors.append('缺少语义复核结论：'+field)
    positive=bundle.get('positive_review',{})
    if not isinstance(positive,dict):positive={}
    counter=positive.get('counterfactual',{})
    if not isinstance(counter,dict):counter={}
    if counter.get('status')!='clear' or not isinstance(counter.get('evidence'),str) or not counter['evidence'].strip():errors.append('正向正文反事实审查缺失或仍有冲突')
    pr=positive.get('references',[]) if isinstance(positive,dict) else []
    if not isinstance(pr,list):pr=[]
    reviewed=[];modes={r.get('id'):r.get('mode') for r in refs if _text(r.get('id'))}
    for r in pr:
     if not isinstance(r,dict):errors.append('无效正向参考审查');continue
     rid=r.get('id')
     if not _text(rid):errors.append('无效正向参考ID');continue
     reviewed.append(rid)
     if any(not isinstance(r.get(k),str) or not r[k].strip() for k in ['necessity','positive_role']):errors.append('缺少参考必要性或正向职责')
     if type(r.get('implied_endpoint')) is not bool:errors.append('须明确是否存在隐性画面落点')
     elif r['implied_endpoint'] and (modes.get(rid)!='strict_boundary' or not r.get('exception_evidence')):errors.append('普通参考被用作隐性画面落点')
    if set(reviewed)!=set(ids) or len(reviewed)!=len(set(reviewed)):errors.append('正向审查未唯一覆盖全部参考')
    events=positive.get('events') if isinstance(positive,dict) else None
    if not isinstance(events,list):errors.append('缺少事件触发审查列表');events=[]
    for e in events:
     if not isinstance(e,dict) or any(not isinstance(e.get(k),str) or not e[k].strip() for k in ['event','observable_trigger','before_trigger']):errors.append('事件缺少可观察触发依据或触发前状态')
     elif e.get('kind','completion')=='completion' and e.get('timing_basis') not in ('event','event_with_budget'):errors.append('完成反馈不能只由时钟触发')
     elif e.get('kind','completion') not in ('completion','timed','music','edit'):errors.append('未知事件触发类型')
     elif e.get('kind') in ('timed','music','edit') and (e.get('timing_basis') not in ('clock','beat','edit','event','event_with_budget') or not e.get('timing_evidence')):errors.append('定时、音乐或编辑触发缺少实际时基依据')
    if not isinstance(positive.get('control_budget'),str) or not positive['control_budget'].strip():errors.append('缺少有效控制与删减依据')


def inspect(bundle, expected_shot_ids=None):
    errors, signals = [], []
    if not isinstance(bundle, dict):
        bundle = {}
        errors.append('出稿记录须为对象')
    prompt = bundle.get('prompt', '')
    prompt = prompt if isinstance(prompt, str) else ''
    digest = hashlib.sha256(prompt.encode()).hexdigest()
    if not prompt.strip():
        errors.append('缺少实际投喂正文')
    version = bundle.get('review_version')
    v3 = type(version) is int and version == 3
    legacy = version is None or type(version) is int and version in (1, 2)
    if not v3 and not legacy:
        errors.append('不支持的review_version')
    refs = _reference_errors(bundle, prompt, errors, v3)
    if v3:
        _requirement_errors(bundle, prompt, errors)
        if expected_shot_ids is None:
            signals.append({'code': 'shot_coverage_unverified', 'text': '未提供实际包镜头，不能核验镜头覆盖'})
    elif legacy:
        _legacy_review_errors(bundle, digest, refs, errors)
        signals.append({'code': 'legacy_review', 'text': '旧版复核可读；未验证v3前置位置，新修订采用v3；真实镜头覆盖仅在提供实际镜头时核验'})
    unverified = _continuity_errors(bundle, errors, v3, expected_shot_ids)
    return {
        'ok': not errors, 'errors': errors, 'review_version': 3 if v3 else version,
        'legacy_review': legacy, 'prompt_sha256': digest, 'reference_count': len(refs),
        'strict_boundaries': [r.get('id') for r in refs if r.get('mode') == 'strict_boundary'],
        'review_signals': signals, 'unverified_joins': unverified, 'limits': LIMITS,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--input')
    parser.add_argument('--policy-text', action='store_true')
    parser.add_argument('--shot-id', action='append', help='实际包镜头ID，按顺序重复传入')
    args = parser.parse_args()
    if args.policy_text:
        print(POLICY)
        return
    if not args.input:
        parser.error('需要--input或--policy-text')
    try:
        result = inspect(json.loads(Path(args.input).read_text()), args.shot_id)
    except (ValueError, OSError) as error:
        print(json.dumps({'ok': False, 'errors': [str(error)]}, ensure_ascii=False))
        sys.exit(1)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    sys.exit(0 if result['ok'] else 1)


if __name__ == '__main__':
    main()
