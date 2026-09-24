"""Thin project assignments and versioned reports. No scheduling or tool calls."""
import copy
from datetime import datetime, timezone
import json

ITEM_STATUSES={'planned','working','blocked','done'}
REPORT_STATUSES={'sent','applied','blocked'}
ITEM_FIELDS={'id','title','work_id','group_id','summary','directory','thread_id','host_id','status'}


def initial():
    return {'schema_version':1,'mode':'single','controller':None,'work_items':[],'directives':[]}


def _text(value,label,identifier=False):
    if not isinstance(value,str) or not value.strip():raise ValueError(label+'须为非空文字')
    if identifier and (value!=value.strip() or any(c.isspace() for c in value)):
        raise ValueError(label+'不能含空白')


def _ids(value,label):
    if not isinstance(value,list) or not value:raise ValueError(label+'须为非空ID列表')
    for identifier in value:_text(identifier,label,True)
    if len(set(value))!=len(value):raise ValueError(label+'含重复ID')


def _version(value,label):
    if type(value) is not int or value<1:raise ValueError(label+'须为正整数')


def _thread(value,label):
    if not isinstance(value,dict):raise ValueError(label+'格式错误')
    _text(value.get('thread_id'),label+' thread_id',True)
    for key in ('host_id','title'):
        if key in value and value[key] is not None:_text(value[key],label+' '+key)


def validate(state):
    if not isinstance(state,dict) or type(state.get('schema_version')) is not int or state['schema_version']!=1:
        raise ValueError('不支持的项目协作数据版本')
    try:json.dumps(state,ensure_ascii=False,allow_nan=False)
    except (TypeError,ValueError) as exc:raise ValueError('协作数据须为有效JSON') from exc
    if state.get('mode') not in ('single','coordinated'):raise ValueError('未知协作模式')
    if 'controller' not in state:raise ValueError('缺少总控登记字段')
    if state['controller'] is not None:_thread(state['controller'],'总控')
    items=state.get('work_items');directives=state.get('directives')
    if not isinstance(items,list) or not isinstance(directives,list):raise ValueError('条目与指令须为列表')
    item_ids=set()
    for item in items:
        if not isinstance(item,dict):raise ValueError('执行条目格式错误')
        for key in ('id','title','work_id','summary','directory'):_text(item.get(key),'条目 '+key,key in ('id','work_id'))
        if item['id'] in item_ids:raise ValueError('执行条目ID重复')
        item_ids.add(item['id'])
        if not isinstance(item.get('status'),str) or item['status'] not in ITEM_STATUSES:raise ValueError('未知执行条目状态')
        for key in ('group_id','thread_id','host_id'):
            if item.get(key) is not None:_text(item[key],'条目 '+key,True)
        if item.get('host_id') and not item.get('thread_id'):raise ValueError('没有thread_id时不能登记会话host_id')
    directive_ids=set()
    for directive in directives:
        if not isinstance(directive,dict):raise ValueError('共用指令格式错误')
        _text(directive.get('id'),'指令ID',True);_text(directive.get('text'),'指令正文')
        if directive['id'] in directive_ids:raise ValueError('共用指令ID重复')
        directive_ids.add(directive['id']);_version(directive.get('version'),'指令版本')
        _ids(directive.get('item_ids'),'指令范围')
        if not set(directive['item_ids'])<=item_ids:raise ValueError('指令引用不存在的执行条目')
        receipts=directive.get('receipts')
        if not isinstance(receipts,dict):raise ValueError('落实回报须按条目ID登记')
        for item_id,receipt in receipts.items():
            if item_id not in item_ids or not isinstance(receipt,dict):raise ValueError('落实回报引用无效条目')
            _version(receipt.get('version'),'回报版本')
            if receipt['version']>directive['version']:raise ValueError('回报不能领先指令版本')
            if not isinstance(receipt.get('status'),str) or receipt['status'] not in REPORT_STATUSES:raise ValueError('未知落实回报状态')
            _text(receipt.get('thread_id'),'回报会话ID',True)
            _text(receipt.get('summary'),'实际回报');_text(receipt.get('reported_at'),'回报时间')
            if receipt['status']=='applied':_text(receipt.get('evidence'),'落实依据')
            elif receipt.get('evidence') is not None and not isinstance(receipt['evidence'],str):raise ValueError('回报依据须为文字')


