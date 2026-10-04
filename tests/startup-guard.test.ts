import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtemp,mkdir,readFile,writeFile,readdir,rm,symlink,stat} from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import {spawn,type ChildProcess} from 'node:child_process';
import {once} from 'node:events';
import {createServer} from 'node:net';
import {setTimeout as delay} from 'node:timers/promises';
import {acquireStartupGuard} from '../server/startup-guard.js';

const root=path.resolve(import.meta.dirname,'..');
async function temporary(){return mkdtemp(path.join(os.tmpdir(),'finance-startup-guard-'));}
async function removeTemporary(dir:string){assert.equal(path.dirname(dir),path.resolve(os.tmpdir()));assert.ok(path.basename(dir).startsWith('finance-startup-guard-'));await rm(dir,{recursive:true,force:true});}
async function freePort(){const server=createServer();server.listen(0,'127.0.0.1');await once(server,'listening');const port=(server.address() as any).port;await new Promise<void>(resolve=>server.close(()=>resolve()));return port;}
const exited=(child:ChildProcess)=>child.exitCode!==null||child.signalCode!==null?Promise.resolve():once(child,'exit').then(()=>{});
async function stop(child:ChildProcess){if(child.exitCode===null&&child.signalCode===null){const done=exited(child);child.kill('SIGKILL');await done;}}
async function childGuard(data:string,marker:string){
 const child=spawn(process.execPath,['--import','tsx','tests/fixtures/startup-guard-child.ts'],{cwd:root,windowsHide:true,env:{...process.env,FIXTURE_DATA:data,FIXTURE_MARKER:marker,FIXTURE_PORT:'0'},stdio:['ignore','ignore','pipe','ipc']});
 let errors='';child.stderr!.on('data',x=>errors+=x);
 const result=await Promise.race([once(child,'message').then(([x])=>x as any),delay(12000,undefined,{ref:false}).then(()=>{throw Error('Child guard timed out: '+errors);})]).catch(async e=>{await stop(child);throw e;});
 return {child,result};
}
async function conflictingMain(data:string,port:number){
 const child=spawn(process.execPath,['--import','tsx','server/main.ts'],{cwd:root,windowsHide:true,env:{...process.env,FINANCE_DATA_DIR:data,FINANCE_PORT:String(port),FINANCE_HOST:'127.0.0.1',FINANCE_PYTHON:path.join(data,'fixture-no-such-python.exe')},stdio:['ignore','pipe','pipe']});
 let output='';child.stdout!.on('data',x=>output+=x);child.stderr!.on('data',x=>output+=x);
 try{await Promise.race([exited(child),delay(15000,undefined,{ref:false}).then(()=>{throw Error('Conflicting main did not exit');})]);return {code:child.exitCode,output};}finally{await stop(child);}
}

test('public port is claimed before creating DATA; initial 503 and application use the same continuously held listener',async()=>{
 const dir=await temporary(),first=await acquireStartupGuard({dataDir:path.join(dir,'first'),host:'127.0.0.1',port:0});
 try{
  const blockedData=path.join(dir,'must-not-exist');
  await assert.rejects(acquireStartupGuard({dataDir:blockedData,host:'127.0.0.1',port:first.port}),(e:any)=>e.code==='STARTUP_PORT_IN_USE');
  await assert.rejects(stat(blockedData),(e:any)=>e.code==='ENOENT');
  const before=await fetch('http://127.0.0.1:'+first.port+'/api/health');assert.equal(before.status,503);assert.equal((await before.json()).service,'starting');
  first.activate((_req,res)=>res.end('active'));assert.equal(await(await fetch('http://127.0.0.1:'+first.port)).text(),'active');
  await assert.rejects(acquireStartupGuard({dataDir:blockedData,host:'127.0.0.1',port:first.port}),(e:any)=>e.code==='STARTUP_PORT_IN_USE');
 }finally{await first.close();await removeTemporary(dir);}
});

