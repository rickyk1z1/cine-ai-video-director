#!/usr/bin/env python3
"""Bind a derived SceneSpec to current scoped input. No Blender or network calls."""
import argparse
import copy
import json
import math
from fractions import Fraction
from pathlib import Path
import sys
import uuid
import production
from storyboard import Store, atomic
sys.path.insert(0,str(Path(__file__).parent/'previs'))
from validate_handoff import Audit, check_scene

def current_shots(doc,sid):
    section=production.sections(doc).get(sid)
    if section is None or sid in production.cancelled_sections(doc):raise ValueError('段落不存在或已取消')
    return [shot for group in section['groups'] for shot in group['shots']]

def scope_ids(shots,selection):
    ids=[s['id'] for s in shots]
    if selection is not None:
        if (not isinstance(selection,list) or not selection or any(not isinstance(v,str) for v in selection)
                or len(set(selection))!=len(selection) or any(v not in ids for v in selection)):
            raise ValueError('shot_ids须为非空、唯一的当前镜头ID列表')
        positions=[ids.index(v) for v in selection]
        if positions!=list(range(positions[0],positions[0]+len(positions))):
            raise ValueError('shot_ids须按当前顺序选择连续镜头；分离镜头分别建立工程')
    return selection if selection is not None else ids

def scope_notes(section,selected):
    return {'section':section.get('notes',''),
            'groups':[[g['id'],g.get('notes','')] for g in section['groups']
                      if any(s['id'] in selected for s in g['shots'])]}

def binding(doc,sid,selection=None,timebase='section'):
    shots=current_shots(doc,sid);selected=scope_ids(shots,selection)
    if timebase not in ('section','local'):raise ValueError('source_timebase须为section或local')
    if not selected or not production.can_prepare(doc,{'section_ids':[sid],'shot_ids':selected}):
        raise ValueError('所选镜头缺少内容确认或当前范围的继续制作授权')
    first=[s['id'] for s in shots].index(selected[0]);wanted=set(selected)
    payload={'context':{'brief':doc.get('brief'),'source_text':doc.get('source_text','')},
             'notes':scope_notes(production.sections(doc)[sid],wanted),
             'shots':[shot for shot in shots if shot['id'] in wanted],'source_timebase':timebase,
             'preceding_timing':[[s['id'],s['duration']] for s in shots[:first]] if timebase=='section' else []}
    result={'document_id':doc['id'],'section_id':sid,'scope_version':2,'source_timebase':timebase,
            'fingerprint':production.digest(payload),'source_revision':doc['revision']}
    if selection is not None:result['shot_ids']=list(selection)
    return result

def legacy_binding_matches(doc,source):
    """Read old confirmation bindings without invalidating unrelated local scopes."""
    sid=source.get('section_id');c=production.state(doc)['confirmations'].get(sid)
    if not c or source.get('document_id')!=doc['id'] or source.get('fingerprint')!=c['fingerprint']:return False
    if source.get('source_timebase','section')!='section':return False
    current=current_shots(doc,sid);original=[s for g in c['snapshot']['groups'] for s in g['shots']]
    selected=source.get('shot_ids')
    if selected is None:return production.confirmation_status(doc,sid)=='confirmed'
    old_ids=[s['id'] for s in original];new_ids=[s['id'] for s in current]
    if any(sid not in old_ids for sid in selected):return False
    if c['context'].get('brief')!=doc.get('brief') or c['context'].get('source_text','')!=doc.get('source_text',''):return False
    wanted=set(selected)
    return ([s for s in original if s['id'] in wanted]==[s for s in current if s['id'] in wanted]
            and scope_notes(c['snapshot'],wanted)==scope_notes(production.sections(doc)[sid],wanted)
            and [[s['id'],s['duration']] for s in original[:old_ids.index(selected[0])]]
            ==[[s['id'],s['duration']] for s in current[:new_ids.index(selected[0])]])

