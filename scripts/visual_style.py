"""Visual direction shared by the workbench, CLI and production readiness."""
import copy


def initial():
    return {'contract_version': 1, 'status': 'pending', 'brief': ''}


def validate(workspace):
    choice = workspace.get('style_choice')
    if choice is not None:
        if not isinstance(choice, dict) or not isinstance(choice.get('brief'), str):
            raise ValueError('视觉定调选择格式错误')
        if choice.get('contract_version') == 1:
            if choice.get('status') not in ('pending', 'selected', 'skipped'):
                raise ValueError('未知视觉定调状态')
            if choice['status'] != 'pending' and not choice.get('selection_evidence', '').strip():
                raise ValueError('视觉定调须保留实际选择或跳过依据')
    recommendations = workspace.get('style_recommendations')
    if recommendations is not None and not isinstance(recommendations, dict):
        raise ValueError('视觉定调推荐格式错误')


def view(doc):
    workspace = doc.get('workspace', {})
    choice = workspace.get('style_choice')
    records = doc.get('production', {}).get('records', [])
    retired = {rid for record in records for rid in record.get('data', {}).get('supersedes', [])}
    styles = [r for r in records if r.get('kind') == 'style' and r['id'] not in retired
              and r.get('data', {}).get('status') not in ('excluded', 'revise')]
    result = {'status': 'pending', 'ready': False, 'choice': copy.deepcopy(choice),
              'record_id': None, 'brief': '',
              'recommendations': copy.deepcopy(workspace.get('style_recommendations', {})),
              'message': '先在视觉定调中看图比较并保存方向；已有参考或明确跳过也在这里记录。'}
    if choice and choice.get('status') == 'skipped' and choice.get('selection_evidence'):
        result.update(status='skipped', ready=True, brief=choice['brief'],
                      message='已按明确决定跳过视觉定调，沿本次约定继续。')
        return result
    if choice and choice.get('status') == 'selected':
        record = next((r for r in styles if r['id'] == choice.get('record_id')
                       and r['data'].get('style_choice_id') == choice.get('id')), None)
        if record and choice.get('selection_evidence') and record['data'].get('adoption_evidence'):
            result.update(status='selected', ready=True, record_id=record['id'], brief=record['body'],
                          message='视觉定调已保存，后续制作使用这份风格约定。')
        else:
            result.update(status='needs_sync', brief=choice['brief'],
                          message='视觉方向已选择，尚未同步到制作约定；沿已有选择补同步，无需重选。')
        return result
    # Existing projects keep their adopted direction without a retrospective gate.
    if not choice or choice.get('contract_version') != 1:
        adopted = [r for r in styles if r['data'].get('status') == 'adopted'
                   and r['data'].get('adoption_evidence')]
        if adopted:
            record = adopted[-1]
            direction = record['data'].get('visual_direction', {})
            ids = direction.get('style_ids', [])
            projection = {'brief': record['body'], 'project_notes': '',
                          'base_id': ids[0] if ids else None, 'world_id': None, 'tones': [],
                          'record_id': record['id'], 'source': 'existing'}
            result.update(status='inherited', ready=True, choice=projection,
                          record_id=record['id'], brief=record['body'],
                          message='沿用已有采用风格；这里显示当前制作约定，不要求重新选择。')
    return result


def recommendation(command, atlas):
    items = command.get('items')
    ids = {card['id'] for card in atlas['cards']}
    if not isinstance(items, list) or not 1 <= len(items) <= 5:
        raise ValueError('按本次内容提供1–5个视觉推荐；方向未定时通常比较3–5个')
    if any(not isinstance(item, dict) or item.get('id') not in ids
           or not isinstance(item.get('reason'), str) or not item['reason'].strip() for item in items):
        raise ValueError('视觉推荐须使用实际图鉴条目并说明适合本片的理由')
    if len({item['id'] for item in items}) != len(items):
        raise ValueError('视觉推荐不能重复')
    brief = command.get('brief', '')
    if not isinstance(brief, str):
        raise ValueError('视觉推荐说明须为文字')
    return {'items': copy.deepcopy(items), 'brief': brief}


def enforce_transition(old, doc):
    """Guard new production writes, not old data, review history or authorisation."""
    choice = doc.get('workspace', {}).get('style_choice', {})
    if choice.get('contract_version') != 1 or view(doc)['ready']:
        return
    previous = {r['id']: r for r in (old or {}).get('production', {}).get('records', [])}
    for record in doc.get('production', {}).get('records', []):
        before = previous.get(record['id'])
        data = record.get('data', {})
        if data.get('status') == 'excluded':
            continue
        entry = data.get('decision_type') in ('image_stage_entry', 'video_preparation_entry')
        entry = entry or (data.get('decision_type') == 'production_path' and not data.get('planning_only'))
        starts = entry and (before is None or set(record.get('shot_ids', [])) - set(before.get('shot_ids', [])))
        media = record.get('kind') in ('asset', 'grid', 'previs', 'package')
        changes_media = media and (before is None or record.get('files') != before.get('files')
                                   or (record['kind'] == 'package' and record.get('data') != before.get('data')))
        if starts or changes_media:
            raise ValueError('先完成工作台视觉定调并同步制作约定，再开始本次绘图或视频准备；已有参考或明确跳过可直接记录。')

