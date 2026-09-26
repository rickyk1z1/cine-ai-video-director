"""Confirmed production records and handoffs. No media/API submission or network I/O."""
import copy
import hashlib
import html
import json
import math
import re
import struct
import prompt_guard
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote
from contextlib import contextmanager
from contextvars import ContextVar

KINDS = {'style','asset','voice','grid','previs','package','task','result','decision'}
PREVIS_PATHS = {'previs_reference','blender_previs'}  # The latter remains readable for existing projects.
LABELS = dict(style='影像风格',asset='图片与物料',voice='声音资产',grid='分镜组图',previs='预演参考',package='视频投产包',task='生成任务',result='生成结果',decision='采用与修改决定')
PERMISSION_TYPES = {'image_stage_entry','production_path','video_preparation_entry'}
_evaluation = ContextVar('storyboard_evaluation', default=None)

@contextmanager
def evaluation():
    """Share file/dependency checks for one immutable read, never across writes."""
    if _evaluation.get() is not None:
        yield
        return
    token = _evaluation.set({'files': {}, 'stale': {}})
    try:
        yield
    finally:
        _evaluation.reset(token)

def record_review_status(record):
    """One adoption interpretation for previews, the library and production checks."""
    data = record.get('data', {})
    states = [str(data.get(k) or '').strip().lower() for k in ('status','review_status')]
    if any(s.startswith(('rejected','excluded','superseded','cancelled','retired','not_adopted','revoked')) for s in states):
        return 'excluded'
    if any(s.startswith(('revise','needs_revision','needs_review','changed','stale')) for s in states):
        return 'revise'
    if any(s.startswith(('candidate','pending','planned','awaiting','prepared_for_review','draft','proposed')) for s in states):
        return 'candidate'
    evidence = data.get('adoption_evidence')
    if isinstance(evidence, str) and evidence.strip():
        return 'adopted'
    return 'unknown'

def is_permission(record):
    return (record.get('kind') == 'decision' and record.get('data', {}).get('decision_type') in PERMISSION_TYPES
            and record.get('data', {}).get('planning_only') is not True)

def current_routes(doc):
    latest={}
    choices=sorted((r for r in active_records(doc) if r['kind']=='decision' and r.get('data',{}).get('decision_type')=='production_path'),
                   key=lambda r:(r.get('source_revision',0),r.get('updated_at','')))
    for record in choices:
        for sid in record.get('shot_ids',[]):latest[sid]=record
    return latest

def permission_shots(doc, decision_type=None):
    current = {shot['id'] for sec in doc['sections'] if sec['id'] not in cancelled_sections(doc)
               for group in sec['groups'] for shot in group['shots']}
    if decision_type=='production_path':
        return {sid for sid,record in current_routes(doc).items() if sid in current and record_review_status(record)!='excluded' and record['data'].get('selection_evidence')}
    return {sid for record in active_records(doc) if is_permission(record)
            and (decision_type is None or record['data'].get('decision_type') == decision_type)
            and record_review_status(record) != 'excluded'
            and record['data'].get('selection_evidence')
            for sid in record.get('shot_ids', []) if sid in current}

def shot_confirmed(doc, shot_id):
    """An untouched shot does not lose confirmation when its sibling is edited."""
    for sec in doc['sections']:
        current = next((s for g in sec['groups'] for s in g['shots'] if s['id'] == shot_id), None)
        if current is None:
            continue
        confirmation = state(doc)['confirmations'].get(sec['id'])
        if not confirmation or sec['id'] in cancelled_sections(doc):
            return False
        if confirmation['context'].get('brief') != doc.get('brief') or confirmation['context'].get('source_text','') != doc.get('source_text',''):
            return False
        previous = next((s for g in confirmation['snapshot']['groups'] for s in g['shots'] if s['id'] == shot_id), None)
        return current == previous
    return False

def can_prepare(doc, record):
    wanted = set(record.get('shot_ids', []))
    if wanted:
        return all(shot_confirmed(doc, sid) or sid in permission_shots(doc) for sid in wanted)
    return all(confirmation_status(doc, sid) == 'confirmed' for sid in record['section_ids'])

def sequence_receipt(doc, record):
    """One completed review per work; later user revisions do not reopen it."""
    candidates=[]
    for review in active_records(doc):
        data=review.get('data',{})
        if data.get('decision_type')!='sequence_review' or record_review_status(review)=='excluded' or data.get('result') not in ('ready','revise') or not data.get('summary'):
            continue
        scope=data.get('manifest',{}).get('scope',{})
        if 'reviewed_section_ids' in data:
            covered=set(data['reviewed_section_ids'])
        elif scope.get('shot_ids') is None:
            covered=set(review['section_ids'])
        else:continue
        for revision in active_records(doc):
            basis=revision.get('data',{}).get('revision_basis',[])
            if basis and set(basis)<=covered and revision['data'].get('selection_evidence'):
                covered.update(revision['section_ids'])
        if set(record['section_ids'])<=covered:candidates.append(review)
    return max(candidates,key=lambda r:(r.get('source_revision',0),r.get('updated_at','')),default=None)

def stamp():
    return datetime.now(timezone.utc).isoformat()

def digest(value):
    return hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True,allow_nan=False).encode()).hexdigest()

def state(doc):
    return doc.get('production', {'confirmations':{},'records':[],'export_hash':None})

def context(doc):
    value={k:doc[k] for k in ('title','brief')}
    if doc.get('source_text'):value['source_text']=doc['source_text']
    return value

def active_records(doc):
    records=state(doc)['records']
    retired={i for r in records for i in r.get('data',{}).get('supersedes',[])}
    return [r for r in records if r['id'] not in retired]

def cancelled_sections(doc):
    return {sid for r in active_records(doc) if r['kind']=='decision'
            and r['data'].get('decision_type')=='scope_cancellation'
            and r['data'].get('production_required') is False for sid in r['section_ids']}

def semantic_section(section):
    value=copy.deepcopy(section)
    value.pop('title',None)
    for group in value.get('groups',[]):group.pop('title',None)
    return value

def sections(doc):
    return {s['id']:s for s in doc['sections']}

def shot_ids(section):
    return [s['id'] for g in section['groups'] for s in g['shots']]

def section_hash(doc,section):
    return digest([context(doc),section])

def confirmation_status(doc,sid):
    c=state(doc)['confirmations'].get(sid)
    if not c:return 'draft'
    current=sections(doc).get(sid)
    if sid in cancelled_sections(doc):return 'cancelled'
    return 'confirmed' if current and c['context'].get('brief')==doc.get('brief') and c['context'].get('source_text','')==doc.get('source_text','') and semantic_section(c['snapshot'])==semantic_section(current) else 'changed'

def validate_state(doc):
    p=state(doc)
    if not isinstance(p,dict) or not isinstance(p.get('confirmations'),dict) or not isinstance(p.get('records'),list):
        raise ValueError('制作记录格式错误')
    seen=set()
    for r in p['records']:
        if not isinstance(r,dict) or not isinstance(r.get('id'),str) or r['id'] in seen:raise ValueError('制作记录ID重复或无效')
        seen.add(r['id'])
        if r.get('kind') not in KINDS:raise ValueError('未知制作记录类型')
    for sid,c in p['confirmations'].items():
        if c.get('snapshot',{}).get('id')!=sid or c.get('fingerprint')!=digest([c.get('context'),c.get('snapshot')]):
            raise ValueError('确认快照损坏')

def local_file(root,path):
    if not isinstance(path,str) or not path:raise ValueError('文件路径不能为空')
    p=Path(path).expanduser()
    resolved=p.resolve() if p.is_absolute() else (Path(root)/p).resolve()
    if resolved.exists():return resolved
    # Exact, byte-verified relocation preserves immutable historical references.
    manifest=Path(root)/'过程记录/文件迁移.json'
    if manifest.is_file():
        for entry in json.loads(manifest.read_text('utf8')).get('files',[]):
            if Path(entry['old_path']).resolve()==resolved:
                target=Path(entry['new_path'])
                if target.is_file() and hashlib.sha256(target.read_bytes()).hexdigest()==entry['sha256']:
                    return target
                raise ValueError('迁移后的文件缺失或已变化：'+str(target))
    return resolved

def file_digest(root,path):
    p=local_file(root,path)
    if not p.is_file() or p.stat().st_size==0:raise ValueError('文件缺失或为空：'+path)
    cache = _evaluation.get()
    stat = p.stat()
    key = (str(p), stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns)
    if cache is not None and key in cache['files']:
        return cache['files'][key]
    h=hashlib.sha256()
    with p.open('rb') as stream:
        for block in iter(lambda:stream.read(1024*1024),b''):h.update(block)
    result = h.hexdigest()
    if cache is not None:
        cache['files'][key] = result
    return result

def selected_shots(doc,ids):
    wanted=set(ids); result=[]
    for sec in doc['sections']:
        for group in sec['groups']:
            for shot in group['shots']:
                if shot['id'] in wanted:result.append([sec['id'],sec['title'],sec['notes'],group['id'],group['title'],group['notes'],shot])
    return result

def validate_production_path_decision(r):
    """Validate a user-selected path for one invocation/batch; platform defaults cannot stand in for it."""
    d=r['data']
    if r['kind']!='decision' or d.get('decision_type')!='production_path':return
    for key in ('batch_id','path','selection_evidence'):
        if not isinstance(d.get(key),str) or not d[key].strip():raise ValueError('投产路径决定缺少 '+key)
    if d.get('recommended_path') and d['recommended_path'] not in ('direct_platform','previs_reference'):
        raise ValueError('推荐路线须为直投或先白模预演')
    if 'planning_only' in d and type(d['planning_only']) is not bool:raise ValueError('planning_only须为布尔值')
    path=d['path']
    if path not in ('direct_platform','previs_reference','blender_previs','hybrid'):raise ValueError('未知投产路径')
    if not r['shot_ids']:raise ValueError('投产路径决定须覆盖本批镜头')
    assignments=d.get('assignments')
    if assignments is None and path!='hybrid':
        assignments=[{'path':path,'shot_ids':list(r['shot_ids'])}]
        if d.get('tool'):assignments[0]['tool']=d['tool']
        d['assignments']=assignments
    if not isinstance(assignments,list) or not assignments:raise ValueError('投产路径决定须逐镜分配路径')
    covered=[];kinds=set()
    for item in assignments:
        if not isinstance(item,dict) or item.get('path') not in ('direct_platform',*PREVIS_PATHS):
            raise ValueError('投产路径assignment无效')
        if item['path']=='previs_reference' and not (isinstance(item.get('tool'),str) and item['tool'].strip()):
            raise ValueError('预演参考须声明实际制作工具')
        ids=item.get('shot_ids')
        if not isinstance(ids,list) or not ids or any(not isinstance(i,str) for i in ids) or len(ids)!=len(set(ids)):
            raise ValueError('投产路径assignment须关联唯一镜头')
        covered.extend(ids);kinds.add('previs_reference' if item['path'] in PREVIS_PATHS else item['path'])
    if len(covered)!=len(set(covered)) or set(covered)!=set(r['shot_ids']):
        raise ValueError('投产路径assignment须无重复覆盖本批全部镜头')
    if path in PREVIS_PATHS and any(item['path']!=path for item in assignments):
        raise ValueError('预演路径与逐镜分配类型不一致')
    expected={'direct_platform'} if path=='direct_platform' else {'previs_reference'} if path in PREVIS_PATHS else {'direct_platform','previs_reference'}
    if kinds!=expected:raise ValueError('投产路径类型与逐镜分配不一致')

