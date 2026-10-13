// One authorized resume per document. Polling never sends continuation messages.
import fs from 'node:fs/promises';
import path from 'node:path';
const root=process.cwd(),dir=path.join(root,'data/evaluation/blind-eval-broker-resume-20261008');
const file=path.join(dir,'preparation.json');
const keys=['everbright_20240512','huatai_20241030','everbright_20241104'];
const [command,key]=process.argv.slice(2);
const write=async(p,x)=>{await fs.mkdir(path.dirname(p),{recursive:true});await fs.writeFile(p,JSON.stringify(x,null,2)+'\n');};
const read=async p=>JSON.parse(await fs.readFile(p,'utf8'));
const api=async(route,body)=>{const r=await fetch('http://127.0.0.1:3001'+route,{signal:AbortSignal.timeout(120000),...(body===undefined?{}:{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)})});if(!r.ok)throw Error(`${route}: ${r.status} ${await r.text()}`);return r.json();};
let state;
try{state=await read(file);}catch(e){if(e.code!=='ENOENT')throw e;state={createdAt:new Date().toISOString(),purpose:'broker_material_preparation_resume_only',deployedCommit:'2f65edc',providerBilledCost:null,jobs:[]};}
if(command==='start'){
 if(!keys.includes(key))throw Error('Only the three authorized brokers may resume');
 if(state.jobs.some(j=>j.key===key))throw Error('Resume already recorded; inspect without reposting');
 const old=(await read(path.join(root,'data/evaluation/blind-eval-ingestion-20261007/preparation.json'))).jobs.find(j=>j.key===key);
 const health=await api('/api/health'),settings=await api('/api/settings');
 if(!health.ok||health.service!=='connected'||settings.llm.provider!=='cpa-local'||settings.llm.model!=='gpt-6-luna')throw Error('Approved healthy CPA gpt-6-luna runtime required');
 const previous=await api('/api/runs/'+old.attempts.at(-1).runId);
 if(!['completed','failed','cancelled'].includes(previous.status))throw Error('Existing document run is still active');
 const before=await api(`/api/projects/${old.projectId}/documents/${old.document.id}`);
 const content='继续上次这份研报的完整入库，从现有持久化断点恢复，复用已完成且仍有效的结果，不强制重洗。完整处理尚未完成的全部表格及正文观点、预测、依据和风险，保留来源、主体、期间、单位与实际/预测身份；不能确定的原格和语义留下具体待核说明。只做资料准备，不做金融分析。完成后简短报告覆盖和剩余疑点；尚未完成时保留实际停止原因。';
 const job={key,projectId:old.projectId,documentId:old.document.id,conversationId:old.conversationId,priorAttempts:old.attempts,before,provider:settings.llm.provider,model:settings.llm.model,health,content,requestedAt:new Date().toISOString(),status:'posting',manualFollowups:0};
 state.jobs.push(job);await write(file,state);
 Object.assign(job,await api(`/api/conversations/${job.conversationId}/messages`,{content,documentIds:[job.documentId]}),{status:'running'});await write(file,state);
 console.log(JSON.stringify({key,documentId:job.documentId,runId:job.runId,status:job.status}));
}else if(command==='poll'){
 for(const j of state.jobs){
  const run=await api('/api/runs/'+j.runId);j.status=run.status;j.usage=run.usage??null;j.error=run.error??null;j.finishedAt=run.finishedAt??null;j.startedAt=run.createdAt;j.elapsedMs=run.finishedAt?Date.parse(run.finishedAt)-Date.parse(run.createdAt):Date.now()-Date.parse(run.createdAt);
  j.document=await api(`/api/projects/${j.projectId}/documents/${j.documentId}`);
  await write(path.join(dir,j.key,'run.json'),run);await write(path.join(dir,j.key,'document.json'),j.document);
  await write(path.join(dir,j.key,'conversation.json'),await api('/api/conversations/'+j.conversationId));
  const audit=await fs.readFile(path.join(root,'data/active/audit',j.runId+'.jsonl'),'utf8');await fs.writeFile(path.join(dir,j.key,'audit.jsonl'),audit);
  const events=audit.trim().split('\n').filter(Boolean).map(JSON.parse);j.autoContinuations=events.filter(e=>e.type==='ingestion_continuation').length;j.stall=events.filter(e=>e.type==='ingestion_stalled').at(-1)?.data??null;
  const cover=events.filter(e=>e.type==='tool_result'&&e.data.result?.data?.coverage).at(-1);j.latestCoverage=cover?.data.result.data.coverage??null;
 }
 state.updatedAt=new Date().toISOString();await write(file,state);
 console.log(JSON.stringify(state.jobs.map(j=>({key:j.key,status:j.status,autoContinuations:j.autoContinuations,coverage:j.latestCoverage,records:j.document?.researchRecordCount,elapsedMs:j.elapsedMs,error:j.error,usage:j.usage?Object.fromEntries(['input','output','uncachedInput','cacheRead','cacheWrite','reasoning','calls','unknownCalls'].map(k=>[k,j.usage[k]])):null}))));
}else throw Error('start KEY | poll');
