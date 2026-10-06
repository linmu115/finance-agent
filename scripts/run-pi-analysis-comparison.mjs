// Analysis-only client: reuse existing documents; never upload or ingest them.
import {readFile,writeFile,mkdir,rename,copyFile} from 'node:fs/promises';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {createHash} from 'node:crypto';
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
const studyName=process.env.FINANCE_COMPARISON_DIR||'pi-analysis-20261005-r2';
const dir=path.join(root,'data/evaluation',studyName);
const stateFile=path.join(dir,'experiment.json');
const projectId=process.env.FINANCE_COMPARISON_PROJECT_ID||'374beac2-a970-4972-b210-e91018bbd6e6';
const sha=x=>createHash('sha256').update(x).digest('hex');
const api=async(route,body)=>{const init={signal:AbortSignal.timeout(120000)};if(body!==undefined){init.method='POST';init.headers={'Content-Type':'application/json'};init.body=JSON.stringify(body);}const r=await fetch('http://127.0.0.1:3001'+route,init),t=await r.text();if(!r.ok)throw Error(`${route}: ${r.status} ${t.slice(0,600)}`);return JSON.parse(t);};
const load=()=>readFile(stateFile,'utf8').then(JSON.parse);
const save=async s=>{await writeFile(stateFile+'.tmp',JSON.stringify(s,null,2)+'\n');await rename(stateFile+'.tmp',stateFile);};
const json=async(name,v)=>writeFile(path.join(dir,name),JSON.stringify(v,null,2)+'\n');
const common='仅分析当前项目已有资料，不重新入库、清洗、修订原有数据或联网。可查询已整理的记录及相应原文；疑点仅影响相关结论。不要读取或使用其他会话已有的研究成果、模型或答案；本会话自己新建的成果可复用。给出简洁专业的结论、来源页码和关键假设，并交付可下载的研报排版风格中文图表、底稿 CSV、Markdown 报告和完整可复算 Python 脚本。数值计算请用工具或 Python 完成。';
const tasks=[
 {id:'1',name:'瑞和利润与现金流',documentId:'ab25c52089fd4db89fba046c9c811c46',prompt:`纯分析对照｜瑞和利润与现金流\n${common}\n使用已有文档 ab25c52089fd4db89fba046c9c811c46（瑞和数智2025中报，57页），比较2025H1与2024H1的收入、毛利率、经营利润、合并净利润和经营现金流。解释利润转正是否代表经营改善，建立2025H1从合并净利润到经营现金流的调节，区分有证据支持的项目和未解释差额，明确单位、口径和非现金影响。`},
 {id:'2',name:'伊利研报分析',documentId:'585db15e768043b7b465d1af7c690e90',prompt:`纯分析对照｜伊利研报分析\n${common}\n使用已有文档 585db15e768043b7b465d1af7c690e90（国信证券伊利深度报告，2025-07-16，38页），提炼机构主要投资逻辑、预测依据及风险；列出2025至2027年收入、归母净利润和EPS，明确实际值与机构预测的身份。复算报告的PE目标价区间，说明估值依据。不要把机构观点或预测写成已发生的事实。`},
 {id:'3',name:'伊利DCF初建',documentId:'585db15e768043b7b465d1af7c690e90',prompt:`纯分析对照｜伊利DCF初建\n${common}\n使用已有文档 585db15e768043b7b465d1af7c690e90（国信证券伊利深度报告，2025-07-16，38页）建立可更新的伊利FCFF折现模型。估值锚点统一为2024年末，明确预测期2025至2027年；依据营业收入、EBIT、税率、折旧摊销、资本开支与营运资金变化计算FCFF，并与报告披露的FCFF比较，差异无法解释时明确说明。净债务和股数取报告中可确认的口径，解释少数股东权益处理；无法直接取得的参数作为显式假设。WACC取7.9%，永续增长率取1.8%；敏感性用WACC=[7.5%,7.9%,8.5%]、g=[1.0%,1.8%,2.2%]。输出EV、股权价值和每股价值，判断31.36元是否落在你算出的敏感性区间内。保留完整输入及计算结果，供本会话下一条问题局部更新。`},
 {id:'4',name:'伊利DCF局部更新',continuationOf:'3',prompt:`纯分析对照｜伊利DCF局部更新\n沿用本会话刚完成的DCF模型和数据，不重新入库或从头读取整篇报告。仅作三项修改：WACC增加0.5个百分点；2025至2027年各年资本开支乘1.20；2025至2027年各年折旧摊销乘1.10。其余输入、估值锚点、g和股数全部保持不变。计算新旧每股价值及差额，将差额按上述修改顺序逐项归因，说明顺序归因的含义；列出各年FCFF的变化。两版敏感性图沿用前次相同的绝对WACC/g网格，并列展示且坐标、单位和色标一致。给出简洁解释，以及两版输入、结果、差异CSV、Markdown报告和完整可复算Python脚本；可复用本会话新建成果，不使用其他会话成果。`}
];
await mkdir(dir,{recursive:true});
const command=process.argv[2];
if(command==='init'){
 try{await load();throw Error('Experiment exists; use start/poll, do not overwrite');}catch(e){if(e.code!=='ENOENT')throw e;}
 const [settings,docs,catalog,chats]=await Promise.all([api('/api/settings'),api(`/api/projects/${projectId}/documents`),api(`/api/projects/${projectId}/assets/catalog`),api(`/api/projects/${projectId}/conversations`)]);
 if(chats.conversations.some(c=>c.activeRunId))throw Error('Existing project task active; wait before freezing');
 const d=await api(`/api/projects/${projectId}/data-catalog`);
 await json('documents-before.json',docs);await json('catalog-before.json',catalog);await json('financial-catalog-before.json',d);await json('tasks.json',tasks);
 await mkdir(path.join(dir,'judge'),{recursive:true});await copyFile(path.join(root,'data/evaluation/pi-pilot-20261005/judge/gold.json'),path.join(dir,'judge/source-reference.json'));
 const s={createdAt:new Date().toISOString(),study:'analysis_only_development_regression_not_heldout',projectId,model:settings.llm.model,provider:settings.llm.provider,endpointSha256:sha(settings.llm.baseUrl||''),taskSha256:sha(JSON.stringify(tasks)),catalogSha256:sha(JSON.stringify(catalog)),dataSummary:catalog.summary,documents:docs.documents.map(({id,name,sha256,pageCount})=>({id,name,sha256,pageCount})),tasks,arms:[{id:'A',profile:'generic'},{id:'B',profile:'prepared'},{id:'C',profile:'financial'}],plannedOrder:['A1','B1','C1','B2','C2','A2','C3','A3','B3','A4','B4','C4'],evaluationLimits:{max_model_calls:1000,max_input_tokens:50000000,max_output_tokens:2000000,max_total_tokens:52000000,max_wall_seconds:43200},sandboxReady:false,runs:[],interventions:[]};
 await save(s);console.log(JSON.stringify({model:s.model,documents:s.documents,summary:s.dataSummary,order:s.plannedOrder},null,2));
}else if(command==='ready'){
 const s=await load(),smoke=JSON.parse(await readFile(path.join(dir,'sandbox-smoke.json'),'utf8'));if(!smoke.runs.every(r=>r.status==='succeeded'&&r.container_removed))throw Error('Sandbox smoke incomplete');s.sandboxReady=true;s.sandboxImage=smoke.runs[0].image_id;await save(s);console.log('Sandbox verified');
}else if(command==='start'){
 const s=await load(),label=process.argv[3],arm=s.arms.find(a=>a.id===label?.[0]),task=s.tasks.find(t=>t.id===label?.[1]);
 if(!arm||!task)throw Error('Invalid run label');if(!s.sandboxReady)throw Error('Sandbox not verified');if(s.runs.some(r=>r.label===label))throw Error('Already registered; read result instead of resending');
 const settings=await api('/api/settings');if(settings.llm.model!==s.model||sha(settings.llm.baseUrl||'')!==s.endpointSha256)throw Error('Model/provider changed');
 let conversationId;
 if(task.continuationOf){const prior=s.runs.find(r=>r.label===arm.id+task.continuationOf);if(!prior||prior.status!=='completed')throw Error('Initial model not completed');conversationId=prior.conversationId;}else{conversationId=(await api(`/api/projects/${projectId}/conversations`,{})).id;}
 const record={label,profile:arm.profile,projectId,conversationId,requestedAt:new Date().toISOString(),status:'posting',documentIds:[],budgetGroupId:studyName+'-'+label};s.runs.push(record);await save(s);
 const r=await api(`/api/conversations/${conversationId}/messages`,{content:task.prompt,documentIds:[],evaluation:{profile:arm.profile,budget_group_id:record.budgetGroupId,budget:s.evaluationLimits}});
 Object.assign(record,r,{status:'running'});await save(s);console.log(JSON.stringify(record,null,2));
}else if(command==='poll'){
 const s=await load(),out=[];
 for(const r of s.runs){if(!r.runId){out.push({label:r.label,status:r.status});continue;}if(process.argv.includes('--active')&&!['running','queued','posting'].includes(r.status))continue;
  const [run,chat]=await Promise.all([api('/api/runs/'+r.runId),api('/api/conversations/'+r.conversationId)]);
  await json(r.label+'-run.json',run);await json(r.label+'-conversation.json',chat);
  r.status=run.status;r.usage=run.usage;r.error=run.error;r.completedAt=run.finishedAt;
  await copyFile(path.join(root,'data/active/audit',r.runId+'.jsonl'),path.join(dir,r.label+'-audit.jsonl')).catch(e=>{if(e.code!=='ENOENT')throw e;});
  out.push({label:r.label,status:r.status,stage:run.stage,error:run.error,usage:Object.fromEntries(['calls','input','output','reasoning','cacheRead','cacheKnownInput','unknownCalls','costCnyMin','costCnyMax'].map(k=>[k,r.usage?.[k]])),tools:run.tools?.slice(-2)});
 }
 await save(s);console.log(JSON.stringify(out,null,2));
}else if(command==='freeze-data'||command==='verify-data'){
 const s=await load(),snapshot={facts:[],research:[]};
 for(const [key,route] of [['facts','financial-data'],['research','assets/records']]){
  let offset=0;
  while(true){const page=await api(`/api/projects/${projectId}/${route}?limit=200&offset=${offset}`);const data=page.data??page;const rows=data.items??[];snapshot[key].push(...rows);offset+=rows.length;if(!rows.length||offset>=data.total||data.next_offset===null)break;}
 }
 const hash=sha(JSON.stringify(snapshot));
 await json(command==='freeze-data'?'structured-data-before.json':'structured-data-after.json',snapshot);
 if(command==='freeze-data'){s.structuredDataSha256=hash;}else{s.structuredDataUnchanged=hash===s.structuredDataSha256;}
 await save(s);console.log(JSON.stringify({facts:snapshot.facts.length,research:snapshot.research.length,hash,unchanged:s.structuredDataUnchanged}));
}else if(command==='freeze-after'){
 const s=await load(),cat=await api(`/api/projects/${projectId}/assets/catalog`);await json('catalog-after.json',cat);s.finalDataSummary=cat.summary;s.catalogUnchanged=sha(JSON.stringify(cat))===s.catalogSha256;await save(s);console.log(JSON.stringify({summary:cat.summary,catalogUnchanged:s.catalogUnchanged}));
}else throw Error('Use init/ready/start LABEL/poll/freeze-after');