def validate_generation_recommendation(r):
    d=r['data']
    if d.get('decision_type')!='generation_recommendation':return
    basis=d.get('selection_basis')
    if 'selection_basis' in d:
        if not isinstance(basis,dict) or basis.get('status') not in ('supported','provisional','user_specified'):
            raise ValueError('推荐依据须说明 supported、provisional 或 user_specified 状态')
        priorities=basis.get('priorities')
        if not isinstance(priorities,list) or not 1<=len(priorities)<=3 or any(not isinstance(v,str) or not v.strip() for v in priorities):
            raise ValueError('推荐依据须列出本段一至三个主要要求')
        if any(not isinstance(basis.get(k),str) or not basis[k].strip() for k in ('comparison','cost','uncertainty')):
            raise ValueError('推荐依据须说明候选取舍、整体成本与未确定项；未知应如实说明')
    evidence=d.get('method_evidence',{})
    if isinstance(evidence,dict) and isinstance(evidence.get('sources'),list):
        for source in evidence['sources']:
            if isinstance(source,dict) and 'kind' in source and source['kind'] not in ('official','case','observed_result','user_report'):
                raise ValueError('未知的模型推荐依据类型')
    # Older recommendations stay selectable; missing comparison evidence is not a new permission gate.
    if 'planning_version' not in d:return
    if d['planning_version']!=1:raise ValueError('不支持的生成建议版本')
    if not r['shot_ids']:raise ValueError('生成建议须关联实际镜头')
    evidence=d.get('method_evidence',{})
    if not isinstance(evidence,dict) or evidence.get('status') not in ('queried','reused','no_match','unavailable','user_specified') or not str(evidence.get('summary','')).strip():
        raise ValueError('生成建议须记录实际资料匹配结果与理由')
    if evidence['status'] in ('queried','reused'):
        sources=evidence.get('sources',[])
        if not isinstance(sources,list) or not sources or any(not isinstance(s,dict) or not all(isinstance(s.get(k),str) and s[k].strip() for k in ('url','checked_at','applied','limits')) for s in sources):
            raise ValueError('已查询或复用依据须有来源、日期、借用方法及适用限制')
    options=d.get('options',[])
    if not isinstance(options,list) or not options:raise ValueError('生成建议缺少具体方案')
    ids=[]
    for option in options:
        if not isinstance(option,dict) or not all(isinstance(option.get(k),str) and option[k].strip() for k in ('id','path','model','platform','input_mode','reason','inputs','limits')):
            raise ValueError('方案须说明id、路线、模型、平台、输入方式、素材、理由与限制')
        if option['path'] not in ('direct_platform','previs_reference'):raise ValueError('未知建议路线')
        if option['path']=='previs_reference' and not option.get('tool'):raise ValueError('预演方案须注明工具')
        ids.append(option['id'])
    if len(ids)!=len(set(ids)):raise ValueError('方案ID重复')
    if sum(o.get('recommended') is True for o in options)!=1:raise ValueError('生成建议须有一个主推荐')


def validate_image_stage_decision(r):
    """Record the user's permission to enter image asset and storyboard-image work."""
    d=r['data']
    if r['kind']!='decision' or d.get('decision_type')!='image_stage_entry':return
    if not r['shot_ids']:raise ValueError('图片制作阶段决定须覆盖实际镜头')
    for key in ('batch_id','selection_evidence'):
        if not isinstance(d.get(key),str) or not d[key].strip():raise ValueError('图片制作阶段决定缺少 '+key)

def package_path_issues(doc,r,root,records):
    d=r['data'];issues=[]
    rid=d.get('production_path_decision_id')
    invocation=d.get('production_invocation_id');batch=d.get('production_batch_id')
    if not all(isinstance(x,str) and x.strip() for x in (rid,batch)):
        return ['缺少本批投产路径选择绑定']
    decision=records.get(rid)
    if rid not in {x['id'] for x in active_records(doc)}:return ['投产路径选择已被替代或不存在']
    if not decision or decision.get('kind')!='decision' or decision.get('data',{}).get('decision_type')!='production_path':
        return ['投产路径选择记录不存在或类型错误']
    if rid not in r['depends_on']:issues.append('投产路径选择未列为投产包依赖')
    if is_stale(doc,decision,root):issues.append('投产路径选择范围已变化，须本批重新选择')
    choice=decision['data']
    latest=current_routes(doc)
    if any(latest.get(sid,{}).get('id')!=rid for sid in r['shot_ids']):issues.append('相关镜头已有更新的路线选择，须采用当前决定')
    for key in ('platform','model','input_mode'):
        if choice.get(key) and d.get(key)!=choice[key]:issues.append('当前'+key+'与本批已选组合不一致')
    if batch!=choice.get('batch_id'):
        issues.append('投产路径选择不属于当前批次')
    if not choice.get('selection_evidence'):issues.append('投产路径缺少用户选择依据')
    wanted=set(r['shot_ids'])
    matches=[a for a in choice.get('assignments',[]) if wanted & set(a.get('shot_ids',[]))]
    covered={sid for a in matches for sid in a['shot_ids'] if sid in wanted}
    if not matches or covered!=wanted:
        issues.append('投产包镜头未完整归入本批路径');return issues
    kinds={'previs_reference' if a['path'] in PREVIS_PATHS else a['path'] for a in matches};route=d.get('route')
    if kinds=={'direct_platform'} and route not in ('direct','grid'):
        issues.append('本批直投镜头的投产包路径不一致')
    if kinds=={'previs_reference'} and route!='previs':
        issues.append('本批预演镜头须使用previs投产包路径')
    if len(kinds)==2 and (choice.get('path')!='hybrid' or route!='hybrid'):
        issues.append('同一视频混合输入须使用hybrid投产包路径')
    return issues

def dependency_identity(record):
    """Editing a label or receipt does not change a media input's identity."""
    data = {k:v for k,v in record.get('data',{}).items()
            if k not in {'adoption_evidence','selection_evidence','selection_context','invocation_id','updated_at','checked_at','status','review_status'}}
    return digest([record['kind'], record.get('shot_ids',[]), record.get('files',[]), data,
                   record.get('body','') if not record.get('files') and not is_permission(record) else ''])

def fingerprint(doc,r,root):
    records={x['id']:x for x in state(doc)['records']}
    refs={rid:records.get(rid,{}).get('version') for rid in r['depends_on']}
    files={}
    for f in r.get('files',[]):
        try:files[f['path']]=file_digest(root,f['path'])
        except (ValueError,OSError):files[f['path']]=None
    scope=selected_shots(doc,r['shot_ids']) if r['shot_ids'] else [[sid,sections(doc).get(sid)] for sid in r['section_ids']]
    styles={x['id']:x['version'] for x in state(doc)['records'] if x['kind']=='style' and x['id']!=r['id'] and set(x['section_ids'])&set(r['section_ids'])} if r['kind']!='style' else {}
    if r.get('_binding_version') == 4:
        refs = {rid:dependency_identity(records[rid]) if rid in records else None for rid in r['depends_on']}
        visual = r['kind'] in ('asset','grid')
        if visual:
            # Artwork does not change when its display number, duration or soundtrack is edited.
            fields = ('content','framing','camera','start','end','transition','assets','notes')
            frame = r['kind']=='grid' or r['data'].get('asset_role')=='storyboard_frame'
            scope = [[x[0],x[2],x[3],x[5],{k:x[6].get(k) for k in ('id',*fields)}] for x in scope] if frame and r['shot_ids'] else r['shot_ids']
            binding_context = None
        else:
            binding_context = [doc.get('brief'),doc.get('source_text','')]
            scope=[[x[0],x[2],x[3],x[5],x[6]] for x in scope] if r['shot_ids'] else [[sid,semantic_section(sec) if sec else None] for sid,sec in scope]
        inputs = r.get('data',{}).get('actual_inputs',[])
        input_files = []
        for item in inputs if isinstance(inputs,list) else []:
            path = item.get('path') if isinstance(item,dict) else None
            try:input_files.append(file_digest(root,path) if path else None)
            except (ValueError,OSError):input_files.append(None)
        styles={x['id']:dependency_identity(x) for x in active_records(doc) if x['kind']=='style' and x['id']!=r['id']
                and record_review_status(x) not in ('candidate','revise','excluded') and set(x['section_ids'])&set(r['section_ids'])}
        return digest([binding_context,scope,refs,files,inputs,input_files,styles])
    if r.get('_binding_version') in (2,3):
        scope=[[x[0],x[2],x[3],x[5],x[6]] for x in scope] if r['shot_ids'] else [[sid,semantic_section(sec) if sec else None] for sid,sec in scope]
        binding_context=[doc.get('brief'),doc['source_text']] if doc.get('source_text') else doc.get('brief')
        if r.get('_binding_version')==3:
            inputs=r.get('data',{}).get('actual_inputs',[])
            input_files=[]
            if isinstance(inputs,list):
                for item in inputs:
                    path=item.get('path') if isinstance(item,dict) else None
                    try:input_files.append(file_digest(root,path) if path else None)
                    except (ValueError,OSError):input_files.append(None)
            return digest([binding_context,scope,refs,files,styles,inputs,input_files])
        return digest([binding_context,scope,refs,files,styles])
    return digest([context(doc),scope,refs,files,styles])

