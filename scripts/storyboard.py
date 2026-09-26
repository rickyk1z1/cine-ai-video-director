#!/usr/bin/env python3
"""Local storyboard store, CLI and loopback editor. Python standard library only."""
import argparse
import copy
import hashlib
import html
import json
import math
import os
from pathlib import Path
import secrets
import tempfile
from contextlib import contextmanager, nullcontext
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs, unquote
import uuid
import sys
sys.dont_write_bytecode = True
import production
import rehearsal
import coordination
import reference_search
import pacing
from file_lock import exclusive_lock
import shutil
import subprocess
import threading
import time
import urllib.request
import urllib.error

SHOT_FIELDS = ('number','content','framing','camera','sound','start','end','transition','assets','reason','notes')
ROOT = Path(__file__).resolve().parent.parent
ATLAS_FILES={'index.html':'text/html; charset=utf-8','app.js':'text/javascript; charset=utf-8',
             'style.css':'text/css; charset=utf-8','full-page.css':'text/css; charset=utf-8','atlas-data.js':'text/javascript; charset=utf-8',
             'atlas.json':'application/json; charset=utf-8','glossary.md':'text/markdown; charset=utf-8',
             '视觉风格图鉴.md':'text/markdown; charset=utf-8'}
ATLAS_IMAGES={'.png':'image/png','.jpg':'image/jpeg','.jpeg':'image/jpeg','.webp':'image/webp',
              '.gif':'image/gif','.avif':'image/avif'}

def atlas_file(name):
    """Only bundled atlas files and raster images; never follow directory/file links."""
    parts=name.split('/')
    if not name or '\\' in name or '\0' in name or any(part in ('','.','..') for part in parts):return None
    ctype=ATLAS_FILES.get(name)
    if ctype is None:
        if len(parts)<2 or parts[0]!='images':return None
        ctype=ATLAS_IMAGES.get(Path(parts[-1]).suffix.lower())
        if ctype is None:return None
    root=ROOT/'assets/visual-style-atlas'
    target=root
    if root.is_symlink():return None
    for part in parts:
        target=target/part
        if target.is_symlink():return None
    if not target.is_file() or not target.resolve().is_relative_to(root.resolve()):return None
    return target,ctype

def runtime_signature():
    names=['SKILL.md','scripts/storyboard.py','scripts/production.py','scripts/prompt_guard.py','scripts/rehearsal.py','scripts/file_lock.py',
           'assets/app.js','assets/workspace.js','assets/style.css','assets/index.html',
           'scripts/coordination.py','scripts/reference_search.py','scripts/pacing.py','assets/reference-sources.json']
    signature=hashlib.sha256(b''.join((ROOT/name).read_bytes() for name in names))
    # Image bytes are served on demand; page, code and data changes restart the runtime.
    for name in sorted(ATLAS_FILES):
        entry=atlas_file(name)
        if entry:signature.update(name.encode()+b'\0'+entry[0].read_bytes())
    return signature.hexdigest()

BUILD_ID = runtime_signature()

def runtime_info():
    current=runtime_signature()
    return {'build_id':BUILD_ID,'disk_build_id':current,'current':BUILD_ID==current}

class Conflict(Exception):
    pass

_MISSING = object()

def editable(doc):
    return {k:copy.deepcopy(v) for k,v in doc.items() if k not in ('production','workspace','revision') and not k.startswith('_')}

def merge_edits(base, local, current, path='分镜'):
    """Merge disjoint edits by stable IDs; overlapping edits stay explicit conflicts."""
    def duplicate(value):
        return _MISSING if value is _MISSING else copy.deepcopy(value)
    if local == base:return duplicate(current)
    if current == base or local == current:return duplicate(local)
    if all(isinstance(v,dict) for v in (base,local,current)):
        result={}
        for key in dict.fromkeys([*base,*current,*local]):
            value=merge_edits(base.get(key,_MISSING),local.get(key,_MISSING),current.get(key,_MISSING),path+'/'+key)
            if value is not _MISSING:result[key]=value
        return result
    if all(isinstance(v,list) for v in (base,local,current)) and all(isinstance(x,dict) and isinstance(x.get('id'),str) for v in (base,local,current) for x in v):
        orders=[[x['id'] for x in v] for v in (base,local,current)]
        if orders[1]==orders[0]:order=orders[2]
        elif orders[2]==orders[0] or orders[1]==orders[2]:order=orders[1]
        else:raise Conflict('双方都调整了顺序或结构：'+path)
        maps=[{x['id']:x for x in v} for v in (base,local,current)]
        values={}
        for key in set().union(*(m.keys() for m in maps)):
            values[key]=merge_edits(*(m.get(key,_MISSING) for m in maps),path+'/'+key)
        return [values[key] for key in order if values[key] is not _MISSING]
    raise Conflict('同一内容有不同修改，已保留双方版本：'+path)

def uid():
    return uuid.uuid4().hex

def new_shot():
    return dict(id=uid(), duration=None, **{k:'' for k in SHOT_FIELDS})

def new_document(title):
    return dict(schema_version=1,id=uid(),title=title,source_text='',brief='',revision=0,
                sections=[],suggestions=[],prompts=[])

def nodes(doc):
    yield doc
    for section in doc['sections']:
        yield section
        for group in section['groups']:
            yield group
            yield from group['shots']

def validate(doc):
    if not isinstance(doc,dict) or doc.get('schema_version') != 1:
        raise ValueError('不支持的文档格式')
    production.validate_state(doc)
    workspace=doc.get('workspace',{})
    if not isinstance(workspace,dict):raise ValueError('workspace须为对象')
    if 'coordination' in workspace:coordination.validate(workspace['coordination'])
    if 'reference_sessions' in workspace:reference_search.validate(workspace['reference_sessions'])
    if 'style_choice' in workspace:
        choice=workspace['style_choice']
        if not isinstance(choice,dict) or not isinstance(choice.get('brief'),str):raise ValueError('视觉定调选择格式错误')
    ids=set()
    def check(obj, strings, arrays=()):
        if not isinstance(obj,dict) or not isinstance(obj.get('id'),str) or not obj['id'] or obj['id'] in ids:
            raise ValueError('对象标识缺失或重复')
        ids.add(obj['id'])
        for field in strings:
            if not isinstance(obj.get(field),str):
                raise ValueError('字段必须是文字：'+field)
        for field in arrays:
            if not isinstance(obj.get(field),list):
                raise ValueError('字段必须是列表：'+field)
    check(doc,('title','brief'),('sections','suggestions','prompts'))
    if not isinstance(doc.get('source_text',''),str):
        raise ValueError('字段必须是文字：source_text')
    if type(doc.get('revision')) is not int or doc['revision']<0:
        raise ValueError('无效修订号')
    for sec in doc['sections']:
        check(sec,('title','notes'),('groups',))
        for group in sec['groups']:
            check(group,('title','notes'),('shots',))
            for shot in group['shots']:
                check(shot,SHOT_FIELDS)
                d=shot.get('duration')
                if d is not None and (type(d) not in (int,float) or not math.isfinite(d) or d<0):
                    raise ValueError('时长须为空或非负有限数字')
    for item in doc['suggestions']:
        check(item,('target_id','problem','impact','status'))
        if item['status'] not in ('pending','accepted','ignored') or type(item.get('base_revision')) is not int:
            raise ValueError('无效建议状态或来源修订')
        if not isinstance(item.get('changes'),dict) or not item['changes']:
            raise ValueError('建议必须包含字段修改')
        for k,v in item['changes'].items():
            if k not in set(SHOT_FIELDS)|{'title','brief'} or not isinstance(v,str):
                raise ValueError('建议只支持文字字段修改：'+k)
    for item in doc['prompts']:
        check(item,('title','text','references','constraints'),('shot_ids',))
        if type(item.get('base_revision')) is not int or any(not isinstance(x,str) for x in item['shot_ids']):
            raise ValueError('无效提示词来源')
        if not item['shot_ids'] or len(set(item['shot_ids']))!=len(item['shot_ids']):
            raise ValueError('提示词须关联不重复的镜头标识')

