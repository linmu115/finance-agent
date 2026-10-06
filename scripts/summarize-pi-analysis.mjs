// Read-only summaries from provider usage, recorded task results and evaluator reviews.
import {readFile,writeFile,mkdir} from 'node:fs/promises';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
const dir=path.join(root,'data/evaluation',process.env.FINANCE_COMPARISON_DIR||'pi-analysis-20261005-r2');
const read=async f=>JSON.parse(await readFile(path.join(dir,f),'utf8'));
const optional=async f=>{try{return await read(f);}catch(e){if(e.code==='ENOENT')return null;throw e;}};
const state=await read('experiment.json'),replays=await optional('replay-results.json')||[];
const rows=[];
for(const r of state.runs){
 const audit=(await readFile(path.join(dir,r.label+'-audit.jsonl'),'utf8')).trim().split('\n').map(JSON.parse);
 const tools={},efforts={};
 for(const event of audit){if(event.type==='tool_request')tools[event.data.name]=(tools[event.data.name]||0)+1;if(event.type==='model_request'){const e=event.data.sentReasoningEffort||event.data.reasoningEffort||'unspecified';efforts[e]=(efforts[e]||0)+1;}}
 const delivery=await optional(r.label+'-deliverables.json'),review=await optional('judge/'+r.label+'-review.json');
 rows.push({label:r.label,profile:r.profile,status:r.status,conversationId:r.conversationId,runId:r.runId,
  seconds:r.completedAt?(Date.parse(r.completedAt)-Date.parse(r.requestedAt))/1000:null,usage:r.usage,
  tools,reasoningEfforts:efforts,toolErrors:audit.filter(e=>e.type==='tool_error').map(e=>({name:e.data.name,error:e.data.message})),
  ingestionCalls:['process_documents','run_cleaning_script','commit_cleaning_result','save_research_claims'].reduce((sum,k)=>sum+(tools[k]||0),0),
  deliveries:delivery?{total:delivery.artifacts.length,downloaded:delivery.artifacts.filter(a=>a.httpStatus===200).length,analyses:delivery.evaluatorScripts.map(x=>({runId:x.runId,status:x.status,containerRemoved:x.containerRemoved}))}:null,
  replay:replays.filter(x=>x.label===r.label),review});
}
const groups=[];
for(const arm of state.arms)for(const phase of ['initial','update']){
 const attempted=rows.filter(r=>r.label[0]===arm.id&&(phase==='update'?r.label[1]==='4':r.label[1]!=='4'));
 const subset=attempted.filter(r=>r.status==='completed');
 const totals=Object.fromEntries(['input','output','reasoning','cacheRead','cacheKnownInput','uncachedInput','calls','unknownCalls','costUnknownCalls'].map(k=>[k,subset.reduce((n,r)=>n+(r.usage?.[k]||0),0)]));
 for(const key of ['costCnyMin','costCnyMax']){const known=subset.filter(r=>typeof r.usage?.[key]==='number');totals[key]=known.length?known.reduce((n,r)=>n+r.usage[key],0):null;}
 groups.push({arm:arm.id,profile:arm.profile,phase,tasks:subset.length,completed:subset.filter(r=>r.status==='completed').length,coreNumericPassed:subset.reduce((n,r)=>n+(r.review?.core_numeric?.passed||0),0),coreNumericTotal:subset.reduce((n,r)=>n+(r.review?.core_numeric?.total||0),0),seconds:subset.reduce((n,r)=>n+(r.seconds||0),0),...totals,cacheHitPercent:totals.cacheKnownInput?totals.cacheRead/totals.cacheKnownInput*100:null});
}
const prior=path.basename(dir).startsWith('pi-analysis-20261005')?JSON.parse(await readFile(path.join(root,'data/evaluation/pi-analysis-20261005/interruption.json'),'utf8')):null;
const report={study:state.study,model:state.model,projectId:state.projectId,dataSummary:state.dataSummary,structuredDataUnchanged:state.structuredDataUnchanged,documents:state.documents,taskSha256:state.taskSha256,plannedOrder:state.plannedOrder,
 price:state.model==='deepseek-flash'?{source:'https://api-docs.deepseek.com/zh-cn/quick_start/pricing/',verified:'2026-10-05',currency:'CNY',perMillion:{cacheHit:[0.02,0.04],uncached:[1,2],output:[4,8]},note:'Known provider token usage at official low/high tariffs; not an invoice. Reasoning is already included in output.'}:{source:'local CPA usage responses',currency:null,perMillion:null,note:'No verified CPA monetary tariff configured. Token usage and cache accounting are reported; price remains unknown, not zero.'},
  groups,runs:rows,interruptedAttempts:rows.filter(r=>r.status!=='completed').map(r=>({label:r.label,status:r.status,usage:r.usage})),interruptedFirstAttempt:prior,
 limits:['Development regression on two previously used documents, one run per arm per task; not held out or statistically significant.', 'Same model/router policy; actual reasoning efforts recorded per request, provider cache warmth not controlled.', 'A reads raw source; B/C have identical frozen prepared records. Ingestion cost excluded from analysis and no new ingestion is requested.', ...(prior?['First attempt exposed missing sandbox feedback. It is preserved with expense separate from the corrected comparison; one cancelled request has unknown usage.']:[])]};
await writeFile(path.join(dir,'results.json'),JSON.stringify(report,null,2)+'\n');
if(process.argv.includes('--publish')){const dest=path.join(root,'docs/evidence',process.env.FINANCE_COMPARISON_DIR||'pi-analysis-20261005');await mkdir(dest,{recursive:true});await writeFile(path.join(dest,state.model==='deepseek-flash'?'deepseek-results.json':'cpa-results.json'),JSON.stringify(report,null,2)+'\n');}
console.log(JSON.stringify({groups,reviewed:rows.filter(r=>r.review).length,runs:rows.length},null,2));