def is_stale(doc,r,root,visiting=None):
    cache = _evaluation.get()
    key = (id(doc), r['id'], r.get('version'), r.get('_dependency'), str(root))
    if cache is not None and key in cache['stale']:
        return cache['stale'][key]
    result = _is_stale(doc,r,root,visiting)
    if cache is not None:
        cache['stale'][key] = result
    return result

def _is_stale(doc,r,root,visiting=None):
    if r.get('data',{}).get('decision_type')=='generation_recommendation' and not r['data'].get('partial_scope'):
        expected={sid for sec in doc['sections'] if sec['id'] in r['section_ids'] and sec['id'] not in cancelled_sections(doc) for sid in shot_ids(sec)}
        if expected!=set(r['shot_ids']):return True
    if is_permission(r) or r.get('data',{}).get('decision_type')=='production_path':
        # Permission is a scoped user decision, not a snapshot of the creative draft.
        current = {s['id'] for sec in doc['sections'] if sec['id'] not in cancelled_sections(doc)
                   for group in sec['groups'] for s in group['shots']}
        return record_review_status(r)=='excluded' or not bool(set(r['shot_ids']) & current)
    visiting=set(visiting or ())
    if r['id'] in visiting:return True
    visiting.add(r['id'])
    if r.get('_dependency')!=fingerprint(doc,r,root):
        # Legacy records remain readable; accept only a proven display-title change.
        old=copy.deepcopy(doc); confirmations=state(doc)['confirmations']
        contexts=[confirmations[sid].get('context',{}) for sid in r['section_ids'] if sid in confirmations]
        if r.get('_binding_version') in (2,3,4) or not contexts or any(c!=contexts[0] for c in contexts):return True
        old['title']=contexts[0].get('title',old['title'])
        for sec in old['sections']:
            snapshot=confirmations.get(sec['id'],{}).get('snapshot',{})
            if snapshot:
                sec['title']=snapshot['title'];groups={g['id']:g for g in snapshot['groups']}
                for g in sec['groups']:
                    if g['id'] in groups:g['title']=groups[g['id']]['title']
        if r.get('_dependency')!=fingerprint(old,r,root):return True
    records={x['id']:x for x in state(doc)['records']}
    # A flawed source video is factual repair evidence, not an adopted current design.
    source=r.get('data',{}).get('repair_context') if r.get('kind')=='package' else None
    historical_origin=source.get('source_result_id') if isinstance(source,dict) else None
    return any(rid not in records or rid!=historical_origin and is_stale(doc,records[rid],root,visiting) for rid in r['depends_on'])

def confirm(doc,sid,evidence):
    sec=sections(doc).get(sid)
    if sid in cancelled_sections(doc):raise ValueError('该段已取消制作，历史可读但不能重新确认')
    if not sec or not shot_ids(sec):raise ValueError('段落不存在或没有镜头')
    if not isinstance(evidence,str) or not evidence.strip():raise ValueError('须记录用户确认依据')
    p=doc.setdefault('production',copy.deepcopy(state(doc)))
    old=p['confirmations'].get(sid)
    if old and confirmation_status(doc,sid)=='confirmed':return
    history=copy.deepcopy(old.get('history',[])) if old else []
    if old:history.append({k:v for k,v in old.items() if k!='history'})
    p['confirmations'][sid]={'snapshot':copy.deepcopy(sec),'context':context(doc),
        'fingerprint':section_hash(doc,sec),'source_revision':doc['revision'],
        'confirmed_at':stamp(),'evidence':evidence,'history':history}

def put_record(doc,item,root):
    if not isinstance(item,dict):raise ValueError('记录须为对象')
    r={k:copy.deepcopy(item.get(k,default)) for k,default in {
        'id':'','kind':'','title':'','body':'','section_ids':[],'shot_ids':[],
        'depends_on':[],'files':[],'data':{}}.items()}
    for key in ('id','kind','title','body'):
        if not isinstance(r[key],str) or (key!='body' and not r[key].strip()):raise ValueError('记录缺少 '+key)
    if r['kind'] not in KINDS:raise ValueError('未知制作类型')
    for key in ('section_ids','shot_ids','depends_on'):
        if not isinstance(r[key],list) or any(not isinstance(x,str) for x in r[key]) or len(set(r[key]))!=len(r[key]):raise ValueError('关联ID无效：'+key)
    historical=r['kind'] in ('task','result')
    if not r['section_ids'] or (not historical and any(s not in sections(doc) for s in r['section_ids'])):raise ValueError('须关联实际段落')
    available={i for sid in r['section_ids'] if sid in sections(doc) for i in shot_ids(sections(doc)[sid])}
    if not historical and not set(r['shot_ids'])<=available:raise ValueError('镜头不属于声明段落')
    if not isinstance(r['data'],dict) or not isinstance(r['files'],list):raise ValueError('data/files格式错误')
    validate_production_path_decision(r)
    validate_image_stage_decision(r)
    validate_generation_recommendation(r)
    if r['kind']=='decision' and r['data'].get('decision_type')=='sequence_review':
        data=r['data']
        if data.get('result') not in ('ready','revise') or not isinstance(data.get('summary'),str) or not data['summary'].strip():
            raise ValueError('整段审查须保存本次实际结论，不能自动填通过')
        if not isinstance(data.get('manifest'),dict) or not data['manifest'].get('fingerprint'):
            raise ValueError('整段审查须引用实际图序预演依据')
        previous=next((x for x in state(doc)['records'] if x['id']==r['id']),None)
        if previous is None:
            import rehearsal
            scope=data['manifest'].get('scope',{})
            actual=rehearsal.manifest(doc,root,section_ids=scope.get('section_ids'),shot_ids=scope.get('shot_ids'))
            if actual['issues']:
                raise ValueError('首次整段审查的实际图序输入尚不完整：'+'；'.join(actual['issues']))
            actual_sections={frame['section_id'] for frame in actual['frames']}
            if set(r['section_ids'])!=actual_sections:raise ValueError('审查声明段落与实际所看范围不一致')
            if data['manifest']['fingerprint']!=actual['fingerprint'] or r['shot_ids']!=actual['shot_ids']:
                raise ValueError('审查所引用的图序不是当前实际范围，请读取准确预演依据')
            data['reviewed_section_ids']=[sid for sid in r['section_ids'] if set(shot_ids(sections(doc)[sid]))<=set(actual['shot_ids'])]
        else:
            data['reviewed_section_ids']=list(previous['data'].get('reviewed_section_ids',[]))
    if r['kind'] not in ('style','decision','task','result') and set(r['section_ids']) & cancelled_sections(doc):raise ValueError('已取消范围不能准备新的制作输入')
    p=doc.setdefault('production',copy.deepcopy(state(doc)))
    by_id={x['id']:x for x in p['records']}
    # Recording a scoped user choice does not execute media or adopt unfinished inputs.
    supersedes=r['data'].get('supersedes',[])
    if not isinstance(supersedes,list) or any(not isinstance(i,str) or i not in by_id or i==r['id'] for i in supersedes):
        raise ValueError('被替代记录须引用其他已存在的记录ID')
    if any(i not in by_id or i==r['id'] for i in r['depends_on']):raise ValueError('依赖记录不存在或自引用')
    def cycle(rid,seen):
        if rid==r['id']:return True
        if rid in seen:return False
        return any(cycle(x,seen|{rid}) for x in by_id[rid]['depends_on'])
    if any(cycle(i,set()) for i in r['depends_on']):raise ValueError('制作依赖存在循环')
    for f in r['files']:
        if not isinstance(f,dict) or not isinstance(f.get('role'),str):raise ValueError('文件须声明path和role')
        f['sha256']=file_digest(root,f.get('path'))
    if r['kind'] not in ('style','decision') and not can_prepare(doc,r):
        # Results/tasks from already submitted jobs remain recordable after draft changes.
        if r['kind'] not in ('task','result'):raise ValueError('先确认关联段落，再记录制作输入')
    if r['kind']=='grid':
        cells=r['data'].get('cells',[])
        if not isinstance(cells,list) or not cells:raise ValueError('组图须声明画格')
        mapped=[x.get('shot_id') for x in cells if isinstance(x,dict)]
        expected=[x[-1]['id'] for x in selected_shots(doc,r['shot_ids'])]
        if mapped!=expected or len(mapped)!=len(cells):raise ValueError('画格须按原分镜顺序一一对应镜头')
        all_ids=[x[-1]['id'] for x in selected_shots(doc,[s['id'] for sec in doc['sections'] for g in sec['groups'] for s in g['shots']])]
        positions=[all_ids.index(s) for s in mapped]
        if positions!=list(range(positions[0],positions[0]+len(positions))):raise ValueError('组图不能跨过中间镜头')
    external = r['kind']=='result' and r['data'].get('source_type')=='external'
    if external:
        if not r['data'].get('source_evidence') or not any(Path(f['path']).suffix.lower() in ('.mp4','.mov','.mkv','.webm') for f in r['files']):
            raise ValueError('外部视频须有真实视频文件和来源依据，不伪造历史投产包')
        video=next(f for f in r['files'] if Path(f['path']).suffix.lower() in ('.mp4','.mov','.mkv','.webm'))
        try:
            probe=subprocess.run(['ffprobe','-v','error','-select_streams','v:0','-show_entries','stream=codec_name,width,height:format=duration',
                                  '-of','json',str(local_file(root,video['path']))],capture_output=True,text=True,check=True,timeout=15)
            media=json.loads(probe.stdout);duration=float(media['format']['duration'])
            if not media.get('streams') or not math.isfinite(duration) or duration<=0:raise ValueError('视频无有效时长或视频流')
            declared=r['data'].get('source_duration')
            if declared is not None and (type(declared) not in (int,float) or abs(declared-duration)>.05):raise ValueError('声明时长与外部视频不一致')
            r['data']['source_duration']=duration
        except (OSError,ValueError,KeyError,subprocess.SubprocessError) as exc:
            raise ValueError('无法核实外部视频：'+str(exc)) from exc
    if r['kind'] in ('task','result') and not external:
        pkg=r['data'].get('package_id'); ver=r['data'].get('package_version')
        if pkg not in by_id or by_id[pkg]['kind']!='package' or type(ver) is not int:raise ValueError('任务/结果须绑定投产包及版本')
        versions=[by_id[pkg]]+by_id[pkg].get('history',[])
        source=next((v for v in versions if v['version']==ver),None)
        if source is None:raise ValueError('投产包版本不存在')
        if not set(r['section_ids'])<=set(source['section_ids']) or not set(r['shot_ids'])<=set(source['shot_ids']):raise ValueError('任务/结果范围不属于所引用的历史投产包')
        if r['kind']=='task' and r['data'].get('status')=='submitted' and not (r['data'].get('task_id') or r['data'].get('thread_id')):raise ValueError('已提交任务须保存真实任务标识')
    if r['kind']=='result' and r['data'].get('status')=='partially_adopted':
        accepted=r['data'].get('adopted_shot_ids')
        if not isinstance(accepted,list) or not accepted or len(accepted)!=len(set(accepted)) or not set(accepted)<set(r['shot_ids']) or not r['data'].get('adoption_evidence'):
            raise ValueError('部分采用须列出本结果中的已采用镜头及实际采用依据')
    if r['kind']=='result' and r['data'].get('status')=='adopted' and 'adopted_shot_ids' in r['data']:
        accepted=r['data']['adopted_shot_ids']
        if not isinstance(accepted,list) or len(accepted)!=len(set(accepted)) or set(accepted)!=set(r['shot_ids']):
            raise ValueError('整项采用不能只列出部分镜头')
    old=by_id.get(r['id'])
    if old and old['kind']!=r['kind']:raise ValueError('记录类型不可变更，请使用新的ID')
    r['version']=(old['version']+1) if old else 1
    r['history']=copy.deepcopy(old.get('history',[])) if old else []
    if old:r['history'].append({k:v for k,v in old.items() if k!='history'})
    r['source_revision']=doc['revision'];r['updated_at']=stamp()
    r['_binding_version']=4
    r['_dependency']=fingerprint(doc,r,root)
    if old:p['records'][p['records'].index(old)]=r
    else:p['records'].append(r)
    return r

