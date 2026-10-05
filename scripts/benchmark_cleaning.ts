// Scoped, real-model A/B using the same Pi runtime and private bridge as the app.
// Never writes the production database, conversation, settings, or extraction cache.
import {ModelRuntime} from '@earendil-works/pi-coding-agent';
import {InMemoryCredentialStore} from '@earendil-works/pi-ai';
import {appendFile,mkdir,writeFile} from 'node:fs/promises';
import {spawn} from 'node:child_process';
import {randomUUID} from 'node:crypto';
import path from 'node:path';
import {PiModelBridge} from '../server/model-bridge.js';
import {loadSettings,PYTHON,redactError} from '../server/config.js';
import {extractionEffort,extractionReasoning} from '../server/reasoning-routing.js';

const args=process.argv.slice(2),arg=(name:string,fallback='')=>args.includes(name)?args[args.indexOf(name)+1]||fallback:fallback;
const mode=arg('--mode','low'),directory=path.resolve(arg('--output','data/retests/yili-20261004/cost-ab'));
if(!['low','compact-low','targeted-low'].includes(mode))throw Error('invalid mode: cleaning requires at least low reasoning');
const review=args.includes('--review'),auditName=mode+(review?'-review':'');
const settings=await loadSettings();
if(new URL(settings.llm.baseUrl).hostname!=='api.deepseek.com')throw Error('benchmark expects the configured official DeepSeek endpoint');
const runtime=await ModelRuntime.create({credentials:new InMemoryCredentialStore(),modelsPath:null,allowModelNetwork:false,refreshOnCreate:false});
runtime.registerProvider('financial-provider',{baseUrl:settings.llm.baseUrl,api:'openai-completions',models:[{id:settings.llm.model,name:settings.llm.model,reasoning:true,input:['text'],contextWindow:settings.llm.contextWindow,maxTokens:32768,cost:{input:0,output:0,cacheRead:0,cacheWrite:0},compat:{supportsStore:false,supportsDeveloperRole:false,maxTokensField:'max_tokens',thinkingFormat:'deepseek',supportsReasoningEffort:true}}]});
await runtime.setRuntimeApiKey('financial-provider',settings.llm.apiKey);
const model=runtime.getModel('financial-provider',settings.llm.model)!;
await mkdir(directory,{recursive:true});
const bridge=new PiModelBridge(),controller=new AbortController(),session=randomUUID();
let calls=0,knownUsd=0;
const audit=(type:string,data:any)=>appendFile(path.join(directory,auditName+'-requests.jsonl'),JSON.stringify({at:new Date().toISOString(),session,type,...data})+'\n');
const transport=await bridge.register(session,controller.signal,async(body,signal)=>{
 if(calls>=50||knownUsd>=Number(arg('--budget-usd','0.40')))throw Error('isolated benchmark budget reached');
 const requestId=randomUUID(),effort=extractionEffort(body.reasoning_effort);calls++;
 await audit('request',{requestId,effort,messages:body.messages});
 const started=Date.now();
 let answer;
 try{answer=await runtime.completeSimple(model,{
  systemPrompt:body.messages.filter((m:any)=>m.role==='system').map((m:any)=>m.content).join('\n'),
  messages:body.messages.filter((m:any)=>m.role!=='system').map((m:any)=>({role:'user',content:m.content,timestamp:Date.now()}))
 },{signal,reasoning:extractionReasoning(effort),maxTokens:32768,temperature:0,onPayload:async(payload:any)=>{
  await audit('payload',{requestId,thinking:payload.thinking,reasoning_effort:payload.reasoning_effort,max_tokens:payload.max_tokens});
  return {...payload,response_format:{type:'json_object'}};
 }});}catch(error){
  await audit('result',{requestId,effort,stopReason:'error',usage:{},usageKnown:false,durationMs:Date.now()-started,error:redactError(error)});
  throw error;
 }
 const usage=answer.usage,content=answer.content.filter((b:any)=>b.type==='text').map((b:any)=>b.text).join('');
 knownUsd+=(Number(usage.input)*.15+Number(usage.cacheRead)*.003+Number(usage.output)*.6)/1e6;
 await audit('result',{requestId,effort,stopReason:answer.stopReason,usage,content,durationMs:Date.now()-started,error:answer.errorMessage?redactError(answer.errorMessage):undefined});
 if(answer.stopReason==='length')throw Object.assign(Error('output limit'),{status:422,code:'model_output_limit',request_id:requestId,stop_reason:'length'});
 if(answer.stopReason==='error'||answer.stopReason==='aborted')throw Error(redactError(answer.errorMessage||answer.stopReason));
 return {content,model:settings.llm.model,input:usage.input+usage.cacheRead,output:usage.output};
});
try{
 const child=spawn(PYTHON,[review?'scripts/benchmark_temporal_review.py':'scripts/benchmark_cleaning.py','--prepared','data/indexes/b43ae45c-d96b-43b6-ab5b-04306c0eb142/1f94f25a3cb74d528f10ddac0be06a0d.json','--output',directory,'--mode',mode,...(args.includes('--cases')?['--cases',arg('--cases')]:[])],{stdio:['pipe','inherit','inherit'],env:{...process.env,PYTHONIOENCODING:'utf-8'},windowsHide:true});
 child.stdin.end(JSON.stringify({...transport,model:settings.llm.model,max_tokens:32768,owner_run_id:session})+'\n');
 const code=await new Promise<number|null>((resolve,reject)=>{child.once('exit',resolve);child.once('error',reject);});
 await writeFile(path.join(directory,auditName+'-session-'+session+'.json'),JSON.stringify({session,mode,review,calls,knownUsd,code,model:settings.llm.model,pricing:'2026-10-04 official Sunday off-peak USD estimate; unknown failed usage excluded'},null,2));
 process.exitCode=code||0;
}finally{controller.abort();await bridge.close();}