test('canonical DATA blocks another port and junction alias while different DATA can run independently',async()=>{
 const dir=await temporary(),data=path.join(dir,'real'),alias=path.join(dir,'alias'),first=await acquireStartupGuard({dataDir:data,host:'127.0.0.1',port:0});let other;
 try{
  await assert.rejects(acquireStartupGuard({dataDir:data,host:'127.0.0.1',port:0}),(e:any)=>e.code==='STARTUP_DATA_IN_USE');
  await symlink(data,alias,process.platform==='win32'?'junction':'dir');
  await assert.rejects(acquireStartupGuard({dataDir:alias,host:'127.0.0.1',port:0}),(e:any)=>e.code==='STARTUP_DATA_IN_USE');
  other=await acquireStartupGuard({dataDir:path.join(dir,'other'),host:'127.0.0.1',port:0});assert.notEqual(other.port,first.port);
  first.stopAccepting();
  await assert.rejects(acquireStartupGuard({dataDir:data,host:'127.0.0.1',port:0}),(e:any)=>e.code==='STARTUP_DATA_IN_USE','HTTP shutdown must retain DATA until writers stop');
  assert.deepEqual(await readdir(data),[],'no PID/lease file to steal or delete');
 }finally{await other?.close();await first.close();await removeTemporary(dir);}
});

test('crash releases kernel DATA ownership; simultaneous successors have one winner and one initialization side effect',async()=>{
 const dir=await temporary(),data=path.join(dir,'data'),marker=path.join(dir,'init.jsonl');const children:ChildProcess[]=[];
 try{
  const original=await childGuard(data,marker);children.push(original.child);assert.equal(original.result.status,'acquired');
  const conflict=await childGuard(data,marker);children.push(conflict.child);assert.equal(conflict.result.code,'STARTUP_DATA_IN_USE');await exited(conflict.child);
  assert.equal((await readFile(marker,'utf8')).trim().split('\n').length,1);
  await stop(original.child); // abrupt termination, no guard.close or stale cleanup
  const contenders=await Promise.all(Array.from({length:4},()=>childGuard(data,marker)));children.push(...contenders.map(c=>c.child));
  assert.equal(contenders.filter(c=>c.result.status==='acquired').length,1);
  assert.equal(contenders.filter(c=>c.result.code==='STARTUP_DATA_IN_USE').length,3);
  assert.equal((await readFile(marker,'utf8')).trim().split('\n').length,2,'only old winner and one new winner initialize');
 }finally{await Promise.all(children.map(stop));await removeTemporary(dir);}
});

test('actual main rejects occupied port or owned DATA before settings initialization or MCP spawn',async()=>{
 const dir=await temporary(),data=path.join(dir,'owned'),guard=await acquireStartupGuard({dataDir:data,host:'127.0.0.1',port:0});
 try{
  const missing=path.join(dir,'not-created'),portConflict=await conflictingMain(missing,guard.port);
  assert.notEqual(portConflict.code,0);assert.match(portConflict.output,/STARTUP_PORT_IN_USE/);await assert.rejects(stat(missing),(e:any)=>e.code==='ENOENT');
  // Invalid settings would fail if loadSettings ran; exact directory contents
  // must survive rejection, even when the attempted public port is different.
  const marker='intentionally invalid settings; must never be read';await writeFile(path.join(data,'settings.json'),marker);
  const dataConflict=await conflictingMain(data,await freePort());assert.notEqual(dataConflict.code,0);assert.match(dataConflict.output,/STARTUP_DATA_IN_USE/);
  assert.equal(await readFile(path.join(data,'settings.json'),'utf8'),marker);assert.deepEqual(await readdir(data),['settings.json']);
 }finally{await guard.close();await removeTemporary(dir);}
});

test('failed real bootstrap releases both reservations for a later startup',async()=>{
 const dir=await temporary(),data=path.join(dir,'data'),port=await freePort();let guard;
 try{
  const failed=await conflictingMain(data,port);assert.notEqual(failed.code,0);assert.match(failed.output,/ENOENT|fixture-no-such-python/);
  guard=await acquireStartupGuard({dataDir:data,host:'127.0.0.1',port});assert.equal(guard.port,port);
 }finally{await guard?.close();await removeTemporary(dir);}
});
