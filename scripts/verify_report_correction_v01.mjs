// One first-run Pi correction challenge; gold remains on the host.
import fs from 'node:fs/promises';
import path from 'node:path';
import {createHash} from 'node:crypto';
import {fileURLToPath} from 'node:url';
import {setTimeout as delay} from 'node:timers/promises';
import {scoreReportCorrection} from './score_report_correction_v01.mjs';
import {summarizeBudget} from './validation_budget_v05.mjs';
const root=path.resolve(import.meta.dirname,'..'),suite=path.join(root,'benchmark/versions/v0.1-report-correction');
const sha=x=>createHash('sha256').update(x).digest('hex'),terminal=r=>['completed','failed','cancelled'].includes(r?.status),redact=e=>String(e?.message??e).replace(/sk-[A-Za-z0-9_-]+/g,'[REDACTED]');
const helpers=['scripts/verify_report_correction_v01.mjs','scripts/score_report_correction_v01.mjs','scripts/validation_budget_v05.mjs'];
async function snapshot(){
 const files=['package-lock.json','requirements.lock.txt','service/requirements.txt',...helpers];
 for(const directory of ['server','service','web/src'])for(const name of await fs.readdir(path.join(root,directory),{recursive:true})){
  const s=name.replaceAll('\\','/');if(/(^|\/)(?:tests?|runs|staged[^/]*|__pycache__)(?:\/|_)/.test(s)||/(^|\/)test_/.test(s))continue;
  if((directory==='web/src'||/\.(?:ts|py|mjs|json|txt|yaml)$/.test(s))&&(await fs.stat(path.join(root,directory,name))).isFile())files.push(directory+'/'+s);
 }
 for(const name of await fs.readdir(suite,{recursive:true}))if((await fs.stat(path.join(suite,name))).isFile())files.push(path.relative(root,path.join(suite,name)).replaceAll('\\','/'));
 const hashes={};for(const f of files.sort())hashes[f]=sha(await fs.readFile(path.join(root,f)));return hashes;
}
async function events(id){try{const raw=await fs.readFile(path.join(root,'data/audit',id+'.jsonl'),'utf8'),lines=raw.split('\n');if(!raw.endsWith('\n'))lines.pop();return lines.filter(Boolean).map(JSON.parse);}catch(e){if(e.code==='ENOENT')return [];throw e;}}
const config=s=>({llm:{baseUrl:s.llm?.baseUrl,model:s.llm?.model,contextWindow:s.llm?.contextWindow,maxTokens:s.llm?.maxTokens},runtime:s.runtime});
export async function runReportCorrection(argv=process.argv.slice(2),testHarness={}){
 const arg=(name,fallback)=>argv.includes(name)?argv[argv.indexOf(name)+1]:fallback;
 const base=arg('--base-url','http://127.0.0.1:3001').replace(/\/$/,''),output=path.resolve(arg('--output','benchmark/results/pi-report-correction-v01-'+Date.now()+'.json'));
 const lock=testHarness.lockPath??path.join(root,'benchmark/results/report-correction-v01-first-run.lock.json');
 try{return {already_started:true,...JSON.parse(await fs.readFile(lock,'utf8'))};}catch(e){if(e.code!=='ENOENT')throw e;}
 const report={version:'report-correction-0.1',kind:testHarness.lockPath?'isolated_mock_runner_test':'task_level_held_out_planted_report_errors',status:'running',started_at:new Date().toISOString(),checks:[],gold_sent_to_agent:false,snapshots:[],cancellations:[]};
 let owned=false,started=Date.now(),budget,audit=[];
 const request=async(route,options={})=>{const r=await fetch(base+route,{...options,signal:AbortSignal.timeout(90000)});if(!r.ok)throw Error('HTTP '+r.status+' '+route);return r.json();};
 const post=(route,data)=>request(route,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)});
 const save=async()=>{if(owned){report.updated_at=new Date().toISOString();await fs.writeFile(output,JSON.stringify(report,null,2),'utf8');}};
 const check=(name,passed,evidence)=>report.checks.push({name,status:passed?'passed':'failed',evidence});
 async function observe(){report.run=await request('/api/runs/'+report.run_id);audit=await(testHarness.auditReader??events)(report.run_id);report.budget=summarizeBudget([report.run],{[report.run_id]:audit},(Date.now()-started)/1000,budget);}
 async function cancel(reason){if(report.run_id&&!terminal(report.run)&&!report.cancellations.length){const record={run_id:report.run_id,at:new Date().toISOString(),initiator:'benchmark_runner',reason};report.cancellations.push(record);try{await post('/api/runs/'+report.run_id+'/cancel',{});record.accepted=true;}catch(e){record.error=redact(e);}}}
 try{
  const manifest=JSON.parse(await fs.readFile(path.join(suite,'manifest.json'),'utf8'));report.sampling=manifest.sampling;
  for(const [file,hash] of Object.entries(manifest.files))if(sha(await fs.readFile(path.join(suite,file)))!==hash)throw Error('Frozen fixture changed: '+file);
  report.snapshot_before=await snapshot();budget=JSON.parse(await fs.readFile(path.join(suite,'BUDGET.json'),'utf8'));report.budget_policy=budget;
  const settings=await request('/api/settings');if(!settings.llm?.hasKey||new URL(settings.llm.baseUrl).hostname!=='api.deepseek.com')throw Error('Official DeepSeek must already be configured');report.configuration_before=config(settings);
  const jobId=arg('--job-id',null);report.evaluation={profile:'financial',budget_group_id:'correction-v01-'+(jobId||Date.now()),budget:Object.fromEntries(['max_model_calls','max_input_tokens','max_output_tokens','max_total_tokens','max_wall_seconds'].map(k=>[k,budget[k]]))};
  if(argv.includes('--prepare-only'))return {prepared:true,version:report.version,snapshot:report.snapshot_before,evaluation:report.evaluation};
  await fs.mkdir(path.dirname(lock),{recursive:true});await fs.mkdir(path.dirname(output),{recursive:true});
  await fs.writeFile(lock,JSON.stringify({job_id:jobId,runner_pid:process.pid,output,started_at:report.started_at,snapshot:report.snapshot_before,evaluation:report.evaluation}),{flag:'wx'});owned=true;
  await fs.writeFile(output,JSON.stringify(report,null,2),{flag:'wx'});
  const project=await post('/api/projects',{name:'研报纠错独立任务 v0.1'});report.project_id=project.id;
  const chat=await post('/api/projects/'+project.id+'/conversations',{});report.conversation_id=chat.id;
  const sourceMap=JSON.parse(await fs.readFile(path.join(suite,'source-map.json'),'utf8')),form=new FormData();form.append('files',new Blob([await fs.readFile(path.join(suite,'inputs',sourceMap.input_file))]),sourceMap.input_file);
  const upload=await request('/api/projects/'+project.id+'/uploads',{method:'POST',body:form});report.document_id=upload.documents[0].id;report.source_mapping=sourceMap;
  const task=await fs.readFile(path.join(suite,'TASK.txt'),'utf8'),original=await fs.readFile(path.join(suite,'REPORT.txt'),'utf8');started=Date.now();
  const run=await post('/api/conversations/'+chat.id+'/messages',{content:task+original,documentIds:[report.document_id],evaluation:report.evaluation});report.run_id=run.runId;await save();
  let last=0,cancelAt=null;
  while(true){await observe();if(terminal(report.run))break;if(report.budget.cap_reached&&!cancelAt){cancelAt=Date.now();await cancel('pre-registered evaluation budget reached');}if(cancelAt&&Date.now()-cancelAt>90000)throw Error('Cancellation did not become terminal within 90 seconds');if(Date.now()-last>15000){last=Date.now();report.snapshots.push({at:new Date().toISOString(),status:report.run.status,stage:report.run.stage,budget:report.budget.actual});await save();console.log('RUNNING',report.run.status,report.budget.actual.model_calls);}await delay(budget.poll_interval_ms);}
  check('真实Pi会话完成',report.run.status==='completed',{id:report.run_id,status:report.run.status,error:report.run.error});
  check('预算与用量可核对',report.budget.accounting_valid&&!report.budget.exceeded.length,report.budget);
  const applied=report.run.evaluation??audit.find(e=>e.type==='run_config')?.data?.evaluation;
  check('运行级共享预算配置生效',applied?.profile==='financial'&&applied?.budget_group_id===report.evaluation.budget_group_id,applied);
  const conversation=await request('/api/conversations/'+chat.id),answer=conversation.messages.filter(m=>m.role==='assistant'&&m.runId===report.run_id).at(-1);
  check('最终回答持久保存',Boolean(answer?.content?.trim()),{message_id:answer?.id});
  const candidates=[];
  for(const a of answer?.artifacts||[]){if(!a.url?.startsWith('/api/projects/'+project.id+'/research/artifacts/'))continue;const saved=await request(a.url);if(saved.kind==='report_correction'&&saved.run_id===report.run_id)candidates.push({url:a.url,sha256:sha(JSON.stringify(saved)),artifact:saved});}
  report.artifact_candidates=candidates;report.selected_artifact=candidates.at(-1);
  const tools=audit.filter(e=>e.type==='tool_request').map(e=>e.data.name);
  check('通过真实保存工具交付纠错成果',tools.includes('save_research_report')&&candidates.length>0,{used_tools:tools,candidate_count:candidates.length});
  // Gold is first parsed after the model run is terminal, never added to task.
  const gold=JSON.parse(await fs.readFile(path.join(suite,'gold.json'),'utf8')),sourcePages={};for(const p of sourceMap.page_mapping)sourcePages[p.input_page]=await fs.readFile(path.join(suite,'evidence/original-page-'+p.original_page+'.txt'),'utf8');
  report.correction=scoreReportCorrection(gold,original,report.selected_artifact?.artifact??{}, {documentId:report.document_id,sourcePages});report.score=report.correction.score;report.normalization=report.correction.normalization;
  check('纠错precision至少95%且recall至少90%',report.correction.acceptance.correction_gate,report.score);
  check('正确陈述与合理观点保持原文',report.correction.acceptance.protection_gate,report.correction.protected_claims);
  check('原文定位及替换成果可独立重放',report.correction.acceptance.output_integrity_gate,report.correction.errors);
 }catch(e){report.error=redact(e);if(owned&&report.run_id){try{await observe();}catch(e){report.final_observation_error=redact(e);}await cancel('benchmark runner exception: '+report.error);}}
 finally{if(owned){report.snapshot_after=await snapshot();check('运行前后实现输入答案评分器冻结',JSON.stringify(report.snapshot_before)===JSON.stringify(report.snapshot_after),{changed:Object.keys(report.snapshot_before).filter(k=>report.snapshot_before[k]!==report.snapshot_after[k])});try{report.configuration_after=config(await request('/api/settings'));check('模型配置冻结',JSON.stringify(report.configuration_before)===JSON.stringify(report.configuration_after),report.configuration_after);}catch(e){check('模型配置冻结',false,{error:redact(e)});}report.finished_at=new Date().toISOString();report.status=!report.error&&report.checks.every(c=>c.status==='passed')?'passed':'failed';await save();console.log('REPORT',output);}}
 return report;
}
if(process.argv[1]&&path.resolve(process.argv[1])===fileURLToPath(import.meta.url)){
 if(process.argv.includes('--help'))console.log('node scripts/verify_report_correction_v01.mjs --base-url http://127.0.0.1:3001 --output ABS.json --job-id ID [--prepare-only]. A first-run lock prevents repeat model calls.');
 else{const r=await runReportCorrection();if(r.status==='failed')process.exitCode=1;}
}
