import { createHash, randomUUID } from 'node:crypto';
import { lookup } from 'node:dns/promises';
import { request as httpsRequest } from 'node:https';
import { request as httpRequest } from 'node:http';
import { isIP } from 'node:net';
import { mkdir, readFile, writeFile, readdir, unlink } from 'node:fs/promises';
import { spawn } from 'node:child_process';
import path from 'node:path';
import { Readability } from '@mozilla/readability';
import { parseHTML } from 'linkedom';
import { z } from 'zod';
import { DATA } from './config.js';
import type { SearchConfig, Envelope } from './types.js';
import { publishFile } from './immutable-files.js';

const identifier = z.string().regex(/^[A-Za-z0-9_-]{1,100}$/);
const day = z.string().regex(/^\d{4}-\d{2}-\d{2}$/);
const searchInput = z.object({query:z.string().trim().min(1).max(1500),search_depth:z.enum(['basic','advanced']).optional(),max_results:z.number().int().min(1).max(20).optional(),include_domains:z.array(z.string().regex(/^[a-z0-9.-]+$/i)).max(12).optional(),as_of:day.optional()});
export type SearchInput=z.infer<typeof searchInput>;
export interface SearchHit {title:string;url:string;snippet:string;published_at:string|null;date_basis:'search_provider'|'unknown';score:number|null}
export interface SearchResult {provider:string;query:string;search_depth:string;retrieved_at:string;as_of:string|null;results:SearchHit[];usage:unknown;provider_request_id:string|null}
export async function searchWeb(config:SearchConfig|undefined, input:SearchInput, signal?:AbortSignal, fetcher:typeof fetch=fetch):Promise<SearchResult> {
 const args=searchInput.parse(input);
 if(!config?.apiKey)throw new Error('请在 API 配置的联网搜索页填写搜索服务密钥');
 const base=new URL(config.baseUrl);if(base.protocol!=='https:'||base.username||base.password)throw new Error('搜索 API 需要 HTTPS 地址');
 const count=args.max_results??config.maxResults;
 let url:string,init:RequestInit;
 if(config.provider==='tavily'){
  url=base.href.replace(/\/$/,'')+'/search';
  init={method:'POST',headers:{'Content-Type':'application/json',Authorization:'Bearer '+config.apiKey},body:JSON.stringify({query:args.query,search_depth:args.search_depth??'basic',max_results:count,include_answer:false,include_raw_content:false,include_published_date:true,include_usage:true,auto_parameters:false,...(args.include_domains?.length?{include_domains:args.include_domains}:{}),...(args.as_of?{end_date:args.as_of,filter_by_published_date:true}:{})})};
 }else{
  const endpoint=new URL(base.href.replace(/\/$/,'')+'/res/v1/web/search');endpoint.searchParams.set('q',args.query+(args.include_domains?.length?' ('+args.include_domains.map(x=>'site:'+x).join(' OR ')+')':''));endpoint.searchParams.set('count',String(count));
  if(args.as_of)endpoint.searchParams.set('freshness','2000-01-01to'+args.as_of);
  url=endpoint.href;init={headers:{Accept:'application/json','X-Subscription-Token':config.apiKey}};
 }
 const response=await fetcher(url,{...init,redirect:'error',signal:signal?AbortSignal.any([signal,AbortSignal.timeout(45000)]):AbortSignal.timeout(45000)});
 // Provider errors must never echo a credential, request header or arbitrary response body.
 if(!response.ok)throw new Error('搜索服务请求失败，HTTP '+response.status);
 const payload:any=await response.json(),items=config.provider==='tavily'?payload.results:payload.web?.results;
 if(!Array.isArray(items))throw new Error('搜索服务没有返回有效结果列表');
 const results:SearchHit[]=items.slice(0,count).filter((x:any)=>{try{return ['https:','http:'].includes(new URL(x.url).protocol);}catch{return false;}}).map((x:any)=>({title:String(x.title||x.url),url:x.url,snippet:String(x.content??x.description??''),published_at:x.published_date??x.page_age??null,date_basis:x.published_date||x.page_age?'search_provider':'unknown',score:typeof x.score==='number'?x.score:null}));
 return {provider:config.provider,query:args.query,search_depth:config.provider==='tavily'?(args.search_depth??'basic'):'provider_default',retrieved_at:new Date().toISOString(),as_of:args.as_of??null,results,usage:payload.usage??null,provider_request_id:payload.request_id??null};
}

