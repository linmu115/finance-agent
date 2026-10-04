/** Real-company research DEVELOPMENT workflow. --prepare is entirely offline.
 * --run requires separate authorization; never starts/stops a host, changes settings,
 * retries a terminal run, or treats interface success as financial-accuracy acceptance.
 */
import fs from 'node:fs/promises';
import path from 'node:path';
import {setTimeout as delay} from 'node:timers/promises';
import {researchHash as hash,researchWorkflowIO} from './research_workflow_io.mjs';
import {reconcileContinuationAccounting} from './research_workflow_accounting.mjs';

const root=path.resolve(import.meta.dirname,'..'),args=process.argv.slice(2);
const arg=(key,fallback)=>args.includes(key)?args[args.indexOf(key)+1]:fallback;
const version=arg('--version','v06');if(!['v06','v07'].includes(version))throw Error('Supported workflow versions: v06, v07');
const base=arg('--base-url','http://127.0.0.1:3001');
const prefix=path.resolve(root,arg('--prefix','benchmark/results/liugong-research-workflow-'+version));
const originalBudget={max_model_calls:60,max_input_tokens:3000000,max_output_tokens:450000,max_total_tokens:3450000,max_wall_seconds:1800};
let budget=originalBudget,continuation;
if(version==='v07'){
 const priorPath=path.resolve(root,arg('--resume-from','benchmark/results/liugong-research-workflow-v06.json'));
 const priorRaw=await fs.readFile(priorPath,'utf8'),prior=JSON.parse(priorRaw),last=prior.stages?.at(-1);
 if(prior.status!=='failed'||prior.stages?.length!==1||!last?.run?.evaluation||last.run.status!=='failed')throw Error('v07 continuation expects the preserved first-stage terminal v06 failure');
 const accounting=last.run.evaluation;if(JSON.stringify(accounting.budget)!==JSON.stringify(originalBudget))throw Error('Prior budget differs from the original frozen research budget');
 const usage=accounting.usage;
 budget={max_model_calls:originalBudget.max_model_calls-usage.model_calls,max_input_tokens:originalBudget.max_input_tokens-usage.input_tokens,max_output_tokens:originalBudget.max_output_tokens-usage.output_tokens,max_total_tokens:originalBudget.max_total_tokens-usage.total_tokens,max_wall_seconds:Math.floor(originalBudget.max_wall_seconds-accounting.elapsed_seconds)};
 if(Object.values(budget).some(value=>!Number.isFinite(value)||value<=0))throw Error('Prior run left no usable continuation budget');
 const auditPath=path.join(path.dirname(priorPath),last.events_file),auditRaw=await fs.readFile(auditPath,'utf8'),events=JSON.parse(auditRaw);
 continuation={project_id:prior.project_id,conversation_id:last.conversation_id,prior_report:path.relative(root,priorPath).replaceAll('\\','/'),prior_report_sha256:hash(priorRaw),prior_task_sha256:prior.task_sha256,prior_run_id:last.run.id,prior_budget_group_id:prior.budget_group_id,prior_audit:path.relative(root,auditPath).replaceAll('\\','/'),prior_audit_sha256:hash(auditRaw),prior_successful_tools:[...new Set(events.filter(e=>e.type==='tool_result'&&e.data?.result?.status==='ok').map(e=>e.data.name))],prior_usage:usage,prior_elapsed_seconds:accounting.elapsed_seconds,original_budget:originalBudget,remaining_budget:budget,accounting_note:'A new continuation budget group receives only the original remaining calls/tokens and floored remaining active elapsed seconds. Previous failed usage remains included; operator waiting/restart time is not charged twice.'};
}
const scope={company:'广西柳工机械股份有限公司',ticker:'000528',research_cutoff:'2025-09-08',valuation_base_year:2025,valuation_date:'2025-12-31',workflow_messages:3,tool_limit_per_message:version==='v07'?64:24};
const tasks=[
`这是实际公司研究工作流的开发验收，不是已通过的精度留出测试。请研究柳工（000528），研究信息截止日为2025年9月8日。当前项目独立保存所有原文和成果，不读取其他项目、基准答案或本地验收资料。每条消息工具上限24次，配置不改变；注意合理分配搜索、原文阅读和保存次数，真实失败不要同参数反复重试。
第一阶段只做已披露业绩归因与盈利质量，暂不写估值结论。自己通过搜索和发行人/法定披露渠道找到截止日前已经公开的年报、中报或正式公告，归档实际原文；不要只依赖新闻摘要，不能猜URL或页码。明确来源发布日、取回日和披露期间；历史页面若后来更新、发布日期不明，应说明历史可得性限制。PDF只需阅读时先索引原文，再按目录定点阅读，不必清洗全部财报。
把同期间、同合并范围的收入、利润、经营现金流及有证据的应收/存货等期初期末项目放入财务质量模型，实际保存 financial_quality 成果。对收入、成本、费用、其他经营项目和非经常性损益解释利润变化：有充分同口径字段才运行归因桥；销量/单价或分部数据未披露时保留残差和缺项，不把推断写成披露事实。合并经营现金流不能不加说明地与不同股东范围的利润混配；周转率缺期间边界时不得补零。
通过 input_basis 按输入路径标记 disclosed/derived/assumption 并说明依据，原文引用只放同路径 source_refs；披露值要有可定位原文，推导值要给公式与输入来源。最后简短列出来源ID、财务质量成果ID、业绩驱动、现金利润差与数据缺项，供下一阶段复用。这个阶段不要搜索同行估值，不生成虚构参数。`,
`继续使用当前项目已经保存的证据，仍只使用2025年9月8日及之前可获得的信息。现在完成产业链与估值。目标价值时点统一为2025财年末，DCF base_year=2025，显式预测从2026年开始；截至研究日尚未披露的2025全年收入、营运资本和年末价值桥必须明确标为预测/研究假设，不能冒充2025全年实际数，也不能把年末模型值称作2025年9月8日即时价格。
先核对已有模型结构和项目来源，必要时定点补充原文。参数由你提出合理研究假设并解释依据：收入或等效销量/单价、原料敞口、提价、传导率、需求弹性和时滞，以及利润、税、折旧、资本开支、营运资本、WACC、永续增长、ROIC和净债务到普通股价值桥。没有披露的参数明确标为 assumption；材料成本占比不等于某一种商品的真实价格敞口。多产品只能采用明确说明范围的整体等效量，不能直接相加不同机械的实物台数当作同质产品。缺失净债务/NCI/股数等不得默认为零；可以提出有依据的估计并说明不确定性，股数与金额倍率单独声明，扣现、非经营资产、可转债与稀释保持一致。
保存三个 manufacturing_scenario 成果，标题分别包含“基线”“经营上行”“经营下行”。三者采用相同口径、单位、预测年限和可追踪基线，通过明确、可调整的成本/销量/价格冲击形成经营情景；上下行指经营效果，不仅改折现率。保存一份独立DCF，用 source_model 引用“基线”情景实际版本、variant=scenario，完整继承参数依据，并包含WACC/永续增长敏感性。使用独立可比估值工具交叉检查时，只有查到截止日前可靠、同估值日期及同利润口径的同行价格/倍数与分母，才能保存 comparables；明确PE是股权、EV/EBITDA是企业价值。若查不到必要同行数据，诚实列出缺项并声明相对估值未完成，不能塞入示例倍数或凭空生成同行股价；允许这一项留缺，不得说已通过。
保存 industry_chain 成果，区别上游/企业/下游的原文事实、方向推断、量化敞口和研究假设，附实际证据与依赖。按路径提供参数性质及来源，避免重复抄写整篇原文。每条消息仍最多24次工具；最后列出各成果ID、基线/上下行结果和未完成项。自动计算成功并不代表估值正确，后续还要独立原文核对与复算。`,
`这是同一项目的独立新会话。请实际列出并按需读取已保存的柳工研究来源、财务质量、三种经营情景、独立DCF、产业链和存在时的相对估值；不要依赖之前会话的隐含上下文。研究信息截止日仍为2025年9月8日，目标价值时点2025年末。
先基于读取到的当前成果保存一份 investment_memo，包含可定位事实、判断、估值区间与口径、催化剂、主要风险、量化可证伪指标/条件/期限/行动，以及缺项；实际记录所依赖的成果版本。相对估值若缺来源，备忘录明确未完成，不能以DCF代替其验收。
随后做一次明确的增量假设更新：只把标题含“基线”的制造业情景内 dcf.discount.wacc 在原值上增加0.01（一个百分点），其他计算输入保持不变。这是新的研究假设，不是新披露；更新相应 input_basis 的 rationale，保留原文引用作背景，不宣称新WACC由原文直接给出。用原 artifact_id/parent_revision_id 保存新情景版本。实际读取依赖状态，记录哪些下游旧结论因此过期。通过 source_model 对新情景版本定点重算已有独立DCF并保存其新版本；再更新刚保存的同一备忘录，只修改受估值假设影响的部分，复用原有仍有效事实。保留全部历史版本，不重新下载未变化来源，不重做盈利质量或经营上下行情景，不把未更新的成果悄悄称为最新。
每条消息仍最多24次工具。最终简短列出新旧情景/DCF/备忘录版本、实际 changed_dependencies、WACC修改及价值变化、仍未更新或未验证的项目。请把真实工具失败和资料缺口如实留下；终态失败不自动重试。`
];
if(version==='v07'){
 for(let i=0;i<tasks.length;i++)tasks[i]=tasks[i].replaceAll('24次','64次');
 tasks[0]='接续本项目上次因工具次数上限而中断的同一研究任务。已有报告已下载、归档并完成原文索引；优先读取当前项目目录与现有索引/原文，不再搜索或下载同一份报告，不重复准备已有索引。先把上次尚未保存的盈利质量成果完成，再继续原研究目标；没有任何正确答案数值或页码预置。\n本轮公开配置由原 maxTokens=8192、每条24工具改为 maxTokens=32768、每条64工具；总调用和token配额扣除了前次实际消耗，并未增加。以下原研究任务中的64是本轮配置。\n'+tasks[0];
}
const contract={version:'liugong-'+version+'-development',accuracy_holdout:false,
 automatic_scope:['Actual Pi tool events, source snapshots and saved artifact lineage','Frozen budget and '+scope.tool_limit_per_message+'-tool configuration','Exact source_model import and WACC-only computational edit','Actual stale dependency evidence before targeted revision'],
 independent_review_required:['Issuer facts: original text, publication cutoff, period, scope, units and nonrecurring classification','Profit/quality formulas and independent numeric recalculation','Explicit assumptions and aggregation limits for three operating scenarios','DCF timing, terminal reinvestment, EV/equity bridge and shares','Peer evidence date/basis and independent relative-valuation calculation if available','Chain mechanisms, memo evidence and falsification relevance','Export/recompute and historical revision evidence'],
 no_fake_pass:['Missing relative-valuation sources remain an explicit unverified capability','Artifact or tool existence never establishes factual or economic correctness','API completed does not mean full acceptance','No answer values, page positions, or benchmark gold are supplied to the agent'],...(continuation?{configuration_change:{prior:{maxTokens:8192,maxToolCalls:24},current:{maxTokens:32768,maxToolCalls:64},reason:'Explicitly versioned response to real reasoning-length and tool-budget failures; same cumulative model-call/token caps',previous_failed_report:continuation.prior_report}}:{})};
