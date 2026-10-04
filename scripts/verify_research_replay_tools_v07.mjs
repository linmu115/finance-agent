/** Zero-provider evidence/decimal-tool replay of an already archived official page.
 * Uses the production ResearchStore reader and production MCP calculator in private DATA.
 * This is not a new Pi/LLM research test and never edits an old report or live project.
 */
import fs from 'node:fs/promises';
import path from 'node:path';
import assert from 'node:assert/strict';
import {execFile} from 'node:child_process';
import {promisify} from 'node:util';
import {setTimeout as delay} from 'node:timers/promises';
import http from 'node:http';
import https from 'node:https';
import net from 'node:net';
import {Client} from '@modelcontextprotocol/sdk/client/index.js';
import {StdioClientTransport} from '@modelcontextprotocol/sdk/client/stdio.js';
import {digest,stableJson} from './validation_utils.mjs';

const root=path.resolve(import.meta.dirname,'..'),stamp=Date.now();
const prefix=path.join(root,'benchmark/results/research-replay-tools-v07-'+stamp);
await fs.mkdir(path.join(root,'tmp'),{recursive:true});
const data=await fs.mkdtemp(path.join(root,'tmp/research-replay-'));
const project='6f664280-4448-4e8f-a900-70de7eebe73a';
const sourceId='web_3041e395-17aa-4fef-895c-7daf79dc1fde';
const originalFolder=path.join(root,'data/research',project);
const sourcePath=path.join(originalFolder,'sources',sourceId+'.json');
const sourceBytes=await fs.readFile(sourcePath),metadata=JSON.parse(sourceBytes);
const blobPath=path.join(originalFolder,'blobs',metadata.sha256+'.bin');
const blobBytes=await fs.readFile(blobPath);
const protectedFiles=[sourcePath,blobPath,
 path.join(root,'benchmark/results/research-workflow-v06-evidence-precision.json'),
 path.join(root,'benchmark/results/research-workflow-v06-evidence-precision-review.json'),
 path.join(root,'benchmark/results/research-trust-v01-first.json'),
 path.join(root,'benchmark/results/research-trust-v01-first-diagnosis.json')];
const fileHashes=async files=>Object.fromEntries(await Promise.all(files.map(async p=>[p,digest(await fs.readFile(p))])));
const protectedBefore=await fileHashes(protectedFiles);
const productionFiles=['server/research.ts','server/config.ts','server/mcp.ts','service/server.py','service/core.py','service/store.py','service/lifecycle.py'];
const productionHashes=()=>fileHashes(productionFiles.map(p=>path.join(root,p)));
const protocol={kind:'frozen_official_snapshot_calculation_replay_protocol',created_at:new Date().toISOString(),
 execution:'Production ResearchStore.read + production service.server MCP calculate_financial_metrics. No application host and no Pi/model execution.',
 input:{project_id:project,source_id:sourceId,url:metadata.url,source_file_sha256:digest(sourceBytes),raw_sha256:digest(blobBytes),locator:'p1',
  period:'2025年上半年',currency:'CNY',amount_unit:'亿元',accounting_scope:'company news wording; consolidated scope is not inferred',
  published_at:metadata.published_at,retrieved_at:metadata.retrieved_at,
  disclosed:[{id:'total',value:'181.81',literal:'营业总收入181.81亿元'},{id:'domestic',value:'96.58',literal:'国内收入96.58亿元'},{id:'overseas',value:'85.23',literal:'海外收入85.23亿元'}]},
 operations:[{id:'regions_sum',operation:'sum',inputs:{values:['96.58','85.23'],unit:'亿元'},source_inputs:['domestic','overseas']},
  {id:'regions_minus_total',operation:'subtract',inputs:{a:'181.81',b:'181.81',unit:'亿元'},source_inputs:['regions_sum','total']},
  {id:'domestic_share',operation:'ratio',inputs:{numerator:'96.58',denominator:'181.81'},source_inputs:['domestic','total']},
  {id:'overseas_share',operation:'ratio',inputs:{numerator:'85.23',denominator:'181.81'},source_inputs:['overseas','total']}],
 independent_reference:'Python Fraction from frozen disclosed decimal strings, without production imports. Exact sums/differences, ratio absolute tolerance 5e-41 for the current 40-significant-digit calculator output.',
 isolation:'Private DATA contains only a copied source JSON/blob and newly created empty database/project. No live DB/settings/key/task copy. Node network entry points denied; Python socket audit hook denies external DNS/connect/bind, allowing logged loopback sockets needed by the Windows asyncio self-pipe; MCP is stdio.',
 replay:'Read archived source and calculate twice, with network denied for both runs. Compare exact source metadata/paragraphs and calculation data, excluding per-call trace_id.',
 limitations:['No new LLM or search call: does not retest model interpretation or source discovery.',
  'Shares are derived from rounded news figures, not more precise company disclosures. No yuan-level precision is claimed.',
  'No use of parent-attributable profit as consolidated profit. No external date or accounting scope is inferred.',
  'Scalar calculation calls do not automatically attach webpage citations; this report records the explicit source locator/literal/value-to-input ledger.']};
