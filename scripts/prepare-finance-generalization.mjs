// New-source preparation only. Model answers/gold remain outside project exports.
import {readFile,writeFile,mkdir,readdir} from 'node:fs/promises';
import path from 'node:path';
import {createHash} from 'node:crypto';
const name='pi-finance-generalization-20261006';
const dir=path.resolve('data/evaluation',name),file=path.join(dir,'setup.json');
await mkdir(dir,{recursive:true});
const api=async(route,body)=>{const opt={signal:AbortSignal.timeout(120000)};if(body!==undefined){opt.method='POST';opt.headers={'Content-Type':'application/json'};opt.body=JSON.stringify(body);}const r=await fetch('http://127.0.0.1:3001'+route,opt);if(!r.ok)throw Error(`${route}: ${r.status} ${await r.text()}`);return r.json();};
const save=async s=>writeFile(file,JSON.stringify(s,null,2)+'\n');
let s;try{s=JSON.parse(await readFile(file,'utf8'));}catch(e){if(e.code!=='ENOENT')throw e;s={createdAt:new Date().toISOString(),documents:[],ingestion:[]};}
const command=process.argv[2];
if(command==='prepare'){
 if(!s.projectId){const p=await api('/api/projects',{name:'新公司对照｜卡罗特（2026-10-06）'});s.projectId=p.id;await save(s);}
 for(const filename of ['Carote_2025_Interim_55p.pdf','CMBI_Carote_20241108_47p.pdf']){
  const existing=(await api(`/api/projects/${s.projectId}/documents`)).documents.find(d=>d.name===filename);
  if(existing){if(!s.documents.some(d=>d.id===existing.id))s.documents.push(existing);await save(s);continue;}
  const form=new FormData();form.append('files',new Blob([await readFile(path.join('samples/holdout-20261006',filename))],{type:'application/pdf'}),filename);
  const r=await fetch(`http://127.0.0.1:3001/api/projects/${s.projectId}/uploads`,{method:'POST',body:form});if(!r.ok)throw Error(await r.text());
  s.documents.push(...(await r.json()).documents);await save(s);
 }
 console.log(JSON.stringify({projectId:s.projectId,documents:s.documents.map(({id,name})=>({id,name}))}));
}else if(command==='ingest'){
 const i=Number(process.argv[3]);if(![0,1].includes(i)||!s.documents[i])throw Error('ingest 0 or 1');
 if(s.ingestion.some(r=>r.documentId===s.documents[i].id))throw Error('Already posted/registered; inspect persisted request instead of replaying');
 const chat=await api(`/api/projects/${s.projectId}/conversations`,{});
 const item={documentId:s.documents[i].id,conversationId:chat.id,status:'posting'};s.ingestion.push(item);await save(s);
 const content=i===0?'准备资料｜卡罗特2025中报\n请完整处理这份财报，提取主表与附注并入库，保留期间、合并口径、单位和来源；无法结构化的内容保留原文及疑点。不做金融问答或估值，不读取测试答案。完成后简短报告覆盖范围和待核验项。':'准备资料｜招银国际卡罗特研报\n请按研报路线完整处理这份报告，入库表格数据、机构预测、观点与风险，保留机构、日期、主体、来源和实际/预测身份。保留原文内部不一致和待核验信息，不替机构改写预测。不做额外估值，不读取测试答案。完成后简短报告覆盖范围。';
 Object.assign(item,await api(`/api/conversations/${chat.id}/messages`,{content,documentIds:[item.documentId]}),{status:'running'});await save(s);console.log(JSON.stringify(item));
}else if(command==='resume'||command==='continue'){
 const i=Number(process.argv[3]),doc=s.documents[i],item=s.ingestion.find(r=>r.documentId===doc?.id);
 if(!item)throw Error('No existing preparation');
 const previous=await api('/api/runs/'+item.runId);
 if(!(command==='continue'?['completed','failed','cancelled']:['failed','cancelled']).includes(previous.status))throw Error('Previous run is not stopped');
 await writeFile(path.join(dir,'ingest-attempt-'+item.runId+'.json'),JSON.stringify(previous,null,2));
 (item.previousAttempts??=[]).push({runId:item.runId,status:previous.status,usage:previous.usage,error:previous.error});
 const content=process.argv[4]||'继续刚才的完整资料入库。宿主的 Responses 参数和普通入库路由已修复。请识别并保存来源类型，沿现有脚本清洗流程完成全部数值表及研报正文覆盖；可复用已解析原文。早期旧流程尚未完成，已有部分解释如与正确来源类型不符，应通过正常清洗提交更新，历史保留。保持原任务完整覆盖要求，不做金融问答。';
 (s.interventions??=[]).push({at:new Date().toISOString(),priorRunId:item.runId,documentId:item.documentId,message:content,phase:'preparation'});
 Object.assign(item,await api(`/api/conversations/${item.conversationId}/messages`,{content,documentIds:[item.documentId]}),{status:'running'});
 await save(s);console.log(JSON.stringify({runId:item.runId,conversationId:item.conversationId,status:item.status}));
}else if(command==='poll'){
 for(const item of s.ingestion){if(!item.runId)continue;const run=await api('/api/runs/'+item.runId);item.status=run.status;item.usage=run.usage;item.error=run.error;await writeFile(path.join(dir,'ingest-'+item.documentId+'-run.json'),JSON.stringify(run,null,2));await writeFile(path.join(dir,'ingest-'+item.documentId+'-conversation.json'),JSON.stringify(await api('/api/conversations/'+item.conversationId),null,2));}
 await save(s);console.log(JSON.stringify(s.ingestion.map(r=>({documentId:r.documentId,status:r.status,usage:r.usage,error:r.error})),null,2));
}else if(command==='freeze'){
 if(s.ingestion.length!==2||s.ingestion.some(r=>r.status!=='completed'))throw Error('Preparation not complete');
 const stateFile=path.join(dir,'experiment.json');try{await readFile(stateFile);throw Error('Already frozen');}catch(e){if(e.code!=='ENOENT')throw e;}
 const f=s.documents[0].id,r=s.documents[1].id;
 const common='仅分析指定项目已有资料，不重新入库、清洗、修改数据或联网。只使用指定报告及本会话新建的成果，不读取其他会话成果。计算用工具或Python。中文简洁专业回答，给来源页码，区分事实、机构预测和自己的假设；交付研报风格图表、底稿CSV、Markdown报告及可复算脚本。图、表、正文须使用一致币种和单位，未知保留缺口。';
 const tasks=[
 {id:'1',name:'卡罗特中报利润和现金',prompt:`新公司对照｜利润与现金流\n${common}\n使用 ${f}（卡罗特2025中报，55页）。比较2025H1和2024H1的收入、毛利率、经营利润、合并净利润、归母净利润及经营现金流。解释利润与现金转化的变化，区分经营利润和净利息收益的作用；用报表可确认项目连接经营产生现金与经营活动净现金，说明未获得的调节明细，不凭空补平。金额统一展示人民币百万元，并给一张与结论直接相关的图。`},
 {id:'2',name:'卡罗特研报预测与DCF',prompt:`新公司对照｜研报预测与估值\n${common}\n仅使用 ${r}（招银国际2024-11-08卡罗特报告，47页），站在报告发布日期，不使用2025中报。概括投资逻辑与主要风险，列出2024E至2026E收入、净利润和EPS并说明身份，展示金额为人民币亿元，每股值保持原单位。复算PE目标价，区分人民币盈利与港币股价。另按报告DCF表的2024E至2028E Unleveraged FCF原行（不从别表替换口径），按2023年末估值、每年末折现、末年FCF乘(1+g)延伸终值进行独立复算：WACC=12.2%，g=2%，股数、净现金及人民币到港币的汇率取该DCF表。列出EV、股权价值与港币每股值，解释与报告目标值的差异；来源内字段矛盾应指出。敏感性为WACC=[11.2%,12.2%,13.2%]，g=[1%,2%,3%]。保留所有输入，供下一条问题更新。`},
 {id:'3',name:'卡罗特DCF局部更新',continuationOf:'2',prompt:`新公司对照｜局部更新\n沿用本会话刚建的DCF及其输入和方法，不重读整份报告、不使用其他会话成果。依次作两项变化：WACC增加0.5个百分点；2024E至2028E各年的原FCF乘0.90。其他输入全部保持不变，终值继续依修改后的末年FCF计算。计算新旧港币每股值和差额，按上述顺序拆出两项贡献；敏感性仍使用原问题的绝对WACC/g网格，给两版并列且同坐标、同色标图。用简洁金融语言解释，交付新旧参数、结果、差异CSV、Markdown及可复算脚本。`}
 ];
 const sha=v=>createHash('sha256').update(v).digest('hex');
 const [settings,docs,catalog]=await Promise.all([api('/api/settings'),api(`/api/projects/${s.projectId}/documents`),api(`/api/projects/${s.projectId}/assets/catalog`)]);
 if(s.documents.some(d=>!['ready','needs_review'].includes(docs.documents.find(x=>x.id===d.id)?.status)))throw Error('A conversation ended, but source preparation remains incomplete');
 const smoke=JSON.parse(await readFile(path.join(dir,'presentation-smoke.json'),'utf8'));
 if(smoke.status!=='succeeded'||!smoke.container_removed)throw Error('Real presentation smoke has not passed');
 const files={};async function walk(p){for(const ent of await readdir(p,{withFileTypes:true})){if(['tests','__pycache__','dist'].includes(ent.name))continue;const file=path.join(p,ent.name);if(ent.isDirectory())await walk(file);else if(/\.(py|ts|md)$/.test(file))files[file]=sha(await readFile(file));}}
 for(const folder of ['server','service','skills'])await walk(folder);
 const experiment={createdAt:new Date().toISOString(),study:'new_company_screen_not_statistical_superiority',projectId:s.projectId,model:settings.llm.model,provider:settings.llm.provider,endpointSha256:sha(settings.llm.baseUrl||''),taskSha256:sha(JSON.stringify(tasks)),codeSha256:sha(JSON.stringify(files)),codeFiles:files,catalogSha256:sha(JSON.stringify(catalog)),dataSummary:catalog.summary,documents:docs.documents,tasks,
  arms:[{id:'A',profile:'generic',repeat:1},{id:'B',profile:'prepared',repeat:1},{id:'C',profile:'financial',repeat:1},{id:'D',profile:'prepared',repeat:2},{id:'E',profile:'financial',repeat:2}],
  plannedOrder:['A1','B1','C1','C2','B2','A2','B3','C3','A3','E1','D1','D2','E2','E3','D3'],
  evaluationLimits:{max_model_calls:1000,max_input_tokens:50000000,max_output_tokens:2000000,max_total_tokens:52000000,max_wall_seconds:43200},sandboxReady:true,sandboxImage:smoke.image_id,ingestion:s.ingestion,runs:[],interventions:[]};
 await writeFile(stateFile,JSON.stringify(experiment,null,2));await writeFile(path.join(dir,'catalog-before.json'),JSON.stringify(catalog,null,2));await writeFile(path.join(dir,'tasks.json'),JSON.stringify(tasks,null,2));
 console.log(JSON.stringify({projectId:s.projectId,model:experiment.model,order:experiment.plannedOrder,codeSha256:experiment.codeSha256}));
}else throw Error('Use prepare / ingest 0|1 / poll / freeze');