export function publicAddress(address:string):boolean {
 const ip=address.toLowerCase().replace(/^\[|\]$/g,'');
 if(ip.startsWith('::ffff:'))return publicAddress(ip.slice(7));
 if(isIP(ip)===4){const a=ip.split('.').map(Number);return !(a[0]===0||a[0]===10||a[0]===127||a[0]>=224||a[0]===169&&a[1]===254||a[0]===172&&a[1]>=16&&a[1]<=31||a[0]===192&&[0,168].includes(a[1])||a[0]===100&&a[1]>=64&&a[1]<=127||a[0]===198&&[18,19].includes(a[1]));}
 return isIP(ip)===6&&/^[23]/.test(ip)&&!ip.startsWith('2001:db8:');
}
export interface Download {body:Buffer;url:string;contentType:string;headers:Record<string,string|string[]|undefined>;retrieval?:{method:'tavily_extract';representation:'provider_extracted_text';provider_request_id:string|null;usage:unknown;direct_error:string}}
export async function downloadWithReader(url:string,config:SearchConfig|undefined,signal?:AbortSignal):Promise<Download>{
 try{return await downloadPublic(url,signal);}catch(error:any){
  signal?.throwIfAborted();
  const eligible=['UNABLE_TO_VERIFY_LEAF_SIGNATURE','CERT_HAS_EXPIRED','UNABLE_TO_GET_ISSUER_CERT_LOCALLY','ECONNRESET','ETIMEDOUT','ENOTFOUND','EAI_AGAIN'].includes(error.code)||/读取原文超时|原文服务器返回 HTTP (403|429|5\d\d)/.test(error.message||'');
  if(!eligible||config?.provider!=='tavily'||!config.apiKey)throw error;
  return extractWithTavily(url,config,signal,error.code||error.message);
 }
}
export async function extractWithTavily(url:string,config:SearchConfig,signal?:AbortSignal,directError='direct_reader_unavailable',fetcher:typeof fetch=fetch):Promise<Download>{
 const target=new URL(url);if(!['http:','https:'].includes(target.protocol)||target.username||target.password||isIP(target.hostname.replace(/^\[|\]$/g,''))&&!publicAddress(target.hostname))throw new Error('只能读取公开来源');
 const response=await fetcher(config.baseUrl.replace(/\/$/,'')+'/extract',{method:'POST',headers:{'Content-Type':'application/json',Authorization:'Bearer '+config.apiKey},body:JSON.stringify({urls:[url],extract_depth:'basic',format:'text',include_usage:true,timeout:30}),redirect:'error',signal:signal?AbortSignal.any([signal,AbortSignal.timeout(45000)]):AbortSignal.timeout(45000)});
 if(!response.ok)throw new Error('原文提取服务请求失败，HTTP '+response.status);
 const payload:any=await response.json(),item=payload.results?.find((x:any)=>typeof x.raw_content==='string'&&x.raw_content.trim());
 if(!item)throw new Error('原文提取服务未读取到该来源正文，不能以搜索摘要代替原文');
 return {body:Buffer.from(item.raw_content,'utf8'),url:item.url||url,contentType:'text/plain; charset=utf-8',headers:{},retrieval:{method:'tavily_extract',representation:'provider_extracted_text',provider_request_id:payload.request_id||null,usage:payload.usage||null,direct_error:String(directError).slice(0,200)}};
}
export async function downloadPublic(rawUrl:string,signal?:AbortSignal):Promise<Download>{
 let url=new URL(rawUrl);
 for(let redirect=0;redirect<=5;redirect++){
  if(!['https:','http:'].includes(url.protocol)||url.username||url.password)throw new Error('只能读取不带凭据的公开 HTTP/HTTPS 来源');
  const hostname=url.hostname.replace(/^\[|\]$/g,'');
  const addresses=isIP(hostname)?[{address:hostname,family:isIP(hostname)}]:await lookup(hostname,{all:true});
  if(!addresses.length||addresses.some(x=>!publicAddress(x.address)))throw new Error('来源地址不能指向本机或内网');
  const pinned=addresses[0];
  const result=await new Promise<{status:number;location?:string;download:Download}>((resolve,reject)=>{
   const req=(url.protocol==='https:'?httpsRequest:httpRequest)(url,{method:'GET',signal,headers:{'User-Agent':'FinancialResearchWorkbench/0.4 (+source-archive)','Accept':'text/html,application/pdf,text/plain;q=0.9','Accept-Encoding':'identity'},lookup:((_host:any,options:any,callback:any)=>options?.all?callback(null,[{address:pinned.address,family:pinned.family}]):callback(null,pinned.address,pinned.family)) as any},res=>{
    const chunks:Buffer[]=[];let size=0;
    res.on('data',(chunk:Buffer)=>{size+=chunk.length;if(size>50*1024*1024){req.destroy(new Error('来源超过 50 MB，请下载后作为附件上传'));return;}chunks.push(chunk);});
    res.on('error',reject);res.on('end',()=>resolve({status:res.statusCode||0,location:res.headers.location,download:{body:Buffer.concat(chunks),url:url.href,contentType:String(res.headers['content-type']||''),headers:res.headers}}));
   });req.setTimeout(45000,()=>req.destroy(new Error('读取原文超时')));req.on('error',reject);req.end();
  }).catch(async(error:any)=>{
   // Schannel can build issuer chains from the Windows intermediate store/AIA;
   // OpenSSL does not. Both paths keep certificate verification enabled.
   if(process.platform==='win32'&&['UNABLE_TO_VERIFY_LEAF_SIGNATURE','UNABLE_TO_GET_ISSUER_CERT_LOCALLY'].includes(error.code))return windowsDownload(url.href,pinned.address,signal).catch(nativeError=>{signal?.throwIfAborted();throw Object.assign(new Error(nativeError.message),{code:error.code});});
   throw error;
  });
  if([301,302,303,307,308].includes(result.status)&&result.location){url=new URL(result.location,url);continue;}
  if(result.status<200||result.status>=300)throw new Error('原文服务器返回 HTTP '+result.status);
  return result.download;
 }
 throw new Error('原文重定向次数过多');
}
async function windowsDownload(url:string,address:string,signal?:AbortSignal):Promise<{status:number;location?:string;download:Download}>{
 const dir=path.join(DATA,'runtime','reader-temp');await mkdir(dir,{recursive:true});const target=path.join(dir,randomUUID()+'.response');
 try{
  const metadata=await new Promise<any>((resolve,reject)=>{
   const parsed=new URL(url),host=parsed.hostname.replace(/^\[|\]$/g,''),port=parsed.port||(parsed.protocol==='https:'?'443':'80');
   // Windows' bundled curl uses Schannel. Disable curlrc, ambient proxies and
   // automatic redirects so the same public-address pinning applies here.
   const child=spawn(path.join(process.env.SystemRoot||'C:\\Windows','System32','curl.exe'),['-q','--silent','--show-error','--noproxy','*','--proto','=http,https','--max-time','45','--max-filesize','52428800','--resolve',`${host}:${port}:${address.includes(':')?'['+address+']':address}`,'--user-agent','FinancialResearchWorkbench/0.4 (+source-archive)','--header','Accept-Encoding: identity','--output',target,'--write-out','%{json}','--url',url],{windowsHide:true,stdio:['ignore','pipe','pipe'],signal});
   let out='';child.stdout.on('data',b=>out+=b.toString('utf8'));child.stderr.resume();const timer=setTimeout(()=>{child.kill();reject(new Error('Windows 原文读取超时'));},55000);
   child.on('error',reject);child.on('close',code=>{clearTimeout(timer);if(code!==0)reject(new Error('Windows 原文读取失败，证书校验或网络请求未通过'));else try{resolve(JSON.parse(out));}catch{reject(new Error('Windows 原文读取返回无效'));}});
  });
  const body=await readFile(target);if(body.length>50*1024*1024)throw new Error('来源超过 50 MB，请下载后作为附件上传');
  return {status:metadata.http_code,location:metadata.redirect_url||undefined,download:{body,url,contentType:metadata.content_type||'',headers:{}}};
 }finally{await unlink(target).catch(()=>{});}
}

