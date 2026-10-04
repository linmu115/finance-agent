// One untouched-source challenge run, via the same public conversation API.
import fs from 'node:fs/promises';
import path from 'node:path';
import {setTimeout as delay} from 'node:timers/promises';
import {digest,extractionEvidence,readPersistedRunAnswer,temporalAcceptance} from './validation_utils.mjs';
import {verifyTemporalCacheEvidence} from './temporal_evidence.mjs';
import {scoreHoldout} from './score_holdout.mjs';
const root=path.resolve(import.meta.dirname,'..'),suite=path.join(root,'benchmark/versions/v0.4.1-holdout');
const args=process.argv.slice(2),arg=(key,fallback)=>args.includes(key)?args[args.indexOf(key)+1]:fallback;
const base=arg('--base-url','http://127.0.0.1:3001').replace(/\/$/,''),output=path.resolve(arg('--output','benchmark/results/pi-holdout-v04-'+Date.now()+'.json'));
const report={version:'v0.4.1-holdout',kind:'company_held_out_challenge',status:'running',started_at:new Date().toISOString(),gold_sent_to_agent:false,scope:'30 purposively selected cells from two companies absent from historical project benchmarks, source samples and model audits before preparation; not a blind pretraining-free, random, exhaustive or official competition benchmark.',checks:[],documents:[],runs:[],snapshots:[]};
const save=async()=>{report.updated_at=new Date().toISOString();await fs.mkdir(path.dirname(output),{recursive:true});await fs.writeFile(output,JSON.stringify(report,null,2));};
const check=(name,passed,evidence)=>{report.checks.push({name,status:passed?'passed':'failed',evidence});console.log(passed?'PASS':'FAIL',name);};
const request=async(route,options={})=>{const response=await fetch(base+route,{...options,signal:AbortSignal.timeout(90000)});const data=await response.json();if(!response.ok)throw Error('HTTP '+response.status+' '+route);return data;};
const post=(route,data)=>request(route,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)});
async function implementation(){
 const files=['package-lock.json','requirements.lock.txt','service/requirements.txt'];
 for(const dir of ['server','service','web/src'])for(const name of await fs.readdir(path.join(root,dir),{recursive:true})){
  const normalized=name.replaceAll('\\','/');
  if(!/(^|\/)(?:tests?|runs|staged[^/]*|__pycache__)(?:\/|_)/.test(normalized)&&!/(^|\/)test_/.test(normalized)&&(dir==='web/src'||/\.(?:ts|py|mjs)$/.test(normalized))&&(await fs.stat(path.join(root,dir,name))).isFile())files.push(dir+'/'+normalized);
 }
 const hashes={};for(const file of files.sort())hashes[file]=digest(await fs.readFile(path.join(root,file)));
 return hashes;
}
async function suiteHashes(){const files=['manifest.json','gold.jsonl','relations.json',...(await fs.readdir(path.join(suite,'inputs'))).map(name=>'inputs/'+name)];const hashes={};for(const file of files)hashes[file]=digest(await fs.readFile(path.join(suite,file)));return hashes;}
async function scorerHashes(){const hashes={};for(const file of ['scripts/score_holdout.mjs','scripts/score_normalization.mjs','scripts/validation_utils.mjs','scripts/temporal_evidence.mjs','scripts/export_temporal_evidence.py','scripts/verify_holdout.mjs'])hashes[file]=digest(await fs.readFile(path.join(root,file)));return hashes;}
const configuration=s=>({llm:{baseUrl:s.llm.baseUrl,model:s.llm.model,contextWindow:s.llm.contextWindow,maxTokens:s.llm.maxTokens},runtime:{maxToolCalls:s.runtime.maxToolCalls}});
try{
 const manifest=JSON.parse(await fs.readFile(path.join(suite,'manifest.json'),'utf8'));
 const settings=await request('/api/settings');if(!settings.llm?.hasKey||new URL(settings.llm.baseUrl).hostname!=='api.deepseek.com')throw Error('Official DeepSeek must already be configured.');
 report.implementation_before=await implementation();report.suite_before=await suiteHashes();report.model_configuration_before=configuration(settings);
 report.scorer_sha256=digest(await fs.readFile(path.join(root,'scripts/score_holdout.mjs')));report.scorer_hashes_before=await scorerHashes();report.source_mapping=manifest.inputs.map(({file,source,pages})=>({file,source,pages}));
 if(report.suite_before['gold.jsonl']!==manifest.gold_sha256||report.suite_before['relations.json']!==manifest.relations_sha256||manifest.inputs.some(i=>report.suite_before['inputs/'+i.file]!==i.sha256))throw Error('Locked holdout hash mismatch');
 await fs.writeFile(path.join(root,'benchmark/results/holdout-v04-first-run.lock.json'),JSON.stringify({version:'v0.4.1-holdout',job_id:arg('--job-id',null),started_at:report.started_at,output,implementation:report.implementation_before,inputs_gold:report.suite_before}),{flag:'wx'});
 const project=await post('/api/projects',{name:'独立留出验收 v0.4.1'});report.project_id=project.id;await save();
 report.conversation_ids=[];report.run_ids=[];
 for(const input of manifest.inputs){
  const chat=await post('/api/projects/'+project.id+'/conversations',{});report.conversation_ids.push(chat.id);
  const form=new FormData();form.append('files',new Blob([await fs.readFile(path.join(suite,'inputs',input.file))]),input.file);
  const upload=await request('/api/projects/'+project.id+'/uploads',{method:'POST',body:form});
  report.documents.push({file:input.file,id:upload.documents[0].id,conversation_id:chat.id});
 }
 const before=await request('/api/projects/'+project.id+'/financial-data?limit=200&offset=0');check('发送前附件只登记',before.total===0,{facts:before.total});
 for(const doc of report.documents){const run=await post('/api/conversations/'+doc.conversation_id+'/messages',{content:'请处理附件中的财报原文页片，理解并清洗所有可提取财务表格，保留原文金额、币种、期间、版本和披露口径，入库并更新看板。完成后简述处理结果和数据存储位置。',documentIds:[doc.id]});report.run_ids.push(run.runId);await save();}
 const deadline=Date.now()+Number(arg('--timeout-seconds','2400'))*1000;let last=0;
 while(true){
  report.runs=await Promise.all(report.run_ids.map(id=>request('/api/runs/'+id)));
  if(report.runs.every(r=>['completed','failed','cancelled'].includes(r.status)))break;
  if(Date.now()>deadline)throw Error('Observation timeout; existing runs may remain active. Do not start a second holdout run.');
  if(Date.now()-last>15000){last=Date.now();report.snapshots.push({at:new Date().toISOString(),runs:report.runs.map(r=>({id:r.id,status:r.status,stage:r.stage}))});console.log('RUNS',report.runs.map(r=>r.status+': '+r.stage).join(' | '));await save();}
  await delay(1500);
 }
 check('两个真实Pi会话完成',report.runs.every(r=>r.status==='completed'),report.runs.map(r=>({id:r.id,status:r.status,error:r.error,usage:r.usage})));
 const facts=[];for(let offset=0;;){const page=await request('/api/projects/'+project.id+'/financial-data?limit=200&offset='+offset);facts.push(...page.items);offset+=page.items.length;if(offset===page.total)break;if(!page.items.length||offset>page.total)throw Error('Incomplete financial-data pagination');}
 const catalog=await request('/api/projects/'+project.id+'/catalog');report.facts=facts;report.catalog=catalog;report.audit=[];
 for(const run of report.runs){const events=(await fs.readFile(path.join(root,'data/audit',run.id+'.jsonl'),'utf8')).trim().split('\n').map(JSON.parse);const {signatures,...proof}=extractionEvidence(events,run.id);report.audit.push({run_id:run.id,...proof,failed_calls:events.filter(e=>e.type==='extraction_result'&&e.data.stopReason!=='stop').map(e=>({at:e.at,stop_reason:e.data.stopReason,usage:e.data.usage})),processing_attempts:events.filter(e=>e.type==='processing_started').length});}
 check('LangExtract经所属Pi实际调用',report.audit.every(a=>a.valid_owners&&a.successful_results>0&&a.extraction_classes.includes('financial_row')),report.audit);
 check('项目目录覆盖所有事实',catalog.catalog_review?.status==='reviewed'&&catalog.catalog_review?.reviewed_fact_count===facts.length&&catalog.catalog_review?.pending_fact_count===0&&report.audit.some(a=>a.valid_owners&&a.extraction_classes.includes('catalog_review'))&&facts.every(f=>f.canonical_alias?.status==='reviewed'&&f.canonical_alias?.engine==='LangExtract'),catalog.catalog_review);
 const cache=await verifyTemporalCacheEvidence(project.id,catalog.temporal_review).catch(error=>({status:'failed',error:error.message}));
 report.temporal={...temporalAcceptance(catalog.temporal_review,facts,[...report.audit,...(cache.audits||[])]),cache_evidence:cache};
 check('期间审校有完整真实模型证据',report.temporal.status==='passed'&&cache.status==='passed',report.temporal);
 // No answer material is parsed until all Agent runs have terminated.
 const gold=(await fs.readFile(path.join(suite,'gold.jsonl'),'utf8')).trim().split('\n').map(JSON.parse),relations=JSON.parse(await fs.readFile(path.join(suite,'relations.json'),'utf8'));
 report.normalization=scoreHoldout(gold,relations,facts,report.documents);report.score={passed:report.normalization.passed_facts,total:gold.length,failed:report.normalization.failed_facts};
 check('30个独立源格逐项核对',report.normalization.failed_facts===0,{...report.score,failed_ids:report.normalization.checks.filter(c=>c.status==='failed').map(c=>c.id)});
 check('不同财务定义可分别查询',report.normalization.failed_relations===0,report.normalization.relations);
 const answers=[];for(const run of report.runs)answers.push(await readPersistedRunAnswer(()=>request('/api/conversations/'+run.conversationId),run.id));
 check('完成回复已持久化',answers.every(a=>a.answer?.content.trim()),answers.map(a=>({message_id:a.answer?.id,attempts:a.attempts})));
 report.status=report.checks.every(c=>c.status==='passed')?'passed':'failed';
}catch(error){report.status='failed';report.error=String(error.message).replace(/sk-[A-Za-z0-9_-]+/g,'[REDACTED]');console.error('FAIL',report.error);}
finally{
 report.implementation_after=await implementation();report.suite_after=await suiteHashes();
 report.scorer_hashes_after=await scorerHashes();if(report.scorer_hashes_before)check('评分程序保持冻结',stable(report.scorer_hashes_before)===stable(report.scorer_hashes_after),report.scorer_hashes_after);
 if(report.implementation_before)check('实现及输入答案保持冻结',stable(report.implementation_before)===stable(report.implementation_after)&&stable(report.suite_before)===stable(report.suite_after),{implementation_changed:stable(report.implementation_before)!==stable(report.implementation_after),suite_changed:stable(report.suite_before)!==stable(report.suite_after)});
 try{report.model_configuration_after=configuration(await request('/api/settings'));if(report.model_configuration_before)check('模型配置保持冻结',stable(report.model_configuration_before)===stable(report.model_configuration_after),report.model_configuration_after);}catch(error){check('模型配置保持冻结',false,{error:error.message});}
 if(report.checks.some(c=>c.status==='failed'))report.status='failed';report.finished_at=new Date().toISOString();await save();console.log('REPORT',output);if(report.status!=='passed')process.exitCode=1;
}
function stable(value){return JSON.stringify(value);}