def image_size(path):
    # Header dimensions only; this deliberately does not claim image decode/visual validation.
    with Path(path).open('rb') as stream:
        header=stream.read(24)
        if header[:8]==b'\x89PNG\r\n\x1a\n' and header[12:16]==b'IHDR':return struct.unpack('>II',header[16:24])
        stream.seek(0)
        if stream.read(2)==b'\xff\xd8':
            while True:
                b=stream.read(1)
                if not b:break
                if b!=b'\xff':continue
                marker=stream.read(1)
                while marker==b'\xff':marker=stream.read(1)
                if not marker or marker in (b'\xd9',b'\xda'):break
                if marker[0] in (0x01,*range(0xD0,0xD9)):continue
                length=stream.read(2)
                if len(length)!=2:break
                size=struct.unpack('>H',length)[0]
                if size<2:break
                if marker[0] in (0xC0,0xC1,0xC2,0xC3,0xC5,0xC6,0xC7,0xC9,0xCA,0xCB,0xCD,0xCE,0xCF):
                    data=stream.read(5)
                    if len(data)==5:
                        h,w=struct.unpack('>HH',data[1:]);return w,h
                    break
                stream.seek(size-2,1)
    raise ValueError('组图尺寸无法读取，请用已检查的PNG/JPEG组图')

def grid_issues(record,root,path):
    errors=[];boxes=[]
    try:w,h=image_size(local_file(root,path))
    except (ValueError,OSError,struct.error) as e:return [str(e)]
    cells=record['data'].get('cells',[])
    if not cells:return ['组图缺少画格映射']
    for cell in cells:
        box=cell.get('box')
        if not isinstance(box,list) or len(box)!=4 or any(type(x) is not int for x in box) or not (0<=box[0]<box[2]<=w and 0<=box[1]<box[3]<=h):
            errors.append('组图画格缺少有效实际裁切范围');continue
        for other in boxes:
            if min(box[2],other[2])>max(box[0],other[0]) and min(box[3],other[3])>max(box[1],other[1]):errors.append('组图画格重复或交叠')
        boxes.append(box)
    return list(dict.fromkeys(errors))

def adopted(value):
    """Structured, evidence-backed adoption; legacy values remain readable, not auto-approved."""
    return (isinstance(value,dict) and value.get('status')=='adopted'
            and isinstance(value.get('evidence'),str) and bool(value['evidence'].strip()))

def reference_record(records,data,rid):
    """A repair may use an immutable historical result instead of its latest version."""
    current=records[rid];ctx=data.get('repair_context')
    if isinstance(ctx,dict) and rid==ctx.get('source_result_id'):
        return next((v for v in [current]+current.get('history',[]) if v['version']==ctx.get('source_result_version')),current)
    return current

def repair_issues(doc,r,root,records):
    """Check factual source binding; isolation and cut quality still need human review."""
    ctx=r['data'].get('repair_context')
    if ctx is None:return []
    if not isinstance(ctx,dict):return ['返修来源须为对象']
    issues=[]
    rid=ctx.get('source_result_id');version=ctx.get('source_result_version')
    current=records.get(rid)
    if not current or current.get('kind')!='result' or type(version) is not int:
        return ['返修须绑定已有生成结果及其版本']
    source=next((v for v in [current]+current.get('history',[]) if v['version']==version),None)
    if source is None:return ['返修来源版本不存在']
    if rid not in r['depends_on']:issues.append('返修来源结果未列为投产包依赖')
    if not set(r['shot_ids'])<=set(source['shot_ids']):issues.append('返修镜头不属于来源结果')
    path=ctx.get('source_file_path');sha=ctx.get('source_sha256')
    found=[f for f in source['files'] if f['path']==path and Path(f['path']).suffix.lower() in ('.mp4','.mov','.mkv','.webm')]
    if len(found)!=1 or not isinstance(sha,str) or found[0]['sha256']!=sha:
        issues.append('返修须精确绑定来源视频文件与记录哈希')
        return issues
    try:
        if file_digest(root,path)!=sha:issues.append('返修来源视频文件已变化')
        probe=subprocess.run(['ffprobe','-v','error','-show_entries','format=duration','-of','json',str(local_file(root,path))],capture_output=True,text=True,check=True,timeout=15)
        source_duration=float(json.loads(probe.stdout)['format']['duration'])
        if not math.isfinite(source_duration) or source_duration<=0:raise ValueError('时长无效')
    except (OSError,ValueError,KeyError,subprocess.SubprocessError):
        issues.append('返修来源视频无法实测时长');return issues
    def interval(value):
        return (isinstance(value,list) and len(value)==2 and
                all(type(x) in (int,float) and math.isfinite(x) for x in value) and
                0<=value[0]<value[1]<=source_duration+0.05)
    reported=ctx.get('reported_range')
    if not (interval(reported) or isinstance(reported,str) and reported.strip()):issues.append('缺少用户所述时间范围')
    cut=ctx.get('cut_range')
    if not interval(cut):issues.append('返修实际剪点超出来源视频或无效')
    elif interval(reported) and (reported[1]<=cut[0] or cut[1]<=reported[0]):issues.append('用户所述时间范围与实际定位镜头不相交')
    if ctx.get('isolation')!='separable' or not ctx.get('cut_evidence'):
        issues.append('单镜替换须有可独立拆出及前后剪点的实际画面依据')
    for key in ('left_join','right_join','selection_evidence'):
        if not isinstance(ctx.get(key),str) or not ctx[key].strip():issues.append('返修缺少 '+key)
    if ctx.get('method') not in ('independent_clip','native_retake'):issues.append('未知返修方式')
    target=ctx.get('target_duration')
    if type(target) not in (int,float) or not math.isfinite(target) or target<=0:issues.append('返修目标时长无效')
    return issues

def timing_issues(doc, record):
    """Content time is not stretched to fill a platform duration or hidden handles."""
    data=record['data']
    if data.get('repair_context'):return []  # Actual source cut/target is checked by repair_issues.
    timeline=data.get('timeline',[])
    if not isinstance(timeline,list) or not timeline:return []
    shots=[entry[-1] for entry in selected_shots(doc,record['shot_ids'])]
    if len(timeline)!=len(shots):return []
    finite=lambda value:type(value) in (int,float) and math.isfinite(value)
    handles=data.get('generation_handles',{})
    if not isinstance(handles,dict):return ['生成裁切余量须为对象']
    if set(handles)-{'head_seconds','tail_seconds','evidence'}:return ['生成裁切余量含未知字段']
    head,tail=handles.get('head_seconds',0),handles.get('tail_seconds',0)
    if not all(finite(value) and value>=0 for value in (head,tail)):return ['生成首尾余量须为非负有限秒数']
    issues=[]
    if (head or tail) and not (isinstance(handles.get('evidence'),str) and handles['evidence'].strip()):
        issues.append('平台档位或裁切余量须说明实际用途，不能默认拉长内容')
    content=data.get('content_timeline')
    if content is not None:
        if not isinstance(content,list) or [x.get('shot_id') for x in content if isinstance(x,dict)]!=[sh['id'] for sh in shots]:
            return issues+['内容时间表与当前镜头顺序不一致']
        end=0
        for span in content:
            start,stop=span.get('start'),span.get('end')
            if not finite(start) or not finite(stop) or not math.isclose(start,end,abs_tol=1e-6) or stop<=start:
                return issues+['内容时间表有空隙、交叠或无效值']
            end=stop
    for index,(shot,span) in enumerate(zip(shots,timeline)):
        if not isinstance(span,dict):continue
        start,stop=span.get('start'),span.get('end')
        if not finite(start) or not finite(stop):continue
        extra=(head if index==0 else 0)+(tail if index==len(shots)-1 else 0)
        seconds=(content[index]['end']-content[index]['start']) if content is not None else stop-start-extra
        if seconds<=0:issues.append('生成余量占满了镜头内容时段：'+shot['id']);continue
        planned=shot.get('duration')
        if finite(planned) and planned>0 and not math.isclose(seconds,planned,abs_tol=.001):
            issues.append('生成时间安排未承接工作台当前内容时长：'+(shot.get('number') or shot['id']))
        if content is not None and not math.isclose(stop-start,seconds+extra,abs_tol=.001):
            issues.append('生成时间与内容时间加首尾余量不一致：'+(shot.get('number') or shot['id']))
    return issues

