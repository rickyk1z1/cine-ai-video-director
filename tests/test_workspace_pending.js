'use strict';
// Evaluate shipped functions against delayed transport and a small form-only DOM.
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const app=fs.readFileSync(path.join(__dirname,'../assets/app.js'),'utf8');
const helpers=app.slice(app.indexOf('function editableSnapshot('),app.indexOf('function renderPreservingFocus('));
const workspace=fs.readFileSync(path.join(__dirname,'../assets/workspace.js'),'utf8');
function element(tag,attrs={},text){
 return {tag,attrs,text,children:[],value:'',checked:false,style:{},classList:{toggle(){}},
  append(...nodes){this.children.push(...nodes)},replaceChildren(...nodes){this.children=[...nodes]},
  focus(){},select(){},addEventListener(){},setAttribute(key,value){this.attrs[key]=value;}};
}
function find(root,predicate){
 if(predicate(root))return root;
 for(const child of root.children||[]){const match=find(child,predicate);if(match)return match;}
}
function fixture(){
 const elements=new Map(),notices=[],drafts=[],timers=[],listeners={};
 const byId=id=>{if(!elements.has(id))elements.set(id,element('section',{id}));return elements.get(id)};
 const initial={id:'doc',revision:1,title:'Before',brief:'',sections:[{id:'s1',title:'First',groups:[]},{id:'s2',title:'Second',groups:[]}],workspace:{},
  _coordination:{mode:'single',items:['A','B'].map(id=>({id,title:id,work_id:'work-'+id,directory:id,summary:id,status:'planned'})),directives:[]}};
 const context={doc:structuredClone(initial),baseDocument:structuredClone(initial),savedRevision:1,
  dirty:false,saving:false,blocked:false,version:0,timer:null,
  $:byId,clone:value=>structuredClone(value),uid:()=> 'new-id',save:async()=>{},
  state(){},notice:text=>notices.push(text),renderPreservingFocus(){},
  persist:()=>drafts.push(structuredClone(context.doc)),draftKey:()=> 'test-draft',localStorage:{removeItem(){}},
  clearTimeout(){},setTimeout:fn=>{timers.push(fn);return timers.length;},
  el:(tag,attrs={},text)=>{const node=element(tag,attrs,text);if(attrs.id)elements.set(attrs.id,node);return node;},
  button:(text,onclick,cls)=>Object.assign(element('button',{class:cls},text),{onclick}),
  document:{createTextNode:text=>element('text',{},text),getElementById:id=>elements.get(id)},
  window:{addEventListener:(type,fn)=>listeners[type]=fn},location:{origin:'http://127.0.0.1:12345'}};
 vm.createContext(context);vm.runInContext(helpers+'\n'+workspace,context);
 return {context,byId,notices,drafts,timers,listeners,initial,read:code=>vm.runInContext(code,context)};
}
const tick=()=>new Promise(setImmediate);
function delayedForm(f){let resolve;f.context.workspaceCommand=()=>new Promise(done=>{resolve=done});return value=>resolve(value);}
function input(node,value){node.value=value;node.oninput();}