def digest(value):
    return hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True).encode()).hexdigest()

def dependency(doc, item, kind):
    """Content dependencies, not the global revision: unrelated shots stay current."""
    index={x['id']:x for x in nodes(doc)}
    global_context={'title':doc['title'],'brief':doc['brief']}
    if doc.get('source_text'):global_context['source_text']=doc['source_text']
    if kind=='suggestion':
        target=index.get(item['target_id'])
        if target is None:
            return None
        context=[]
        for sec in doc['sections']:
            for group in sec['groups']:
                if target is group or any(target is s for s in group['shots']):
                    context.append([sec['id'],sec['title'],sec['notes']])
                if any(target is s for s in group['shots']):
                    context.append([group['id'],group['title'],group['notes']])
        if target is doc:
            target=global_context
        return digest({'target':target,'context':global_context,'ancestors':context})
    wanted=set(item['shot_ids'])
    ordered=[]
    for sec in doc['sections']:
        for group in sec['groups']:
            for shot in group['shots']:
                if shot['id'] in wanted:
                    ordered.append({'section':[sec['id'],sec['title'],sec['notes']],
                                    'group':[group['id'],group['title'],group['notes']], 'shot':shot})
    if len(ordered)!=len(wanted):
        return None
    return digest({'context':global_context,'shots':ordered})

def bind_derived(doc, old=None):
    for collection,kind in [('suggestions','suggestion'),('prompts','prompt')]:
        prior={x['id']:x for x in (old or {}).get(collection,[])}
        for item in doc[collection]:
            previous=prior.get(item['id'])
            fields=('target_id','changes','problem','impact') if kind=='suggestion' else ('shot_ids','title','text','references','constraints')
            unchanged=previous is not None and all(previous.get(k)==item.get(k) for k in fields)
            if unchanged:
                item['_dependency']=previous.get('_dependency')
                item['base_revision']=previous['base_revision']
            else:
                if item['base_revision'] != (old['revision'] if old else 0):
                    raise Conflict('新增或重写的建议/提示词必须依据当前修订')
                if kind=='suggestion':
                    target=next((x for x in nodes(doc) if x['id']==item['target_id']),{})
                    if any(k not in target or not isinstance(target[k],str) for k in item['changes']):
                        raise ValueError('建议修改字段不属于目标对象')
                item['_dependency']=dependency(doc,item,kind)
                if item['_dependency'] is None:
                    raise ValueError('建议或提示词引用不存在的对象')
            stale=dependency(doc,item,kind)!=item.get('_dependency') or item.get('_dependency') is None
            item['stale']=stale
            if kind=='prompt':
                item['status']='stale' if stale else 'current'
            elif not unchanged:
                item['status']='pending'
            else:
                item['status']=previous['status']

def atomic(path, text):
    if path.is_symlink():
        raise ValueError('拒绝覆盖符号链接：'+str(path))
    if path.exists() and path.read_text('utf8') == text:
        return
    fd,name=tempfile.mkstemp(prefix='.write-',dir=path.parent)
    try:
        with os.fdopen(fd,'w',encoding='utf8') as f:
            f.write(text); f.flush(); os.fsync(f.fileno())
        os.replace(name,path)
    finally:
        if os.path.exists(name): os.unlink(name)

def markdown(doc, prompts_only=False):
    labels={x['id']:x.get('number') or x.get('title') or '未命名镜头' for x in nodes(doc)}
    field_labels=dict(number='镜号',content='内容与动作',framing='景别与构图',camera='机位与运动',sound='声音',start='开始状态',end='结束状态',transition='衔接',assets='资产参考',reason='设计说明',notes='备注',title='标题',brief='大纲与创作意图')
    lines=[f"# {doc['title']}", '',f"> 修订 {doc['revision']} · 自动生成阅览稿；请通过 HTML 工作台编辑。",'']
    if not prompts_only:
        if doc.get('source_text'):lines += ['## 对应原文','',doc['source_text'],'']
        lines += [doc['brief'],'']
        for sec in doc['sections']:
            lines += ['## '+sec['title'],sec['notes'],'']
            for group in sec['groups']:
                lines += ['### '+group['title'],group['notes'],'']
                # Two linked tables keep all fields readable without a 12-column sheet.
                def cell(value):
                    text = html.escape(str(value), quote=False).replace('|', '&#124;')
                    return text.replace('\r\n', '\n').replace('\r', '\n').replace('\n', '<br>') or '—'
                tables = [
                    [('number','镜号'),('duration','预计秒数'),('content','内容与动作'),('framing','景别与构图'),('camera','机位与运动'),('sound','声音')],
                    [('number','镜号'),('start','开始状态'),('end','结束状态'),('transition','衔接'),('assets','资产参考'),('reason','设计说明'),('notes','备注')],
                ]
                if not group['shots']:
                    lines += ['暂无镜头。', '']
                for columns in tables if group['shots'] else []:
                    lines += ['| ' + ' | '.join(label for _, label in columns) + ' |',
                              '| ' + ' | '.join('---' for _ in columns) + ' |']
                    for shot in group['shots']:
                        values = [cell('待定' if key == 'duration' and shot[key] is None else shot[key]) for key, _ in columns]
                        lines.append('| ' + ' | '.join(values) + ' |')
                    lines.append('')
        lines+=['## 修改建议','']
        for s in doc['suggestions']:
            state={'pending':'待决定','accepted':'已采用','ignored':'已忽略'}[s['status']]
            lines += [f"### {s['problem']}",f"对象：{labels.get(s['target_id'],'原对象已删除')} · {state}"+(' · 内容已变化，需要复核' if s['stale'] else ''),s['impact'],'']
            for key,value in s['changes'].items():
                lines += ['建议'+field_labels.get(key,key)+'：',value,'']
    lines+=['## 生图提示词包','']
    for p in doc['prompts']:
        lines += ['### '+p['title'], '需要复核' if p['status']=='stale' else '对应当前内容',
                  '关联镜头：'+', '.join(labels.get(sid,'原镜头已删除') for sid in p['shot_ids']),p['text'],'参考：'+p['references'],'约束：'+p['constraints'],'']
    return '\n'.join(lines)+'\n'