def scoped_timeline(shots,fps,selection=None,timebase='section'):
    selected=scope_ids(shots,selection);ids=[s['id'] for s in shots]
    if timebase not in ('section','local'):raise ValueError('source_timebase须为section或local')
    if timebase=='local':shots=[s for s in shots if s['id'] in selected];ids=[s['id'] for s in shots]
    wanted=set(selection or ids);elapsed=Fraction(0);previous=0;result=[]
    last=ids.index(selection[-1]) if selection else len(shots)-1
    for shot in shots[:last+1]:
        duration=shot['duration']
        if type(duration) not in (int,float) or not math.isfinite(duration) or duration<=0:
            raise ValueError('相关镜头时长未确定，不能建立帧时序：'+shot['number'])
        elapsed+=Fraction(str(duration));end=round(elapsed*Fraction(str(fps)))
        if end<=previous:raise ValueError('当前fps无法表达镜头时长')
        if shot['id'] in wanted:result.append((shot,previous+1,end))
        previous=end
    return result

def prepare(doc,sid,engineering):
    shots=current_shots(doc,sid);timebase=engineering.get('source_timebase','section')
    source=binding(doc,sid,engineering.get('shot_ids'),timebase)
    fps=engineering['fps']
    if type(fps) not in (int,float) or not math.isfinite(fps) or fps<=0:raise ValueError('fps必须为有效正数')
    cameras=engineering.get('cameras',{})
    assets=copy.deepcopy(engineering.get('assets',[]));ids={a['id'] for a in assets}
    selected=engineering.get('shot_ids')
    timeline=scoped_timeline(shots,fps,selected,timebase)
    offset=timeline[0][1]-1 if timeline else 0
    result_shots=[];cuts=[];previous=0
    for shot,source_start,source_end in timeline:
        camera=copy.deepcopy(cameras.get(shot['id'],{}))
        if not camera.get('id') or type(camera.get('lens_mm')) not in (int,float) or not math.isfinite(camera['lens_mm']) or camera['lens_mm']<=0 or camera.get('focus_target') not in ids:raise ValueError('缺少镜头工程机位、焦段或声明的焦点对象：'+shot['number'])
        end=source_end-offset
        result_shots.append({'id':shot['id'],'number':shot['number'],'frame_range':[previous+1,end],
            'dramatic_intent':shot['reason'] or shot['content'],'shot_size':shot['framing'],'camera':camera,
            'storyboard':{k:shot[k] for k in ('content','framing','camera','sound','start','end','transition')},
            'continuity_links':[]})
        if selected is not None and timebase=='section':result_shots[-1]['source_frame_range']=[source_start,source_end]
        cuts.append({'edit_frame':previous+1,'shot_id':shot['id'],'camera_id':camera['id'],'source_frame':previous+1});previous=end
    spec={'schema_version':'1.1','project':{'id':doc['id'],'seed':engineering.get('seed',0),'request_id':uuid.uuid4().hex},
        'source_binding':source,'scene':{'id':engineering['scene_id'],'units':'m','up_axis':'Z','fps':fps,'frame_start':1,'frame_end':previous},
        'assets':assets,'shots':result_shots,'sequence':{'timeline_fps':fps,'camera_cuts':cuts},
        'events':copy.deepcopy(engineering.get('events',[])),'continuity':{'links':[]},
        'budgets':copy.deepcopy(engineering['budgets']),'performance':copy.deepcopy(engineering['performance']),
        'warnings':['Derived plan only; Blender objects, animation, visual quality and viewport FPS are not verified.']}
    for a,b in zip(result_shots,result_shots[1:]):
        spec['continuity']['links'].append({'from_shot':a['id'],'to_shot':b['id'],'from_frame':a['frame_range'][1],'to_frame':b['frame_range'][0],
            'handoff_state':{'end':a['storyboard']['end'],'start':b['storyboard']['start'],'transition':a['storyboard']['transition']},
            'allowed_error':{'status':'unverified','note':'按实际事件选择容差'}})
    for key in ('blocking','previs_profile','contact_hand_plan','scene_research_manifest','design_intent','asset_uses','directing','assumptions','source_refs','render','reference_roles'):
        if key in engineering:spec[key]=copy.deepcopy(engineering[key])
    for container,reserved in [('sequence',{'timeline_fps','camera_cuts'}),('scene',{'id','units','up_axis','fps','frame_start','frame_end'})]:
        extra=engineering.get(container,{})
        if not isinstance(extra,dict):raise ValueError(container+'工程扩展须为对象')
        for key,value in extra.items():
            if key in reserved and value!=spec[container].get(key):raise ValueError('工程扩展不能覆盖分镜时间或身份：'+container+'.'+key)
            spec[container][key]=copy.deepcopy(value)
    known={'shot_ids','source_timebase','scene_id','fps','seed','assets','cameras','budgets','performance','events','blocking','previs_profile','contact_hand_plan','scene_research_manifest','design_intent','asset_uses','directing','assumptions','source_refs','render','reference_roles','scene','sequence'}
    spec['unmapped_engineering']={k:copy.deepcopy(v) for k,v in engineering.items() if k not in known}
    if spec['unmapped_engineering']:spec['warnings'].append('Unmapped engineering fields retained for review: '+', '.join(spec['unmapped_engineering']))
    return spec

