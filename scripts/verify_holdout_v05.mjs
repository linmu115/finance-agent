// One frozen complete-table arm, driven through the normal public chat API.
// Neither gold nor its table boundaries enter a model request.
import fs from 'node:fs/promises';
import path from 'node:path';
import {setTimeout as delay} from 'node:timers/promises';
import {fileURLToPath} from 'node:url';
import {createHash} from 'node:crypto';
import {scoreFinancialTables,signature,exactDecimal} from './score_financial_tables_v05.mjs';
import {summarizeBudget} from './validation_budget_v05.mjs';
import {verifyReviewsV05} from './review_evidence_v05.mjs';
import {extractionEvidence,readPersistedRunAnswer} from './validation_utils.mjs';
const root=path.resolve(import.meta.dirname,'..'),suite=path.join(root,'benchmark/versions/v0.5-holdout');
const hash=value=>createHash('sha256').update(value).digest('hex'),stable=value=>JSON.stringify(value);
const redact=e=>String(e?.message??e).replace(/sk-[A-Za-z0-9_-]+/g,'[REDACTED]');
const terminal=r=>['completed','failed','cancelled'].includes(r.status);
export function compareExportedFacts(database,exported){
 const normalize=f=>{const meta=f.source_ref?.normalization||{},value={};for(const key of ['company','metric','label','raw_value','raw_unit','currency','normalized_unit','unit_kind','period','period_start','period_end','scope','version','dimensions','definition','definition_scope'])value[key]=(f[key]??meta[key])??null;value.value=exactDecimal(f.value);value.source={document_id:f.source_ref?.document_id,page:f.source_ref?.page,bbox:f.source_ref?.bbox};return value;};
 const counts=items=>{const m=new Map();for(const f of items){const key=signature(normalize(f));m.set(key,(m.get(key)||0)+1);}return m;};
 const wanted=counts(database),actual=counts(exported);let missing=0,unexpected=0;
 for(const [k,n] of wanted)missing+=Math.max(0,n-(actual.get(k)||0));for(const [k,n] of actual)unexpected+=Math.max(0,n-(wanted.get(k)||0));
 return {status:missing||unexpected?'failed':'passed',database_facts:database.length,exported_facts:exported.length,missing_or_changed:missing,unexpected_or_changed:unexpected};
}
const helpers=['scripts/verify_holdout_v05.mjs','scripts/score_financial_tables_v05.mjs','scripts/validation_budget_v05.mjs','scripts/review_evidence_v05.mjs','scripts/export_review_evidence_v05.py','scripts/definition_evidence_v2.mjs','scripts/export_definition_evidence_v2.py','scripts/validation_utils.mjs','scripts/score_normalization.mjs'];
async function hashes(files){const result={};for(const file of [...files].sort())result[file]=hash(await fs.readFile(path.join(root,file)));return result;}
async function productionHashes(){
 const files=['package-lock.json','requirements.lock.txt','service/requirements.txt'];
 for(const directory of ['server','service','web/src'])for(const name of await fs.readdir(path.join(root,directory),{recursive:true})){
  const normalized=name.replaceAll('\\','/');
  if(/(^|\/)(?:tests?|runs|staged[^/]*|__pycache__)(?:\/|_)/.test(normalized)||/(^|\/)test_/.test(normalized))continue;
  if((directory==='web/src'||/\.(?:ts|py|mjs|json|txt|yaml)$/.test(normalized))&&(await fs.stat(path.join(root,directory,name))).isFile())files.push(directory+'/'+normalized);
 }
 return hashes(files);
}
async function suiteHashes(){return hashes(['manifest.json','gold.json','SCORING.txt','DESIGN.txt','BUDGET.json','TASK.txt','BASELINE_PLAN.json','SCORER_PRE_RUN_CHANGES.json',...(await fs.readdir(path.join(suite,'inputs'))).map(n=>'inputs/'+n)].map(n=>'benchmark/versions/v0.5-holdout/'+n));}
function publicConfiguration(s){return {llm:{baseUrl:s.llm?.baseUrl,model:s.llm?.model,contextWindow:s.llm?.contextWindow,maxTokens:s.llm?.maxTokens,inputPricePerMillionUsd:s.llm?.inputPricePerMillionUsd,outputPricePerMillionUsd:s.llm?.outputPricePerMillionUsd},runtime:s.runtime};}
async function auditEvents(runId){
 try{const raw=await fs.readFile(path.join(root,'data/audit',runId+'.jsonl'),'utf8'),lines=raw.split('\n');if(!raw.endsWith('\n'))lines.pop();return lines.filter(Boolean).map(JSON.parse);}catch(e){if(e.code==='ENOENT')return [];throw e;}
}
export async function runHoldoutV05(argv=process.argv.slice(2),testHarness={}){
 const arg=(key,fallback)=>argv.includes(key)?argv[argv.indexOf(key)+1]:fallback;
 const arm=arg('--profile','financial');if(!['financial','generic'].includes(arm))throw Error('profile must be financial or generic');
 const base=arg('--base-url','http://127.0.0.1:3001').replace(/\/$/,''),output=path.resolve(arg('--output','benchmark/results/pi-holdout-v05-'+arm+'-'+Date.now()+'.json'));
 const lock=testHarness.lockPath??path.join(root,'benchmark/results/holdout-v05-'+arm+'-first-run.lock.json');
 try{const existing=JSON.parse(await fs.readFile(lock,'utf8'));console.log('ALREADY_STARTED',existing.output);return {already_started:true,...existing};}catch(e){if(e.code!=='ENOENT')throw e;}
 const report={version:'v0.5-holdout',kind:testHarness.lockPath?'isolated_mock_runner_test':'company_held_out_complete_tables',profile:arm,status:'running',started_at:new Date().toISOString(),gold_sent_to_agent:false,checks:[],documents:[],runs:[],snapshots:[],cancellations:[]};
 let lockOwned=false,events={},budget,started=Date.now();
 const request=async(route,options={})=>{const response=await fetch(base+route,{...options,signal:AbortSignal.timeout(90000)});if(!response.ok)throw Error('HTTP '+response.status+' '+route);return response.json();};
 const post=(route,value)=>request(route,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(value)});
 const save=async()=>{if(!lockOwned)return;report.updated_at=new Date().toISOString();await fs.mkdir(path.dirname(output),{recursive:true});await fs.writeFile(output,JSON.stringify(report,null,2),'utf8');};
 const check=(name,passed,evidence)=>{report.checks.push({name,status:passed?'passed':'failed',evidence});console.log(passed?'PASS':'FAIL',name);};
 async function cancelActive(reason){
  for(const r of report.runs.filter(r=>!terminal(r))){
   if(report.cancellations.some(c=>c.run_id===r.id))continue;
   const record={run_id:r.id,at:new Date().toISOString(),initiator:'benchmark_runner',reason};report.cancellations.push(record);
   try{await post('/api/runs/'+r.id+'/cancel',{});record.request_accepted=true;}catch(e){record.error=redact(e);}
  }
 }
 async function observe(){
  report.runs=await Promise.all((report.run_ids||[]).map(id=>request('/api/runs/'+id)));
  events=Object.fromEntries(await Promise.all(report.runs.map(async r=>[r.id,await (testHarness.auditReader??auditEvents)(r.id)])));
  report.budget=summarizeBudget(report.runs,events,(Date.now()-started)/1000,budget);
 }
 try{
  const manifest=JSON.parse(await fs.readFile(path.join(suite,'manifest.json'),'utf8'));
  budget=JSON.parse(await fs.readFile(path.join(suite,'BUDGET.json'),'utf8'));report.budget_policy=budget;
  report.implementation_before=await productionHashes();report.suite_before=await suiteHashes();report.scorer_before=await hashes(helpers);
  const key='benchmark/versions/v0.5-holdout/';
  if(report.suite_before[key+'gold.json']!==manifest.gold_sha256||report.suite_before[key+'SCORING.txt']!==manifest.protocol_sha256||manifest.inputs.some(i=>report.suite_before[key+'inputs/'+i.file]!==i.sha256))throw Error('Locked input, gold or protocol hash changed');
  report.source_mapping=manifest.inputs;report.scope=manifest.sampling;report.thresholds=manifest.thresholds;
  const settings=await request('/api/settings');if(!settings.llm?.hasKey||new URL(settings.llm.baseUrl).hostname!=='api.deepseek.com')throw Error('Official DeepSeek must already be configured');
  report.model_configuration_before=publicConfiguration(settings);
  const frozenBudget=Object.fromEntries(['max_model_calls','max_input_tokens','max_output_tokens','max_total_tokens','max_wall_seconds'].map(k=>[k,budget[k]]));
  const jobId=arg('--job-id',null);report.evaluation={profile:arm,budget_group_id:'v05-'+arm+'-'+(jobId||Date.now()),budget:frozenBudget};
  if(argv.includes('--prepare-only'))return {prepared:true,version:report.version,profile:arm,implementation:report.implementation_before,suite:report.suite_before,scorer:report.scorer_before,budget:report.evaluation};
  await fs.mkdir(path.dirname(lock),{recursive:true});
  await fs.writeFile(lock,JSON.stringify({version:report.version,profile:arm,job_id:jobId,runner_pid:process.pid,started_at:report.started_at,output,implementation:report.implementation_before,suite:report.suite_before,scorer:report.scorer_before,evaluation:report.evaluation}),{flag:'wx'});lockOwned=true;
  await fs.writeFile(output,JSON.stringify(report,null,2),{flag:'wx'});
  const project=await post('/api/projects',{name:'整表留出 v0.5 · '+arm});report.project_id=project.id;report.run_ids=[];report.conversation_ids=[];await save();
  for(const input of manifest.inputs){
   const chat=await post('/api/projects/'+project.id+'/conversations',{});report.conversation_ids.push(chat.id);
   const form=new FormData();form.append('files',new Blob([await fs.readFile(path.join(suite,'inputs',input.file))]),input.file);
   const uploaded=await request('/api/projects/'+project.id+'/uploads',{method:'POST',body:form});
   report.documents.push({file:input.file,id:uploaded.documents[0].id,conversation_id:chat.id});await save();
  }
  const before=await request('/api/projects/'+project.id+'/financial-data?limit=200&offset=0');check('附件在会话前只登记',before.total===0,{facts:before.total});
  const task=await fs.readFile(path.join(suite,'TASK.txt'),'utf8');report.task_sha256=hash(task);started=Date.now();
  for(const doc of report.documents){const run=await post('/api/conversations/'+doc.conversation_id+'/messages',{content:task,documentIds:[doc.id],evaluation:report.evaluation});report.run_ids.push(run.runId);await save();}
  let last=0,cancelAt=null;
  while(true){
   await observe();if(report.runs.every(terminal))break;
   if(report.budget.cap_reached&&!cancelAt){cancelAt=Date.now();await cancelActive('pre-registered shared budget cap reached');}
   if(cancelAt&&Date.now()-cancelAt>90000)throw Error('Cancellation did not terminate all runs within 90 seconds; no second run is authorized by this report');
   if(Date.now()-last>15000){last=Date.now();report.snapshots.push({at:new Date().toISOString(),runs:report.runs.map(r=>({id:r.id,status:r.status,stage:r.stage})),budget:report.budget.actual});await save();console.log('RUNNING',arm,report.budget.actual.model_calls,report.runs.map(r=>r.status).join(','));}
   await delay(budget.poll_interval_ms);
  }
  check('两个独立Pi会话完成',report.runs.every(r=>r.status==='completed'),report.runs.map(r=>({id:r.id,status:r.status,error:r.error})));
  check('预算统计可核对且实际消耗未超过上限',report.budget.accounting_valid&&!report.budget.exceeded.length,report.budget);
  report.run_configuration=report.runs.map(r=>({id:r.id,evaluation:r.evaluation,config:events[r.id].filter(e=>e.type==='run_config').map(e=>e.data)}));
  check('所请求对照配置确实生效',report.run_configuration.every(r=>r.evaluation?.profile===arm&&r.evaluation?.budget_group_id===report.evaluation.budget_group_id||r.config.some(c=>c.evaluation?.profile===arm&&c.evaluation?.budget_group_id===report.evaluation.budget_group_id)),report.run_configuration);
  const chats=await Promise.all(report.conversation_ids.map(id=>request('/api/conversations/'+id)));
  const artifacts=[];
  for(const chat of chats){
   const messages=chat.messages.filter(m=>report.run_ids.includes(m.runId)&&m.role==='assistant');
   const candidates=messages.flatMap(m=>m.artifacts||[]).filter(a=>a.name==='facts.json');
   report.artifact_candidates??=[];report.artifact_candidates.push(...candidates.map(a=>({conversation_id:chat.id,...a})));
   // The final artifact of the same run may repair an earlier attempt. Keep
   // all candidates in the report; score only the last published version.
   for(const artifact of candidates.slice(-1)){
    if(!artifact.url.startsWith('/api/projects/'+project.id+'/artifacts/'))throw Error('Artifact does not belong to this project');
    const body=await request(artifact.url);
    if(body.schema_version!=='financial-facts-1'||!Array.isArray(body.facts))throw Error('facts.json does not follow the predeclared output contract');
    artifacts.push({conversation_id:chat.id,url:artifact.url,sha256:hash(JSON.stringify(body)),facts:body.facts});
   }
  }
  report.output_artifacts=artifacts;check('事实产物可下载且结构正确',new Set(artifacts.map(a=>a.conversation_id)).size===report.documents.length,artifacts.map(({facts,...a})=>({...a,fact_count:facts.length})));
  let facts=[];
  if(arm==='financial'){
   for(let offset=0;;){const page=await request('/api/projects/'+project.id+'/financial-data?limit=200&offset='+offset);facts.push(...page.items);offset+=page.items.length;if(offset===page.total)break;if(!page.items.length||offset>page.total)throw Error('Fact pagination incomplete');}
   report.export_consistency=compareExportedFacts(facts,artifacts.flatMap(a=>a.facts));check('交付事实产物与数据库逐格一致',report.export_consistency.status==='passed',report.export_consistency);
   report.catalog=await request('/api/projects/'+project.id+'/catalog');
   report.review_evidence=await verifyReviewsV05(project.id,report.catalog,facts).catch(e=>({error:redact(e),catalog:{status:'failed'},temporal:{status:'failed'}}));
   check('目录或定义审校可追溯真实Pi及不可变结果',report.review_evidence.catalog.status==='passed'&&report.catalog.catalog_review?.status==='reviewed'&&report.catalog.catalog_review?.pending_fact_count===0,report.review_evidence.catalog);
   check('期间审校覆盖完整且缓存签名未被覆盖',report.review_evidence.temporal.status==='passed',report.review_evidence.temporal);
   const extraction=report.runs.map(r=>{const {signatures,...proof}=extractionEvidence(events[r.id],r.id);return {run_id:r.id,...proof};});
   check('主抽取在所属Pi中执行',extraction.every(p=>p.valid_owners&&p.extraction_classes.includes('financial_row')),extraction);
   check('全部已接受抽取逐条对应原会话实际响应',report.review_evidence.normalization?.status==='passed',report.review_evidence.normalization);
  }else{
   facts=artifacts.flatMap(a=>a.facts);
   const database=await request('/api/projects/'+project.id+'/financial-data?limit=200&offset=0');check('通用组没有专用清洗事实输入',database.total===0,{database_fact_count:database.total});
   const prohibited=['process_documents','query_financial_data','get_financial_metrics','get_normalization_details','calculate_financial_metrics'];
   const used=report.runs.flatMap(r=>events[r.id].filter(e=>e.type==='tool_request').map(e=>e.data.name));check('通用组未调用专用金融工作流',!used.some(t=>prohibited.includes(t))&&report.budget.bridge_total.calls===0,{used,bridge_calls:report.budget.bridge_total.calls});
  }
  report.facts=facts;
  // First parse of answer material occurs only after both model sessions ended.
  const gold=JSON.parse(await fs.readFile(path.join(suite,'gold.json'),'utf8'));
  report.financial_score=scoreFinancialTables(gold,facts,report.documents);report.normalization=report.financial_score.normalization;report.score=report.financial_score.score;
  check('整表precision与recall分别达到95%',report.financial_score.acceptance.statistical_gate_passed,{...report.score,company_scores:report.financial_score.company_scores,table_scores:report.financial_score.table_scores});
  check('没有未解决重大金额单位期间范围错误',report.financial_score.major_errors.length===0,{errors:report.financial_score.major_errors});
  const answers=[];for(const run of report.runs)answers.push(await readPersistedRunAnswer(()=>request('/api/conversations/'+run.conversationId),run.id));
  check('最终回答已持久化',answers.every(a=>a.answer?.content.trim()),answers.map(a=>({message_id:a.answer?.id,attempts:a.attempts})));
 }catch(e){report.status='failed';report.error=redact(e);if(lockOwned&&report.run_ids?.length){try{await observe();}catch(observationError){report.final_observation_error=redact(observationError);}await cancelActive('benchmark runner exception: '+report.error);}console.error('FAIL',report.error);}
 finally{
  if(lockOwned){
   report.implementation_after=await productionHashes();report.suite_after=await suiteHashes();report.scorer_after=await hashes(helpers);
   check('运行前后实现答案评分器保持冻结',stable(report.implementation_before)===stable(report.implementation_after)&&stable(report.suite_before)===stable(report.suite_after)&&stable(report.scorer_before)===stable(report.scorer_after),{implementation_changed:stable(report.implementation_before)!==stable(report.implementation_after),suite_changed:stable(report.suite_before)!==stable(report.suite_after),scorer_changed:stable(report.scorer_before)!==stable(report.scorer_after)});
   try{report.model_configuration_after=publicConfiguration(await request('/api/settings'));check('模型配置保持冻结',stable(report.model_configuration_before)===stable(report.model_configuration_after),report.model_configuration_after);}catch(e){check('模型配置保持冻结',false,{error:redact(e)});}
   report.finished_at=new Date().toISOString();report.status=!report.error&&report.checks.every(c=>c.status==='passed')?'passed':'failed';await save();console.log('REPORT',output);
  }
 }
 return report;
}
if(process.argv[1]&&path.resolve(process.argv[1])===fileURLToPath(import.meta.url)){
 if(process.argv.includes('--help'))console.log('node scripts/verify_holdout_v05.mjs --profile financial|generic --base-url http://127.0.0.1:3001 --output ABS.json --job-id ID [--prepare-only]. Uses one immutable first-run lock per arm; no second model run.');
 else {const report=await runHoldoutV05();if(report.status==='failed')process.exitCode=1;}
}
