import {ModelRuntime,getAgentDir} from '@earendil-works/pi-coding-agent';
import path from 'node:path';
import {stat} from 'node:fs/promises';
import type {LlmConfig} from './types.js';

// JSON mode belongs to the selected API, not the provider's hostname.
export function jsonOutputPayload(payload:Record<string,unknown>,api:string){
 if(api==='openai-responses'||api==='openai-codex-responses'||api==='azure-openai-responses'){
  return {...payload,text:{...(payload.text as Record<string,unknown>|undefined),format:{type:'json_object'}}};
 }
 if(api==='openai-completions')return {...payload,response_format:{type:'json_object'}};
 return payload;
}

export async function modelCatalogRevision(){
 return JSON.stringify(await Promise.all(['models.json','auth.json','models-store.json'].map(async name=>{
  const file=path.join(getAgentDir(),name);try{const info=await stat(file);return [file,info.mtimeMs,info.size];}catch(error){if((error as NodeJS.ErrnoException).code==='ENOENT')return [file,null];throw error;}
 })));
}

// Native catalog + global models.json/auth.json. Application API overrides stay
// in memory; selecting a model never rewrites the user's global configuration.
export async function configuredModel(config:LlmConfig){
 const runtime=await ModelRuntime.create({allowModelNetwork:false});
 const legacy=config.provider==='openai-compatible';
 const candidates=runtime.getModels().filter(m=>m.id===config.model);
 const catalog=legacy?(candidates.find(m=>m.provider==='deepseek')||(candidates.length===1?candidates[0]:undefined)):runtime.getModel(config.provider,config.model);
 if(!legacy&&!catalog)throw new Error('Pi 模型目录中没有此模型：'+config.provider+'/'+config.model);
 if(catalog){
  if(legacy&&config.baseUrl)runtime.registerProvider(catalog.provider,{baseUrl:config.baseUrl});
  if(config.apiKey)await runtime.setRuntimeApiKey(catalog.provider,config.apiKey);
  const resolved=runtime.getModel(catalog.provider,catalog.id)!;
  // Explicit legacy gateway limits remain valid; catalog selections use native metadata.
  const model=legacy?{...resolved,contextWindow:config.contextWindow,maxTokens:resolved.maxTokens}:resolved;
  return {runtime,model};
 }
 // Existing private/local endpoints unknown to the catalog remain usable.
 // They can instead be defined in global models.json, including reasoning/compat.
 runtime.registerProvider('financial-custom',{baseUrl:config.baseUrl,api:'openai-completions',authHeader:!!config.apiKey,models:[{id:config.model,name:config.model,reasoning:false,input:['text'],contextWindow:config.contextWindow,maxTokens:Math.max(config.maxTokens,32768),cost:{input:config.inputPricePerMillionUsd||0,output:config.outputPricePerMillionUsd||0,cacheRead:0,cacheWrite:0},compat:{supportsStore:false,supportsDeveloperRole:false,maxTokensField:'max_tokens'}}]});
 await runtime.setRuntimeApiKey('financial-custom',config.apiKey||'local-no-key');
 return {runtime,model:runtime.getModel('financial-custom',config.model)!};
}
export async function modelCatalog(){
 const runtime=await ModelRuntime.create({allowModelNetwork:false});
 return {path:path.join(getAgentDir(),'models.json'),models:runtime.getModels().map(m=>({provider:m.provider,id:m.id,name:m.name,reasoning:m.reasoning,contextWindow:m.contextWindow,maxTokens:m.maxTokens,configured:runtime.hasConfiguredAuth(m.provider)})),error:runtime.getError()};
}
