/** Real public API -> Pi -> Tavily / financial tools. A development workflow test, not an accuracy holdout. */
import fs from 'node:fs/promises';
import path from 'node:path';
import {setTimeout as delay} from 'node:timers/promises';
const root=path.resolve(import.meta.dirname,'..'),args=process.argv.slice(2),arg=(k,d)=>args.includes(k)?args[args.indexOf(k)+1]:d;
const base=arg('--base-url','http://127.0.0.1:3001'),output=path.resolve(arg('--output','benchmark/results/research-workflow-v04.json'));
let ownsOutput=false;
let report={kind:'development_research_workflow',started_at:new Date().toISOString(),status:'running',checks:[],runs:[],requires_independent_evidence_review:true};
const save=()=>ownsOutput?fs.writeFile(output,JSON.stringify(report,null,2)):Promise.resolve();
async function api(route,body){const r=await fetch(base+route,{method:body?'POST':'GET',headers:body?{'Content-Type':'application/json'}:undefined,body:body?JSON.stringify(body):undefined,signal:AbortSignal.timeout(90000)});const v=await r.json();if(!r.ok)throw new Error('HTTP '+r.status+' '+route+': '+v.error?.message);return v;}
const check=(name,ok,evidence)=>{report.checks.push({name,status:ok?'passed':'failed',evidence});console.log(ok?'PASS':'FAIL',name);};
async function wait(id){const deadline=Date.now()+25*60000;let last=0;while(Date.now()<deadline){const run=await api('/api/runs/'+id);report.runs=report.runs.filter(r=>r.id!==id).concat(run);if(['completed','failed','cancelled'].includes(run.status)){await save();return run;}if(Date.now()-last>15000){console.log(run.status,run.stage,JSON.stringify(run.usage));last=Date.now();await save();}await delay(1500);}await api('/api/runs/'+id+'/cancel',{});throw Error('Workflow observation timeout; cancelled this run only');}
const tools=async id=>(await fs.readFile(path.join(root,'data/audit',id+'.jsonl'),'utf8')).trim().split('\n').map(JSON.parse).filter(e=>e.type==='tool_result').map(e=>e.data.name);
try{
 if(args.includes('--resume')){const prior=JSON.parse(await fs.readFile(output,'utf8'));if(['passed','failed'].includes(prior.status))throw Error('Terminal report is immutable; inspect it rather than resume.');report=prior;ownsOutput=true;}
 else{
  await fs.mkdir(path.dirname(output),{recursive:true});await fs.writeFile(output,JSON.stringify(report,null,2),{flag:'wx'});ownsOutput=true;
  const settings=await api('/api/settings');if(!settings.search?.hasKey)throw Error('Search not configured');
  const project=await api('/api/projects',{name:'升级开发验收 · 联网与研究成果'});report.project_id=project.id;
  const conversation=await api('/api/projects/'+project.id+'/conversations',{});report.conversation_id=conversation.id;
  const run=await api('/api/conversations/'+conversation.id+'/messages',{content:'查询柳工2025年半年度经营业绩的公司官方原文：通过联网搜索找到公司官方网站的新闻正文，读取并保存来源快照。依据这份保存的原文，给出营业总收入和归母净利润，并附引用。只做此任务，不下载PDF，不清洗其他文档。',documentIds:[],evaluation:{profile:'financial',budget_group_id:'research-network-'+Date.now(),budget:{max_model_calls:14,max_input_tokens:250000,max_output_tokens:100000,max_total_tokens:350000,max_wall_seconds:900}}});report.search_run_id=run.runId;await save();
 }
 const search=await wait(report.search_run_id),used=await tools(search.id);
 check('真实 Pi 调用搜索与原文归档',search.status==='completed'&&used.includes('search_web')&&used.includes('fetch_research_source'),{run_id:search.id,tools:used,usage:search.usage,error:search.error});
 const sources=(await api('/api/projects/'+report.project_id+'/research/sources')).sources;
 check('公司来源可从产品读取',sources.some(s=>new URL(s.url).hostname.endsWith('liugong.com')&&s.paragraph_count>0),sources.map(s=>({id:s.source_id,url:s.url,paragraphs:s.paragraph_count,sha256:s.sha256})));
 const chat=await api('/api/conversations/'+report.conversation_id);
 const answer=chat.messages.filter(m=>m.runId===search.id&&m.role==='assistant').map(m=>m.content||'').join('\n');
 const compact=answer.replace(/[，,\s]/g,'');
 check('营业收入与归母净利润符合官方发布数值',/181\.81|18181000000/.test(compact)&&/12\.3(?:0)?|1230000000/.test(compact),{answer,reference:'Official company 2025H1 release, checked independently of the agent task; units and scope require human review.'});
 check('已保存回复包含可打开网页快照引用',chat.messages.some(m=>m.runId===search.id&&m.sources?.some(s=>s.url&&s.snapshotUrl)),chat.messages.filter(m=>m.runId===search.id).map(m=>({content:m.content,sources:m.sources})));
 report.status=report.checks.every(c=>c.status==='passed')?'passed':'failed';
}catch(error){report.status='failed';report.error=error.message;console.error('FAIL',error.message);}
finally{report.finished_at=new Date().toISOString();await save();if(report.status!=='passed')process.exitCode=1;console.log('REPORT',output);}