def package_issues(doc,r,root):
    issues=[];d=r['data'];records={x['id']:x for x in state(doc)['records']}
    if r['kind']!='package':return ['不是投产包']
    if set(r['section_ids']) & cancelled_sections(doc):issues.append('该范围已取消制作，禁止投产')
    issues.extend(package_path_issues(doc,r,root,records))
    issues.extend(repair_issues(doc,r,root,records))
    if isinstance(d.get('prompt_review'),dict) and d['prompt_review'].get('review_version')==3 and d.get('review_basis','storyboard_images')!='text_only' and not d.get('repair_context'):
        receipt=sequence_receipt(doc,r)
        if receipt is None:issues.append('本批图稿尚未完成那一次整段预演审查；由助手完成并给出生成建议，不增加用户审批')
        elif d.get('sequence_review_id') and d['sequence_review_id']!=receipt['id']:
            issues.append('整段审查来源不属于本批当前工作')
    if is_stale(doc,r,root):issues.append('输入或依赖已变化，须更新投产包')
    for key in ('platform','mode','model','prompt','selection_evidence','capability_evidence','grouping_reason'):
        if not isinstance(d.get(key),str) or not d[key].strip():issues.append('缺少 '+key)
    params=d.get('parameters',{})
    if not isinstance(params,dict):params={};issues.append('parameters须为对象')
    duration=params.get('duration')
    if type(duration) not in (int,float) or not math.isfinite(duration) or duration<=0:issues.append('缺少有效视频时长')
    for key in ('ratio','resolution'):
        if not isinstance(params.get(key),str) or not params[key]:issues.append('缺少 '+key)
    if not r['shot_ids']:issues.append('投产包未关联镜头')
    expected=[x[-1]['id'] for x in selected_shots(doc,r['shot_ids'])]
    timeline=d.get('timeline',[])
    if not isinstance(timeline,list):timeline=[]
    if [x.get('shot_id') for x in timeline if isinstance(x,dict)]!=expected:issues.append('时间安排与镜头顺序不一致')
    end=0
    for span in timeline:
        if not isinstance(span,dict):issues.append('无效时间安排');continue
        start,stop=span.get('start'),span.get('end')
        if type(start) not in (int,float) or type(stop) not in (int,float) or not math.isfinite(start) or not math.isfinite(stop) or start!=end or stop<=start:issues.append('时间安排有空隙/交叠或无效值');continue
        end=stop
    if duration is not None and end!=duration:issues.append('时间安排未覆盖完整时长')
    issues.extend(timing_issues(doc,r))
    refs=d.get('references',[])
    if not isinstance(refs,list):refs=[];issues.append('references须为列表')
    coverage=set();labels=set();used_files=set();voice_ids=set()
    current_ids={x['id'] for x in active_records(doc)}
    for rid in r['depends_on']:
        a=records.get(rid)
        if not a or rid not in current_ids or is_stale(doc,a,root) or record_review_status(a)!='adopted':continue
        if a['kind']=='asset' and a['data'].get('asset_role')=='storyboard_frame' and a['files']:
            coverage.update(a['shot_ids'])
        if a['kind']=='grid' and a['files']:
            if any(not grid_issues(a,root,f['path']) for f in a['files']):coverage.update(a['shot_ids'])
    for ref in refs:
        if not isinstance(ref,dict):issues.append('无效素材引用');continue
        rid=ref.get('record_id');current=records.get(rid)
        if not current or rid not in r['depends_on']:issues.append('引用素材未列为依赖：'+str(rid));continue
        a=reference_record(records,d,rid)
        ctx=d.get('repair_context')
        repair_source=isinstance(ctx,dict) and a['kind']=='result' and rid==ctx.get('source_result_id') and ref.get('file_path')==ctx.get('source_file_path')
        if not repair_source:
            if rid not in current_ids:issues.append('素材已被替代：'+rid)
            if is_stale(doc,a,root):issues.append('素材记录需复核：'+rid)
            if record_review_status(a)!='adopted':issues.append('素材尚未采用：'+rid)
            if not a['data'].get('adoption_evidence'):issues.append('素材缺少采用依据：'+rid)
        if not a['files']:issues.append('素材没有实际文件：'+rid)
        selected=ref.get('file_path')
        matches=[f for f in a['files'] if f['path']==selected]
        if len(matches)!=1:issues.append('引用须精确选择一个实际文件：'+rid)
        else:used_files.add((rid,selected))
        label=ref.get('label')
        if not isinstance(label,str) or not label or label in labels:issues.append('素材标签缺失或重复')
        labels.add(label)
        if not ref.get('purpose'):issues.append('缺少素材职责：'+rid)
        if a['kind']=='voice':voice_ids.add(rid)
        if a['kind']=='grid':
            grid_errors=grid_issues(a,root,selected)
            issues.extend(grid_errors)
    if d.get('review_basis','storyboard_images') not in ('storyboard_images','text_only'):issues.append('未知审阅依据类型')
    if d.get('review_basis')=='text_only' and not d.get('review_basis_evidence'):issues.append('文字审阅路径缺少本次任务依据')
    if d.get('review_basis','storyboard_images')!='text_only' and not set(r['shot_ids'])<=coverage:issues.append('存在缺少采用分镜图的镜头')
    for sid in r['shot_ids']:
        if not shot_confirmed(doc,sid) and sid not in coverage:
            issues.append('本镜当前内容尚待审阅：'+sid)
    if d.get('route') not in ('direct','grid','previs','hybrid'):issues.append('缺少制作路径')
    if (d.get('route')=='grid' or any(records.get(x.get('record_id'),{}).get('kind')=='grid' for x in refs if isinstance(x,dict))) and not d.get('grid_full_frame_instruction'):
        issues.append('须声明组图仅供参考、成片全画幅')
    if d.get('route') in ('previs','hybrid'):
        previews=[records.get(x,{}) for x in r['depends_on'] if records.get(x,{}).get('kind')=='previs']
        choice=records.get(d.get('production_path_decision_id'),{}).get('data',{})
        needed={sid for a in choice.get('assignments',[]) if a.get('path') in PREVIS_PATHS for sid in a.get('shot_ids',[]) if sid in r['shot_ids']}
        covered=set()
        for a in previews:
            if adopted(a['data'].get('static_adoption')) and adopted(a['data'].get('dynamic_adoption')) and any(f.get('role')=='reference_video' and (a['id'],f['path']) in used_files for f in a['files']):
                covered.update(a['shot_ids'])
        if not needed<=covered:issues.append('缺少覆盖预演镜头的已确认静态/动态参考视频')
    ctx=d.get('repair_context')
    if isinstance(ctx,dict) and ctx.get('method')=='native_retake' and not any(x.get('record_id')==ctx.get('source_result_id') and x.get('file_path')==ctx.get('source_file_path') for x in refs if isinstance(x,dict)):
        issues.append('平台局部重拍须把真实来源视频列入实际上传')
    speech=d.get('speech')
    if speech not in ('none','offscreen','dialogue'):issues.append('须声明人声类型')
    if speech in ('offscreen','dialogue'):
        uses=d.get('audio_uses')
        if uses is None:
            uses=[{'record_id':rid,'implementation':'native_recording'} for rid in voice_ids]
        if not isinstance(uses,list) or not uses:
            issues.append('缺少实际对白音频或音频使用计划');uses=[]
        for use in uses:
            if not isinstance(use,dict):issues.append('音频使用项无效');continue
            method=use.get('implementation');caps=d.get('audio_capability',{})
            if not isinstance(caps,dict):caps={}
            if method=='native_generation':
                if not all(isinstance(use.get(k),str) and use[k].strip() for k in ('text','speaker')):
                    issues.append('原生人声须声明台词和说话者')
                elif use['text'] not in d.get('prompt','') or use['speaker'] not in d.get('prompt',''):
                    issues.append('原生人声的台词和说话者须进入实际投喂正文')
                if caps.get('native_speech') is not True or not caps.get('evidence'):
                    issues.append('未核实入口原生人声能力')
                if speech=='dialogue' and caps.get('native_lipsync') is not True:
                    issues.append('未核实入口原生对白口型能力')
                continue
            rid=use.get('record_id');a=records.get(rid)
            if not a or a['kind']!='voice' or rid not in r['depends_on']:
                issues.append('声音未绑定实际依赖');continue
            if record_review_status(a)!='adopted':issues.append('声音尚未采用：'+rid)
            v=a['data'];source=v.get('source_type','synthesized')
            if source not in ('synthesized','recorded','licensed'):issues.append('未知声音来源：'+rid)
            if source=='synthesized' and not (v.get('voice_id') or v.get('source_evidence')):issues.append('合成声音缺少声线标识或来源依据：'+rid)
            if source!='synthesized' and not v.get('source_evidence'):issues.append('录音缺少来源依据：'+rid)
            if not v.get('text') or not v.get('adoption_evidence') or not a['files'] or is_stale(doc,a,root) or rid not in current_ids:issues.append('声音缺少台词、采用或有效文件：'+rid)
            vd=v.get('source_duration',v.get('duration_seconds'))
            audio_files=[f for f in a['files'] if Path(f['path']).suffix.lower() in ('.wav','.mp3','.m4a','.aac','.flac','.ogg')]
            chosen=use.get('file_path')
            matches=[f for f in audio_files if f['path']==chosen] if chosen else audio_files
            if len(matches)!=1:issues.append('声音使用须唯一选择实际文件：'+rid)
            else:
                try:
                    out=subprocess.run(['ffprobe','-v','error','-show_entries','format=duration','-of','json',str(local_file(root,matches[0]['path']))],capture_output=True,text=True,check=True,timeout=15)
                    measured=float(json.loads(out.stdout)['format']['duration'])
                    if type(vd) not in (int,float) or not math.isfinite(measured) or abs(measured-vd)>0.05:issues.append('声音声明时长与实测不符：'+rid)
                except (OSError,ValueError,KeyError,subprocess.SubprocessError):issues.append('声音文件无法实测：'+rid)
            begin=use.get('source_in',0);stop=use.get('source_out',vd);at=use.get('start',0)
            valid=all(type(x) in (int,float) and math.isfinite(x) for x in (vd,begin,stop,at))
            if not valid or not (0<=begin<stop<=vd and at>=0):issues.append('声音源时长或采用区间无效：'+rid);continue
            if type(duration) in (int,float) and at+stop-begin>duration:issues.append('采用音频超出视频播放窗口：'+rid)
            if method=='native_recording':
                if rid not in voice_ids:issues.append('原生音频未在实际上传中：'+rid)
                if caps.get('preserves_recording') is not True or not caps.get('evidence'):issues.append('未核实入口保留采用录音')
                if speech=='dialogue' and caps.get('native_lipsync') is not True:issues.append('未核实入口直接完成口型同步')
                if (begin!=0 or stop!=vd) and (caps.get('supports_audio_range') is not True or not use.get('range_evidence')):issues.append('未核实原生入口的音频片段消费：'+rid)
            elif method in ('post_lipsync','external_overlay'):
                if speech=='dialogue' and method=='external_overlay':issues.append('贴音不能代替画内对白口型')
                if not use.get('handoff') or not use.get('authorization_evidence'):issues.append('后续声音工序缺少交接或授权依据：'+rid)
            else:issues.append('未知音频实现方式：'+str(method))
    issues.extend(sound_issues(doc,r))
    try:
        review=d.get('prompt_review')
        payload=delivery_input(doc,r,root)
        if not isinstance(review,dict):issues.append('缺少本版出稿复核记录')
        else:
            if review.get('prompt')!=d.get('prompt'):issues.append('复核正文与实际交付正文不一致')
            if review.get('input_sha256')!=digest(payload):issues.append('出稿复核未绑定当前附件、模式、参数与声音计划')
            actual=[x['label'] for x in payload['references']]
            if [x.get('id') for x in review.get('reference_policy',[]) if isinstance(x,dict)]!=actual:issues.append('复核参考与实际上传顺序不一致')
            for ref,policy in zip(payload['references'],review.get('reference_policy',[])):
                ext=Path(ref['file_path']).suffix.lower()
                media='audio' if ext in ('.wav','.mp3','.m4a','.aac','.flac','.ogg') else 'video' if ext in ('.mp4','.mov','.mkv','.webm') else 'image' if ext in ('.png','.jpg','.jpeg','.webp','.gif') else 'other'
                if policy.get('type')!=media:issues.append('复核媒体类型与实际文件不符：'+ref['label'])
                if media=='audio' and Path(policy.get('audio_contract',{}).get('file','')).resolve()!=local_file(root,ref['file_path']):issues.append('音频规格复核未绑定实际文件：'+ref['label'])
            issues.extend(prompt_guard.inspect(review, expected_shot_ids=expected)['errors'])
    except (ValueError,OSError,TypeError,KeyError) as e:issues.append('出稿输入无法验证：'+str(e))
    return list(dict.fromkeys(issues))

