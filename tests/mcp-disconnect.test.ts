import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtemp} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import path from 'node:path';
import {setTimeout as delay} from 'node:timers/promises';

test('a real private MCP subprocess exit clears connected and rejects later calls',{timeout:45000},async()=>{
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
  const pid=(service as any).transport?.pid;
  assert.ok(Number.isInteger(pid)&&pid>0&&pid!==process.pid);
  process.kill(pid);
  const until=Date.now()+5000;while(service.connected&&Date.now()<until)await delay(25);
  assert.equal(service.connected,false,'worker exit must invalidate the host readiness state');
  await assert.rejects(service.call('list_projects',{}),/文档服务尚未就绪/);
 }finally{await service.close();}
});
