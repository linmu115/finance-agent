// Evaluator only: include every attempt; never turn missing usage into a bill.
import {readFile,writeFile,mkdir} from 'node:fs/promises';
import {createHash} from 'node:crypto';
import path from 'node:path';
const name='pi-finance-generalization-20261006',dir=path.resolve('data/evaluation',name);
const json=async name=>JSON.parse(await readFile(path.join(dir,name),'utf8'));
const optional=async name=>{try{return await json(name);}catch(e){if(e.code==='ENOENT')return null;throw e;}};
const state=await json('experiment.json'),setup=await json('setup.json');
const rows=[];
for(const r of state.runs){
 const events=(await readFile(path.join(dir,r.label+'-audit.jsonl'),'utf8')).trim().split('\n').filter(Boolean).map(JSON.parse);
 const tools={},efforts={};let inputCharacters=0,scriptCharacters=0,scriptRequests=0,sourceRunReuse=0,reportRequests=0;
 for(const e of events){
  if(e.type==='model_request'){const effort=e.data.sentReasoningEffort||e.data.reasoningEffort||'unspecified';efforts[effort]=(efforts[effort]||0)+1;inputCharacters+=e.data.contextCharacters||0;}
  if(e.type==='tool_request'){
   const n=e.data.name;tools[n]=(tools[n]||0)+1;
   const args=e.data.arguments||e.data.args||{};
   if(n==='run_analysis'){scriptCharacters+=(args.code||'').length;scriptRequests+=!!args.code;sourceRunReuse+=!!args.source_run_id;reportRequests+=!!args.report;}
  }
 }
 const delivery=await optional(r.label+'-deliverables.json');
 rows.push({label:r.label,profile:r.profile,status:r.status,runId:r.runId,conversationId:r.conversationId,error:r.error,
  seconds:r.completedAt?(Date.parse(r.completedAt)-Date.parse(r.requestedAt))/1000:null,
  usage:r.usage,tools,efforts,inputCharacters,scriptCharacters,scriptRequests,sourceRunReuse,reportRequests,
  ingestionCalls:['process_documents','run_cleaning_script','commit_cleaning_result','save_research_claims'].reduce((n,k)=>n+(tools[k]||0),0),
  toolErrors:events.filter(e=>e.type==='tool_error').map(e=>({name:e.data.name,error:e.data.message})),
  delivery:delivery?{artifacts:delivery.artifacts.length,downloaded:delivery.artifacts.filter(x=>x.httpStatus===200).length,analyses:delivery.evaluatorScripts}:null,
  review:await optional('judge/'+r.label+'-review.json')});
}
const totals=rs=>Object.fromEntries(['input','output','reasoning','cacheRead','uncachedInput','cacheKnownInput','calls','unknownCalls','costUnknownCalls'].map(k=>[k,rs.reduce((s,r)=>s+(r.usage?.[k]||0),0)]));
const summarize=rs=>{const t=totals(rs);return {attempts:rs.length,completed:rs.filter(r=>r.status==='completed').length,seconds:rs.reduce((n,r)=>n+(r.seconds||0),0),...t,cacheHitPercent:t.cacheKnownInput?t.cacheRead/t.cacheKnownInput*100:null,scriptRequests:rs.reduce((n,r)=>n+r.scriptRequests,0),scriptCharacters:rs.reduce((n,r)=>n+r.scriptCharacters,0),reportRequests:rs.reduce((n,r)=>n+r.reportRequests,0),sourceRunReuse:rs.reduce((n,r)=>n+r.sourceRunReuse,0)};};
const groups=state.arms.map(a=>({arm:a.id,profile:a.profile,repeat:a.repeat,...summarize(rows.filter(r=>r.label[0]===a.id))}));
const paired=[];
for(const task of state.tasks){
 const b=rows.filter(r=>r.profile==='prepared'&&r.label.slice(1)===task.id),c=rows.filter(r=>r.profile==='financial'&&r.label.slice(1)===task.id);
 const bt=summarize(b),ct=summarize(c);
 paired.push({task:task.id,name:task.name,prepared:bt,financial:ct,ratioFinancialToPrepared:Object.fromEntries(['input','output','seconds','scriptCharacters'].map(k=>[k,bt[k]?ct[k]/bt[k]:null]))});
}
const changed=[];
for(const [file,expected] of Object.entries(state.codeFiles))if(createHash('sha256').update(await readFile(file)).digest('hex')!==expected)changed.push(file);
const preparations=setup.ingestion.flatMap(r=>[...(r.previousAttempts||[]),{runId:r.runId,status:r.status,usage:r.usage,error:r.error}]);
const report={createdAt:new Date().toISOString(),study:state.study,projectId:state.projectId,model:state.model,provider:state.provider,documents:state.documents,
 codeUnchanged:changed.length===0,changedCodeFiles:changed,structuredDataUnchanged:state.structuredDataUnchanged,taskSha256:state.taskSha256,plannedOrder:state.plannedOrder,
 interventions:state.interventions,frontendRendering:await optional('frontend-rendering-update.json'),artifactReplays:await optional('replay-results.json'),environmentCleanup:await optional('environment-final-cleanup.json'),
 preparation:{attempts:preparations,totals:totals(preparations),jsonProbe:await optional('cpa-json-probe.json')},groups,paired,runs:rows,
 monetaryPrice:{currency:null,verified:false,note:'CPA tariff not verified. Pi catalog cost is not a bill; report tokens and unknown calls, not inferred currency cost.'},
 limitations:['Two new documents from one company; not proof of cross-industry generalization or statistical superiority.','B/C have identical prepared records and two repetitions each. A reads the same raw documents once.','Same model and router policy; actual reasoning per request is recorded, upstream cache warmth is uncontrolled.','All failed attempts and unknown usage remain counted. Ingestion preparation is separate from analysis.','Deterministic rendering smoke alone does not prove model adoption or financial correctness. Review actual answers, calculations and figures.','Developer-reviewed, not blinded: arithmetic/download/replay checks are deterministic; interpretation and visual assessments are qualitative, not independent expert scoring.']};
await writeFile(path.join(dir,'results.json'),JSON.stringify(report,null,2)+'\n');
if(process.argv.includes('--publish')){const dest=path.resolve('docs/evidence',name);await mkdir(dest,{recursive:true});await writeFile(path.join(dest,'results.json'),JSON.stringify(report,null,2)+'\n');}
console.log(JSON.stringify({groups,paired,reviewed:rows.filter(r=>r.review).length,codeUnchanged:report.codeUnchanged,structuredDataUnchanged:report.structuredDataUnchanged},null,2));
