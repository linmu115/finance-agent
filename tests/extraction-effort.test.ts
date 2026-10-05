import test from 'node:test';
import assert from 'node:assert/strict';
import {createServer} from 'node:http';
import type {AddressInfo} from 'node:net';
import {ModelRuntime} from '@earendil-works/pi-coding-agent';
import {InMemoryCredentialStore} from '@earendil-works/pi-ai';
import {extractionEffort,extractionReasoning} from '../server/reasoning-routing.js';

test('private bridge floors legacy off/none to low in actual DeepSeek payloads',async()=>{
 const payloads:any[]=[];
 const server=createServer(async(req,res)=>{
  const chunks=[];for await(const chunk of req)chunks.push(chunk);
  payloads.push(JSON.parse(Buffer.concat(chunks).toString()));
  res.writeHead(200,{'Content-Type':'text/event-stream'});
  res.end('data: '+JSON.stringify({id:'test',object:'chat.completion.chunk',model:'fixture',choices:[{index:0,delta:{role:'assistant',content:'{}'},finish_reason:'stop'}],usage:{prompt_tokens:3,completion_tokens:2,total_tokens:5}})+'\n\ndata: [DONE]\n\n');
 });
 await new Promise<void>(resolve=>server.listen(0,'127.0.0.1',resolve));
 try{
  const runtime=await ModelRuntime.create({credentials:new InMemoryCredentialStore(),modelsPath:null,allowModelNetwork:false,refreshOnCreate:false});
  runtime.registerProvider('fixture',{baseUrl:`http://127.0.0.1:${(server.address() as AddressInfo).port}/v1`,api:'openai-completions',models:[{id:'fixture',name:'fixture',reasoning:true,input:['text'],contextWindow:100000,maxTokens:32768,cost:{input:0,output:0,cacheRead:0,cacheWrite:0},compat:{thinkingFormat:'deepseek',supportsReasoningEffort:true,supportsStore:false,supportsDeveloperRole:false,maxTokensField:'max_tokens'}}]});
  await runtime.setRuntimeApiKey('fixture','test');
  const model=runtime.getModel('fixture','fixture')!;
  for(const requested of ['none','off',undefined,'low','high']){
   const result=await runtime.completeSimple(model,{messages:[{role:'user',content:'test',timestamp:Date.now()}]},{reasoning:extractionReasoning(extractionEffort(requested)),maxTokens:128});
   assert.equal(result.stopReason,'stop');
  }
  assert.deepEqual(payloads.map(p=>p.thinking),Array.from({length:5},()=>({type:'enabled'})));
  assert.deepEqual(payloads.map(p=>p.reasoning_effort),['low','low','low','low','high']);
  assert.equal(extractionEffort(undefined),'low');
 }finally{await new Promise<void>(resolve=>server.close(()=>resolve()));server.closeAllConnections();}
});
