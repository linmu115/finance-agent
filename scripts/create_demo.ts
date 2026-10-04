// A real, user-visible walkthrough using the three public annual reports.
import {readFile,writeFile,mkdir} from 'node:fs/promises';
import {setTimeout as delay} from 'node:timers/promises';
import path from 'node:path';
import {ROOT} from '../server/config.js';
const fresh=process.argv.includes('--fresh');
const base='http://127.0.0.1:3001',output=path.join(ROOT,'benchmark/results',fresh?'demo-latest.json':'demo.json');
async function api(endpoint:string,method='GET',body?:any):Promise<any>{
 const response=await fetch(base+endpoint,{method,...(body instanceof FormData?{body}:body?{headers:{'Content-Type':'application/json'},body:JSON.stringify(body)}:{})});
 const value=await response.json();if(!response.ok)throw new Error('Application HTTP '+response.status);return value;
}
let record:any;
try{record=JSON.parse(await readFile(output,'utf8'));}catch{}
if(record?.status==='completed'){console.log(JSON.stringify({projectId:record.projectId,conversationId:record.conversationId,status:record.status}));process.exit(0);}
if(!record){
 const project=await api('/api/projects','POST',{name:fresh?'财报研究 · 三公司对比':'财报示例 · 茅台、美的、伊利'});
 const form=new FormData();
 for(const file of ['moutai_2024.pdf','midea_2024.pdf','yili_2024.pdf'])form.append('files',new Blob([await readFile(path.join(ROOT,'benchmark/agent_input/reports',file))],{type:'application/pdf'}),file);
 const uploaded=await api('/api/projects/'+project.id+'/uploads','POST',form);
 const chat=await api('/api/projects/'+project.id+'/conversations','POST',{});
 const run=await api('/api/conversations/'+chat.id+'/messages','POST',{
  content:'请分析附件三家公司的完整2024年报：分别查出2023年和2024年合并营业收入，列出金额、单位和原文物理页引用。使用计算工具算出各公司收入同比。再在独立分析容器绘制三家公司2023/2024营业收入分组柱状图，统一用亿元、中文标签、纵轴从0开始，并输出可下载PNG和chart_data.json。chart_data要保留人民币元的原值、公司和年份以便复核。请直接完成任务；若容器代码出错可依据日志修正，不能用估计值补数据。',
  documentIds:uploaded.documents.map((d:any)=>d.id)
 });
 record={projectId:project.id,conversationId:chat.id,runId:run.runId,documentIds:uploaded.documents.map((d:any)=>d.id),status:'running',createdAt:new Date().toISOString(),purpose:'Real three-report application walkthrough; not a benchmark score'};
 await mkdir(path.dirname(output),{recursive:true});await writeFile(output,JSON.stringify(record,null,2),'utf8');
}
const deadline=Date.now()+25*60000;
while(Date.now()<deadline){
 const run=await api('/api/runs/'+record.runId);
 if(['completed','failed','cancelled'].includes(run.status)){
  const chat=await api('/api/conversations/'+record.conversationId);
  Object.assign(record,{status:run.status,finishedAt:new Date().toISOString(),run,conversation:chat});
  await writeFile(output,JSON.stringify(record,null,2),'utf8');
  console.log(JSON.stringify({projectId:record.projectId,conversationId:record.conversationId,status:run.status,toolEvents:run.tools?.length,usage:run.usage}));process.exit(run.status==='completed'?0:1);
 }
 await delay(2000);
}
throw new Error('Walkthrough remains active; inspect its existing run ID before retrying.');
