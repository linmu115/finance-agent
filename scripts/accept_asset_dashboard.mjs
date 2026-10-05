// User-authorized live acceptance, using only the visible application's normal APIs.
import {readFile,writeFile,mkdir} from 'node:fs/promises';
import path from 'node:path';
const base='http://127.0.0.1:3001',root=path.resolve('data/acceptance/asset-dashboard');
await mkdir(root,{recursive:true});
const request=async(url,body)=>{
 const response=await fetch(base+url,body===undefined?{}:{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
 const data=await response.json();if(!response.ok)throw Error(JSON.stringify(data));return data;
};
const manifestPath=path.join(root,'manifest.json');
let manifest;try{manifest=JSON.parse(await readFile(manifestPath,'utf8'));}catch(error){if(error.code!=='ENOENT')throw error;manifest={project:await request('/api/projects',{name:'资产看板验收 · 财报、研报与金融建模'}),tasks:[]};await writeFile(manifestPath,JSON.stringify(manifest,null,2));}
const action=process.argv[2];
if(action==='status'){
 for(const task of manifest.tasks){const run=await request('/api/runs/'+task.runId);await writeFile(path.join(root,task.kind+'-run.json'),JSON.stringify(run,null,2));const chat=await request('/api/conversations/'+task.conversationId);await writeFile(path.join(root,task.kind+'-conversation.json'),JSON.stringify(chat,null,2));console.log(JSON.stringify({kind:task.kind,runId:task.runId,stage:run.stage,state:run.state,status:run.status,error:run.error,lastTools:run.tools?.slice(-3),answer:chat.messages?.filter(m=>m.role==='assistant').at(-1)?.content?.slice(-700)}));}
 console.log(JSON.stringify({catalog:await request(`/api/projects/${manifest.project.id}/assets/catalog`)}));
}else if(action==='financial_repair'){
 if(manifest.tasks.some(task=>task.kind===action))throw Error('Repair task already exists. Inspect it instead of replaying.');
 const financial=manifest.tasks.find(t=>t.kind==='financial');
 const state=await request('/api/runs/'+financial.runId);if(state.status!=='completed')throw Error('Financial ingestion still active');
 const prompt=`财报映射复核｜补充分部与原格维度
工程验收发现已保存脚本对部分列写了 dimensions_json；当前运行服务的列定义正确字段是 dimensions（行属性仍可用 dimensions_json）。结果部分合并原格内同指标多条数值被合并，分部与合计混在一起。请修复当前报告的这批映射，不改原文数字、不调用通用数据库管理。
报告 document_id=${financial.documentId}，原处理 processing_id=65f43fca4ab9470c97077c895d7b4241，已提交脚本结果 run_id=def6f2ab90934380948bc64fc9ce653a。受影响 table index：2、7、18、22、26、27、28、34、39、40、41、48。
可以 process_documents 复用现有进度，在 run_cleaning_script 的 script_refs 中引用该 run_id，从 /input/cleaning_def6f2ab90934380948bc64fc9ce653a.json 读取已保存映射，筛选上述12张表；将所有 schema.columns_json 和 rows[].attributes.columns_json 里的列级 dimensions_json 无损转为 dimensions（若同名冲突必须回原文核实），保留行维度、数值坐标、单位、期间和已有明确排除。输出 cleaning_result.json，再 get_cleaning_result 分批核验、commit_cleaning_result 提交。
这是修复既有映射的程序字段错误，避免重新生成整份映射。重点核对分部、地区、权益组成、账龄等维度及公司合计没有混淆。已有复杂附注的真实待核验项仍保留。完成后核对 revenue 按分部/公司合计区分，说明新增恢复的记录及剩余疑点。`;
 const task={kind:action,conversationId:financial.conversationId,documentId:financial.documentId,prompt,startedAt:new Date().toISOString()};manifest.tasks.push(task);await writeFile(manifestPath,JSON.stringify(manifest,null,2));
 Object.assign(task,await request('/api/conversations/'+task.conversationId+'/messages',{content:prompt,documentIds:[]}));await writeFile(manifestPath,JSON.stringify(manifest,null,2));console.log(JSON.stringify({kind:action,runId:task.runId,conversationId:task.conversationId}));
}else if(action==='modeling_review'){
 if(manifest.tasks.some(task=>task.kind===action))throw Error('Model review already exists. Inspect instead of replaying.');
 const original=manifest.tasks.find(t=>t.kind==='modeling');
 if((await request('/api/runs/'+original.runId)).status!=='completed')throw Error('Modeling still active');
 const prompt=`建模验收复核｜修正利润桥与假设归类
三份模型的数值公式已独立复算一致，但经济口径复核发现以下问题，请在原有三个 artifact_id 上保存新版本并保留旧版，不另建重复模型，也不重跑入库。
1. 瑞和模型的 profit_bridge 定义说 Operating loss 在财务收入/成本之前，finance_expense_treatment 却设为 separate，计算再次扣财务费用，导致 reported_operating_profit_residual = -2986（人民币千元）。请重新核对财报第28页，选择与原文小计一致的处理（该利润桥应排除财务费用）。保留利息指标本身用于独立分析，核对2024、2025经营小计及变动桥余项归零，勿通过改造实际值硬凑平衡。
2. 伊利两个DCF模型的 EBIT=13839/14677/15335 是依据收入、成本、税金、销售/管理/研发费用推导的经营EBIT，现 source_refs 仅引用12938/14116/15196（这是原表营业利润）。请把引用改为真正支持推导的组成数据/原文，不混称两种小计。
3. 终值EBIT率和终值税率是将有限年度预测延展到永续期的本次估值假设；terminal.ebit_margin 与 terminal.tax_rate 应归为 assumption，并说明参考来源，不能说“避免额外假设”或当成已披露的永续数值。
4. 净债务桥把“短期借款及交易性金融负债＋长期借款及应付债券”作为有息负债代理、把全部现金视为可抵扣的多余现金；少数股东权益以账面值代理其经济价值；基期NWC用简化流动项目代理经营性资本；非经营资产取0也有遗漏价值风险。请在对应input_basis中明确这些是本次估值采用的代理/假设，区分来源金额与经济分类选择。数值计算和原始金额正确的部分保留，不凭空改数。
对基准和压力两个DCF同步修正依据分类与引用，仍只有WACC不同。保存后核对利润桥、DCF结果、原始输入和来源，再给出修正后的结论与限制。`;
 const task={kind:action,conversationId:original.conversationId,prompt,startedAt:new Date().toISOString()};manifest.tasks.push(task);await writeFile(manifestPath,JSON.stringify(manifest,null,2));
 Object.assign(task,await request('/api/conversations/'+task.conversationId+'/messages',{content:prompt,documentIds:[]}));await writeFile(manifestPath,JSON.stringify(manifest,null,2));console.log(JSON.stringify({kind:action,runId:task.runId}));
}else if(action==='modeling'){
 if(manifest.tasks.some(task=>task.kind===action))throw Error('Modeling task already exists. Continue its visible conversation instead of replaying.');
 for(const prior of manifest.tasks){const state=await request('/api/runs/'+prior.runId);if(state.status!=='completed')throw Error(`${prior.kind} is not completed`);}
 const chat=await request(`/api/projects/${manifest.project.id}/conversations`,{});
 const prompt=`金融建模验收｜瑞和财务质量与伊利DCF
请使用当前项目已经入库的两份报告与原文完成以下研究，在这个会话里执行计算并保存可编辑、可复算的模型到资产看板。无需重新入库，不联网，不调用通用数据库管理。
一、瑞和数智科技控股有限公司：建立2024年上半年与2025年上半年可比的 financial_quality 模型，比较收入、毛利、净利润、经营现金流及现金利润差，解释由亏转盈是否代表主营经营改善。中期流量不能冒充全年，2024H1为182天、2025H1为181天；缺失期初余额的指标保留不可计算及原因。按原文区分经营损益、公允价值变动、税项、合并与归母，不把税前公允价值收益直接当作税后非经常性净利。
二、伊利股份：用国信证券2025-07-16研报中的2024A作为基期、2025—2027E作为显式预测，构建 FCFF DCF。先获取模型schema并核对收入、EBIT口径、税率、折旧摊销、资本开支、营运资本变动、净债务与股数。全部输入注明来源、口径和性质：研报引用历史值、机构预测、本次估值假设必须区分；来源存在不等于已由公司正式披露。预测没有的数据可以提出清楚标注的合理假设，说明影响，不能用合成示例当公司事实。币种、金额单位和每股单位保持一致；不用期末营运资本余额替代现金流变动，也不能重复加减现金。
为便于验证，基准模型使用WACC 8%、永续增长率2%、终值ROIC 12%、年末折现；其他终值和桥接参数按原文或明确假设。该模型定义估值时点为2024年末，信息来自2025-07-16报告，必须说明这是事后情景演示，不能冒充当时已知的历史估值。
保存基准DCF，再保持其余参数完全一致，将WACC改为10%保存为独立压力情景，核对折现率升高的影响。保存的模型标题应包含对应公司名，关键输入填写input_basis和精确source_refs。重要假设、缺失项和不能核实的估值限制在会话里明确说明。
最终简洁汇报两个公司的分析结论、三份已保存模型及DCF差异。实际调用计算工具完成建模，不只描述思路。`;
 const task={kind:action,conversationId:chat.id,prompt,startedAt:new Date().toISOString()};manifest.tasks.push(task);await writeFile(manifestPath,JSON.stringify(manifest,null,2));
 Object.assign(task,await request('/api/conversations/'+chat.id+'/messages',{content:prompt,documentIds:[]}));await writeFile(manifestPath,JSON.stringify(manifest,null,2));console.log(JSON.stringify(task));
}else{
 const sources={
  financial:{file:'samples/native-pdf/Ruihe_Data_2025_Interim_57p.pdf',name:'睿和数智_2025中期报告_57页.pdf',title:'财报入库验收｜57页睿和数智中报',prompt:'请将附件财报完整处理入库，供后续金融建模。根据报告原文登记真实公司名称、原文别名、证券标识及披露日期，不把文件名当成主体。使用现有脚本清洗工具，完整处理主表和附注候选表，核对期间、币种、单位、公司与业务维度；中期流量和期末余额、同比列不能混淆。每批落库后继续剩余批次，直到没有待处理表。遇到不能确认的数值、原格或口径，保留明确待核验说明并继续其他表，不编造缺失值。完成后报告覆盖范围、数据量和真正未决项，保留原文可追溯。本轮不联网、不做金融建模、不调用通用数据库管理。'},
  research:{file:'samples/retained-originals/6242c4d8fd51-guosen-yili-20250716.pdf',name:'国信证券_伊利股份深度报告_20250716_38页.pdf',title:'研报入库验收｜38页伊利深度报告',prompt:'请将附件研报完整处理入库，供后续研究与建模。按原文登记机构、真正的证券分析师、报告发布日期及公司/行业对象和有依据的别名。共用脚本清洗已有表格：实际引用值、机构预测、行业统计和假设分别保存，多公司表保留各行对象；不把研报数字混入公司正式披露。覆盖所有候选数值表以及全部正文页，保存重要观点、风险、催化因素及明确归属和原文定位。图形无法可靠读数或语义有歧义时标待核验，继续剩余工作，不猜值。直到 pending_tables 和 pending_pages 均为空再报告完成。本轮不联网、不做金融建模、不调用通用数据库管理。'}
 };
 if(!sources[action])throw Error('Use financial, research, or status');
 if(manifest.tasks.some(task=>task.kind===action))throw Error('Task already exists. Inspect and continue its visible conversation; do not replay.');
 const source=sources[action],chat=await request(`/api/projects/${manifest.project.id}/conversations`,{});
 const form=new FormData();form.append('files',new Blob([await readFile(source.file)],{type:'application/pdf'}),source.name);
 const upload=await fetch(base+`/api/projects/${manifest.project.id}/uploads`,{method:'POST',body:form});const uploaded=await upload.json();if(!upload.ok)throw Error(JSON.stringify(uploaded));
 const task={kind:action,source:source.file,conversationId:chat.id,documentId:uploaded.documents[0].id,prompt:source.title+'\n'+source.prompt,startedAt:new Date().toISOString()};
 manifest.tasks.push(task);await writeFile(manifestPath,JSON.stringify(manifest,null,2));
 const started=await request('/api/conversations/'+chat.id+'/messages',{content:task.prompt,documentIds:[task.documentId]});Object.assign(task,started);await writeFile(manifestPath,JSON.stringify(manifest,null,2));console.log(JSON.stringify({projectId:manifest.project.id,...task}));
}
