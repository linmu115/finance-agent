import test from 'node:test';
import assert from 'node:assert/strict';
import { createServer } from 'node:http';
import { mkdtemp, readFile, mkdir } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { randomUUID } from 'node:crypto';
import { setTimeout as delay } from 'node:timers/promises';

test('Pi SDK + real MCP service: tool execution, persistence, isolation and encrypted settings', {timeout:180000}, async()=>{
 const dir=await mkdtemp(path.join(tmpdir(),'finance-integration-'));
 process.env.FINANCE_DATA_DIR=dir;
 const {loadSettings,saveSettings,publicSettings,getSettings}=await import('../server/config.js');
 const {FinanceService}=await import('../server/mcp.js');
 const {RunManager}=await import('../server/runs.js');
 await loadSettings();
 const service=new FinanceService();await service.connect();
 const requests:any[]=[];
 const mock=createServer(async(req,res)=>{
   if(req.url!=='/v1/chat/completions'){res.writeHead(404);res.end();return;}
   let raw='';for await(const chunk of req)raw+=chunk;
   const body=JSON.parse(raw);requests.push(body);
   const toolMessage=body.messages.findLast((m:any)=>m.role==='tool');
   const response=toolMessage?{content:'实测计算结果为 '+JSON.parse(toolMessage.content).data.value+'。'}:
     {tool_calls:[{index:0,id:'calc-1',type:'function',function:{name:'calculate_financial_metrics',arguments:JSON.stringify({operation:'divide',inputs:{a:'12',b:'3'}})}}]};
   res.writeHead(200,{'Content-Type':'text/event-stream'});
   res.write('data: '+JSON.stringify({id:'mock-'+requests.length,object:'chat.completion.chunk',created:Math.floor(Date.now()/1000),model:'integration-mock',choices:[{index:0,delta:{role:'assistant',...response},finish_reason:null}]})+'\n\n');
   res.write('data: '+JSON.stringify({id:'mock-'+requests.length,object:'chat.completion.chunk',created:Math.floor(Date.now()/1000),model:'integration-mock',choices:[{index:0,delta:{},finish_reason:toolMessage?'stop':'tool_calls'}],usage:{prompt_tokens:100,completion_tokens:20,total_tokens:120}})+'\n\n');
   res.end('data: [DONE]\n\n');
 });
 await new Promise<void>(r=>mock.listen(0,'127.0.0.1',r));
 const port=(mock.address() as any).port;
 const manager=new RunManager(service);
 try{
   await saveSettings({llm:{baseUrl:'http://127.0.0.1:'+port+'/v1',model:'integration-mock',apiKey:'TEST-ONLY-API-KEY',contextWindow:16384,maxTokens:1024}});
   assert.equal((publicSettings().llm as any).apiKey,undefined);
   assert.equal(publicSettings().llm.hasKey,true);
   assert.ok(!(await readFile(path.join(dir,'settings.json'),'utf8')).includes('TEST-ONLY-API-KEY'));
   await loadSettings();assert.equal(getSettings().llm.apiKey,'TEST-ONLY-API-KEY');
   await service.call('create_project',{project_id:'test',name:'Integration'});
   const now=new Date().toISOString(),chat={id:randomUUID(),projectId:'test',title:'新对话',messages:[],createdAt:now,updatedAt:now};
   await service.putState('test','conversations',chat.id,chat);manager.indexConversation(chat.id,'test');
   const run=await manager.start(chat,'请使用工具计算12除以3。',[]);
   const deadline=Date.now()+60000;
   while(!['completed','failed','cancelled'].includes((await manager.getRun(run.id)).status)){
    if(Date.now()>deadline)throw new Error('Pi integration did not finish');
    await delay(100);
   }
   await delay(400);
   const actual=await manager.getRun(run.id),stored=await manager.getConversation(chat.id);
   assert.equal(actual.status,'completed',actual.error);
   assert.equal(stored.messages.at(-1)?.content,'实测计算结果为 4。');
   assert.ok(actual.tools.some(t=>t.name==='calculate_financial_metrics'&&t.status==='completed'));
   assert.equal(actual.usage.calls,2);
   assert.equal(actual.usage.costUsd,null);
   assert.equal(requests.length,2);
   for(const request of requests){
    const names=request.tools.map((t:any)=>t.function.name);
    assert.ok(!names.some((n:string)=>['bash','read','write','edit','codemode','powershell','ingest_document','list_projects','get_app_state'].includes(n)));
    for(const tool of request.tools)assert.ok(!('project_id' in tool.function.parameters.properties));
    assert.equal(request.max_tokens,1024);
   }
   const audit=await readFile(path.join(dir,'audit',run.id+'.jsonl'),'utf8');
   assert.ok(audit.includes('tool_request'));assert.ok(audit.includes('tool_result'));assert.ok(!audit.includes('TEST-ONLY-API-KEY'));
   await assert.rejects(service.call('get_app_state',{project_id:'unknown',kind:'conversations',key:chat.id}));
 }finally{await manager.shutdown();await service.close();await new Promise<void>(r=>mock.close(()=>r()));}
});
