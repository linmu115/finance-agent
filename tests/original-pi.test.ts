import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtemp,readFile,writeFile,mkdir} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import path from 'node:path';
import {randomUUID,createHash} from 'node:crypto';
import {setTimeout as delay} from 'node:timers/promises';
import {ModelRuntime} from '@earendil-works/pi-coding-agent';
import {createAssistantMessageEventStream,normalizeContext,getCurrentTools,getCurrentSystemPrompt,getCurrentSystemMessage,type AssistantMessage} from '@earendil-works/pi-ai';
import {fauxAssistantMessage as answer,fauxToolCall as tool} from '@earendil-works/pi-ai/providers/faux';
import {ORIGINAL_PI_PROMPT,ORIGINAL_PI_TOOLS} from '../server/original-pi.js';
import {evaluationRuntime,evaluationIsolation,withEvaluationScope} from '../server/evaluation-isolation.js';
import {normalizeEvaluation} from '../server/evaluation-budget.js';

const sha=(value:string)=>createHash('sha256').update(value).digest('hex');
const expectedSha='6c71fd727034260afcaa6e29e833ff27000cb7f246b2b0ffc83aa867be20c32f';
const profiles=['original_pi','prepared','financial'] as const;
const limits={max_model_calls:40,max_input_tokens:1000000,max_output_tokens:100000,max_total_tokens:1100000,max_wall_seconds:90};
const options=(profile:typeof profiles[number])=>({profile,budget_group_id:profile,budget:limits,isolation_key:profile+'-chain',analysis_only:true});

test('explicit evaluation profile preserves legacy prompt and ten tool schemas',()=>{
 assert.equal(sha(ORIGINAL_PI_PROMPT),expectedSha);
 assert.equal(normalizeEvaluation(options('original_pi'))?.profile,'original_pi');
 assert.equal(normalizeEvaluation(undefined),undefined);
 assert.equal(ORIGINAL_PI_TOOLS.length,10);
 assert.deepEqual(ORIGINAL_PI_TOOLS.map(t=>t.name),['prepare_document_sources','list_documents','get_document','get_document_index','get_source_page','get_source_table','search_evidence','run_analysis','get_analysis_status','get_artifact']);
 for(const spec of ORIGINAL_PI_TOOLS)assert.equal(spec.inputSchema.additionalProperties,false);
 const analysis=ORIGINAL_PI_TOOLS.find(t=>t.name==='run_analysis')!;
 assert.deepEqual(Object.keys(analysis.inputSchema.properties),['code','document_ids','timeout_seconds']);
 assert.deepEqual(analysis.inputSchema.required,['code']);
 assert.deepEqual(Object.keys(ORIGINAL_PI_TOOLS.find(t=>t.name==='get_artifact')!.inputSchema.properties),['run_id','name']);
});

