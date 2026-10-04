import { mkdir, readFile, writeFile, rename } from 'node:fs/promises';
import { existsSync } from 'node:fs';
import { createCipheriv, createDecipheriv, randomBytes } from 'node:crypto';
import { spawn } from 'node:child_process';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { z } from 'zod';
import type { Settings } from './types.js';
import { DEFAULT_CONTEXT_COMPACTION } from './types.js';

const moduleDirectory = path.dirname(fileURLToPath(import.meta.url));
// Compiled releases run from server/dist; source development runs from server.
export const ROOT = path.resolve(moduleDirectory, path.basename(moduleDirectory) === 'dist' ? '../..' : '..');
try { process.loadEnvFile(path.join(ROOT, '.env')); } catch (e: any) { if (e.code !== 'ENOENT') throw e; }
export const DATA = path.resolve(process.env.FINANCE_DATA_DIR || path.join(ROOT, 'data'));
const portablePython = path.join(ROOT, 'runtime', 'python', 'python.exe');
export const PYTHON = process.env.FINANCE_PYTHON || (process.platform === 'win32' && existsSync(portablePython) ? portablePython : path.join(ROOT, '.venv', process.platform === 'win32' ? 'Scripts/python.exe' : 'bin/python'));
export const PORT = Number(process.env.FINANCE_PORT || 3001);
export const HOST = process.env.FINANCE_HOST || '127.0.0.1';
if (!['127.0.0.1','::1','localhost'].includes(HOST)) throw new Error('本版本只允许绑定本机回环地址');
export async function initDirectories() {
  for (const dir of ['', 'uploads', 'workspaces', 'audit', 'exports']) await mkdir(path.join(DATA, dir), {recursive:true,mode:0o700});
}
const defaultSettings: Settings = {
  llm: {provider:'openai-compatible',baseUrl:process.env.FINANCE_LLM_BASE_URL || '',model:process.env.FINANCE_LLM_MODEL || '',apiKey:process.env.FINANCE_LLM_API_KEY || '',contextWindow:128000,maxTokens:32768},
  embedding:{enabled:false,baseUrl:'',model:'',apiKey:''},
  ocr:{mode:'local',baseUrl:'',model:'',apiKey:''},
  search:{provider:'tavily',baseUrl:'https://api.tavily.com',apiKey:'',maxResults:6},
  runtime:{maxToolCalls:64,timeoutSeconds:120,contextCompaction:{...DEFAULT_CONTEXT_COMPACTION}},
};
const url = z.string().trim().max(2048).refine(value => {
  if (!value) return true;
  try { const u=new URL(value); return !u.username && !u.password && !u.search && !u.hash && (u.protocol==='https:' || (u.protocol==='http:' && ['localhost','127.0.0.1','[::1]'].includes(u.hostname))); } catch { return false; }
},'使用HTTPS地址；本机服务可使用HTTP，地址不能包含密钥或查询参数');
const key=z.string().max(16384), model=z.string().trim().max(300);
const settingsSchema=z.object({
  llm:z.object({provider:z.literal('openai-compatible'),baseUrl:url,model,apiKey:key,contextWindow:z.number().int().min(4096).max(2000000),maxTokens:z.number().int().min(128).max(131072),inputPricePerMillionUsd:z.number().nonnegative().optional(),outputPricePerMillionUsd:z.number().nonnegative().optional()}),
  embedding:z.object({enabled:z.boolean(),baseUrl:url,model,apiKey:key,dimensions:z.number().int().min(1).max(65536).optional()}),
  ocr:z.object({mode:z.enum(['local','api']),baseUrl:url,model,apiKey:key}),
  search:z.object({provider:z.enum(['tavily','brave']),baseUrl:url,apiKey:key,maxResults:z.number().int().min(1).max(20)}).default({provider:'tavily',baseUrl:'https://api.tavily.com',apiKey:'',maxResults:6}),
  runtime:z.object({maxToolCalls:z.number().int().min(1).max(100),timeoutSeconds:z.number().int().min(10).max(120),budgetCny:z.number().positive().optional(),usdToCny:z.number().positive().optional(),contextCompaction:z.object({enabled:z.boolean(),targetTokens:z.number().int().min(4096).max(2000000),keepRecentTokens:z.number().int().min(1024).max(1000000),summaryMaxTokens:z.number().int().min(512).max(32768)}).refine(v=>v.keepRecentTokens<v.targetTokens&&v.summaryMaxTokens<v.targetTokens,'近期保留量和摘要输出必须小于压缩触发阈值').default({...DEFAULT_CONTEXT_COMPACTION})}),
});
const settingsPath=path.join(DATA,'settings.json');
let current: Settings=structuredClone(defaultSettings);
let saveQueue: Promise<unknown>=Promise.resolve();
async function dpapi(value:string, decrypt=false):Promise<string> {
  const command = "Add-Type -AssemblyName System.Security; $data=[Convert]::FromBase64String([Console]::In.ReadToEnd()); $entropy=[Text.Encoding]::UTF8.GetBytes('finance-research-agent-v1'); " +
    (decrypt ? "$result=[Security.Cryptography.ProtectedData]::Unprotect($data,$entropy,[Security.Cryptography.DataProtectionScope]::CurrentUser);" : "$result=[Security.Cryptography.ProtectedData]::Protect($data,$entropy,[Security.Cryptography.DataProtectionScope]::CurrentUser);") +
    " [Console]::Out.Write([Convert]::ToBase64String($result));";
  return new Promise((resolve,reject)=>{
    const child=spawn('powershell.exe',['-NoProfile','-NonInteractive','-Command',command],{windowsHide:true,stdio:['pipe','pipe','pipe']});
    let out=''; child.stdout.on('data',v=>out+=v); child.stderr.resume();
    child.on('error',()=>reject(new Error('无法访问Windows凭据保护服务')));
    child.on('close',code=>code===0?resolve(out.trim()):reject(new Error('无法保护或解密本地凭据')));
    child.stdin.end(decrypt?value:Buffer.from(value).toString('base64'));
  });
}
async function encrypt(value:string):Promise<string> {
  if (!value) return '';
  if(process.platform==='win32') return 'dpapi:'+await dpapi(value);
  const master=path.join(DATA,'secret.key');
  let bytes:Buffer;try{bytes=await readFile(master);}catch(e:any){if(e.code!=='ENOENT')throw e;bytes=randomBytes(32);await writeFile(master,bytes,{mode:0o600,flag:'wx'});}
  const iv=randomBytes(12),cipher=createCipheriv('aes-256-gcm',bytes,iv),encrypted=Buffer.concat([cipher.update(value,'utf8'),cipher.final()]);
  return 'aesgcm:'+Buffer.concat([iv,cipher.getAuthTag(),encrypted]).toString('base64');
}
async function decrypt(value:string):Promise<string> {
  if(!value)return '';
  if(value.startsWith('dpapi:'))return Buffer.from(await dpapi(value.slice(6),true),'base64').toString('utf8');
  if(value.startsWith('aesgcm:')){
    const b=Buffer.from(value.slice(7),'base64'),decipher=createDecipheriv('aes-256-gcm',await readFile(path.join(DATA,'secret.key')),b.subarray(0,12));
    decipher.setAuthTag(b.subarray(12,28));return Buffer.concat([decipher.update(b.subarray(28)),decipher.final()]).toString('utf8');
  }
  throw new Error('不接受未加密的已存API凭据');
}
export async function loadSettings() {
  await initDirectories();
  if(existsSync(settingsPath)){
    const stored=JSON.parse(await readFile(settingsPath,'utf8'));
    for(const section of ['llm','embedding','ocr','search'] as const) if(stored[section])stored[section].apiKey=await decrypt(stored[section].apiKey || '');
    current=settingsSchema.parse({...defaultSettings,...stored});
  }
  return getSettings();
}
export function getSettings():Settings{return structuredClone(current);}
export function publicSettings(){
 const copy:any=getSettings();
 for(const section of ['llm','embedding','ocr','search'])if(copy[section]){copy[section].hasKey=!!copy[section].apiKey;delete copy[section].apiKey;}
 return copy;
}
export async function saveSettings(patch:unknown) {
 if(!patch || typeof patch!=='object' || Array.isArray(patch))throw new Error('配置必须为对象');
 const p=patch as Record<string,any>,merged:any={};
 for(const section of ['llm','embedding','ocr','search','runtime'] as const) merged[section]={...current[section],...(p[section]||{})};
 const next=settingsSchema.parse(merged);
 if(next.llm.maxTokens>next.llm.contextWindow)throw new Error('最大输出不能超过上下文窗口');
 if(next.runtime.budgetCny && (next.llm.inputPricePerMillionUsd===undefined || next.llm.outputPricePerMillionUsd===undefined || !next.runtime.usdToCny))throw new Error('启用人民币预算前，请填写模型输入/输出价格和美元折算率');
 const operation=saveQueue.then(async()=>{
   const stored:any=structuredClone(next);
   for(const section of ['llm','embedding','ocr','search'] as const)stored[section].apiKey=await encrypt(stored[section].apiKey);
   const temp=settingsPath+'.tmp';await writeFile(temp,JSON.stringify(stored,null,2),{mode:0o600});await rename(temp,settingsPath);current=next;
 });
 saveQueue=operation.catch(()=>{});await operation;return publicSettings();
}
export function redactError(error:unknown):string {
 let message=error instanceof Error?error.message:String(error);
 for(const s of [current.llm.apiKey,current.embedding.apiKey,current.ocr.apiKey,current.search?.apiKey])if(s)message=message.split(s).join('[REDACTED]');
 return message.slice(0,1800);
}
export function requireModel() {
 const s=getSettings();
 if(!s.llm.baseUrl || !s.llm.model)throw new Error('请先在API配置中填写主模型地址和模型ID');
 if(!s.llm.apiKey && !['localhost','127.0.0.1','[::1]'].includes(new URL(s.llm.baseUrl).hostname))throw new Error('请先配置主模型API Key');
 return s;
}
export async function testSettings(section:string) {
 const s=getSettings(),config=section==='embedding'?s.embedding:section==='ocr'?s.ocr:s.llm;
 if(section==='ocr'&&s.ocr.mode==='local')return {ok:true,message:'本地OCR状态由文档服务报告',local:true};
 if(section==='embedding'&&!s.embedding.enabled)throw new Error('Embedding尚未启用');
 if(!config.baseUrl || (section!=='ocr'&&!config.model))throw new Error('请填写服务地址和模型ID');
 const endpoint=section==='embedding'?'embeddings':'chat/completions';
 const requestBody=section==='ocr'?{image_base64:'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jRZkAAAAASUVORK5CYII=',language:'zh'}:section==='embedding'?{model:config.model,input:['财报检索连通检查']}:{model:config.model,messages:[{role:'user',content:'Reply with OK only.'}],max_tokens:16,stream:false,...(new URL(config.baseUrl).hostname==='api.deepseek.com'?{thinking:{type:'disabled'}}:{})};
 const start=performance.now();
 const target=section==='ocr'?config.baseUrl:config.baseUrl.replace(/\/$/,'')+'/'+endpoint;
 const response=await fetch(target,{method:'POST',headers:{'Content-Type':'application/json',...(config.apiKey?{Authorization:'Bearer '+config.apiKey}:{})},body:JSON.stringify(requestBody),redirect:'error',signal:AbortSignal.timeout(30000)});
 if(!response.ok)throw new Error('API连通检查失败，HTTP '+response.status+'：'+(await response.text()).slice(0,500));
 const result:any=await response.json();
 if(section==='embedding'&&!Array.isArray(result.data?.[0]?.embedding))throw new Error('服务没有返回有效向量');
 if(section==='ocr'&&typeof result.text!=='string')throw new Error('OCR服务应返回text字符串及可选lines数组');
 if(section==='llm'&&!result.choices?.[0]?.message)throw new Error('服务没有返回兼容格式的模型消息');
 return {ok:true,message:'连接成功，已完成真实请求',latencyMs:Math.round(performance.now()-start),model:result.model || config.model,dimensions:result.data?.[0]?.embedding?.length,usage:result.usage};
}
