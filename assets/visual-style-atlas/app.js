(function(global){
'use strict';
const defaultBase=new URL('.',document.currentScript?.src||document.baseURI).href;
const mounts=new WeakMap();
function mount(root,data,options={}){
 if(!root||typeof root.querySelector!=='function')throw new Error('Atlas mount requires a root containing the page template');
 if(!data?.cards||!data?.assets||!data?.forms||!data?.moods)throw new Error('Atlas catalog is incomplete');
 mounts.get(root)?.destroy();
 const doc=root.ownerDocument||document,view=doc.defaultView||global;
 const basePath=options.assetBase||defaultBase;
 const assetBase=new URL(basePath.endsWith('/')?basePath:basePath+'/',doc.baseURI);
 const assetURL=path=>new URL(path,assetBase).href;
 const cleanups=[];let destroyed=false,modalState=null;
 const listen=(node,event,handler)=>{node.addEventListener(event,handler);cleanups.push(()=>node.removeEventListener(event,handler));};
 const sheet=doc.createElement('link');sheet.rel='stylesheet';sheet.href=assetURL('full-page.css');root.prepend(sheet);
 root.querySelectorAll('footer a[href]').forEach(link=>{link.href=assetURL(link.getAttribute('href'));});
 function unlockPage(event){
  if(!modalState||event&&(event.target!==modalState.dialog||event.target.open))return;
  const saved=modalState;modalState=null;
  doc.documentElement.style.overflow=saved.htmlOverflow;doc.body.style.overflow=saved.bodyOverflow;
  view.scrollTo(saved.x,saved.y);
  const focus=saved.focus?.isConnected?saved.focus:[...root.querySelectorAll('[data-detail]')].find(node=>node.dataset.detail===saved.detailId);
  focus?.focus({preventScroll:true});
 }
 function openDialog(id){
  for(const other of root.querySelectorAll('dialog'))if(other.open)other.close();
  unlockPage();
  modalState={htmlOverflow:doc.documentElement.style.overflow,bodyOverflow:doc.body.style.overflow,
              x:view.scrollX,y:view.scrollY,focus:root.activeElement||doc.activeElement,dialog:root.querySelector('#'+id)};
  modalState.detailId=modalState.focus?.dataset?.detail;
  doc.documentElement.style.overflow='hidden';doc.body.style.overflow='hidden';
  try{root.querySelector('#'+id).showModal();}catch(error){unlockPage();throw error;}
 }

const D=data,byId=Object.fromEntries(D.cards.map(c=>[c.id,c])),assets=Object.fromEntries(D.assets.map(a=>[a.id,a]));
const $=id=>root.querySelector('#'+id),esc=s=>String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const requested=options.recommend ?? new URLSearchParams(view.location.search).get('recommend')?.split(',') ?? [];
const provided=[...new Set(requested.filter(id=>typeof id==='string'&&byId[id]))];
const recommended=provided.length?provided.slice(0,5):D.default_recommendations;
let mode='recommended',form='all',base=null,world=null,tones=new Set(),comparison=new Set(),projectNotes='';
const aliases={clay:'粘土 橡皮泥',cgtoon:'皮克斯 3D动漫 三维',anime:'日式动漫 动画 二次元',cgfantasy:'国漫 中国动漫 三维',shadow:'皮影 剪影',paper:'剪纸 纸雕 纸片'};
function formLabel(id){return D.forms.find(f=>f.id===id)?.name||'跨形式美术方向'}
$('edition').textContent=`${D.cards.length} 个方向 · ${D.assets.length} 幅本地参考 · ${D.updated_at}`;
$('formButtons').innerHTML=[['all','全部形式'],...D.forms.map(f=>[f.id,f.name]),['world','跨形式美术方向']].map(([id,name])=>`<button data-form="${id}" class="${id==='all'?'active':''}">${name}</button>`).join('');
listen($('formButtons'),'click',e=>{const b=e.target.closest('[data-form]');if(!b)return;form=b.dataset.form;mode='all';render()});
$('tones').innerHTML=D.moods.map(m=>`<button class="tone" data-tone="${m.name}" aria-pressed="false">${m.name}</button>`).join('');
listen($('tones'),'click',e=>{const b=e.target.closest('[data-tone]');if(!b)return;const t=b.dataset.tone;tones.has(t)?tones.delete(t):tones.add(t);selection()});
function imageFor(c){return assets[c.images[0]]}
function render(){
 const q=$('search').value.trim().toLowerCase();let cards=D.cards.filter(c=>(mode==='all'||recommended.includes(c.id))&&(form==='all'||(form==='world'?c.family==='world':c.compatible_forms.includes(form)))&&(!q||JSON.stringify(c).toLowerCase().includes(q)||(aliases[c.id]||'').includes(q)));
 if(mode==='recommended')cards.sort((a,b)=>recommended.indexOf(a.id)-recommended.indexOf(b.id));
 $('recommended').classList.toggle('active',mode==='recommended');$('all').classList.toggle('active',mode==='all');
 root.querySelectorAll('[data-form]').forEach(b=>{b.classList.toggle('active',b.dataset.form===form);b.setAttribute('aria-pressed',String(b.dataset.form===form))});
 $('formHint').textContent=D.forms.find(f=>f.id===form)?.description||(form==='world'?'这些方向可以组合在不同的呈现形式上。':'不确定形式时，先比较几种明显不同的视觉方向。');
 $('count').textContent=`当前显示 ${cards.length} 个方向`;
 $('viewNote').textContent=mode==='recommended'?(provided.length?'这组方向由传入的推荐清单指定，可随时切换到全部。':'这五种是差异明显的浏览起点。新项目中，助手会结合品牌、受众和用途重新推荐。'):'查看样图与具体边界后再选择。方向之间的区别，主要看形体、线条、材质和空间，而不只看颜色。';
 $('cards').innerHTML=cards.length?cards.map(c=>{const a=imageFor(c),selected=base===c.id||world===c.id;return `<article class="card ${selected?'selected':''}"><button class="art" data-detail="${c.id}" aria-label="查看${esc(c.name)}的全部参考与说明"><img src="${esc(assetURL(a.path))}" alt="${esc(c.name)}参考：${esc(a.source_label)}" loading="lazy"><span class="count">${c.images.length} 幅参考 · 查看</span></button><div class="info"><h2>${c.name}</h2><div class="english">${c.english}</div><p class="desc">${c.definition}</p><div class="tags">${c.family==='world'?'可叠加的世界方向':formLabel(c.family)} · ${c.suggested_moods.join(' / ')}</div><div class="actions"><button class="button ${selected?'active':''}" data-select="${c.id}" aria-pressed="${selected}">${selected?'已选方向':'选择方向'}</button><button class="button ${comparison.has(c.id)?'active':''}" data-compare="${c.id}" aria-pressed="${comparison.has(c.id)}">${comparison.has(c.id)?'取消对比':'加入对比'}</button></div></div></article>`}).join(''):'<div class="empty">没有匹配的方向。试试更宽泛的名词，或重置筛选查看全部。</div>';
 $('compare').textContent=`对比已选（${comparison.size}）`;$('compare').disabled=comparison.size<2;
}
function selection(){
 const parts=[];
 if(base)parts.push(`<div class="chosen">基础画风<strong>${byId[base].name}<button class="clear" data-remove="base">移除</button></strong></div>`);
 if(world)parts.push(`<div class="chosen">世界方向<strong>${byId[world].name}<button class="clear" data-remove="world">移除</button></strong></div>`);
 $('chosen').innerHTML=parts.join('')||'<p class="small">从左侧选一个你愿意继续探索的方向。</p>';
 root.querySelectorAll('[data-tone]').forEach(b=>{let on=tones.has(b.dataset.tone);b.classList.toggle('active',on);b.setAttribute('aria-pressed',String(on))});
 $('toneHint').textContent=[...tones].map(t=>D.moods.find(m=>m.name===t).guidance).join(' ');
 const c=base&&byId[base],w=world&&byId[world];
 let lines=[];
 if(c||w){lines=['视觉定调简报',c?`基础画风：${c.name}（${c.english}）。`:'基础画风：待结合内容确定。',...(c?[`画面特征：${c.definition}`]:[]),...(w?[`世界方向：${w.name}。${w.definition}`]:[]),`调性：${[...tones].join('、')||'待确定'}。`,...(c?[`动态方向：${c.motion_guidance}`]:[]),'人物、场景、品牌色与镜头内容：按当前项目简报确定。','参考只用于说明视觉特征，不照搬图中的人物、服装或构图。','这份简报不替代具体镜头提示词。'];}
 if(projectNotes.trim())lines.push('本片补充：'+projectNotes.trim());
 $('brief').value=lines.join('\n');render();
}
function showDetail(id){const c=byId[id];$('detailTitle').textContent=c.name+' · '+c.english;$('detailBody').innerHTML=`<div class="samplegrid">${c.images.map(id=>{const a=assets[id];return `<div class="sample"><img src="${esc(assetURL(a.path))}" alt="${esc(c.name)}参考"><p>${esc(a.kind)}<br><a href="${esc(a.page)}" target="_blank" rel="noreferrer">${esc(a.publisher)} · ${esc(a.source_label)}</a></p></div>`}).join('')}</div><div class="detailtext"><p><strong>看什么：</strong>${c.definition}</p><p><strong>适合：</strong>${c.suited_for}</p><p><strong>动态需要另定：</strong>${c.motion_guidance}</p><p><strong>容易混淆的地方：</strong>${c.boundary}</p><p><strong>可组合形式：</strong>${c.compatible_forms.map(formLabel).join('、')}</p><p class="small">${c.editorial_note}</p><button class="button primary" data-modal-select="${id}">选择这个方向</button></div>`;openDialog('detail')}
function choose(id){byId[id].family==='world'?world=id:base=id;selection();$('notice').textContent='已更新定调说明。';}
listen($('cards'),'click',e=>{const b=e.target.closest('button');if(!b)return;if(b.dataset.detail)showDetail(b.dataset.detail);if(b.dataset.select)choose(b.dataset.select);if(b.dataset.compare){const id=b.dataset.compare;if(comparison.has(id))comparison.delete(id);else if(comparison.size<3)comparison.add(id);else{$('notice').textContent='一次对比 2–3 个方向，更容易看清差异。';return}render()}});
listen($('detailBody'),'click',e=>{const b=e.target.closest('[data-modal-select]');if(b){choose(b.dataset.modalSelect);$('detail').close()}});
listen($('chosen'),'click',e=>{const b=e.target.closest('[data-remove]');if(b){b.dataset.remove==='base'?base=null:world=null;selection()}});
$('recommended').onclick=()=>{mode='recommended';form='all';$('search').value='';render()};$('all').onclick=()=>{mode='all';render()};$('search').oninput=()=>{mode='all';render()};$('reset').onclick=()=>{mode='all';form='all';$('search').value='';render()};
$('compare').onclick=()=>{$('compareBody').style.gridTemplateColumns=`repeat(${comparison.size},minmax(0,1fr))`;if(view.innerWidth<650)$('compareBody').style.gridTemplateColumns='1fr';$('compareBody').innerHTML=[...comparison].map(id=>{const c=byId[id];return `<section><img src="${esc(assetURL(imageFor(c).path))}" alt="${c.name}"><h3>${c.name}</h3><p>${c.definition}</p><p><strong>差别：</strong>${c.boundary}</p><p><strong>动作：</strong>${c.motion_guidance}</p></section>`}).join('');openDialog('comparison')};
$('closeDetail').onclick=()=>$('detail').close();$('closeCompare').onclick=()=>$('comparison').close();
$('copy').onclick=async()=>{if(!$('brief').value){$('notice').textContent='先选择一个方向。';return}try{await view.navigator.clipboard.writeText($('brief').value);$('notice').textContent='定调说明已复制。'}catch{ $('brief').focus();$('brief').select();$('notice').textContent='已选中文本，请按 ⌘C 或 Ctrl+C 复制。'}};
$('saveProject').hidden=typeof options.onSave!=='function';
$('projectNotes').oninput=()=>{projectNotes=$('projectNotes').value;selection();};
function getChoice(){return {base_id:base,world_id:world,tones:[...tones],brief:$('brief').value,project_notes:projectNotes};}
function restoreChoice(choice={}){
 base=byId[choice.base_id]&&byId[choice.base_id].family!=='world'?choice.base_id:null;
 world=byId[choice.world_id]?.family==='world'?choice.world_id:null;
 tones=new Set((Array.isArray(choice.tones)?choice.tones:[]).filter(t=>D.moods.some(m=>m.name===t)));
 projectNotes=typeof choice.project_notes==='string'?choice.project_notes:'';selection();
 // Preserve older free-form briefs, including ones with no recognizable card ID.
 if(typeof choice.brief==='string'&&choice.brief.trim()&&choice.brief!==$('brief').value){
  projectNotes=projectNotes ? projectNotes+'\n原有自定义说明：'+choice.brief : choice.brief;
  selection();
 }
 $('projectNotes').value=projectNotes;
}
$('saveProject').onclick=async()=>{
 if(!$('brief').value){$('notice').textContent='先选择一个方向。';return;}
 if(typeof options.onSave!=='function')return;
 $('saveProject').disabled=true;$('notice').textContent='正在保存到当前工作台…';
 const sent=getChoice();
 try{const ok=await options.onSave(sent);if(!destroyed)$('notice').textContent=ok?(JSON.stringify(sent)===JSON.stringify(getChoice())?'已保存到当前工作台。':'已保存上一版；当前新修改尚未保存。'):'尚未保存，请查看工作台提示后重试。';}
 catch{if(!destroyed)$('notice').textContent='尚未保存，请查看工作台提示后重试。';}
 finally{if(!destroyed)$('saveProject').disabled=false;}
};
$('download').onclick=()=>{if(!$('brief').value){$('notice').textContent='先选择一个方向。';return}const u=URL.createObjectURL(new Blob([$ ('brief').value],{type:'text/plain;charset=utf-8'}));const a=doc.createElement('a');a.href=u;a.download='视觉定调简报.txt';a.click();setTimeout(()=>URL.revokeObjectURL(u),1000);$('notice').textContent='已发起保存文本。'};

 for(const dialog of root.querySelectorAll('dialog'))listen(dialog,'close',unlockPage);
 if(options.initialChoice)restoreChoice(options.initialChoice);else selection();
 const api={getChoice,restoreChoice,destroy(){
  if(destroyed)return;destroyed=true;
  for(const dialog of root.querySelectorAll('dialog'))if(dialog.open)dialog.close();
  unlockPage();cleanups.forEach(clean=>clean());
  root.querySelectorAll('button,input,textarea').forEach(node=>{node.onclick=null;node.oninput=null;});
  sheet.remove();mounts.delete(root);
 }};
 mounts.set(root,api);return api;
}
global.CinematicAtlas={mount};
const standalone=document.querySelector('[data-cinematic-atlas-root]');
if(standalone&&global.STYLE_ATLAS)mount(standalone,global.STYLE_ATLAS);
})(window);
