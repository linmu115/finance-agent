import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtemp,readFile} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import path from 'node:path';
import {randomUUID} from 'node:crypto';
import {setTimeout as delay} from 'node:timers/promises';
import {createFauxCore,fauxAssistantMessage as answer,fauxToolCall as tool} from '@earendil-works/pi-ai/providers/faux';

test('shared native A1 repair handles section and reference failures once, then exports persisted exact tables',{timeout:60000},async()=>{
 const dir=await mkdtemp(path.join(tmpdir(),'finance-analyst-delivery-'));process.env.FINANCE_DATA_DIR=dir;
 const {loadSettings,saveSettings}=await import('../server/config.js');
 const {FinanceService}=await import('../server/mcp.js');const {RunManager}=await import('../server/runs.js');
 const {exportReportPackage,reportSnapshot}=await import('../server/report-package.js');
 await loadSettings();await saveSettings({llm:{baseUrl:'http://127.0.0.1:9/v1',model:'offline',apiKey:'fixture',contextWindow:128000,maxTokens:4096}});
 const service=new FinanceService();await service.connect();const manager:any=new RunManager(service);
 manager.bridge={register:async()=>({}),unregister:()=>{},close:async()=>{}};
 const faux=createFauxCore({tokensPerSecond:0}),sessionFor=manager.sessionFor.bind(manager);
 manager.sessionFor=async(...args:any[])=>{const e=await sessionFor(...args);e.runtime.streamSimple=faux.streamSimple;return e;};
 const original=service.call.bind(service);
 const tables={valuation:{columns:{item:{label:'项目'},value:{unit:'元/股',currency:'CNY',decimals:2}},rows:[{item:'price',value:'12.0715486123456789'}],row_keys:['price'],evidence:[{value:{formula:'FCF / shares',inputs:[{value:'12.0715486123456789',source:{user_input:true}}]}}]}};
 service.call=async(name,args,signal)=>name==='get_analysis_status'?{status:'ok',data:{run_id:args.run_id,status:'succeeded',artifacts:[],numeric_tables:tables}}:original(name,args,signal);
 const wait=async(id:string)=>{while(manager.activeFor((await manager.getRun(id)).conversationId))await delay(20);return manager.getRun(id);};
 const evaluation=(profile:string)=>({profile,budget_group_id:randomUUID(),budget:{max_model_calls:10,max_input_tokens:1000000,max_output_tokens:100000,max_total_tokens:1100000,max_wall_seconds:50}});
 const make=async(profile:string)=>{const c:any={id:randomUUID(),projectId:'test',title:'测试财报分析',createdAt:new Date().toISOString(),updatedAt:new Date().toISOString(),messages:[],evaluationProfile:profile};await service.putState('test','conversations',c.id,c);manager.indexConversation(c.id,'test');return c;};
 try{
  await service.call('create_project',{project_id:'test',name:'Analyst delivery'});
  for(const profile of ['prepared','financial']){
   const chat=await make(profile);
   faux.setResponses([answer(tool('get_analysis_status',{run_id:'saved'}),{stopReason:'toolUse'}),answer('目标价 {{valuation.bad.value}}。'),answer('目标价 {{valuation.price.value}}。\n\n{{table:valuation}}\n\n## 假设\n【推论】输入情景不变。\n## 风险\n【推论】现金流可能低于情景。\n## 适用范围\n【观点】仅适用于本次模型。')]);
   const run=await manager.start(chat,'给出模型估值。',[],undefined,evaluation(profile));assert.equal((await wait(run.id)).status,'completed');
   const saved=await manager.getConversation(chat.id),text=saved.messages.at(-1).content;
   assert.match(text,/【事实\/数据】目标价 12.07 CNY 元\/股/);assert.match(text,/\n\n\|/);assert.ok(!text.includes('{{'));
   const events=(await readFile(path.join(dir,'audit',run.id+'.jsonl'),'utf8')).trim().split('\n').map(l=>JSON.parse(l));
   const failures=events.filter(e=>e.type==='answer_binding_error');assert.equal(failures.length,1);assert.match(failures[0].data.message,/假设/);assert.match(failures[0].data.message,/可用行键/);
   const snapshot=await reportSnapshot(saved);assert.deepEqual(snapshot.turns[0].tables,tables);
   const exported=await exportReportPackage(service,saved);assert.deepEqual(exported.files,['report.md','report.pdf','workpapers.xlsx','snapshot.json']);
   const zip=await readFile(path.join(dir,exported.relative_path));assert.equal(zip.subarray(0,2).toString(),'PK');
   const md=await readFile(path.join(dir,path.dirname(exported.relative_path),'report.md'),'utf8');
   for(const heading of ['结论','关键数据','业绩变化归因','特殊损益与口径','异常信号','估值','假设、风险与局限','来源'])assert.ok(md.includes('## '+heading));
  }
  const chat=await make('prepared');faux.setResponses([answer('目标价 20 元。'),answer('目标价 21 元。')]);
  const run=await manager.start(chat,'估值',[],undefined,evaluation('prepared')),failed=await wait(run.id);assert.equal(failed.status,'failed');assert.match(failed.error,/假设/);assert.equal(faux.getPendingResponseCount(),0);
 }finally{await manager.shutdown();await service.close();}
});