await fs.writeFile(prefix+'.protocol.json',JSON.stringify(protocol,null,2),{flag:'wx'});
const report={kind:'official_snapshot_existing_tools_offline_replay',status:'running',started_at:new Date().toISOString(),
 protocol_path:prefix+'.protocol.json',protocol_sha256:digest(JSON.stringify(protocol,null,2)),data_dir:data,
 live_app_contacted:false,model_calls:0,search_calls:0,new_web_fetches:0,checks:[],tool_calls:[],rounds:[],
 protected_before:protectedBefore,implementation_before:await productionHashes(),limitations:protocol.limitations};
const save=()=>fs.writeFile(prefix+'.json',JSON.stringify(report,null,2));
const check=(name,ok,evidence)=>{report.checks.push({name,status:ok?'passed':'failed',evidence});assert.ok(ok,name);};
const blockedNetwork=[];
function deny(kind){return function(...args){blockedNetwork.push({kind,argument_type:typeof args[0]});throw Error('Network denied in archived evidence replay: '+kind);};}
globalThis.fetch=deny('fetch');http.request=deny('http.request');http.get=deny('http.get');https.request=deny('https.request');https.get=deny('https.get');net.Socket.prototype.connect=deny('socket.connect');
process.env.FINANCE_DATA_DIR=data;process.env.FINANCE_LLM_API_KEY='';process.env.FINANCE_LLM_BASE_URL='';process.env.FINANCE_LLM_MODEL='';
const python=path.join(root,'.venv/Scripts/python.exe');
const env={};for(const key of ['PATH','Path','SystemRoot','SYSTEMROOT','WINDIR','TEMP','TMP','USERPROFILE','LOCALAPPDATA','APPDATA'])if(process.env[key])env[key]=process.env[key];
Object.assign(env,{FINANCE_DATA_DIR:data,PYTHONPATH:root,PYTHONIOENCODING:'utf-8',PYTHONUNBUFFERED:'1'});
const networkLog=path.join(data,'network-audit.jsonl');
const pythonWrapper="import sys,os,json,runpy\ndef no_network(event,args):\n if event in ('socket.connect','socket.getaddrinfo','socket.bind'):\n  address=args[0] if event=='socket.getaddrinfo' else args[1]\n  host=address[0] if isinstance(address,tuple) else address\n  allowed=host in ('127.0.0.1','::1','localhost')\n  with open(os.path.join(os.environ['FINANCE_DATA_DIR'],'network-audit.jsonl'),'a',encoding='utf8') as f:f.write(json.dumps({'event':event,'address':address,'loopback_allowed':allowed})+'\\n')\n  if not allowed:raise RuntimeError('External network forbidden in offline research replay')\nsys.addaudithook(no_network)\nrunpy.run_module('service.server',run_name='__main__')\n";
const client=new Client({name:'independent-archived-replay',version:'0.1.0'});
let transport,childPid;
const allowed=new Set(['create_project','calculate_financial_metrics']);
async function call(name,args){assert.ok(allowed.has(name),'Only fixed source-free calculator/admin MCP methods');const started=new Date().toISOString();const raw=await client.callTool({name,arguments:args});let result=raw.structuredContent;if(!result)result=JSON.parse(raw.content.filter(c=>c.type==='text').map(c=>c.text).join('\n'));report.tool_calls.push({name,args,started_at:started,result});assert.ok(!raw.isError&&result.status==='ok',name+' succeeded');return result;}
try{
 check('original_blob_matches_frozen_snapshot',digest(blobBytes)===metadata.sha256&&blobBytes.length===metadata.byte_count,{sha256:metadata.sha256,bytes:blobBytes.length});
 const privateFolder=path.join(data,'research',project);await fs.mkdir(path.join(privateFolder,'sources'),{recursive:true});await fs.mkdir(path.join(privateFolder,'blobs'),{recursive:true});
 await fs.writeFile(path.join(privateFolder,'sources',sourceId+'.json'),sourceBytes,{flag:'wx'});await fs.writeFile(path.join(privateFolder,'blobs',metadata.sha256+'.bin'),blobBytes,{flag:'wx'});
 const {ResearchStore}=await import('../server/research.ts');const {DATA,getSettings}=await import('../server/config.ts');const store=new ResearchStore(path.join(data,'research'));
 check('private_data_and_empty_credentials',DATA===data&&!getSettings().llm.apiKey&&!getSettings().search.apiKey&&!getSettings().embedding.apiKey,{data_dir:DATA});
 transport=new StdioClientTransport({command:python,args:['-c',pythonWrapper],cwd:root,env,stderr:'pipe'});transport.stderr?.on('data',x=>{report.private_mcp_stderr=(report.private_mcp_stderr||'')+x;});
 await client.connect(transport);childPid=transport.pid;report.private_mcp_pid=childPid;await call('create_project',{project_id:project,name:'Private frozen official news replay'});
 for(let round=1;round<=2;round++){
  const read=await store.read(project,sourceId,0,40),p=read.paragraphs.find(p=>p.id===protocol.input.locator);assert.ok(p);
  const sourceInputs=protocol.input.disclosed.map(item=>({...item,locator:p.id,quote:p.text,source_id:read.source_id,sha256:read.sha256,exact_literal_present:p.text.includes(item.literal)}));
  check('round_'+round+'_disclosed_inputs_are_in_actual_archived_read',sourceInputs.every(i=>i.exact_literal_present),sourceInputs);
  const calculations=[];
  for(const operation of protocol.operations){const inputs=structuredClone(operation.inputs);if(operation.id==='regions_minus_total')inputs.a=calculations.find(x=>x.id==='regions_sum').response.data.value;
   const response=await call('calculate_financial_metrics',{project_id:project,operation:operation.operation,inputs});calculations.push({...operation,actual_inputs:inputs,response});}
  report.rounds.push({round,network_policy:'deny_all_external',source:read,source_inputs:sourceInputs,calculations});await save();
 }
 check('replay_source_exactly_identical',stableJson(report.rounds[0].source)===stableJson(report.rounds[1].source),{source_sha256:metadata.sha256});
 check('replay_calculator_exactly_identical',stableJson(report.rounds[0].calculations.map(c=>c.response.data))===stableJson(report.rounds[1].calculations.map(c=>c.response.data)),{operations:protocol.operations.map(o=>o.id),calls:8});
 const reference="import json,sys\nfrom fractions import Fraction as F\nd=json.load(sys.stdin)\nexpected={'regions_sum':F(9658+8523,100),'regions_minus_total':F(0),'domestic_share':F(9658,18181),'overseas_share':F(8523,18181)}\nchecks=[]\nfor run in d['rounds']:\n for c in run['calculations']:\n  e=expected[c['id']];a=F(c['response']['data']['value']);tol=F(1,2*10**40) if c['id'].endswith('_share') else F(0)\n  checks.append({'round':run['round'],'id':c['id'],'actual':str(a),'expected_fraction':str(e),'absolute_error':str(abs(a-e)),'tolerance':str(tol),'passed':abs(a-e)<=tol})\nprint(json.dumps({'method':'fractions.Fraction independent fixed disclosed-input reference','checks':checks,'passed':all(c['passed'] for c in checks)}))\n";
 const independent=await new Promise((resolve,reject)=>{const child=execFile(python,['-c',reference],{cwd:root,env,windowsHide:true,maxBuffer:1024*1024},(error,stdout,stderr)=>error?reject(Error(stderr||error.message)):resolve(JSON.parse(stdout)));child.stdin.end(JSON.stringify({rounds:report.rounds}));});
 report.independent=independent;check('independent_fraction_verification',independent.passed,{checks:independent.checks});
 const privateSource=await fs.readFile(path.join(privateFolder,'sources',sourceId+'.json')),privateBlob=await fs.readFile(path.join(privateFolder,'blobs',metadata.sha256+'.bin'));
 check('private_archive_bytes_unchanged',digest(privateSource)===digest(sourceBytes)&&digest(privateBlob)===metadata.sha256,{});
 report.protected_after=await fileHashes(protectedFiles);check('original_sources_and_old_reports_unchanged',stableJson(report.protected_before)===stableJson(report.protected_after),{paths:protectedFiles});
 report.implementation_after=await productionHashes();check('production_files_unchanged',stableJson(report.implementation_before)===stableJson(report.implementation_after),{});
 let pythonAttempts=[];try{pythonAttempts=(await fs.readFile(networkLog,'utf8')).trim().split('\n').filter(Boolean).map(JSON.parse);}catch(e){if(e.code!=='ENOENT')throw e;}
 report.network={node_attempts:blockedNetwork,python_attempts:pythonAttempts,policy:'deny_external_connect_dns_bind_in_python_and_network_entry_points_in_node; Windows asyncio local self-pipe sockets allowed and logged'};
 check('no_network_provider_or_unapproved_tool_attempt',blockedNetwork.length===0&&pythonAttempts.every(x=>x.loopback_allowed)&&report.tool_calls.every(x=>allowed.has(x.name)),{network:report.network,tools:report.tool_calls.map(x=>x.name)});
 report.status='passed';
}catch(error){report.status='failed';report.error=error.stack||String(error);}
finally{
 try{await client.close();}catch(error){report.close_error=String(error);report.status='failed';}
 let alive=false;if(childPid){for(let i=0;i<100;i++){try{process.kill(childPid,0);alive=true;}catch{alive=false;break;}await delay(50);}}
 report.private_mcp_exited=!alive;report.checks.push({name:'private_mcp_process_exited',status:alive?'failed':'passed',evidence:{pid:childPid}});if(alive)report.status='failed';
 report.finished_at=new Date().toISOString();await save();console.log(JSON.stringify({status:report.status,path:prefix+'.json',checks:report.checks.length,passed:report.checks.filter(c=>c.status==='passed').length,official_calls:0}));
}
if(report.status!=='passed')process.exitCode=1;