def global_audio_bans(prompt):
    """Recognize narrow, unambiguous sound bans; scoped prose remains a semantic review.

    ponytail: this is not a natural-language sound planner. Only whole-video directives
    and unscoped opening directives become errors; ambiguous exceptions stay unclassified.
    """
    # A character's words or a quoted example are not instructions to the generator.
    quoted=r'“[^”]*”|‘[^’]*’|「[^」]*」|『[^』]*』|"[^"\n]*"'
    clean=re.sub(quoted,lambda match:' '*len(match.group()),prompt).replace('**','')
    opening=prompt_guard._opening(clean)
    local=r'镜头\s*[一二三四五六七八九十\d]+|第[一二三四五六七八九十\d]+(?:镜|段)|SH\d+|开头|开场|片尾|结尾|前\s*\d+(?:\.\d+)?\s*秒|\d+(?:\.\d+)?\s*[-–~至]\s*\d+(?:\.\d+)?\s*(?:秒|s\b)|(?:shot|scene)\s*\d+|\b(?:intro|outro|first|last|beginning|ending)\b'
    scoped_opening=bool(re.search(local,clean[:clean.find(opening)]+opening,re.I))
    roles={'音乐':{'music'},'配乐':{'music'},'背景音乐':{'music'},'背景配乐':{'music'},'bgm':{'music'},
           'music':{'music'},'background music':{'music'},'对白':{'dialogue'},'对话':{'dialogue'},'台词':{'dialogue'},
           'dialogue':{'dialogue'},'dialog':{'dialogue'},'旁白':{'narration'},'解说':{'narration'},
           'narration':{'narration'},'voiceover':{'narration'},'voice-over':{'narration'},
           '人声':{'dialogue','narration'},'配音':{'dialogue','narration'},'speech':{'dialogue','narration'},'voices':{'dialogue','narration'}}
    scope=r'^(?:全片|全程|整部(?:视频|影片|作品)|整条(?:视频|影片)|整个(?:视频|影片)|本片|本视频|本次生成(?:的)?(?:视频)?|throughout (?:the )?(?:video|film)|(?:the )?(?:entire|whole) (?:video|film))\s*[:：,，]?\s*'
    negative=r'^(?:不生成|不加入|不添加|不播放|不得(?:生成|加入|添加|播放|出现|有)?|禁止(?:生成|加入|添加|播放|出现)?|不要(?:生成|加入|添加|播放|出现)?|没有|无)\s*(?:任何|一切|全部)?\s*(.+)$'
    english=r"^(?:no|without|do not (?:generate|add|include|play)|don't (?:generate|add|include|play))\s+(?:(?:any|all)\s+)?(.+)$"
    bans=set()
    for sentence in re.split(r'[。！？!?;；\n]+',clean):
        if re.search(r'除.{0,24}外|除了|除外|仅在|只有|\b(?:except|unless)\b',sentence,re.I):continue
        # Treat a scope prefix and its following comma as one directive.
        sentence=re.sub(scope,lambda match:match.group().rstrip(' ,，:：')+' ',sentence.strip(),flags=re.I)
        for clause in re.split(r'[，,]',sentence):
            clause=clause.strip(' \t-•').rstrip('.')
            clause=re.sub(r'^(?:声音(?:要求|规则)?|音频(?:要求|规则)?|sound|audio)\s*[:：]\s*','',clause,flags=re.I)
            match=re.match(scope,clause,re.I)
            if match:directive=clause[match.end():]
            elif clause and clause in opening and not scoped_opening and not re.search(local,sentence,re.I):directive=clause
            else:continue
            ban=re.match(negative,directive) or re.match(english,directive,re.I)
            if not ban:continue
            names=[re.sub(r'\s+',' ',name.strip().lower()) for name in re.split(r'\s*(?:、|和|与|及|或|/|\band\b|\bor\b)\s*',ban.group(1),flags=re.I)]
            if names and all(name in roles for name in names):
                for name in names:bans.update(roles[name])
    return bans


def sound_issues(doc,r):
    d=r['data'];scope=d.get('output_scope',{});issues=[]
    count=scope.get('video_count') if isinstance(scope,dict) else None
    if type(count) is not int or count<1 or not scope.get('evidence'):
        return ['须声明本次制作最终生成的视频条数及范围依据']
    if scope.get('part_of_multi_video') is True:count=max(2,count)
    records={x['id']:x for x in state(doc)['records']}
    choice=records.get(d.get('production_path_decision_id'),{}).get('data',{}).get('output_scope')
    if choice!=scope:issues.append('声音范围须与本批投产决定一致，拆包不得缩小范围')
    plan=d.get('sound_plan',{})
    policy='single_video' if count==1 and not isinstance(d.get('repair_context'),dict) else 'effects_only'
    if plan.get('policy')!=policy:issues.append('声音策略与最终视频条数不一致')
    tracks=plan.get('tracks',[])
    if not isinstance(tracks,list):return issues+['声音声部须为列表']
    # Catch explicit contradictions, not a general keyword-based semantic verdict.
    # Absence of a planned track is not permission to silence every track.
    prompt=d.get('prompt','')
    silent=False
    for match in re.finditer(r'(?:全片|整段|整个视频|本片|视频|画面|本次生成)\s*(?:为|保持|采用|是)?\s*静音|(?:silent video|mute all audio|no sound at all)',prompt,re.I):
        before=prompt[max(0,match.start()-12):match.start()]
        if not re.search(r'(?:不(?:要|应|要求|强制|必|能|得)(?:让|把|将)?|禁止|避免|not(?: a)?|never)\s*$',before,re.I):silent=True
    no_sfx=bool(re.search(r'(?:不生成|禁止|不要|无)(?:(?:任何|全部|一切|对白|旁白|配音|台词|音乐|配乐|人声|环境声|环境铺底)|[、，,或及和与\s])*(?:音效|所有声音)(?=[。；，,、\n]|$)|no\s+(?:sound effects|sfx|audio)',prompt,re.I))
    native_sfx=any(isinstance(t,dict) and t.get('role')=='sfx' and t.get('implementation')=='native' for t in tracks)
    native_speech=any(isinstance(t,dict) and t.get('role') in ('dialogue','narration') and t.get('implementation')=='native' for t in tracks)
    if silent and not plan.get('silence_evidence'):
        issues.append('正文要求全静音，但没有本作品的静默选择依据；未安排对白不等于禁止音效')
    if native_sfx and (silent or no_sfx):issues.append('正文禁止音效，与已定原生动作音效冲突')
    if native_speech and silent:issues.append('正文全静音，与已定原生人声冲突')
    bans=global_audio_bans(prompt)
    for role,label in (('music','音乐'),('dialogue','对白'),('narration','旁白')):
        native=any(isinstance(t,dict) and t.get('role')==role and t.get('implementation')=='native' for t in tracks)
        if native and (role in bans or (role=='music' and silent)):
            issues.append('正文全片禁止'+label+'，与声音计划中已定的原生'+label+'冲突')
    if policy=='effects_only' and any(t.get('role') in ('music','ambience') and t.get('implementation')=='native' for t in tracks if isinstance(t,dict)):
        issues.append('多条视频素材或局部替换镜头禁止原生生成音乐和环境铺底')
    for t in tracks:
        if not isinstance(t,dict) or t.get('role') not in ('dialogue','narration','sfx','ambience','music') or t.get('implementation') not in ('native','external','none'):
            issues.append('无效声音声部');continue
        if not t.get('description'):issues.append('声音声部缺少用途说明')
    if any(isinstance(u,dict) and u.get('implementation')=='native_generation' for u in d.get('audio_uses',[]) or []):
        roles={'dialogue'} if d.get('speech')=='dialogue' else {'dialogue','narration'}
        if not any(isinstance(t,dict) and t.get('role') in roles and t.get('implementation')=='native' for t in tracks):
            issues.append('原生人声未列入本次声音计划')
    if policy=='single_video' and any(t.get('role')=='music' and t.get('implementation')=='native' for t in tracks if isinstance(t,dict)):
        caps=d.get('audio_capability',{})
        if caps.get('native_music') is not True or not caps.get('evidence'):issues.append('单条视频的原生音乐能力尚未核实')
    return issues

def package_warnings(doc,r,root):
    expected=[x[-1]['id'] for x in selected_shots(doc,r['shot_ids'])]
    review=prompt_guard.inspect(r['data'].get('prompt_review',{}),expected_shot_ids=expected)
    return [*review.get('review_signals',[]),
            *({'kind':'unverified_join',**join} for join in review.get('unverified_joins',[]))]

