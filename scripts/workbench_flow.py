"""One derived next-action list for the UI and assistant; no queue or new authority."""
import copy
import production


def actions(doc, root, workflow, coordination, references, visual):
    pending=[]
    def add(code, text, view, **detail):
        pending.append({'code':code,'text':text,'view':view,**detail})
    if not visual['ready']:
        add('visual_style',visual['message'],'style')
    if (doc.get('workspace',{}).get('style_choice',{}).get('contract_version')==1
            and visual['ready'] and doc['sections'] and not coordination['mode_selected']):
        add('choose_work_mode','内容划分后确定工作方式；默认单会话不等于已经作出选择。','project')
    if coordination['mode']=='coordinated':
        if not coordination['controller']:
            add('coordination_controller','按已选分工登记真实总控会话，再继续分配。','project')
        if not coordination['items']:
            add('coordination_plan','根据内容与关联关系登记执行条目。','project')
        for item in coordination['items']:
            if not item.get('thread_id'):
                add('coordination_assign','为“'+item['title']+'”复用或建立获授权的执行会话，并登记真实结果。','project',item_id=item['id'])
    for directive in coordination['directives']:
        for target in directive['targets']:
            status=target['status']
            if status=='applied':continue
            if coordination['mode']=='single' and status in ('unassigned','pending'):
                code='coordination_local_apply';text='在当前会话落实所选条目的共用要求，登记当前会话及实际结果。'
            else:
                code='coordination_'+status
                text={'unassigned':'先完成会话分配，再落实共用要求。','pending':'向相关执行会话下发当前版本要求。',
                      'sent':'读取当前版本的真实落实回报；发送成功不等于已落实。',
                      'blocked':'根据已报告的缺口处理受影响条目，保留其他已完成内容。'}[status]
            add(code,text,'project',directive_id=directive['id'],item_id=target['item_id'],version=directive['version'])
    current=references.get('current')
    if current and current['status'] in ('request','searching'):
        scope=production.reference_scope(doc,current)
        if scope['section_ids'] or not doc['sections']:
            add('reference_search','处理已保存的画面参考请求：'+current['query'],'references',session_id=current['id'],scope=current.get('scope'),**scope)
    for application in references.get('applications',[]):
        if application['status']=='pending':
            add('reference_apply','把已选效果落实到相关分镜或输入：'+application['adoption_note'],'references',
                session_id=application['session_id'],section_ids=application['section_ids'],shot_ids=application['shot_ids'])
    for scope in workflow['scopes']:
        for action in scope['next_actions']:
            if action['code']=='visual_style':continue
            value=copy.deepcopy(action);value['section_id']=scope['section_id']
            value['text']=scope['title']+'：'+value['text'] if len(workflow['scopes'])>1 else value['text']
            value.setdefault('view',{'assess_route':'storyboard','design':'storyboard','inputs':'assets',
                                    'sequence_review':'preview','prepare':'preview','select_route':'preview',
                                    'prepare_or_review':'preview','adopted':'preview'}.get(value['code'],'storyboard'))
            pending.append(value)
    return pending
