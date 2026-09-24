'use strict';
// Exercise the actual UI functions with delayed transport, without a DOM or a server.
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const source=fs.readFileSync(path.join(__dirname,'../assets/app.js'),'utf8');
const helpers=source.slice(source.indexOf('function editableSnapshot('),source.indexOf('function renderPreservingFocus('));
const choose=source.slice(source.indexOf('async function chooseRoute('),source.indexOf('let rehearsalTimer'));
const save=source.slice(source.indexOf('async function save('),source.indexOf('function editField('));

function fixture(){
 let resolveRoute, rejectRoute;
 const saved=[],timers=[],drafts=[];
 const initial={id:'doc',revision:1,title:'Before',brief:'',sections:[{id:'sec',groups:[{id:'group',shots:[{id:'shot',content:'Before'}]}]}],production:{records:[]}};
 const context={doc:structuredClone(initial),baseDocument:structuredClone(initial),savedRevision:1,
  dirty:false,saving:false,blocked:false,version:0,timer:null,
  clone:x=>structuredClone(x),state:()=>{},notice:()=>{},renderPreservingFocus:()=>{},renderSectionStates:()=>{},
  $:()=>({hidden:false}),draftKey:()=> 'test-draft',localStorage:{removeItem:()=>{}},
  persist:()=>drafts.push(structuredClone(context.doc)),setTimeout:fn=>{timers.push(fn);return timers.length;},
  api:async(url,body)=>{
   if(url==='/api/routes/choose')return new Promise((resolve,reject)=>{resolveRoute=resolve;rejectRoute=reject;});
   assert.equal(url,'/api/document');saved.push(structuredClone(body));
   return {...structuredClone(body.document),revision:body.expected_revision+1};
  }};
 vm.createContext(context);vm.runInContext(helpers+'\n'+save+'\n'+choose,context);
 return {context,initial,saved,timers,drafts,resolve:value=>resolveRoute(value),reject:error=>rejectRoute(error)};
}
const tick=()=>new Promise(setImmediate);
async function preservesPendingEdit(){
 const f=fixture(),c=f.context;
 const pending=c.chooseRoute('PLAN','direct_platform');await tick();
 assert.equal(c.saving,true);
 c.doc.sections[0].groups[0].shots[0].content='Typed while choosing route';c.version++;c.dirty=true;
 const remote={...structuredClone(f.initial),revision:2,production:{records:[{id:'route-PLAN'}]}};
 f.resolve(remote);await pending;
 assert.equal(c.doc.sections[0].groups[0].shots[0].content,'Typed while choosing route');
 assert.equal(c.doc.production.records[0].id,'route-PLAN');assert.equal(c.savedRevision,2);
 assert.equal(c.baseDocument.sections[0].groups[0].shots[0].content,'Before');assert.equal(c.dirty,true);
 assert.ok(f.drafts.length);assert.equal(c.blocked,false);
 await c.save();
 assert.equal(f.saved.length,1);assert.equal(f.saved[0].expected_revision,2);
 assert.equal(f.saved[0].document.sections[0].groups[0].shots[0].content,'Typed while choosing route');
 assert.equal(c.dirty,false);assert.equal(c.savedRevision,3);
}
async function preservesConflictingDraft(){
 const f=fixture(),c=f.context;
 const pending=c.chooseRoute('PLAN','direct_platform');await tick();
 c.doc.title='My pending title';c.version++;c.dirty=true;
 f.resolve({...structuredClone(f.initial),revision:2,title:'Other title'});await pending;
 assert.equal(c.doc.title,'My pending title');assert.equal(c.blocked,true);assert.equal(c.dirty,true);
 assert.equal(f.saved.length,0);assert.equal(f.drafts.at(-1).title,'My pending title');
}
async function preservesEditAfterFailure(){
 const f=fixture(),c=f.context;
 const pending=c.chooseRoute('PLAN','direct_platform');await tick();
 c.doc.title='Keep after network failure';c.version++;c.dirty=true;
 f.reject(new Error('transport unavailable'));await pending;
 assert.equal(c.doc.title,'Keep after network failure');assert.equal(c.dirty,true);assert.equal(c.saving,false);
 assert.equal(c.savedRevision,1);
}
(async()=>{
 await preservesPendingEdit();await preservesConflictingDraft();await preservesEditAfterFailure();
 process.stdout.write('3 delayed route-choice regressions passed\n');
})().catch(error=>{console.error(error);process.exitCode=1;});