test('three-arm native request capture, exclusions, MCP scope and common retry/audit',{timeout:120000},async()=>{
 const dir=await mkdtemp(path.join(tmpdir(),'finance-original-pi-'));process.env.FINANCE_DATA_DIR=dir;
 const {loadSettings,saveSettings,getSettings}=await import('../server/config.js');
 const {FinanceService}=await import('../server/mcp.js');const {RunManager}=await import('../server/runs.js');
 const {exportReportPackage}=await import('../server/report-package.js');
 await loadSettings();await saveSettings({llm:{baseUrl:'http://127.0.0.1:9/v1',model:'three-arm-offline',apiKey:'fixture',contextWindow:128000,maxTokens:4096}});
 const service=new FinanceService();await service.connect();const manager:any=new RunManager(service);
 // No HTTP server or sandbox is started. Native Pi, MCP and audit are real.
 manager.bridge={register:async()=>({}),unregister:()=>{},close:async()=>{}};
 const priorStream=ModelRuntime.prototype.streamSimple;
 let responses:AssistantMessage[]=[],contexts:any[]=[],requestOptions:any[]=[];
 ModelRuntime.prototype.streamSimple=function(model,context,config){
  const transcript=normalizeContext(context),tools=getCurrentTools(transcript.messages);
  const stream=createAssistantMessageEventStream(),next=tools.length?responses.shift():answer('{"task":"analysis","afterIngestion":"high","reason":"合成分析"}');assert.ok(next,'unexpected offline model request');
  contexts.push(structuredClone({messages:transcript.messages,systemPrompt:getCurrentSystemPrompt(transcript.messages),tools}));requestOptions.push({api:model.api,model:model.id,provider:model.provider,contextWindow:model.contextWindow,maxRetries:config?.maxRetries,reasoning:config?.reasoning,maxTokens:config?.maxTokens});
  const message={...next,api:model.api,model:model.id,provider:model.provider,timestamp:Date.now()};
  void(async()=>{
   await config?.onPayload?.({messages:context.messages},model);
   await config?.onResponse?.({status:200,headers:{'content-type':'text/event-stream'}},model);
   stream.push({type:'start',partial:message});
   if(message.stopReason==='error')stream.push({type:'error',reason:'error',error:message});
   else stream.push({type:'done',reason:message.stopReason as 'stop'|'toolUse'|'length',message});
  })();return stream;
 };
 const originalCall=service.call.bind(service);let calls:any[]=[];
 const table={columns:{value:{unit:'元',currency:'CNY'}},row_keys:['0'],rows:[{value:'137'}]};
 service.call=async(name,args,signal)=>{
  const runtime=evaluationRuntime.getStore();calls.push({name,args:structuredClone(args),profile:runtime?.profile,isolation_key:evaluationIsolation.getStore(),analysis_only:runtime?.analysis_only});
  if(name==='run_analysis')return {status:'accepted',data:{run_id:'synthetic-analysis',state:'queued'},source_refs:[],warnings:[],trace_id:'fixture'};
  if(name==='get_analysis_status')return {status:'ok',data:{run_id:'synthetic-analysis',status:'succeeded',artifacts:[],stdout:'137',...(runtime?.profile==='original_pi'?{}:{numeric_tables:{result:table}})},source_refs:[],warnings:[],trace_id:'fixture'};
  return originalCall(name,args,signal);
 };
 const captures:Record<string,any>={};
 try{
  await service.call('create_project',{project_id:'p',name:'Synthetic fixture'});
  const source=path.join(dir,'uploads','source.csv');await writeFile(source,'项目,本期\n收入,137\n');
  const doc=(await service.call('register_document',{project_id:'p',path:source,original_name:'source.csv'})).data.document_id;
  // Actual stdio metadata reaches Python; ordinary preparation still parses once.
  for(const profile of profiles){
   await assert.rejects(withEvaluationScope(options(profile),()=>service.call('prepare_document_sources',{project_id:'p',document_ids:[doc]})),/analysis_sources_not_prepared/);
  }
  await service.call('prepare_document_sources',{project_id:'p',document_ids:[doc]});
  for(const profile of profiles){
   calls=[];contexts=[];requestOptions=[];
   const c:any={id:randomUUID(),projectId:'p',title:'Synthetic fixture',messages:[],createdAt:new Date().toISOString(),updatedAt:new Date().toISOString()};
   await service.putState('p','conversations',c.id,c);manager.indexConversation(c.id,'p');
   const rawAnswer='目标估值 {{missing.0.value}} 元。';
   responses=[answer('断流',{stopReason:'error',errorMessage:'TLS connection closed'}),
    answer(tool('prepare_document_sources',{document_ids:[doc]}),{stopReason:'toolUse'}),
    answer(tool('run_analysis',{code:'print(137)'}),{stopReason:'toolUse'}),
    answer(tool('get_analysis_status',{run_id:'synthetic-analysis'}),{stopReason:'toolUse'}),answer(rawAnswer),
    ...(profile==='original_pi'?[]:[answer('结果为 {{result.0.value}}。')])];
   const started=await manager.start(c,'请根据现有原文计算并给出估值。',[],undefined,options(profile));
   const deadline=Date.now()+60000;
   while(manager.activeFor(c.id)){if(Date.now()>deadline)throw Error('offline request capture timeout');await delay(20);}
   const state=await manager.getRun(started.id),chat=await manager.getConversation(c.id);
   assert.equal(state.status,'completed',state.error);assert.equal(responses.length,0);
   const events=(await readFile(path.join(dir,'audit',started.id+'.jsonl'),'utf8')).trim().split('\n').map(s=>JSON.parse(s));
   const initialIndex=contexts.findIndex(c=>c.tools.length),initial=contexts[initialIndex],visible=initial.tools.map((t:any)=>t.name),entry=manager.sessions.get(c.id);
   assert.deepEqual(events.filter(e=>e.type==='transport_retry_start').map(e=>e.data.delayMs),[2000]);
   assert.equal(events.filter(e=>e.type==='model_request').length,contexts.length);
   assert.equal(events.filter(e=>e.type==='model_usage').length,contexts.length);
   assert.equal(events.find(e=>e.type==='run_config').data.profile,profile);
   assert.ok((await readFile(path.join(dir,'workspaces/p',c.id,'sessions/session.jsonl'),'utf8')).includes('TLS connection closed'));
   assert.deepEqual(calls.filter(c=>c.name==='run_analysis').map(c=>[c.args.raw_only,c.args.financial_tools]),[[profile==='original_pi',profile==='financial']]);
   assert.ok(calls.filter(c=>['run_analysis','get_analysis_status','prepare_document_sources','render_answer'].includes(c.name)).every(c=>c.profile===profile&&c.isolation_key===profile+'-chain'&&c.analysis_only));
   if(profile==='original_pi'){
    const sections=getCurrentSystemMessage(initial.messages)!.sections!;
    assert.equal(sections.preamble,ORIGINAL_PI_PROMPT);
    assert.equal(sha(sections.preamble!),expectedSha);
    assert.deepEqual(Object.keys(sections),['preamble','cwd'],'only legacy prompt and common native cwd');
    assert.equal(initial.systemPrompt,ORIGINAL_PI_PROMPT+'\n\n'+sections.cwd);
    assert.deepEqual(initial.tools,ORIGINAL_PI_TOOLS.map(({name,description,inputSchema})=>({name,description,parameters:inputSchema})));
    assert.equal(chat.messages.at(-1).content,rawAnswer,'no binding, repair, semantic annotation or valuation validation');
    assert.equal(calls.some(c=>c.name==='render_answer'),false);
    assert.equal(events.some(e=>e.type==='project_resources'||e.type.startsWith('answer_')),false);
    assert.equal(initial.messages.some((m:any)=>JSON.stringify(m).includes('statement_analysis')),false);
    assert.throws(()=>exportReportPackage(service,chat),/original_pi 不提供标准报告包/);
    // Enforced on the execution entry, even if called outside native schema validation.
    const live={controller:new AbortController(),run:{projectId:'p',request:{evaluation:options(profile)}},chat};
    for(const name of ['query_financial_data','query_research_records','financial_workpaper','run_financial_model','read_project_skill','list_research_artifacts','render_answer','process_documents']){
     await assert.rejects(manager.executeTool(live,getSettings(),name,'forbidden',{}),/工具不属于当前运行配置/);
    }
    for(const args of [{code:'pass',report:{}},{code:'pass',source_run_id:'x'},{code:'pass',params:{}},{code:'pass',model_refs:{}},{code:'pass',edits:[]}]){
     await assert.rejects(manager.executeTool(live,getSettings(),'run_analysis','forbidden',args),/original_pi 不提供此工具参数/);
    }
    await assert.rejects(manager.executeTool(live,getSettings(),'get_artifact','forbidden',{run_id:'x',name:'x.csv',rows:{start:0}}),/original_pi 不提供此工具参数/);
   }else{
    assert.ok(visible.includes('query_financial_data'));assert.ok(visible.includes('query_research_records'));
    assert.ok(calls.some(c=>c.name==='render_answer'));assert.match(chat.messages.at(-1).content,/137/);
    assert.equal(visible.includes('financial_workpaper'),profile==='financial');
   }
   const sections=getCurrentSystemMessage(initial.messages)!.sections!;
   captures[profile]={systemPrompt:initial.systemPrompt,fullNativePromptSha256:sha(initial.systemPrompt),promptSections:sections,
    configuredPromptSha256:sha(sections.preamble!),tools:initial.tools,
    toolsSha256:sha(JSON.stringify(initial.tools)),requestOptions:requestOptions[initialIndex],requestCount:contexts.length,
    routerPrompt:contexts.find(c=>!c.tools.length)?.systemPrompt,routerRequestOptions:requestOptions.find(o=>o.maxRetries===undefined),
    runtimeClass:entry.runtime.constructor.name,sessionClass:entry.session.constructor.name,
    compaction:getSettings().runtime.contextCompaction,
    hostCalls:calls.filter(c=>['prepare_document_sources','run_analysis','get_analysis_status','render_answer'].includes(c.name)),
    events:events.map(e=>e.type),answer:chat.messages.at(-1).content};
  }
  assert.equal(captures.prepared.tools.length,13);
  for(const key of ['requestOptions','runtimeClass','sessionClass','compaction','routerPrompt','routerRequestOptions']){
   assert.deepEqual(captures.original_pi[key],captures.prepared[key],key);
   assert.deepEqual(captures.original_pi[key],captures.financial[key],key);
  }
  // Evaluation context is request-local and cannot bleed into ordinary product calls.
  assert.equal(evaluationRuntime.getStore(),undefined);assert.equal(evaluationIsolation.getStore(),undefined);
  if(process.env.ORIGINAL_PI_EVIDENCE_DIR){
   const target=process.env.ORIGINAL_PI_EVIDENCE_DIR;await mkdir(target,{recursive:true});
   await writeFile(path.join(target,'native-request-capture.json'),JSON.stringify({mode:'scripted provider on actual Pi/RunManager; real stdio MCP; fake sandbox result; no HTTP listener',profiles:captures},null,2)+'\n');
  }
 }finally{
  ModelRuntime.prototype.streamSimple=priorStream;await manager.shutdown();await service.close();
 }
});
