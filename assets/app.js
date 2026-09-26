'use strict';
let doc, baseDocument, savedRevision, dirty=false, saving=false, blocked=false, version=0, timer, undoDoc=null, syncLost=false;
// Isolate unsaved drafts across tabs; a successful save in one tab must not erase another tab's work.
const tabKey='cinematic-storyboard-tab';
let tabId=sessionStorage.getItem(tabKey);
if(!tabId){tabId=crypto.randomUUID();sessionStorage.setItem(tabKey,tabId);}
const $=id=>document.getElementById(id), clone=x=>JSON.parse(JSON.stringify(x)), uid=()=>crypto.randomUUID();
const fields=['content','framing','camera','sound','start','end','transition','assets','reason','notes'];
const names={content:'内容与动作',framing:'景别与构图',camera:'机位与运动',sound:'声音',start:'开始状态',end:'结束状态',transition:'前后衔接',assets:'资产与参考',reason:'设计说明',notes:'备注'};
function el(tag,attrs={},text){const e=document.createElement(tag);for(const [k,v] of Object.entries(attrs)){if(k==='class')e.className=v;else e.setAttribute(k,v);}if(text!==undefined)e.textContent=text;return e;}
function button(text,fn,cls=''){const b=el('button',{type:'button',class:cls},text);b.onclick=fn;return b;}
function notice(text=''){ $('notice').textContent=text;$('notice').hidden=!text; }
function state(text){renderSectionStates();renderWorkflowStage();$('save-state').textContent=text;$('retry').hidden=!(dirty&&!saving&&!blocked);$('reload').hidden=!blocked;}
function draftKey(){return 'cinematic-storyboard:'+doc.id+':'+tabId;}
function persist(){try{localStorage.setItem(draftKey(),JSON.stringify({base_revision:savedRevision,document:doc}));}catch(e){notice('浏览器无法保存恢复草稿，请及时导出本地草稿。');}}
function mark(immediate=false){dirty=true;version++;persist();state(blocked?'存在冲突 · 本地修改已保留':'等待保存');totals();clearTimeout(timer);if(!blocked)timer=setTimeout(save,immediate?0:1000);}
async function api(path,body){let options={cache:'no-store'};if(body){const session=await fetch('/api/session',{cache:'no-store'});if(!session.ok)throw new Error('无法建立本地保存会话');const {token}=await session.json();options={method:'POST',headers:{'Content-Type':'application/json','X-Storyboard-Token':token},body:JSON.stringify(body)};}const r=await fetch(path,options);let data;try{data=await r.json();}catch(e){throw new Error('服务返回了无法读取的内容');}if(!r.ok){const e=new Error(typeof data.error==='string'?data.error:('请求失败（'+r.status+'）'));e.status=r.status;throw e;}return data;}
function editableSnapshot(value){return Object.fromEntries(Object.entries(value).filter(([key])=>key!=='production'&&key!=='workspace'&&key!=='revision'&&!key.startsWith('_')));}
function mergePending(base,local,remote){
 const same=(a,b)=>JSON.stringify(a)===JSON.stringify(b);
 if(same(local,base))return remote;
 if(same(remote,base)||same(local,remote))return local;
 if([base,local,remote].every(v=>v&&typeof v==='object'&&!Array.isArray(v))){
  const out={};for(const key of new Set([...Object.keys(base),...Object.keys(remote),...Object.keys(local)])){const value=mergePending(base[key],local[key],remote[key]);if(value!==undefined)out[key]=value;}return out;
 }
 if([base,local,remote].every(Array.isArray)&&[...base,...local,...remote].every(v=>v&&typeof v.id==='string')){
  const lists=[base,local,remote].map(v=>v.map(x=>x.id));
  const order=same(lists[1],lists[0])?lists[2]:same(lists[2],lists[0])||same(lists[1],lists[2])?lists[1]:null;
  if(!order)throw new Error('保存期间双方同时改变镜头顺序；本地草稿已保留。');
  const maps=[base,local,remote].map(v=>new Map(v.map(x=>[x.id,x]))),values=new Map();
  for(const id of new Set(lists.flat()))values.set(id,mergePending(...maps.map(m=>m.get(id))));
  return order.map(id=>values.get(id)).filter(v=>v!==undefined);
 }
 throw new Error('保存期间同一内容又有不同修改；本地草稿已保留。');
}
function renderPreservingFocus(){
 const focus=document.activeElement,id=focus?.dataset.targetId,key=focus?.dataset.key,start=focus?.selectionStart,end=focus?.selectionEnd,x=window.scrollX,y=window.scrollY;
 render();
 if(id&&key){const input=document.querySelector('[data-target-id="'+CSS.escape(id)+'"][data-key="'+CSS.escape(key)+'"]');if(input){input.focus({preventScroll:true});if(typeof start==='number')try{input.setSelectionRange(start,end);}catch{}}}
 window.scrollTo(x,y);
}
async function save(){
 if(!dirty||saving||blocked)return;
 saving=true;state('保存中…');const sentVersion=version,snapshot=clone(doc);
 try{
  const result=await api('/api/document',{document:snapshot,expected_revision:savedRevision,base_document:baseDocument});
  let merged;
  try{merged=version===sentVersion?result:{...result,...mergePending(editableSnapshot(snapshot),editableSnapshot(doc),editableSnapshot(result))};}
  catch(error){blocked=true;throw error;}
  savedRevision=result.revision;baseDocument=clone(result);doc=merged;doc.revision=savedRevision;
  dirty=version!==sentVersion;
  if(dirty)persist();else localStorage.removeItem(draftKey());
  renderPreservingFocus();notice(doc._export_warning||'');state(dirty?'等待保存':'已保存 · 修订 '+savedRevision);
 }catch(error){
  if(error.status===409||blocked){blocked=true;persist();notice(error.message+' 可导出本地草稿后与最新稿核对。');state('存在冲突 · 未覆盖已保存稿');}
  else{notice('保存失败：'+error.message+'。本地修改仍保留，请重试或导出草稿。');state('保存失败');}
 }finally{saving=false;renderSectionStates();$('retry').hidden=!(dirty&&!blocked);if(dirty&&!blocked&&version!==sentVersion)timer=setTimeout(save,0);}
}
function editField(obj,key,label,{type='textarea',className='',placeholder=''}={}){const wrap=el('label',{class:'field '+className});wrap.append(el('span',{},label));const input=el(type==='textarea'?'textarea':'input',{'aria-label':label,placeholder,'data-target-id':obj.id,'data-key':key});if(type!=='textarea')input.type=type;input.value=obj[key]??'';input.oninput=()=>{obj[key]=type==='number'?(input.value===''?null:Number(input.value)):input.value;mark();};wrap.append(input);return wrap;}
function titleInput(obj,key,label,cls=''){const i=el('textarea',{'aria-label':label,class:'title-control '+cls,rows:'1'});i.value=obj[key]||'';i.oninput=()=>{obj[key]=i.value;mark();renderNav();};return i;}
function mutate(fn){fn();mark(true);render();}
function removeItem(list,index){let parent=doc,key='sections';for(const section of doc.sections){if(section.groups===list){parent=section;key='groups';}for(const group of section.groups)if(group.shots===list){parent=group;key='shots';}}undoDoc={parentId:parent.id,key,index,item:clone(list[index])};$('undo').disabled=false;mutate(()=>list.splice(index,1));}
function move(list,index,delta){const target=index+delta;if(target<0||target>=list.length)return;mutate(()=>{const [item]=list.splice(index,1);list.splice(target,0,item);});}
function listTools(list,index,kind){const tools=el('div',{class:'tools'});const up=button('↑',()=>move(list,index,-1));up.setAttribute('aria-label','上移'+kind);up.disabled=index===0;const down=button('↓',()=>move(list,index,1));down.setAttribute('aria-label','下移'+kind);down.disabled=index===list.length-1;tools.append(up,down,button('删除'+kind,()=>removeItem(list,index),'danger'));return tools;}
function newShot(){const sh={id:uid(),number:'',duration:null};for(const f of fields)sh[f]='';return sh;}
function allGroups(){return doc.sections.flatMap(s=>s.groups.map(g=>({s,g})));}
function totals(){
 if(!doc)return;
 const shots=allGroups().flatMap(x=>x.g.shots),known=shots.filter(s=>Number.isFinite(s.duration)&&s.duration>0),total=known.reduce((n,s)=>n+s.duration,0),unknown=shots.length-known.length;
 let timing=known.length?'预计 '+Number(total.toFixed(2))+' 秒':'时长待定';
 if(unknown&&known.length)timing+=' + '+unknown+' 镜待定';
 const estimates=activeRecords().filter(record=>record.data?.decision_type==='pacing_revision_candidate'&&!doc._record_states?.[record.id]?.stale&&record.shot_ids?.length===shots.length&&shots.every(shot=>record.shot_ids.includes(shot.id))&&Number.isFinite(record.data?.proposed_duration_seconds));
 const latest=estimates.at(-1);
 if(latest&&Number(latest.data.proposed_duration_seconds)!==total)timing+=' · 新估约 '+latest.data.proposed_duration_seconds+' 秒（待同步）';
 const cancelled=cancelledSections(),allCancelled=doc.sections.length>0&&doc.sections.every(s=>cancelled.has(s.id));
 $('duration').textContent=allCancelled?'历史分镜 · '+shots.length+' 镜 · 无需制作':doc.sections.length+' 段落 · '+shots.length+' 镜 · '+timing;
 $('nav-count').textContent=shots.length+' 镜';$('rail-title').textContent=doc.title||'未命名分镜';document.title=(doc.title||'分镜工作台')+' · Cine AI Video Director';
}
function renderNav(){
 const nav=$('navigation');nav.replaceChildren();if(!doc)return;
 const query=($('nav-search').value||'').trim().toLocaleLowerCase();
 const match=(...v)=>v.join(' ').toLocaleLowerCase().includes(query);
 const groups=allGroups();let shown=0;
 nav.append(el('span',{class:'structure-total'},groups.length+' 个镜头组 · '+groups.reduce((n,{g})=>n+g.shots.length,0)+' 个镜头'));
 groups.forEach(({s,g},index)=>{
  const groupMatch=match(s.title,g.title);
  const visible=g.shots.map((shot,i)=>({shot,i})).filter(({shot})=>groupMatch||match(shot.number,shot.content));
  if(query&&!groupMatch&&!visible.length)return;
  shown++;
  const group=el('div',{class:'structure-group',role:'group','aria-label':'第 '+(index+1)+' 组：'+g.title});
  group.append(el('span',{class:'structure-label',title:s.title},'第 '+(index+1)+' 组 · '+(g.title||'未命名镜头组')+' · '+g.shots.length+' 镜'));
  for(const {shot,i} of visible)group.append(el('span',{class:'structure-shot',title:shot.content||'待填写镜头内容','aria-label':'组内第 '+(i+1)+' 镜'},String(i+1)));
  nav.append(group);
 });
 $('nav-empty').hidden=shown>0||!query;
}
// Each disclosure belongs to one document, stable shot ID and field; never to a whole card.
const shotFieldStates = new Map();
function renderShotFields(sh) {
 const body=el('div',{class:'shot-body'}),primary=el('div',{class:'shot-primary'});
 const toggles=el('div',{class:'shot-field-toggles',role:'group','aria-label':'逐项查看拍摄细节'}),panels=el('div',{class:'shot-field-panels'});
 function fieldControl(key) {
  const stateKey=JSON.stringify([doc.id,sh.id,key]),open=shotFieldStates.has(stateKey)?shotFieldStates.get(stateKey):key==='content';
  const id='shot-field-'+sh.id+'-'+key,control=button(names[key],()=>setOpen(panel.hidden),'shot-field-toggle');
  control.id=id+'-toggle';control.dataset.fieldToggle=key;control.setAttribute('aria-controls',id);
  const panel=el('div',{id,class:'shot-field-panel','data-field':key,role:'region','aria-labelledby':control.id});
  const field=editField(sh,key,names[key]);field.querySelector('textarea').rows=key==='content'?4:2;panel.append(field);
  function setOpen(value) {
   shotFieldStates.set(stateKey,value);panel.hidden=!value;control.setAttribute('aria-expanded',String(value));
   control.title=(value?'收起':'展开')+names[key];
  }
  panel.hidden=!open;control.setAttribute('aria-expanded',String(open));control.title=(open?'收起':'展开')+names[key];
  return {control,panel};
 }
 const content=fieldControl('content');primary.append(content.control,content.panel);body.append(primary);
 const advice=activeRecords().filter(r=>r.data?.decision_type==='generation_recommendation'&&doc._record_states?.[r.id]?.status!=='excluded').flatMap(r=>(r.data.groups||[]).filter(g=>g.shot_ids?.includes(sh.id)).map(g=>({record:r,group:g}))).at(-1);
 if(advice){const detail=el('details',{class:'shot-generation-advice'});detail.append(el('summary',{},'生成建议 · '+(advice.group.input_mode||'方式待定')),el('p',{},[advice.group.reason,advice.group.cost,advice.group.limits].filter(Boolean).join('；')));if(doc._record_states?.[advice.record.id]?.stale)detail.append(el('p',{class:'review-note'},'方案有调整，相关生成建议待同步；已选路线保留。'));primary.append(detail);}
 for(const key of fields.slice(1)){const item=fieldControl(key);toggles.append(item.control);panels.append(item.panel);}
 body.append(toggles,panels);return body;
}

