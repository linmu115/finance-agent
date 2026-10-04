/** One old-development Pi turn; --start is explicit, --resume only observes. */
import fs from 'node:fs/promises';
import path from 'node:path';
import {execFile} from 'node:child_process';
import {promisify} from 'node:util';
import {setTimeout as delay} from 'node:timers/promises';
import {digest,stableJson,extractionEvidence,readPersistedRunAnswer} from './validation_utils.mjs';
import {compareFinancialSnapshots} from './compare_financial_snapshots.mjs';

const execute=promisify(execFile),root=path.resolve(import.meta.dirname,'..'),args=process.argv.slice(2);
const arg=(key,fallback)=>args.includes(key)?args[args.indexOf(key)+1]:fallback;
if(!args.includes('--start')&&!args.includes('--resume'))throw Error('Provide --start only after host READY, or --resume REPORT to observe an existing run.');
if(args.includes('--start')&&args.includes('--resume'))throw Error('Choose start or resume, never both.');
const base=arg('--base-url','http://127.0.0.1:3001').replace(/\/$/,'');
const stamp=new Date().toISOString().replace(/[:.]/g,'-');
const output=path.resolve(arg('--resume',arg('--output','benchmark/results/pi-known-definition-existing-only-'+stamp+'.json')));
const prefix=output.replace(/\.json$/,''),now=()=>new Date().toISOString();
const request=async(route,body)=>{const response=await fetch(base+route,{...(body?{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)}:{}),signal:AbortSignal.timeout(90000)});if(!response.ok)throw Error('HTTP '+response.status+' '+route);return response.json();};
const save=async()=>{report.updated_at=now();await fs.writeFile(output,JSON.stringify(report,null,2));};
const check=(name,passed,evidence)=>{report.checks.push({name,status:passed?'passed':'failed',evidence});console.log(passed?'PASS':'FAIL',name);};
const terminal=new Set(['completed','failed','cancelled']);
let report={kind:'known_development_definition_repair',status:'preparing',started_at:now(),checks:[],snapshots:[],gold_sent_to_agent:false,
 scope:'Only previously known Moutai definition defects. No new holdout. Historical 2/15 source-definition anchors and 0/9 distinctions remain unchanged.'};
