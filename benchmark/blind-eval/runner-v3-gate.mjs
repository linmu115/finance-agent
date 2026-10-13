// Gate only: plan/check/observe are unbilled. run is paid and requires coordinator approval.
import fs from 'node:fs/promises';
import {existsSync} from 'node:fs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {execFileSync} from 'node:child_process';
import {planGate,tick,terminal,digest,canonical} from './study-v3-gate.mjs';
import {requestJson} from './evaluation-http.mjs';
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'../..');
const [command,name,arg]=process.argv.slice(2);
if(!/^blind-eval-[\w.-]+$/.test(name||''))throw Error('Expected private blind-eval study name');
const dir=path.join(root,'data/evaluation',name),file=path.join(dir,'experiment.json'),stop=path.join(dir,'DRAIN.json'),lock=path.join(dir,'worker.lock');
const read=async p=>JSON.parse(await fs.readFile(p,'utf8'));
const write=async(p,v)=>{await fs.mkdir(path.dirname(p),{recursive:true});await fs.writeFile(p,JSON.stringify(v,null,2)+'\n');};
const save=async s=>{await write(file+'.tmp',s);await fs.rename(file+'.tmp',file);};
let interrupted=false;process.on('SIGINT',()=>{interrupted=true;});process.on('SIGTERM',()=>{interrupted=true;});
const stopped=()=>interrupted||existsSync(stop);
const api=(route,body)=>requestJson(route,body,{stopped});
const exec=(bin,args)=>execFileSync(bin,args,{cwd:root,encoding:'utf8',windowsHide:true,maxBuffer:256*1024*1024,env:{...process.env,PYTHONDONTWRITEBYTECODE:'1',PYTHONIOENCODING:'utf-8',FINANCE_COMPARISON_DIR:name}});
const python=args=>exec(path.join(root,'.venv/Scripts/python.exe'),['-B',...args]);
const listener=()=>JSON.parse(exec('powershell',['-NoProfile','-Command',"$taskListener=Get-NetTCPConnection -State Listen -LocalPort 3001; $taskProcess=Get-Process -Id ($taskListener|Select-Object -First 1 -ExpandProperty OwningProcess); @{pid=$taskProcess.Id;startedAt=$taskProcess.StartTime.ToUniversalTime().ToString('o')} | ConvertTo-Json -Compress"]));
async function hashes(paths){
 const result=[];
 async function walk(p){const full=path.join(root,p),stat=await fs.stat(full);if(stat.isDirectory()){for(const n of (await fs.readdir(full)).sort())if(!['node_modules','__pycache__','tests','.pytest_cache'].includes(n))await walk(path.join(p,n));}else result.push({path:p.replaceAll('\\','/'),sha256:digest(await fs.readFile(full))});}
 for(const p of paths)await walk(p);return result;
}
const code=()=>hashes(['server','service','skills','sandbox','package.json','package-lock.json','requirements.lock.txt']);
const refs=s=>hashes(s.config.referenceFiles.map(n=>'benchmark/blind-eval/'+n));
const materials=s=>JSON.parse(python(['benchmark/blind-eval/snapshot-f14.py',...new Set(s.runs.map(r=>r.projectId))]));
async function settings(){const v=await api('/api/settings');if(v.llm.provider!=='cpa-local'||v.llm.model!=='gpt-6-luna')throw Error('model_provider_changed');return {llm:v.llm,runtime:v.runtime};}
async function verify(s){
 const observed={code:digest(await code()),settings:digest(await settings()),references:digest(await refs(s)),material:digest(materials(s)),listener:digest(listener()),config:digest(s.config)};
 const differences=Object.keys(observed).filter(k=>observed[k]!==s.freeze.digests[k]);
 await write(path.join(dir,'latest-freeze-check.json'),{at:new Date().toISOString(),observed,differences});
 if(differences.length){s.stopReason='freeze_drift:'+differences.join(',');await save(s);throw Error(s.stopReason);}
}
async function capture(r,run,chat){
 await write(path.join(dir,r.label+'-run.json'),run);await write(path.join(dir,r.label+'-conversation.json'),chat);
 const source=path.join(root,'data/active/audit',run.id+'.jsonl');
 if(!existsSync(source)){if(terminal.has(run.status))throw Error('terminal_audit_missing');return;}
 const raw=await fs.readFile(source,'utf8');await fs.writeFile(path.join(dir,r.label+'-audit.jsonl'),raw);
 const lines=raw.split('\n');if(!raw.endsWith('\n'))lines.pop(); // Active audit may have an unfinished last line; original bytes retained.
 const events=lines.filter(Boolean).map(JSON.parse),cfg=events.find(e=>e.type==='run_config')?.data;
 const state=await read(file),expected=state.freeze.contract.profiles[r.profile];
 if(cfg&&(cfg.analysis_only!==true||cfg.profile!==r.profile||canonical([...cfg.tools].sort())!==canonical([...expected.tools].sort())))throw Error('actual_profile_or_tool_drift');
 if(terminal.has(run.status)&&!cfg)throw Error('terminal_run_config_missing');
 const forbidden=new Set(['process_documents','run_cleaning_script','commit_cleaning_result','set_document_profile']);
 if(events.some(e=>e.type==='tool_request'&&forbidden.has(e.data.name)))throw Error('ingestion_triggered_in_evaluation');
}
const io={api,save,verify,capture,stopped};
if(command==='plan'){
 const config=await read(path.join(root,'benchmark/blind-eval/v3-gate-plan.json')),schedule=await read(path.join(root,'benchmark/blind-eval/v3-gate-schedule.json'));
 const state=planGate(config,schedule,name,arg||'F2.0.2');if(['F2.0.3','F2.1'].includes(arg))state.firstTurnInspectionRequired=true;if(arg==='F2.1')state.firstFinancialInspectionRequired=true;await fs.mkdir(dir,{recursive:true});await fs.writeFile(file,JSON.stringify(state,null,2)+'\n',{flag:'wx'});console.log(JSON.stringify({turns:18,participantPosts:0}));
}else if(command==='drain'){
 await write(stop,{at:new Date().toISOString(),reason:arg||'account switch / operator pause; do not cancel server runs'});console.log('Dispatch stopped. In-flight runs remain on 3001 and will be reconciled.');
}else if(command==='freeze'){
 const s=await read(file),receipt=await read(path.resolve(arg));
 if(s.freeze||s.runs.some(r=>r.status!=='planned'))throw Error('Freeze is write-once before participation');
 if(receipt.version!==(s.version||'F2.0.2'))throw Error('Expected coordinated study deployment');
 const head=exec('git',['rev-parse','HEAD']).trim(),runtime=listener(),health=await api('/api/health');
 if(head!==receipt.commit||runtime.pid!==receipt.pid||Math.abs(Date.parse(runtime.startedAt)-Date.parse(receipt.startedAt))>1000||!health.ok||health.service!=='connected'||!health.modelConfigured)throw Error('Deployment receipt differs from 3001');
 const contract=await read(path.resolve(receipt.contractReceipt));if(contract.status!=='passed'||contract.commit!==head)throw Error('Independent original_pi acceptance pending');
 const readiness=JSON.parse(python(['benchmark/blind-eval/gate-readiness-f20.py']));await write(path.join(dir,'freeze-readiness.json'),readiness);
 if(!readiness.all_required_submitted||!readiness.all_projects_idle)throw Error('Current tables not ready or project writing; never reuse old readiness');
 for(const p of new Set(s.runs.map(r=>r.projectId))){const chats=await api(`/api/projects/${p}/conversations`);if(chats.conversations.some(c=>c.activeRunId))throw Error('Project still active');}
 const c=await code(),r=await refs(s),m=materials(s),cfg=await settings();
 s.config.executionEnabled=true;s.config.status='approved_frozen_ready';
 await write(path.join(dir,'material-snapshot.json'),m);await write(path.join(dir,'code-files.json'),c);await write(path.join(dir,'reference-files.json'),r);
 s.freeze={version:receipt.version,commit:head,tree:exec('git',['rev-parse','HEAD^{tree}']).trim(),at:new Date().toISOString(),receipt,contract,listener:runtime,health,
  digests:{code:digest(c),settings:digest(cfg),references:digest(r),material:digest(m),listener:digest(runtime),config:digest(s.config)}};
 await save(s);console.log('Frozen; participant POSTs remain zero until run command is authorized.');
}else if(['run','resume','observe'].includes(command)){
 if(command==='resume'&&existsSync(stop))await fs.rename(stop,path.join(dir,'DRAIN-resumed-'+Date.now()+'.json'));
 if(existsSync(lock)){
  const owner=await read(lock);let alive=true;try{process.kill(owner.pid,0);}catch(e){if(e.code==='ESRCH')alive=false;else throw e;}
  if(alive)throw Error('Existing evaluator worker is alive; do not launch a second scheduler');
  await fs.rename(lock,path.join(dir,'worker-stale-'+Date.now()+'.json'));
 }
 await fs.writeFile(lock,JSON.stringify({pid:process.pid,at:new Date().toISOString()}),{flag:'wx'});
 try{
  let s=await read(file);if(command!=='observe'){if(!s.freeze||s.config.executionEnabled!==true)throw Error('Missing approved freeze');await verify(s);}
  do{
   s=await read(file);const result=await tick(s,io,{submit:command!=='observe'});if(result.status==='complete'&&s.freeze)await verify(s);console.log(JSON.stringify(result));
   if(command==='observe'||['complete','uncertain_post','uncertain_conversation','stopped','first_turn_inspection_required','financial_inspection_required'].includes(result.status)||(stopped()&&!s.runs.some(r=>['running','queued'].includes(r.status))))break;
   await new Promise(resolve=>setTimeout(resolve,result.status==='submitted'?100:10000));
  }while(true);
 }catch(e){await write(path.join(dir,'worker-error-'+Date.now()+'.json'),{at:new Date().toISOString(),error:String(e),participantRetry:false});throw e;}
 finally{await fs.unlink(lock);}
}else if(command==='verify')await verify(await read(file));
else if(command==='collect')console.log(exec(process.execPath,['benchmark/blind-eval/collect-v3-gate.mjs']));
else if(command==='a5'){
 const s=await read(file);for(const r of s.runs.filter(r=>terminal.has(r.status)))console.log(python(['benchmark/blind-eval/a5-adapter.py',path.join(dir,r.label+'-a5.json'),'--study',dir,'--label',r.label]));
}else if(command==='check'){
 const s=await read(file);console.log(JSON.stringify({freeze:s.freeze?.version??null,counts:s.runs.reduce((a,r)=>(a[r.status]=(a[r.status]||0)+1,a),{}),stop:s.stopReason,drain:existsSync(stop)}));
}else throw Error('plan | freeze RECEIPT | check | run (paid) | drain | observe | resume (paid) | verify | collect | a5');
