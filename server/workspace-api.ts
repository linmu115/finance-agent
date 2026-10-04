import type { Express } from 'express';
import { readFile, writeFile, mkdir, stat, readdir } from 'node:fs/promises';
import { spawn } from 'node:child_process';
import { randomUUID } from 'node:crypto';
import path from 'node:path';
import {setTimeout as delay} from 'node:timers/promises';
import { ROOT as DEFAULT_ROOT, PORT as DEFAULT_PORT, redactError } from './config.js';
import type { FinanceService } from './mcp.js';

const validId=(value:any)=>{if(typeof value!=='string'||!/^[A-Za-z0-9_-]{1,100}$/.test(value))throw new Error('无效的标识');return value;};
const route=(fn:(req:any,res:any)=>Promise<any>)=>(req:any,res:any,next:any)=>Promise.resolve(fn(req,res)).catch(next);
const csvCell=(value:any)=>{
 let text=typeof value==='object'?JSON.stringify(value):String(value??'');
 if(/^[=+@\-]/.test(text)&&!/^[-+]?\d+(?:\.\d+)?$/.test(text))text="'"+text;
 return '"'+text.replaceAll('"','""')+'"';
};

export function installWorkspaceApi(app:Express,service:FinanceService,options:{root?:string;port?:number;spawn?:typeof spawn}={}){
 const ROOT=options.root??DEFAULT_ROOT,PORT=options.port??DEFAULT_PORT,spawnRunner=options.spawn??spawn;
 const folder=path.join(ROOT,'benchmark/results');
 const progressEvidence=new Set([
  'research-models-pi-workflow-v06.json','research-models-pi-workflow-v06.independent.json',
  'pi-known-definition-existing-only-20261004-clean2.json','known-definition-clean2-runtime-review.json',
  'known-definition-clean2-provenance-v2.json','liugong-research-workflow-v06.failure-diagnosis.json',
  'research-workflow-v06-evidence-precision-review.json','research-trust-v01-first.json',
  'research-trust-v01-first-diagnosis.json','utf8-http-pi-restart-1791052167616.json',
  'controlled-pi-cache-cancellation-v06.json','development-v041-independent-review-20261004.json',
  'release-v06-20261004.json',
  'z4-isolated-1791054293428.json','z4-isolated-1791054293428.environment.json',
 ]);
 const jobs=new Map<string,any>();
 const processAlive=(pid:any)=>{if(!Number.isSafeInteger(pid)||pid<=0)return false;try{process.kill(pid,0);return true;}catch{return false;}};
 const readJson=async(file:string):Promise<any>=>{for(let attempt=0;;attempt++){try{return JSON.parse(await readFile(file,'utf8'));}catch(error:any){if(error.code==='ENOENT')return undefined;if(error instanceof SyntaxError&&attempt<3){await delay(10);continue;}throw error;}}};
 const formalModes:Record<string,{title:string;lock:string;script:string;args:string[]}>= {
  financial_v05:{title:'整表 v0.5 · 金融工作台',lock:'holdout-v05-financial-first-run.lock.json',script:'scripts/verify_holdout_v05.mjs',args:['--profile','financial']},
  generic_v05:{title:'整表 v0.5 · 通用 Pi 对照',lock:'holdout-v05-generic-first-run.lock.json',script:'scripts/verify_holdout_v05.mjs',args:['--profile','generic']},
  correction_v01:{title:'研报纠错 v0.1',lock:'report-correction-v01-first-run.lock.json',script:'scripts/verify_report_correction_v01.mjs',args:[]},
 };
 async function lockedResult(mode:string){
  const item=formalModes[mode];if(!item)return null;
  const lock=await readJson(path.join(folder,item.lock));if(!lock)return null;
  const output=path.resolve(lock.output);if(path.dirname(output).toLowerCase()!==folder.toLowerCase())throw new Error('验收结果路径不在项目记录目录');
  const report=await readJson(output);
  const saved=lock.job_id?(jobs.get(validId(lock.job_id))||await readJson(path.join(folder,'pi-workflow-'+validId(lock.job_id)+'.state.json'))):undefined;
  const id='locked-'+mode;
  const runnerPid=lock.runner_pid??saved?.runnerPid;
  const state=report?.status==='passed'?'completed':report?.status==='failed'||saved?.state==='failed'?'failed':saved?.state==='interrupted'?'interrupted':processAlive(runnerPid)?'running':'interrupted';
  return {id,mode,state,runnerPid,startedAt:lock.started_at,reportUrl:'/api/benchmark/run/'+id,message:state==='interrupted'?'测试运行已中断，首次记录仍保留；未自动重跑。':'保留首次运行记录；重复打开不会调用模型。',report};
 }
 for(const [endpoint,tool] of [['dashboard','get_dashboard'],['data-catalog','get_data_catalog'],['catalog','get_data_catalog']] as const){
  app.get('/api/projects/:projectId/'+endpoint,route(async(req,res)=>res.json((await service.call(tool,{project_id:validId(req.params.projectId)})).data)));
 }
 app.get('/api/projects/:projectId/documents/:documentId/normalization',route(async(req,res)=>{
  res.json((await service.call('get_normalization_details',{project_id:validId(req.params.projectId),document_id:validId(req.params.documentId),limit:Math.min(20,Math.max(1,Number(req.query.limit)||20)),offset:Math.max(0,Number(req.query.offset)||0),...(req.query.table_id?{table_id:String(req.query.table_id)}:{})})).data);
 }));
 app.get('/api/projects/:projectId/financial-data',route(async(req,res)=>{
  const filters=req.query.filters?JSON.parse(String(req.query.filters)):{};
  if(!filters||typeof filters!=='object'||Array.isArray(filters))throw new Error('筛选条件必须是对象');
  const limit=Math.min(200,Math.max(1,Number(req.query.limit)||200));
  const result=await service.call('query_financial_data',{project_id:validId(req.params.projectId),filters,limit,offset:req.query.format==='csv'?0:Math.max(0,Number(req.query.offset)||0)});
  if(req.query.format!=='csv'){res.json(result.data);return;}
  const columns=['company','label','metric','statement','period','period_start','period_end','scope','currency','unit_kind','value','raw_value','raw_unit','normalized_unit','numeric_span','version','dimensions','document_id','source_ref'];
  const items=[...(result.data.items||[])];
  let offset=items.length;
  while(offset<result.data.total){const more=await service.call('query_financial_data',{project_id:req.params.projectId,filters,limit:200,offset});if(!more.data.items?.length)break;items.push(...more.data.items);offset=items.length;}
  res.type('text/csv; charset=utf-8').setHeader('Content-Disposition','attachment; filename="financial-data.csv"');
  res.send('\uFEFF'+columns.join(',')+'\r\n'+items.map(item=>columns.map(key=>csvCell(item[key])).join(',')).join('\r\n'));
 }));
 const downloads:Record<string,{title:string;file:string;description:string}>={
  'native-pdf':{title:'4 份无需 OCR 的原始年报',file:'samples/无需OCR财报测试包-4份.zip',description:'茅台2024、伊利2023/2024、海尔2024，共925页；逐页文字层已检查。'},
  'normalization-v03':{title:'开发回归集 v0.3.1',file:'samples/normalization-benchmark-v0.3.1.zip',description:'10份输入、37个标准事实，已用于发现和修复问题；成绩不代表泛化能力。'},
  'holdout-v04':{title:'开发回归集 v0.4.1（保留首次结果）',file:'samples/financial-holdout-v0.4.1.zip',description:'中国神华、柳工的30个源格与7张原页；首次测试后已用于排错，后续成绩仅表示开发回归。'},
  'holdout-v05':{title:'整表独立验收 v0.5 · 完整执行包',file:'samples/financial-holdout-v0.5-evaluation.zip',description:'两家公司、4张逻辑整表、146个数值单元格，包含原页、冻结金标准、运行器与评分说明。同预算比较金融工作台和通用Pi，同时计漏抽、多抽和重复，按公司及表分别报告。'},
  'report-correction-v01':{title:'研报纠错验收 v0.1',file:'samples/financial-report-correction-v0.1.zip',description:'包含原始财报依据、待核验研报和冻结评分协议。检验可定位、可执行且有证据的修改，并检查是否误改正确事实和合理观点；这是任务级挑战，非新公司留出测试。'},
  'benchmark-v02':{title:'历史财报问答 benchmark v0.2',file:'samples/financial-benchmark-v0.2.zip',description:'186题，开发62/验收124；保留原始标签和历史结果，与新版清洗测试分开。'},
 };
 app.get('/api/benchmark/catalog',route(async(_req,res)=>{
  const datasets=[];
  for(const [id,value] of Object.entries(downloads)){
   const size=await stat(path.join(ROOT,value.file)).then(s=>s.size).catch(()=>null);
   if(size!==null)datasets.push({id,title:value.title,description:value.description,url:'/api/benchmark/download/'+id,bytes:size});
  }
  const states=await readdir(path.join(ROOT,'benchmark/results')).catch(()=>[]);
  const recent=await Promise.all(states.filter(name=>/^pi-workflow-[a-zA-Z0-9_-]+\.state\.json$/.test(name)).map(name=>readFile(path.join(ROOT,'benchmark/results',name),'utf8').then(JSON.parse).catch(()=>null)));
  const reports=recent.filter(Boolean).filter(job=>!formalModes[job.mode]).sort((a,b)=>String(b.startedAt).localeCompare(String(a.startedAt))).slice(0,6).map(job=>({title:`${job.mode==='holdout'?'旧 v0.4.1 首次验收':job.mode==='full'?'完整开发回归':'快速开发回归'} · ${job.startedAt.slice(0,16).replace('T',' ')} UTC`,url:'/api/benchmark/run/'+job.id}));
  for(const [mode,item] of Object.entries(formalModes)){const result=await lockedResult(mode);if(result)reports.unshift({title:item.title+' · 首次结果',url:result.reportUrl});}
  reports.push({title:'历史 v0.2 评测报告',url:'/api/benchmark/report/acceptance'});
  reports.unshift({title:'本轮升级进度与原始证据',url:'/api/benchmark/report/progress'});
  res.json({datasets,reports,validation:{runUrl:'/api/benchmark/run',statusUrl:'/api/benchmark/run/',description:'整表 v0.5 冻结原页与全部数值标准，金融工作台和通用 Pi 使用同一主模型及总预算。每组保留首次结果，重复点击只打开记录。纠错另计修改精确率、召回率及误改。',modes:['quick','full',...Object.keys(formalModes)]}});
 }));
 app.get('/api/benchmark/download/:id',route(async(req,res)=>{
  const item=downloads[validId(req.params.id)];if(!item){res.status(404).end();return;}
  const filename=path.join(ROOT,item.file);await stat(filename);res.download(filename,path.basename(filename));
 }));
 app.get('/api/benchmark/report/acceptance',route(async(_req,res)=>res.sendFile(path.join(ROOT,'benchmark/results/acceptance-report.html'))));
 app.get('/api/benchmark/report/progress',route(async(_req,res)=>{
  const html=await readFile(path.join(folder,'upgrade-progress-v06.html'),'utf8');
  res.type('html').send(html.replace(/data-evidence href="([^"]+)"/g,(match,name)=>progressEvidence.has(name)
   ?`data-evidence href="/api/benchmark/evidence/${encodeURIComponent(name)}"`:match));
 }));
 app.get('/api/benchmark/evidence/:name',route(async(req,res)=>{
  const name=String(req.params.name);
  if(!progressEvidence.has(name)){res.status(404).end();return;}
  res.sendFile(path.join(folder,name));
 }));
 app.get('/api/benchmark/design',route(async(_req,res)=>res.sendFile(path.join(ROOT,'benchmark/design.html'))));
 let starting:Promise<{status:number;job:any}>|undefined;
 app.post('/api/benchmark/run',route(async(req,res)=>{
  const mode=req.body?.mode||'quick';if(!['quick','full','holdout',...Object.keys(formalModes)].includes(mode))throw new Error('请选择开发回归或独立验收');
  // Reserve synchronously, before even reading a first-run lock. Concurrent
  // clicks share this exact start, including the filesystem creation window.
  if(starting){const result=await starting;res.status(result.status).json(result.job);return;}
  const reservation=(async()=>{
  if(formalModes[mode]){const prior=await lockedResult(mode);if(prior)return {status:200,job:prior};}
  if(mode==='holdout'){
   const locked=await readFile(path.join(folder,'holdout-v04-first-run.lock.json'),'utf8').then(JSON.parse).catch(error=>{if(error.code==='ENOENT')return null;throw error;});
   if(locked){
    if(!locked.job_id)throw new Error('该留出集已经运行，请查看 benchmark/results 中锁定的首次报告。');
    const priorId=validId(locked.job_id),prior=jobs.get(priorId)||JSON.parse(await readFile(path.join(folder,'pi-workflow-'+priorId+'.state.json'),'utf8'));
    return {status:200,job:{...prior,message:'显示该留出集的首次结果；未启动新的模型运行。'}};
   }
  }
  const active=[...jobs.values()].find(j=>j.state==='running');if(active)return {status:202,job:active};
  // A CLI runner or a child surviving a host restart also occupies the slot.
  for(const otherMode of Object.keys(formalModes)){const existing=await lockedResult(otherMode);if(existing?.state==='running')return {status:202,job:existing};}
  const id=randomUUID(),output=path.join(folder,'pi-workflow-'+id+'.json');await mkdir(folder,{recursive:true});
  const job:any={id,state:'running',mode,startedAt:new Date().toISOString(),message:'正在创建独立测试项目',reportUrl:'/api/benchmark/run/'+id};jobs.set(id,job);
  let saving=Promise.resolve();const save=()=>{const snapshot=JSON.stringify(job,null,2);return saving=saving.then(()=>writeFile(path.join(folder,'pi-workflow-'+id+'.state.json'),snapshot,'utf8'));};
  try{await save();}catch(error){job.state='failed';job.message=redactError(error);throw error;}
  const formal=formalModes[mode];
  const child=spawnRunner(process.execPath,[path.join(ROOT,formal?.script||(mode==='holdout'?'scripts/verify_holdout.mjs':'scripts/verify_pi_workflow.mjs')),'--base-url','http://127.0.0.1:'+PORT,'--output',output,...(formal?.args||[]),...(mode==='quick'?['--quick']:[]),...(formal||mode==='holdout'?['--job-id',id]:[])],{cwd:ROOT,windowsHide:true,stdio:['ignore','pipe','pipe']});
  job.runnerPid=child.pid;
  const update=(chunk:Buffer)=>{job.message=redactError(chunk.toString()).slice(-1200);};child.stdout.on('data',update);child.stderr.on('data',update);
  let spawnError:unknown;
  child.on('error',error=>{spawnError=error;});
  child.on('close',code=>{void(async()=>{
   const report=await readJson(output);
   job.state=report?.status==='passed'?'completed':report?.status==='failed'||spawnError?'failed':'interrupted';
   job.exitCode=code;job.finishedAt=report?.finished_at||new Date().toISOString();
   if(spawnError)job.message=redactError(spawnError);else if(job.state==='interrupted')job.message='测试进程已退出，尚无完整结果；首次记录保留，未自动重跑。';
   await save();
  })().catch(error=>{job.state='failed';job.message=redactError(error);});});
  await save();return {status:202,job};
  })();starting=reservation;
  try{const result=await reservation;res.status(result.status).json(result.job);}finally{if(starting===reservation)starting=undefined;}
 }));
 app.get('/api/benchmark/run/:id',route(async(req,res)=>{
  const id=validId(req.params.id);if(id.startsWith('locked-')){const result=await lockedResult(id.slice(7));if(!result){res.status(404).json({error:{message:'该组测试尚未运行'}});return;}res.json(result);return;}
  const live=jobs.get(id),job=live||JSON.parse(await readFile(path.join(folder,'pi-workflow-'+id+'.state.json'),'utf8'));
  const report=await readFile(path.join(folder,'pi-workflow-'+id+'.json'),'utf8').then(JSON.parse).catch(()=>undefined);
  if(!live&&job.state==='running'&&!processAlive(job.runnerPid)){
   job.state=report?.status==='passed'?'completed':report?.status==='failed'?'failed':'interrupted';
   job.finishedAt=report?.finished_at||new Date().toISOString();
   job.message=report?.status==='passed'?'测试已完成':report?.status==='failed'?(report.error||'测试未全部通过'):'服务重启中断了测试；已保留测试项目、会话和阶段结果。';
   await writeFile(path.join(folder,'pi-workflow-'+id+'.state.json'),JSON.stringify(job,null,2),'utf8');
  }
  res.json({...job,report});
 }));
}
