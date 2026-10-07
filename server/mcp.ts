import { Client } from '@modelcontextprotocol/sdk/client/index.js';
import { StdioClientTransport } from '@modelcontextprotocol/sdk/client/stdio.js';
import { APP_VERSION,DATA,ROOT,PYTHON,redactError } from './config.js';
import type { Envelope } from './types.js';
import path from 'node:path';

export class FinanceService {
 client=new Client({name:'finance-research-host',version:APP_VERSION});
 private transport?:StdioClientTransport;
 private started=false;
 get connected(){return this.started;}
 async connect() {
   const env:Record<string,string>={};
   // Child receives only runtime essentials, never model keys inherited from the host.
   for(const name of ['PATH','Path','SystemRoot','SYSTEMROOT','WINDIR','TEMP','TMP','USERPROFILE','LOCALAPPDATA','APPDATA'])if(process.env[name])env[name]=process.env[name]!;
   env.FINANCE_DATA_DIR=DATA;env.PYTHONPATH=ROOT;env.PYTHONIOENCODING='utf-8';env.PYTHONUNBUFFERED='1';env.PYTHONFAULTHANDLER='1';
   this.transport=new StdioClientTransport({command:PYTHON,args:['-m','service.server'],cwd:ROOT,env,stderr:'pipe'});
   this.transport.stderr?.on('data',chunk=>process.stderr.write('[finance-service] '+redactError(chunk.toString())+'\n'));
   this.client.onclose=()=>{if(this.started)process.stderr.write('[finance-service] Connection closed unexpectedly; restart the application to resume saved work.\n');this.started=false;};
   this.client.onerror=error=>process.stderr.write('[finance-service] '+redactError(error).slice(0,1000)+'\n');
   await this.client.connect(this.transport);this.started=true;
 }
 async close(){this.started=false;await this.client.close();}
 async tools(){return (await this.client.listTools()).tools;}
 async call<T=any>(name:string,args:Record<string,unknown>,signal?:AbortSignal):Promise<Envelope<T>> {
   if(!this.started)throw new Error('文档服务尚未就绪');
   const response=await this.client.callTool({name,arguments:args},undefined,{signal,timeout:180000,resetTimeoutOnProgress:true});
   let result:any=response.structuredContent;
   if(!result){const text=(response.content as any[]).filter(x=>x.type==='text').map(x=>x.text).join('\n');try{result=JSON.parse(text);}catch{throw new Error(response.isError?text:'金融服务返回格式无效');}}
   if(response.isError || result.status==='error'){
     const err:any=new Error(typeof result.error==='string'?result.error:result.error?.message || result.data?.error || result.data?.message || result.data?.availability?.reason || result.message || '金融服务操作失败');
     err.code=result.error?.code || result.data?.code || result.code || 'SERVICE_ERROR';err.details=result.data?.details;throw err;
   }
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
