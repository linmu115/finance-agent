import { test } from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, mkdir, rm, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { setTimeout as delay } from 'node:timers/promises';

test('real MCP database receives nothing before UI approval; HTTP rejection, approval and abort are enforced',async()=>{
 const dir=await mkdtemp(path.join(tmpdir(),'finance-authorized-'));process.env.FINANCE_DATA_DIR=dir;
 await mkdir(path.join(dir,'audit'));
 const [{default:express},{FinanceService},{RunManager},{installProjectApi}]=await Promise.all([import('express'),import('../server/mcp.js'),import('../server/runs.js'),import('../server/project-api.js')]);
 const service=new FinanceService();await service.connect();const manager=new RunManager(service);
 await service.call('create_project',{project_id:'a',name:'授权集成测试'});
 let executions=0;const original=service.call.bind(service);
 (service as any).call=(name:string,args:any,...rest:any[])=>{if(name==='execute_authorized_database_operation')executions++;return original(name,args,...rest);};
 const app=express();app.use(express.json());installProjectApi(app,service,manager,async x=>x);app.use((e:any,_req:any,res:any,_next:any)=>res.status(e.status||400).json({error:e.message}));
 const server=app.listen(0,'127.0.0.1');await new Promise<void>(r=>server.once('listening',r));const url='http://127.0.0.1:'+(server.address() as any).port;
 let n=0;const live=()=>({run:{id:'test'+(++n),projectId:'a'},chat:{id:'chat'},controller:new AbortController(),clients:new Set(),events:[],auditQueue:Promise.resolve()});
 const pending=async()=>{for(let i=0;i<100;i++){const list=await (await fetch(url+'/api/approvals')).json() as any;if(list.requests.length)return list.requests[0];await delay(10);}throw new Error('approval not published');};
 const decide=(a:any,allow:boolean)=>fetch(url+'/api/approvals/'+a.id,{method:'POST',headers:{'Content-Type':'application/json',Origin:url},body:JSON.stringify({digest:a.digest,allow})});
 try{
  const l1=live();const operation=(manager as any).databaseOperation(l1,{operation:'sql',reason:'验收自定义表',sql:'CREATE TABLE approved_table (value TEXT)'});const a=await pending();assert.equal(executions,0);assert.equal(a.operation.current_project,'授权集成测试');
  assert.equal((await fetch(url+'/api/approvals/'+a.id,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({digest:a.digest,allow:true})})).status,403);assert.equal(executions,0);
  assert.equal((await decide(a,true)).status,200);await operation;assert.equal(executions,1);assert.equal((await decide(a,true)).status,409);await l1.auditQueue;
  const l2=live(),rejected=(manager as any).databaseOperation(l2,{operation:'sql',reason:'拒绝示例',sql:'DROP TABLE approved_table'});const rejection=assert.rejects(rejected,/未授权/);const b=await pending();await decide(b,false);await rejection;assert.equal(executions,1);await l2.auditQueue;
  const l3=live(),cancelled=(manager as any).databaseOperation(l3,{operation:'sql',reason:'取消示例',sql:'DROP TABLE approved_table'});const cancellation=assert.rejects(cancelled,/停止/);await pending();l3.controller.abort();await cancellation;assert.equal(executions,1);await l3.auditQueue;
  // Analysis artifacts are frozen before the popup; edits while waiting cannot change authorized SQL.
  const artifactFile=path.join(dir,'changes.json');await writeFile(artifactFile,JSON.stringify({commands:[{sql:'INSERT INTO approved_table VALUES(?)',parameters:['approved bytes']}]}));
  (service as any).call=async(name:string,args:any,...rest:any[])=>{if(name==='get_artifact')return {data:{relative_path:'changes.json'}};if(name==='execute_authorized_database_operation')executions++;return original(name,args,...rest);};
  const l4=live(),written=(manager as any).databaseOperation(l4,{operation:'analysis_changes',reason:'分析写入',analysis_run_id:'sandbox-run'});const c=await pending();await writeFile(artifactFile,JSON.stringify({commands:[{sql:'DROP TABLE approved_table'}]}));await decide(c,true);await written;await l4.auditQueue;
  const l5=live(),read=(manager as any).databaseOperation(l5,{operation:'sql',reason:'验证批准内容',sql:'SELECT * FROM approved_table'});const d=await pending();await decide(d,true);const result=await read;assert.equal(result.data.results[0].rows[0].value,'approved bytes');await l5.auditQueue;
 }finally{await manager.shutdown();await service.close();await new Promise<void>(r=>server.close(()=>r()));await rm(dir,{recursive:true,force:true});}
});