def delivery_input(doc,r,root):
    """Exact outgoing input, excluding the review itself. No semantic claims are inferred."""
    d=r['data'];records={x['id']:x for x in state(doc)['records']};refs=[]
    for ref in d.get('references',[]):
        a=reference_record(records,d,ref['record_id'])
        refs.append({**ref,'version':a['version'],'sha256':file_digest(root,ref['file_path'])})
    keys=('prompt','platform','model','mode','parameters','timeline','speech','audio_uses',
          'audio_capability','output_scope','sound_plan','input_mode','source_range','review_basis','repair_context')
    receipt={k:d.get(k) for k in ('sequence_review_id','sequence_review_version','content_timeline','generation_handles') if d.get(k) is not None}
    return {**{k:d.get(k) for k in keys},**receipt,'references':refs,'shot_ids':r['shot_ids'],'dependencies':[{ 'id':rid,'version':records[rid]['version'],'files':[{**f,'sha256':file_digest(root,f['path'])} for f in records[rid]['files']]} for rid in r['depends_on']]}

def video_adopted_shots(doc,root):
    records={x['id']:x for x in state(doc)['records']};result=set()
    for r in active_records(doc):
        d=r.get('data',{})
        if r['kind']!='result' or d.get('status') not in ('adopted','partially_adopted') or record_review_status(r)!='adopted':continue
        if not any(Path(f['path']).suffix.lower() in ('.mp4','.mov','.mkv','.webm') for f in r['files']):continue
        pkg=records.get(d.get('package_id'),{})
        pkg=next((v for v in [pkg]+pkg.get('history',[]) if v.get('version')==d.get('package_version')),None)
        if d.get('source_type')=='external':
            if is_stale(doc,r,root):continue
        elif not pkg or is_stale(doc,pkg,root):continue
        if any(not shot_confirmed(doc,sid) for sid in r['shot_ids']):continue
        try:
            if any(file_digest(root,f['path'])!=f['sha256'] for f in r['files']):continue
        except (ValueError,OSError):continue
        result.update(d['adopted_shot_ids'] if d['status']=='partially_adopted' else r['shot_ids'])
    return result

def history_markdown(doc,root,render_storyboard):
    p=state(doc)
    if not p['confirmations']:return None
    lines=['# '+doc['title']+' · 素材制作文档','', '> 分镜只在工作台修改；本文件由确认稿及制作记录生成。保存推敲稿不等于确认。','']
    current=sections(doc)
    order=list(current)+[sid for sid in p['confirmations'] if sid not in current]
    rendered_records=set();rendered_contexts=set()
    for sid in order:
        c=p['confirmations'].get(sid)
        if not c:
            lines+=['## '+current[sid]['title'],'','待确认，尚未进入正式制作。',''];continue
        status=confirmation_status(doc,sid)
        frozen={'schema_version':1,'id':doc['id'],'revision':c['source_revision'],**c['context'], 'sections':[c['snapshot']],'suggestions':[],'prompts':[]}
        rendered=render_storyboard(frozen).rsplit('## 修改建议',1)[0]
        # Reuse complete two-table export, without a second document title.
        rendered=rendered[rendered.index('## '):]
        lines += [rendered]
        context_id=digest(c['context'])
        if context_id not in rendered_contexts:
            lines += ['采用的创作说明：'+c['context']['brief'], '']
            rendered_contexts.add(context_id)
        lines += [f"确认依据：{c['evidence']} · 来源修订 {c['source_revision']}",
                  '当前编辑稿已变化或段落已删除，以下仍为上次确认稿；受影响内容需复核，原制作许可与未受影响部分继续有效。' if status!='confirmed' else '本段分镜已确认。','']
        for r in p['records']:
            if sid not in r['section_ids']:continue
            anchor='record-'+hashlib.sha256(r['id'].encode()).hexdigest()[:16]
            if r['id'] in rendered_records:
                lines += [f"共用{LABELS[r['kind']]}：[参见 {r['title']}](#{anchor})",'']
                continue
            rendered_records.add(r['id'])
            stale=is_stale(doc,r,root)
            lines += [f'<a id="{anchor}"></a>','']
            lines+=['### '+LABELS[r['kind']]+'：'+r['title'],'',f"记录 {r['id']} · 版本 {r['version']}"+(' · 依据变化，需复核（历史结果保留）' if stale else ''),'',r['body'],'']
            for f in r['files']:
                try:
                    target=local_file(root,f['path'])
                except ValueError:
                    lines.append('历史附件迁移后的字节已变化，须回查文件迁移记录；不作为当前可用素材：'+f['path'])
                    continue
                lines.append(f"- [{f['role']}：{target.name}]({quote(str(target),safe='/')})")
            lines+=['']
            if r['kind']=='package':
                issues=package_issues(doc,r,root)
                lines+=['投产检查：'+('；'.join(issues) if issues else '声明项与本地文件检查通过；实际入口能力与生成效果仍须核验。'),'']
                lines+=['**完整视频提示词**','',r['data'].get('prompt',''),'']
            # All provider-specific parameters and evidence remain inspectable, never credentials.
            lines+=['<details><summary>完整参数、素材映射与记录</summary>','', '```json',json.dumps(r['data'],ensure_ascii=False,indent=2,allow_nan=False),'```','','</details>','']
    return '\n'.join(lines)+'\n'


def production_markdown(doc,root,render_storyboard):
    """Human reading view. Snapshots and full records remain in the audit export."""
    p=state(doc)
    if not p['confirmations']:return None
    superseded=set()
    for r in p['records']:
        superseded.update(r.get('data',{}).get('supersedes',[]))
    records=[r for r in p['records'] if r['id'] not in superseded]
    lines=['# '+doc['title']+' · 素材制作文档','',
           f'> 修订 {doc["revision"]} · 当前分镜与采用素材。待确认内容仅供审阅，不自动成为投产依据。','']
    if doc.get('source_text'):lines += ['## 对应原文','',doc['source_text'],'']
    lines += [doc['brief'],'','[制作记录与历史确认](制作记录.md) · [工作台数据](storyboard.json)','']
    rendered=set();adopted_ids=video_adopted_shots(doc,root)
    for sec in doc['sections']:
        sid=sec['id'];status=confirmation_status(doc,sid)
        if sid in cancelled_sections(doc):
            label='**无需制作 · 历史分镜。** 取消决定仍有效。'
        elif set(shot_ids(sec)) and set(shot_ids(sec))<=adopted_ids:
            label='**本段视频素材已采用。** 下表为当前镜头说明，采用文件见本节记录。'
        elif set(shot_ids(sec)) & adopted_ids:
            label='**部分镜头视频素材已采用。** 其余镜头仍待修订或验收；不代表整段成片完成。'
        elif status=='confirmed':
            label=f'**分镜已确认。** 来源修订 {p["confirmations"][sid]["source_revision"]}。'
        elif set(shot_ids(sec)) & permission_shots(doc):
            label='**本轮修订稿，沿当前制作继续。** 原确认快照保留；内容修改不重置阶段与许可。'
        else:
            label='**当前编辑稿，待确认。** 历史确认稿保留在制作记录中。'
        lines+=['## '+sec['title'],'',label,'',sec['notes'],'']
        def cell(value):
            return html.escape(str(value),quote=False).replace('|','&#124;').replace('\n','<br>') or '—'
        for group in sec['groups']:
            lines += ['### '+group['title'],'',group['notes'],'',
                      '| 镜号 | 时长（秒） | 画面与动作 |','| --- | --- | --- |']
            for shot in group['shots']:
                lines += ['| '+cell(shot['number'])+' | '+cell(shot['duration'] if shot['duration'] is not None else '待定')+' | '+cell(shot['content'])+' |']
            lines += ['']
            for shot in group['shots']:
                lines += ['<details><summary>'+html.escape(shot['number'])+' · 构图、声音与制作细节</summary>','']
                for key,label in [('framing','构图'),('camera','运镜'),('sound','声音与原文'),('start','起始'),('end','结束'),('transition','衔接'),('assets','素材'),('reason','观看意图'),('notes','制作说明')]:
                    if shot.get(key):lines += ['**'+label+'：** '+cell(shot[key]),'']
                lines += ['</details>','']
        for r in records:
            if sid not in r['section_ids']:continue
            anchor='record-'+hashlib.sha256(r['id'].encode()).hexdigest()[:16]
            if r['id'] in rendered:
                lines += [f"共用资料：[参见 {r['title']}](#{anchor})",''];continue
            rendered.add(r['id'])
            lines += [f'<a id="{anchor}"></a>','', '### '+r['title'],'',r['body'],'']
            if r.get('data',{}).get('decision_type')=='generation_recommendation':
                basis=r['data'].get('selection_basis')
                if basis:
                    status={'supported':'推荐依据','provisional':'暂定推荐依据','user_specified':'用户指定方案依据'}[basis['status']]
                    lines += ['**'+status+'**','', '本段重点：'+cell('；'.join(basis['priorities'])),'']
                    for key,label in [('comparison','与备选的区别'),('cost','整体制作成本'),('uncertainty','仍未确定')]:
                        lines += [label+'：'+cell(basis[key]),'']
                for option in r['data'].get('options',[]):
                    lines += ['- '+cell(option.get('label') or option.get('id') or option.get('path'))+'：'+cell(' / '.join(str(option.get(k) or '') for k in ('model','platform','input_mode')))+'；'+cell(option.get('reason',''))+'；输入：'+cell(option.get('inputs',''))+'；限制：'+cell(option.get('limits','')),'']
                evidence=r['data'].get('method_evidence',{})
                if evidence:lines += ['制作依据：'+cell(evidence.get('status'))+'；'+cell(evidence.get('summary')),'']
            if r.get('data',{}).get('decision_type')=='production_path':
                lines += ['当前选择：'+cell(' / '.join(str(r['data'].get(k) or '') for k in ('path','model','platform','input_mode')))+'；'+('方案已选，阶段与提交权限另计。' if r['data'].get('planning_only') else '沿当前制作范围执行。'),'']
            if r['kind']=='result':
                d=r['data'];lines += ['结果状态：'+str(d.get('status','待核查'))+('；已采用镜头：'+', '.join(d.get('adopted_shot_ids',[])) if d.get('status')=='partially_adopted' else ''),'']
            if r['kind'] in ('asset','grid','voice','previs','package') and is_stale(doc,r,root):
                lines += ['制作依据已变化，使用前需复核；历史采用证据仍保留。','']
            for asset in r['files']:
                target=local_file(root,asset['path'])
                lines.append(f"- [{target.name}]({quote(str(target),safe='/')})")
            lines += ['']
            if r['kind']=='package':
                lines += ['**本包完整提示词**','',r['data'].get('prompt',''),'',
                          '投产检查：'+('；'.join(package_issues(doc,r,root)) or '本地声明检查通过，动态效果仍需验收。'),'']
    return '\n'.join(lines)+'\n'

