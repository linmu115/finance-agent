import fs from 'node:fs/promises';
import path from 'node:path';
import {setTimeout as delay} from 'node:timers/promises';
import {decimalKey,digest} from './validation_utils.mjs';
const root=path.resolve(import.meta.dirname,'..'),base='http://127.0.0.1:3001';
const full=process.argv.includes('--full-report'),outputName=full?'pi-full-report-chart-v03':'pi-semantic-chart-v03';
const quick=JSON.parse(await fs.readFile(path.join(root,full?'benchmark/results/pi-full-report-v03.json':'benchmark/results/pi-workflow-v03-quick.json'),'utf8'));
const document=full?{id:quick.document_id,conversation_id:quick.conversation_id}:quick.documents.find(d=>d.file.endsWith('.pdf'));
const output=path.join(root,'benchmark/results',outputName+'.json');
let report={status:'running',project_id:quick.project_id,conversation_id:document.conversation_id,document_id:document.id,started_at:new Date().toISOString(),checks:[]};
const save=()=>fs.writeFile(output,JSON.stringify(report,null,2));
const request=async(route,body)=>{const res=await fetch(base+route,{...(body?{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)}:{}),signal:AbortSignal.timeout(90000)});if(!res.ok)throw Error('HTTP '+res.status);return res.json();};
const check=(name,ok,evidence)=>report.checks.push({name,status:ok?'passed':'failed',evidence});
try{
 const resumed=process.argv.includes('--resume')?JSON.parse(await fs.readFile(output,'utf8')):null;
 if(resumed){
  const snapshot=path.join(root,'benchmark/results',outputName+'-before-exact-review.json');
  await fs.writeFile(snapshot,JSON.stringify(resumed,null,2),{flag:'wx'}).catch(error=>{if(error.code!=='EEXIST')throw error;});
 }
 const started=resumed?{runId:resumed.run_id}:await request(`/api/conversations/${document.conversation_id}/messages`,{content:'请使用这个项目已经入库的贵州茅台2024年四个季度营业收入，查询数据库，在独立科学计算容器中画四季度柱状图，标出年份、季度、人民币亿元单位，输出中文PNG和chart_data.json。JSON格式为 {"unit":"CNY","data":[{"period":"2024-Q1","value":"原始元的精确十进制字符串"}]}，四个季度各一条，勿将同比增长率当金额；PNG纵轴按亿元显示。从现有数据读取，不要重新清洗。',documentIds:[]});
 if(resumed){report.started_at=resumed.started_at;report.rescored_at=new Date().toISOString();report.harness_correction=resumed.harness_correction||'Rescoring the same completed model run and artifacts.';report.scorer_revision='Exact decimal strings, currency/scope/source checks and artifact byte hashes; no new model call.';}
 report.run_id=started.runId;await save();
 const deadline=Date.now()+600000;let run;
 while(Date.now()<deadline){run=await request('/api/runs/'+started.runId);if(['completed','failed','cancelled'].includes(run.status))break;await delay(2000);}
 report.run=run;check('已持久化Pi会话可继续查询并完成',run.status==='completed',{status:run.status,error:run.error});
 check('使用结构化查询和真实容器工具',['run_analysis','get_analysis_status'].every(n=>run.tools.some(t=>t.name===n&&t.status==='completed'))&&run.tools.some(t=>['query_financial_data','get_financial_metrics'].includes(t.name)&&t.status==='completed'),{tool_names:[...new Set(run.tools.map(t=>t.name))]});
 const chat=await request('/api/conversations/'+document.conversation_id),answer=chat.messages.find(m=>m.runId===run.id&&m.role==='assistant');report.answer=answer;
 const artifacts=answer?.artifacts||[],json=artifacts.find(a=>a.name==='chart_data.json'),png=artifacts.find(a=>a.name.endsWith('.png'));
 check('返回JSON与PNG可下载产物',!!json&&!!png,{artifacts});
 if(json){
  const data=await request(json.url);report.chart_data=data;report.chart_data_sha256=digest(data);
  const filters={document_id:document.id,metric:'revenue',periods:['2024-Q1','2024-Q2','2024-Q3','2024-Q4']};
  const actual=await request(`/api/projects/${quick.project_id}/financial-data?filters=${encodeURIComponent(JSON.stringify(filters))}&limit=1000`);
  const checks=['2024-Q1','2024-Q2','2024-Q3','2024-Q4'].map(period=>{
   const found=data.data?.filter(d=>d.period===period)||[],facts=actual.items.filter(f=>f.period===period&&f.metric==='revenue');
   const valid=facts.filter(f=>f.normalized_unit==='CNY'&&f.currency==='CNY'&&f.scope==='consolidated_CAS'&&f.document_id===document.id&&f.source_ref?.document_id===document.id&&f.source_ref?.page===(full?6:2)&&f.source_ref?.table_id&&f.source_ref?.row&&f.source_ref?.column&&f.source_ref?.normalization?.engine==='LangExtract'&&Object.keys(f.dimensions||{}).length===0);
   const values=[...new Set(facts.map(f=>decimalKey(f.value)))],chart=decimalKey(found[0]?.value);
   return {period,chart:found.map(f=>f.value),source:facts.map(f=>({value:f.value,currency:f.currency,scope:f.scope,source_ref:f.source_ref})),passed:found.length===1&&typeof found[0].value==='string'&&chart!==null&&valid.length>0&&valid.length===facts.length&&values.length===1&&values[0]===chart};
  });
  check('四季度绘图数据与数据库原值一致',data.unit==='CNY'&&data.data?.length===4&&checks.every(c=>c.passed),checks);
  const independent=(await fs.readFile(path.join(root,'benchmark/versions/v0.3-normalization/gold.jsonl'),'utf8')).trim().split('\n').map(JSON.parse).find(g=>g.id==='native_revenue_q3');
  const q3=data.data?.find(d=>d.period==='2024-Q3');
  check('图表第三季度数值同时符合独立原文金标准',!!independent&&!!q3&&decimalKey(q3.value)===decimalKey(independent.value)&&data.unit===independent.currency,{period:'2024-Q3',expected:independent?.value,actual:q3?.value,original_report_page:independent?.original_page});
 }
 if(png){
  const res=await fetch(base+png.url);if(!res.ok)throw Error('PNG download failed');const bytes=Buffer.from(await res.arrayBuffer());
  const header=bytes.length>24&&bytes.subarray(0,8).equals(Buffer.from([137,80,78,71,13,10,26,10]));
  check('图表下载返回有效PNG及实际尺寸',header&&bytes.readUInt32BE(16)>100&&bytes.readUInt32BE(20)>100,{bytes:bytes.length,width:header?bytes.readUInt32BE(16):null,height:header?bytes.readUInt32BE(20):null,mime:res.headers.get('content-type')});
  const dest=path.join(root,'benchmark/results',outputName+'.png');await fs.writeFile(dest,bytes);report.png_path=dest;report.png_sha256=digest(bytes);
 }
 report.status=report.checks.every(c=>c.status==='passed')?'passed':'failed';
}catch(error){report.status='failed';report.error=String(error.message).replace(/sk-[A-Za-z0-9_-]+/g,'[REDACTED]');}
report.finished_at=new Date().toISOString();await save();console.log(JSON.stringify({status:report.status,checks:report.checks,error:report.error,png:report.png_path}));if(report.status!=='passed')process.exitCode=1;