class Store:
    def __init__(self,directory):
        self.root=Path(directory).expanduser().resolve()
        if self.root == ROOT or ROOT in self.root.parents:
            raise ValueError('项目数据不能保存在Skill安装目录内，请使用项目分镜目录。')
        self.path=self.root/'storyboard.json'

    @contextmanager
    def lock(self):
        self.root.mkdir(parents=True,exist_ok=True)
        path=self.root/'.storyboard.lock'
        with exclusive_lock(path):
            yield

    def _read(self):
        if self.path.is_symlink(): raise ValueError('文档不能是符号链接')
        doc=json.loads(self.path.read_text('utf8')); validate(doc)
        return doc

    def read(self):
        with self.lock():
            return self.view(self._read())

    def current(self, section_id=None):
        """Read-only projection of current work; retain states and detail IDs, not history copies."""
        view=self.read()
        sections=[sec for sec in view['sections'] if section_id is None or sec['id']==section_id]
        if section_id is not None and not sections:raise ValueError('段落不存在')
        section_ids={sec['id'] for sec in sections}
        shot_ids={shot['id'] for sec in sections for group in sec['groups'] for shot in group['shots']}
        records=production.state(view)['records'];by_id={record['id']:record for record in records}
        selected={record['id'] for record in production.active_records(view)
                  if view['_record_states'][record['id']]['status']!='excluded'
                  and (section_id is None or not record['section_ids'] or section_ids.intersection(record['section_ids'])
                       or shot_ids.intersection(record['shot_ids']))}
        # A scoped overview must not hide a referenced record outside its section.
        pending=list(selected)
        while pending:
            record=by_id[pending.pop()]
            refs=record.get('depends_on',[])+[ref.get('record_id') for ref in record.get('data',{}).get('references',[]) if isinstance(ref,dict)]
            for rid in refs:
                if rid in by_id and rid not in selected:selected.add(rid);pending.append(rid)
        summaries=[]
        for record in records:
            if record['id'] not in selected:continue
            item={key:copy.deepcopy(record.get(key)) for key in ('id','kind','title','body','version','section_ids','shot_ids','depends_on','files')}
            item['state']=view['_record_states'][record['id']]
            if record.get('data',{}).get('decision_type'):item['decision_type']=record['data']['decision_type']
            item['details']={'command':'read','record_id':record['id']}
            summaries.append(item)
        workflow=copy.deepcopy(view['_workflow'])
        if section_id is not None:
            workflow['scopes']=[scope for scope in workflow.get('scopes',[]) if scope.get('section_id')==section_id]
            scope=next(iter(workflow['scopes']),None)
            workflow.update(phase=scope['phase'] if scope else 0,title=scope['status'] if scope else '范围已取消或暂无镜头',
                            detail=scope['detail'] if scope else '范围不从其他段落继承状态。')
        return {'view':'current','id':view['id'],'title':view['title'],'revision':view['revision'],
                'brief':view.get('brief',''),'source_text':view.get('source_text',''),'sections':sections,
                'section_status':{sid:status for sid,status in view['_section_status'].items() if sid in section_ids},
                'workflow':workflow,'routes':{sid:route for sid,route in view['_current_routes'].items() if sid in shot_ids},
                'generation_plans':[r for r in production.active_records(view) if r.get('data',{}).get('decision_type')=='generation_recommendation' and r['id'] in selected],
                'preview': [row for row in view['_preview_rows'] if row['shot_id'] in shot_ids],
                'records':summaries,'export_warning':view['_export_warning'],
                'prompts':[p for p in view.get('prompts',[]) if section_id is None or shot_ids.intersection(p.get('shot_ids',[]))],
                'suggestions':view.get('suggestions',[]),
                'workspace':{'style_choice':view.get('workspace',{}).get('style_choice'),
                             'coordination':view['_coordination'],
                             'reference_request':view['_references'].get('current')},
                'omitted':{'history':True,'record_data':'read --record-id ID','full_document':'read'},
                'limits':'概览不代替完整记录、投产包校验或平台实际输入回读；候选与需复核状态按原数据保留。'}

    def read_record(self, rid):
        """Return one editable record with its true version and state, without copying its history."""
        with self.lock(), production.evaluation():
            doc=self._read();record=next((r for r in production.state(doc)['records'] if r['id']==rid),None)
            if record is None:raise ValueError('制作记录不存在')
            return {'document_id':doc['id'],'revision':doc['revision'],'record_version':record['version'],
                    'state':production.record_states(doc,self.root)[rid],
                    'record':{key:copy.deepcopy(record[key]) for key in ('id','kind','title','body','section_ids','shot_ids','depends_on','files','data')},
                    'history_available':bool(record.get('history'))}

    def view(self,doc):
        with production.evaluation():
            result=copy.deepcopy(doc)
            result['_section_status']={sec['id']:production.confirmation_status(doc,sec['id']) for sec in doc['sections']}
            result['_export_warning']=self.export_problem(doc)
            result['_record_states']=production.record_states(doc,self.root)
            result['_current_routes']={sid:{'record_id':r['id'],**{k:r['data'].get(k) for k in ('path','option_id','model','platform','input_mode','planning_only')}} for sid,r in production.current_routes(doc).items() if production.record_review_status(r)!='excluded'}
            result['_sequence_receipts']={}
            for record in production.active_records(doc):
                if record.get('data',{}).get('decision_type')=='generation_recommendation':
                    receipt=production.sequence_receipt(doc,record)
                    if receipt:result['_sequence_receipts'][record['id']]=receipt['id']
            workspace=doc.get('workspace',{})
            result['_coordination']=coordination.view(workspace.get('coordination'),doc['title'])
            result['_references']=reference_search.view(workspace.get('reference_sessions',[]))
            result['_pacing']=pacing.summary(doc)
            result['_preview_rows']=production.preview_rows(doc,self.root)
            result['_workflow']=production.workflow_status(doc,self.root,result['_preview_rows'])
            result['_view_revision']=digest([result['_record_states'],result['_preview_rows'],result['_workflow'],result['_sequence_receipts'],result['_export_warning'],
                result['_coordination'],result['_references'].get('current'),workspace.get('style_choice')])
            return result

    def text(self,doc):
        with production.evaluation():
            return production.production_markdown(doc,self.root,markdown)

    def export_problem(self,doc):
        dest=self.root/'分镜阅览.md'
        if dest.is_symlink():return '正式文档是符号链接，未覆盖'
        if not dest.exists():return ''
        known=production.state(doc).get('export_hash')
        actual=hashlib.sha256(dest.read_bytes()).hexdigest()
        if known and known==actual:return ''
        text=self.text(doc)
        if text is not None and dest.read_text('utf8')==text:return ''
        if not known and dest.read_text('utf8')==markdown(doc):return ''
        return '现有Markdown含未同步或无法还原的内容；已保留，须核对后合并，未覆盖'

    def exports(self,doc):
        text=self.text(doc)
        if text is None:raise Conflict('尚无已确认段落，不能导出正式制作文档')
        problem=self.export_problem(doc)
        if problem:raise Conflict(problem)
        history=production.history_markdown(doc,self.root,markdown)
        history_path=self.root/'制作记录.md'
        if history_path.is_symlink():raise Conflict('制作记录是符号链接，未覆盖')
        if history_path.exists():
            known=production.state(doc).get('history_export_hash')
            actual=hashlib.sha256(history_path.read_bytes()).hexdigest()
            if actual!=known and history_path.read_text('utf8')!=history:
                raise Conflict('制作记录含未同步的人工内容，已保留')
        atomic(history_path,history)
        atomic(self.root/'分镜阅览.md',text)
        return text

    def persist(self,doc):
        # One atomic JSON commits draft, snapshots and production records together.
        # export_hash authorizes replacement of only the previous generated Markdown.
        # If export fails, explicit export retries from the committed JSON.
        old=self._read() if self.path.exists() else None
        if old and 'production' in doc:
            dest=self.root/'分镜阅览.md'
            if not self.export_problem(old) and dest.is_file() and not dest.is_symlink():
                doc['production']['export_hash']=hashlib.sha256(dest.read_bytes()).hexdigest()
            history_path=self.root/'制作记录.md'
            if history_path.is_file() and not history_path.is_symlink():
                known=production.state(old).get('history_export_hash')
                actual=hashlib.sha256(history_path.read_bytes()).hexdigest()
                if actual==known or history_path.read_text('utf8')==production.history_markdown(old,self.root,markdown):
                    doc['production']['history_export_hash']=actual
        for key in list(doc):
            if key.startswith('_'):doc.pop(key)
        atomic(self.path,json.dumps(doc,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
        if production.state(doc)['confirmations']:
            try:self.exports(doc)
            except (OSError,ValueError,Conflict) as e:
                result=self.view(doc);result['_export_warning']=str(e);return result
        return self.view(doc)

    def export(self):
        with self.lock():return self.exports(self._read())

    def expected(self,doc,expected):
        if type(expected) is not int or expected!=doc['revision']:raise Conflict('内容已经更新，请读取最新修订')

    def confirm(self,sid,expected,evidence):
        with self.lock():
            doc=self._read();self.expected(doc,expected)
            production.confirm(doc,sid,evidence)
            doc['revision']+=1
            return self.persist(doc)

    def record(self,item,expected):
        with self.lock():
            doc=self._read();self.expected(doc,expected)
            production.put_record(doc,item,self.root)
            doc['revision']+=1
            return self.persist(doc)

    def workspace_action(self,command,expected):
        """Small shared-state actions; native Codex performs research and thread work."""
        if not isinstance(command,dict):raise ValueError('工作台操作须为对象')
        with self.lock():
            doc=self._read();self.expected(doc,expected)
            workspace=doc.setdefault('workspace',{})
            area=command.get('area')
            if area=='coordination':
                workspace['coordination']=coordination.apply(workspace.get('coordination',coordination.initial()),command.get('command'))
            elif area=='references':
                workspace['reference_sessions']=reference_search.apply(workspace.get('reference_sessions',[]),command.get('command'))
            elif area=='style':
                choice=command.get('choice')
                if not isinstance(choice,dict) or not isinstance(choice.get('brief'),str) or not choice['brief'].strip():
                    raise ValueError('先选择或描述本次视觉方向')
                atlas=json.loads((ROOT/'assets/visual-style-atlas/atlas.json').read_text())
                cards={card['id'] for card in atlas['cards']}
                for key in ('base_id','world_id'):
                    if choice.get(key) is not None and choice[key] not in cards:raise ValueError('未知图库条目')
                tones=choice.get('tones',[])
                if not isinstance(tones,list) or any(t not in {m['name'] for m in atlas['moods']} for t in tones):raise ValueError('未知调性')
                notes=choice.get('project_notes','')
                if not isinstance(notes,str):raise ValueError('本片定调补充须为文字')
                old_choice=workspace.get('style_choice')
                if old_choice:workspace.setdefault('style_choice_history',[]).append(copy.deepcopy(old_choice))
                workspace['style_choice']={'id':uid(),'brief':choice['brief'].strip(),'project_notes':notes,'base_id':choice.get('base_id'),
                    'world_id':choice.get('world_id'),'tones':tones,'selected_at':production.stamp(),
                    'status':'selected','selection_evidence':'用户在工作台保存本次视觉定调选择'}
            elif area=='pacing':
                plan=command.get('plan')
                before=copy.deepcopy(doc)
                doc=pacing.apply(doc,plan)
                bind_derived(doc,before)
                ids=[item['shot_id'] for item in plan['shots']]
                scope=[sec['id'] for sec in doc['sections'] if any(sid in ids for sid in production.shot_ids(sec))]
                production.put_record(doc,{'id':'pacing-'+str(doc['revision']+1),'kind':'decision','title':'当前内容时长校准',
                    'body':plan['evidence'],'section_ids':scope,'shot_ids':ids,
                    'data':{'decision_type':'pacing_calibration','plan':plan}},self.root)
            else:raise ValueError('未知工作台操作范围')
            validate(doc);doc['revision']+=1
            return self.persist(doc)

    def package(self,rid,output=None,*,_snapshot=None):
        with (self.lock() if _snapshot is None else nullcontext()), production.evaluation():
            doc=self._read() if _snapshot is None else _snapshot
            r=next((r for r in production.state(doc)['records'] if r['id']==rid),None)
            if r is None:raise ValueError('投产包不存在')
            issues=production.package_issues(doc,r,self.root)
            warnings=production.package_warnings(doc,r,self.root)
            result={'package_id':rid,'version':r['version'],'issues':issues,'warnings':warnings,
                    'content_timing':pacing.summary(doc,r['shot_ids']),
                    'readiness':'blocked' if issues else 'ready_for_authorized_generation','record':r,
                    'limits':'仅本地输入及已记录复核通过；平台消费和实际声画效果仍需验证。'}
            try:
                result['review_input']=production.delivery_input(doc,r,self.root)
                result['input_sha256']=production.digest(result['review_input'])
            except (ValueError,OSError,KeyError,TypeError):pass
            if output is None:return result
            if issues:raise Conflict('投产包尚不可交接：'+'；'.join(issues))
            dest=Path(output).expanduser().resolve()
            if dest.exists():raise Conflict('交付目录已存在，请选择新的版本目录')
            by_id={x['id']:x for x in production.state(doc)['records']}
            dest.mkdir(parents=True)
            try:
                copied={};mapping=[]
                for ref in r['data']['references']:
                    asset=by_id[ref['record_id']]
                    source=production.local_file(self.root,ref['file_path'])
                    sha=production.file_digest(self.root,ref['file_path'])
                    name=copied.get(sha)
                    if name is None:
                        name=f'{len(copied)+1:02d}-'+source.name
                        shutil.copy2(source,dest/name)
                        if production.file_digest(dest,name)!=sha:raise ValueError('复制校验失败')
                        copied[sha]=name
                    mapping.append({**ref,'package_path':name,'sha256':sha})
                handoff=[]
                for use in r['data'].get('audio_uses',[]):
                    if use.get('implementation') not in ('external_overlay','post_lipsync'):continue
                    asset=by_id[use['record_id']]
                    for f in asset['files']:
                        source=production.local_file(self.root,f['path']);sha=production.file_digest(self.root,f['path'])
                        folder=dest/'后续声音';folder.mkdir(exist_ok=True)
                        name=sha[:12]+'-'+source.name
                        shutil.copy2(source,folder/name)
                        if production.file_digest(folder,name)!=sha:raise ValueError('声音交接复制校验失败')
                        handoff.append({**use,'source_path':f['path'],'package_path':'后续声音/'+name,'sha256':sha})
                repair=r['data'].get('repair_context')
                repair_source=None
                if isinstance(repair,dict):
                    repair_source={**repair,'absolute_source_path':str(production.local_file(self.root,repair['source_file_path']))}
                manifest={**result,'audio_handoff':handoff,'references':mapping,'repair_source':repair_source,'source_revision':doc['revision'],'exported_at':production.stamp()}
                atomic(dest/'manifest.json',json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
                atomic(dest/'提示词.txt',r['data']['prompt']+'\n')
                atomic(dest/'参数与上传.json',json.dumps({'parameters':r['data']['parameters'],'platform':r['data']['platform'],'mode':r['data']['mode'],'model':r['data']['model'],'references':mapping},ensure_ascii=False,indent=2)+'\n')
            except Exception:
                shutil.rmtree(dest);raise
            return {**result,'output_path':str(dest)}

    def create(self,title,doc=None):
        with self.lock():
            if self.path.exists(): raise Conflict('文档已存在，请读取后更新')
            doc=copy.deepcopy(doc) if doc else new_document(title)
            if 'production' in doc:raise ValueError('新建不能注入确认与制作记录')
            validate(doc)
            doc['revision']=0; bind_derived(doc)
            return self.persist(doc)

    def update(self,doc,expected,base=None):
        with self.lock():
            old=self._read()
            if type(expected) is not int:raise Conflict('缺少读取时的修订号')
            if expected!=old['revision']:
                if not isinstance(base,dict) or base.get('revision')!=expected or base.get('id')!=old['id']:
                    raise Conflict('内容已经更新，请读取最新修订；本次未覆盖')
                doc={**merge_edits(editable(base),editable(doc),editable(old)), 'revision':old['revision']}
            doc=copy.deepcopy(doc)
            doc.pop('production',None)
            if 'production' in old:doc['production']=copy.deepcopy(old['production'])
            doc.pop('workspace',None)
            if 'workspace' in old:doc['workspace']=copy.deepcopy(old['workspace'])
            validate(doc)
            if doc['id']!=old['id']: raise ValueError('不能替换文档标识')
            bind_derived(doc,old)
            doc['revision']=old['revision']+1
            return self.persist(doc)

    def transact(self, incoming, expected, revise=False):
        """Commit a coherent edit and its scoped records once, or not at all."""
        if not isinstance(incoming,dict):raise ValueError('批次更新须为对象')
        with self.lock():
            old=self._read();self.expected(old,expected)
            doc=copy.deepcopy(incoming.get('document',old))
            doc.pop('production',None)
            if 'production' in old:doc['production']=copy.deepcopy(old['production'])
            doc.pop('workspace',None)
            if 'workspace' in old:doc['workspace']=copy.deepcopy(old['workspace'])
            doc['revision']=old['revision']
            if doc.get('id')!=old['id']:raise ValueError('不能替换文档标识')
            validate(doc);bind_derived(doc,old)
            if revise:
                evidence=incoming.get('evidence')
                if not isinstance(evidence,str) or not evidence.strip():raise ValueError('局部修订须记录本轮用户反馈')
                old_sections=production.sections(old)
                affected=incoming.get('section_ids') or [sec['id'] for sec in doc['sections'] if sec!=old_sections.get(sec['id'])]
                if not affected:affected=list(dict.fromkeys(sid for r in incoming.get('records',[]) for sid in r.get('section_ids',[])))
                basis=incoming.get('basis_section_ids') or affected
                working={s['section_id'] for s in production.workflow_status(old,self.root)['scopes'] if s['phase']>=1}
                if not affected or not set(affected)<=set(production.sections(doc)) or not set(basis)<=working:
                    raise ValueError('局部修订须承接已有图稿或视频制作范围；新任务请明确建立自己的范围')
                ids=[sid for sec in doc['sections'] if sec['id'] in affected for sid in production.shot_ids(sec)]
                production.put_record(doc,{'id':'revision-'+str(old['revision']+1),'kind':'decision','title':'本轮制作内容修订',
                    'body':'按实际影响更新内容与依赖，保留有效决定和未受影响成果；不把修改许可记为结果采用。',
                    'section_ids':affected,'shot_ids':ids,'data':{'decision_type':'image_stage_entry',
                    'batch_id':doc['id'],'selection_evidence':evidence,'revision_basis':basis}},self.root)
                old_ids={sid for sec in old['sections'] if sec['id'] in basis for sid in production.shot_ids(sec)}
                current_ids=[sid for sec in doc['sections'] for sid in production.shot_ids(sec)]
                previous_scopes=production.workflow_status(old,self.root)['scopes']
                if any(s['section_id'] in basis and s['phase']==2 for s in previous_scopes):
                    production.put_record(doc,{'id':'revision-video-'+str(old['revision']+1),'kind':'decision','title':'承接本轮视频修订范围',
                        'section_ids':affected,'shot_ids':ids,'data':{'decision_type':'video_preparation_entry','batch_id':doc['id'],
                        'selection_evidence':evidence,'revision_basis':basis}},self.root)
                current_routes=production.current_routes(old)
                for route in production.active_records(old):
                    rd=route.get('data',{})
                    if rd.get('decision_type')!='production_path' or production.record_review_status(route)=='excluded' or rd.get('path')=='hybrid' or not old_ids or not old_ids<=set(route['shot_ids']):continue
                    if any(current_routes.get(sid,{}).get('id')!=route['id'] for sid in old_ids):continue
                    new_ids=set(ids)-old_ids
                    reuse=incoming.get('route_reuse_evidence')
                    if new_ids and not (isinstance(reuse,str) and reuse.strip()):continue
                    assignments=rd.get('assignments',[])
                    tools={a.get('tool') for a in assignments}
                    if rd['path'] in production.PREVIS_PATHS and len(tools)!=1:continue
                    updated=copy.deepcopy(route)
                    scope=(set(route['shot_ids'])-old_ids)|set(ids)
                    updated['shot_ids']=[sid for sid in current_ids if sid in scope]
                    updated['section_ids']=list(dict.fromkeys([*(sid for sid in route['section_ids'] if sid in production.sections(doc)),*affected]))
                    assignment={'path':rd['path'],'shot_ids':updated['shot_ids']}
                    if tools and next(iter(tools)):assignment['tool']=next(iter(tools))
                    updated['data']['assignments']=[assignment]
                    updated['data']['scope_extension_evidence']=incoming.get('route_reuse_evidence') or evidence
                    production.put_record(doc,updated,self.root)
            for item in incoming.get('confirmations',[]):production.confirm(doc,item['section_id'],item['evidence'])
            remaining=copy.deepcopy(incoming.get('records',[]))
            if not isinstance(remaining,list):raise ValueError('records须为列表')
            if len({r.get('id') for r in remaining})!=len(remaining):raise ValueError('同一批次不能重复更新一个记录')
            remaining.sort(key=lambda r:0 if r.get('kind') in ('decision','style') else 1)
            while remaining:
                pending={r['id'] for r in remaining}
                ready=[r for r in remaining if not (set(r.get('depends_on',[])) & pending)]
                if not ready:raise ValueError('批次记录依赖存在循环')
                for item in ready:
                    production.put_record(doc,item,self.root);remaining.remove(item)
            validate(doc);doc['revision']+=1
            return self.persist(doc)

    def prepare(self, incoming, expected, output=None, record_id=None):
        """Bind an authored review to its exact input without a manual hash round trip."""
        if output and Path(output).expanduser().exists():raise Conflict('交付目录已存在，请选择新的版本目录')
        with self.lock():
            doc=self._read();self.expected(doc,expected)
            item=copy.deepcopy(incoming)
            if record_id is not None:
                original=next((r for r in production.active_records(doc) if r['id']==record_id),None)
                if original is None or original['kind']!='package':raise ValueError('待修改的当前投产包不存在')
                if production.record_review_status(original)=='excluded':raise ValueError('已排除的投产包不能作为当前包更新')
                fields=('id','kind','title','body','section_ids','shot_ids','depends_on','files','data')
                if not isinstance(item,dict) or set(item)-set(fields):raise ValueError('局部更新只接受投产包可编辑字段')
                if item.get('id',record_id)!=record_id or item.get('kind','package')!='package':raise ValueError('局部更新不能改变记录ID或类型')
                if 'data' in item and not isinstance(item['data'],dict):raise ValueError('data须为对象')
                def merge(base, patch):
                    for key,value in patch.items():
                        if isinstance(value,dict) and isinstance(base.get(key),dict):merge(base[key],value)
                        else:base[key]=copy.deepcopy(value)
                    return base
                patch=item
                item=merge({key:copy.deepcopy(original[key]) for key in fields},patch)
                old_data=original['data'];new_data=item['data']
                if new_data.get('prompt')!=old_data.get('prompt') and 'prompt_review' not in patch.get('data',{}):
                    raise ValueError('修改正文须同时提供针对新正文的复核更新')
            if not isinstance(item,dict) or item.get('kind')!='package':raise ValueError('prepare需要完整投产包记录')
            data=item.get('data',{});review=data.get('prompt_review')
            if not isinstance(review,dict) or review.get('prompt')!=data.get('prompt'):
                raise ValueError('复核须针对这份准确正文，不自动改写复核内容')
            records={r['id']:r for r in production.state(doc)['records']}
            choice=records.get(data.get('production_path_decision_id'),{}).get('data',{})
            if choice:
                data.setdefault('production_batch_id',choice.get('batch_id'))
                if choice.get('output_scope'):data.setdefault('output_scope',copy.deepcopy(choice['output_scope']))
            receipt=production.sequence_receipt(doc,item)
            if receipt and not data.get('sequence_review_id'):
                data['sequence_review_id']=receipt['id'];data['sequence_review_version']=receipt['version']
            dependencies=list(item.get('depends_on',[]))
            dependencies.extend(ref['record_id'] for ref in data.get('references',[]) if isinstance(ref,dict) and ref.get('record_id'))
            if data.get('production_path_decision_id'):dependencies.append(data['production_path_decision_id'])
            item['depends_on']=list(dict.fromkeys(dependencies))
            review['input_sha256']=production.digest(production.delivery_input(doc,item,self.root))
            if review.get('review_version')!=3:
                review.setdefault('semantic_review',{})['prompt_sha256']=hashlib.sha256(data['prompt'].encode()).hexdigest()
            record=production.put_record(doc,item,self.root)
            with production.evaluation():issues=production.package_issues(doc,record,self.root)
            if issues:raise Conflict('投产包尚不可交接：'+'；'.join(issues))
            doc['revision']+=1;self.persist(doc)
            revision=doc['revision']
            result=self.package(item['id'],output,_snapshot=doc)
            result['revision']=revision
            return result

    def choose_route(self, recommendation_id, path, expected, option_id=None):
        with self.lock():
            doc=self._read();self.expected(doc,expected)
            recommendation=next((r for r in production.active_records(doc) if r['id']==recommendation_id
                and r.get('data',{}).get('decision_type')=='generation_recommendation'),None)
            if recommendation is None:raise ValueError('生成建议不存在')
            if production.is_stale(doc,recommendation,self.root):raise Conflict('建议依据已变化，请先同步受影响的生成建议')
            data=recommendation['data']
            matches=[x for x in data.get('options',[]) if x.get('id')==option_id] if option_id is not None else [x for x in data.get('options',[]) if x.get('path')==path]
            if len(matches)!=1:raise ValueError('请用option_id选择唯一方案')
            option=matches[0];path=option.get('path')
            if option is None or path not in ('direct_platform','previs_reference'):raise ValueError('请选择当前展示的生成路线')
            continued=[scope for scope in production.workflow_status(doc,self.root)['scopes'] if scope['phase']==2 and scope['section_id'] in recommendation['section_ids']]
            for scope in continued:
                sid=scope['section_id'];ids=[i for i in production.shot_ids(production.sections(doc)[sid]) if i in recommendation['shot_ids']]
                production.put_record(doc,{'id':'continue-video-'+sid,'kind':'decision','title':'沿用本段视频制作进度',
                    'section_ids':[sid],'shot_ids':ids,'data':{'decision_type':'video_preparation_entry',
                    'batch_id':data.get('batch_id') or doc['id'],'selection_evidence':'已有视频制作范围内调整方案，保持该范围进度'}},self.root)
            selected={'decision_type':'production_path','batch_id':data.get('batch_id') or doc['id'],
                'path':path,'selection_evidence':'用户在工作台选择：'+option.get('label',path),
                'source_recommendation':recommendation_id,
                'planning_only':True}
            for key in ('id','model','input_mode','inputs','method_evidence'):
                if option.get(key) is not None:selected['option_id' if key=='id' else key]=copy.deepcopy(option[key])
            if data.get('method_evidence'):selected['method_evidence']=copy.deepcopy(data['method_evidence'])
            if option.get('tool'):selected['tool']=option['tool']
            if option.get('platform') or data.get('platform'):selected['platform']=option.get('platform') or data['platform']
            if option.get('output_scope') or data.get('output_scope'):selected['output_scope']=option.get('output_scope') or data['output_scope']
            preferred=next((x['path'] for x in data.get('options',[]) if x.get('recommended')),None)
            if preferred:selected['recommended_path']=preferred
            production.put_record(doc,{'id':'route-'+recommendation_id,'kind':'decision','title':'本批生成路线选择',
                'body':selected['selection_evidence'],'section_ids':recommendation['section_ids'],
                'shot_ids':recommendation['shot_ids'],'data':selected},self.root)
            doc['revision']+=1
            return self.persist(doc)

    def decide(self,sid,decision,expected):
        with self.lock():
            old=self._read()
            if type(expected) is not int or expected!=old['revision']: raise Conflict('请读取最新修订')
            doc=copy.deepcopy(old)
            suggestion=next((s for s in doc['suggestions'] if s['id']==sid),None)
            if suggestion is None: raise ValueError('建议不存在')
            if suggestion['status']!='pending': raise Conflict('建议已处理')
            if decision=='accept':
                if suggestion['stale'] or dependency(doc,suggestion,'suggestion')!=suggestion['_dependency']:
                    raise Conflict('建议依据已变化，需要复核')
                target=next(x for x in nodes(doc) if x['id']==suggestion['target_id'])
                for k,v in suggestion['changes'].items():
                    if k not in target or not isinstance(target[k],str) or k=='id': raise ValueError('目标不支持该字段')
                    target[k]=v
            bind_derived(doc,old)
            suggestion['status']='accepted' if decision=='accept' else 'ignored'
            validate(doc);doc['revision']+=1
            return self.persist(doc)

def serve(store,port):
    token=secrets.token_urlsafe(24)
    instance=secrets.token_hex(12)
    # A running backend serves the matching assets, even while a release is replaced on disk.
    assets={name:(ROOT/'assets'/name).read_bytes() for name in ('index.html','app.js','workspace.js','style.css')}
    atlas_assets={name:(entry[0].read_bytes(),entry[1]) for name in ATLAS_FILES if (entry:=atlas_file(name))}
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args): pass
        def send(self,status,data,ctype='application/json; charset=utf-8',atlas_page=False):
            body=(json.dumps(data,ensure_ascii=False).encode() if not isinstance(data,bytes) else data)
            self.send_response(status);self.send_header('Content-Type',ctype)
            self.send_header('Content-Length',str(len(body)));self.send_header('Cache-Control','no-store')
            self.send_header('X-Content-Type-Options','nosniff')
            policy="default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self' https: data:; media-src 'self' https:; frame-src 'self'; object-src 'none'; frame-ancestors 'none'; base-uri 'none'"
            if atlas_page:
                policy="default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'none'; object-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'"
            self.send_header('Content-Security-Policy',policy)
            self.end_headers();self.wfile.write(body)
        def local(self):
            host=self.headers.get('Host','')
            return host in (f'127.0.0.1:{self.server.server_port}',f'localhost:{self.server.server_port}')
        def do_GET(self):
            if not self.local(): return self.send(403,{'error':'仅允许本机访问'})
            path=urlparse(self.path).path
            try:
                if path.startswith('/style-atlas/'):
                    name=unquote(path[len('/style-atlas/'):])
                    if name in atlas_assets:
                        payload,ctype=atlas_assets[name]
                        return self.send(200,payload,ctype,atlas_page=name=='index.html')
                    entry=atlas_file(name)
                    if entry is None or name in ATLAS_FILES:return self.send(404,{'error':'图库文件不存在'})
                    return self.send(200,entry[0].read_bytes(),entry[1])
                if path=='/api/session': return self.send(200,{'token':token})
                if path=='/api/health': return self.send(200,{**runtime_info(),'directory':str(store.root),'instance':instance,'pid':os.getpid()})
                if path=='/favicon.ico': return self.send(204,b'','image/x-icon')
                if path=='/api/document': return self.send(200,store.read())
                if path=='/api/rehearsal':
                    query=parse_qs(urlparse(self.path).query)
                    with store.lock():doc=store._read()
                    return self.send(200,rehearsal.manifest(doc,store.root,section_ids=query.get('section_id')))
                if path=='/api/image':
                    query=parse_qs(urlparse(self.path).query)
                    rid=query.get('record',[''])[0]
                    with store.lock():
                        records=store._read().get('production',{}).get('records',[])
                    record=next((r for r in records if r['id']==rid),None)
                    if 'input' in query:
                        index=int(query['input'][0])
                        inputs=record.get('data',{}).get('actual_inputs',[]) if record else []
                        if not isinstance(inputs,list) or index<0 or index>=len(inputs) or not isinstance(inputs[index],dict):
                            return self.send(404,{'error':'实际用图未登记'})
                        entry=inputs[index]
                        if not isinstance(entry.get('path'),str) or not entry['path']:
                            return self.send(404,{'error':'实际用图缺少路径'})
                        image_path=production.local_file(store.root,entry['path'])
                        inside_project=image_path==store.root or store.root in image_path.parents
                        source_id=entry.get('record_id') or entry.get('source_record_id')
                        source=next((r for r in records if r['id']==source_id),None)
                        registered_file=next((f for f in source.get('files',[]) if production.local_file(store.root,f['path'])==image_path),None) if source else None
                        if not inside_project and not registered_file:
                            return self.send(403,{'error':'项目外用图须有已登记来源'})
                        expected_hash=entry.get('sha256') or (registered_file.get('sha256') if registered_file else None)
                    else:
                        index=int(query.get('file',['-1'])[0])
                        if record is None or index<0 or index>=len(record.get('files',[])):
                            return self.send(404,{'error':'图片未登记'})
                        entry=record['files'][index]
                        image_path=production.local_file(store.root,entry['path'])
                        expected_hash=entry.get('sha256')
                    types={'.png':'image/png','.jpg':'image/jpeg','.jpeg':'image/jpeg','.webp':'image/webp','.gif':'image/gif'}
                    ctype=types.get(image_path.suffix.lower())
                    if not ctype:return self.send(415,{'error':'不支持的图片格式'})
                    if not image_path.is_file():return self.send(404,{'error':'图片文件缺失'})
                    payload=image_path.read_bytes()
                    if expected_hash and hashlib.sha256(payload).hexdigest()!=expected_hash:
                        return self.send(409,{'error':'图片已变化，请更新制作记录'})
                    return self.send(200,payload,ctype)

                if path in ('/api/markdown','/api/prompts'):
                    return self.send(200,store.export().encode(),'text/markdown; charset=utf-8')
                allowed={'/':'index.html','/index.html':'index.html','/app.js':'app.js','/workspace.js':'workspace.js','/style.css':'style.css'}
                if path not in allowed: return self.send(404,{'error':'不存在'})
                name=allowed[path];ctype={'html':'text/html','js':'text/javascript','css':'text/css'}[name.rsplit('.',1)[1]]
                return self.send(200,assets[name],ctype+'; charset=utf-8')
            except Conflict as e: self.send(409,{'error':str(e)})
            except Exception as e: self.send(400,{'error':str(e)})
        def do_POST(self):
            origin=self.headers.get('Origin')
            if not self.local() or (origin and origin not in (f'http://127.0.0.1:{self.server.server_port}',f'http://localhost:{self.server.server_port}')):
                return self.send(403,{'error':'不允许跨站写入'})
            if self.headers.get('X-Storyboard-Token')!=token: return self.send(403,{'error':'请重新连接编辑页'})
            try:
                length=int(self.headers.get('Content-Length','0'))
                if not 0<length<=8_000_000: raise ValueError('请求大小不合法')
                body=json.loads(self.rfile.read(length));path=urlparse(self.path).path
                if path=='/api/shutdown':
                    self.send(200,{'stopping':True})
                    threading.Thread(target=self.server.shutdown,daemon=True).start()
                    return
                if path=='/api/document': result=store.update(body['document'],body['expected_revision'],body.get('base_document'))
                elif path in ('/api/transact','/api/revise'): result=store.transact(body['transaction'],body['expected_revision'],path=='/api/revise')
                elif path=='/api/workspace': result=store.workspace_action(body['command'],body['expected_revision'])
                elif path=='/api/prepare': result=store.prepare(body['record'],body['expected_revision'])
                elif path=='/api/routes/choose': result=store.choose_route(body['recommendation_id'],body.get('path'),body['expected_revision'],body.get('option_id'))
                elif path=='/api/production/records': result=store.record(body['record'],body['expected_revision'])
                elif path=='/api/sections/confirm': result=store.confirm(body['section_id'],body['expected_revision'],body['evidence'])
                elif path.startswith('/api/suggestions/'):
                    parts=path.split('/')
                    if len(parts)!=5 or parts[4] not in ('accept','ignore'): raise ValueError('未知建议操作')
                    result=store.decide(parts[3],parts[4],body['expected_revision'])
                else: return self.send(404,{'error':'不存在'})
                self.send(200,result)
            except Conflict as e: self.send(409,{'error':str(e)})
            except Exception as e: self.send(400,{'error':str(e)})
    server=ThreadingHTTPServer(('127.0.0.1',port),Handler)
    manifest=store.root/'.storyboard-server.json'
    atomic(manifest,json.dumps({'url':f'http://127.0.0.1:{server.server_port}','pid':os.getpid(),'instance':instance,'build_id':BUILD_ID}))
    print(f'http://127.0.0.1:{server.server_port}',flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        try:
            if json.loads(manifest.read_text()).get('instance')==instance:manifest.unlink()
        except (OSError,ValueError):pass

def service_request(url, path, body=None, token=None):
    parsed=urlparse(url)
    if parsed.hostname!='127.0.0.1' or parsed.scheme!='http' or not parsed.port:raise ValueError('服务入口必须是本机工作台')
    headers={'Content-Type':'application/json'}
    if token:headers['X-Storyboard-Token']=token
    request=urllib.request.Request(url+path,data=json.dumps(body).encode() if body is not None else None,headers=headers)
    with urllib.request.urlopen(request,timeout=2) as response:return json.load(response)

def service_process_options():
    # Both branches detach the background service from the invoking console.
    return {'creationflags':subprocess.DETACHED_PROCESS} if sys.platform=='win32' else {'start_new_session':True}

def open_service(store, stop=False):
    """Reuse or safely restart this directory's service; never terminate an unrelated PID."""
    store._read()
    manifest=store.root/'.storyboard-server.json'
    lock_path=store.root/'.storyboard-runtime.lock'
    with exclusive_lock(lock_path):
        saved={};health={};port=0
        try:
            saved=json.loads(manifest.read_text());health=service_request(saved['url'],'/api/health')
        except (OSError,ValueError,KeyError):pass
        owned=health.get('directory')==str(store.root) and health.get('instance')==saved.get('instance')
        if owned and health.get('build_id')==BUILD_ID and not stop:
            return {'url':saved['url'],'reused':True,'build_id':BUILD_ID}
        if owned:
            port=urlparse(saved['url']).port
            token=service_request(saved['url'],'/api/session')['token']
            service_request(saved['url'],'/api/shutdown',{},token)
            for _ in range(30):
                try:service_request(saved['url'],'/api/health')
                except (OSError,ValueError):break
                time.sleep(.1)
        if stop:return {'stopped':bool(owned),'directory':str(store.root)}
        logs=store.root/'过程记录';logs.mkdir(exist_ok=True)
        with (logs/'工作台服务.log').open('ab') as log:
            process=subprocess.Popen([sys.executable,str(ROOT/'scripts/storyboard.py'),'serve','--directory',str(store.root),'--port',str(port)],
                                     stdin=subprocess.DEVNULL,stdout=log,stderr=log,**service_process_options())
        for _ in range(50):
            if process.poll() is not None:raise ValueError('工作台启动失败，请查看过程记录/工作台服务.log')
            try:
                current=json.loads(manifest.read_text());health=service_request(current['url'],'/api/health')
                if health.get('pid')==process.pid and health.get('build_id')==BUILD_ID:
                    return {'url':current['url'],'reused':False,'build_id':BUILD_ID,'restarted':bool(owned)}
            except (OSError,ValueError,KeyError):pass
            time.sleep(.1)
        raise ValueError('工作台尚未就绪；保留日志后重试 open，不重复创建数据')

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command',choices=['create','read','current','update','export','serve','open','stop','confirm','record','package','transact','revise','prepare','rehearse','workspace'])
    parser.add_argument('--directory',required=True)
    parser.add_argument('--title',default='未命名分镜')
    parser.add_argument('--input',help='UTF-8 JSON document')
    parser.add_argument('--expected-revision',type=int)
    parser.add_argument('--section-id')
    parser.add_argument('--evidence')
    parser.add_argument('--record-id')
    parser.add_argument('--output')
    parser.add_argument('--compact',action='store_true',help='prepare/package只返回检查结果和准确输入标识，完整包按需读取')
    parser.add_argument('--port',type=int,default=0)
    args=parser.parse_args()
    try:
        if args.compact and args.command not in ('prepare','package'):parser.error('--compact only supports prepare/package')
        store=Store(args.directory)
        if args.command=='serve': return serve(store,args.port)
        incoming=json.loads(Path(args.input).read_text('utf8')) if args.input else None
        if args.command in ('open','stop'):result=open_service(store,args.command=='stop')
        elif args.command=='create': result=store.create(args.title,incoming)
        elif args.command=='update':
            if incoming is None or args.expected_revision is None: parser.error('update requires --input and --expected-revision')
            result=store.update(incoming,args.expected_revision)
        elif args.command=='confirm': result=store.confirm(args.section_id,args.expected_revision,args.evidence)
        elif args.command=='record': result=store.record(incoming,args.expected_revision)
        elif args.command in ('transact','revise'): result=store.transact(incoming,args.expected_revision,args.command=='revise')
        elif args.command=='workspace': result=store.workspace_action(incoming,args.expected_revision)
        elif args.command=='prepare': result=store.prepare(incoming,args.expected_revision,args.output,args.record_id)
        elif args.command=='current': result=store.current(args.section_id)
        elif args.command=='read' and args.record_id: result=store.read_record(args.record_id)
        elif args.command=='rehearse':
            with store.lock():doc=store._read()
            result=rehearsal.manifest(doc,store.root,section_ids=[args.section_id] if args.section_id else None)
        elif args.command=='package': result=store.package(args.record_id,args.output)
        elif args.command=='export':
            store.export(); result=store.read()
        else: result=store.read()
        if args.compact:result={key:value for key,value in result.items() if key not in ('record','review_input')}
        print(json.dumps(result,ensure_ascii=False,indent=2))
    except (ValueError,Conflict,OSError) as e:
        parser.exit(1,str(e)+'\n')

if __name__=='__main__': main()
