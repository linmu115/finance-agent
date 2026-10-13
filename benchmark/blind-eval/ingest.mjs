// Authorized material preparation via the existing product API; no DB access or service management.
import fs from 'node:fs/promises';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'../..');
const dir=path.join(root,'data/evaluation/blind-eval-ingestion-20261007');
const statePath=path.join(dir,'preparation.json');
const [command,arg,extra]=process.argv.slice(2);
const read=async p=>JSON.parse(await fs.readFile(p,'utf8'));
const write=async(p,x)=>{await fs.mkdir(path.dirname(p),{recursive:true});await fs.writeFile(p,JSON.stringify(x,null,2)+'\n');};
const save=s=>write(statePath,s);
const api=async(route,body)=>{const response=await fetch('http://127.0.0.1:3001'+route,{signal:AbortSignal.timeout(120000),...(body===undefined?{}:{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)})});if(!response.ok)throw Error(`${route}: ${response.status} ${await response.text()}`);return response.json();};
let s;
try{s=await read(statePath);}catch(e){if(e.code!=='ENOENT')throw e;s={createdAt:new Date().toISOString(),purpose:'material_preparation_not_analysis',authorizedModel:'cpa-local/gpt-6-luna',providerBilledCost:null,jobs:[]};}
if(command==='start'){
 const spec=await read(path.resolve(arg));
 const health=await api('/api/health'),settings=await api('/api/settings');
 if(!health.ok||health.service!=='connected')throw Error('Product service is not healthy');
 if(settings.llm.provider!=='cpa-local'||settings.llm.model!=='gpt-6-luna')throw Error('Preparation requires the approved CPA gpt-6-luna configuration');
 if(s.jobs.some(j=>j.key===spec.key))throw Error('Preparation already recorded; inspect the existing job rather than repost');
 const job={key:spec.key,source:spec.source,originalName:spec.originalName,projectId:spec.projectId??null,projectName:spec.projectName??null,content:spec.content,provider:settings.llm.provider,model:settings.llm.model,health,createdAt:new Date().toISOString(),status:'preparing',attempts:[]};s.jobs.push(job);await save(s);
 if(!job.projectId){job.projectId=(await api('/api/projects',{name:job.projectName})).id;await save(s);}
 const form=new FormData();form.append('files',new Blob([await fs.readFile(path.resolve(root,job.source))],{type:'application/pdf'}),job.originalName);
 const response=await fetch(`http://127.0.0.1:3001/api/projects/${job.projectId}/uploads`,{method:'POST',body:form,signal:AbortSignal.timeout(120000)});
 if(!response.ok)throw Error(`upload: ${response.status} ${await response.text()}`);
 const docs=(await response.json()).documents;if(docs.length!==1)throw Error('Expected exactly one uploaded document');
 job.document=docs[0];await save(s);
 job.conversationId=(await api(`/api/projects/${job.projectId}/conversations`,{})).id;await save(s);
 const attempt={requestedAt:new Date().toISOString(),status:'posting',content:job.content};job.attempts.push(attempt);job.status='posting';await save(s);
 Object.assign(attempt,await api(`/api/conversations/${job.conversationId}/messages`,{content:job.content,documentIds:[job.document.id]}),{status:'running'});job.status='running';await save(s);
 console.log(JSON.stringify({key:job.key,projectId:job.projectId,documentId:job.document.id,conversationId:job.conversationId,runId:attempt.runId,status:job.status}));
}else if(command==='poll'){
 for(const job of s.jobs){
  const attempt=job.attempts.at(-1);if(!attempt?.runId)continue;
  const run=await api('/api/runs/'+attempt.runId);Object.assign(attempt,{status:run.status,usage:run.usage??null,error:run.error??null,finishedAt:run.finishedAt??null});job.status=run.status;
  await write(path.join(dir,'runs',attempt.runId+'.json'),run);
  await write(path.join(dir,'conversations',job.conversationId+'.json'),await api('/api/conversations/'+job.conversationId));
  job.document=await api(`/api/projects/${job.projectId}/documents/${job.document.id}`);
  job.preparationComplete=run.status==='completed'&&['ready','needs_review'].includes(job.document.status);
  const audit=path.join(root,'data/active/audit',attempt.runId+'.jsonl');
  try{await fs.mkdir(path.join(dir,'audit'),{recursive:true});await fs.copyFile(audit,path.join(dir,'audit',attempt.runId+'.jsonl'));}catch(e){if(e.code!=='ENOENT')throw e;attempt.auditMissing=true;}
 }
 const attempts=s.jobs.flatMap(j=>j.attempts);s.usage={providerBilledCost:null,attemptCount:attempts.length,unknownUsageAttempts:attempts.filter(a=>a.usage==null).length};
 for(const key of ['input','output','uncachedInput','cacheRead','cacheWrite','reasoning','calls','unknownCalls','cacheUnknownCalls','costUnknownCalls']){const known=attempts.filter(a=>a.usage?.[key]!=null);s.usage[key]={knownSum:known.length?known.reduce((n,a)=>n+a.usage[key],0):null,unknownAttempts:attempts.length-known.length};}
 s.updatedAt=new Date().toISOString();await save(s);
 console.log(JSON.stringify({jobs:s.jobs.map(j=>({key:j.key,projectId:j.projectId,documentId:j.document?.id,runStatus:j.status,preparationComplete:j.preparationComplete,documentStatus:j.document?.status,pageCount:j.document?.pageCount,factCount:j.document?.factCount,researchRecordCount:j.document?.researchRecordCount,latestRunId:j.attempts.at(-1)?.runId,latestError:j.attempts.at(-1)?.error})),usage:s.usage}));
}else if(command==='continue'){
 const job=s.jobs.find(j=>j.key===arg);if(!job)throw Error('Unknown job');
 const settings=await api('/api/settings');if(settings.llm.provider!==job.provider||settings.llm.model!==job.model)throw Error('Approved preparation provider/model changed');
 const prior=job.attempts.at(-1),run=await api('/api/runs/'+prior.runId);if(!['completed','failed','cancelled'].includes(run.status))throw Error('Previous run is still active');
 Object.assign(prior,{status:run.status,usage:run.usage??null,error:run.error??null,finishedAt:run.finishedAt??null});
 const content=await fs.readFile(path.resolve(extra),'utf8'),attempt={requestedAt:new Date().toISOString(),status:'posting',content};job.attempts.push(attempt);job.status='posting';await save(s);
 Object.assign(attempt,await api(`/api/conversations/${job.conversationId}/messages`,{content,documentIds:[job.document.id]}),{status:'running'});job.status='running';await save(s);console.log(JSON.stringify({key:job.key,runId:attempt.runId,status:job.status}));
}else throw Error('start SPEC.json | poll | continue KEY CONTENT.txt');
