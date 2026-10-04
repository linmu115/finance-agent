import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import http from 'node:http';
import {createHash} from 'node:crypto';
// @ts-expect-error independent host runner
import {runReportCorrection} from '../scripts/verify_report_correction_v01.mjs';

test('correction runner uses normal chat/artifact contract once and never sends host gold',async()=>{
 const folder=await fs.mkdtemp(path.join(os.tmpdir(),'correction-runner-fixture-')),output=path.join(folder,'result.json'),lockPath=path.join(folder,'lock.json');
 let requests=0,evaluation:any,sent:any;
 const app=http.createServer(async(req,res)=>{
  requests++;const chunks=[];for await(const c of req)chunks.push(c);const body=Buffer.concat(chunks).toString('utf8');
  const route=new URL(req.url!,'http://fixture').pathname;res.setHeader('Content-Type','application/json');let result:any;
  if(route==='/api/settings')result={llm:{baseUrl:'https://api.deepseek.com',model:'fixed-fixture',hasKey:true},runtime:{}};
  else if(route==='/api/projects')result={id:'fixture-project'};
  else if(route==='/api/projects/fixture-project/conversations')result={id:'fixture-chat'};
  else if(route==='/api/projects/fixture-project/uploads')result={documents:[{id:'fixture-document'}]};
  else if(route==='/api/conversations/fixture-chat/messages'){sent=JSON.parse(body);evaluation=sent.evaluation;result={runId:'fixture-run'};}
  else if(route==='/api/runs/fixture-run')result={id:'fixture-run',conversationId:'fixture-chat',status:'completed',evaluation,usage:{calls:1,input:20,output:30}};
  else if(route==='/api/conversations/fixture-chat')result={id:'fixture-chat',messages:[{id:'fixture-answer',role:'assistant',runId:'fixture-run',content:'fixture intentionally submits no correction artifact',artifacts:[]}]};
  else{res.statusCode=404;result={error:'unexpected path'};}
  res.end(JSON.stringify(result));
 });
 await new Promise<void>(resolve=>app.listen(0,'127.0.0.1',resolve));const address=app.address() as any;
 try{
  const args=['--base-url','http://127.0.0.1:'+address.port,'--output',output,'--job-id','fixture'];
  const report=await runReportCorrection(args,{lockPath,auditReader:async()=>[]});
  assert.equal(report.kind,'isolated_mock_runner_test');assert.equal(report.status,'failed');assert.equal(report.score.true_corrections,0);assert.equal(report.score.expected_errors,12);
  assert.equal(sent.documentIds[0],'fixture-document');assert.equal(sent.evaluation.profile,'financial');
  assert.ok(sent.content.includes('待审原文：'));assert.ok(!sent.content.includes('accepted_replacements'));assert.ok(!sent.content.includes('planted_errors'));assert.ok(!sent.content.includes('植入错误'));
  const digest=async()=>createHash('sha256').update(await fs.readFile(output)).digest('hex'),before=await digest(),count=requests;
  const again=await runReportCorrection(args,{lockPath,auditReader:async()=>[]});assert.equal(again.already_started,true);assert.equal(requests,count);assert.equal(await digest(),before);
 }finally{
  await new Promise<void>(resolve=>app.close(()=>resolve()));
  assert.equal(path.dirname(folder),path.resolve(os.tmpdir()));assert.ok(path.basename(folder).startsWith('correction-runner-fixture-'));await fs.rm(folder,{recursive:true});
 }
});