def check(doc,spec,project_root):
    a=Audit(project_root);check_scene(a,spec)
    source=spec.get('source_binding',{})
    if not isinstance(source,dict):a.error('STORYBOARD_BINDING_STALE');return a.result()
    timebase=source.get('source_timebase','section')
    try:
        expected=binding(doc,source.get('section_id'),source.get('shot_ids'),timebase)
        shots=current_shots(doc,expected['section_id'])
    except ValueError as e:a.error('STORYBOARD_NOT_AUTHORIZED',detail=str(e));return a.result()
    if source.get('scope_version')==2:
        matches=all(source.get(k)==expected[k] for k in ('document_id','section_id','fingerprint'))
    elif 'scope_version' not in source:matches=legacy_binding_matches(doc,source)
    else:matches=False
    if not matches:a.error('STORYBOARD_BINDING_STALE')
    fps=spec.get('scene',{}).get('fps')
    if type(fps) not in (int,float) or not math.isfinite(fps) or fps<=0:
        a.error('STORYBOARD_TIMING_DRIFT');return a.result()
    try:timeline=scoped_timeline(shots,fps,source.get('shot_ids'),timebase)
    except ValueError as e:
        a.error('STORYBOARD_SHOT_ORDER_MISMATCH',detail=str(e));return a.result()
    if [s.get('id') for s in spec.get('shots',[])]!=[s['id'] for s,_,_ in timeline]:a.error('STORYBOARD_SHOT_ORDER_MISMATCH')
    offset=timeline[0][1]-1 if timeline else 0
    for (original,source_start,source_end),derived in zip(timeline,spec.get('shots',[])):
        if derived.get('number')!=original['number'] or derived.get('shot_size')!=original['framing'] or derived.get('dramatic_intent')!=(original['reason'] or original['content']):a.error('STORYBOARD_CONSUMER_FIELD_DRIFT',shot=original['id'])
        if derived.get('storyboard')!={k:original[k] for k in ('content','framing','camera','sound','start','end','transition')}:a.error('STORYBOARD_CONTENT_DRIFT',shot=original['id'])
        if derived.get('frame_range')!=[source_start-offset,source_end-offset]:a.error('STORYBOARD_TIMING_DRIFT',shot=original['id'])
        if 'shot_ids' in source and timebase=='section' and derived.get('source_frame_range')!=[source_start,source_end]:a.error('STORYBOARD_SOURCE_TIMING_DRIFT',shot=original['id'])
        if timebase=='local' and 'source_frame_range' in derived:a.error('STORYBOARD_SOURCE_TIMING_DRIFT',shot=original['id'])
    return a.result()

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('command',choices=['prepare','check'])
    ap.add_argument('--directory',required=True);ap.add_argument('--section-id');ap.add_argument('--engineering');ap.add_argument('--spec');ap.add_argument('--output');ap.add_argument('--project-root',required=True)
    args=ap.parse_args();doc=Store(args.directory).read()
    try:
        if args.command=='prepare':
            if not(args.section_id and args.engineering and args.output):raise ValueError('prepare需要section-id、engineering、output')
            target=Path(args.output)
            if target.exists():raise ValueError('输出已存在，使用新的工程版本路径')
            spec=prepare(doc,args.section_id,json.loads(Path(args.engineering).read_text()))
        else:
            if not args.spec:raise ValueError('check需要spec')
            spec=json.loads(Path(args.spec).read_text())
        result=check(doc,spec,args.project_root)
        if args.command=='prepare' and not result['errors']:
            target.parent.mkdir(parents=True,exist_ok=True);atomic(target,json.dumps(spec,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
            result['output']=str(target.resolve())
        print(json.dumps(result,ensure_ascii=False,indent=2));return 1 if result['errors'] or result['warnings'] else 0
    except (ValueError,KeyError,TypeError,OSError) as e:
        ap.exit(2,str(e)+'\n')

if __name__=='__main__':raise SystemExit(main())