export interface SourceSnapshot {source_id:string;project_id:string;url:string;requested_url:string;title:string;kind:'web'|'pdf'|'text';retrieved_at:string;published_at:string|null;publication_evidence:string|null;modified_at:string|null;sha256:string;content_type:string;byte_count:number;paragraphs:{id:string;text:string;start:number;end:number}[];links:{title:string;url:string}[];document_id?:string;as_of:string|null;temporal_status:'dated_within_cutoff'|'dated_after_cutoff'|'undated'|'no_cutoff';date_caveat:string;retrieval?:Download['retrieval'];content_representation:'original_response_bytes'|'provider_extracted_text'}
const digest=(body:Buffer|string)=>createHash('sha256').update(body).digest('hex');
function decodeBody(download:Download){
 const probe=download.body.subarray(0,4096).toString('latin1');
 const charset=/charset\s*=\s*["']?([\w-]+)/i.exec(download.contentType)?.[1]||/charset\s*=\s*["']?([\w-]+)/i.exec(probe)?.[1]||'utf-8';
 try{return new TextDecoder(charset).decode(download.body);}catch{return download.body.toString('utf8');}
}
export function extractSnapshot(projectId:string,requestedUrl:string,download:Download,asOf?:string):SourceSnapshot {
 const pdf=download.body.subarray(0,5).toString()==='%PDF-',html=!pdf&&(/html/i.test(download.contentType)||/<html[\s>]/i.test(download.body.subarray(0,4096).toString()));
 const text=pdf?'':decodeBody(download);let title=new URL(download.url).pathname.split('/').pop()||new URL(download.url).hostname;
 let published:string|null=null,publicationEvidence:string|null=null,modified:string|null=null,blocks:string[]=[],links:{title:string;url:string}[]=[];
 if(html){
  const {document}=parseHTML(text);const base=document.createElement('base');base.setAttribute('href',download.url);document.head?.prepend(base);
  const dateNode=document.querySelector('meta[property="article:published_time"],meta[name="date"],meta[name="publishdate"],meta[itemprop="datePublished"]');
  published=dateNode?.getAttribute('content')??null;publicationEvidence=dateNode?.outerHTML??null;
  modified=document.querySelector('meta[property="article:modified_time"]')?.getAttribute('content')??null;
  if(!published){const t=document.querySelector('time[datetime]');if(t){published=t.getAttribute('datetime');publicationEvidence=t.outerHTML;}}
  for(const a of Array.from(document.querySelectorAll('a[href]'))){try{const u=new URL(a.getAttribute('href')!,download.url);if(['http:','https:'].includes(u.protocol)&&!links.some(x=>x.url===u.href))links.push({title:(a.textContent||'').trim().slice(0,300),url:u.href});}catch{}}
  const parsed=new Readability(document.cloneNode(true) as any,{charThreshold:80}).parse();
  title=parsed?.title||document.querySelector('title')?.textContent||title;
  const content=parseHTML('<html><body>'+(parsed?.content||document.querySelector('main,article')?.outerHTML||document.body?.innerHTML||'')+'</body></html>').document;
  content.querySelectorAll('script,style,nav,footer,header,noscript,form').forEach(x=>x.remove());
  blocks=Array.from(content.querySelectorAll('h1,h2,h3,h4,p,li,tr,blockquote')).filter(x=>!x.querySelector('p,li,tr,blockquote')).map(x=>x.tagName==='TR'?Array.from(x.querySelectorAll('th,td')).map(c=>c.textContent?.trim()).join(' | '):(x.textContent||'').trim()).filter(Boolean);
  if(!blocks.length)blocks=[content.body?.textContent?.trim()||''];
 }else if(!pdf)blocks=text.split(/\n\s*\n/).map(x=>x.trim()).filter(Boolean);
 let cursor=0;const paragraphs:SourceSnapshot['paragraphs']=[];
 for(const text of blocks.filter(Boolean)){
  for(let offset=0;offset<text.length;){let end=Math.min(offset+4096,text.length);const last=text.charCodeAt(end-1);if(end<text.length&&last>=0xd800&&last<=0xdbff)end--;
   paragraphs.push({id:'p'+(paragraphs.length+1),text:text.slice(offset,end),start:cursor+offset,end:cursor+end});offset=end;
  }cursor+=text.length+2;
 }
 const validDate=published&&!Number.isNaN(Date.parse(published))?new Date(published).toISOString():null;
 return {source_id:'web_'+randomUUID(),project_id:projectId,url:download.url,requested_url:requestedUrl,title,kind:pdf?'pdf':html?'web':'text',retrieved_at:new Date().toISOString(),published_at:validDate,publication_evidence:publicationEvidence,modified_at:modified,sha256:digest(download.body),content_type:download.contentType,byte_count:download.body.length,paragraphs,links,as_of:asOf??null,temporal_status:!asOf?'no_cutoff':!validDate?'undated':validDate.slice(0,10)>asOf?'dated_after_cutoff':'dated_within_cutoff',date_caveat:'页面日期来自发布者标注，不保证当前网页与历史时点内容相同；历史研究还需核验修订日期与当时披露版本。',retrieval:download.retrieval,content_representation:download.retrieval?'provider_extracted_text':'original_response_bytes'};
}

export class ResearchStore {
 constructor(readonly root=path.join(DATA,'research')){}
 private folder(projectId:string,kind='sources'){return path.join(this.root,identifier.parse(projectId),kind);}
 private async put(projectId:string,kind:string,id:string,value:any){const dir=this.folder(projectId,kind);await publishFile(path.join(dir,identifier.parse(id)+'.json'),JSON.stringify(value,null,2));}
 async search(projectId:string,config:SearchConfig|undefined,input:SearchInput,signal?:AbortSignal){const result=await searchWeb(config,input,signal);const query_id='query_'+randomUUID();await this.put(projectId,'queries',query_id,{query_id,...result});return {query_id,...result};}
 async saveSnapshot(projectId:string,url:string,options:{as_of?:string;signal?:AbortSignal;download?:(url:string,signal?:AbortSignal)=>Promise<Download>;registerPdf?:(filename:string,name:string)=>Promise<string>}={}){
  identifier.parse(projectId);if(options.as_of)day.parse(options.as_of);
  const download=await (options.download??downloadPublic)(url,options.signal),snapshot=extractSnapshot(projectId,url,download,options.as_of);
  const blobDir=this.folder(projectId,'blobs');await mkdir(blobDir,{recursive:true});const filename=path.join(blobDir,snapshot.sha256+(snapshot.kind==='pdf'?'.pdf':'.bin'));
  try{await publishFile(filename,download.body);}catch(e:any){if(e.code!=='EEXIST')throw e;}
  if(snapshot.kind==='pdf'&&options.registerPdf){
   let name=new URL(download.url).pathname.split('/').pop()||'网上公告.pdf';try{name=decodeURIComponent(name);}catch{}
   name=name.replace(/[\\/:*?"<>|\x00-\x1f]/g,'_').slice(0,210);if(!/\.pdf$/i.test(name))name+='.pdf';
   snapshot.document_id=await options.registerPdf(filename,name);
  }
  await this.put(projectId,'sources',snapshot.source_id,snapshot);return snapshot;
 }
 async get(projectId:string,id:string):Promise<SourceSnapshot>{return JSON.parse(await readFile(path.join(this.folder(projectId),identifier.parse(id)+'.json'),'utf8'));}
 async latestVersion(projectId:string,id:string){const original=await this.get(projectId,id),latest=(await this.list(projectId)).filter(x=>x.url===original.url).sort((a,b)=>b.retrieved_at.localeCompare(a.retrieved_at))[0];return latest?.sha256??original.sha256;}
 async list(projectId:string){let files:string[];try{files=await readdir(this.folder(projectId));}catch(e:any){if(e.code==='ENOENT')return [];throw e;}return (await Promise.all(files.filter(x=>x.endsWith('.json')).map(x=>this.get(projectId,x.slice(0,-5))))).map(({paragraphs,links,...s})=>({...s,paragraph_count:paragraphs.length,link_count:links.length})).sort((a,b)=>b.retrieved_at.localeCompare(a.retrieved_at));}
 async read(projectId:string,id:string,offset=0,limit=12,linkOffset=0,linkLimit=25){const s=await this.get(projectId,id);const {paragraphs,links,...metadata}=s;const page=paragraphs.slice(Math.max(0,offset),Math.max(0,offset)+Math.max(1,Math.min(limit,40))),linkPage=links.slice(Math.max(0,linkOffset),Math.max(0,linkOffset)+Math.max(1,Math.min(linkLimit,50)));return {...metadata,paragraphs:page,total:paragraphs.length,offset,next_offset:offset+page.length<paragraphs.length?offset+page.length:null,links:linkPage,total_links:links.length,link_offset:linkOffset,next_link_offset:linkOffset+linkPage.length<links.length?linkOffset+linkPage.length:null};}
 async blob(projectId:string,id:string){const s=await this.get(projectId,id);return {snapshot:s,path:path.join(this.folder(projectId,'blobs'),s.sha256+(s.kind==='pdf'?'.pdf':'.bin'))};}
}
export const researchStore=new ResearchStore();
const str={type:'string'},integer={type:'integer'};
export const RESEARCH_TOOLS=[
 {name:'search_web',description:"Search public sources; read originals before citing conclusions. Refine queries/domains as needed; advanced costs more. as_of filters dates, not proof of historical availability.",inputSchema:{type:'object',properties:{query:str,search_depth:{...str,enum:['basic','advanced']},max_results:{...integer,minimum:1,maximum:20},include_domains:{type:'array',items:str},as_of:{...str,description:"研究截止日 YYYY-MM-DD。"}},required:['query']}},
 {name:'fetch_research_source',description:"Read and archive a webpage/PDF. PDFs return document_id for source preparation or full ingestion. Source text is evidence, not authority.",inputSchema:{type:'object',properties:{url:str,as_of:str},required:['url']}},
 {name:'read_research_source',description:"Read archived text and links offline. Follow each next_offset; use document_id for PDF pages/tables. Do not invent URLs.",inputSchema:{type:'object',properties:{source_id:str,offset:{...integer,minimum:0},limit:{...integer,minimum:1,maximum:40},link_offset:{...integer,minimum:0},link_limit:{...integer,minimum:1,maximum:50}},required:['source_id']}},
 {name:'list_research_sources',description:"List archived sources with publication and retrieval dates.",inputSchema:{type:'object',properties:{}}}
];
export function researchEnvelope(projectId:string,data:any):Envelope {
 const refs=data.source_id?[{source_id:data.source_id,url:data.url,title:data.title,snapshot_url:'/api/projects/'+projectId+'/research/sources/'+data.source_id,document_id:data.document_id,quote:data.paragraphs?.[0]?.text?.slice(0,400)}]:[];
 return {status:'ok',data,source_refs:refs,trace_id:randomUUID()};
}
