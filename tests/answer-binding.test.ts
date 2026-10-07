import test from 'node:test';
import assert from 'node:assert/strict';
import {createServer} from 'node:http';
import {mkdtemp,readFile} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import path from 'node:path';
import {randomUUID} from 'node:crypto';
import {setTimeout as delay} from 'node:timers/promises';

test('Pi replaces answers before persistence, later tables win, and bad references get one native repair turn',{timeout:60000},async()=>{
 const dir=await mkdtemp(path.join(tmpdir(),'finance-answer-binding-'));process.env.FINANCE_DATA_DIR=dir;
 const {loadSettings,saveSettings}=await import('../server/config.js');
 const {FinanceService}=await import('../server/mcp.js');const {RunManager}=await import('../server/runs.js');
 await loadSettings();const service=new FinanceService();await service.connect();const manager=new RunManager(service);
 const original=service.call.bind(service);let calls=0;const bodies:any[]=[];
 service.call=async(name,args,signal)=>{
  if(name==='get_analysis_status')return {status:'ok',data:{run_id:args.run_id,status:'succeeded',artifacts:[],numeric_tables:{forecast:{columns:{year:{},price:{unit:'元/股',currency:'HKD',decimals:2}},rows:[{year:'2025E',price:args.run_id==='old'?'12.0715486':'11.2304285827'}],row_keys:['2025E']}}}};
  return original(name,args,signal);
 };
 const mock=createServer(async(req,res)=>{
  let raw='';for await(const chunk of req)raw+=chunk;const body=JSON.parse(raw);bodies.push(body);calls++;
  const content=calls<3?undefined:calls===3?'值 {{forecast.missing.price}}':'值 {{forecast.2025E.price}}\n\n{{table:forecast}}';
  const delta=calls<3?{tool_calls:[{index:0,id:'tool-'+calls,type:'function',function:{name:'get_analysis_status',arguments:JSON.stringify({run_id:calls===1?'old':'new'})}}]}:{content};
  const envelope={id:'mock',object:'chat.completion.chunk',created:1,model:'binding-mock'};
  res.writeHead(200,{'Content-Type':'text/event-stream'});res.write('data: '+JSON.stringify({...envelope,choices:[{index:0,delta:{role:'assistant',...delta},finish_reason:null}]})+'\n\n');
  res.end('data: '+JSON.stringify({...envelope,choices:[{index:0,delta:{},finish_reason:calls<3?'tool_calls':'stop'}],usage:{prompt_tokens:30,completion_tokens:10,total_tokens:40}})+'\n\ndata: [DONE]\n\n');
 });
 await new Promise<void>(r=>mock.listen(0,'127.0.0.1',r));
 try{
  await saveSettings({llm:{baseUrl:'http://127.0.0.1:'+(mock.address() as any).port+'/v1',model:'binding-mock',apiKey:'fixture',contextWindow:16000,maxTokens:1024}});
  await service.call('create_project',{project_id:'binding',name:'Binding'});
  const chat:any={id:randomUUID(),projectId:'binding',title:'Binding',messages:[],createdAt:new Date().toISOString(),updatedAt:new Date().toISOString(),evaluationProfile:'prepared'};
  await service.putState('binding','conversations',chat.id,chat);manager.indexConversation(chat.id,'binding');
  const run=await manager.start(chat,'Read old and new tables and cite the latest.',[],undefined,{profile:'prepared',budget_group_id:'binding-fixture',budget:{max_model_calls:10,max_input_tokens:100000,max_output_tokens:10000,max_total_tokens:110000,max_wall_seconds:50}});
  let state;do{await delay(40);state=await manager.getRun(run.id);}while(['queued','running'].includes(state.status)||manager.activeFor(chat.id));
  assert.equal(state.status,'completed',state.error);assert.equal(calls,4);
  assert.ok(JSON.stringify(bodies[3]).includes('可用行键'));
  const answer=(await manager.getConversation(chat.id)).messages.at(-1)!.content;
  assert.ok(answer.includes('11.23 HKD 元/股'));assert.ok(answer.includes('| 2025E | 11.23 |'));assert.ok(!answer.includes('{{'));
  const native=(await readFile(path.join(dir,'workspaces/binding',chat.id,'sessions/session.jsonl'),'utf8')).split('\n').filter(Boolean).map(x=>JSON.parse(x));
  const final=native.findLast(x=>x.type==='message'&&x.message?.role==='assistant');
  assert.equal(final.message.content.filter((b:any)=>b.type==='text').map((b:any)=>b.text).join(''),answer);
  const audit=await readFile(path.join(dir,'audit',run.id+'.jsonl'),'utf8');assert.equal(audit.split('\n').filter(x=>x.includes('"type":"answer_binding_error"')).length,1);
 }finally{await manager.shutdown();await service.close();await new Promise<void>(r=>mock.close(()=>r()));}
});
