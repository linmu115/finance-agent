// Development-only study executor. No server/process management, upload or ingestion.
import fs from 'node:fs/promises';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {createHash} from 'node:crypto';
import {execFileSync} from 'node:child_process';
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'../..');
const [command,studyName,arg]=process.argv.slice(2);
if(!/^blind-eval-[\w.-]+$/.test(studyName||''))throw Error('Study name must be blind-eval-*');
const dir=path.join(root,'data/evaluation',studyName), stateFile=path.join(dir,'experiment.json');
const read=async p=>JSON.parse(await fs.readFile(p,'utf8'));
const sha=x=>createHash('sha256').update(x).digest('hex');
const write=async(p,x)=>{await fs.mkdir(path.dirname(p),{recursive:true});await fs.writeFile(p,JSON.stringify(x,null,2)+'\n');};
const save=async s=>{await write(stateFile+'.tmp',s);await fs.rename(stateFile+'.tmp',stateFile);};
const api=async(route,body)=>{const r=await fetch('http://127.0.0.1:3001'+route,{...(body===undefined?{}:{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)}),signal:AbortSignal.timeout(120000)});if(!r.ok)throw Error(`${route}: ${r.status} ${await r.text()}`);return r.json();};
async function codeDigest(){
 const h=createHash('sha256'),files=[];
 async function walk(folder){for(const e of (await fs.readdir(folder,{withFileTypes:true})).sort((a,b)=>a.name.localeCompare(b.name))){
  if(['node_modules','__pycache__','.pytest_cache','tests','test-results'].includes(e.name))continue;
  const p=path.join(folder,e.name);if(e.isDirectory())await walk(p);else if(/\.(py|ts|tsx|js|md|json|css|html)$/.test(p)){const n=path.relative(root,p).replaceAll('\\','/');h.update(n+'\0');h.update(await fs.readFile(p));files.push(n);}
 }}
 for(const p of ['server','service','skills','sandbox','web'])await walk(path.join(root,p));
 for(const p of ['package.json','package-lock.json','requirements.lock.txt']){h.update(p+'\0');h.update(await fs.readFile(path.join(root,p)));files.push(p);}
 return {sha256:h.digest('hex'),files};
}
async function dataSnapshot(project){
 const result={documents:(await api(`/api/projects/${project}/documents`)).documents,financial:[],research:[]};
 for(const [key,route] of [['financial','financial-data'],['research','assets/records']]){
  let offset=0;
  while(true){const page=await api(`/api/projects/${project}/${route}?limit=200&offset=${offset}`),d=page.data??page;
   if(!Array.isArray(d.items))throw Error('Unexpected paginated response '+route);
   result[key].push(...d.items);const count=result[key].length;
   if(d.next_offset===null||(typeof d.total==='number'&&count>=d.total))break;
   if(!d.items.length)throw Error('Premature empty page '+route);
   const next=d.next_offset??(offset+d.items.length);if(next<=offset)throw Error('Pagination did not advance');offset=next;
  }
 }
 return result;
}
function plan(config){
 if(config.model!=='gpt-6-luna'||config.provider!=='cpa-local')throw Error('Study requires CPA gpt-6-luna');
 if(!config.evaluationLimits)throw Error('Supply the cohort evaluation budget required by the existing API');
 if(!Number.isInteger(config.repeats)||config.repeats<2)throw Error('At least two repetitions per arm');
 const arms=[],plannedOrder=[];
 for(let r=1;r<=config.repeats;r++){
  const pair=[{id:`P${r}`,profile:'prepared',repeat:r},{id:`F${r}`,profile:'financial',repeat:r}];arms.push(...pair);
  // Alternating pair order balances early/late execution, preserving continuation dependencies.
  for(let i=0;i<config.tasks.length;i++)for(const arm of ((i+r)%2?pair:[...pair].reverse()))plannedOrder.push(`${arm.id}_${config.tasks[i].id}`);
 }
 if(new Set(config.tasks.map(t=>t.id)).size!==config.tasks.length)throw Error('Duplicate task IDs');
 for(const t of config.tasks){if(!t.prompt||!t.id)throw Error('Task needs id and prompt');if(t.continuationOf&&(config.tasks.findIndex(x=>x.id===t.continuationOf)<0||config.tasks.findIndex(x=>x.id===t.continuationOf)>=config.tasks.indexOf(t)))throw Error('Continuation must follow its parent');}
 return {...config,study:'blinded_paired_analysis',arms,plannedOrder,runs:[],preparation:{newIngestion:false,analysisUsesSamePreparedRecords:true,providerBilledCost:null,ledger:config.preparationLedger??null},judge:{model:'gpt-6-astra',reasoningEffort:'high',freshThread:true},createdAt:new Date().toISOString()};
}
if(command==='plan'){
 const s=plan(await read(path.resolve(arg)));await fs.mkdir(dir,{recursive:true});await fs.writeFile(stateFile,JSON.stringify(s,null,2)+'\n',{flag:'wx'});await write(path.join(dir,'tasks.json'),s.tasks);console.log(JSON.stringify({planned:s.plannedOrder,paidRequests:0}));
}else if(command==='freeze'){
 const s=await read(stateFile);if(s.runs.length)throw Error('Cannot refreeze after any attempt');
 const settings=await api('/api/settings');if(settings.llm.model!==s.model||settings.llm.provider!==s.provider)throw Error('Model/provider mismatch');
 const chats=await api(`/api/projects/${s.projectId}/conversations`);if(chats.conversations.some(c=>c.activeRunId))throw Error('Project is active; coordinate freeze with main thread');
 const data=await dataSnapshot(s.projectId);await write(path.join(dir,'structured-data-before.json'),data);
 const referenceFiles=s.referenceFiles||[];if(!referenceFiles.length)throw Error('List evaluator reference files before freeze');
 const refs={};for(const p of referenceFiles)refs[p]=sha(await fs.readFile(path.resolve(root,p)));
 s.freeze={code:await codeDigest(),dataSha256:sha(JSON.stringify(data)),taskSha256:sha(JSON.stringify(s.tasks)),references:refs,settingsSha256:sha(JSON.stringify({llm:settings.llm,runtime:settings.runtime})),model:settings.llm.model,provider:settings.llm.provider,runtime:settings.runtime,at:new Date().toISOString()};
 // Whole config digest includes endpoint/price/routing but never writes credentials to the experiment.
 await save(s);console.log(JSON.stringify({freeze:s.freeze,paidRequests:0}));
}else if(command==='start'||command==='retry'){
 // This command submits one paid task. Only invoke after Claude's explicit cohort go-ahead.
 const s=await read(stateFile),plannedLabel=arg;if(!s.freeze)throw Error('Freeze version first');
 if(sha(JSON.stringify(s.tasks))!==s.freeze.taskSha256)throw Error('Frozen task changed');
 const priorAttempts=s.runs.filter(r=>(r.plannedLabel??r.label)===plannedLabel);
 if(command==='retry'&&(!priorAttempts.length||!['failed','cancelled'].includes(priorAttempts.at(-1).status)))throw Error('Retry needs a recorded terminal failed/cancelled attempt; uncertain POST must be reconciled first');
 const label=command==='retry'?`${plannedLabel}__retry${priorAttempts.length}`:plannedLabel;
 if(s.runs.some(r=>r.label===label))throw Error('Attempt already recorded; poll it, never replay an uncertain POST');
 const arm=s.arms.find(a=>plannedLabel?.startsWith(a.id+'_')),task=s.tasks.find(t=>plannedLabel===`${arm?.id}_${t.id}`);if(!arm||!task)throw Error('Unknown planned label');
 const settings=await api('/api/settings');
 if(sha(JSON.stringify({llm:settings.llm,runtime:settings.runtime}))!==s.freeze.settingsSha256||(await codeDigest()).sha256!==s.freeze.code.sha256)throw Error('Frozen model/runtime/code changed; cohort is not comparable');
 let conversationId;
 if(task.continuationOf){const prior=s.runs.findLast(r=>(r.plannedLabel??r.label)===`${arm.id}_${task.continuationOf}`&&r.status==='completed');if(!prior)throw Error('Parent incomplete');conversationId=prior.conversationId;}
 else conversationId=(await api(`/api/projects/${s.projectId}/conversations`,{})).id;
 const record={label,plannedLabel,attempt:priorAttempts.length+1,taskId:task.id,split:task.split,taskType:task.type,profile:arm.profile,repeat:arm.repeat,projectId:s.projectId,conversationId,status:'posting',requestedAt:new Date().toISOString(),budgetGroupId:studyName+'-'+plannedLabel};s.runs.push(record);await save(s);
 const request={content:task.prompt,documentIds:[],evaluation:{profile:arm.profile,budget_group_id:record.budgetGroupId,...(s.evaluationLimits?{budget:s.evaluationLimits}:{})}};
 const response=await api(`/api/conversations/${conversationId}/messages`,request);Object.assign(record,response,{status:'running'});await save(s);console.log(JSON.stringify(record));
}else if(command==='poll'){
 const s=await read(stateFile);
 for(const r of s.runs){if(!r.runId){console.log(JSON.stringify({label:r.label,status:r.status,uncertainPost:true}));continue;}
  const [run,chat]=await Promise.all([api('/api/runs/'+r.runId),api('/api/conversations/'+r.conversationId)]);
  await write(path.join(dir,r.label+'-run.json'),run);await write(path.join(dir,r.label+'-conversation.json'),chat);
  Object.assign(r,{status:run.status,usage:run.usage??null,error:run.error,completedAt:run.finishedAt});
  const audit=path.join(root,'data/active/audit',r.runId+'.jsonl');
  try{await fs.copyFile(audit,path.join(dir,r.label+'-audit.jsonl'));}catch(e){if(e.code!=='ENOENT')throw e;r.auditMissing=true;}
 }await save(s);console.log(JSON.stringify(s.runs.map(r=>({label:r.label,status:r.status,usage:r.usage,error:r.error}))));
}else if(command==='verify'){
 const s=await read(stateFile),data=await dataSnapshot(s.projectId);await write(path.join(dir,'structured-data-after.json'),data);
 const code=await codeDigest(),settings=await api('/api/settings'),references={};
 for(const [p,hash] of Object.entries(s.freeze.references))references[p]=sha(await fs.readFile(path.resolve(root,p)))===hash;
 s.verification={at:new Date().toISOString(),codeUnchanged:code.sha256===s.freeze.code.sha256,dataUnchanged:sha(JSON.stringify(data))===s.freeze.dataSha256,tasksUnchanged:sha(JSON.stringify(s.tasks))===s.freeze.taskSha256,settingsUnchanged:sha(JSON.stringify({llm:settings.llm,runtime:settings.runtime}))===s.freeze.settingsSha256,referencesUnchanged:references};await save(s);console.log(JSON.stringify(s.verification));
}else if(command==='run'){
 // Resume durable progress. A failed/uncertain task is reported, never silently resubmitted.
 const cli=fileURLToPath(import.meta.url);
 const invoke=(...args)=>execFileSync(process.execPath,[cli,...args],{cwd:root,encoding:'utf8',windowsHide:true,stdio:'pipe',maxBuffer:8*1024*1024});
 for(const label of (await read(stateFile)).plannedOrder){
  let s=await read(stateFile),attempt=s.runs.findLast(r=>(r.plannedLabel??r.label)===label);
  if(!attempt){console.log(invoke('start',studyName,label).trim());}
  while(true){
   s=await read(stateFile);attempt=s.runs.findLast(r=>(r.plannedLabel??r.label)===label);
   if(attempt.status==='posting')throw Error('Uncertain POST preserved at '+label+'; reconcile its run ID before resuming');
   if(attempt.status==='completed')break;
   if(!['running','queued'].includes(attempt.status))throw Error('Terminal failure preserved at '+label+'; inspect and explicitly retry if appropriate');
   invoke('poll',studyName);s=await read(stateFile);attempt=s.runs.findLast(r=>(r.plannedLabel??r.label)===label);
   console.log(JSON.stringify({label,status:attempt.status,calls:attempt.usage?.calls??null}));
   if(['running','queued'].includes(attempt.status))await new Promise(resolve=>setTimeout(resolve,15000));
  }
 }
 console.log(invoke('collect',studyName).trim());console.log(invoke('verify',studyName).trim());
}else if(command==='collect'||command==='replay'){
 // Existing collector preserves actual HTTP results; existing replay uses isolated containers only.
 const script=command==='collect'?'scripts/collect-pi-analysis.mjs':'benchmark/blind-eval/replay.py';
 const bin=command==='collect'?process.execPath:(process.env.PYTHON||'python');
 const args=command==='collect'?[path.join(root,script)]:['-B',path.join(root,script),dir];
 execFileSync(bin,args,{cwd:root,env:{...process.env,PYTHONDONTWRITEBYTECODE:'1',FINANCE_COMPARISON_DIR:studyName},stdio:'inherit',windowsHide:true});
}else throw Error('Commands: plan STUDY config.json | freeze/run/start/retry/poll/verify/collect/replay STUDY [label]. run/start/retry are paid.');
