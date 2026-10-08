import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtemp} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import path from 'node:path';
import {setTimeout as delay} from 'node:timers/promises';

test('a private MCP exit reconnects once and concurrent reads continue; explicit close stays closed',{timeout:60000},async()=>{
 const dir=await mkdtemp(path.join(tmpdir(),'finance-mcp-disconnect-'));
 process.env.FINANCE_DATA_DIR=dir;
 const {loadSettings}=await import('../server/config.js');
 const {FinanceService}=await import('../server/mcp.js');
 await loadSettings();
 const service=new FinanceService();
 try{
  assert.equal(service.connected,false);
  await service.connect();assert.equal(service.connected,true);
  await service.call('list_projects',{});
  // This PID comes from this test's own transport, never from an app PID file.
  const pid=(service as any).transport?.inner?.pid;
  assert.ok(Number.isInteger(pid)&&pid>0&&pid!==process.pid);
  process.kill(pid);
  const until=Date.now()+5000;while(service.connected&&Date.now()<until)await delay(25);
  assert.equal(service.connected,false,'worker exit must invalidate the host readiness state');
  const results=await Promise.all([service.call('list_projects',{}),service.call('list_projects',{}),service.tools()]);
  assert.equal(results[0].status,'ok');assert.equal(results[1].status,'ok');assert.ok(results[2].length);
  assert.equal(service.connected,true);assert.notEqual((service as any).transport.inner.pid,pid);
  // All three callers are already awaiting the same lost connection. Reconnect
  // replays reads once, while an uncertain mutation is never submitted again.
  const old=service.client;let entered=0,release!:()=>void,allEntered!:()=>void;
  const gate=new Promise<void>(r=>{release=r;}),entry=new Promise<void>(r=>{allEntered=r;});
  old.callTool=async()=>{if(++entered===3)allEntered();await gate;throw Object.assign(new Error('Connection closed'),{code:-32000});};
  const pending=Promise.allSettled([service.call('list_projects',{}),service.call('list_projects',{}),service.call('start_document_processing',{project_id:'absent'})]);
  await entry;await old.close();release();const resultsAfterLoss=await pending;
  assert.deepEqual(resultsAfterLoss.map(r=>r.status),['fulfilled','fulfilled','rejected']);
  assert.equal((resultsAfterLoss[2] as PromiseRejectedResult).reason.code,'MCP_RESULT_UNKNOWN');
  assert.equal(service.connected,true);
  await service.close();await assert.rejects(service.call('list_projects',{}),/文档服务已关闭/);
 }finally{await service.close();}
});
