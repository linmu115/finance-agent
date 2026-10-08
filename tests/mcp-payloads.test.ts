import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtemp,writeFile,readFile} from 'node:fs/promises';
import path from 'node:path';
import {tmpdir} from 'node:os';
import {PayloadTransport,MCP_INLINE_BYTES} from '../server/mcp-payloads.js';

test('large requests use complete handles; one broken response leaves concurrent responses connected',async()=>{
 const root=await mkdtemp(path.join(tmpdir(),'finance-payload-'));
 const sent:any[]=[],received:any[]=[];let closed=false;
 const inner:any={start:async()=>{},close:async()=>{closed=true;},send:async(m:any)=>{sent.push(m);}};
 const transport=new PayloadTransport(inner,root);transport.onmessage=m=>received.push(m);await transport.start();
 const request:any={jsonrpc:'2.0',id:9,method:'tools/call',params:{name:'render_answer',arguments:{body:'中'.repeat(4_000_000)},_meta:{finance_evaluation_isolation_key:'private'}}};
 await transport.send(request);
 assert.ok(Buffer.byteLength(JSON.stringify(sent[0]))<MCP_INLINE_BYTES);
 assert.deepEqual(JSON.parse(await readFile(path.join(root,'.mcp-payloads',sent[0].params._finance_payload+'.json'),'utf8')),request);
 const handle='a'.repeat(32),large={jsonrpc:'2.0',id:2,result:{body:'正文'.repeat(6_000_000)}};
 await writeFile(path.join(root,'.mcp-payloads',handle+'.json'),JSON.stringify(large));
 const completed=new Promise<void>(resolve=>{transport.onmessage=m=>{received.push(m);if(received.length===3)resolve();};});
 inner.onmessage({jsonrpc:'2.0',id:1,result:{_finance_payload:'b'.repeat(32)}});
 inner.onmessage({jsonrpc:'2.0',id:2,result:{_finance_payload:handle}});
 inner.onmessage({jsonrpc:'2.0',id:3,result:{ok:true}});
 await completed;
 assert.match(received.find(x=>x.id===1).error.message,/MCP_PAYLOAD_READ_FAILED/);
 assert.deepEqual(received.find(x=>x.id===2),large);assert.deepEqual(received.find(x=>x.id===3).result,{ok:true});
 assert.equal(closed,false);
});
