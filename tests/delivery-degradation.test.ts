import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtemp,readFile,mkdir,writeFile} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import path from 'node:path';
import {randomUUID,createHash} from 'node:crypto';
import {setTimeout as delay} from 'node:timers/promises';
import {createFauxCore,fauxAssistantMessage as answer,fauxToolCall as tool} from '@earendil-works/pi-ai/providers/faux';

const fixture=(name:string)=>readFile(new URL('./fixtures/v3-delivery/'+name,import.meta.url),'utf8');
test('native delivery: actual failures, one shared repair, retained attachments and all three profiles',{timeout:180000},async()=>{
 const dir=await mkdtemp(path.join(tmpdir(),'finance-v3-delivery-'));process.env.FINANCE_DATA_DIR=dir;
 const {loadSettings,saveSettings}=await import('../server/config.js');
 const {FinanceService}=await import('../server/mcp.js');const {RunManager}=await import('../server/runs.js');
 await loadSettings();await saveSettings({llm:{baseUrl:'http://127.0.0.1:9/v1',model:'delivery-offline-fixture',apiKey:'fixture',contextWindow:128000,maxTokens:4096}});
 const service=new FinanceService();await service.connect();const manager:any=new RunManager(service);
 manager.bridge={register:async()=>({}),unregister:()=>{},close:async()=>{}};
 const faux=createFauxCore({tokensPerSecond:0}),sessionFor=manager.sessionFor.bind(manager);
 manager.sessionFor=async(...args:any[])=>{const entry=await sessionFor(...args);entry.runtime.streamSimple=faux.streamSimple;return entry;};
 const tables={...JSON.parse(await fixture('F1_X3-tables.json')),...JSON.parse(await fixture('P2_X7-tables.json'))};
 const original=service.call.bind(service),project='delivery-fixture';
 const manifests=new Map<string,any>();
 const delivery=async(text:string,xlsx=false)=>{
  const id=randomUUID().replaceAll('-',''),folder=path.join(dir,'research',project,'deliveries',id);await mkdir(folder,{recursive:true});
  const files=[];
  for(const [name,content] of Object.entries({'report.md':text,'changes.csv':'指标,描述\n现金流,'+text,'ocf_contribution.png':'fixture image','column_choice_chart.png':'fixture image','haier_comparison.png':'fixture image'})){
   await writeFile(path.join(folder,name),content);files.push({name,size:Buffer.byteLength(content),sha256:createHash('sha256').update(content).digest('hex')});
  }
  if(xlsx){
   const content=await readFile(new URL('./fixtures/f21/F1_X7.xlsx',import.meta.url));
   await writeFile(path.join(folder,'workbook.xlsx'),content);
   files.push({name:'workbook.xlsx',size:content.length,sha256:createHash('sha256').update(content).digest('hex')});
  }
  await writeFile(path.join(folder,'delivery.json'),JSON.stringify({delivery_id:id,isolation_key:'chain',files}));manifests.set(id,files);return id;
 };
 service.call=async(name,args,signal)=>{
  if(name==='get_analysis_status')return {status:'ok',data:{status:'succeeded',artifacts:manifests.get(args.run_id),numeric_tables:tables}};
  return original(name,args,signal);
 };
 const runCase=async(profile:'financial'|'generic'|'prepared'|'original_pi',responses:any[])=>{
  const chat:any={id:randomUUID(),projectId:project,title:'Fixture',messages:[],createdAt:new Date().toISOString(),updatedAt:new Date().toISOString()};
  await service.putState(project,'conversations',chat.id,chat);manager.indexConversation(chat.id,project);faux.setResponses(responses);
  const run=await manager.start(chat,'分析当前资料',[],undefined,{profile,budget_group_id:chat.id,isolation_key:'chain',analysis_only:true,budget:{max_model_calls:50,max_input_tokens:0,max_output_tokens:0,max_total_tokens:0,max_wall_seconds:60}});
  const end=Date.now()+40000;while(manager.activeFor(chat.id)&&Date.now()<end)await delay(20);
  assert.equal(manager.activeFor(chat.id),undefined);const state=await manager.getRun(run.id);
  assert.equal(state.status,'completed',state.error);assert.equal(faux.getPendingResponseCount(),0);
  const last=(await manager.getConversation(chat.id)).messages.at(-1);
  const audit=(await readFile(path.join(dir,'audit',run.id+'.jsonl'),'utf8')).trim().split('\n').map(x=>JSON.parse(x));
  const native=(await readFile(path.join(dir,'workspaces',project,chat.id,'sessions/session.jsonl'),'utf8')).trim().split('\n').map(x=>JSON.parse(x));
  assert.equal(native.findLast(e=>e.type==='message'&&e.message?.role==='assistant').message.content.filter((b:any)=>b.type==='text').map((b:any)=>b.text).join(''),last.content);
  return {last,audit,repairs:native.filter(e=>e.customType==='answer_reference_error').length};
 };
 try{
  await service.call('create_project',{project_id:project,name:'Offline delivery'});
  const clean=await delivery('变化为 -3亿元。');
  const real=await runCase('financial',[answer(tool('get_analysis_status',{run_id:clean}),{stopReason:'toolUse'}),answer(await fixture('F1_X3-1.md')),answer(await fixture('F1_X3-2.md'))]);
  assert.equal(real.repairs,1);assert.equal(real.last.artifacts.length,5);
  assert.match(real.last.content,/\[引用无效：\{\{get_artifact\(\.\.\.\)\}\}\]/);
  assert.match(real.last.content,/\| 合并净利润 \|/);assert.match(real.last.content,/!\[ocf_contribution.png\]/);
  assert.equal(real.audit.filter(e=>e.type==='answer_reference_rewrite').length,2);
  assert.equal(real.audit.filter(e=>e.type==='answer_degraded').length,1);
  for(const [profile,label] of [['financial','F2_X7'],['prepared','P2_X7']] as const){
   const passed=await runCase(profile,[answer(tool('get_analysis_status',{run_id:clean}),{stopReason:'toolUse'}),answer(await fixture(label+'-1.md'))]);
   assert.equal(passed.repairs,0);assert.equal(passed.audit.filter(e=>e.type==='answer_degraded').length,0);
  }
  const bad=await delivery('同比增长 -3%');
  const text='目标价20元。现金流增加 -3亿元。\n{{missing.row.value}}\n{{table:key_metrics}}';
  for(const profile of ['financial','generic','prepared'] as const){
   const degraded=await runCase(profile,[answer(tool('get_analysis_status',{run_id:bad}),{stopReason:'toolUse'}),answer(text),answer(text)]);
   assert.equal(degraded.repairs,1);assert.equal(degraded.last.artifacts.length,5);
   assert.match(degraded.last.content,/report.md 第1行/);assert.match(degraded.last.content,/changes.csv 第2行/);
   assert.match(degraded.last.content,/估值说明缺少：假设/);assert.match(degraded.last.content,/估值说明缺少：风险/);
   assert.match(degraded.last.content,/估值说明缺少：适用范围/);assert.match(degraded.last.content,/\| 合并净利润 \|/);
   const issues=degraded.audit.find(e=>e.type==='answer_degraded').data.issues;
   assert.deepEqual(new Set(issues.map((i:any)=>i.kind)),new Set(['reference','direction','valuation_section']));
   assert.equal(degraded.audit.filter(e=>e.type==='ingestion_continuation').length,0);
  }
  // A corrected rerun replaces the old named files. A1 must inspect the delivered version.
  const repaired=await runCase('prepared',[answer(tool('get_analysis_status',{run_id:bad}),{stopReason:'toolUse'}),answer('现金流增加 -3亿元。'),
   answer(tool('get_analysis_status',{run_id:clean}),{stopReason:'toolUse'}),answer('现金流减少 3亿元。')]);
  assert.equal(repaired.repairs,1);assert.equal(repaired.last.artifacts.length,5);
  assert.ok(repaired.last.artifacts.every((a:any)=>a.url.includes(clean)));
  assert.equal(repaired.audit.filter(e=>e.type==='answer_degraded').length,0);
  // Unresolved relation assertions in the actual F1_X7 workbook are notices only.
  const workbook=await delivery('变化已列示。',true);
  for(const profile of ['prepared','financial','original_pi'] as const){
   const result=await runCase(profile,[answer(tool('get_analysis_status',{run_id:workbook}),{stopReason:'toolUse'}),answer('变化已列示。')]);
   assert.equal(result.repairs,0);assert.equal(result.last.artifacts.length,6);
   assert.equal(result.audit.filter(e=>e.type==='answer_degraded').length,0);
   if(profile==='original_pi'){
    assert.doesNotMatch(result.last.content,/关系方向断言需核对/);
    assert.equal(result.audit.filter(e=>e.type==='answer_direction_notices').length,0);
   }else{
    assert.match(result.last.content,/关系方向断言需核对/);
    assert.match(result.last.content,/workbook.xlsx Calculations!F10/);
    assert.equal(result.audit.filter(e=>e.type==='answer_direction_notices').length,1);
   }
  }
 }finally{await manager.shutdown();await service.close();}
});
