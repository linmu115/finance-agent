import test from 'node:test';
import assert from 'node:assert/strict';
import express from 'express';
import fs from 'node:fs/promises';
import path from 'node:path';
import os from 'node:os';
import {once} from 'node:events';
import {spawn,type ChildProcess} from 'node:child_process';
import {setTimeout as delay} from 'node:timers/promises';
import {installWorkspaceApi} from '../server/workspace-api.js';
const fixture=path.resolve(import.meta.dirname,'fixtures/benchmark-api-runner.mjs');
async function setup(kind='hold'){
 const root=await fs.mkdtemp(path.join(os.tmpdir(),'finance-benchmark-api-')),folder=path.join(root,'benchmark/results');await fs.mkdir(folder,{recursive:true});
 const children:ChildProcess[]=[],app=express();app.use(express.json());
 installWorkspaceApi(app,{call:async()=>{throw Error('No MCP/model allowed');}} as any,{root,spawn:((_exe:string,args:string[],options:any)=>{const child=spawn(process.execPath,[fixture,...args.slice(1)],{...options,env:{...process.env,FIXTURE_MODE:kind}});children.push(child);return child;}) as any});
 app.use((e:any,_req:any,res:any,_next:any)=>res.status(500).json({error:String(e)}));
 const server=app.listen(0,'127.0.0.1');await once(server,'listening');const base='http://127.0.0.1:'+(server.address() as any).port;
 const get=async(url:string)=>{const r=await fetch(base+url);assert.equal(r.status,200,await r.clone().text());return r.json() as Promise<any>;};
 const post=async(mode='financial_v05')=>{const r=await fetch(base+'/api/benchmark/run',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({mode})});assert.ok([200,202].includes(r.status),await r.clone().text());return r.json() as Promise<any>;};
 return {root,folder,children,get,post,async close(){for(const c of children)if(c.exitCode===null&&c.signalCode===null){const end=once(c,'exit');c.kill('SIGKILL');await end;}await new Promise<void>(r=>server.close(()=>r()));assert.equal(path.dirname(root),path.resolve(os.tmpdir()));assert.ok(path.basename(root).startsWith('finance-benchmark-api-'));await fs.rm(root,{recursive:true,force:true});}};
}
async function until<T>(read:()=>Promise<T>,ok:(value:T)=>boolean){const end=Date.now()+8000;while(Date.now()<end){try{const v=await read();if(ok(v))return v;}catch{}await delay(20);}throw Error('Private API fixture condition timed out');}

test('simultaneous formal starts spawn one runner; killed runner keeps immutable lock and returns interrupted without rerun',async()=>{
 const x=await setup();try{
  const replies=await Promise.all(Array.from({length:12},()=>x.post()));assert.equal(x.children.length,1);assert.ok(replies.every(r=>r.mode==='financial_v05'));
  const lock=path.join(x.folder,'holdout-v05-financial-first-run.lock.json');const original=await until(()=>fs.readFile(lock,'utf8'),s=>s.length>0);
  const end=once(x.children[0],'exit');x.children[0].kill('SIGKILL');await end;
  const result=await until(()=>x.get('/api/benchmark/run/locked-financial_v05'),r=>r.state==='interrupted');assert.equal(result.report.status,'running');
  const repeated=await x.post();assert.equal(repeated.state,'interrupted');assert.equal(x.children.length,1);assert.equal(await fs.readFile(lock,'utf8'),original);
 }finally{await x.close();}
});
test('legacy CLI lock without known live owner is interrupted; completed actual report is authoritative',async()=>{
 const x=await setup();try{
  const output=path.join(x.folder,'cli.json'),lock=path.join(x.folder,'holdout-v05-financial-first-run.lock.json');const raw=JSON.stringify({output,started_at:'2026-01-01T00:00:00Z'});await fs.writeFile(lock,raw);await fs.writeFile(output,JSON.stringify({status:'running'}));
  assert.equal((await x.post()).state,'interrupted');assert.equal(x.children.length,0);
  await fs.writeFile(output,JSON.stringify({status:'passed',checks:[]}));assert.equal((await x.post()).state,'completed');assert.equal(await fs.readFile(lock,'utf8'),raw);assert.equal(x.children.length,0);
 }finally{await x.close();}
});
for(const kind of ['empty','failed'])test(`runner exit code 0 with ${kind} report does not invent a passing result`,async()=>{
 const x=await setup(kind);try{const job=await x.post();const expected=kind==='failed'?'failed':'interrupted';const result=await until(()=>x.get('/api/benchmark/run/'+job.id),r=>r.state===expected);assert.equal(result.state,expected);const locked=await x.post();assert.equal(locked.state,expected);assert.equal(x.children.length,1);}finally{await x.close();}
});
test('a live CLI owner occupies the shared start slot for a different mode',async()=>{
 const x=await setup();try{
  const output=path.join(x.folder,'cli.json');await fs.writeFile(path.join(x.folder,'holdout-v05-financial-first-run.lock.json'),JSON.stringify({output,runner_pid:process.pid,started_at:new Date().toISOString()}));
  const result=await x.post('generic_v05');assert.equal(result.id,'locked-financial_v05');assert.equal(result.state,'running');assert.equal(x.children.length,0);
 }finally{await x.close();}
});