function renderShot(sh,g,index){
 const card=el('article',{class:'shot',id:sh.id,'aria-label':'镜头 '+(sh.number||'未编号')});
 const ordinal=allGroups().flatMap(x=>x.g.shots).findIndex(x=>x.id===sh.id)+1;
 const top=el('div',{class:'shot-top'});top.append(el('span',{class:'shot-ordinal',title:'当前排列第 '+ordinal+' 镜'},String(ordinal).padStart(2,'0')),editField(sh,'number','镜号 / SHOT',{type:'text',className:'shot-number',placeholder:'填写镜号'}),editField(sh,'duration','预计时长 / 秒',{type:'number',className:'shot-duration',placeholder:'待定'}));
 const duration=top.querySelector('input[type=number]');duration.min='0';duration.step='0.1';
 const tools=listTools(g.shots,index,'镜头');tools.prepend(button('复制',()=>mutate(()=>{const copy=clone(sh);copy.id=uid();copy.number=sh.number?sh.number+'-副本':'';g.shots.splice(index+1,0,copy);})));
 const select=el('select',{'aria-label':'将镜头移动到镜头组'});for(const {s,g:target} of allGroups()){const option=el('option',{value:target.id},s.title+' / '+target.title);option.selected=target.id===g.id;select.append(option);}
 select.onchange=()=>mutate(()=>{const target=allGroups().find(x=>x.g.id===select.value).g;g.shots.splice(index,1);target.shots.push(sh);});
 const movePanel=el('details',{class:'shot-move'}),moveLabel=el('label',{class:'field'},'所属镜头组');movePanel.append(el('summary',{},'移动至…'));moveLabel.append(select);movePanel.append(moveLabel);tools.append(movePanel);top.append(tools);
 const body=renderShotFields(sh);card.append(top,body);return card;
}
// Presentation-only state. No changes to document schema, saving, confirmation or production APIs.
const openPanels=new Set();let activeTarget='';
function disclosure(key,label,cls){const node=el('details',{class:cls});node.open=openPanels.has(key);node.append(el('summary',{},label));node.ontoggle=()=>{if(node.open)openPanels.add(key);else openPanels.delete(key);};return node;}
function contextNotes(obj,label,key,cls='context-notes'){const node=disclosure(key,label,cls);node.append(editField(obj,obj===doc?'brief':'notes',label));return node;}
function viewIcon(name){const ns='http://www.w3.org/2000/svg',svg=document.createElementNS(ns,'svg');svg.setAttribute('viewBox','0 0 24 24');svg.setAttribute('class','view-icon');svg.setAttribute('aria-hidden','true');const p=document.createElementNS(ns,'path');p.setAttribute('d',name==='preview'?'M3 3h7v7H3z M14 3h7v7h-7z M3 14h7v7H3z M14 14h7v7h-7z':name==='assets'?'M3 4h8v7H3z M13 4h8v7h-8z M3 14h18v6H3z':'M4 4h16v16H4z M8 8h8 M8 12h8 M8 16h5');svg.append(p);return svg;}
function selectTarget(id){activeTarget=id;document.querySelectorAll('.shot.is-active').forEach(n=>n.classList.remove('is-active'));const item=$(id);if(item?.classList.contains('shot'))item.classList.add('is-active');document.querySelectorAll('#navigation a').forEach(a=>{if(a.dataset.target===id)a.setAttribute('aria-current','location');else a.removeAttribute('aria-current');});}
$('nav-search').addEventListener('input',renderNav);
$('editor').addEventListener('focusin',e=>{const target=e.target.closest('.shot,.group,.section');if(target)selectTarget(target.id);});
$('editor').addEventListener('input',e=>{if(e.target.closest('.shot'))renderNav();if(e.target.closest('.doc-head')){$('rail-title').textContent=doc.title||'未命名分镜';}});
const chromeObserver=new ResizeObserver(entries=>{document.documentElement.style.setProperty('--chrome-height',Math.ceil(entries[0].target.getBoundingClientRect().height)+'px');});
chromeObserver.observe(document.querySelector('.sticky-chrome'));