const frozen={kind:'development_real_manufacturing_research',prepared_at:new Date().toISOString(),scope,budget,tasks,conversation_plan:[continuation?'continue_original_stage_1':'create','reuse_stage_1','create_independent'],contract,restrictions:['Prepare mode performs no HTTP or model calls','Never start or stop any host','Never change API/model/search/runtime settings','Never read another project or holdout materials','Never retry a terminal stage automatically','All three stages share one budget group; input limit remains observed-usage soft cap'],...(continuation?{continuation}:{})};
const payload=x=>({scope:x.scope,budget:x.budget,tasks:x.tasks,conversation_plan:x.conversation_plan,contract:x.contract,restrictions:x.restrictions,...(x.continuation?{continuation:x.continuation}:{})});
frozen.task_sha256=hash(payload(frozen));
await fs.mkdir(path.dirname(prefix),{recursive:true});
if(args.includes('--prepare')){await fs.writeFile(prefix+'.before.json',JSON.stringify(frozen,null,2),{flag:'wx'});console.log('FROZEN',prefix+'.before.json',frozen.task_sha256);process.exit(0);}
if(!args.includes('--run'))throw Error('Use --prepare (offline) or separately authorized --run');
if(new URL(base).origin!=='http://127.0.0.1:3001')throw Error('This development runner is restricted to the existing 127.0.0.1:3001 host');
const before=JSON.parse(await fs.readFile(prefix+'.before.json','utf8'));
if(before.task_sha256!==hash(payload(before)))throw Error('Frozen task integrity mismatch');
if((version==='v07')!==!!before.continuation)throw Error('Selected version and frozen continuation differ');
if(before.continuation){for(const [file,expected] of [[before.continuation.prior_report,before.continuation.prior_report_sha256],[before.continuation.prior_audit,before.continuation.prior_audit_sha256]])if(hash(await fs.readFile(path.join(root,file),'utf8'))!==expected)throw Error('Preserved prior evidence changed');}
const {api,audit,artifacts,implementationHashes}=researchWorkflowIO(root,base);
const output=prefix+'.json';await fs.writeFile(output,JSON.stringify({status:'starting'}),{flag:'wx'});
const report={kind:before.kind,accuracy_holdout:false,acceptance_status:'not_evaluated',requires_independent_evidence_review:true,contract:before.contract,task_sha256:before.task_sha256,started_at:new Date().toISOString(),status:'running',checks:[],stages:[],failures:[],budget_group_id:'liugong-research-'+Date.now(),...(before.continuation?{continuation:before.continuation}:{})};
let activeRun;
const save=()=>fs.writeFile(output,JSON.stringify(report,null,2));
const check=(name,ok,evidence)=>report.checks.push({name,status:ok?'passed':'failed',evidence,scope:'workflow_only'});
const successfulResults=events=>events.filter(e=>e.type==='tool_result'&&e.data?.result?.status==='ok');
async function wait(id){
 const deadline=Date.now()+(before.budget.max_wall_seconds+60)*1000;let last=0;
 while(Date.now()<deadline){const run=await api('/api/runs/'+id);report.active_run=run;report.last_observed_run=run;if(['completed','failed','cancelled'].includes(run.status)){activeRun=undefined;delete report.active_run;return run;}if(Date.now()-last>15000){console.log(run.status,run.stage,JSON.stringify(run.usage));await save();last=Date.now();}await delay(1500);}
 await api('/api/runs/'+id+'/cancel',{});activeRun=undefined;throw Error('Observer cancelled the active run after budget plus 60-second observation grace; not user cancellation');
}
async function stage(index,conversationId){
 const conversation=conversationId?{id:conversationId}:await api('/api/projects/'+report.project_id+'/conversations',{});
 const attempt={index,conversation_id:conversation.id,submission_started_at:new Date().toISOString()};(report.stage_attempts??=[]).push(attempt);await save();
 const started=await api('/api/conversations/'+conversation.id+'/messages',{content:before.tasks[index-1],documentIds:[],evaluation:{profile:'financial',budget_group_id:report.budget_group_id,budget:before.budget}});
 attempt.run_id=started.runId;
 activeRun=started.runId;report.active_stage={index,conversation_id:conversation.id,run_id:started.runId};await save();
 const run=await wait(started.runId),events=await audit(run.id),auditPath=prefix+`.stage-${index}.audit.json`;
 await fs.writeFile(auditPath,JSON.stringify(events,null,2),{flag:'wx'});
 const chat=await api('/api/conversations/'+conversation.id),messages=chat.messages.filter(m=>m.runId===run.id),saved=await artifacts(report.project_id);
 const entry={index,conversation_id:conversation.id,run,events_file:path.basename(auditPath),messages,artifacts:saved};report.stages.push(entry);delete report.active_stage;
 report.failures.push(...events.filter(e=>e.type==='tool_error'||e.type==='model_usage'&&['error','aborted','length'].includes(e.data?.stopReason)).map(event=>({stage:index,run_id:run.id,event})));
 check(`阶段${index}真实Pi完成且使用共享预算`,run.status==='completed'&&run.evaluation?.profile==='financial'&&JSON.stringify(run.evaluation).includes(report.budget_group_id),{id:run.id,status:run.status,usage:run.usage,evaluation:run.evaluation});
 check(`阶段${index}保留${before.scope.tool_limit_per_message}次工具限制`,events.filter(e=>e.type==='tool_request').length<=before.scope.tool_limit_per_message,{tool_requests:events.filter(e=>e.type==='tool_request').length,expected_max:before.scope.tool_limit_per_message});
 await save();if(run.status!=='completed')throw Error(`Stage ${index} ended ${run.status}; no automatic retry or later stage`);
 return {...entry,events};
}
function decimal(value){const text=String(value),match=/^([+-]?)(\d+)(?:\.(\d*))?$/.exec(text);if(!match)throw Error('Unverifiable decimal '+text);return {n:BigInt((match[1]==='-'?'-':'')+match[2]+(match[3]||'')),d:10n**BigInt((match[3]||'').length)};}
const fractionEqual=(a,b)=>{const x=decimal(a),y=decimal(b);return x.n*y.d===y.n*x.d;};
function changedInputs(a,b,p=''){
 if(a&&b&&typeof a==='object'&&typeof b==='object'){return [...new Set([...Object.keys(a),...Object.keys(b)])].filter(k=>p||!['input_basis','source_refs'].includes(k)).flatMap(k=>changedInputs(a[k],b[k],p?`${p}.${k}`:k));}
 if(a===b)return [];try{if(fractionEqual(a,b))return [];}catch{}return [{path:p,before:a,after:b}];
}
const canonical=x=>Array.isArray(x)?x.map(canonical):x&&typeof x==='object'?Object.fromEntries(Object.keys(x).sort().map(k=>[k,canonical(x[k])])):x;
const exact=(a,b)=>JSON.stringify(canonical(a))===JSON.stringify(canonical(b));
try{
 const settings=await api('/api/settings');if(!settings.search?.hasKey)throw Error('Search is not configured; settings will not be changed');if(settings.runtime?.maxToolCalls!==before.scope.tool_limit_per_message)throw Error('Tool setting differs from frozen contract; settings will not be changed');
 if(before.contract.configuration_change&&settings.llm?.maxTokens!==before.contract.configuration_change.current.maxTokens)throw Error('Model maxTokens differs from frozen continuation contract; settings will not be changed');
 report.preflight={tool_limit:settings.runtime.maxToolCalls,model:settings.llm?.model,max_tokens:settings.llm?.maxTokens,search_provider:settings.search?.provider};
 report.implementation_before=await implementationHashes();
 const project=before.continuation?{id:before.continuation.project_id}:await api('/api/projects',{name:'真实制造业研究开发验收 · 柳工 · 截止2025-09-08'});report.project_id=project.id;await save();
 const first=await stage(1,before.continuation?.conversation_id),firstNames=successfulResults(first.events).map(e=>e.data.name);
 const existingEvidence=before.continuation?.prior_successful_tools||[],sourceReady=(firstNames.includes('search_web')&&firstNames.includes('fetch_research_source'))||(existingEvidence.includes('search_web')&&existingEvidence.includes('fetch_research_source')&&existingEvidence.includes('prepare_document_sources'));
 const firstReady=sourceReady&&first.artifacts.some(a=>a.kind==='financial_quality'&&a.run_id===first.run.id);
 check('第一阶段已有实际检索归档证据并保存盈利质量成果',firstReady,{tools:firstNames,prior_evidence:before.continuation?{run_id:before.continuation.prior_run_id,audit_sha256:before.continuation.prior_audit_sha256,tools:existingEvidence}:null,quality_ids:first.artifacts.filter(a=>a.kind==='financial_quality').map(a=>a.id)});
 if(!firstReady)throw Error('First-stage required evidence or quality artifact is missing; later dependent stages not sent');
 const second=await stage(2,first.conversation_id),scenarios=second.artifacts.filter(a=>a.kind==='manufacturing_scenario'),baseline=scenarios.filter(a=>a.title.includes('基线'));
 check('经营基线/上行/下行及产业链已保存',scenarios.length>=3&&['基线','经营上行','经营下行'].every(label=>scenarios.some(a=>a.title.includes(label)))&&second.artifacts.some(a=>a.kind==='industry_chain'),second.artifacts.map(({id,kind,title,revision_id})=>({id,kind,title,revision_id})));
 const imports=second.artifacts.filter(a=>a.kind==='dcf'&&a.source_model);
 check('独立DCF通过固定版本引用导入实际情景',imports.some(a=>scenarios.some(s=>s.id===a.source_model.artifact_id&&s.revision_id===a.source_model.revision_id&&exact(a.spec,s.result?.results?.[a.source_model.variant+'_dcf_spec']))),imports.map(a=>({id:a.id,source_model:a.source_model,dependencies:a.dependencies})));
 check('估值基期与预测起点符合明确时点',scenarios.length>=3&&scenarios.every(a=>a.spec.base_year===2025&&a.spec.baseline?.[0]?.year===2026)&&imports.every(a=>a.spec.base_year===2025&&a.spec.forecast?.[0]?.year===2026),{scenarios:scenarios.map(a=>({id:a.id,base_year:a.spec.base_year,first_forecast_year:a.spec.baseline?.[0]?.year})),dcf:imports.map(a=>({id:a.id,base_year:a.spec.base_year,first_forecast_year:a.spec.forecast?.[0]?.year}))});
 const comps=second.artifacts.filter(a=>a.kind==='comparables');report.relative_valuation={status:comps.length?'present_pending_independent_source_and_formula_review':'missing_not_verified',artifact_ids:comps.map(a=>a.id),stage_answer:second.messages.filter(m=>m.role==='assistant').map(m=>m.content).join('\n'),note:'No company facts or peer values are preloaded into this runner. Existence is never a factual accuracy pass.'};
 if(baseline.length!==1||!imports.some(a=>a.source_model.artifact_id===baseline[0].id))throw Error('Exactly one baseline scenario and its imported DCF are required before incremental update; no third stage sent');
 const third=await stage(3),thirdResults=successfulResults(third.events),savedRevisions=thirdResults.filter(e=>['run_financial_model','save_research_report'].includes(e.data.name)).map(e=>e.data.result.data);
 check('第三阶段在项目独立会话读取实际成果',third.conversation_id!==first.conversation_id&&thirdResults.some(e=>['list_research_artifacts','read_research_artifact'].includes(e.data.name)),{first_conversation:first.conversation_id,third_conversation:third.conversation_id});
 const oldBaseline=baseline.length===1?baseline[0]:undefined,newBaseline=oldBaseline&&third.artifacts.find(a=>a.id===oldBaseline.id);
 let waccChange=false,changes=[];
 if(oldBaseline&&newBaseline){changes=changedInputs(oldBaseline.spec,newBaseline.spec);const a=decimal(oldBaseline.spec.dcf.discount.wacc),b=decimal(newBaseline.spec.dcf.discount.wacc);waccChange=(b.n*a.d-a.n*b.d)*100n===a.d*b.d;}
 const changedBasis=newBaseline?.spec.input_basis?.['dcf.discount.wacc'];
 check('增量更新仅将基线WACC增加一个百分点并保留历史父版本',!!oldBaseline&&!!newBaseline&&newBaseline.parent_revision_id===oldBaseline.revision_id&&waccChange&&changes.length===1&&changes[0].path==='dcf.discount.wacc'&&changedBasis?.basis==='assumption'&&typeof changedBasis?.rationale==='string'&&changedBasis.rationale.trim().length>0,{old_id:oldBaseline?.id,old_revision:oldBaseline?.revision_id,new_revision:newBaseline?.revision_id,changes,new_basis:changedBasis});
 const staleEvidence=thirdResults.flatMap(e=>e.data.name==='list_research_artifacts'?e.data.result.data.artifacts||[]:e.data.name==='read_research_artifact'?[e.data.result.data]:[]).filter(a=>a.dependency_status==='stale');
 check('增量重算前实际读取到下游过期证据',staleEvidence.some(a=>a.changed_dependencies?.some(d=>d.id===oldBaseline?.id)),staleEvidence.map(({id,revision_id,changed_dependencies})=>({id,revision_id,changed_dependencies})));
 const oldDcf=oldBaseline&&imports.find(a=>a.source_model.artifact_id===oldBaseline.id),newDcf=oldDcf&&third.artifacts.find(a=>a.id===oldDcf.id),memos=savedRevisions.filter(a=>a.kind==='investment_memo');
 check('只更新受影响DCF与备忘录并保存其新版本',!!oldDcf&&!!newDcf&&newDcf.parent_revision_id===oldDcf.revision_id&&newDcf.source_model?.revision_id===newBaseline?.revision_id&&memos.some(a=>memos.some(previous=>a.id===previous.id&&a.parent_revision_id===previous.revision_id)),{dcf:{old_revision:oldDcf?.revision_id,new_revision:newDcf?.revision_id,source_model:newDcf?.source_model},memo_revisions:memos.map(({id,revision_id,parent_revision_id,dependencies})=>({id,revision_id,parent_revision_id,dependencies}))});
 const thirdRequests=third.events.filter(e=>e.type==='tool_request');
 check('增量阶段复用来源与未变化模型',!thirdRequests.some(e=>['search_web','fetch_research_source','process_documents'].includes(e.data.name)||e.data.name==='run_financial_model'&&e.data.args?.kind==='financial_quality'),thirdRequests.map(e=>({name:e.data.name,kind:e.data.args?.kind,artifact_id:e.data.args?.artifact_id})));
 report.sources=(await api('/api/projects/'+project.id+'/research/sources')).sources;
 report.implementation_after=await implementationHashes();report.implementation_changed=[...new Set([...Object.keys(report.implementation_before),...Object.keys(report.implementation_after)])].filter(file=>report.implementation_before[file]!==report.implementation_after[file]);
 check('执行期间实现保持冻结',report.implementation_changed.length===0,report.implementation_changed);
 report.status=report.checks.every(c=>c.status==='passed')?(comps.length?'workflow_completed_pending_independent_review':'workflow_completed_with_missing_relative_valuation'):'workflow_checks_failed';
 report.acceptance_status='pending_independent_fact_and_calculation_review';
}catch(error){report.status='failed';report.error=error.message;report.failures.push({at:new Date().toISOString(),message:error.message});if(activeRun){try{await api('/api/runs/'+activeRun+'/cancel',{});report.observer_cancelled={run_id:activeRun,reason:'Runner error; prevent unobserved continuation. Not a user cancellation.'};}catch(cancel){report.cancellation_error=cancel.message;}}}
finally{
 if(before.continuation){
  report.cumulative_accounting=await reconcileContinuationAccounting({before,report,api,audit});
 }
 report.finished_at=new Date().toISOString();await save();console.log('REPORT',output,report.status);if(['failed','workflow_checks_failed'].includes(report.status))process.exitCode=1;
}
