import {evaluationIsolation,evaluationRuntime} from './evaluation-isolation.js';
import { Client } from '@modelcontextprotocol/sdk/client/index.js';
import { StdioClientTransport } from '@modelcontextprotocol/sdk/client/stdio.js';
import { APP_VERSION,DATA,ROOT,PYTHON,redactError } from './config.js';
import type { Envelope } from './types.js';
import path from 'node:path';
import {setTimeout as delay} from 'node:timers/promises';
import {PayloadTransport} from './mcp-payloads.js';

// Only reads and explicitly idempotent host persistence can be repeated after
// losing a response. Never duplicate a financial model, ingestion or SQL write.
export const replayableServiceCall=(name:string)=>/^(get_|list_|query_|search_|read_)/.test(name)||['put_app_state','configure_processing','calculate_financial_metrics'].includes(name);
const connectionLost=(error:any)=>error.code===-32000||/^Not connected$/i.test(error.message);

export class FinanceService {
 client=new Client({name:'finance-research-host',version:APP_VERSION});
 private transport?:PayloadTransport;
 private started=false;
 private stopped=false;
 private connecting?:Promise<void>;
 private configurations=new Map<string,any>();
 get connected(){return this.started;}
 connect():Promise<void> {
   if(this.stopped)return Promise.reject(new Error('文档服务已关闭'));
   if(this.started)return Promise.resolve();
   if(!this.connecting)this.connecting=this.open().finally(()=>{this.connecting=undefined;});
   return this.connecting;
 }
 private async open(){
   for(const wait of [0,250,1000]){
    await delay(wait);
    if(this.stopped)throw new Error('文档服务已关闭');
    try{await this.openOnce();return;}catch(error){await this.transport?.close();if(wait===1000)throw error;}
   }
 }
 private async openOnce() {
   const env:Record<string,string>={};
   // Child receives only runtime essentials, never model keys inherited from the host.
   for(const name of ['PATH','Path','SystemRoot','SYSTEMROOT','WINDIR','TEMP','TMP','USERPROFILE','LOCALAPPDATA','APPDATA'])if(process.env[name])env[name]=process.env[name]!;
   env.FINANCE_DATA_DIR=DATA;env.PYTHONPATH=ROOT;env.PYTHONIOENCODING='utf-8';env.PYTHONUNBUFFERED='1';env.PYTHONFAULTHANDLER='1';
   const raw=new StdioClientTransport({command:PYTHON,args:['-m','service.server'],cwd:ROOT,env,stderr:'pipe'});
   const transport=this.transport=new PayloadTransport(raw,DATA);
   raw.stderr?.on('data',chunk=>process.stderr.write('[finance-service] '+redactError(chunk.toString())+'\n'));
   const client=this.client=new Client({name:'finance-research-host',version:APP_VERSION});
   client.onclose=()=>{
    if(this.client!==client)return;
    const wasConnected=this.started;this.started=false;
    if(wasConnected&&!this.stopped){
     process.stderr.write('[finance-service] Connection closed; reconnecting.\n');
     void this.connect().catch(error=>process.stderr.write('[finance-service] Reconnect failed: '+redactError(error)+'\n'));
    }
   };
   client.onerror=error=>process.stderr.write('[finance-service] '+redactError(error).slice(0,1000)+'\n');
   await client.connect(transport);
   for(const args of this.configurations.values())await client.callTool({name:'configure_processing',arguments:args});
   if(this.stopped){await client.close();throw new Error('文档服务已关闭');}
   this.started=true;
 }
 async close(){this.stopped=true;this.started=false;await this.connecting?.catch(()=>{});await this.client.close();}
 async tools(){
   await this.connect();
   try{return (await this.client.listTools()).tools;}
   catch(error){if(!connectionLost(error))throw error;await this.connect();return (await this.client.listTools()).tools;}
 }
 async call<T=any>(name:string,args:Record<string,unknown>,signal?:AbortSignal):Promise<Envelope<T>> {
   await this.connect();signal?.throwIfAborted();
   const meta={...(evaluationIsolation.getStore()!==undefined?{finance_evaluation_isolation_key:evaluationIsolation.getStore()}:{}),
    ...(evaluationRuntime.getStore()?{finance_evaluation_profile:evaluationRuntime.getStore()!.profile,finance_analysis_only:evaluationRuntime.getStore()!.analysis_only===true}:{})};
   const request={name,arguments:args,...(Object.keys(meta).length?{_meta:meta}:{})};
   const options={signal,timeout:180000,resetTimeoutOnProgress:true};
   const client=this.client;
   let response;
   try{response=await client.callTool(request,undefined,options);}
   catch(error){
    signal?.throwIfAborted();
    if(!connectionLost(error))throw error;
    process.stderr.write('[finance-service] '+JSON.stringify({event:'call_transport_lost',tool:name,replay:replayableServiceCall(name)})+'\n');
    await this.connect();
    if(!replayableServiceCall(name))throw Object.assign(new Error(`${name}: MCP 连接中断，执行结果未知；请读取已保存进度/产物后决定是否重试。连接已重建，未自动重复写操作。`),{code:'MCP_RESULT_UNKNOWN',cause:error});
    response=await this.client.callTool(request,undefined,options);
   }
   let result:any=response.structuredContent;
   if(!result){const text=(response.content as any[]).filter(x=>x.type==='text').map(x=>x.text).join('\n');try{result=JSON.parse(text);}catch{throw new Error(response.isError?text:'金融服务返回格式无效');}}
   if(response.isError || result.status==='error'){
     const err:any=new Error(typeof result.error==='string'?result.error:result.error?.message || result.data?.error || result.data?.message || result.data?.availability?.reason || result.message || '金融服务操作失败');
     err.code=result.error?.code || result.data?.code || result.code || 'SERVICE_ERROR';err.details=result.data?.details;throw err;
   }
   if(name==='configure_processing')this.configurations.set(String(args.project_id),structuredClone(args));
   return result;
 }
 async configure(projectId:string,settings:any){
  return this.call('configure_processing',{project_id:projectId,embedding:{enabled:!!settings.embedding.enabled,base_url:settings.embedding.baseUrl,model:settings.embedding.model,api_key:settings.embedding.apiKey,...(settings.embedding.dimensions?{dimensions:settings.embedding.dimensions}:{})},ocr:{mode:settings.ocr.mode,base_url:settings.ocr.baseUrl,model:settings.ocr.model,api_key:settings.ocr.apiKey}});
 }
 async getState<T>(projectId:string,kind:'conversations'|'runs'|'evaluation_budgets',key:string):Promise<T|undefined>{
  const r=await this.call('get_app_state',{project_id:projectId,kind,key});return (r.data?.value ?? undefined) as T|undefined;
 }
 async putState(projectId:string,kind:'conversations'|'runs'|'evaluation_budgets',key:string,value:any){
  return this.call('put_app_state',{project_id:projectId,kind,key,value});
 }
 async listState<T>(projectId:string,kind:'conversations'|'runs'|'evaluation_budgets'):Promise<T[]>{
  const r=await this.call('list_app_state',{project_id:projectId,kind});return (r.data?.items || []).map((x:any)=>x.value??x);
 }
}
export function safeDataPath(relative:string):string {
 const full=path.resolve(DATA,relative);
 if(full===DATA || !full.startsWith(DATA+path.sep))throw new Error('文件路径越界');
 return full;
}
