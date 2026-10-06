// Small, resumable experiment client for the existing 3001 API. It does not
// implement an agent loop, execute model code, or retry uncertain POSTs.
import {readFile,writeFile,mkdir,rename,copyFile} from 'node:fs/promises';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {createHash} from 'node:crypto';
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
const dir=path.join(root,'data/evaluation/pi-pilot-20261005');
const stateFile=path.join(dir,'experiment.json');
const sha=x=>createHash('sha256').update(x).digest('hex');
const api=async(route,body)=>{
 const init={signal:AbortSignal.timeout(120000)};
 if(body!==undefined){init.method='POST';init.body=body instanceof FormData?body:JSON.stringify(body);if(!(body instanceof FormData))init.headers={'Content-Type':'application/json'};}
 const res=await fetch('http://127.0.0.1:3001'+route,init);
 const text=await res.text();if(!res.ok)throw Error(`${route}: HTTP ${res.status}: ${text.slice(0,600)}`);
 return JSON.parse(text);
};
const load=()=>readFile(stateFile,'utf8').then(JSON.parse);
const save=async s=>{await writeFile(stateFile+'.tmp',JSON.stringify(s,null,2)+'\n');await rename(stateFile+'.tmp',stateFile);};
const command=process.argv[2];
await mkdir(dir,{recursive:true});
if(command==='init'){
 let s=await load().catch(e=>{if(e.code==='ENOENT')return null;throw e;});
 if(!s){
  const tasks=JSON.parse(await readFile(path.join(dir,'tasks.json'),'utf8'));
  const gold=await readFile(path.join(dir,'judge/gold.json'));
  const settings=await api('/api/settings');
  s={createdAt:new Date().toISOString(),status:'initializing',study:'development_pilot_not_heldout',
   model:settings.llm.model,provider:settings.llm.provider,endpointSha256:sha(settings.llm.baseUrl||''),
   taskSha256:sha(JSON.stringify(tasks)),goldSha256:sha(gold),tasks,
   plannedOrder:['A1','B1','B2','A2','A3','B3'],
   evaluationLimits:{max_model_calls:1000,max_input_tokens:50000000,max_output_tokens:2000000,max_total_tokens:52000000,max_wall_seconds:43200},
   price:{currency:'CNY',cache_hit_per_million:[0.02,0.04],cache_miss_per_million:[1,2],output_per_million:[4,8],source:'https://api-docs.deepseek.com/zh-cn/quick_start/pricing/',kind:'estimate_range_not_bill',verifiedAt:'2026-10-05'},
   sandboxReady:false,arms:[{id:'A',profile:'generic'},{id:'B',profile:'financial'}],runs:[],interventions:[]};
  await save(s);
 }
 for(const arm of s.arms){
  if(!arm.projectId){const p=await api('/api/projects',{name:`对照试跑 10-05 · ${arm.id} ${arm.profile==='generic'?'通用 Pi':'金融项目'}`});arm.projectId=p.id;await save(s);}
  if(!arm.conversationId){const c=await api(`/api/projects/${arm.projectId}/conversations`,{});arm.conversationId=c.id;await save(s);}
 }
 s.status='ready_pending_sandbox';await save(s);
 console.log(JSON.stringify({status:s.status,arms:s.arms},null,2));
}else if(command==='start'){
 const s=await load(),label=process.argv[3],arm=s.arms.find(a=>a.id===label?.[0]),task=s.tasks.find(t=>String(t.id)===label?.[1]);
 if(!arm||!task)throw Error('Use start A1 / B1 / B2 / A2 / A3 / B3');
 if(!s.sandboxReady)throw Error('Equal isolated Python not verified; no model request sent');
 if(s.runs.some(r=>r.label===label))throw Error('Task already registered; inspect its result instead of resending');
 const settings=await api('/api/settings');if(settings.llm.model!==s.model||sha(settings.llm.baseUrl||'')!==s.endpointSha256)throw Error('Model/provider changed; do not mix arms');
 const existing=await api(`/api/conversations/${arm.conversationId}`);
 if(existing.activeRunId)throw Error('Conversation still active');
 let docs=[];
 if(task.file){
  arm.documents ||= {};
  if(!arm.documents[task.file]){const bytes=await readFile(path.join(root,task.file));if(sha(bytes)!==task.fileSha256)throw Error('PDF changed');const form=new FormData();form.append('files',new Blob([bytes],{type:'application/pdf'}),path.basename(task.file));const upload=await api(`/api/projects/${arm.projectId}/uploads`,form);arm.documents[task.file]=upload.documents[0].id;await save(s);}
  docs=[arm.documents[task.file]];
 }
 const record={label,taskId:task.id,profile:arm.profile,projectId:arm.projectId,conversationId:arm.conversationId,documentIds:docs,requestedAt:new Date().toISOString(),status:'posting'};
 s.runs.push(record);await save(s);
 // The posting marker remains if HTTP outcome is uncertain. Resolve by reading
 // the conversation, never by automatically replaying this request.
 // Each matched task has its own identical technical allowance. Cumulative
 // arm cost is computed from all runs, so later questions do not lose their
 // allowance merely because this arm did more ingestion on an earlier task.
 const group='pilot-20261005-'+arm.id+(task.id===1?'':'-task'+task.id);
 record.budgetGroupId=group;await save(s);
 const r=await api(`/api/conversations/${arm.conversationId}/messages`,{content:task.prompt,documentIds:docs,evaluation:{profile:arm.profile,budget_group_id:group,budget:s.evaluationLimits}});
 Object.assign(record,r,{status:'running'});s.status='running';await save(s);
 console.log(JSON.stringify(record,null,2));
}else if(command==='poll'){
 const s=await load(),out=[];
 for(const r of s.runs){if(!r.runId){out.push({label:r.label,status:r.status});continue;}
  const run=await api('/api/runs/'+r.runId);
  await writeFile(path.join(dir,r.label+'-run.json'),JSON.stringify(run,null,2)+'\n');
  const chat=await api('/api/conversations/'+r.conversationId);
  await writeFile(path.join(dir,r.profile+'-conversation.json'),JSON.stringify(chat,null,2)+'\n');
  r.status=run.status;r.usage=run.usage;r.error=run.error;r.completedAt=run.finishedAt;
  const usage=Object.fromEntries(['calls','input','output','reasoning','cacheRead','cacheKnownInput','unknownCalls','costCnyMin','costCnyMax'].map(k=>[k,r.usage?.[k]]));
  out.push({label:r.label,runId:r.runId,status:r.status,stage:run.stage,usage,error:r.error,finishedAt:run.finishedAt,tools:run.tools?.slice(-3)});
  await copyFile(path.join(root,'data/active/audit',r.runId+'.jsonl'),path.join(dir,r.label+'-audit.jsonl')).catch(e=>{if(e.code!=='ENOENT')throw e;});
 }
 await save(s);const active=out.filter(r=>['running','queued','posting'].includes(r.status));
 console.log(JSON.stringify(process.argv.includes('--active')?(active.length?active:out.slice(-1)):out,null,2));
}else{throw Error('Expected init, start, or poll');}
