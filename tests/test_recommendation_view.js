'use strict';
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const source=fs.readFileSync(path.join(__dirname,'../assets/app.js'),'utf8');
const code=source.slice(source.indexOf('function recommendationLabel('),source.indexOf('async function chooseRoute('));
function element(tag,attrs={},text=''){
 return {tag,attrs,text,children:[],append(...children){this.children.push(...children);}};
}
function flatten(node){return [node.text||'',...node.children.map(flatten)].join('\n');}
function fixture(basis){
 const plan={id:'plan',shot_ids:['s'],data:{decision_type:'generation_recommendation',
  options:[{id:'a',path:'direct_platform',recommended:true,label:'A',model:'model A',reason:'Both can work.'},{id:'b',path:'direct_platform',recommended:false,label:'B',model:'model B'}],
  method_evidence:{status:'reused',summary:'Capability is confirmed; quality ranking is not.',sources:[{kind:'official',url:'https://example.com',applied:'duration supported'},{kind:'observed_result',url:'record:result-1',applied:'checked motion on one sample'}]}}};
 if(basis)plan.data.selection_basis=basis;
 const context={el:element,button:(label,handler,cls)=>element('button',{class:cls},label),
  activeRecords:()=>[plan],doc:{sections:[],_record_states:{},_current_routes:{}},openRehearsal:()=>{},chooseRoute:()=>{}};
 vm.createContext(context);vm.runInContext(code,context);return context;
}
const basis={status:'provisional',priorities:['motion continuity','reuse inputs'],comparison:'No measured quality advantage.',cost:'Price unknown.',uncertainty:'Motion untested.'};
for(const review of [false,true]){
 const c=fixture(basis),root=element('main');c.renderSequencePlan(root,review);const text=flatten(root);
 for(const value of ['暂定推荐','motion continuity','No measured quality advantage.','Price unknown.','Motion untested.','官方能力资料','已检查的生成结果','record:result-1'])assert.ok(text.includes(value),value);
 const buttons=[];function walk(n){if(n.tag==='button')buttons.push(n);n.children.forEach(walk);}walk(root);
 assert.equal(buttons.filter(n=>n.text==='选择此方案').length,2);
 assert.ok(buttons.filter(n=>n.text==='选择此方案').every(n=>!n.disabled));
}
{
 const c=fixture(),root=element('main');c.renderSequencePlan(root,false);const text=flatten(root);
 assert.ok(text.includes('尚未单独记录模型间的比较依据'));assert.ok(text.includes('选择此方案'));assert.ok(!text.includes('暂定推荐'));
}
{
 const c=fixture({...basis,status:'user_specified'}),root=element('main');c.renderSequencePlan(root,false);
 assert.ok(flatten(root).includes('用户指定'));
}
process.stdout.write('4 recommendation rendering regressions passed\n');
