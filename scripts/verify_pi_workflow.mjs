/** Real HTTP -> persistent Pi sessions -> LangExtract -> official DeepSeek -> SQLite.
 * Creates an isolated project. This driver never reads keys or writes application DBs.
 * Gold is loaded only after all Agent calls complete, and is never sent to the model.
 */
import fs from 'node:fs/promises';
import path from 'node:path';
import {createHash} from 'node:crypto';
import {setTimeout as delay} from 'node:timers/promises';
import {scoreNormalization} from './score_normalization.mjs';
import {extractionEvidence,temporalAcceptance,readPersistedRunAnswer} from './validation_utils.mjs';
import {verifyTemporalCacheEvidence} from './temporal_evidence.mjs';
const root=path.resolve(import.meta.dirname,'..'),suite=path.join(root,'benchmark/versions/v0.3.1-normalization');
const args=process.argv.slice(2),option=(key,fallback)=>args.includes(key)?args[args.indexOf(key)+1]:fallback;
const base=option('--base-url','http://127.0.0.1:3001').replace(/\/$/,''),quick=args.includes('--quick');
const now=()=>new Date().toISOString(),stamp=now().replace(/[:.]/g,'-');
const implementationFiles=['server/runs.ts','server/model-bridge.ts','server/mcp.ts','server/main.ts','server/workspace-api.ts','service/server.py','service/processing.py','service/completed_document.py','service/core.py','service/semantic.py','service/parser.py','service/parser_worker.py','service/normalization.py','service/extraction_alignment.py','service/catalog_model.py','service/catalog_semantics.py','service/temporal_model.py','service/temporal_semantics.py','service/definition_model.py','service/definition_semantics.py','service/temporal_repair.py'];
const implementationHashes=async()=>Object.fromEntries(await Promise.all(implementationFiles.map(async file=>[file,createHash('sha256').update(await fs.readFile(path.join(root,file))).digest('hex')])));
const output=path.resolve(option('--output',path.join(root,'benchmark/results/pi-workflow-'+stamp+'.json')));
const deadlineMs=Number(option('--timeout-seconds',quick?'900':'1800'))*1000;
let report={version:'v0.3.1-normalization',gold_revision:2,scorer_version:'0.3.2-source-conflicts',test_layer:'real_pi_conversation_semantic_ingestion',started_at:now(),status:'running',quick,
 scope:'Small regression suite; not evidence of full annual-report completeness or competition-wide accuracy.',gold_sent_to_agent:false,checks:[],documents:[],runs:[],snapshots:[]};
