'use strict';
// Shared shell only: Codex's native tools perform thread work and online research.
let referenceQuery='',referenceFeedback='',referenceScope='',directiveDraft='',directiveEditId=null,directiveEditVersion=0,directiveTargets=new Set();
let stylePanelInitialized=false,styleAtlasController=null;

async function workspaceCommand(command,message){
 await save();
 if(dirty||saving||blocked){notice('请先保存当前修改并处理冲突；本次操作尚未写入。');return false;}
 saving=true;const sentVersion=version,snapshot=clone(doc);state('正在保存工作安排…');
 try{
  const result=await api('/api/workspace',{command,expected_revision:savedRevision});
  let merged;
  try{merged=version===sentVersion?result:{...result,...mergePending(editableSnapshot(snapshot),editableSnapshot(doc),editableSnapshot(result))};}
  catch(error){blocked=true;throw error;}
  doc=merged;baseDocument=clone(result);savedRevision=result.revision;doc.revision=savedRevision;
  dirty=version!==sentVersion;
  if(dirty)persist();else localStorage.removeItem(draftKey());
  renderPreservingFocus();notice(doc._export_warning||message||'已保存');
  return true;
 }catch(error){
  if(error.status===409)blocked=true;
  if(dirty||blocked)persist();
  notice('操作未完成：'+error.message);return false;
 }finally{
  saving=false;state(blocked?'存在冲突 · 修改保留':dirty?'等待保存':'已保存 · 修订 '+savedRevision);
  if(dirty&&!blocked){clearTimeout(timer);timer=setTimeout(save,0);}
 }
}
function workspaceHeading(title,description){const head=el('div',{class:'workspace-heading'});head.append(el('h1',{},title),el('p',{},description));return head;}
function labeledControl(label,node){const wrap=el('label',{class:'workspace-field'});wrap.append(el('span',{},label),node);return wrap;}
async function copyWorkspaceText(text){
 try{await navigator.clipboard.writeText(text);notice('已复制，可在当前Codex对话中使用。');}
 catch{const field=el('textarea',{'aria-label':'可复制的请求文本',class:'copy-fallback'});field.value=text;$('notice').replaceChildren(field);$('notice').hidden=false;field.focus();field.select();}
}
function renderProjectOverview(){
 const root=$('project-overview');root.replaceChildren();const state=doc._coordination||{mode:'single',items:[],directives:[],pending_count:0};
 root.append(workspaceHeading('项目与协作','先看清内容与关联，再选择工作方式。单会话也可以一段一段推进。'));
 const modes=el('div',{class:'work-mode-grid'});
 for(const [mode,title,detail] of [['single','单会话制作','在当前会话掌握全片，按需要逐条、逐段完成。'],['coordinated','总控＋分段并行','总控统一方向和共用资料，执行会话分别完成所负责的内容。']]){
  const card=el('article',{class:'work-mode '+(state.mode===mode?'selected':'')});card.append(el('h2',{},title),el('p',{},detail));
  const choose=button(state.mode===mode?'当前模式':'选择此模式',()=>workspaceCommand({area:'coordination',command:{op:'set_mode',mode}},'工作模式已记录；会话建立与同步由Codex执行。'),'primary');choose.disabled=state.mode===mode;card.append(choose);modes.append(card);
 }
 root.append(modes);
 if(state.mode==='coordinated'){
  const info=el('section',{class:'workspace-note'});info.append(el('strong',{},state.controller?.title||state.controller_title||'项目总控'),el('p',{},state.controller?'总控会话已登记，执行条目及同步进度见下方。':'已选择并行模式，等待Codex建立或登记真实会话。'));
  root.append(info);
 }
 const items=el('section',{class:'work-items'});items.append(el('h2',{},'内容划分与执行会话'));
 if(!state.items.length)items.append(el('p',{class:'empty'},'项目信息与风格明确后，助手在这里列出制作条目、关联组和各段职责；无需你填写系统字段。'));
 const groups=new Map();for(const item of state.items){const key=item.group_id||'';if(!groups.has(key))groups.set(key,[]);groups.get(key).push(item);}
 const labels={planned:'待推进',working:'制作中',blocked:'有待处理事项',done:'已完成'};
 for(const [group,list] of groups){const block=el('section',{class:'work-group'});block.append(el('h3',{},group?'关联组 · '+group:'独立条目'));
  for(const item of list){const row=el('article',{class:'work-item'});row.append(el('h4',{},item.title),el('p',{},item.summary));const meta=el('p',{class:'workspace-meta'},labels[item.status]||item.status);if(item.thread_id)meta.append(el('span',{},' · 执行会话已登记'));else meta.append(el('span',{},state.mode==='coordinated'?' · 待分配会话':' · 当前会话推进'));row.append(meta);
   if(item.pending_directive_ids?.length)row.append(el('p',{class:'sync-pending'},item.pending_directive_ids.length+' 项共用要求待落实'));
   const details=el('details');details.append(el('summary',{},'查看工作范围'),el('p',{},'作品：'+item.work_id),el('p',{},'制作目录：'+item.directory));if(item.thread_id)details.append(el('p',{},'会话标识：'+item.thread_id));row.append(details);block.append(row);
  }items.append(block);
 }root.append(items);
 const shared=el('section',{class:'shared-directives'});shared.append(el('h2',{},'共用要求与变更同步'));
 shared.append(el('p',{class:'workspace-meta'},state.mode==='coordinated'?'总控向适用条目下发；发送成功与实际落实分别记录，原制作阶段继续保留。':'共用要求应用到所选条目，由当前会话按内容推进。'));
 const statuses={unassigned:'待分配',pending:'待同步',sent:'已发送 · 待落实',applied:'已落实',blocked:'受阻'};
 for(const directive of state.directives){const card=el('article',{class:'directive-card'});card.append(el('p',{class:'creative-text'},directive.text),el('small',{},'第 '+directive.version+' 版'));
  const list=el('ul');for(const target of directive.targets||[]){const item=state.items.find(x=>x.id===target.item_id),receipt=target.receipt;const currentReceipt=receipt&&receipt.version===target.version&&receipt.thread_id===item?.thread_id;const summary=receipt?.summary?' · '+(currentReceipt?'':'历史回报（第'+receipt.version+'版）：')+receipt.summary:'';list.append(el('li',{},(item?.title||target.item_id)+'：'+(statuses[target.status]||target.status)+summary));}card.append(list);
  card.append(button('调整这条要求',()=>{directiveEditId=directive.id;directiveEditVersion=directive.version;directiveDraft=directive.text;directiveTargets=new Set(directive.item_ids);renderProjectOverview();$('directive-text')?.focus();},'secondary'));shared.append(card);
 }
 if(state.items.length){
  const form=el('form',{class:'directive-form'}),field=el('textarea',{id:'directive-text',rows:'3','data-target-id':doc.id,'data-key':'directive-draft',placeholder:'例如：选中的条目统一采用同一角色参考；保留各条已经确定的内容。'});field.value=directiveDraft;field.oninput=()=>{directiveDraft=field.value;};form.append(labeledControl(directiveEditId?'调整共用要求':'新增共用要求',field));
  const targets=el('fieldset');targets.append(el('legend',{},'应用到哪些条目'));
  for(const item of state.items){const checkbox=el('input',{type:'checkbox',value:item.id});checkbox.checked=directiveTargets.has(item.id);checkbox.onchange=()=>checkbox.checked?directiveTargets.add(item.id):directiveTargets.delete(item.id);const label=el('label');label.append(checkbox,document.createTextNode(item.title));targets.append(label);}form.append(targets);
  const submit=el('button',{type:'submit',class:'primary'},state.mode==='coordinated'?'交给总控同步':'保存共用要求');form.append(submit);
  form.onsubmit=async event=>{event.preventDefault();if(!directiveDraft.trim()||!directiveTargets.size){notice('请写明共用要求并选择适用条目。');return;}
   const sentDraft=directiveDraft,sentEditId=directiveEditId,sentEditVersion=directiveEditVersion,sentTargets=[...directiveTargets];
   const command={op:'upsert_directive',directive:{id:directiveEditId||'directive-'+uid(),text:directiveDraft.trim(),item_ids:[...directiveTargets]},expected_version:directiveEditId?directiveEditVersion:0};
   if(await workspaceCommand({area:'coordination',command},'共用要求已记录，等待总控下发并回读落实结果。')){if(directiveDraft===sentDraft&&directiveEditId===sentEditId&&directiveEditVersion===sentEditVersion&&JSON.stringify([...directiveTargets])===JSON.stringify(sentTargets)){directiveDraft='';directiveEditId=null;directiveEditVersion=0;directiveTargets.clear();}renderProjectOverview();}
  };shared.append(form);
 }
 root.append(shared);
 const timing=doc._pacing;
 if(timing){const block=el('section',{class:'workspace-note'});block.append(el('h2',{},'当前内容时间'),el('p',{},timing.content_duration_seconds!==null?timing.content_duration_seconds+' 秒 · 依据当前逐镜安排':timing.known_duration_seconds+' 秒已知，另有 '+timing.unknown_shot_ids.length+' 镜待估'));block.append(el('p',{class:'workspace-meta'},'按正常动作、声音及信息辨认需要估算；平台档位和额外裁切余量在生成方案中单列。'));root.append(block);}
}
function renderCreativeReferences(){
 const root=$('creative-references');root.replaceChildren();const view=doc._references||{},current=view.current;
 root.append(workspaceHeading('创意镜头参考','特殊运镜、形变、穿越或难以描述的视觉效果，都可以用真实片段来对齐。找到三个即停，单轮软上限四分钟。'));
 const form=el('form',{class:'reference-request-form'}),query=el('textarea',{id:'reference-query',rows:'3','aria-label':'想找的画面效果','data-target-id':doc.id,'data-key':'reference-query',placeholder:'描述想发生的变化即可，不必知道专业技法名称。'});query.value=referenceQuery;query.oninput=()=>{referenceQuery=query.value;};form.append(labeledControl('想找的画面效果',query));
 const scope=el('select',{'aria-label':'参考用于哪里'});scope.append(el('option',{value:''},'当前作品 / 尚未分段'));for(const section of doc.sections)scope.append(el('option',{value:section.id},section.title));scope.value=referenceScope;scope.onchange=()=>{referenceScope=scope.value;};form.append(labeledControl('用于哪里',scope));
 const send=el('button',{type:'submit',class:'primary'},'交给助手找三个参考');form.append(send);form.onsubmit=async event=>{event.preventDefault();if(!referenceQuery.trim()){notice('先描述想看到的画面变化。');return;}
  const sentQuery=referenceQuery,sentScope=referenceScope;const command={action:'request',query:referenceQuery.trim(),scope:referenceScope?{section_id:referenceScope}:null};
  if(await workspaceCommand({area:'references',command},'参考需求已记录；助手开始处理时计时，找到三个或达到四分钟即收口。')){if(referenceQuery===sentQuery&&referenceScope===sentScope)referenceQuery='';renderCreativeReferences();}
 };root.append(form);
 if(current){
  const labels={request:'待助手检索 · 尚未开始计时',searching:'正在寻找参考',ready:'本轮参考已收口',exhausted:'本轮检索已结束'};
  const status=el('section',{class:'reference-round'});status.append(el('h2',{},labels[current.status]||current.status),el('p',{},current.query));
  if(current.status==='searching')status.append(el('p',{class:'workspace-meta'},'当前已找到 '+view.valid_count+' / 3 个匹配示例；本轮开始：'+new Date(current.started_at).toLocaleTimeString()));
  if(current.status==='exhausted')status.append(el('p',{class:'workspace-meta'},'未满三个也按实际结果交付，继续制作不依赖凑齐参考。'));
  if(current.request_feedback)status.append(el('p',{},'上一轮反馈：'+current.request_feedback));
  if(current.status==='request')status.append(button('复制检索请求',()=>copyWorkspaceText('请处理工作台当前创意参考请求：'+current.query+'。读取当前参考轮次后开始，限定已选来源，找三个即停，软上限四分钟。')));
  root.append(status);
  const cards=el('div',{class:'reference-cards'});
  for(const candidate of current.candidates||[]){const card=el('article',{class:'reference-card'});card.append(el('h3',{},candidate.title));
   if(candidate.preview_url){let preview;if(candidate.preview_kind==='video'){preview=el('video',{src:candidate.preview_url,controls:'',preload:'none',playsinline:'','aria-label':candidate.title});}else preview=el('img',{src:candidate.preview_url,alt:candidate.title,loading:'lazy',referrerpolicy:'no-referrer'});preview.onerror=()=>{preview.hidden=true;const message=el('p',{class:'workspace-meta'},'预览暂不可用，可以打开原站查看。');card.prepend(message);};card.append(preview);}
   else card.append(el('div',{class:'reference-placeholder'},'打开原站观看对应效果'));
   const source=view.sources?.find(x=>x.id===candidate.source_id);card.append(el('p',{class:'workspace-meta'},(source?.label||candidate.source_id)+' · '+(candidate.observation==='viewed'?'已查看对应效果':'动态尚待核实')));
   if(candidate.watch_range)card.append(el('p',{},'看这里：'+candidate.watch_range));
   card.append(el('p',{},'接近之处：'+candidate.match_reason),el('p',{},'差异：'+candidate.difference),el('p',{},'可借鉴：'+candidate.reuse_note));
   card.append(el('a',{href:candidate.source_url,target:'_blank',rel:'noopener noreferrer',class:'source-link'},'在原站观看 ↗'));
   if(candidate.matched){const chosen=current.chosen_candidate_id===candidate.id;const choose=button(chosen?'已选择这个参考':'选择这个方向',()=>workspaceCommand({area:'references',command:{action:'choose',session_id:current.id,candidate_id:candidate.id,adoption_note:candidate.reuse_note}},'已记录所选效果，后续仅继承这些特征，保留已有镜头要求。'),'primary');choose.disabled=chosen;card.append(choose);}
   cards.append(card);
  }root.append(cards);
  for(const restriction of current.restrictions||[]){const note=el('aside',{class:'workspace-note'});note.append(el('strong',{},'来源访问限制'),el('p',{},(view.sources?.find(x=>x.id===restriction.source_id)?.label||restriction.source_id)+'：'+restriction.capability+' · '+restriction.reason),el('p',{},'可考虑的价值：'+restriction.value));root.append(note);}
  if(current.chosen_candidate_id)root.append(el('p',{class:'selected-reference'},'已选特征：'+current.adoption_note));
  if(current.candidates?.length||['ready','exhausted'].includes(current.status)){
   const feedback=el('textarea',{rows:'2','aria-label':'换一组的反馈','data-target-id':doc.id,'data-key':'reference-feedback',placeholder:'哪里不接近？例如要连续形变，不要硬切。'});feedback.value=referenceFeedback;feedback.oninput=()=>{referenceFeedback=feedback.value;};
   const next=button('这组不合适，换三个',async()=>{const sentFeedback=referenceFeedback;const feedbackText=referenceFeedback.trim()||'用户在工作台明确表示本组不合适，请换一组。';if(await workspaceCommand({area:'references',command:{action:'reject',session_id:current.id,feedback:feedbackText}},'已记录换组请求；下一轮会避开已否定的例子。')){if(referenceFeedback===sentFeedback)referenceFeedback='';renderCreativeReferences();}},'secondary');root.append(labeledControl('哪里不接近（可选）',feedback),next);
  }
 }
 const sources=el('details',{class:'reference-sources'});sources.append(el('summary',{},'限定来源与会员提示'));
 for(const source of view.sources||[])sources.append(el('p',{},(source.label||source.id)+'：'+(source.use||'')));
 sources.append(el('p',{},'按当前摄影或动画需求选择相关来源，不逐站遍历。会员或配额限制会明确告知；不自动购买，也不扩展全网。'));root.append(sources);
}
async function renderStyleLibrary(){
 const host=$('style-library');
 if(stylePanelInitialized)return;
 stylePanelInitialized=true;
 host.replaceChildren(el('p',{class:'empty'},'正在打开视觉定调页面…'));
 try{
  const [pageResponse,dataResponse]=await Promise.all([fetch('/style-atlas/index.html',{cache:'no-store'}),fetch('/style-atlas/atlas.json',{cache:'no-store'})]);
  if(!pageResponse.ok||!dataResponse.ok)throw new Error('视觉图库暂时无法读取');
  const parsed=new DOMParser().parseFromString(await pageResponse.text(),'text/html');
  const template=parsed.querySelector('[data-cinematic-atlas-root]');
  if(!template||!window.CinematicAtlas?.mount)throw new Error('视觉图库与工作台版本不一致，请恢复当前服务');
  const data=await dataResponse.json(),root=host.shadowRoot||host.attachShadow({mode:'open'});
  host.replaceChildren();root.innerHTML=template.innerHTML;
  const recommend=(new URLSearchParams(location.search).get('recommend')||'').split(',').filter(Boolean);
  styleAtlasController=window.CinematicAtlas.mount(root,data,{assetBase:'/style-atlas/',recommend,
   initialChoice:doc.workspace?.style_choice,
   onSave:choice=>workspaceCommand({area:'style',choice},'视觉定调选择已保存到当前工作台。')});
 }catch(error){
  stylePanelInitialized=false;
  const target=host.shadowRoot||host;target.replaceChildren(el('p',{class:'empty'},error.message),button('重新打开视觉定调',renderStyleLibrary));
 }
}