def record_states(doc, root):
    active = {r['id'] for r in active_records(doc)}
    result = {}
    for record in state(doc)['records']:
        status = record_review_status(record) if record['id'] in active else 'excluded'
        stale = is_stale(doc,record,root) if status != 'excluded' else False
        result[record['id']] = {'status': status, 'stale': stale,
            'display_status': 'needs_review' if stale and status != 'excluded' else status}
        if record.get('data',{}).get('decision_type')=='sequence_review' and status!='excluded':
            result[record['id']]['display_status']='review_completed_with_changes' if stale else 'review_completed'
    return result


def preview_rows(doc,root):
    with evaluation():
        return _preview_rows(doc,root)

def ordered_state_images(images):
    """Keep image consumers in the same order without inventing missing evidence.

    The boolean marks a complete explicit order. Endpoint placement alone does
    not resolve an ambiguous multi-record sequence with intermediate states.
    """
    images=list(images)
    if len(images)<2:return images,True
    orders=[image.get('sequence_order') for image in images]
    if all(type(order) in (int,float) and math.isfinite(order) for order in orders) and len(set(orders))==len(orders):
        ordered=sorted(images,key=lambda image:image['sequence_order']);explicit=True
    else:
        endpoints={'state_start':0,'start_frame':0,'state_end':2,'end_frame':2}
        ranks=[endpoints.get(image.get('moment'),1) for image in images]
        # Python's stable sort preserves the original order of unlabelled states.
        ordered=sorted(images,key=lambda image:endpoints.get(image.get('moment'),1))
        explicit=len(images)==2 and set(ranks)=={0,2}
    adopted=[image for image in ordered if image.get('review_status')=='adopted']
    if 1<len(adopted)<len(ordered):
        # Unplaced alternatives must not reverse the adopted-only rehearsal.
        selected,_=ordered_state_images(adopted)
        replacements=iter(selected)
        ordered=[next(replacements) if image.get('review_status')=='adopted' else image for image in ordered]
    return ordered,explicit

def _preview_rows(doc,root):
    rows=[];cancelled=cancelled_sections(doc)
    available=[]
    for r in active_records(doc):
        data=r['data'];status=record_review_status(r)
        if status=='excluded':continue
        if r['kind']=='decision' and data.get('decision_type')=='static_exploration':
            if status in ('candidate','revise'):available.append((r,status,is_stale(doc,r,root)))
        elif r['kind']=='asset' and data.get('asset_role')=='storyboard_frame' or r['kind']=='grid':
            if status in ('candidate','adopted','revise'):available.append((r,status,is_stale(doc,r,root)))
    for sec in doc['sections']:
        for group in sec['groups']:
            for shot in group['shots']:
                options={}
                for r,status,stale in available:
                    if shot['id'] not in r['shot_ids']:continue
                    for index,f in enumerate(r['files']):
                        if Path(f['path']).suffix.lower() not in ('.png','.jpg','.jpeg','.webp','.gif'):continue
                        role=f.get('role','').lower()
                        if role.startswith(('process','historical','rejected')):continue
                        if r['kind']=='decision' and 'candidate' not in role:continue
                        moment=f.get('moment') or r['data'].get('moment') or (role if role in ('state_start','state_end','start_frame','end_frame') else '')
                        item={'record_id':r['id'],'file_index':index,'title':r['title'],'path':f['path'],
                              'review_status':'needs_review' if stale else status,'adoption_status':status,
                              'moment':moment,'sequence_order':f.get('sequence_order'),'stale':stale}
                        if stale:item['reason']='镜头或实际输入已变化，原图与采用历史保留，当前用途待复核。'
                        if r['kind']=='grid':
                            cell=next((c for c in r['data'].get('cells',[]) if c.get('shot_id')==shot['id']),None)
                            if not cell:continue
                            problems=grid_issues(r,root,f['path'])
                            if problems:
                                item['review_status']='needs_review';item['reason']='；'.join(problems)
                            else:item['box']=cell['box'];item['size']=image_size(local_file(root,f['path']))
                        key=(f['path'],moment)
                        priority={'adopted':4,'candidate':3,'revise':2,'needs_review':1}
                        if key not in options or priority.get(item['review_status'],0)>priority.get(options[key]['review_status'],0):options[key]=item
                images,_=ordered_state_images(options.values())
                status='adopted' if any(i['review_status']=='adopted' for i in images) else 'candidate' if any(i['review_status']=='candidate' for i in images) else 'needs_review' if images else 'missing'
                rows.append({'shot_id':shot['id'],'number':shot['number'],'section_id':sec['id'],'section':sec['title'],'content':shot['content'],
                             'status':'cancelled' if sec['id'] in cancelled else status,'images':[] if sec['id'] in cancelled else images})
    return rows


def next_actions(doc, root, sec, phase, related, adopted):
    ids=set(shot_ids(sec));actions=[]
    plans=[r for r in active_records(doc) if r.get('data',{}).get('decision_type')=='generation_recommendation'
           and record_review_status(r)!='excluded' and ids.intersection(r['shot_ids'])]
    current={sid for r in plans if not is_stale(doc,r,root) for sid in r['shot_ids']}
    routes=current_routes(doc)
    missing=ids-current
    if missing:
        actions.append({'code':'assess_route','shot_ids':sorted(missing),
            'text':'评估或同步受影响范围的模型、平台、输入方式与素材缺口；复用有效依据，已有选择不自动撤销。'})
    if ids <= adopted:
        actions.append({'code':'adopted','text':'当前范围已有采用视频，按用户反馈处理；已定超分选择不重复询问。'})
    elif phase==0:
        actions.append({'code':'design','text':'完善当前文字与拍法，连同路线和素材建议一起呈现；已有决定直接沿用。'})
    elif phase==1:
        if any(row['status']!='adopted' for row in related):
            actions.append({'code':'inputs','text':'按已选方式补齐或修订必要输入；无图路径无需出图，变更只更新实际依赖，不退回重新确认。'})
        elif not sequence_receipt(doc,{'section_ids':[sec['id']]}):
            actions.append({'code':'sequence_review','text':'图稿已采用，完成本批尚未进行的一次整段预演与审查。'})
        else:
            actions.append({'code':'prepare','text':'沿有效方案准备准确视频输入；人工修订不重启整段审查。'})
    else:
        actions.append({'code':'prepare_or_review','text':'准备或同步准确输入；已有生成任务则核对实际结果。沿已定提交分工，不重复提交。'})
    if phase and any(sid not in routes or record_review_status(routes[sid])=='excluded' for sid in ids):
        actions.append({'code':'select_route','text':'仅补尚未选择或新控制需求涉及的路线，不重选无关范围。'})
    return actions


def workflow_status(doc, root, rows=None):
    """A view of scoped work, never a second authorization state machine."""
    rows = preview_rows(doc,root) if rows is None else rows
    by_shot = {row['shot_id']:row for row in rows}
    image_scope = permission_shots(doc,'image_stage_entry')
    route_scope = permission_shots(doc,'production_path')
    video_scope = route_scope | permission_shots(doc,'video_preparation_entry')
    entered_images={sid for r in active_records(doc) if is_permission(r) and record_review_status(r)!='excluded'
                    and r['data'].get('selection_evidence') for sid in r['section_ids']}
    entered_video={sid for r in active_records(doc) if is_permission(r) and r['data'].get('decision_type') in ('production_path','video_preparation_entry')
                   and record_review_status(r)!='excluded' and r['data'].get('selection_evidence') for sid in r['section_ids']}
    entered_video.update(sid for r in active_records(doc) if r['kind'] in ('package','task','result') and record_review_status(r)!='excluded' for sid in r['section_ids'])
    adopted_videos=video_adopted_shots(doc,root)
    scopes=[]
    for sec in doc['sections']:
        if sec['id'] in cancelled_sections(doc):continue
        ids=set(shot_ids(sec))
        if not ids:continue
        related=[by_shot[sid] for sid in ids if sid in by_shot]
        ready=sum(row['status']=='adopted' for row in related)
        review=sum(row['status']=='needs_review' for row in related)
        phase=2 if sec['id'] in entered_video else 1 if sec['id'] in entered_images or any(row['images'] for row in related) else 0
        if phase==0:
            title='文字分镜已确认' if all(shot_confirmed(doc,sid) for sid in ids) else '文字分镜讨论'
            detail='已有范围决定直接沿用；只处理本次仍缺少的制作选择。'
        elif phase==1:
            title='图稿修订与审阅' if review or confirmation_status(doc,sec['id'])=='changed' else '图片资产与分镜图'
            detail=f'{ready}/{len(ids)} 镜有当前采用图；局部修改在本阶段完成，已有制作许可继续有效。'
            receipt=sequence_receipt(doc,{'section_ids':[sec['id']]})
            if receipt:
                title='整段审查已完成 · 生成方式选择'
                detail='人工调整只同步相关图稿、生成建议和输入，不重新启动审查；已有路线选择继续沿用。'
            elif ready==len(ids):
                title='图稿已采用 · 助手整段预演与生成建议'
                detail='助手完成本批一次整段图序审查，并在工作台给出生成方式建议，无需再次授权检查。'
        else:
            title='视频制作与返修'
            detail=f'路线已覆盖 {len(ids & route_scope)}/{len(ids)} 镜；输入变更只复核相关素材和交接。'
        if ids <= adopted_videos:
            phase=2;title='视频素材已采用';detail='当前范围已有采用结果；可选超分不影响原片完成。'
        scopes.append({'section_id':sec['id'],'title':sec['title'],'phase':phase,'status':title,'detail':detail,
                       'ready_shots':ready,'review_shots':review,'shot_count':len(ids),
                       'next_actions':next_actions(doc,root,sec,phase,related,adopted_videos)})
    phase=max((s['phase'] for s in scopes),default=0)
    mixed=len({s['phase'] for s in scopes})>1
    title='各段分别推进' if mixed else scopes[0]['status'] if len(scopes)==1 else ('文字分镜','图片资产与分镜图','视频制作与返修')[phase]
    return {'phase':phase,'title':title,'detail':'各范围的决定独立沿用，不由未完成段落阻挡其他段落。' if mixed else scopes[0]['detail'] if scopes else '从本次目标开始，复用已有输入。','scopes':scopes}
