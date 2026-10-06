// Diagnostic only: same native Pi adapter, synthetic inputs, no project writes.
import {writeFile} from 'node:fs/promises';
import {ModelRuntime} from '@earendil-works/pi-coding-agent';
import {Type} from 'typebox';
import {loadSettings} from '../server/config.js';
import {jsonOutputPayload} from '../server/model-runtime.js';
const {llm}=await loadSettings();
if(llm.provider!=='cpa-local'||new URL(llm.baseUrl).hostname!=='127.0.0.1')throw Error('Expected current local CPA');
const runtime=await ModelRuntime.create({allowModelNetwork:false});
const ids=['gpt-6-luna','gpt-6.1-sol'];
const definitions=ids.map(id=>{const m=runtime.getModel('openai',id)!;return {id,name:id,reasoning:m.reasoning,input:m.input,contextWindow:m.contextWindow,maxTokens:m.maxTokens,cost:m.cost};});
runtime.registerProvider('cpa-diagnostic',{baseUrl:llm.baseUrl,api:'openai-responses',authHeader:true,models:definitions});
await runtime.setRuntimeApiKey('cpa-diagnostic',llm.apiKey);
const evidence:any={at:new Date().toISOString(),scope:'synthetic short requests, not a long-task reliability proof',requests:[]};
const file='data/evaluation/pi-finance-generalization-20261006/cpa-stream-probes.json';
async function call(id:string,name:string,context:any,json=false){
 const record:any={model:id,name,startedAt:new Date().toISOString(),http:[],terminals:[],eventCounts:{}};const start=Date.now();
 const result=await runtime.completeSimple(runtime.getModel('cpa-diagnostic',id)!,context,{
  reasoning:'low',maxTokens:2048,signal:AbortSignal.timeout(90000),
  onPayload:(payload:any)=>{const p=json?jsonOutputPayload(payload,'openai-responses'):payload;record.payload=p;return p;},
  onResponse:(r:any)=>record.http.push({status:r.status,requestId:r.headers['x-request-id'],contentType:r.headers['content-type']}),
  onProviderStreamEvent:(event:any)=>{record.eventCounts[event.type]=(record.eventCounts[event.type]||0)+1;if(['response.completed','response.failed','response.incomplete','error'].includes(event.type))record.terminals.push(event);}
 } as any);
 record.durationMs=Date.now()-start;record.result=result;evidence.requests.push(record);await writeFile(file,JSON.stringify(evidence,null,2));
 console.log(JSON.stringify({model:id,name,status:record.http.map((r:any)=>r.status),stopReason:result.stopReason,error:result.errorMessage,terminal:record.terminals.map((r:any)=>({type:r.type,status:r.response?.status,model:r.response?.model,incomplete:r.response?.incomplete_details})),content:result.content,usage:result.usage,durationMs:record.durationMs}));
 return result;
}
for(const id of ids){
 await call(id,'json',{systemPrompt:'Return a JSON object only.',messages:[{role:'user',content:'Return {"ready":true}.',timestamp:Date.now()}]},true);
 const tools=[{name:'read_sample',description:'Read the synthetic source table.',parameters:Type.Object({table_id:Type.String()})},{name:'save_sample',description:'Save a normalized synthetic value. Use after reading the source.',parameters:Type.Object({table_id:Type.String(),value_yuan:Type.Number()})}];
 const context:any={systemPrompt:'Complete the requested tool workflow before your final reply.',tools,messages:[{role:'user',content:'Read table T1 with read_sample, convert its disclosed value to yuan, call save_sample, then briefly report the saved result.',timestamp:Date.now()}]};
 // This diagnostic has three expected requests; it does not alter the application loop.
 for(let step=0;step<3;step++){
  const message=await call(id,'tool_'+step,context);context.messages.push(message);
  const calls=message.content.filter((x:any)=>x.type==='toolCall');if(!calls.length)break;
  for(const c of calls){const data=c.name==='read_sample'?{table_id:'T1',value:'1,234.50',unit:'万元',currency:'CNY'}:{saved:c.arguments.table_id==='T1'&&c.arguments.value_yuan===12345000,received:c.arguments};context.messages.push({role:'toolResult',toolCallId:c.id,toolName:c.name,content:[{type:'text',text:JSON.stringify(data)}],isError:false,timestamp:Date.now()});}
 }
}