async function pendingDocumentEditSurvivesWorkspaceSave(){
 const f=fixture(),c=f.context;let resolve;
 c.api=()=>new Promise(done=>{resolve=done});
 const pending=c.workspaceCommand({area:'coordination',command:{op:'set_mode',mode:'coordinated'}});await tick();
 c.doc.title='Typed while request is pending';c.version++;c.dirty=true;
 resolve({...structuredClone(f.initial),revision:2,workspace:{coordination:{mode:'coordinated'}}});
 assert.equal(await pending,true);assert.equal(c.doc.title,'Typed while request is pending');
 assert.equal(c.doc.workspace.coordination.mode,'coordinated');assert.equal(c.savedRevision,2);
 assert.equal(c.baseDocument.title,'Before');assert.equal(c.dirty,true);assert.ok(f.drafts.length);
}
async function conflictingDocumentEditIsRetained(){
 const f=fixture(),c=f.context;let resolve;c.api=()=>new Promise(done=>{resolve=done});
 const pending=c.workspaceCommand({area:'style',choice:{brief:'Direction'}});await tick();
 c.doc.title='Local pending title';c.version++;c.dirty=true;
 resolve({...structuredClone(f.initial),revision:2,title:'Other title'});
 assert.equal(await pending,false);assert.equal(c.doc.title,'Local pending title');
 assert.equal(c.blocked,true);assert.equal(f.drafts.at(-1).title,'Local pending title');
}
async function pendingDirectiveDraftIsRetained(){
 const f=fixture(),c=f.context,finish=delayedForm(f);c.renderProjectOverview();
 const form=find(f.byId('project-overview'),n=>n.tag==='form');
 input(f.byId('directive-text'),'First requirement');f.read("directiveTargets.add('A')");
 const pending=form.onsubmit({preventDefault(){}});
 input(f.byId('directive-text'),'New requirement typed while saving');f.read("directiveTargets.add('B')");
 finish(true);await pending;
 assert.equal(f.read('directiveDraft'),'New requirement typed while saving');
 assert.deepEqual([...f.read('directiveTargets')],['A','B']);
}
async function targetOnlyChangeIsRetained(){
 const f=fixture(),c=f.context,finish=delayedForm(f);c.renderProjectOverview();
 const form=find(f.byId('project-overview'),n=>n.tag==='form');input(f.byId('directive-text'),'Same text, new target');f.read("directiveTargets.add('A')");
 const pending=form.onsubmit({preventDefault(){}});f.read("directiveTargets.add('B')");finish(true);await pending;
 assert.equal(f.read('directiveDraft'),'Same text, new target');assert.deepEqual([...f.read('directiveTargets')],['A','B']);
}
async function directiveEditKeepsItsOriginalVersionAfterPolling(){
 const f=fixture(),c=f.context;let submitted;
 c.doc._coordination.directives=[{id:'LOOK',text:'First version',version:1,item_ids:['A'],targets:[]}];
 c.renderProjectOverview();find(f.byId('project-overview'),n=>n.tag==='button'&&n.text==='调整这条要求').onclick();
 input(f.byId('directive-text'),'My edit based on the first version');
 c.doc._coordination.directives=[{id:'LOOK',text:'A concurrent second version',version:2,item_ids:['A'],targets:[]}];
 c.renderProjectOverview();
 c.workspaceCommand=async command=>{submitted=command;return false;};
 await find(f.byId('project-overview'),n=>n.tag==='form').onsubmit({preventDefault(){}});
 assert.equal(submitted.command.expected_version,1,'polling must not silently rebase an old instruction draft');
 assert.equal(submitted.command.directive.text,'My edit based on the first version');
}
async function pendingReferenceRequestIsRetained(){
 const f=fixture(),c=f.context,finish=delayedForm(f);c.renderCreativeReferences();
 const form=find(f.byId('creative-references'),n=>n.tag==='form');input(f.byId('reference-query'),'First query');
 const pending=form.onsubmit({preventDefault(){}});input(f.byId('reference-query'),'Second query during request');finish(true);await pending;
 assert.equal(f.read('referenceQuery'),'Second query during request');
}
async function referenceScopeOnlyChangeIsRetained(){
 const f=fixture(),c=f.context,finish=delayedForm(f);c.renderCreativeReferences();
 const form=find(f.byId('creative-references'),n=>n.tag==='form');input(f.byId('reference-query'),'Same effect for another section');
 f.read("referenceScope='s1'");const pending=form.onsubmit({preventDefault(){}});f.read("referenceScope='s2'");finish(true);await pending;
 assert.equal(f.read('referenceQuery'),'Same effect for another section');assert.equal(f.read('referenceScope'),'s2');
}
async function pendingReferenceFeedbackIsRetained(){
 const f=fixture(),c=f.context,finish=delayedForm(f);
 c.doc._references={current:{id:'round-1',status:'exhausted',query:'Effect',candidates:[]}};c.renderCreativeReferences();
 const root=f.byId('creative-references');input(find(root,n=>n.attrs?.['aria-label']==='换一组的反馈'),'First feedback');
 const next=find(root,n=>n.tag==='button'&&n.text==='这组不合适，换三个');const pending=next.onclick();
 input(find(root,n=>n.attrs?.['aria-label']==='换一组的反馈'),'New feedback while saving');finish(true);await pending;
 assert.equal(f.read('referenceFeedback'),'New feedback while saving');
}
async function explicitRequestForNewReferencesNeedsNoExtraFeedback(){
 const f=fixture(),c=f.context;let submitted;
 c.doc._references={current:{id:'round-1',status:'exhausted',query:'Effect',candidates:[]}};
 c.workspaceCommand=async command=>{submitted=command;return false;};
 c.renderCreativeReferences();
 await find(f.byId('creative-references'),n=>n.tag==='button'&&n.text==='这组不合适，换三个').onclick();
 assert.equal(submitted.area,'references');assert.equal(submitted.command.action,'reject');
 assert.equal(submitted.command.session_id,'round-1');assert.ok(submitted.command.feedback.trim());
}
(async()=>{
 const tests=[pendingDocumentEditSurvivesWorkspaceSave,conflictingDocumentEditIsRetained,pendingDirectiveDraftIsRetained,
  targetOnlyChangeIsRetained,directiveEditKeepsItsOriginalVersionAfterPolling,pendingReferenceRequestIsRetained,referenceScopeOnlyChangeIsRetained,
  pendingReferenceFeedbackIsRetained,explicitRequestForNewReferencesNeedsNoExtraFeedback];
 let failed=0;
 for(const test of tests){try{await test();process.stdout.write('PASS '+test.name+'\n');}catch(error){failed++;console.error('FAIL '+test.name+': '+error.message);}}
 if(failed)process.exitCode=1;else process.stdout.write(tests.length+' workspace regressions passed\n');
})().catch(error=>{console.error(error);process.exitCode=1;});
