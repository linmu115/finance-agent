// N1 private held-out preparation. Standard product API only. No cancel or follow-up command.
import fs from 'node:fs/promises';
import path from 'node:path';
const root=process.cwd(),dir=path.join(root,'data/evaluation/blind-eval-v3-heldout-private-20261008/ingestion');
const stateFile=path.join(dir,'preparation.json');
const write=async(p,v)=>fs.writeFile(p,JSON.stringify(v,null,2)+'\n');
const api=async(route,body)=>{const r=await fetch('http://127.0.0.1:3001'+route,{signal:AbortSignal.timeout(120000),...(body===undefined?{}:{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)})});if(!r.ok)throw Error(`${route}: ${r.status} ${await r.text()}`);return r.json();};
const command=process.argv[2];
if(command==='start'){
 const health=await api('/api/health'),settings=await api('/api/settings');
 if(!health.ok||health.service!=='connected'||!health.modelConfigured)throw Error('3001 not healthy');
 if(settings.llm.provider!=='cpa-local'||settings.llm.model!=='gpt-6-luna')throw Error('Approved CPA gpt-6-luna config unavailable');
 const source=path.join(root,'data/evaluation/blind-eval-v3-heldout-private-20261008/白云机场2024年年度报告.pdf');
 const s={createdAt:new Date().toISOString(),category:'preparation_only',health,model:settings.llm.model,provider:settings.llm.provider,billedCost:null,projectName:'N1-v3-heldout-20261008',status:'creating',source,manualFollowups:0,attempts:[],authority:'User explicitly authorized new isolated project and complete standard ingestion; low cleaning/local high; coordinator handles cancellation and later v3 reapply.'};
 await fs.mkdir(dir,{recursive:true});await fs.writeFile(stateFile,JSON.stringify(s,null,2)+'\n',{flag:'wx'});
 s.projectId=(await api('/api/projects',{name:s.projectName})).id;await write(stateFile,s);
 const form=new FormData();form.append('files',new Blob([await fs.readFile(source)],{type:'application/pdf'}),path.basename(source));
 const r=await fetch(`http://127.0.0.1:3001/api/projects/${s.projectId}/uploads`,{method:'POST',body:form,signal:AbortSignal.timeout(120000)});if(!r.ok)throw Error(`upload ${r.status}: ${await r.text()}`);
 const uploaded=await r.json();if(uploaded.documents.length!==1)throw Error('Expected one uploaded source');s.document=uploaded.documents[0];await write(stateFile,s);
 s.conversationId=(await api(`/api/projects/${s.projectId}/conversations`,{})).id;await write(stateFile,s);
 const content='请按产品标准完整入库流程处理本次上传的年报，保留全部财务主表、附注及原文，不做投资或金融分析。清洗使用 low，真正有疑点的局部使用 high；主体、期间、会计准则、合并与母公司、币种单位和利润归属以文档本身为准。复用已经有效提交的断点，force=false，不手工改库。不读取其他项目或评测文件。让宿主自动续跑并保留搁置项、待核验项和真实停止原因，不把部分入库称为完整完成。';
 const a={requestedAt:new Date().toISOString(),status:'posting',content};s.attempts.push(a);s.status='posting';await write(stateFile,s);
 Object.assign(a,await api(`/api/conversations/${s.conversationId}/messages`,{content,documentIds:[s.document.id]}),{status:'running'});s.status='running';await write(stateFile,s);
 console.log(JSON.stringify({status:s.status,projectId:s.projectId,documentId:s.document.id,conversationId:s.conversationId,runId:a.runId,category:s.category}));
}else if(['resume-f20','resume-f202','resume-f203','resume-f21'].includes(command)){
 const s=JSON.parse(await fs.readFile(stateFile,'utf8')),prior=s.attempts.at(-1);
 const version=command==='resume-f21'?'F2.1':command==='resume-f203'?'F2.0.3':command==='resume-f202'?'F2.0.2':'F2.0',expectedPrior=command==='resume-f21'?'831d6910-24bc-4b68-93cc-9e72dbeeb956':command==='resume-f203'?'3491e5ff-2e3f-499c-b9e4-e72b81f4a390':command==='resume-f202'?'f4246e8f-887b-43e1-a34a-e3ee3109bc34':'45b7ad9a-7dc9-4c66-8df1-66b4b4680448';
 if(prior?.runId!==expectedPrior)throw Error('Coordinated resume already attempted; inspect before posting');
 if(command==='resume-f203'){
  const reconciled=await api('/api/runs/'+prior.runId);
  if(reconciled.status!=='failed')throw Error('Expected main-reconciled recoverable failure');
  await write(path.join(dir,'F203-prior-reconciled-run.json'),reconciled);
 }else if(prior.status!=='cancelled')throw Error('Prior pause not sealed as cancelled');
 const health=await api('/api/health'),settings=await api('/api/settings');
 if(!health.ok||health.service!=='connected'||!health.modelConfigured)throw Error('3001 not healthy');
 if(settings.llm.provider!=='cpa-local'||settings.llm.model!=='gpt-6-luna')throw Error('Approved model differs');
 const reapply=JSON.parse(await fs.readFile(path.join(dir,'../live/baiyun/report.json'),'utf8'));
 if(!reapply.passed)throw Error('Production reapplication not verified');
 const content='请从这份年报已经保存的断点恢复标准完整入库，调用 process_documents 时使用 force=false，复用已有 processing_id 和已提交结果。继续清洗 low，真正疑点局部 high，按宿主自动续跑流程处理剩余表和搁置表；不重新开始、不做金融分析、不读取其他项目或评测文件。保留全部原文、局部待核验项和真实停止原因。';
 const a={requestedAt:new Date().toISOString(),status:'posting',content,segment:version+'-resume',commit:command==='resume-f21'?'7e702ff3f53eba8686254895ad98300445eac759':command==='resume-f203'?'14b9bde7687322cd1b82d67926f59029f39be11e':command==='resume-f202'?'b559f06149d1e4d431cb18521c027ce00dd44891':'ca81187c043eea52249cfe52a69ce5534aaa153b',reason:'authorized resume after coordinated deployment; reuse existing checkpoint',reapplication:reapply.result};
 s.attempts.push(a);s.status='posting';await write(stateFile,s);
 Object.assign(a,await api(`/api/conversations/${s.conversationId}/messages`,{content,documentIds:[s.document.id]}),{status:'running'});
 s.status='running';await write(stateFile,s);
 console.log(JSON.stringify({status:s.status,segment:a.segment,projectId:s.projectId,conversationId:s.conversationId,runId:a.runId}));
}else if(command==='poll'){
 const s=JSON.parse(await fs.readFile(stateFile,'utf8')),a=s.attempts.at(-1);if(!a?.runId)throw Error('Uncertain prior POST; inspect conversation before any further action');
 const run=await api('/api/runs/'+a.runId);await write(path.join(dir,'run.json'),run);
 s.document=await api(`/api/projects/${s.projectId}/documents/${s.document.id}`);await write(path.join(dir,'document.json'),s.document);
 await write(path.join(dir,'conversation.json'),await api('/api/conversations/'+s.conversationId));
 Object.assign(a,{status:run.status,usage:run.usage??null,error:run.error??null,finishedAt:run.finishedAt??null});s.status=run.status;s.updatedAt=new Date().toISOString();
 const audit=await fs.readFile(path.join(root,'data/active/audit',a.runId+'.jsonl'),'utf8');await fs.writeFile(path.join(dir,'audit.jsonl'),audit);
 const ev=audit.trim().split('\n').filter(Boolean).map(JSON.parse);s.autoContinuations=ev.filter(e=>e.type==='ingestion_continuation').length;s.stall=ev.filter(e=>e.type==='ingestion_stalled').at(-1)?.data??null;
 s.latestCoverage=ev.filter(e=>e.type==='tool_result'&&e.data.result?.data?.coverage).at(-1)?.data.result.data.coverage??null;
 await write(stateFile,s);console.log(JSON.stringify({status:s.status,documentStatus:s.document.status,factCount:s.document.factCount,autoContinuations:s.autoContinuations,coverage:s.latestCoverage,usage:a.usage,error:a.error}));
}else throw Error('start | resume-f20 | resume-f202 | poll (poll never posts messages; cancellation belongs to main)');
