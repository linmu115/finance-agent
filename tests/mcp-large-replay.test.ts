import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtemp,mkdir,writeFile,readFile,readdir} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import path from 'node:path';
import {createHash} from 'node:crypto';
import {Client} from '@modelcontextprotocol/sdk/client/index.js';
import {StdioClientTransport} from '@modelcontextprotocol/sdk/client/stdio.js';
import {PayloadTransport,MCP_INLINE_BYTES} from '../server/mcp-payloads.js';

test('7.22 MB and 32 MiB downloads are metadata-only; full model reads use handles alongside concurrent reads',{timeout:90000},async()=>{
 const root=await mkdtemp(path.join(tmpdir(),'finance-large-download-'));process.env.FINANCE_DATA_DIR=root;
 const {FinanceService}=await import('../server/mcp.js');const {deliveryFile}=await import('../server/research-artifacts.js');
 const service=new FinanceService();const wireSizes:number[]=[],calls:string[]=[];
 try{
  await service.connect();await service.call('create_project',{project_id:'p',name:'synthetic'});
  const raw=(service as any).transport.inner,prior=raw.onmessage;
  raw.onmessage=(m:any,e:any)=>{wireSizes.push(Buffer.byteLength(JSON.stringify(m)+'\n'));prior(m,e);};
  let breakNextHandle=false;
  const send=raw.send.bind(raw);raw.send=(m:any)=>{
   if(breakNextHandle&&m.params?._finance_payload){breakNextHandle=false;m={...m,params:{_finance_payload:'f'.repeat(32)}};}
   wireSizes.push(Buffer.byteLength(JSON.stringify(m)+'\n'));return send(m);
  };
  const value={text:'中'.repeat(900_000)};
  await service.putState('p','runs','large-request',value);
  assert.deepEqual(await service.getState('p','runs','large-request'),value);
  const originalPid=raw.pid;
  breakNextHandle=true;
  const [broken,concurrent]=await Promise.allSettled([service.putState('p','runs','missing-payload',value),service.call('list_projects',{})]);
  assert.equal(broken.status,'rejected');assert.equal((broken as PromiseRejectedResult).reason.code,'MCP_REQUEST_UNAVAILABLE',String((broken as PromiseRejectedResult).reason));
  assert.equal(concurrent.status,'fulfilled');assert.equal(await service.getState('p','runs','missing-payload'),undefined);
  await assert.rejects(service.call('get_artifact_metadata',{project_id:'other',run_id:'missing',name:'private.json'}));
  assert.equal((service as any).transport.inner.pid,originalPid,'business errors do not restart the worker');
  const call=service.call.bind(service);service.call=async(name,args,signal)=>{calls.push(name);return call(name,args,signal);};
  for(const size of [7_221_871,32*1024*1024]){
   const id=(size===7_221_871?'1':'2').repeat(32),folder=path.join(root,'research','p','deliveries',id);await mkdir(folder,{recursive:true});
   const bytes=Buffer.from(JSON.stringify({text:'x'.repeat(size-11)}));assert.equal(bytes.length,size);
   await writeFile(path.join(folder,'chart_data.json'),bytes);
   await writeFile(path.join(folder,'delivery.json'),JSON.stringify({files:[{name:'chart_data.json',size,sha256:createHash('sha256').update(bytes).digest('hex')}]}));
   const meta=await service.call('get_artifact_metadata',{project_id:'p',run_id:id,name:'chart_data.json'});assert.equal(meta.data.content,undefined);
   const download=await deliveryFile('p',id,'chart_data.json',service);assert.deepEqual(download.bytes,bytes);
   assert.equal(calls.at(-1),'get_artifact_metadata');
   const [large,other]=await Promise.all([service.call('get_artifact',{project_id:'p',run_id:id,name:'chart_data.json'}),service.call('list_projects',{})]);
   assert.equal(large.data.content.text.length,size-11);assert.equal(other.status,'ok');assert.equal(service.connected,true);
  }
  assert.ok(Math.max(...wireSizes)<MCP_INLINE_BYTES);
  assert.ok((await readdir(path.join(root,'.mcp-payloads'))).length>=2);
 }finally{await service.close();}
});

test('real Yili/Haier maxima across three profiles traverse the actual SDK losslessly',{skip:!process.env.MCP_REAL_CASES,timeout:90000},async()=>{
 const root=await mkdtemp(path.join(tmpdir(),'finance-real-mcp-')),cases=process.env.MCP_REAL_CASES!;
 const raw=new StdioClientTransport({command:process.env.FINANCE_PYTHON!,args:['tests/fixtures/mcp-large-child.py'],cwd:process.cwd(),env:{...process.env as Record<string,string>,FINANCE_DATA_DIR:root,PYTHONPATH:process.cwd(),PYTHONIOENCODING:'utf-8'},stderr:'pipe'});
 raw.stderr?.on('data',()=>{});
 const transport=new PayloadTransport(raw,root),client=new Client({name:'offline-mcp-replay',version:'1'}),wireSizes:number[]=[];
 const prior=raw.onmessage;raw.onmessage=(m,e)=>{wireSizes.push(Buffer.byteLength(JSON.stringify(m)+'\n'));prior?.(m,e);};
 try{
  await client.connect(transport);
  const names=(await readdir(cases)).filter(n=>n.endsWith('.json'));
  const evidence=[];
  for(const name of names){
   const expected=JSON.parse(await readFile(path.join(cases,name),'utf8')).result;
   const actual=await client.callTool({name:'get_replay',arguments:{case:name}});
   assert.deepEqual(actual,expected,name);evidence.push({case:name,equal:true,originalBytes:Buffer.byteLength(JSON.stringify(expected))});
  }
  assert.ok(Math.max(...wireSizes)<MCP_INLINE_BYTES);
  if(process.env.MCP_REPLAY_EVIDENCE)await writeFile(process.env.MCP_REPLAY_EVIDENCE,JSON.stringify({cases:evidence,maxWireBytes:Math.max(...wireSizes),paidCalls:0},null,2)+'\n');
 }finally{await client.close();}
});
