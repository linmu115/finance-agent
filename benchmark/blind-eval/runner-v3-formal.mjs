// The formal adapter shares the tested HTTP boundary and snapshot/collection paths.
// All raw evidence, including BH material, stays under the N1 private batch.
import fs from 'node:fs/promises';
import {existsSync} from 'node:fs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {execFileSync} from 'node:child_process';
import {tick,terminal,digest,canonical,accountError} from './study-v3-formal.mjs';
import {requestJson} from './evaluation-http.mjs';
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'../..');
const name='blind-eval-F21-formal-private-20261009',dir=path.join(root,'data/evaluation',name);
const pub=path.join(root,'data/evaluation/blind-eval-F21-formal-20261009');
const [command,...args]=process.argv.slice(2),file=path.join(dir,'experiment.json');
const stop=path.join(dir,'DRAIN.json'),lock=path.join(dir,'worker.lock');
const read=async p=>JSON.parse(await fs.readFile(p,'utf8'));
const write=async(p,v)=>{await fs.mkdir(path.dirname(p),{recursive:true});await fs.writeFile(p,JSON.stringify(v,null,2)+'\n');};
const save=async s=>{await write(file+'.tmp',s);await fs.rename(file+'.tmp',file);};
let interrupted=false;process.on('SIGINT',()=>{interrupted=true;});process.on('SIGTERM',()=>{interrupted=true;});
const stopped=()=>interrupted||existsSync(stop);
const api=(route,body)=>requestJson(route,body,{stopped});
const exec=(bin,argv)=>execFileSync(bin,argv,{cwd:root,encoding:'utf8',windowsHide:true,maxBuffer:512*1024*1024,env:{...process.env,PYTHONDONTWRITEBYTECODE:'1',PYTHONIOENCODING:'utf-8',FINANCE_COMPARISON_DIR:name}});
const python=argv=>exec(path.join(root,'.venv/Scripts/python.exe'),['-B',...argv]);
const listener=()=>JSON.parse(exec('powershell',['-NoProfile','-Command',"$formalListener=Get-NetTCPConnection -State Listen -LocalPort 3001; $formalProcess=Get-Process -Id ($formalListener|Select-Object -First 1 -ExpandProperty OwningProcess); @{pid=$formalProcess.Id;startedAt=$formalProcess.StartTime.ToUniversalTime().ToString('o')} | ConvertTo-Json -Compress"]));
async function hashes(paths){
 const rows=[];
 async function walk(p){const full=path.join(root,p),stat=await fs.stat(full);if(stat.isDirectory()){for(const n of (await fs.readdir(full)).sort())if(!['node_modules','__pycache__','tests','.pytest_cache'].includes(n))await walk(path.join(p,n));}else rows.push({path:p.replaceAll('\\','/'),sha256:digest(await fs.readFile(full))});}
 for(const p of paths)await walk(p);return rows;
}
const code=()=>hashes(['server','service','skills','sandbox','package.json','package-lock.json','requirements.lock.txt']);
const evaluator=()=>hashes(['benchmark/blind-eval/study-v3-formal.mjs','benchmark/blind-eval/runner-v3-formal.mjs','benchmark/blind-eval/evaluation-http.mjs','benchmark/blind-eval/snapshot-f14.py']);
const materials=projects=>JSON.parse(python(['benchmark/blind-eval/snapshot-f14.py',...projects]));
async function settings(){const v=await api('/api/settings');if(v.llm.provider!=='cpa-local'||v.llm.model!=='gpt-6-luna')throw Error('model_provider_changed');return {llm:v.llm,runtime:v.runtime};}
async function refs(){
 const protocol=await read(path.join(pub,'protocol-freeze.json'));
 for(const [p,h] of Object.entries(protocol.protocolFiles))if(digest(await fs.readFile(path.join(root,p)))!==h)throw Error('sealed_protocol_changed:'+p);
 const priv=await hashes(['data/evaluation/'+name+'/tasks.json','data/evaluation/'+name+'/planned-runs.json','data/evaluation/'+name+'/frozen-heldout-inputs','data/evaluation/'+name+'/frozen-judge-instructions']);
 return {protocol:digest(protocol),privateInputs:priv};
}
async function verify(s){
 const observed={code:digest(await code()),settings:digest(await settings()),references:digest(await refs()),listener:digest(listener()),evaluator:digest(await evaluator())};
 const differences=Object.keys(observed).filter(k=>observed[k]!==s.runtimeFreeze.digests[k]);
 const data=materials(Object.keys(s.projectFreezes));
 for(const [p,f] of Object.entries(s.projectFreezes))if(digest(data[p])!==f.sha256)differences.push('material:'+p);
 await write(path.join(dir,'latest-freeze-check.json'),{at:new Date().toISOString(),observed,differences});
 if(differences.length){s.stopReason='freeze_drift:'+differences.join(',');await save(s);throw Error(s.stopReason);}
 const h=await api('/api/health');if(!h.ok||h.service!=='connected'||!h.modelConfigured)throw Error('service_disconnected');
}
async function capture(r,run,chat){
 await write(path.join(dir,r.label+'-run.json'),run);await write(path.join(dir,r.label+'-conversation.json'),chat);
 const source=path.join(root,'data/active/audit',run.id+'.jsonl');
 if(!existsSync(source)){if(terminal.has(run.status))throw Error('terminal_audit_missing');return;}
 const raw=await fs.readFile(source,'utf8');await fs.writeFile(path.join(dir,r.label+'-audit.jsonl'),raw);
 const lines=raw.split('\n');if(!raw.endsWith('\n'))lines.pop();
 const events=lines.filter(Boolean).map(JSON.parse),cfg=events.find(e=>e.type==='run_config')?.data;
 const state=await read(file),expected=state.runtimeFreeze.contract.profiles[r.profile];
 if(cfg&&(cfg.analysis_only!==true||cfg.profile!==r.profile||canonical([...cfg.tools].sort())!==canonical([...expected.tools].sort())))throw Error('actual_profile_or_tool_drift');
 if(terminal.has(run.status)&&!cfg)throw Error('terminal_run_config_missing');
 const forbidden=new Set(['process_documents','run_cleaning_script','commit_cleaning_result','set_document_profile']);
 if(events.some(e=>e.type==='tool_request'&&forbidden.has(e.data.name)))throw Error('ingestion_triggered_in_evaluation');
 const auth=events.find(e=>/error|failed/.test(e.type)&&accountError(JSON.stringify(e.data)));
 if(auth){await write(path.join(dir,'account-stop-evidence.json'),{at:new Date().toISOString(),label:r.label,event:auth});throw Error('authentication_or_quota');}
}
const io={api,save,verify,capture,stopped};
if(command==='freeze-ready'){
 if(existsSync(file))throw Error('Formal runtime freeze is write-once');
 const s=await read(path.join(dir,'execution-state.json')),probe=await read(path.join(pub,'model-connectivity-after-restore.json'));
 if(!probe.passed)throw Error('Model connectivity check did not pass');
 const gate=await read(path.join(root,'data/evaluation/blind-eval-F21-gate-20261009/experiment.json'));
 const current=await code(),baseline=await read(path.join(root,'data/evaluation/blind-eval-F21-gate-20261009/code-files.json'));
 if(digest(current)!==digest(baseline))throw Error('F21 product files differ from accepted deployment');
 const runtime=listener(),health=await api('/api/health');
 if(runtime.pid!==36552||!health.ok||health.service!=='connected'||!health.modelConfigured)throw Error('Restored runtime differs from handoff');
 s.config={...gate.config,tasks:await read(path.join(dir,'tasks.json')),gate:undefined,repeats:undefined,executionEnabled:true,status:'formal_approved',referenceFiles:[]};
 s.study=name;s.judge={model:'gpt-6-astra',reasoningEffort:'high'};s.plannedOrder=await read(path.join(dir,'planned-runs.json'));
 const projects=[...new Set(s.runs.filter(r=>!r.taskId.startsWith('X')).map(r=>r.projectId))];
 for(const p of projects){const chats=await api(`/api/projects/${p}/conversations`);if(chats.conversations.some(c=>c.activeRunId))throw Error('Ready project has an active run');}
 const material=materials(projects);
 const held=await read(path.join(root,'data/evaluation/blind-eval-v3-heldout-private-20261008/completed-F21-20261009/material-snapshot.json'));
 for(const [p,data] of Object.entries(held))if(digest(material[p])!==digest(data))throw Error('Held-out source freeze changed');
 await write(path.join(dir,'material-snapshot.json'),material);await write(path.join(dir,'code-files.json'),current);
 for(const [p,data] of Object.entries(material))s.projectFreezes[p]={at:new Date().toISOString(),sha256:digest(data),documents:data.documents.map(d=>({document_id:d.document_id,status:d.status})),idleAtFreeze:true};
 const cfg=await settings();
 if(digest(cfg)!==gate.freeze.digests.settings)throw Error('F21 configured model/runtime changed');
 s.runtimeFreeze={version:'F2.1',commit:s.deployedCommit,protocolGitCommit:'207e105c37eae89131fb8cc264eba42781e7f3cc',at:new Date().toISOString(),listener:runtime,health,contract:gate.freeze.contract,
  digests:{code:digest(current),settings:digest(cfg),references:digest(await refs()),listener:digest(runtime),evaluator:digest(await evaluator())}};
 s.freeze=s.runtimeFreeze;s.stopReason=null;await save(s);
 await write(path.join(pub,'runtime-freeze.json'),{version:s.version,commit:s.deployedCommit,protocolGitCommit:s.runtimeFreeze.protocolGitCommit,at:s.runtimeFreeze.at,listener:runtime,health,ready_turns:108,project_snapshot_hashes:Object.values(s.projectFreezes).map(v=>v.sha256),participant_posts:0});
 console.log(JSON.stringify({frozen:true,ready:108,remaining_pending_data:54}));
}else if(command==='drain'){
 await write(stop,{at:new Date().toISOString(),reason:args.join(' ')||'operator pause'});console.log('Dispatch stopped; server runs retained.');
}else if(['run','resume','observe'].includes(command)){
 if(command==='resume'&&existsSync(stop))await fs.rename(stop,path.join(dir,'DRAIN-resumed-'+Date.now()+'.json'));
 if(existsSync(lock)){const owner=await read(lock);let alive=true;try{process.kill(owner.pid,0);}catch(e){if(e.code==='ESRCH')alive=false;else throw e;}if(alive)throw Error('Formal evaluator worker already alive');await fs.rename(lock,path.join(dir,'worker-stale-'+Date.now()+'.json'));}
 await fs.writeFile(lock,JSON.stringify({pid:process.pid,at:new Date().toISOString()}),{flag:'wx'});
 try{
  let s=await read(file);if(command!=='observe')await verify(s);
  for(;;){
   s=await read(file);const before=new Set(s.runs.filter(r=>terminal.has(r.status)).map(r=>r.label));
   const result=await tick(s,io,{submit:command!=='observe'});
   const finished=s.runs.filter(r=>terminal.has(r.status)&&!before.has(r.label));
   if(result.status!=='waiting'&&result.status!=='observed'||finished.length)console.log(JSON.stringify({...result,finished:finished.map(r=>({label:r.label,status:r.status,failureClass:r.failureClass})),terminal:s.runs.filter(r=>terminal.has(r.status)).length}));
   if(['complete','ready_blocks_complete'].includes(result.status))await verify(s);
   if(command==='observe'||['complete','ready_blocks_complete','uncertain_post','uncertain_conversation','stopped','first_turn_inspection_required'].includes(result.status)||(stopped()&&!s.runs.some(r=>['running','queued'].includes(r.status))))break;
   await new Promise(resolve=>setTimeout(resolve,result.status==='submitted'?100:10000));
  }
 }catch(e){const s=await read(file);s.stopReason=String(e);await save(s);await write(path.join(dir,'worker-error-'+Date.now()+'.json'),{at:new Date().toISOString(),error:String(e),participantRetry:false});throw e;}
 finally{await fs.unlink(lock);}
}else if(command==='verify')await verify(await read(file));
else if(command==='collect')console.log(exec(process.execPath,['benchmark/blind-eval/collect-v3-gate.mjs']));
else if(command==='inspect-first'){
 const s=await read(file),first=s.runs[0];
 if(s.runs.filter(r=>r.runId).length!==1||!terminal.has(first.status))throw Error('Exactly one terminal participant required');
 await verify(s);const before=await api('/api/health');
 const codeText=await fs.readFile(path.join(root,'server/dist/main.js'),'utf8'),deliveryText=await fs.readFile(path.join(root,'server/dist/research-artifacts.js'),'utf8');
 const route=codeText.slice(codeText.indexOf("app.get('/api/projects/:projectId/artifacts/:runId/:name'"),codeText.indexOf("app.get('/api/projects/:projectId/artifacts/:runId/:name'")+1800);
 if(!route.includes("service.call('get_artifact_metadata'"))throw Error('artifact_route_not_metadata');
 const delivery=deliveryText.slice(deliveryText.indexOf('export async function deliveryFile('),deliveryText.indexOf('export async function deliveryFile(')+1000);
 if(!delivery.includes("service.call('get_artifact_metadata'"))throw Error('delivery_route_not_metadata');
 exec(process.execPath,['benchmark/blind-eval/collect-v3-gate.mjs']);
 const manifest=await read(path.join(dir,first.label+'-deliverables.json'));
 const charts=manifest.artifacts.filter(a=>a.mimeType?.startsWith('image/')||/\.(png|svg|jpe?g)$/i.test(a.name));
 const after=await api('/api/health');if(!after.ok||after.service!=='connected')throw Error('service_disconnected_after_delivery');
 s.firstTurnInspection={passed:true,at:new Date().toISOString(),label:first.label,runStatus:first.status,before,after,metadataRoutes:true,chartCount:charts.length,downloadStatus:charts.map(a=>a.httpStatus),note:'Compiled metadata route and actual HTTP download observed; no independent wire interception. Missing/failed deliveries remain participant quality defects.'};
 await write(path.join(dir,'first-turn-inspection.json'),s.firstTurnInspection);await save(s);
 console.log(JSON.stringify({passed:true,service:after.service,charts:charts.length,chartDownloads:charts.map(a=>a.httpStatus)}));
}else if(command==='check'){
 const s=await read(file);console.log(JSON.stringify({counts:s.runs.reduce((a,r)=>(a[r.status]=(a[r.status]||0)+1,a),{}),stopReason:s.stopReason,drain:existsSync(stop),packets:Object.fromEntries([...new Set(s.runs.map(r=>r.reviewPacket))].map(p=>[p,s.runs.filter(r=>r.reviewPacket===p&&terminal.has(r.status)).length]))}));
}else throw Error('freeze-ready | run | resume | observe | verify | collect | inspect-first | drain | check');
