/** Full original annual report through the public conversation API. Gold stays host-side. */
import fs from 'node:fs/promises';
import path from 'node:path';
import {createHash} from 'node:crypto';
import {setTimeout as delay} from 'node:timers/promises';
import {decimalKey,extractionEvidence,extractionSignature,collectNormalizationPages,temporalAcceptance} from './validation_utils.mjs';
import {checkFact} from './score_normalization.mjs';
import {verifyTemporalCacheEvidence} from './temporal_evidence.mjs';
const root=path.resolve(import.meta.dirname,'..'),base='http://127.0.0.1:3001';
const output=path.join(root,'benchmark/results/pi-full-report-v03.json');
const now=()=>new Date().toISOString();
const definitionRequest=process.argv.includes('--review-definitions')?'另外，已发现收入（revenue）、租赁负债（lease_liabilities）、政府补助（non_recurring_government_grants）三组现有指标可能混合了不同披露定义。请在同一会话中调用 review_metrics，依据完整原文上下文逐组复核，自己判断哪些定义应保留、拆分或归并，并保存依据；不要仅因金额相同而当成同一概念。':'';
let report={version:'0.3',status:'running',started_at:now(),scope:'Full-file execution and five independent source anchors; not exhaustive fact accuracy.',checks:[],snapshots:[]};
const save=()=>fs.writeFile(output,JSON.stringify(report,null,2));
const request=async(route,body)=>{const res=await fetch(base+route,{...(body?{method:'POST',body:body instanceof FormData?body:JSON.stringify(body),headers:body instanceof FormData?{}:{'Content-Type':'application/json'}}:{}),signal:AbortSignal.timeout(90000)});if(!res.ok)throw new Error('HTTP '+res.status+' '+route);return res.json();};
function check(name,ok,evidence){report.checks.push({name,status:ok?'passed':'failed',evidence});console.log(ok?'PASS':'FAIL',name);}
const implementation=async()=>Object.fromEntries(await Promise.all(['server/runs.ts','server/model-bridge.ts','server/mcp.ts','server/main.ts','server/workspace-api.ts','service/server.py','service/processing.py','service/completed_document.py','service/core.py','service/semantic.py','service/parser.py','service/parser_worker.py','service/normalization.py','service/extraction_alignment.py','service/catalog_model.py','service/catalog_semantics.py','service/temporal_model.py','service/temporal_semantics.py','service/definition_model.py','service/definition_semantics.py','service/temporal_repair.py'].map(async name=>[name,createHash('sha256').update(await fs.readFile(path.join(root,name))).digest('hex')])));
const eventsFor=async runId=>(await fs.readFile(path.join(root,'data/audit',runId+'.jsonl'),'utf8')).trim().split('\n').filter(Boolean).map(JSON.parse);
try{
 if(process.argv.includes('--continue')&&process.argv.includes('--resume'))throw Error('Use either --continue (new Pi turn) or --resume (observe existing turn), not both.');
 if(definitionRequest&&!process.argv.includes('--continue'))throw Error('--review-definitions requires --continue for the existing development report.');
 if(process.argv.includes('--continue')){
  report=JSON.parse(await fs.readFile(output,'utf8'));
  const priorRun=await request('/api/runs/'+report.run_id);
  if(['running','queued'].includes(priorRun.status))throw Error('The previous Pi turn is still active. Use --resume to observe it.');
  const attempt=(report.previous_attempts?.length||0)+1;
  await fs.writeFile(path.join(root,`benchmark/results/pi-full-report-v03-attempt-${attempt}.json`),JSON.stringify(report,null,2));
  report.previous_attempts=[...(report.previous_attempts||[]),{run_id:report.run_id,status:report.status,usage:report.run?.usage,evidence:`pi-full-report-v03-attempt-${attempt}.json`}];
  report.checks=report.checks.filter(c=>c.name==='完整原始PDF上传只登记');report.snapshots=[];report.status='running';delete report.finished_at;delete report.error;
  report.continued_at=now();
  report.requested_definition_review=definitionRequest||null;
  report.implementation_before=await implementation();
  for(const key of ['implementation_after','implementation_snapshot_note','implementation_snapshot_started_at','mapping_quality','extraction_provenance','execution_status'])delete report[key];
  const run=await request(`/api/conversations/${report.conversation_id}/messages`,{content:'继续完整处理这份年报。上次尚未完成全部处理，相关程序问题已修复。复用有效已保存结果，接着完成目录及期间审校和未完成批次。完成剩余所有可提取的财务主表和附注表，分批入库更新看板；不要强制重新调用已完成批次。'+definitionRequest+'完成后简要说明实际覆盖和数据库位置。',documentIds:[report.document_id]});
  report.run_id=run.runId;await save();
 }
 else if(process.argv.includes('--resume')){
  report=JSON.parse(await fs.readFile(output,'utf8'));
  const priorScore='pi-full-report-v03-rescore-'+now().replace(/[:.]/g,'-')+'.json';
  await fs.writeFile(path.join(root,'benchmark/results',priorScore),JSON.stringify(report,null,2));
  report.previous_scores=[...(report.previous_scores||[]),priorScore];
  report.checks=report.checks.filter(c=>c.name==='完整原始PDF上传只登记');
  report.resumed_at=now();report.status='running';delete report.error;delete report.finished_at;
 }
 else{
  const p=await request('/api/projects',{name:'财报研究 · 完整年报'});report.project_id=p.id;
  const chat=await request(`/api/projects/${p.id}/conversations`,{});report.conversation_id=chat.id;
  const form=new FormData(),filename='贵州茅台2024年年度报告.pdf';
  form.append('files',new Blob([await fs.readFile(path.join(root,'samples/native-pdf',filename))]),filename);
  const uploaded=await request(`/api/projects/${p.id}/uploads`,form);report.document_id=uploaded.documents[0].id;
  check('完整原始PDF上传只登记',uploaded.documents[0].status==='registered',{filename,document_id:report.document_id,status:uploaded.documents[0].status});
  report.implementation_before=await implementation();
  const run=await request(`/api/conversations/${chat.id}/messages`,{content:'请完整处理这份年报的全部可提取财务主表和附注表。通过 LangExtract 理解并统一字段、单位、期间、合并与母公司口径、重述及分部，分批入库并更新看板；保持财务金额与增长率指标不同。完成后简要说明数据覆盖情况和数据库位置。先完成清洗，不需要写长报告或作图。',documentIds:[report.document_id]});
  report.run_id=run.runId;await save();
 }
 if(!report.implementation_before){report.implementation_before=await implementation();report.implementation_snapshot_started_at=now();report.implementation_snapshot_note='Legacy report had no initial snapshot; this snapshot covers observation only.';}await save();
 let last=0,run;
 const deadline=Date.now()+2*60*60*1000;
 while(Date.now()<deadline){
  run=await request('/api/runs/'+report.run_id);
  if(Date.now()-last>20000){last=Date.now();const doc=await request(`/api/projects/${report.project_id}/documents/${report.document_id}`);const sample={at:now(),status:run.status,stage:run.stage,usage:run.usage,document:doc};report.snapshots.push(sample);report.last=sample;await save();console.log(JSON.stringify({at:sample.at,status:run.status,stage:run.stage,usage:run.usage}));}
  if(['completed','failed','cancelled'].includes(run.status))break;
  await delay(2500);
 }
 report.run=run;
 if(['running','queued'].includes(run.status))throw Error('Observation deadline reached; Pi is still active. Use --resume instead of creating another run.');
 check('所属Pi运行完成',run.status==='completed',{status:run.status,error:run.error,usage:run.usage});
 const catalog=await request(`/api/projects/${report.project_id}/catalog`);report.catalog=catalog;
 const doc=await request(`/api/projects/${report.project_id}/documents/${report.document_id}`);report.document=doc;
 const original=await fs.readFile(path.join(root,'samples/native-pdf/贵州茅台2024年年度报告.pdf'));
 check('完整143页已建立索引',doc.pageCount===143&&doc.sha256===createHash('sha256').update(original).digest('hex'),{document_pages:doc.pageCount,document_sha256:doc.sha256,counts:catalog.counts,index_path:catalog.index_path});
 const own=catalog.processing.filter(p=>p.owner_run_id===report.run_id);report.processing=own;
 check('全部候选表格批次均完成',own.length>0&&own.every(p=>['completed','ready','needs_review'].includes(p.state)&&p.coverage?.batches_total>0&&p.coverage.batches_completed===p.coverage.batches_total&&p.coverage.tables_completed===p.coverage.tables_total&&!p.errors?.length),own.map(p=>({state:p.state,coverage:p.coverage,errors:p.errors})));
 const normalization=await collectNormalizationPages(request,`/api/projects/${report.project_id}/documents/${report.document_id}/normalization`);
 report.normalization_pagination=normalization.pagination;
 check('全部清洗批次明细分页读取完整',normalization.pagination.loaded===normalization.pagination.total,normalization.pagination);
 const issues=normalization.batches.flatMap(batch=>(batch.result?.issues||[]).map(issue=>({batch_key:batch.batch_key,processing_id:batch.processing_id,...issue})));
 const reasons={};for(const issue of issues)reasons[issue.reason]=(reasons[issue.reason]||0)+1;
 report.mapping_quality={status:issues.length?'needs_review':'passed',issue_count:issues.length,issue_reasons:reasons,issues,document_warnings:doc.warnings||[]};
 const all=[];for(let offset=0;;){const page=await request(`/api/projects/${report.project_id}/financial-data?limit=200&offset=${offset}`);all.push(...page.items);offset+=page.items.length;if(offset>=page.total||!page.items.length)break;}
 const documentFacts=all.filter(f=>f.document_id===report.document_id);
 report.fact_count=documentFacts.length;report.metric_count=new Set(documentFacts.map(f=>f.metric)).size;
 check('财务主表和附注均入库', ['income','balance','cashflow','notes'].every(s=>documentFacts.some(f=>f.statement===s)),{statements:[...new Set(documentFacts.map(f=>f.statement))],facts:documentFacts.length,metrics:report.metric_count});
 const gold=(await fs.readFile(path.join(root,'benchmark/versions/v0.3-normalization/gold.jsonl'),'utf8')).trim().split('\n').map(JSON.parse).filter(g=>g.original_page);
 report.anchors=gold.map(g=>{
  const found=documentFacts.filter(f=>f.metric===g.metric&&f.period===g.period&&f.source_ref?.page===g.original_page);
  const valid=found.filter(f=>f.currency===g.currency&&f.normalized_unit===g.currency&&f.source_ref?.document_id===report.document_id&&f.source_ref?.table_id&&f.source_ref?.row&&f.source_ref?.column&&f.source_ref?.normalization?.engine==='LangExtract');
  const expected=decimalKey(g.value),values=[...new Set(found.map(f=>decimalKey(f.value)))];
  const errors=found.map(f=>({fact_id:f.fact_id,errors:checkFact({...g,page:g.original_page},f)}));
  return {id:g.id,page:g.original_page,expected:g.value,currency:g.currency,actual:found.map(f=>f.value),passed:valid.length>0&&valid.length===found.length&&values.length===1&&values[0]===expected&&errors.every(x=>!x.errors.length),source_refs:found.map(f=>f.source_ref),errors};
 });
 check('五个独立来源标准值',report.anchors.every(a=>a.passed),report.anchors);
 const events=await eventsFor(report.run_id),current=extractionEvidence(events,report.run_id);
 // Batch reuse must lead back to actual successful Pi extraction results. It is
 // not enough for cached rows to merely claim engine=LangExtract.
 const ownerByProcessing=new Map(catalog.processing.map(p=>[p.processing_id,p.owner_run_id]));
 const audits=new Map([[report.run_id,current]]);
 for(const attempt of report.previous_attempts||[]){
  try{const prior=await eventsFor(attempt.run_id);for(const event of prior.filter(e=>e.type==='processing_started'))ownerByProcessing.set(event.data.processingId,attempt.run_id);audits.set(attempt.run_id,extractionEvidence(prior,attempt.run_id));}catch{/* missing evidence is reported below */}
 }
 const batchEvidence=[];
 for(const batch of normalization.batches){
  const detail=batch.result||{},originProcessing=detail.extraction_processing_id||batch.processing_id,owner=ownerByProcessing.get(originProcessing);
  if(owner&&!audits.has(owner)){try{audits.set(owner,extractionEvidence(await eventsFor(owner),owner));}catch{/* report missing owner evidence */}}
  const audit=audits.get(owner),extractions=detail.extractions||[],matched=extractions.filter(ex=>audit?.signatures.has(extractionSignature(ex))).length;
  batchEvidence.push({batch_key:batch.batch_key,processing_id:batch.processing_id,origin_processing_id:originProcessing,origin_run_id:owner||null,reused:!!detail.reused_extraction,extractions:extractions.length,matched_extractions:matched,passed:!!audit?.valid_owners&&extractions.length>0&&matched===extractions.length});
 }
 report.extraction_provenance={audits:[...audits].map(([run_id,a])=>({run_id,...a,signatures:undefined})),batches:batchEvidence};
 check('清洗或复用抽取均可追溯到所属Pi运行',current.valid_owners&&batchEvidence.length>0&&batchEvidence.every(b=>b.passed),report.extraction_provenance);
 check('项目指标目录审校完成且有真实Pi模型证据',catalog.catalog_review?.status==='reviewed'&&catalog.catalog_review?.pending_fact_count===0&&catalog.catalog_review?.reviewed_fact_count===all.length&&[...audits.values()].some(a=>a.valid_owners&&a.extraction_classes.includes('catalog_review'))&&documentFacts.every(f=>f.canonical_alias?.status==='reviewed'&&f.canonical_alias?.engine==='LangExtract'),{directory:catalog.catalog_review,audited_classes:[...audits].map(([run_id,a])=>({run_id,classes:a.extraction_classes}))});
 for(const fact of all){const owner=fact.source_ref?.normalization?.temporal_correction?.owner_run_id;if(owner&&!audits.has(owner)){try{audits.set(owner,extractionEvidence(await eventsFor(owner),owner));}catch{/* missing temporal owner is reported below */}}}
 const temporalCache=await verifyTemporalCacheEvidence(report.project_id,catalog.temporal_review).catch(error=>({status:'failed',error:String(error.message).replace(/sk-[A-Za-z0-9_-]+/g,'[REDACTED]')}));
 report.temporal={...temporalAcceptance(catalog.temporal_review,all,[...[...audits].map(([run_id,a])=>({run_id,...a})),...(temporalCache.audits||[])]),cache_evidence:temporalCache};
 check('期间审校覆盖项目事实且修订可追溯真实Pi输出',report.temporal.status==='passed'&&temporalCache.status==='passed',report.temporal);
 report.implementation_after=await implementation();
 check('本次运行实现保持固定',JSON.stringify(report.implementation_before)===JSON.stringify(report.implementation_after),{before:report.implementation_before,after:report.implementation_after});
 report.execution_status=report.checks.every(c=>c.status==='passed')?'passed':'failed';
 report.status=report.execution_status==='failed'?'failed':report.mapping_quality.status==='needs_review'?'needs_review':'passed';report.finished_at=now();
}catch(error){report.status='failed';report.error=String(error.message).replace(/sk-[A-Za-z0-9_-]+/g,'[REDACTED]');console.error(report.error);}
finally{await save();console.log('REPORT',output);if(report.status!=='passed')process.exitCode=1;}