const save=async()=>{report.updated_at=now();await fs.mkdir(path.dirname(output),{recursive:true});await fs.writeFile(output,JSON.stringify(report,null,2));};
function check(name,passed,evidence){report.checks.push({name,status:passed?'passed':'failed',evidence});console.log(passed?'PASS':'FAIL',name);}
async function request(route,options={}){
 const response=await fetch(base+route,{...options,signal:AbortSignal.timeout(90000)});
 const text=await response.text();let body;try{body=JSON.parse(text);}catch{throw new Error('Non-JSON HTTP '+response.status+' at '+route);}
 if(!response.ok)throw new Error('HTTP '+response.status+' '+route+': '+(body.error?.message||body.error?.code||'request failed'));
 return body;
}
const post=(route,body)=>request(route,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
async function facts(){
 const all=[];let offset=0;
 while(true){const response=await request(`/api/projects/${report.project_id}/financial-data?limit=200&offset=${offset}`);all.push(...response.items);offset+=response.items.length;if(offset>=response.total||!response.items.length)break;}
 return all;
}
async function waitRuns(ids){
 const deadline=Date.now()+deadlineMs;let lastLog=0;
 while(Date.now()<deadline){
  const states=await Promise.all(ids.map(id=>request('/api/runs/'+id)));report.runs=states;
  if(states.every(x=>['completed','failed','cancelled'].includes(x.status))){await save();return states;}
  if(Date.now()-lastLog>15000){console.log('RUNS',states.map(x=>x.status+': '+x.stage).join(' | '));lastLog=Date.now();report.snapshots.push({at:now(),runs:states.map(x=>({id:x.id,status:x.status,stage:x.stage,usage:x.usage}))});await save();}
  await delay(1500);
 }
 throw new Error('Observation deadline reached. Runs may still be active; use --resume '+output+' instead of starting duplicate model calls.');
}
async function auditSummary(run){
 const file=path.join(root,'data/audit',run.id+'.jsonl');
 const events=(await fs.readFile(file,'utf8')).trim().split('\n').filter(Boolean).map(x=>JSON.parse(x));
 const proof=extractionEvidence(events,run.id);
 return {run_id:run.id,persistent_session:events.some(x=>x.type==='run_config'&&x.data.persistentSession),extraction_classes:proof.extraction_classes,valid_owners:proof.valid_owners,temporal_correction_signatures:proof.temporal_correction_signatures,
  extraction_requests:events.filter(x=>x.type==='extraction_request').map(x=>({owner_run_id:x.data.ownerRunId,runtime:x.data.runtime,model:x.data.model})),
  extraction_results:events.filter(x=>x.type==='extraction_result').map(x=>({owner_run_id:x.data.ownerRunId,stop_reason:x.data.stopReason,usage:x.data.usage})),
  processing_started:events.filter(x=>x.type==='processing_started').map(x=>({owner_run_id:x.data.ownerRunId,document_ids:x.data.documentIds})),
  tool_names:[...new Set(events.filter(x=>x.type==='tool_request').map(x=>x.data.name))]};
}
try{
 const resume=option('--resume',null);
 if(resume){report=JSON.parse(await fs.readFile(path.resolve(resume),'utf8'));report.status='running';report.resumed_at=now();}
 else{
  const [health,settings,manifest]=await Promise.all([request('/api/health'),request('/api/settings'),fs.readFile(path.join(suite,'manifest.json'),'utf8').then(JSON.parse)]);
  if(!health.modelConfigured||!settings.llm?.hasKey)throw new Error('Configure the official DeepSeek API in the application first.');
  if(new URL(settings.llm.baseUrl).hostname!=='api.deepseek.com')throw new Error('This live acceptance suite requires the configured official DeepSeek endpoint.');
  report.model={id:settings.llm.model,base_url:settings.llm.baseUrl};
  report.implementation_sha256_before=await implementationHashes();
  report.suite_sha256=createHash('sha256').update(await fs.readFile(path.join(suite,'manifest.json'))).digest('hex');
  report.scorer_sha256=createHash('sha256').update(await fs.readFile(path.join(root,'scripts/score_normalization.mjs'))).digest('hex');
  const files=manifest.inputs.filter(x=>!quick||['01_current_prior_millions.csv','10_moutai_2024_pages5-6.pdf'].includes(x.file));
  for(const item of files){const actual=createHash('sha256').update(await fs.readFile(path.join(suite,'inputs',item.file))).digest('hex');if(actual!==item.sha256)throw new Error('Fixture hash mismatch: '+item.file);}
  const project=await post('/api/projects',{name:'Pi 清洗验证 '+new Date().toLocaleString('zh-CN',{timeZone:'Asia/Shanghai'})});report.project_id=project.id;await save();
  const conversations=await Promise.all([0,1].map(()=>post(`/api/projects/${project.id}/conversations`,{})));report.conversation_ids=conversations.map(x=>x.id);
  const groups=[files.filter((_,i)=>i%2===0),files.filter((_,i)=>i%2===1)];
  for(let i=0;i<groups.length;i++){
   const form=new FormData();for(const item of groups[i])form.append('files',new Blob([await fs.readFile(path.join(suite,'inputs',item.file))]),item.file);
   const uploaded=await request(`/api/projects/${project.id}/uploads`,{method:'POST',body:form});
   report.documents.push(...uploaded.documents.map((d,j)=>({file:groups[i][j].file,id:d.id,conversation_id:conversations[i].id,initial_status:d.status})));
  }
  await delay(2000);const before=await facts(),docsBefore=await request(`/api/projects/${project.id}/documents`);
  check('附件上传只登记，发送前没有自动清洗入库',before.length===0&&docsBefore.documents.every(d=>['uploaded','registered'].includes(d.status)),{fact_count:before.length,documents:docsBefore.documents.map(d=>({id:d.id,status:d.status}))});
  const prompt='请处理这些附件。读取全部可提取的财务主表和附注表，理解字段、期间、币种、单位、合并或母公司口径、分部及重述版本，清洗后入库并更新财报看板。本次需要重新清洗，请使用 force=true，避免复用既有模型映射缓存。完成后告诉我处理了哪些资料、产生多少数据，以及数据存在哪里。不需要计算额外财务指标，不需要作图。';
  report.run_ids=[];
  report.session_markers=conversations.map((_,i)=>'会话批次-'+project.id.slice(0,8)+'-'+(i+1));
  for(const [i,chat] of conversations.entries()){const started=await post(`/api/conversations/${chat.id}/messages`,{content:prompt+' 本会话批次代号：'+report.session_markers[i]+'。',documentIds:report.documents.filter(d=>d.conversation_id===chat.id).map(d=>d.id)});report.run_ids.push(started.runId);await save();}
  const states=await Promise.all(report.run_ids.map(id=>request('/api/runs/'+id)));
  check('同项目两个会话同时独立运行',states.every(x=>['running','queued'].includes(x.status))&&new Set(states.map(x=>x.conversationId)).size===2,{runs:states.map(x=>({id:x.id,status:x.status,conversationId:x.conversationId}))});
  await save();
 }
 const runs=await waitRuns(report.run_ids);check('两个 Pi 清洗运行完成',runs.every(r=>r.status==='completed'),runs.map(r=>({id:r.id,status:r.status,error:r.error,usage:r.usage})));
 const [actual,catalog,documents]=await Promise.all([facts(),request(`/api/projects/${report.project_id}/catalog`),request(`/api/projects/${report.project_id}/documents`)]);
 report.fact_count=actual.length;report.catalog=catalog;report.final_documents=documents.documents;
 check('共享项目看板能读取两个会话处理的数据',report.documents.every(d=>actual.some(f=>(f.document_id||f.source_ref?.document_id)===d.id)),{document_ids_with_facts:[...new Set(actual.map(f=>f.document_id||f.source_ref?.document_id))]});
 check('目录返回真实 SQLite 和索引位置',typeof catalog.database_path==='string'&&catalog.database_path.endsWith('finance.sqlite')&&Object.keys(catalog).some(k=>k.includes('index')),{database_path:catalog.database_path,catalog_fields:Object.keys(catalog)});
 report.audit=[];for(const run of runs)report.audit.push(await auditSummary(run));
 check('LangExtract 模型请求经所属 Pi 会话运行并计入调用记录',report.audit.every(a=>a.persistent_session&&a.tool_names.includes('process_documents')&&a.extraction_requests.length>0&&a.extraction_results.length>0&&a.extraction_requests.every(x=>x.owner_run_id===a.run_id&&x.runtime==='Pi.ModelRuntime')),report.audit);
 check('项目指标目录经过真实 Pi 模型审校并覆盖所有事实',catalog.catalog_review?.status==='reviewed'&&catalog.catalog_review?.reviewed_fact_count===actual.length&&catalog.catalog_review?.pending_fact_count===0&&report.audit.some(a=>a.valid_owners&&a.extraction_classes.includes('catalog_review'))&&actual.every(f=>f.canonical_alias?.status==='reviewed'&&f.canonical_alias?.engine==='LangExtract'),{catalog_review:catalog.catalog_review,audited_classes:report.audit.map(a=>({run_id:a.run_id,classes:a.extraction_classes}))});
 const temporalCache=await verifyTemporalCacheEvidence(report.project_id,catalog.temporal_review).catch(error=>({status:'failed',error:String(error.message).replace(/sk-[A-Za-z0-9_-]+/g,'[REDACTED]')}));
 report.temporal={...temporalAcceptance(catalog.temporal_review,actual,[...report.audit,...(temporalCache.audits||[])]),cache_evidence:temporalCache};
 check('期间审校覆盖项目事实且修订可追溯真实Pi输出',report.temporal.status==='passed'&&temporalCache.status==='passed',report.temporal);
 // Gold is read on the host only now, after all model processing is finished.
 const scoringSuite=report.version==='v0.3-normalization'?path.join(root,'benchmark/versions/v0.3-normalization'):suite;
 const goldText=await fs.readFile(path.join(scoringSuite,'gold.jsonl'),'utf8'),forbiddenText=await fs.readFile(path.join(scoringSuite,'forbidden.json'),'utf8');
 report.gold_sha256=createHash('sha256').update(goldText).digest('hex');
 report.forbidden_sha256=createHash('sha256').update(forbiddenText).digest('hex');
 const gold=goldText.trim().split('\n').map(x=>JSON.parse(x)),forbidden=JSON.parse(forbiddenText);
 report.normalization=scoreNormalization(gold,forbidden,actual,report.documents);
 check('语义清洗独立金标准',report.normalization.failed_facts===0&&report.normalization.failed_forbidden_checks===0,{expected:report.normalization.expected_facts,passed:report.normalization.passed_facts,failed:report.normalization.failed_facts,forbidden_failed:report.normalization.failed_forbidden_checks});
 report.conversations=await Promise.all(report.conversation_ids.map(id=>request('/api/conversations/'+id)));
 check('清洗完成回答能说明数据存储位置',report.conversations.every(c=>c.messages.some(m=>m.role==='assistant'&&/finance\.sqlite/.test(m.content))),{conversation_ids:report.conversation_ids});
 if(report.session_markers?.length&&(runs.every(r=>r.status==='completed')||report.followup_run_id)){
  if(!report.followup_run_id){
   const followup=await post(`/api/conversations/${report.conversation_ids[0]}/messages`,{content:'刚才本会话的批次代号是什么？请保留原文回答。再查项目数据目录，告诉我其他会话上传的资料现在是否也能查询，并给出数据库位置。',documentIds:[]});
   report.followup_run_id=followup.runId;await save();
  }
  const [followup]=await waitRuns([report.followup_run_id]);report.followup_run=followup;report.runs=runs;
  const persisted=await readPersistedRunAnswer(()=>request('/api/conversations/'+report.conversation_ids[0]),followup.id);
  const answer=persisted.answer;report.followup_persistence_observation={attempts:persisted.attempts,waited_ms:persisted.waited_ms};
  const marker=report.session_markers[0],otherMarker=report.session_markers[1];
  check('同一 Pi 会话下一轮保留自己的上下文并查询共享目录',followup.status==='completed'&&answer?.content.includes(marker)&&!answer?.content.includes(otherMarker)&&followup.tools.some(t=>t.name==='get_data_catalog'),{run_id:followup.id,status:followup.status,expected_session_marker:marker,answer:answer?.content});
 }else if(report.session_markers?.length){
  report.checks.push({name:'同一 Pi 会话下一轮保留自己的上下文并查询共享目录',status:'skipped',evidence:{reason:'A prerequisite Pi run did not complete; no dependent model request was made.',failed_run_ids:runs.filter(r=>r.status!=='completed').map(r=>r.id)}});
  console.log('SKIP dependent conversation continuation after an incomplete primary run');
 }
 // Disk session evidence verifies history preservation without restarting the user's service.
 const sessionEvidence=[];
 for(const id of report.conversation_ids){const p=path.join(root,'data/workspaces',report.project_id,id,'sessions/session.jsonl');const text=await fs.readFile(p,'utf8');sessionEvidence.push({conversation_id:id,bytes:Buffer.byteLength(text),contains_processing_tool:text.includes('process_documents')});}
 check('两段独立 Pi 会话各自持久保存工具上下文',sessionEvidence.every(x=>x.bytes>0&&x.contains_processing_tool),sessionEvidence);
 report.status=report.checks.some(x=>x.status==='failed')?'failed':'passed';report.finished_at=now();
}catch(error){report.status='failed';report.error=String(error.message||error).replace(/sk-[A-Za-z0-9_-]+/g,'[REDACTED]');console.error('FAIL',report.error);}
finally{
 report.implementation_sha256_after=await implementationHashes();
 if(report.implementation_sha256_before){
  report.implementation_changed_during_run=JSON.stringify(report.implementation_sha256_before)!==JSON.stringify(report.implementation_sha256_after);
  check('验收期间实现保持固定',!report.implementation_changed_during_run,{before:report.implementation_sha256_before,after:report.implementation_sha256_after});
  if(report.implementation_changed_during_run)report.status='failed';
 }
 await save();console.log('REPORT',output);if(report.status!=='passed')process.exitCode=1;
}
