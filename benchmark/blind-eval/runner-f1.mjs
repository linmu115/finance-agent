// Multi-project formal runner. plan/check are offline; step/run submit paid analysis.
import fs from 'node:fs/promises';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {execFileSync} from 'node:child_process';
import {plan,step,reconcile,digest,canonical} from './study-f1.mjs';
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'../..');
const [command,name,arg,extra]=process.argv.slice(2);
if(!/^blind-eval-[\w.-]+$/.test(name||''))throw Error('Output must be blind-eval-*');
const dir=path.join(root,'data/evaluation',name),file=path.join(dir,'experiment.json');
const read=async p=>JSON.parse(await fs.readFile(p,'utf8'));
const write=async(p,v)=>{await fs.mkdir(path.dirname(p),{recursive:true});await fs.writeFile(p,JSON.stringify(v,null,2)+'\n');};
const save=async s=>{await write(file+'.tmp',s);await fs.rename(file+'.tmp',file);};
const api=async(route,body)=>{const r=await fetch('http://127.0.0.1:3001'+route,{...(body===undefined?{}:{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)}),signal:AbortSignal.timeout(120000)});if(!r.ok)throw Error(`${route}: ${r.status} ${await r.text()}`);return r.json();};
const exec=(bin,args)=>execFileSync(bin,args,{cwd:root,encoding:'utf8',windowsHide:true,maxBuffer:256*1024*1024,env:{...process.env,PYTHONDONTWRITEBYTECODE:'1',PYTHONIOENCODING:'utf-8',FINANCE_COMPARISON_DIR:name}});
async function filesSnapshot(paths){
 const entries=[];
 async function walk(p){const stat=await fs.stat(path.join(root,p));if(stat.isDirectory()){
  for(const n of (await fs.readdir(path.join(root,p))).sort())if(!['node_modules','__pycache__','.pytest_cache','tests','test-results'].includes(n))await walk(path.join(p,n));
 }else entries.push({path:p.replaceAll('\\','/'),sha256:digest(await fs.readFile(path.join(root,p)))});}
 for(const p of paths)await walk(p);return entries;
}
const code=()=>filesSnapshot(['server','service','skills','sandbox','web','package.json','package-lock.json','requirements.lock.txt']);
const refs=s=>filesSnapshot(s.config.referenceFiles);
const phaseRefs=(s,phase)=>filesSnapshot(s.config.phases[String(phase)].referenceFiles);
const projects=(s,phase)=>[...new Set(s.config.tasks.filter(t=>t.phase===phase).map(t=>t.projectId))].sort();
const material=(s,phase)=>JSON.parse(exec(process.env.PYTHON||'python',['-B','benchmark/blind-eval/snapshot-f1.py',...projects(s,phase)]));
const listener=()=>JSON.parse(exec('powershell.exe',['-NoProfile','-Command',"$ids=@(Get-NetTCPConnection -LocalPort 3001 -State Listen -ErrorAction Stop | Select-Object -ExpandProperty OwningProcess -Unique); if($ids.Count -ne 1){throw 'Expected one 3001 listener'}; $p=Get-Process -Id $ids[0]; @{pid=$p.Id; startedAt=$p.StartTime.ToUniversalTime().ToString('o')} | ConvertTo-Json -Compress"]));
async function settings(){const x=await api('/api/settings');if(x.llm.model!=='gpt-6-luna'||x.llm.provider!=='cpa-local')throw Error('Model/provider mismatch');return {llm:x.llm,runtime:x.runtime};}
async function verify(s,phase){
 const observations={code:digest(await code()),settings:digest(await settings()),config:digest(s.config),references:digest(await refs(s)),phaseReferences:digest(await phaseRefs(s,phase)),material:digest(material(s,phase)),runtime:digest(listener())};
 const expected={code:s.freeze.codeSha256,settings:s.freeze.settingsSha256,config:s.freeze.configSha256,references:s.freeze.referencesSha256,phaseReferences:s.phaseFreezes[String(phase)].referencesSha256,material:s.phaseFreezes[String(phase)].sha256,runtime:digest(s.freeze.listener)};
 const differences=Object.keys(expected).filter(k=>expected[k]!==observations[k]);
 await write(path.join(dir,`verification-phase${phase}.json`),{at:new Date().toISOString(),differences,observations,expected});
 if(differences.length)throw Error('Frozen inputs changed: '+differences.join(', ')+'; stop and report affected pairs, never silently refreeze');
}
const io={api,save,verify,capture:async(r,run,chat)=>{
 await write(path.join(dir,r.label+'-run.json'),run);await write(path.join(dir,r.label+'-conversation.json'),chat);
 if(run.request?.evaluation?.isolation_key!==r.isolationKey||chat.evaluationIsolationKey!==r.isolationKey||run.conversationId!==r.conversationId)throw Error('Runtime isolation receipt mismatch; original response preserved');
 try{await fs.copyFile(path.join(root,'data/active/audit',r.runId+'.jsonl'),path.join(dir,r.label+'-audit.jsonl'));}catch(e){if(e.code!=='ENOENT')throw e;r.auditMissing=true;}
}};
if(command==='plan'){
 const s=plan(await read(path.resolve(arg)),name);await fs.mkdir(dir,{recursive:true});await fs.writeFile(file,JSON.stringify(s,null,2)+'\n',{flag:'wx'});console.log(JSON.stringify({turns:s.plannedOrder.length,chains:new Set(s.plannedOrder.map(r=>r.isolationKey)).size,paidRequests:0}));
}else{
 const s=await read(file);
 if(command==='freeze'){
  if(s.freeze||s.runs.length)throw Error('F1 freeze is write-once');
  const receipt=await read(path.resolve(arg));
  if(receipt.freezeVersion!=='F1'||!receipt.loadedCommit||!receipt.pid||!receipt.startedAt||!receipt.environment||!receipt.included?.n4||!receipt.included?.n3||!receipt.included?.isolation||!receipt.configurationFiles?.length)throw Error('Need mainline F1 deployment receipt, versions and effective configuration files');
  const head=exec('git',['rev-parse','HEAD']).trim();if(head!==receipt.loadedCommit)throw Error('HEAD differs from loaded F1 commit');
  const health=await api('/api/health'),runtime=listener(),c=await code(),r=await refs(s),configFiles=await filesSnapshot(receipt.configurationFiles);
  if(!health.ok||health.service!=='connected'||!health.modelConfigured||runtime.pid!==receipt.pid||Math.abs(Date.parse(runtime.startedAt)-Date.parse(receipt.startedAt))>1000)throw Error('Deployment receipt does not match healthy 3001 listener');
  // Hash live settings only: never persist possible credentials from an API response.
  s.freeze={version:'F1',receipt,receiptFiles:configFiles,head,tree:exec('git',['rev-parse','HEAD^{tree}']).trim(),status:exec('git',['status','--porcelain']),health,listener:runtime,code:c,codeSha256:digest(c),settingsSha256:digest(await settings()),configSha256:digest(s.config),references:r,referencesSha256:digest(r),at:new Date().toISOString()};
  await write(path.join(dir,'deployment-receipt.json'),receipt);
  for(const [index,item] of configFiles.entries()){const target=path.join(dir,'effective-config',index+'-'+path.basename(item.path));await fs.mkdir(path.dirname(target),{recursive:true});await fs.copyFile(path.join(root,item.path),target);}
  await save(s);console.log('F1 code/config frozen; freeze each phase data separately');
 }else if(command==='freeze-phase'){
  const phase=Number(arg);if(!s.config.phases[arg]||!s.freeze||s.phaseFreezes[arg]||s.runs.some(r=>r.phase===phase))throw Error('Invalid phase freeze');
  if(s.plannedOrder.filter(r=>r.phase<phase).some(row=>!s.runs.some(r=>r.label===row.label&&['completed','failed','cancelled','blocked_dependency'].includes(r.status))))throw Error('Earlier stage not settled');
  if(digest(await code())!==s.freeze.codeSha256||digest(await settings())!==s.freeze.settingsSha256||digest(await refs(s))!==s.freeze.referencesSha256||digest(listener())!==digest(s.freeze.listener))throw Error('F1 changed before phase freeze');
  for(const project of projects(s,phase)){const chats=await api(`/api/projects/${project}/conversations`);if(chats.conversations.some(c=>c.activeRunId))throw Error('Active task in phase project: '+project);}
  const data=material(s,phase),references=await phaseRefs(s,phase);await write(path.join(dir,`materials-F1-P${phase}.json`),data);s.phaseFreezes[arg]={sha256:digest(data),references,referencesSha256:digest(references),at:new Date().toISOString(),projects:projects(s,phase)};await save(s);console.log('Phase '+phase+' material freeze saved');
 }else if(command==='step'||command==='run'){
  const phase=Number(arg);if(!s.config.phases[arg])throw Error('Unknown configured stage');
  do{const result=await step(await read(file),phase,io);console.log(JSON.stringify(result));if(['phase_complete','uncertain_post'].includes(result.status)||command==='step')break;if(['running','queued'].includes(result.status))await new Promise(resolve=>setTimeout(resolve,15000));}while(true);
  if(command==='run'&&(await read(file)).runs.every(r=>['completed','failed','cancelled','blocked_dependency'].includes(r.status)))await verify(await read(file),phase);
 }else if(command==='reconcile'){
  const run=await api('/api/runs/'+extra),r=s.runs.find(r=>r.label===arg),chat=await api('/api/conversations/'+r.conversationId);reconcile(s,arg,run,chat);await io.capture(r,run,chat);await save(s);console.log('Reconciled existing run; no POST');
 }else if(command==='verify')await verify(s,Number(arg));
 else if(command==='collect')console.log(exec(process.execPath,['scripts/collect-pi-analysis.mjs']).trim());
 else if(command==='a5'){
  for(const r of s.runs.filter(r=>['completed','failed','cancelled'].includes(r.status)))exec(process.env.PYTHON||'python',['-B','benchmark/blind-eval/a5-adapter.py',path.join(dir,r.label+'-a5.json'),'--study',dir,'--label',r.label]);
  console.log('Existing mainline A5 CLI results saved; no model calls');
 }
 else if(command==='check')console.log(JSON.stringify({stages:Object.fromEntries(Object.keys(s.config.phases).map(p=>[p,{name:s.config.phases[p].name,turns:s.plannedOrder.filter(r=>r.phase===Number(p)).length}])),freeze:s.freeze?.version??null,phases:Object.keys(s.phaseFreezes),paidRequests:0}));
 else throw Error('Commands: plan STUDY config | check STUDY | freeze STUDY deployment-receipt | freeze-phase STUDY 1|2 | step/run STUDY 1|2 (paid) | reconcile STUDY label runId | verify STUDY 1|2 | collect/a5 STUDY');
}
