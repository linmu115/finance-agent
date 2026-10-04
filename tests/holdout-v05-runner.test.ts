import test from 'node:test';
import assert from 'node:assert/strict';
import http from 'node:http';
import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
// @ts-expect-error Isolated host runner.
import {runHoldoutV05,compareExportedFacts} from '../scripts/verify_holdout_v05.mjs';

test('v05 mock shared-budget cancellation stops both chats and first-run lock prevents another request',async()=>{
 const temp=await fs.mkdtemp(path.join(os.tmpdir(),'finance-v05-runner-')),runs=new Map<string,any>(),chats=new Map<string,any>();let requests=0,uploads=0,cancelled=0;
 const server=http.createServer(async(req,res)=>{
  requests++;const buffers=[];for await(const chunk of req)buffers.push(chunk);const body=Buffer.concat(buffers).toString('utf8'),url=new URL(req.url||'/', 'http://mock');
  const send=(data:any,status=200)=>{res.writeHead(status,{'content-type':'application/json'});res.end(JSON.stringify(data));};
  if(url.pathname==='/api/settings')return send({llm:{hasKey:true,baseUrl:'https://api.deepseek.com',model:'mock-only',contextWindow:128000,maxTokens:8192},runtime:{maxToolCalls:24}});
  if(url.pathname==='/api/projects')return send({id:'isolated-mock-project'});
  if(url.pathname.endsWith('/conversations')&&req.method==='POST'){const id='chat-'+chats.size;const chat={id,messages:[]};chats.set(id,chat);return send(chat);}
  if(url.pathname.endsWith('/uploads'))return send({documents:[{id:'document-'+(++uploads)}]});
  if(url.pathname.includes('/financial-data'))return send({items:[],total:0,limit:200,offset:0});
  if(url.pathname.endsWith('/messages')){
   const chatId=url.pathname.split('/')[3],input=JSON.parse(body);assert.equal(input.evaluation.profile,'generic');assert.ok(!body.includes('glyph_bbox'));assert.ok(!body.includes('decidable_cells'));
   const id='mock-run-'+runs.size;const run={id,conversationId:chatId,status:'running',stage:'mock',usage:{calls:41,input:100,output:20},evaluation:input.evaluation};runs.set(id,run);
   chats.get(chatId).messages.push({id:'assistant-'+id,role:'assistant',runId:id,content:'mock terminal text',artifacts:[]});return send({runId:id});
  }
  if(url.pathname.startsWith('/api/runs/')){const id=url.pathname.split('/')[3],run=runs.get(id);if(url.pathname.endsWith('/cancel')){run.status='cancelled';cancelled++;}return send(run);}
  if(url.pathname.startsWith('/api/conversations/'))return send(chats.get(url.pathname.split('/')[3]));
  send({error:'unhandled mock path'},404);
 });
 await new Promise<void>(resolve=>server.listen(0,'127.0.0.1',resolve));
 try{
  const port=(server.address() as any).port,args=['--profile','generic','--base-url','http://127.0.0.1:'+port,'--output',path.join(temp,'report.json'),'--job-id','isolated-mock'];
  const harness={lockPath:path.join(temp,'first-run.lock.json'),auditReader:async()=>[]};
  const report=await runHoldoutV05(args,harness);assert.equal(report.kind,'isolated_mock_runner_test');assert.equal(report.status,'failed');assert.equal(cancelled,2);assert.equal(report.budget.actual.model_calls,82);assert.ok(report.cancellations.every((c:any)=>c.initiator==='benchmark_runner'));
  const saved=await fs.readFile(path.join(temp,'report.json'),'utf8'),before=requests;const repeated=await runHoldoutV05(args,harness);assert.equal(repeated.already_started,true);assert.equal(requests,before);assert.equal(await fs.readFile(path.join(temp,'report.json'),'utf8'),saved);
 }finally{await new Promise<void>(resolve=>server.close(()=>resolve()));assert.equal(path.dirname(path.resolve(temp)),path.resolve(os.tmpdir()));assert.ok(path.basename(temp).startsWith('finance-v05-runner-'));await fs.rm(temp,{recursive:true,force:true});}
});

test('export agreement checks exact values, units, periods, source and multiplicity rather than just row count',()=>{
 const fact={metric:'revenue',value:'9007199254740992.01',raw_value:'9007199254740992.01',currency:'CNY',period:'2025',source_ref:{document_id:'d',page:1,bbox:[1,2,3,4]}};
 assert.equal(compareExportedFacts([fact],[structuredClone(fact)]).status,'passed');
 for(const patch of [{value:'9007199254740992.02'},{currency:'USD'},{period:'2024'},{source_ref:{...fact.source_ref,page:2}}])assert.equal(compareExportedFacts([fact],[{...fact,...patch}]).status,'failed');
 assert.equal(compareExportedFacts([fact],[fact,fact]).unexpected_or_changed,1);
});
