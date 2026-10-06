// Read-only evaluation of recorded runs. Never sends model requests or runs generated code.
import {readFile, writeFile, mkdir} from 'node:fs/promises';
import {createHash} from 'node:crypto';
import {fileURLToPath} from 'node:url';
import path from 'node:path';
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
const dir=path.join(root,'data/evaluation/pi-pilot-20261005');
const readJson=async p=>JSON.parse(await readFile(p,'utf8'));
const state=await readJson(path.join(dir,'experiment.json'));
const preparation=await readJson(path.join(dir,'preparation-manifest.json'));
const sumKeys=['input','output','reasoning','cacheRead','cacheKnownInput','costCnyMin','costCnyMax'];
const rows=[];
for(const run of state.runs){
 if(!['completed','failed','cancelled'].includes(run.status))throw Error(`${run.label} is not terminal`);
 const audit=(await readFile(path.join(dir,run.label+'-audit.jsonl'),'utf8')).trim().split('\n').map(JSON.parse);
 const requests=new Map(audit.filter(e=>e.type==='model_request').map(e=>[e.data.requestId,e]));
 const settlements=new Map(audit.filter(e=>e.type==='model_usage').map(e=>[e.data.requestId,e]));
 const missing=[...requests.keys()].filter(id=>!settlements.has(id));
 const unknown=[...new Set([...missing,...[...settlements].filter(([,e])=>e.data.usageKnown===false).map(([id])=>id)])];
 const tools={},routes={};
 for(const e of audit){
  if(e.type==='tool_request')tools[e.data.name]=(tools[e.data.name]||0)+1;
  if(e.type==='model_request'){
   const key=[e.data.phase,e.data.sentReasoningEffort||e.data.reasoningEffort||'unspecified'].join('/');
   routes[key]=(routes[key]||0)+1;
  }
 }
 const deliverables=await readJson(path.join(dir,run.label+'-deliverables.json'));
 const review=await readJson(path.join(dir,'judge',run.label+'-review.json'));
 const row={label:run.label,profile:run.profile,status:run.status,runId:run.runId,
  requestedAt:run.requestedAt,completedAt:run.completedAt,
  elapsedSeconds:(Date.parse(run.completedAt)-Date.parse(run.requestedAt))/1000,
  modelRequests:requests.size,knownUsageCalls:[...settlements.values()].filter(e=>e.data.usageKnown!==false).length,
  missingUsageRequests:missing,unknownUsageCalls:unknown.length,
  ...Object.fromEntries(sumKeys.map(k=>[k,run.usage[k]||0])),
  cacheHitPercent:run.usage.cacheRead/run.usage.cacheKnownInput*100,
  cacheCoverageOfKnownInputPercent:run.usage.cacheKnownInput/run.usage.input*100,
  toolCalls:Object.values(tools).reduce((a,b)=>a+b,0),tools,
  toolErrors:audit.filter(e=>e.type==='tool_error').map(e=>({tool:e.data.name,error:e.data.message})),
  modelRoutes:routes,compactions:audit.filter(e=>e.type==='compaction_started'||e.type==='compaction_saved').map(e=>({at:e.at,type:e.type,data:Object.fromEntries(['reason','tokens_before','tokensBefore','native','reserveTokens','keepRecentTokens','fromExtension'].filter(k=>k in e.data).map(k=>[k,e.data[k]]))})),
  analysisRuns:deliverables.evaluatorScripts.map(x=>({id:x.runId,status:x.status,containerRemoved:x.containerRemoved})),
  artifactDownload:{total:deliverables.artifacts.length,ok:deliverables.artifacts.filter(x=>x.httpStatus===200).length,
   failures:deliverables.artifacts.filter(x=>x.httpStatus!==200).map(x=>({name:x.name,status:x.httpStatus}))},
  review};
 rows.push(row);
}
const arms=['generic','financial'].map(profile=>{
 const r=rows.filter(x=>x.profile===profile),a={profile,tasks:r.length,completedTasks:r.filter(x=>x.status==='completed').length};
 for(const k of [...sumKeys,'modelRequests','knownUsageCalls','unknownUsageCalls','toolCalls','elapsedSeconds'])a[k]=r.reduce((s,x)=>s+x[k],0);
 a.cacheHitPercent=a.cacheRead/a.cacheKnownInput*100;
 a.cacheCoverageOfKnownInputPercent=a.cacheKnownInput/a.input*100;
 a.coreSamplePassed=r.reduce((s,x)=>s+(x.review.core_numeric?.passed||0),0);
 a.coreSampleTotal=r.reduce((s,x)=>s+(x.review.core_numeric?.total||0),0);
 a.toolErrors=r.reduce((s,x)=>s+x.toolErrors.length,0);
 return a;
});
const fingerprints=[];
for(const [file,expected] of Object.entries(preparation.files)){
 const actual=createHash('sha256').update(await readFile(path.join(root,file))).digest('hex');
 if(actual!==expected)fingerprints.push({file,expected,actual});
}
const result={study:'development_pilot_not_heldout',date:'2026-10-05',servicePort:3001,
 model:state.model,provider:state.provider,piVersion:'1.0.0',
 sources:preparation.sources,taskSha256:state.taskSha256,taskHashEncoding:'UTF-8 JSON.stringify(tasks)',goldSha256:state.goldSha256,goldHashEncoding:'file bytes',
 initialCodeSha256:preparation.codeSha256,changedFingerprintedFiles:fingerprints,
 runtimeCodeStillFrozen:!fingerprints.some(x=>/^(server|service|web)\//.test(x.file)),
 plannedOrder:state.plannedOrder,equalPerTaskTechnicalAllowance:state.evaluationLimits,
 price:state.price,costStatus:'Official price band applied to known usage, not invoice; unknown requests excluded, not zero.',
 reasoningAccounting:'Reasoning is already included in output; never added twice.',
 arms,runs:rows,interventions:state.interventions,methodNotes:state.methodNotes,
 cleanup:state.sandboxAuthorization,
 limits:['One paired development pilot, three tasks, two previously used PDFs; no heldout or significance claim.',
 'Generic reads selected pages; financial arm also performs ingestion. Cost difference is whole-workflow cost, not an isolated finance-skill effect.',
 'Same model and router policy, but actual per-request reasoning effort differs; provider cache warmness not controlled.',
 'Generic tool description mentions absent financial chart helper; attempted imports fail and fallback executes.',
 'A3 had a host interruption and infrastructure restart; one request has unknown usage. Wall time includes interruption.',
 'Numeric sample19 per arm is not whole-document correctness. Finance logic and deliverables assessed separately.']};
await writeFile(path.join(dir,'results.json'),JSON.stringify(result,null,2)+'\n');
const publicDir=path.join(root,'docs/evidence/pi-pilot-20261005');await mkdir(publicDir,{recursive:true});
await writeFile(path.join(publicDir,'results.json'),JSON.stringify(result,null,2)+'\n');
console.log(JSON.stringify({arms,runtimeCodeStillFrozen:result.runtimeCodeStillFrozen,changedFingerprintedFiles:fingerprints.map(x=>x.file)},null,2));