let activeView='storyboard';
function setView(id){
 if(!doc)return;
 activeView=id;document.body.dataset.view=id;try{sessionStorage.setItem('cinematic-view:'+doc.id,id);}catch{}
 $('editor').hidden=id!=='storyboard';
 $('image-preview').hidden=id!=='preview';
 $('asset-preview').hidden=id!=='assets';
 $('project-overview').hidden=id!=='project';
 $('creative-references').hidden=id!=='references';
 $('style-library').hidden=id!=='style';
 if(id==='project')renderProjectOverview();
 if(id==='references')renderCreativeReferences();
 if(id==='style')renderStyleLibrary();
 if(id==='preview')renderImagePreview();
 if(id==='assets')renderImageAssets();
 renderViewNavigation();
}
function renderViewNavigation(){
 const nav=$('view-navigation');nav.replaceChildren();nav.hidden=false;
 const referenceTool=$('find-reference');referenceTool.classList.toggle('active',activeView==='references');referenceTool.setAttribute('aria-pressed',String(activeView==='references'));
 for(const [id,label] of [['project','项目与协作'],['style','视觉定调'],['storyboard','文字分镜'],['assets','分镜所用资产'],['preview','分镜预览']]){
  const b=button(label,()=>setView(id),id===activeView?'active':'');b.prepend(viewIcon(id));b.setAttribute('aria-pressed',String(id===activeView));nav.append(b);
 }
}
function renderImagePreview(){
 clearTimeout(rehearsalTimer);
 const root=$('image-preview');root.replaceChildren();
 const heading=el('div',{class:'preview-heading'});heading.append(el('h1',{},'分镜图预览'),el('p',{},'按当前分镜顺序展示，每张图独立编号；待选、已采用和需复核分别标明。'));root.append(heading);renderSequencePlan(root);renderGenerationInputs(root);
 const ordered=el('section',{'aria-label':'按镜号排列的分镜图',class:'preview-sequence'});root.append(ordered);
 const rows=(doc._preview_rows||[]).filter(row=>row.images?.length);
 if(!rows.length){ordered.append(el('p',{class:'empty'},'还没有已登记的分镜图。'));return;}
 let sequenceNumber=0;
 for(const row of rows){
  const card=el('article',{class:'preview-card sequence-card'});card.dataset.shotId=row.shot_id;
  card.append(el('h2',{},row.number||'未编号镜头'));
  let imageIndex=0;
  for(const item of row.images){
   imageIndex++;
   sequenceNumber++;
   const imageNumber=String(sequenceNumber).padStart(2,'0');
   const url='/api/image?record='+encodeURIComponent(item.record_id)+'&file='+item.file_index;
   const link=el('a',{href:url,target:'_blank',rel:'noopener','aria-label':'查看图 '+imageNumber+' · '+(row.number||'未编号镜头')+' 第'+imageIndex+'张原图'});
   if(item.box){
    const [x,y,right,bottom]=item.box,[w,h]=item.size,cw=right-x,ch=bottom-y;
    const crop=el('div',{role:'img','aria-label':row.number+' 采用画格'});
    crop.style.cssText='width:100%;aspect-ratio:'+cw+'/'+ch+';background-image:url("'+url+'");background-repeat:no-repeat;background-size:'+(100*w/cw)+'% '+(100*h/ch)+'%;background-position:'+(w===cw?0:100*x/(w-cw))+'% '+(h===ch?0:100*y/(h-ch))+'%';link.append(crop);
   }else{
    const img=el('img',{src:url,alt:row.number+' 分镜图',loading:'lazy',decoding:'async'});
    img.onerror=()=>{img.hidden=true;link.append(el('span',{class:'image-error'},'图片无法读取，请核对原文件。'));};
    link.append(img);
   }
   const frame=el('div',{class:'preview-item'});
   const labels=el('div',{class:'preview-image-labels'});
   labels.append(el('span',{class:'preview-image-number','aria-label':'图片序号 '+sequenceNumber},'图 '+imageNumber),el('span',{class:'badge '+(item.review_status==='candidate'?'preview-pending':'')},({candidate:'待选',adopted:'已采用',revise:'待修改',needs_review:'原图保留 · 需复核'}[item.review_status]||'状态待核')));
   frame.append(labels,link,el('p',{class:'preview-file'},item.path.split('/').pop()));if(item.reason)frame.append(el('p',{class:'preview-pending'},item.reason));
   card.append(frame);
  }
  ordered.append(card);
 }
}
function renderGenerationInputs(root){
 const packages=activeRecords().filter(r=>r.kind==='package'&&doc._record_states?.[r.id]?.status!=='excluded');
 if(!packages.length)return;
 const section=el('section',{'aria-label':'实际生成输入',class:'sequence-review-panel'});
 section.append(el('h2',{},'当前准备的生成输入'),el('p',{class:'review-note'},'以下来自当前生成包，与供审阅的图序分开。实际节点写入和提交仍以回读记录为准。'));
 for(const pack of packages){
  const d=pack.data||{},card=el('article',{class:'generation-plan'});
  card.append(el('h3',{},pack.title),el('p',{},[d.model,d.platform,d.input_mode||d.mode].filter(Boolean).join(' · ')));
  if(doc._record_states?.[pack.id]?.stale)card.append(el('p',{class:'review-note'},'依据已有修改，本包待同步；保留原输入供回查。'));
  const list=el('ul');for(const ref of d.references||[])list.append(el('li',{},[ref.label,ref.purpose,ref.file_path].filter(Boolean).join(' — ')));
  if(!(d.references||[]).length)list.append(el('li',{},'本包没有上传参考附件。'));
  card.append(list);
  if(d.prompt){const details=el('details');details.append(el('summary',{},'查看本包准确提示词'),el('p',{class:'creative-text'},d.prompt));card.append(details);}
  section.append(card);
 }
 root.append(section);
}
function recommendationLabel(data){return ({supported:'推荐',provisional:'暂定推荐',user_specified:'用户指定'})[data.selection_basis?.status]||'推荐';}
function renderSelectionBasis(parent,data){
 const basis=data.selection_basis;
 if(!basis){
  if((data.options||[]).some(option=>option.recommended))parent.append(el('p',{class:'review-note'},'这份建议尚未单独记录模型间的比较依据；已有选择保留，续做时按需要补充。'));
  return;
 }
 const box=el('section',{class:'generation-route recommendation-basis','aria-label':'为什么推荐这个方案'});
 box.append(el('h4',{},'为什么推荐这个方案'),el('span',{class:'badge'},recommendationLabel(data)));
 const primary=(data.options||[]).find(option=>option.recommended);
 if(primary)box.append(el('p',{},'对应主方案：'+[primary.model,primary.platform,primary.input_mode].filter(Boolean).join(' · ')));
 if(Array.isArray(basis.priorities))box.append(el('p',{},'本段重点：'+basis.priorities.join('；')));
 for(const [key,label] of [['comparison','与备选的区别'],['cost','整体制作成本'],['uncertainty','仍未确定']]){
  if(basis[key])box.append(el('p',{},label+'：'+basis[key]));
 }
 if(data.method_evidence?.summary)box.append(el('p',{class:'review-note'},'现有依据：'+data.method_evidence.summary));
 parent.append(box);
}
function renderSequencePlan(root,includeReview=true){
 const records=activeRecords(),reviews=records.filter(r=>r.data?.decision_type==='sequence_review'&&doc._record_states?.[r.id]?.status!=='excluded');
 const plans=records.filter(r=>r.data?.decision_type==='generation_recommendation'&&doc._record_states?.[r.id]?.status!=='excluded');
 const block=el('section',{class:'sequence-review-panel','aria-label':'整段审查与生成建议'});
 const head=el('div',{class:'preview-heading'});head.append(el('h2',{},includeReview?'整段预演与生成建议':'模型路线与所需素材'));if(includeReview)head.append(button('播放分镜预演',()=>openRehearsal(block),'secondary'));block.append(head);
 if(includeReview&&!reviews.length)block.append(el('p',{class:'review-note'},'图稿确认后，助手完成本批一次整段审查，并在这里汇总生成建议。'));
 for(const record of includeReview?reviews:[]){
  const card=el('article',{class:'sequence-summary'});card.append(el('h3',{},'整段审查已完成'),el('p',{class:'creative-text'},record.data.summary||record.body));
  if(record.data.result==='revise')card.append(el('p',{class:'review-note'},'审查已给出调整建议；人工修改后直接更新图稿与生成建议，不再启动审查环节。'));
  if(doc._record_states?.[record.id]?.stale)card.append(el('p',{class:'review-note'},'此后有方案修订。保留这次审查记录，当前人工方案优先；原判断不冒充覆盖新版本。'));
  const findings=(record.data.continuity_review?.joins||[]).filter(j=>j.status==='design_gap');
  if(findings.length){const list=el('ul');for(const finding of findings)list.append(el('li',{},(finding.from||'')+' → '+(finding.to||'')+'：'+(finding.evidence||finding.budget_check||'见本次审查建议')));card.append(list);}
  block.append(card);
 }
 if(!plans.length)block.append(el('p',{class:'review-note'},'尚未记录生成建议。建议应随每镜设计更新，不能默认全部使用全能参考。'));
 for(const plan of plans){
  const data=plan.data||{},card=el('article',{class:'generation-plan'}),stale=doc._record_states?.[plan.id]?.stale;
  const completed=Boolean(doc._sequence_receipts?.[plan.id]);
  card.append(el('h3',{},completed?'本批生成方案':'文字分镜与制作方案'),el('p',{class:'creative-text'},plan.body||''));
  if(stale)card.append(el('p',{class:'review-note'},'镜头已有调整，助手需同步受影响的生成建议；已有路线不会因此撤销。'));
  renderSelectionBasis(card,data);
  const groups=Array.isArray(data.groups)?data.groups:[];
  if(groups.length){
   const table=el('table',{class:'generation-table'}),thead=el('thead'),tr=el('tr');
   for(const title of ['镜头范围','建议方式','效果与选择理由','输入、成本与限制'])tr.append(el('th',{},title));thead.append(tr);table.append(thead);
   const body=el('tbody'),shots=new Map(doc.sections.flatMap(sec=>sec.groups.flatMap(g=>g.shots.map(sh=>[sh.id,sh.number||sh.id]))));
   for(const group of groups){const row=el('tr');row.append(el('td',{},(group.shot_ids||[]).map(id=>shots.get(id)||id).join('、')),el('td',{},[group.input_mode,group.model,group.platform].filter(Boolean).join(' · ')),el('td',{},group.reason||''),el('td',{},[group.inputs,group.cost,group.limits].filter(Boolean).join('；')));body.append(row);}
   table.append(body);card.append(table);
  }
  const options=Array.isArray(data.options)?data.options:[];
  if(options.length){
   const routes=el('div',{class:'generation-routes'});
   const selected=(plan.shot_ids||[]).map(id=>doc._current_routes?.[id]?.path);
   const chosen=selected.length&&selected.every(path=>path&&path===selected[0])?selected[0]:null;
   for(const option of options.filter(x=>['direct_platform','previs_reference'].includes(x.path))){
    const route=el('article',{class:'generation-route'});route.append(el('h4',{},option.label||(option.path==='direct_platform'?'直接去平台生成':'先 Blender 预演，再平台生成')));
    if(option.recommended)route.append(el('span',{class:'badge'},recommendationLabel(data)));
    route.append(el('p',{},option.reason||''));if(option.tradeoff)route.append(el('p',{class:'review-note'},option.tradeoff));
    const isChosen=option.id?(plan.shot_ids||[]).every(id=>doc._current_routes?.[id]?.option_id===option.id&&doc._current_routes?.[id]?.record_id==='route-'+plan.id):chosen===option.path;
    route.append(el('p',{},[option.model,option.platform,option.input_mode].filter(Boolean).join(' · ')));
    if(option.inputs)route.append(el('p',{},'所需输入：'+option.inputs));if(option.limits)route.append(el('p',{class:'review-note'},option.limits));
    const choose=button(isChosen?'已选此方案':'选择此方案',()=>chooseRoute(plan.id,option.path,option.id),isChosen?'secondary':'primary');choose.disabled=stale||isChosen;route.append(choose);routes.append(route);
   }
   card.append(routes,el('p',{class:'review-note'},'这里记录生成方式，不会点击平台生成或消耗积分。已选择后，在对话中继续即可沿用。'));
  }else card.append(el('p',{class:'review-note'},'这里只提供随设计更新的初步建议，现在不要求选路线。'));
  if(data.method_evidence){const evidence=el('details');evidence.append(el('summary',{},'制作依据 · '+({queried:'本轮查询',reused:'复用依据',no_match:'无匹配案例',unavailable:'来源不可用',user_specified:'用户指定'}[data.method_evidence.status]||'待核')),el('p',{},data.method_evidence.summary||''));for(const source of data.method_evidence.sources||[]){const p=el('p',{},[({official:'官方能力资料',case:'条件相近的案例',observed_result:'已检查的生成结果',user_report:'用户经验线索'})[source.kind],source.model_version,source.platform,source.checked_at,source.applied,source.limits].filter(Boolean).join('；'));if(/^https?:\/\//i.test(source.url||''))p.append(el('a',{href:source.url,target:'_blank',rel:'noopener'},'查看来源'));else if(source.url)p.append(el('span',{},' · '+source.url));evidence.append(p);}card.append(evidence);}
  block.append(card);
 }
 root.append(block);
}
async function chooseRoute(recommendationId,path,optionId){
 await save();if(dirty||saving||blocked){notice('请先保存修改并处理冲突。');return;}
 const sentVersion=version,snapshot=clone(doc);saving=true;state('正在记录路线…');
 try{
  const result=await api('/api/routes/choose',{recommendation_id:recommendationId,path,option_id:optionId,expected_revision:savedRevision});
  let merged;
  try{merged=version===sentVersion?result:{...result,...mergePending(editableSnapshot(snapshot),editableSnapshot(doc),editableSnapshot(result))};}
  catch(error){blocked=true;persist();throw error;}
  doc=merged;baseDocument=clone(result);savedRevision=result.revision;doc.revision=savedRevision;
  dirty=version!==sentVersion;if(dirty)persist();else localStorage.removeItem(draftKey());
  renderPreservingFocus();notice('路线已记录，后续沿用此选择；当前没有提交生成任务。');
 }catch(error){notice('路线未完成同步：'+error.message+'。本地修改保留。');}
 finally{saving=false;state(blocked?'存在冲突':dirty?'等待保存':'已保存 · 修订 '+savedRevision);if(dirty&&!blocked)timer=setTimeout(save,0);}
}

let rehearsalTimer=null;
async function openRehearsal(parent){
 clearTimeout(rehearsalTimer);parent.querySelector('.rehearsal-player')?.remove();
 const player=el('section',{class:'rehearsal-player','aria-label':'静态分镜序列预演'}),controls=el('div',{class:'rehearsal-controls'}),screen=el('div',{class:'rehearsal-screen'}),caption=el('p',{class:'rehearsal-caption'}),note=el('p',{class:'review-note'},'仅按计划节奏播放已采用静帧，不模拟真实运镜、表演或声音，不会启动新的审查或生成。');
 parent.append(player);const scope=el('select',{'aria-label':'预演范围'});scope.append(el('option',{value:''},'当前全部段落'));for(const sec of doc.sections.filter(s=>!cancelledSections().has(s.id)))scope.append(el('option',{value:sec.id},sec.title));
 let entries=[],index=0,playing=false;
 function stop(){playing=false;clearTimeout(rehearsalTimer);play.textContent='播放';}
 function show(){
  screen.replaceChildren();const entry=entries[index];if(!entry){caption.textContent='暂无可播放图序。';return;}
  const item=entry.image;if(item){const url='/api/image?record='+encodeURIComponent(item.record_id)+'&file='+item.file_index;
   if(item.box&&item.size){const [x,y,right,bottom]=item.box,[w,h]=item.size,cw=right-x,ch=bottom-y;const crop=el('div',{class:'rehearsal-crop',role:'img','aria-label':entry.number+'采用画格'});crop.style.cssText='aspect-ratio:'+cw+'/'+ch+';background-image:url("'+url+'");background-size:'+(100*w/cw)+'% '+(100*h/ch)+'%;background-position:'+(w===cw?0:100*x/(w-cw))+'% '+(h===ch?0:100*y/(h-ch))+'%';screen.append(crop);}
   else screen.append(el('img',{src:url,alt:entry.number+' 分镜预演'}));
  }else screen.append(el('p',{class:'image-error'},'该镜没有当前可用采用图，不能跳过这项缺口。'));
  caption.textContent=(index+1)+' / '+entries.length+' · '+entry.number+' · '+(entry.content||'')+(entry.seconds?'（本状态暂分约 '+entry.seconds.toFixed(1)+' 秒）':'（时长待定，可手动查看）');
  if(playing){if(index===entries.length-1){rehearsalTimer=setTimeout(stop,entry.seconds*1000);}else rehearsalTimer=setTimeout(()=>{index++;show();},entry.seconds*1000);}
 }
 const previous=button('上一张',()=>{stop();index=Math.max(0,index-1);show();}),next=button('下一张',()=>{stop();index=Math.min(entries.length-1,index+1);show();});
 const play=button('播放',()=>{if(playing){stop();return;}if(index===entries.length-1)index=0;playing=true;play.textContent='暂停';show();},'primary');
 controls.append(scope,previous,play,next,button('关闭',()=>{stop();player.remove();}));player.append(controls,screen,caption,note);
 async function load(){stop();try{const data=await api('/api/rehearsal'+(scope.value?'?section_id='+encodeURIComponent(scope.value):''));entries=[];for(const frame of data.frames||[]){const images=frame.images?.length?frame.images:[null];for(const image of images)entries.push({image,number:frame.number||frame.shot_id,content:frame.content,seconds:typeof frame.duration==='number'&&frame.duration>0?frame.duration/images.length:null});}index=0;play.disabled=!entries.length||entries.some(e=>!e.seconds||!e.image);note.textContent='静态时序预演，不证明实际运动或声音效果。'+(data.issues?.length?' 当前缺口：'+data.issues.join('；'):' 多状态图暂均分该镜时间，不增加整镜时长。');show();}catch(error){caption.textContent='预演未加载：'+error.message;}}
 scope.onchange=load;await load();
}

function renderImageAssets(){
 const root=$('asset-preview');root.replaceChildren();
 const heading=el('div',{class:'preview-heading'});heading.append(el('h1',{},'分镜图所用图片资产'),el('p',{},'上方按镜号列出分镜图生成时实际用过的图片；下方分别列出已采用资产和待选参考。来源或状态无法核实时会明确标出。'));root.append(heading);
 const records=doc.production?.records||[],byId=new Map(records.map(record=>[record.id,record]));
 const collator=new Intl.Collator('zh-Hans',{numeric:true,sensitivity:'base'});
 const rows=(doc._preview_rows||[]).filter(row=>row.images?.length);
 if(!rows.length){root.append(el('p',{class:'empty'},'当前没有登记的分镜图，因此没有可核对的实际输入资产。'));renderAdoptedAssetLibrary(root);return;}
 function basename(path){return String(path||'').split(/[\\/]/).filter(Boolean).pop()||'';}
 function adoptionLabel(input,source){
  const atUse=String(input?.adoption_status_at_use||'').trim().toLowerCase();
 const excluded=/rejected|excluded|superseded|cancelled|retired|not_adopted/.test(atUse);
  if(excluded)return {label:'出图时明确排除',tone:'asset-excluded',detail:'输入记录本身标记为排除'};
  if(atUse){
   if(/candidate|pending|planned|awaiting|prepared|draft|review|proposed/.test(atUse))return {label:'出图时为候选',tone:'preview-pending',detail:'根据 adoption_status_at_use'};
   if(/adopted|selected|accepted|approved|confirmed/.test(atUse))return {label:'出图时已采用',tone:'asset-adopted',detail:'根据 adoption_status_at_use'};
   return {label:'出图时状态：'+String(input.adoption_status_at_use),tone:'asset-unknown',detail:'保留来源记录中的状态原文'};
  }
  if(!source)return {label:'状态未记录',tone:'asset-unknown',detail:'实际输入没有出图时状态，且找不到来源资产记录'};
  const resolved=doc._record_states?.[source.id],status=resolved?.display_status||'unknown';
  const labels={adopted:'当前已采用',candidate:'当前为候选',revise:'当前待修改',excluded:'当前明确排除',needs_review:'当前用途需复核',unknown:'状态未记录'};
  return {label:labels[status]||labels.unknown,tone:status==='adopted'?'asset-adopted':status==='excluded'?'asset-excluded':'preview-pending',detail:'出图时状态未记录；这里显示当前记录状态，不能倒推历史采用。'};
 }
 const currentShots=new Map(doc.sections.flatMap(section=>section.groups.flatMap(group=>group.shots.map(shot=>[shot.id,shot]))));
 const seen=new Set();let shown=0;
 for(const row of rows){
  const shot=currentShots.get(row.shot_id),shotTitle=(row.number||'未编号镜头')+(shot?.content?' · '+shot.content.slice(0,100):'');
  for(const output of row.images){
   const traceKey=row.shot_id+'\0'+output.record_id+'\0'+output.file_index;
   if(seen.has(traceKey))continue;seen.add(traceKey);
   const board=byId.get(output.record_id),inputs=board?.data?.actual_inputs;
   const card=el('article',{class:'preview-card sequence-card trace-card'});
   const head=el('div',{class:'trace-heading'}),outputInfo=el('div');outputInfo.append(el('h2',{},shotTitle),el('p',{class:'preview-file'},'分镜图：'+(output.path||'文件名未记录')));head.append(outputInfo,el('span',{class:'badge '+(output.review_status==='candidate'?'preview-pending':'')},({candidate:'分镜图待选',adopted:'分镜图已采用',revise:'分镜图待修改',needs_review:'分镜图需复核'}[output.review_status]||'状态待核')));card.append(head);
   if(!Array.isArray(inputs)||inputs.length===0){card.append(el('p',{class:'trace-empty'},'此分镜图没有登记 actual_inputs；无法从依赖关系推断实际使用的图片资产。'));}
   else{
    const list=el('ul',{class:'trace-inputs','aria-label':'实际输入资产'});
    for(const [inputIndex,input] of inputs.entries()){
     const item=(input&&typeof input==='object')?input:{path:String(input||'')};
     const source=byId.get(item.record_id||item.source_record_id),path=String(item.path||'').replace(/\\/g,'/'),state=adoptionLabel(item,source);
     const li=el('li',{class:'trace-input'}),asset=el('div',{class:'trace-asset'});
     const title=String(item.title||source?.title||basename(path)||'未命名输入资产');
     asset.append(el('strong',{},title),el('span',{class:'badge '+state.tone,title:state.detail},state.label));
     if(item.purpose)asset.append(el('span',{class:'trace-purpose'},'用途：'+item.purpose));
     const provenance=path?'记录路径：'+path:source?'来源记录：'+(source.title||source.id):'来源未登记';
     asset.append(el('span',{class:'trace-path'},provenance));
     if(item.record_id||item.source_record_id)asset.append(el('span',{class:'trace-path'},'来源记录：'+(item.record_id||item.source_record_id)+' · '+(item.version_at_use?'使用版本 '+item.version_at_use:'使用版本未记录')));
     if(!item.sha256)asset.append(el('span',{class:'trace-unavailable'},'使用时文件哈希未记录；缩略图只能代表当前文件。'));
     if(item.approval_status_at_use)asset.append(el('span',{class:'trace-path'},'出图时审核：'+item.approval_status_at_use));
     const boardId=board?.id||output.record_id;
     if(boardId&&(path||item.record_id||item.source_record_id)){
      const url='/api/image?record='+encodeURIComponent(boardId)+'&input='+inputIndex;
      const link=el('a',{href:url,target:'_blank',rel:'noopener','aria-label':'查看实际输入资产 '+title+' 原图'}),img=el('img',{src:url,alt:title,loading:'lazy',decoding:'async'});
      img.onerror=()=>{img.hidden=true;link.append(el('span',{class:'image-error'},'无法验证或读取此图片。'));};link.append(img);asset.append(link);
     }else asset.append(el('span',{class:'trace-unavailable'},source||path?'已登记来源，但无法核实对应图片文件，暂不预览。':'来源未登记，无法预览。'));
     li.append(asset);list.append(li);shown++;
    }
    card.append(list);
   }
   root.append(card);
  }
 }
 if(!shown)root.append(el('p',{class:'empty'},'当前分镜图均未记录可展示的 actual_inputs；工作台没有用 depends_on 补猜资产。'));
 renderAdoptedAssetLibrary(root);
}
function renderAdoptedAssetLibrary(root){
 const records=activeRecords(),cancelled=cancelledSections(),currentShots=new Set(doc.sections.flatMap(section=>section.groups.flatMap(group=>group.shots.map(shot=>shot.id))));
 const excluded=/rejected|excluded|superseded|cancelled|retired/i,candidate=/candidate|pending|planned|awaiting|prepared_for_review|revise|draft/i;
 const adoptedGroups=new Map(),referenceGroups=new Map();
 function category(role){return ({identity:'人物',identity_reference:'人物',character:'人物',scene:'场景',scene_reference:'场景',environment:'场景',prop:'道具',prop_shape_reference:'道具',object:'道具',ui:'图形与界面',graphic:'图形与界面',style_reference:'风格参考',composition_reference:'构图参考',storyboard_frame:'分镜状态图'})[role]||'其他资产';}
 for(const record of records){
  const data=record.data||{},role=String(data.asset_role||(record.kind==='decision'&&data.decision_type==='static_exploration'?'storyboard_frame':'')).toLowerCase();
  if(!['asset','decision'].includes(record.kind)||!role)continue;
  if(role==='storyboard_frame'&&data.used_as_reference!==true)continue;
  if(record.shot_ids?.length&&!record.shot_ids.some(id=>currentShots.has(id)))continue;
  if((record.section_ids||[]).length&&(record.section_ids||[]).every(id=>cancelled.has(id)))continue;
  const resolved=doc._record_states?.[record.id],status=resolved?.display_status||'unknown';
  const files=(record.files||[]).map((file,index)=>({file,index})).filter(({file})=>/\.(png|jpe?g|webp|gif)$/i.test(file.path||''));
  if(!files.length||status==='excluded')continue;
  const key=category(role);
  if(status==='adopted'){if(!adoptedGroups.has(key))adoptedGroups.set(key,[]);adoptedGroups.get(key).push({record,files});continue;}
  if(data.used_as_reference===true||['candidate','revise','needs_review'].includes(status)){
   const label=({candidate:'待选参考',revise:'待修改',needs_review:'原采用记录保留 · 当前用途需复核',unknown:'参考状态未记录'})[status]||'状态待核';
   if(!referenceGroups.has(key))referenceGroups.set(key,[]);referenceGroups.get(key).push({record,files,label});
  }
 }
 const section=el('section',{class:'adopted-asset-library','aria-label':'已采用资产库'});
 const heading=el('div',{class:'preview-heading'});heading.append(el('h2',{},'图片资产库'),el('p',{},'已采用资产必须有明确采用记录；参考用途、状态字段和候选标记不会被当作用户采用。上方按镜展示的是生成分镜图时记录的实际输入。'));section.append(heading);
 const order=['人物','场景','道具','图形与界面','风格参考','构图参考','分镜状态图','其他资产'];
 function appendGroups(groups,{headingLabel,badgeLabel,emptyLabel,ariaLabel}){
  const block=el('div',{class:'asset-library-block'});block.append(el('h3',{class:'asset-library-heading'},headingLabel));let total=0;
  for(const key of order){
   const items=groups.get(key);if(!items?.length)continue;total+=items.length;
   const group=el('section',{class:'adopted-asset-group','aria-label':key+'资产'});group.append(el('h4',{},key));const grid=el('div',{class:'preview-sequence'});
   items.sort((a,b)=>new Intl.Collator('zh-Hans',{numeric:true,sensitivity:'base'}).compare(a.record.title,b.record.title));
   for(const {record,files,label} of items){
    const card=el('article',{class:'preview-card sequence-card adopted-asset-card'});card.append(el('h5',{},record.title),el('span',{class:'badge '+(label?'preview-pending':'asset-adopted')},label||badgeLabel));
    if(record.data?.reference_scope)card.append(el('p',{class:'asset-scope'},record.data.reference_scope));
    for(const {file,index} of files){const url='/api/image?record='+encodeURIComponent(record.id)+'&file='+index,link=el('a',{href:url,target:'_blank',rel:'noopener','aria-label':'查看 '+file.path.split('/').pop()+' 原图'}),img=el('img',{src:url,alt:file.path.split('/').pop(),loading:'lazy',decoding:'async'});img.onerror=()=>{img.hidden=true;link.append(el('span',{class:'image-error'},'图片无法读取，请核对原文件。'));};link.append(img);const assetFile=el('div',{class:'asset-file'});assetFile.append(link,el('p',{class:'preview-file'},file.path.split('/').pop()));card.append(assetFile);}
    grid.append(card);
   }
   group.append(grid);block.append(group);
  }
  if(!total)block.append(el('p',{class:'empty'},emptyLabel));block.setAttribute('aria-label',ariaLabel);section.append(block);
 }
 appendGroups(adoptedGroups,{headingLabel:'已采用资产',badgeLabel:'已采用',emptyLabel:'当前没有带有明确采用记录的图片资产。',ariaLabel:'已采用资产'});
 appendGroups(referenceGroups,{headingLabel:'待选参考与状态图',badgeLabel:'待选参考',emptyLabel:'当前没有登记的待选参考或候选状态图。',ariaLabel:'待选参考与状态图'});
 root.append(section);
}
function renderWorkflowStage(){
 const root=$('stage-status');if(!root)return;root.replaceChildren();if(!doc){root.hidden=true;return;}root.hidden=false;
 const workflow=doc._workflow||{phase:0,title:'工作进度待同步',detail:'请通过当前版本的工作台入口继续。'},phase=workflow.phase;
 const top=el('div',{class:'stage-copy'});top.append(el('div',{class:'stage-current'},'当前工作 · '+workflow.title),el('p',{},dirty?'修改正在保存；已有制作决定保留。':workflow.detail));
 const list=el('ol',{class:'stage-steps','aria-label':'制作阶段'});
 [['文字分镜','理解与设计'],['图片资产与分镜图','制作与审阅'],['视频制作与返修','按已选路线推进']].forEach(([label,caption],index)=>{
  const li=el('li',{class:index===phase?'is-current':index<phase?'is-complete':'is-upcoming'}),copy=el('span',{class:'stage-step-copy'});
  copy.append(el('strong',{},label),el('small',{},caption));li.append(el('span',{class:'stage-marker','aria-hidden':'true'},String(index+1)),copy);list.append(li);
 });
 root.append(top,list);root.dataset.phase=String(phase);
 if(workflow.scopes?.length===1){const actions=el('ul',{'aria-label':workflow.scopes[0].title+'下一步'});for(const action of workflow.scopes[0].next_actions||[])actions.append(el('li',{},action.text));root.append(actions);}
 if(workflow.scopes?.length>1){const summary=el('details');summary.append(el('summary',{},'各段当前工作'));for(const scope of workflow.scopes){summary.append(el('p',{},scope.title+'：'+scope.status));for(const action of scope.next_actions||[])summary.append(el('p',{class:'review-note'},action.text));}root.append(summary);}
}

function render(){
 const root=$('editor');root.replaceChildren();const head=el('div',{class:'doc-head'});head.append(el('div',{class:'eyebrow'},'DIRECTOR’S DESK / 文字分镜'),titleInput(doc,'title','分镜标题','title'));
 const source=el('section',{class:'source-panel','aria-label':'对应原文'});
 source.append(el('h2',{},'对应原文'),editField(doc,'source_text','对应原文',{placeholder:'粘贴这段分镜所依据的原文；若只有创意想法，可留空。'}));
 head.append(source);
 renderSequencePlan(head,false);
 head.append(el('section',{id:'review',class:'creative-review','aria-label':'构建思路与导演建议'}));head.append(contextNotes(doc,'范围与补充说明','brief','brief-panel'));root.append(head);
 doc.sections.forEach((s,si)=>{
  const sec=el('section',{class:'section',id:s.id}),h=el('div',{class:'section-heading'}),number=el('span',{class:'section-index'},String(si+1).padStart(2,'0'));number.append(el('small',{},'段落'));h.append(number,titleInput(s,'title','段落标题'),listTools(doc.sections,si,'段落'));
  const gate=el('div',{class:'section-confirmation'});gate.append(el('span',{'data-section-state':s.id}),button('确认本段',()=>confirmSection(s.id),'primary confirm-section'));gate.querySelector('button').dataset.sectionId=s.id;sec.append(h,gate,contextNotes(s,'段落说明与制作边界','section:'+s.id));
  s.groups.forEach((g,gi)=>{const group=el('section',{class:'group',id:g.id}),gh=el('div',{class:'group-heading'});gh.append(el('span',{class:'group-index'},'镜头组 '+String(gi+1).padStart(2,'0')),titleInput(g,'title','镜头组标题'),el('span',{class:'badge'},g.shots.length+' 镜'),listTools(s.groups,gi,'镜头组'));group.append(gh,contextNotes(g,'镜头组意图与备注','group:'+g.id));g.shots.forEach((sh,i)=>group.append(renderShot(sh,g,i)));if(!g.shots.length)group.append(el('p',{class:'empty'},'为这一组加入第一个镜头。'));group.append(button('＋ 新增镜头',()=>mutate(()=>g.shots.push(newShot()))));sec.append(group);});
  sec.append(button('＋ 新增镜头组',()=>mutate(()=>s.groups.push({id:uid(),title:'新镜头组',notes:'',shots:[]}))));root.append(sec);
 });
 if(!doc.sections.length)root.append(el('p',{class:'empty'},'从左侧新增一个情节段落，开始组织分镜。'));renderNav();renderReview();setView(activeView);totals();renderSectionStates();
}
function renderSectionStates(){
 if(!doc)return;
 for(const label of document.querySelectorAll('[data-section-state]')){
  const sid=label.dataset.sectionState,status=(doc._section_status||{})[sid]||'draft';
  const cancelled=cancelledSections().has(sid),control=label.parentElement.querySelector('button');control.hidden=cancelled;
  const entered=doc._workflow?.scopes?.some(scope=>scope.section_id===sid&&scope.phase>=1);
  if(entered&&!cancelled&&status!=='confirmed'){control.hidden=true;label.dataset.status=dirty?'changed':status;label.textContent=dirty?'本轮修改正在保存':'当前修订随制作继续 · 原阶段保留';continue;}
  if(cancelled){label.dataset.status='cancelled';label.textContent='无需制作 · 历史分镜';continue;}
  label.dataset.status=dirty?'changed':status;
  label.textContent=dirty?'有未保存修改':({draft:'尚未确认',confirmed:'本段已确认',changed:'本段有修订 · 仅受影响内容待审阅'}[status]||status);
  const b=label.parentElement.querySelector('button');b.textContent=status==='confirmed'?'本段已确认':status==='draft'?'确认本段':'重新确认本段';b.disabled=dirty||saving||blocked||status==='confirmed';
 }
}
async function confirmSection(sid){
  await save();
  if(dirty||saving||blocked){notice('请先保存修改并处理冲突，再确认本段。');return;}
  const originalVersion=version;
  saving=true;state('正在确认…');
  try{
    const result=await api('/api/sections/confirm',{section_id:sid,expected_revision:savedRevision,evidence:'用户在工作台点击确认本段'});
    if(version!==originalVersion){blocked=true;persist();notice('确认期间又有本地修改；已保留本地草稿，请导出并重新读取。');return;}
    doc=result;baseDocument=clone(result);savedRevision=doc.revision;render();notice(doc._export_warning||'本段已确认，制作Markdown已更新。');
  }catch(e){if(e.status===409)blocked=true;notice('确认未完成：'+e.message);}
  finally{saving=false;state(blocked?'存在冲突':'已保存 · 修订 '+savedRevision);}
}
function download(value,filename,type='application/json'){const url=URL.createObjectURL(new Blob([value],{type}));const a=el('a',{href:url,download:filename});a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}
async function actSuggestion(s,action){await save();if(dirty||saving||blocked){notice('请先完成当前修改的保存，再处理建议。');return;}saving=true;state('保存中…');const actionVersion=version;try{const result=await api('/api/suggestions/'+encodeURIComponent(s.id)+'/'+action,{expected_revision:savedRevision});if(version!==actionVersion){blocked=true;persist();notice('处理建议期间又有本地修改，请导出草稿并重新读取已保存稿。');state('存在冲突');return;}doc=result;baseDocument=clone(result);savedRevision=doc.revision;render();state('已保存 · 修订 '+savedRevision);}catch(e){if(e.status===409)blocked=true;notice('建议未应用：'+e.message);state(blocked?'存在冲突':'操作失败');}finally{saving=false;renderSectionStates();$('retry').hidden=!(dirty&&!blocked);if(dirty&&!blocked){clearTimeout(timer);timer=setTimeout(save,0);}}}
function targetLink(id){const targets=[doc,...doc.sections,...allGroups().map(x=>x.g),...allGroups().flatMap(x=>x.g.shots)],target=targets.find(x=>x.id===id);return target?el('a',{href:'#'+(target===doc?'editor':id),class:'target-link'},'查看对象：'+(target.number||target.title||'未命名镜头')):el('span',{class:'stale'},'原对象已删除');}
// Creative direction is authored by the Agent, never synthesized from status text by the UI.
function activeRecords(){const records=doc?.production?.records||[];const retired=new Set(records.flatMap(r=>r.data?.supersedes||[]));return records.filter(r=>!retired.has(r.id));}
function cancelledSections(){return new Set(activeRecords().filter(r=>r.kind==='decision'&&r.data?.decision_type==='scope_cancellation'&&r.data?.production_required===false).flatMap(r=>r.section_ids||[]));}
function targetIsCancelled(id){const cancelled=cancelledSections();return doc.sections.some(s=>cancelled.has(s.id)&&(s.id===id||s.groups.some(g=>g.id===id||g.shots.some(sh=>sh.id===id))))||(id===doc.id&&doc.sections.length>0&&doc.sections.every(s=>cancelled.has(s.id)));}
function suggestionCard(s){
 const card=el('article',{class:'review-card'}),title=el('h3',{},s.problem||'镜头建议'),pendingStale=s.status==='pending'&&s.stale;
 title.append(el('span',{class:'badge '+(pendingStale?'stale':'')},pendingStale?'方案已变化 · 待更新':({pending:'待讨论',accepted:'已采用',ignored:'已忽略'}[s.status]||s.status)));
 card.append(title,targetLink(s.target_id),el('p',{},s.impact||''));
 const proposed=disclosure('suggestion:'+s.id,'查看具体修改','suggestion-change');
 for(const [key,value] of Object.entries(s.changes||{}))proposed.append(el('p',{},(names[key]||key)+'：'+value));
 card.append(proposed);
 if(s.status==='pending'&&!targetIsCancelled(s.target_id)){const actions=el('div',{class:'tools'}),accept=button('采用建议',()=>actSuggestion(s,'accept'),'primary'),ignore=button('忽略',()=>actSuggestion(s,'ignore'));accept.disabled=Boolean(s.stale);actions.append(accept,ignore);card.append(actions);}
 return card;
}
function renderReview(){
 const root=$('review');if(!root||!doc)return;root.replaceChildren();
 const cancelled=cancelledSections(),allCancelled=doc.sections.length>0&&doc.sections.every(s=>cancelled.has(s.id));
 const directions=activeRecords().filter(r=>r.kind==='decision'&&r.data?.decision_type==='creative_direction'&&(r.body||'').trim());
 const current=directions.filter(r=>(r.section_ids||[]).some(id=>doc.sections.some(s=>s.id===id)&&!cancelled.has(id)));
 if(allCancelled)root.append(el('p',{class:'scope-banner'},'本段无需制作 · 下方分镜仅作历史保留。'));
 for(const r of current){const card=el('article',{class:'creative-card'}),heading=el('div',{class:'creative-heading'});heading.append(el('h2',{},'分镜构建思路'));if(current.length>1)heading.append(el('span',{class:'creative-scope'},doc.sections.filter(s=>(r.section_ids||[]).includes(s.id)).map(s=>s.title).join(' / ')));card.append(heading,el('p',{class:'creative-text'},r.body));root.append(card);}
 if(!current.length&&!allCancelled)root.append(el('p',{class:'creative-missing'},'这份分镜尚未记录构建思路。首次方案应由 Agent 同步说明表达重点、镜头顺序与推荐拍法。'));
 const suggestions=doc.suggestions||[],pending=suggestions.filter(s=>s.status==='pending'&&!targetIsCancelled(s.target_id));
 if(pending.length){const block=el('section',{class:'director-advice'});block.append(el('h2',{},'导演建议'));for(const s of pending)block.append(suggestionCard(s));root.append(block);}
 const historical=suggestions.filter(s=>!pending.includes(s));if(historical.length){const history=disclosure('suggestion-history','已处理与历史建议（'+historical.length+'）','advice-history');for(const s of historical)history.append(suggestionCard(s));root.append(history);}
 // Legacy prompts remain in the document/exports for compatibility, not in this planning UI.
}
async function reload(){if(saving)return;if(dirty&&!confirm('重新读取会用已保存稿替换页面内容。请先导出本地草稿，确定继续？'))return;try{const result=await api('/api/document');doc=result;baseDocument=clone(result);savedRevision=doc.revision;dirty=false;blocked=false;undoDoc=null;$('undo').disabled=true;localStorage.removeItem(draftKey());notice();render();state('已保存 · 修订 '+savedRevision);}catch(e){notice('读取失败：'+e.message);}}
$('add-section').onclick=()=>{if(doc){setView('storyboard');mutate(()=>doc.sections.push({id:uid(),title:'新段落',notes:'',groups:[]}));}};
document.querySelectorAll('a[href="#editor"]').forEach(link=>{link.onclick=()=>setView('storyboard');});
$('undo').onclick=()=>{if(!undoDoc)return;const operation=undoDoc,parent=[doc,...doc.sections,...allGroups().map(x=>x.g)].find(x=>x.id===operation.parentId);if(!parent){notice('原段落或镜头组已不存在，无法在原位置撤销。');return;}parent[operation.key].splice(Math.min(operation.index,parent[operation.key].length),0,operation.item);undoDoc=null;$('undo').disabled=true;mark(true);render();};
$('retry').onclick=()=>doc?save():start();$('reload').onclick=reload;$('draft-export').onclick=()=>{if(doc)download(JSON.stringify({base_revision:savedRevision,document:doc},null,2),'分镜-本地恢复草稿.json');};
document.addEventListener('click',async e=>{const a=e.target.closest('a[download]');if(!a)return;e.preventDefault();await save();if(dirty||saving||blocked){notice('请先完成修改的保存，再导出已保存稿；也可以导出本地恢复草稿。');return;}try{const response=await fetch(a.getAttribute('href'),{cache:'no-store'});if(!response.ok){const problem=await response.json();throw new Error(problem.error||'服务暂时无法导出');}download(await response.text(),a.getAttribute('href').endsWith('prompts')?'生图提示词.md':'分镜阅览.md','text/markdown;charset=utf-8');}catch(error){notice('导出失败：'+error.message);}});
window.addEventListener('beforeunload',e=>{if(dirty){persist();e.preventDefault();e.returnValue='';}});
async function start(){try{doc=await api('/api/document');baseDocument=clone(doc);savedRevision=doc.revision;const preferred=new URLSearchParams(location.search).get('view')||sessionStorage.getItem('cinematic-view:'+doc.id);if(['project','style','references','storyboard','assets','preview'].includes(preferred))activeView=preferred;const raw=localStorage.getItem(draftKey());if(raw){try{const draft=JSON.parse(raw);if(draft.document.id===doc.id){doc=draft.document;dirty=true;version++;if(draft.base_revision!==savedRevision){blocked=true;savedRevision=draft.base_revision;notice('发现未保存草稿，但已保存稿也有更新。先导出草稿，再重新读取并合并。');}else{notice('已恢复上次未保存的草稿。检查内容后点击“重试保存”。');}}}catch(e){notice('恢复草稿无法读取，请保留浏览器数据以便检查。');}}render();state(blocked?'存在冲突 · 已恢复本地草稿':dirty?'已恢复草稿 · 待保存':'已保存 · 修订 '+savedRevision);}catch(e){notice('无法读取分镜：'+e.message);state('服务未连接');$('retry').hidden=false;}}
setInterval(async()=>{if(!doc||dirty||saving||blocked)return;const observed=version;try{const latest=await api('/api/document');if(!dirty&&!saving&&!blocked&&version===observed&&(latest.revision!==savedRevision||latest._view_revision!==doc._view_revision)){doc=latest;baseDocument=clone(latest);savedRevision=doc.revision;undoDoc=null;$('undo').disabled=true;renderPreservingFocus();state('已同步 · 修订 '+savedRevision);}else if(syncLost&&!dirty&&!saving&&!blocked)state('已同步 · 修订 '+savedRevision);syncLost=false;}catch(e){syncLost=true;if(!dirty&&!saving&&!blocked)$('save-state').textContent='实时同步暂不可用 · 正在重连';}},5000);
$('navigation').addEventListener('click',()=>setView('storyboard'));
$('find-reference').onclick=()=>{setView('references');$('reference-query')?.focus();};
$('open-style').onclick=()=>setView('style');
start();
