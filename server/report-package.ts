import {evaluationIsolation} from './evaluation-isolation.js';
import {createReadStream} from 'node:fs';
import {createInterface} from 'node:readline';
import path from 'node:path';
import {createElement} from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
import Markdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import {DATA} from './config.js';
import {registerNumericTables} from './numeric-tables.js';
import type {Conversation} from './types.js';
import type {FinanceService} from './mcp.js';

/** Read only this conversation's persisted turns. Repairs replace, scenarios retain both versions. */
export async function reportSnapshot(chat:Conversation,auditRoot=path.join(DATA,'audit')){
 const turns:any[]=[];
 for(const message of chat.messages){
  if(message.role!=='assistant'||message.status!=='completed')continue;
  const tables:Record<string,any>={};let ingestion=false;
  if(message.runId){
   const lines=createInterface({input:createReadStream(path.join(auditRoot,message.runId+'.jsonl'),{encoding:'utf8'}),crlfDelay:Infinity});
   for await(const line of lines){
    if(!line.trim())continue;const row=JSON.parse(line);
    if(row.type!=='tool_result'||row.data.messageId&&row.data.messageId!==message.id)continue;
    if(row.data.name==='process_documents')ingestion=true;
    const data=row.data.result?.data;
    if(data)registerNumericTables(tables,data);
   }
  }
  if(!ingestion)turns.push({id:message.id,run_id:message.runId,created_at:message.createdAt,body:message.content,tables,sources:message.sources||[],artifacts:message.artifacts||[]});
 }
 if(!turns.length)throw new Error('当前会话还没有已完成的分析回答。');
 return {title:chat.title,conversation_id:chat.id,project_id:chat.projectId,turns};
}
const exportsInFlight=new Map<string,Promise<any>>();
export function exportReportPackage(service:FinanceService,chat:Conversation){
 if(chat.evaluationProfile==='original_pi')throw Object.assign(new Error('original_pi 不提供标准报告包；自行生成的文件仍可下载。'),{status:400});
 const key=JSON.stringify([chat.projectId,chat.id,chat.evaluationIsolationKey]);
 const existing=exportsInFlight.get(key);if(existing)return existing;
 const pending=evaluationIsolation.run(chat.evaluationIsolationKey,()=>exportScopedReportPackage(service,chat))
  .finally(()=>exportsInFlight.delete(key));
 exportsInFlight.set(key,pending);return pending;
}
async function exportScopedReportPackage(service:FinanceService,chat:Conversation){
 const snapshot=await reportSnapshot(chat);
 const prepared=await service.call('prepare_report_package',{project_id:chat.projectId,snapshot});
 const html=renderToStaticMarkup(createElement(Markdown,{remarkPlugins:[remarkGfm],skipHtml:true,
  components:{img:({src,alt})=>src?.startsWith('assets/')?createElement('img',{src,alt}):createElement('p',null,alt||'图表', '（见原会话附件）')}},prepared.data.markdown));
 return (await service.call('finish_report_package',{project_id:chat.projectId,package_id:prepared.data.package_id,html})).data;
}
