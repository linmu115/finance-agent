/** Real HTTP/Pi/MCP/SQLite persistence with a deterministic provider fixture.
 * No official API calls. Only an isolated temporary DATA directory is restarted.
 */
import fs from 'node:fs/promises';
import path from 'node:path';
import {createServer} from 'node:http';
import {spawn,execFile} from 'node:child_process';
import {promisify} from 'node:util';
import {once} from 'node:events';
import {createHash} from 'node:crypto';
import assert from 'node:assert/strict';
import {setTimeout as delay} from 'node:timers/promises';

const root=path.resolve(import.meta.dirname,'..'),stamp=Date.now();
const output=path.join(root,'benchmark/results/utf8-http-pi-restart-'+stamp+'.json');
const data=await fs.mkdtemp(path.join(root,'tmp/utf8-roundtrip-'));
const report={kind:'isolated_http_pi_utf8_roundtrip',model_provider:'deterministic_local_fixture',official_api_calls:0,started_at:new Date().toISOString(),status:'running',data_dir:data,checks:[]};
await fs.writeFile(output,JSON.stringify(report,null,2),{flag:'wx'});
const company='华𠮷制造,研究\n一期💡',label='资产总额“合并”',filename='华𠮷💡_财报2024.csv';
const csv='项目,2024年12月31日\r\n'+label+',137.25\r\n';
const check=(name,ok,details)=>{report.checks.push({name,status:ok?'passed':'failed',details});assert.ok(ok,name);console.log('PASS',name);};
const digest=value=>createHash('sha256').update(value).digest('hex');
let documentId,host,base,providerCalls=0,holdDefinitions=false;
const heldDefinitions=[];
const text=value=>Array.isArray(value)?value.map(x=>x.text||'').join('\n'):String(value||'');
const mock=createServer(async(req,res)=>{
 try{
 const chunks=[];for await(const chunk of req)chunks.push(Buffer.from(chunk));
 const body=JSON.parse(Buffer.concat(chunks).toString('utf8'));providerCalls++;
 const messages=body.messages,last=text(messages.at(-1)?.content);let delta,finish='stop';
 if(last.includes('[[TEMPORAL_REVIEW]]')){const count=new Set(last.match(/\[\[GROUP:[a-f0-9]+\]\]/g)||[]).size;delta={content:JSON.stringify({extractions:[{temporal_review:'[[TEMPORAL_REVIEW]]',temporal_review_attributes:{reviewed_count:count,flag_count:0,keep_count:count}}]})};}
 else if(last.includes('[[CATALOG]]')){const count=new Set(last.match(/\[\[METRIC:[a-z0-9_]+\]\]/g)||[]).size;delta={content:JSON.stringify({extractions:[{catalog_review:'[[CATALOG]]',catalog_review_attributes:{reviewed_count:count,merge_count:0,keep_count:count,keep_summary:'原指标保留'}}]})};}
 else if(last.includes('财务数据清洗工程师'))delta={content:JSON.stringify({extractions:[{table_schema:'[[T0]]',table_schema_attributes:{company,statement:'balance',scope:'consolidated_CAS',unit:'元',currency:'CNY',columns_json:JSON.stringify([{column:2,period:'2024-12-31',start:'',end:'2024-12-31',unit:'元',currency:'CNY'}])}},{financial_row:'[[T0:R2]]',financial_row_attributes:{metric:'assets',label,unit:'元'}}]})};
 else if(last.includes('[[DEFINITION:')){const markers=[...new Set(last.match(/\[\[DEFINITION:[a-f0-9]{64}\]\]/g)||[])];delta={content:JSON.stringify({extractions:markers.map(marker=>({definition_unresolved:marker,definition_unresolved_attributes:{reason:'本夹具只验证编码持久化，不验证定义推理'}}))})};}
 else if(!messages.some(m=>m.role==='tool')){const review=text(messages.findLast(m=>m.role==='user')?.content).includes('review-shared-fixture');finish='tool_calls';delta={tool_calls:[{index:0,id:'clean-'+providerCalls,type:'function',function:{name:'process_documents',arguments:JSON.stringify({document_ids:[documentId],...(review?{review_existing_only:true,review_metrics:['assets']}:{})})}}]};}
 else delta={content:company+'：'+label+' 137.25元。'};
 if(holdDefinitions&&last.includes('[[DEFINITION:'))await new Promise(resolve=>heldDefinitions.push({resolve,res,body,delta}));
 if(res.destroyed)return;
 res.writeHead(200,{'Content-Type':'text/event-stream'});const envelope={id:'utf8-fixture',object:'chat.completion.chunk',created:1,model:'utf8-fixture'};
 res.write('data: '+JSON.stringify({...envelope,choices:[{index:0,delta:{role:'assistant',...delta},finish_reason:null}]})+'\n\n');
 res.write('data: '+JSON.stringify({...envelope,choices:[{index:0,delta:{},finish_reason:finish}],usage:{prompt_tokens:13,completion_tokens:7,total_tokens:20}})+'\n\n');res.end('data: [DONE]\n\n');
 }catch(error){res.writeHead(500);res.end('fixture failure');}
});
await new Promise(resolve=>mock.listen(0,'127.0.0.1',resolve));
const portProbe=createServer();await new Promise(resolve=>portProbe.listen(0,'127.0.0.1',resolve));const port=portProbe.address().port;await new Promise(resolve=>portProbe.close(resolve));base='http://127.0.0.1:'+port;
async function api(route,body,method){const response=await fetch(base+route,{method:method||(body===undefined?'GET':'POST'),headers:body===undefined||body instanceof FormData?undefined:{'Content-Type':'application/json'},body:body===undefined?undefined:body instanceof FormData?body:JSON.stringify(body),signal:AbortSignal.timeout(15000)});if(!response.ok)throw Error('HTTP '+response.status+' '+route+' '+await response.text());return response;}
async function json(route,body,method){return (await api(route,body,method)).json();}
async function startHost(){
 host=spawn(process.execPath,['--import','tsx','server/main.ts'],{cwd:root,windowsHide:true,env:{...process.env,FINANCE_DATA_DIR:data,FINANCE_PORT:String(port),FINANCE_HOST:'127.0.0.1',FINANCE_LLM_BASE_URL:'http://127.0.0.1:'+mock.address().port+'/v1',FINANCE_LLM_MODEL:'utf8-fixture',FINANCE_LLM_API_KEY:'isolated-fixture-not-secret',PYTHONIOENCODING:'utf-8'},stdio:['ignore','pipe','pipe']});
 let error='';host.stdout.resume();host.stderr.on('data',chunk=>{error+=chunk;});
 const until=Date.now()+30000;while(Date.now()<until){if(host.exitCode!==null)throw Error('Isolated host exited: '+error);try{if((await json('/api/health')).ok)return;}catch{}await delay(150);}throw Error('Isolated host not ready');
}
async function stopHost(){if(!host||host.exitCode!==null)return;const child=host;host=undefined;const closed=once(child,'exit');child.kill();await Promise.race([closed,delay(10000).then(()=>{throw Error('Isolated host did not exit');})]);await delay(700);}
async function waitForCondition(predicate,description){const end=Date.now()+30000;while(Date.now()<end){if(await predicate())return;await delay(50);}throw Error('Timed out: '+description);}
async function parseCsv(value){const child=spawn(path.join(root,'.venv/Scripts/python.exe'),['-c','import csv,io,json,sys; rows=list(csv.DictReader(io.StringIO(sys.stdin.read().lstrip("\\ufeff")))); sys.stdout.write(json.dumps(rows,ensure_ascii=False))'],{cwd:root,windowsHide:true,env:{...process.env,PYTHONIOENCODING:'utf-8'},stdio:['pipe','pipe','pipe']});let out='',err='';child.stdout.setEncoding('utf8');child.stdout.on('data',x=>out+=x);child.stderr.on('data',x=>err+=x);const done=once(child,'exit');child.stdin.end(value);const [code]=await done;if(code)throw Error(err);return JSON.parse(out);}
try{
 await startHost();await json('/api/settings',{llm:{maxTokens:512}},'PUT');
 const project=await json('/api/projects',{name:'中文𠮷💡编码验证'}),chat=await json('/api/projects/'+project.id+'/conversations',{});report.project_id=project.id;report.conversation_id=chat.id;
 const form=new FormData();form.append('files',new Blob([Buffer.from(csv,'utf8')],{type:'text/csv'}),filename);
 const upload=await json('/api/projects/'+project.id+'/uploads',form);documentId=upload.documents[0].id;report.document_id=documentId;
 check('multipart_filename_exact',upload.documents[0].name===filename,{expected:filename,actual:upload.documents[0].name});
 const run=await json('/api/conversations/'+chat.id+'/messages',{content:'请处理这个UTF8夹具，中文与𠮷、💡字符保留。',documentIds:[documentId]});report.run_id=run.runId;
 let state;const until=Date.now()+120000;while(Date.now()<until){state=await json('/api/runs/'+run.runId);if(['completed','failed','cancelled'].includes(state.status))break;await delay(150);}check('real_pi_and_mcp_completed',state?.status==='completed',{status:state?.status,error:state?.error});
 const route='/api/projects/'+project.id+'/financial-data',first=await json(route),exported=await (await api(route+'?format=csv')).text(),rows=await parseCsv(exported);
 check('database_exact_unicode',first.total===1&&first.items[0].company===company&&first.items[0].label===label,{company:first.items[0]?.company,label:first.items[0]?.label});
 check('csv_escaped_multiline_and_unicode',rows.length===1&&rows[0].company===company&&rows[0].label===label,{company:rows[0]?.company,label:rows[0]?.label});
 const original=Buffer.from(await (await api('/api/projects/'+project.id+'/documents/'+documentId+'/file')).arrayBuffer());check('original_bytes_unchanged',digest(original)===digest(Buffer.from(csv)),{sha256:digest(original)});
 const conversation=await json('/api/conversations/'+chat.id);check('conversation_exact_unicode',conversation.messages.at(-1).content===company+'：'+label+' 137.25元。',{answer:conversation.messages.at(-1).content});
 const calls=providerCalls;await stopHost();await startHost();
 const restored=await json(route),restoredCsv=await (await api(route+'?format=csv')).text(),restoredChat=await json('/api/conversations/'+chat.id),doc=await json('/api/projects/'+project.id+'/documents/'+documentId);
 check('restart_preserves_database_exports_chat_and_filename',JSON.stringify(restored)===JSON.stringify(first)&&restoredCsv===exported&&JSON.stringify(restoredChat.messages)===JSON.stringify(conversation.messages)&&doc.name===filename,{provider_calls_before:calls,provider_calls_after:providerCalls});
 check('restart_and_read_make_no_model_calls',providerCalls===calls,{calls});
 check('no_replacement_character',![JSON.stringify(first),exported,JSON.stringify(restoredChat),doc.name].some(value=>value.includes('\ufffd')));
 if(process.argv.includes('--cache-cancel')){
  holdDefinitions=true;
  const chats=await Promise.all([json('/api/projects/'+project.id+'/conversations',{}),json('/api/projects/'+project.id+'/conversations',{})]);
  const a=await json('/api/conversations/'+chats[0].id+'/messages',{content:'review-shared-fixture A',documentIds:[]});
  await waitForCondition(()=>heldDefinitions.length===1,'first private Pi definition inference');
  const b=await json('/api/conversations/'+chats[1].id+'/messages',{content:'review-shared-fixture B',documentIds:[]});
  await waitForCondition(async()=>{const catalog=await json('/api/projects/'+project.id+'/catalog');return catalog.processing?.some(p=>p.owner_run_id===b.runId&&!['completed','failed','cancelled'].includes(p.state));},'second session entering shared review');
  await delay(300);
  check('same_cache_key_has_one_inflight_inference',heldDefinitions.length===1,{held:heldDefinitions.length,owner_run:a.runId,waiter_run:b.runId});
  await json('/api/runs/'+a.runId+'/cancel',{});
  await waitForCondition(()=>heldDefinitions.length===2,'survivor taking over cancelled inference');
  heldDefinitions[1].resolve();
  await waitForCondition(async()=>['completed','failed','cancelled'].includes((await json('/api/runs/'+b.runId)).status),'surviving Pi completion');
  const [aState,bState]=await Promise.all([json('/api/runs/'+a.runId),json('/api/runs/'+b.runId)]);
  check('cancelled_owner_does_not_cancel_waiter',aState.status==='cancelled'&&bState.status==='completed',{a:aState.status,b:bState.status});
  const bAudit=(await fs.readFile(path.join(data,'audit',b.runId+'.jsonl'),'utf8')).trim().split('\n').map(JSON.parse),extracts=bAudit.filter(e=>e.type==='extraction_result');
  check('surviving_private_pi_owns_actual_definition_response',extracts.length===1&&extracts[0].data.content===heldDefinitions[1].delta.content,{run_id:b.runId,extraction_count:extracts.length});
  // The public catalog deliberately returns only a review summary. Audit the
  // persisted report for the owner assertion instead of expecting raw audits
  // to be copied into every catalog response.
  const {stdout}=await promisify(execFile)(path.join(root,'.venv/Scripts/python.exe'),['-c','import json,sqlite3,sys,pathlib; c=sqlite3.connect(pathlib.Path(sys.argv[1]).as_uri()+"?mode=ro",uri=True); rows=[json.loads(r[0]) for r in c.execute("select report_json from fact_definition_reviews")]; print(json.dumps(next(r for r in rows if r["owner_run_id"]==sys.argv[2]),ensure_ascii=False))',path.join(data,'finance.sqlite'),b.runId],{cwd:root,windowsHide:true,env:{...process.env,PYTHONIOENCODING:'utf-8'}});
  const review=JSON.parse(stdout);
  const audits=review?.audits||[];
  check('accepted_definition_cache_records_surviving_owner',audits.length===1&&audits.every(item=>item.provenance?.owner_run_id===b.runId),{review_status:review?.status,audits});
  const after=await json(route);check('cancellation_does_not_duplicate_or_modify_facts',after.total===1&&after.items[0].fact_id===first.items[0].fact_id&&after.items[0].value===first.items[0].value);
  report.cache_cancellation={owner_run:a.runId,survivor_run:b.runId,accepted_audits:audits,limitations:'Controlled model response; unresolved definition is intentional. This checks ownership, not financial semantic accuracy.'};
 }
 report.status='passed';report.provider_fixture_calls=providerCalls;
}catch(error){report.status='failed';report.error=error.stack;process.exitCode=1;console.error(error.message);}
finally{for(const held of heldDefinitions)held.resolve();await stopHost().catch(error=>{report.cleanup_error=error.message;process.exitCode=1;});await new Promise(resolve=>{mock.close(resolve);mock.closeAllConnections();});report.finished_at=new Date().toISOString();await fs.writeFile(output,JSON.stringify(report,null,2));console.log('REPORT',output);}
