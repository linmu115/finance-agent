// N1-only held-out preparation. One authorized resume; poll never posts messages.
import fs from 'node:fs/promises';
import path from 'node:path';
import {createHash} from 'node:crypto';
const root=process.cwd(),dir=path.join(root,'data/evaluation/blind-eval-tsingtao-F1-20261008');
const file=path.join(dir,'preparation.json'),oldFile=path.join(root,'data/evaluation/blind-eval-ingestion-20261007/preparation.json');
const write=async(p,x)=>{await fs.mkdir(path.dirname(p),{recursive:true});await fs.writeFile(p,JSON.stringify(x,null,2)+'\n');};
const read=async p=>JSON.parse(await fs.readFile(p,'utf8'));
const sha=x=>createHash('sha256').update(x).digest('hex');
const api=async(route,body)=>{const r=await fetch('http://127.0.0.1:3001'+route,{signal:AbortSignal.timeout(120000),...(body===undefined?{}:{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)})});if(!r.ok)throw Error(`${route}: ${r.status} ${await r.text()}`);return r.json();};
const command=process.argv[2];
if(command==='start'){
 const oldText=await fs.readFile(oldFile,'utf8'),old=JSON.parse(oldText).jobs.find(j=>j.key==='tsingtao_2024');
 const health=await api('/api/health'),settings=await api('/api/settings');
 if(!health.ok||health.service!=='connected'||settings.llm.provider!=='cpa-local'||settings.llm.model!=='gpt-6-luna')throw Error('Approved healthy CPA gpt-6-luna runtime required');
 const chats=await api(`/api/projects/${old.projectId}/conversations`);
 if(chats.conversations.some(c=>c.id===old.conversationId&&c.activeRunId))throw Error('Original conversation is active');
 const before=await api(`/api/projects/${old.projectId}/documents/${old.document.id}`);
 const content='继续这份年报原来已授权的完整入库任务，从现有持久化断点恢复，复用已完成且仍有效的结果，不重新上传或重建文档，不强制全量重洗。按当前产品流程完成全部尚未完成的表格及正文资料，期间、准则、主体、合并与母公司范围、币种单位以文档自身为准；已有结果的一致性和语义疑点也按当前标准流程处理，不直接改库。保留原文、来源和具体待核验项。只做完整资料准备，不做金融分析，不读取评测题面、参考答案或其他项目成果。让宿主按进度自动续跑，包括末尾对搁置集合的high修复；没有推进时保留断点并报告实际停止原因，不把部分事实当作完整完成。';
 const state={createdAt:new Date().toISOString(),purpose:'heldout_preparation_resume_only_N1',deployedCommit:'0c51eeb1f3e843cec83bd6a6f19b2fb9ee8dc0e7',observedPid:80212,providerBilledCost:null,oldLedger:{path:path.relative(root,oldFile).replaceAll('\\','/'),sha256:sha(oldText),attemptCount:old.attempts.length,attempts:old.attempts},job:{key:old.key,projectId:old.projectId,documentId:old.document.id,conversationId:old.conversationId,before,provider:settings.llm.provider,model:settings.llm.model,health,content,requestedAt:new Date().toISOString(),status:'posting',manualFollowups:0}};
 await fs.mkdir(dir,{recursive:true});await fs.writeFile(file,JSON.stringify(state,null,2)+'\n',{flag:'wx'});
 Object.assign(state.job,await api(`/api/conversations/${old.conversationId}/messages`,{content,documentIds:[old.document.id]}),{status:'running'});await write(file,state);
 console.log(JSON.stringify({runId:state.job.runId,status:state.job.status,projectId:old.projectId,documentId:old.document.id}));
}else if(command==='poll'){
 const s=await read(file),j=s.job;if(!j.runId)throw Error('Uncertain POST: reconcile saved conversation; never repost');
 const run=await api('/api/runs/'+j.runId);Object.assign(j,{status:run.status,usage:run.usage??null,error:run.error??null,finishedAt:run.finishedAt??null,startedAt:run.createdAt,elapsedMs:(run.finishedAt?Date.parse(run.finishedAt):Date.now())-Date.parse(run.createdAt)});
 j.document=await api(`/api/projects/${j.projectId}/documents/${j.documentId}`);
 await write(path.join(dir,'run.json'),run);await write(path.join(dir,'document.json'),j.document);
 await write(path.join(dir,'conversation.json'),await api('/api/conversations/'+j.conversationId));
 const audit=await fs.readFile(path.join(root,'data/active/audit',j.runId+'.jsonl'),'utf8');await fs.writeFile(path.join(dir,'audit.jsonl'),audit);
 const events=audit.trim().split('\n').filter(Boolean).map(JSON.parse);
 j.autoContinuations=events.filter(e=>e.type==='ingestion_continuation').length;
 j.stall=events.filter(e=>e.type==='ingestion_stalled').at(-1)?.data??null;
 j.latestCoverage=events.filter(e=>e.type==='tool_result'&&e.data.result?.data?.coverage).at(-1)?.data.result.data.coverage??null;
 s.oldLedger.unchanged=sha(await fs.readFile(oldFile,'utf8'))===s.oldLedger.sha256;s.updatedAt=new Date().toISOString();await write(file,s);
 console.log(JSON.stringify({status:j.status,documentStatus:j.document.status,facts:j.document.factCount,elapsedMs:j.elapsedMs,autoContinuations:j.autoContinuations,coverage:j.latestCoverage,stall:j.stall,error:j.error,usage:j.usage?Object.fromEntries(['input','output','uncachedInput','cacheRead','cacheWrite','reasoning','calls','unknownCalls','costUsd','costUnknownCalls'].map(k=>[k,j.usage[k]])):null,oldLedgerUnchanged:s.oldLedger.unchanged}));
}else throw Error('start | poll');