const artifacts={before:prefix+'-before.json',after:prefix+'-after.json',source_before:prefix+'-source-before.json',source_after:prefix+'-source-after.json',scoring:prefix+'-known-score.json'};
const frozenFiles=['benchmark/results/known-disclosure-scope-assertions.json','benchmark/results/pi-full-report-v03-known-definitions-result.json','scripts/verify_known_definitions.mjs','scripts/definition_evidence.mjs','scripts/export_definition_evidence.py','scripts/compare_financial_snapshots.mjs'];
const hashes=async()=>Object.fromEntries(await Promise.all(frozenFiles.map(async name=>[name,digest(await fs.readFile(path.join(root,name)))])));
const implementationFiles=['server/runs.ts','server/model-bridge.ts','server/main.ts','server/evaluation-budget.ts','service/server.py','service/processing.py','service/existing_review.py','service/review_cache.py','service/definition_model.py','service/definition_semantics.py','service/temporal_semantics.py'];
const implementation=async()=>Object.fromEntries(await Promise.all(implementationFiles.map(async name=>[name,digest(await fs.readFile(path.join(root,name)))])));
async function snapshot(filename){
 const catalog=await request('/api/projects/'+report.project_id+'/catalog');
 if((catalog.processing||[]).some(p=>!['ready','completed','needs_review','failed','cancelled'].includes(p.state)))throw Error('Project document processing is active; no stable snapshot available.');
 const facts=[];for(let offset=0;;){const page=await request('/api/projects/'+report.project_id+'/financial-data?limit=200&offset='+offset);facts.push(...page.items);offset+=page.items.length;if(offset===page.total)break;if(!page.items.length||offset>page.total)throw Error('Incomplete snapshot pagination');}
 const value={project_id:report.project_id,captured_at:now(),source:'public_http_read_only',model_calls:0,fact_count:facts.length,facts_sha256:digest(facts),catalog,facts};
 await fs.writeFile(filename,JSON.stringify(value,null,2),{flag:'wx'});return value;
}
async function sourceSnapshot(filename){await execute(path.join(root,'.venv/Scripts/python.exe'),[path.join(root,'scripts/export_review_source_snapshot.py'),'--project',report.project_id,'--output',filename],{cwd:root,env:{...process.env,PYTHONIOENCODING:'utf-8'},maxBuffer:1024*1024});return JSON.parse(await fs.readFile(filename,'utf8'));}
async function audit(){return (await fs.readFile(path.join(root,'data/audit',report.run_id+'.jsonl'),'utf8')).trim().split('\n').filter(Boolean).map(JSON.parse);}
try{
 if(args.includes('--resume'))report=JSON.parse(await fs.readFile(output,'utf8'));
 else{
  const oldPath=path.join(root,'benchmark/results/pi-full-report-v03.json'),oldBytes=await fs.readFile(oldPath),old=JSON.parse(oldBytes);
  Object.assign(report,{project_id:old.project_id,conversation_id:old.conversation_id,document_id:old.document_id,artifacts,prior_report:{path:oldPath,sha256:digest(oldBytes)},prior_score:{anchors:{passed:2,total:15},distinctions:{passed:0,total:9}},frozen_before:await hashes(),implementation_before:await implementation()});
  await fs.mkdir(path.dirname(output),{recursive:true});await fs.writeFile(output+'.lock.json',JSON.stringify({started_at:report.started_at,output,conversation_id:report.conversation_id}),{flag:'wx'});
  const chat=await request('/api/conversations/'+report.conversation_id);
  if(chat.projectId!==report.project_id)throw Error('Original conversation project mismatch');
  if(chat.activeRunId){const active=await request('/api/runs/'+chat.activeRunId);if(!terminal.has(active.status))throw Error('Original conversation is active');}
  const settings=await request('/api/settings');if(!settings.llm?.hasKey||new URL(settings.llm.baseUrl).hostname!=='api.deepseek.com')throw Error('Configured official DeepSeek required');
  report.model={model:settings.llm.model,base_url:settings.llm.baseUrl,max_tokens:settings.llm.maxTokens};
  const before=await snapshot(artifacts.before),sources=await sourceSnapshot(artifacts.source_before);report.before={fact_count:before.fact_count,facts_sha256:before.facts_sha256,source_sha256:sources.tables_sha256};
  report.evaluation={profile:'financial',budget_group_id:'known-definitions-'+Date.now(),budget:{max_model_calls:40,max_input_tokens:4000000,max_output_tokens:600000,max_total_tokens:4600000,max_wall_seconds:1200}};
  report.status='starting';await save();
  const started=await request('/api/conversations/'+report.conversation_id+'/messages',{content:'仅复核项目中既有财报来源的指标定义。这次不是继续整份文档清洗。请调用一次 process_documents，document_ids为['+JSON.stringify(report.document_id)+']，review_existing_only=true，force=false，review_metrics=["revenue","lease_liabilities","non_recurring_government_grants"]。基于原表标题、定义和包含/排除范围逐来源判断，允许保留、拆分或归并，保留真实引用；不要根据金额相同判断定义相同。不得调用全量重新处理，不要重新解析、入库其他附件、复核期间、计算衍生指标或制图。该模式如报缺来源则说明具体问题并停止，不切换到普通处理。完成后只简述真实复核结果及未决项，不写长报告。',documentIds:[],evaluation:report.evaluation});
  report.run_id=started.runId;report.status='running';await save();
 }
 const until=Date.now()+1300*1000;let lastLog=0;
 while(true){
  report.run=await request('/api/runs/'+report.run_id);
  if(terminal.has(report.run.status))break;
  const events=await audit().catch(()=>[]),wrong=events.find(e=>e.type==='processing_started'&&e.data.mode!=='existing_source_definition_review');
  if(wrong){await request('/api/runs/'+report.run_id+'/cancel',{});report.wrong_mode=wrong;throw Error('Model attempted ordinary ingestion; cancelled to preserve historical sources.');}
  if(Date.now()>until)throw Error('Observation timed out; use --resume to observe this run, never start another.');
  if(Date.now()-lastLog>15000){lastLog=Date.now();report.snapshots.push({at:now(),status:report.run.status,stage:report.run.stage,usage:report.run.usage,evaluation:report.run.evaluation});await save();console.log('RUN',report.run.status,report.run.stage,JSON.stringify(report.run.usage));}
  await delay(1500);
 }
 const before=JSON.parse(await fs.readFile(report.artifacts.before,'utf8')),sourcesBefore=JSON.parse(await fs.readFile(report.artifacts.source_before,'utf8'));
 const after=await snapshot(report.artifacts.after),sourcesAfter=await sourceSnapshot(report.artifacts.source_after);
 const events=await audit(),starts=events.filter(e=>e.type==='processing_started'),proof=extractionEvidence(events,report.run_id);delete proof.signatures;
 report.extraction_evidence=proof;
 check('one_existing_only_processing_call',starts.length===1&&starts[0].data.mode==='existing_source_definition_review',starts);
 check('owning_pi_completed',report.run.status==='completed',{status:report.run.status,error:report.run.error});
 check('only_definition_inference',proof.valid_owners&&proof.successful_results>0&&proof.extraction_classes.every(c=>['definition_decision','definition_unresolved'].includes(c)),proof);
 check('source_index_and_original_mapping_unchanged',sourcesBefore.tables_sha256===sourcesAfter.tables_sha256,{before:sourcesBefore.tables_sha256,after:sourcesAfter.tables_sha256});
 report.conservation=compareFinancialSnapshots(before.facts,after.facts);
 check('all_values_dates_units_and_sources_conserved',report.conservation.status==='passed'&&report.conservation.period_changes.length===0,report.conservation);
 const identity=f=>({fact_id:f.fact_id,document_id:f.document_id,source_key:f.source_ref?.normalization?.source_key,source_fingerprint:f.source_ref?.normalization?.source_fingerprint,original_extraction_hash:f.source_ref?.normalization?.original_extraction_hash,bbox:f.source_ref?.bbox,period_start:f.period_start,period_end:f.period_end,statement:f.statement});
 const identities=rows=>rows.map(identity).sort((a,b)=>a.fact_id.localeCompare(b.fact_id));
 check('fact_identity_geometry_and_origin_conserved',stableJson(identities(before.facts))===stableJson(identities(after.facts)),{before_count:before.facts.length,after_count:after.facts.length});
 try{await execute(process.execPath,[path.join(root,'scripts/verify_known_definitions.mjs'),'--before',report.artifacts.before,'--after',report.artifacts.after,'--output',report.artifacts.scoring],{cwd:root,maxBuffer:2*1024*1024});}catch(error){if(!await fs.stat(report.artifacts.scoring).catch(()=>false))throw error;}
 report.scoring=JSON.parse(await fs.readFile(report.artifacts.scoring,'utf8'));
 const anchors=report.scoring.checks,pairs=report.scoring.relations.flatMap(r=>r.checks);
 report.score={anchors:{passed:anchors.filter(c=>c.status==='passed').length,total:anchors.length},distinctions:{passed:pairs.filter(c=>c.passed).length,total:pairs.length}};
 check('known_15_source_definition_anchors',anchors.every(c=>c.status==='passed'),report.score.anchors);
 check('known_9_definition_distinctions',pairs.every(c=>c.passed),report.score.distinctions);
 check('real_model_ownership_quotes_and_archived_before_values',report.scoring.provenance.status==='passed',report.scoring.provenance);
 const processing=after.catalog.processing.filter(p=>p.owner_run_id===report.run_id);report.processing=processing;
 check('definition_stage_complete_without_hidden_errors',processing.length===1&&processing.every(p=>p.state==='completed'&&!p.errors?.length&&p.definition_review?.status==='reviewed'),processing);
 const answer=await readPersistedRunAnswer(()=>request('/api/conversations/'+report.conversation_id),report.run_id);
 check('final_answer_persisted',!!answer.answer?.content?.trim(),{message_id:answer.answer?.id});
 report.frozen_after=await hashes();report.implementation_after=await implementation();
 check('historical_gold_and_scorers_unchanged',stableJson(report.frozen_before)===stableJson(report.frozen_after),report.frozen_after);
 report.implementation_changes=Object.keys(report.implementation_after).filter(key=>report.implementation_before[key]!==report.implementation_after[key]);
 report.status=report.checks.every(c=>c.status==='passed')?'passed':'failed';
}catch(error){report.status='failed';report.error=String(error.message).replace(/sk-[A-Za-z0-9_-]+/g,'[REDACTED]');console.error('FAIL',report.error);}
finally{report.finished_at=now();await save();console.log('REPORT',output);if(report.status!=='passed')process.exitCode=1;}
