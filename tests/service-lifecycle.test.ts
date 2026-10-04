import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import {spawn,type ChildProcess} from 'node:child_process';
import {once} from 'node:events';
import {setTimeout as delay} from 'node:timers/promises';
import {acquireStartupGuard} from '../server/startup-guard.js';

const root=path.resolve(import.meta.dirname,'..'),python=path.join(root,'.venv',process.platform==='win32'?'Scripts/python.exe':'bin/python');
const exited=(child:ChildProcess)=>child.exitCode!==null||child.signalCode!==null?Promise.resolve():once(child,'exit').then(()=>{});
const alive=(pid?:number)=>{if(!pid)return false;try{process.kill(pid,0);return true;}catch{return false;}};
async function waitFile(name:string,timeout=15000){const end=Date.now()+timeout;while(Date.now()<end){try{const value=await fs.readFile(name,'utf8');if(value.length)return value;}catch(e:any){if(e.code!=='ENOENT')throw e;}await delay(40);}throw Error('Timed out waiting for '+path.basename(name));}
async function runPython(args:string[],data:string){
 const child=spawn(python,args,{cwd:root,windowsHide:true,env:{...process.env,FINANCE_DATA_DIR:data,PYTHONPATH:root,PYTHONIOENCODING:'utf-8'},stdio:['pipe','pipe','pipe']});
 let output='';child.stdout.on('data',v=>output+=v);child.stderr.on('data',v=>output+=v);child.stdin.end();
 try{await Promise.race([exited(child),delay(12000,undefined,{ref:false}).then(()=>{throw Error('Private Python fixture timed out');})]);return {code:child.exitCode,output};}finally{if(child.exitCode===null&&child.signalCode===null){const end=exited(child);child.kill('SIGKILL');await end;}}
}
async function readState(data:string){const value=await runPython(['-c','import os,sqlite3,json;from pathlib import Path;p=Path(os.environ["FINANCE_DATA_DIR"])/"finance.sqlite";c=sqlite3.connect(p.as_uri()+"?mode=ro",uri=True);print(json.loads(c.execute("SELECT state_json FROM processing_runs WHERE processing_id=\'fixture_processing\'").fetchone()[0])["state"])'],data);assert.equal(value.code,0,value.output);return value.output.trim();}

for(const mode of ['stdin-eof','node-crash','default-executor-eof'] as const)test(`${mode}: real MCP child cannot overlap replacement Store recovery or leave a live uncancelled writer`,async t=>{
 const folder=await fs.mkdtemp(path.join(os.tmpdir(),'finance-service-lifecycle-')),data=path.join(folder,'data');
 const parent=spawn(process.execPath,['--import','tsx','tests/fixtures/service-lifecycle-parent.ts'],{cwd:root,windowsHide:true,env:{...process.env,FIXTURE_DATA:data,FIXTURE_PYTHON:python,FIXTURE_DEFAULT:mode==='default-executor-eof'?'1':'0'},stdio:['ignore','ignore','pipe','ipc']});
 let errors='',childPid:number|undefined,actualPid:number|undefined,guard;parent.stderr!.on('data',v=>errors+=v);
 try{
  const started:any=await Promise.race([once(parent,'message').then(([v])=>v),delay(15000,undefined,{ref:false}).then(()=>{throw Error('Private MCP parent failed: '+errors);})]);childPid=started.child_pid;assert.ok(childPid);
  actualPid=Number(await waitFile(path.join(folder,'worker-started')));assert.ok(actualPid);
  const initialBlocked=await runPython(['-c','import os;from service.lifecycle import ServiceOwnership;ServiceOwnership(os.environ["FINANCE_DATA_DIR"])'],data);assert.notEqual(initialBlocked.code,0,initialBlocked.output);assert.match(initialBlocked.output,/service_data_directory_in_use/);
  if(mode!=='node-crash')parent.send('end-stdin');else{const end=exited(parent);parent.kill('SIGKILL');await end;guard=await acquireStartupGuard({dataDir:data,host:'127.0.0.1',port:started.port});}
  // Some Windows launchers terminate their Python child along with the parent.
  // Either actual death or active cancellation is required; absence of a marker
  // alone is never treated as successful graceful shutdown.
  let observed='';const deadline=Date.now()+15000;
  while(Date.now()<deadline){try{observed=await fs.readFile(path.join(folder,'cancel-observed'),'utf8');}catch{}if(observed||(!alive(actualPid)&&!alive(childPid)))break;await delay(40);}
  if(mode==='node-crash'&&!alive(actualPid)&&!alive(childPid)){
   t.diagnostic('Private Python launcher and real worker both terminated after host kill; no orphan remains.');
   assert.equal(await readState(data),'normalizing','abrupt death must not invent completed/cancelled state');
   const successor=await runPython(['-m','service.server'],data);assert.equal(successor.code,0,successor.output);
   assert.equal(await readState(data),'failed','replacement honestly recovers interrupted state');
  }else{
   assert.equal(observed,'True',`EOF must signal cancellation while actual writer stays alive; alive=${alive(actualPid)} stderr=${errors}`);
   assert.ok(alive(actualPid),'draining worker must still exist for lock assertion');
   const blocked=await runPython(['-m','service.server'],data);assert.notEqual(blocked.code,0,blocked.output);assert.match(blocked.output,/service_data_directory_in_use/);
   assert.equal(await readState(data),'normalizing','blocked replacement must not run Store recovery');
   await fs.writeFile(path.join(folder,'release-worker'),'finish final write');
   const expected=mode==='default-executor-eof'?'completed':'cancelled';
   const final=JSON.parse(await waitFile(path.join(folder,'worker-finished')));assert.equal(final.state,expected);
   await waitFile(path.join(folder,'service-exited'));
   const successor=await runPython(['-m','service.server'],data);assert.equal(successor.code,0,successor.output);
   assert.equal(await readState(data),expected);
   t.diagnostic('EOF signalled cancellation and DATA lock remained held through the original worker final write.');
  }
 }finally{
  await fs.writeFile(path.join(folder,'release-worker'),'cleanup');
  if(parent.exitCode===null&&parent.signalCode===null){const end=exited(parent);parent.kill('SIGKILL');await end;}
  const until=Date.now()+5000;while((alive(childPid)||alive(actualPid))&&Date.now()<until)await delay(50);
  for(const pid of new Set([childPid,actualPid]))if(alive(pid)){try{process.kill(pid!,'SIGKILL');}catch{}}
  await guard?.close();
  assert.equal(path.dirname(folder),path.resolve(os.tmpdir()));assert.ok(path.basename(folder).startsWith('finance-service-lifecycle-'));await fs.rm(folder,{recursive:true,force:true});
 }
});