def apply(state,command,now=None):
    """Return a validated copy; stale reports cannot overwrite a newer instruction."""
    validate(state)
    if not isinstance(command,dict):raise ValueError('协作操作须为对象')
    allowed={
        'set_mode':{'op','mode'},'set_controller':{'op','controller'},
        'upsert_item':{'op','item'},'upsert_directive':{'op','directive','expected_version'},
        'report':{'op','directive_id','item_id','version','status','summary','evidence','thread_id'},
    }
    op=command.get('op')
    if not isinstance(op,str) or op not in allowed or set(command)-allowed[op]:raise ValueError('未知协作操作或字段')
    result=copy.deepcopy(state)
    timestamp=now if now is not None else datetime.now(timezone.utc).isoformat()
    _text(timestamp,'操作时间')
    if op=='set_mode':result['mode']=command.get('mode')
    elif op=='set_controller':
        if 'controller' not in command:raise ValueError('缺少总控登记；清空须明确传null')
        controller=command.get('controller')
        if controller is not None and (not isinstance(controller,dict) or set(controller)-{'thread_id','host_id','title'}):
            raise ValueError('总控登记字段无效')
        result['controller']=copy.deepcopy(controller)
    elif op=='upsert_item':
        item=command.get('item')
        if not isinstance(item,dict) or set(item)-ITEM_FIELDS:raise ValueError('执行条目字段无效')
        _text(item.get('id'),'条目ID',True)
        old=next((value for value in result['work_items'] if value['id']==item['id']),None)
        if old and 'work_id' in item and item['work_id']!=old['work_id']:
            raise ValueError('条目ID已属于其他作品，请为新作品使用新ID')
        updated={**(old or {'status':'planned','group_id':None}),**copy.deepcopy(item)}
        if old:result['work_items'][result['work_items'].index(old)]=updated
        else:result['work_items'].append(updated)
    elif op=='upsert_directive':
        value=command.get('directive')
        if not isinstance(value,dict) or set(value)-{'id','text','item_ids'}:raise ValueError('指令只接受ID、正文与接收条目')
        _text(value.get('id'),'指令ID',True)
        old=next((d for d in result['directives'] if d['id']==value['id']),None)
        if 'expected_version' in command and (type(command['expected_version']) is not int or command['expected_version']!=(old['version'] if old else 0)):
            raise ValueError('指令已更新，请读取当前版本')
        updated={**(old or {'version':1,'receipts':{}}),**copy.deepcopy(value)}
        # A scope-only change adds recipients, not a fictitious new content version.
        if old and updated['text']!=old['text']:updated['version']=old['version']+1
        updated['updated_at']=timestamp
        if old:result['directives'][result['directives'].index(old)]=updated
        else:result['directives'].append(updated)
    elif op=='report':
        directive=next((d for d in result['directives'] if d['id']==command.get('directive_id')),None)
        if directive is None:raise ValueError('回报指令不存在')
        item=next((i for i in result['work_items'] if i['id']==command.get('item_id')),None)
        if item is None or item['id'] not in directive['item_ids']:raise ValueError('回报条目不属于当前指令范围')
        if type(command.get('version')) is not int or command['version']!=directive['version']:
            raise ValueError('回报不是当前指令版本；旧回报不能覆盖新指令')
        if not item.get('thread_id') or command.get('thread_id')!=item['thread_id']:
            raise ValueError('回报须来自当前已登记的执行会话')
        old=directive['receipts'].get(item['id'])
        if old and old['version']==directive['version'] and old['thread_id']==item['thread_id'] and old['status'] in ('applied','blocked') and command.get('status')=='sent':
            raise ValueError('发送回执不能覆盖实际落实回报')
        receipt={key:copy.deepcopy(command[key]) for key in ('version','status','summary','evidence','thread_id') if key in command}
        receipt['reported_at']=timestamp
        directive['receipts'][item['id']]=receipt
    validate(result)
    return result


def view(state,project_title=''):
    state=initial() if state is None else state
    validate(state)
    items=copy.deepcopy(state['work_items']);by_id={item['id']:item for item in items}
    for item in items:
        item['directive_status']={};item['pending_directive_ids']=[]
        item['assignment_status']='assigned' if item.get('thread_id') else 'unassigned'
    directives=[];pending_count=0
    for directive in state['directives']:
        targets=[]
        for item_id in directive['item_ids']:
            item=by_id[item_id];receipt=directive['receipts'].get(item_id)
            current=receipt and receipt['version']==directive['version'] and receipt['thread_id']==item.get('thread_id')
            status='unassigned' if not item.get('thread_id') else receipt['status'] if current else 'pending'
            item['directive_status'][directive['id']]=status
            if status!='applied':item['pending_directive_ids'].append(directive['id']);pending_count+=1
            targets.append({'item_id':item_id,'status':status,'version':directive['version'],'receipt':copy.deepcopy(receipt)})
        directives.append({'id':directive['id'],'text':directive['text'],'version':directive['version'],
                           'item_ids':list(directive['item_ids']),'targets':targets})
    return {'mode':state['mode'],'controller':copy.deepcopy(state['controller']),
            'controller_title':'总控｜'+(project_title.strip() if isinstance(project_title,str) and project_title.strip() else '项目'),
            'items':items,'directives':directives,'pending_count':pending_count}
