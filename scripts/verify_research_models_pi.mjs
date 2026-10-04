/** Real Pi development workflow with synthetic assumptions. Not an accuracy holdout.
 * --prepare freezes tasks without network/model calls; --run executes that frozen task once.
 */
import fs from 'node:fs/promises';
import path from 'node:path';
import {setTimeout as delay} from 'node:timers/promises';
import {researchHash as hash,researchWorkflowIO} from './research_workflow_io.mjs';

const root=path.resolve(import.meta.dirname,'..'),args=process.argv.slice(2);
const arg=(name,fallback)=>args.includes(name)?args[args.indexOf(name)+1]:fallback;
const version=arg('--version','v05');if(!['v05','v06'].includes(version))throw Error('Supported versions: v05, v06');
const v06=version==='v06';
const base=arg('--base-url','http://127.0.0.1:3001');
const prefix=path.resolve(root,arg('--prefix','benchmark/results/research-models-pi-workflow-'+version));
const budget={max_model_calls:40,max_input_tokens:2000000,max_output_tokens:300000,max_total_tokens:2300000,max_wall_seconds:1200};
const assumptions={currency:'CNY',amount_scale:'1',base_year:2024,base:{revenue:'1000',net_working_capital:'100'},volume_unit:'件',
 baseline:[{year:2025,volume:'100',fixed_cash_opex:'100',da:'50',capex:'50'},{year:2026,volume:'110',fixed_cash_opex:'110',da:'55',capex:'55'},{year:2027,volume:'121',fixed_cash_opex:'121',da:'60.5',capex:'60.5'}].map(row=>({...row,unit_price:'10',material_cost_per_unit:'4',other_variable_cost_per_unit:'2',nwc_ratio:'0.1',tax_rate:'0.25'})),
 scenario:{exposed_material_share:'0.5',pass_through_rate:'0.5',lag_years:1,price_elasticity:'-1',material_cost_changes:['0.2','0.2','0.2'],volume_changes:['0','0','0'],autonomous_price_changes:['0','0','0']},
 dcf:{cash_tax_policy:'floor_at_zero',discount:{wacc:'0.1',cashflow_timing:'year_end'},terminal:{growth:'0.02',roic:'0.2',ebit_margin:'0.25',tax_rate:'0.25'},bridge:{net_debt:'200',non_controlling_interest:'20',preferred_equity:'10',non_operating_assets_ex_cash:'30'},shares:{count:'100',scale:'1'},sensitivity:{wacc:['0.08','0.1','0.12'],growth:['0','0.02','0.03']}}};
const task1=`这是研究工具的开发联调，独立合成公司“合成制造公司 WF-01”，不是真实公司精度测试。请在当前项目完成并保存以下四项可读取的成果：制造业原料成本/提价/销量/一年传导时滞情景；依据情景工具返回的 scenario_dcf_spec 保存一份独立 DCF；上游原料→制造企业→客户的产业链；投资备忘录。请先通过现有工具核对输入结构后运行，不只在回复里计算。
所有经济数值均为我明确给出的分析假设，绝不是实际披露数据；不联网、不搜索、不读取任何其他项目或本地基准材料，不补造敞口或弹性。报告分析时点为2024年12月31日；股数与金额倍率独立声明，0.1是10%。冲击数组是各年相对当年基线的水平变化，非累计增幅。
独立 DCF 明确依赖已保存情景成果。产业链明确依赖情景，备忘录明确依赖情景和独立 DCF；可定位计算主张引用成果中的具体字段，经济输入标为假设。备忘录要写主要判断、风险及可证伪指标/条件/观察期限，不给真实证券投资建议。产业链中的参数只取给定假设。模型结果保留在研究成果区，不需要生成其他文件。
完整输入假设：${JSON.stringify(assumptions)}
完成后简短列出四项成果ID、情景和独立DCF的每股价值、关键风险。如发生工具错误，保留真实失败说明；同参数失败不要反复重试。`;
const task2=`这是独立会话读取已保存研究成果的开发联调，不是精度留出测试。请使用工具列出并读取当前项目的研究成果，核对它们的依赖和版本状态。上一个会话已完成合成制造公司 WF-01 的情景、独立DCF、产业链和投资备忘录；随后宿主通过产品模型编辑接口只把情景 WACC 从0.10改为0.11，保存为新版本。
请实际读取后说明：哪个成果是新版本，哪些下游成果已经 stale，分别是哪条依赖变化导致；区分仍可查看的历史结果与基于新参数的最新计算。不要重新计算或保存，不要搜索，不要把宿主的这段说明当读取结果。简短引用实际成果ID和读取到的 changed_dependencies，不要为通过测试猜状态。`;
const scoringContract={version:'v06',changes_from_v05:[
 'Require actual source_model scenario import with the selected immutable artifact revision; all spec metadata must be preserved exactly.',
 'Dependency-state evidence may come from list_research_artifacts OR read_research_artifact. Reading every full artifact is not required when the list already provides the same actual state and changed_dependencies.',
 'The v05 failed report and its original read-every-artifact check are retained unchanged; scores across versions are not directly identical contracts.'
],unchanged:['Synthetic company and all economic assumptions','Same shared 40-call / 2M-input / 300k-output / 20-minute budget','Same two independent conversations and WACC edit','No accuracy-holdout claim']};
const frozen={kind:'development_research_models_workflow',accuracy_holdout:false,prepared_at:new Date().toISOString(),budget,assumptions,tasks:[task1+(v06?'\n本轮使用现有 source_model 导入接口保存独立DCF：kind=dcf，source_model 指向已保存情景的 artifact_id 和实际 revision_id，variant=scenario，不同时提供spec。让宿主完整继承所有参数依据和固定来源版本，勿手抄或改写上游spec。':''),task2],host_parameter_edit:{artifact_kind:'manufacturing_scenario',path:'dcf.discount.wacc',before:'0.1',after:'0.11'},restrictions:['No holdout or real-company material','No search or model settings mutation','No automatic retry after terminal failure','All economic parameters are synthetic assumptions'],...(v06?{scoring_contract:scoringContract}: {})};
const taskPayload=value=>({budget:value.budget,assumptions:value.assumptions,tasks:value.tasks,host_parameter_edit:value.host_parameter_edit,...(value.scoring_contract?{scoring_contract:value.scoring_contract}:{})});
frozen.task_sha256=hash(taskPayload(frozen));
await fs.mkdir(path.dirname(prefix),{recursive:true});
if(args.includes('--prepare')){await fs.writeFile(prefix+'.before.json',JSON.stringify(frozen,null,2),{flag:'wx'});console.log('FROZEN',prefix+'.before.json',frozen.task_sha256);process.exit(0);}
if(!args.includes('--run'))throw Error('Use --prepare (no calls) or --run (one frozen workflow)');
const before=JSON.parse(await fs.readFile(prefix+'.before.json','utf8'));
if(before.task_sha256!==hash(taskPayload(before)))throw Error('Frozen task integrity mismatch');
if(v06!==(before.scoring_contract?.version==='v06'))throw Error('Frozen task and selected scoring version differ');
const output=prefix+'.json';
await fs.writeFile(output,JSON.stringify({status:'starting'}),{flag:'wx'});
const report={kind:before.kind,accuracy_holdout:false,limitations:['Synthetic development workflow only; not an independent financial-accuracy holdout.','Input token budget is an observed-usage soft cap as declared by the runtime; output and call reservations use runtime enforcement.'],...(before.scoring_contract?{scoring_contract:before.scoring_contract}:{}),task_sha256:before.task_sha256,started_at:new Date().toISOString(),status:'running',checks:[],runs:[],failures:[],budget_group_id:'research-models-'+Date.now()};
let activeRun;
const save=()=>fs.writeFile(output,JSON.stringify(report,null,2));
const check=(name,ok,evidence)=>{report.checks.push({name,status:ok?'passed':'failed',evidence});console.log(ok?'PASS':'FAIL',name);};
const {api,implementationHashes,audit}=researchWorkflowIO(root,base);
async function wait(runId){let last=0;const deadline=Date.now()+21*60000;while(Date.now()<deadline){const run=await api('/api/runs/'+runId);report.runs=report.runs.filter(value=>value.id!==runId).concat(run);if(['completed','failed','cancelled'].includes(run.status)){activeRun=undefined;await save();return run;}if(Date.now()-last>15000){console.log(run.status,run.stage,JSON.stringify(run.usage));await save();last=Date.now();}await delay(1500);}await api('/api/runs/'+runId+'/cancel',{});activeRun=undefined;throw Error('Observer cancelled this run after 21 minutes; not a user cancellation');}
async function send(content,index){const conversation=await api('/api/projects/'+report.project_id+'/conversations',{});const started=await api('/api/conversations/'+conversation.id+'/messages',{content,documentIds:[],evaluation:{profile:'financial',budget_group_id:report.budget_group_id,budget:before.budget}});activeRun=started.runId;report['conversation_'+index]=conversation.id;report['run_'+index]=started.runId;await save();const run=await wait(started.runId),events=await audit(run.id);await fs.writeFile(prefix+`.run-${index}.audit.json`,JSON.stringify(events,null,2));report['audit_'+index]=path.basename(prefix+`.run-${index}.audit.json`);const chat=await api('/api/conversations/'+conversation.id);report['messages_'+index]=chat.messages.filter(message=>message.runId===run.id);const errors=events.filter(event=>event.type==='tool_error'||(event.type==='model_usage'&&['error','aborted','length'].includes(event.data?.stopReason)));report.failures.push(...errors.map(event=>({run_id:run.id,event})));return {run,events};}
async function artifacts(){const list=(await api('/api/projects/'+report.project_id+'/research/artifacts')).artifacts;return Promise.all(list.map(item=>api('/api/projects/'+report.project_id+'/research/artifacts/'+item.id)));}
const eventArgs=event=>event.data?.args||{};
try{
 report.implementation_before=await implementationHashes();await save();
 const project=await api('/api/projects',{name:'Pi研究工具开发联调 · 合成制造 WF-01'});report.project_id=project.id;await save();
 const first=await send(before.tasks[0],1),names=first.events.filter(event=>event.type==='tool_result').map(event=>event.data.name);
 check('Pi自主读取模型结构并调用模型和报告保存工具',first.run.status==='completed'&&['get_research_model_schema','run_financial_model','get_research_report_schema','save_research_report'].every(name=>names.includes(name)),{run_id:first.run.id,status:first.run.status,tools:names,usage:first.run.usage});
 if(first.run.status!=='completed')throw Error('First Pi run did not complete; no automatic retry or second run');
 report.artifacts_before=await artifacts();const byKind=kind=>report.artifacts_before.filter(item=>item.kind===kind);
 check('四类成果均由本次真实Pi运行保存', ['manufacturing_scenario','dcf','industry_chain','investment_memo'].every(kind=>byKind(kind).length===1&&byKind(kind)[0].run_id===first.run.id),report.artifacts_before.map(({id,kind,run_id,revision_id})=>({id,kind,run_id,revision_id})));
 if(['manufacturing_scenario','dcf','industry_chain','investment_memo'].some(kind=>byKind(kind).length!==1))throw Error('Expected exactly one artifact of each required kind');
 const [scenario,dcf,chain,memo]=['manufacturing_scenario','dcf','industry_chain','investment_memo'].map(kind=>byKind(kind)[0]);
 const depends=(artifact,id)=>artifact.dependencies.some(dependency=>dependency.kind==='artifact'&&dependency.id===id);
 check('产业链和备忘录保存实际依赖而非只写文字',depends(dcf,scenario.id)&&depends(chain,scenario.id)&&depends(memo,scenario.id)&&depends(memo,dcf.id),{scenario:scenario.id,dcf:dcf.dependencies,chain:chain.dependencies,memo:memo.dependencies});
 function equivalent(a,b){if(a&&b&&typeof a==='object'&&typeof b==='object')return Object.keys(b).every(key=>key in a&&equivalent(a[key],b[key]));return typeof a==='number'||typeof b==='number'||(typeof a==='string'&&typeof b==='string'&&a.trim()!==''&&b.trim()!==''&&Number.isFinite(Number(a))&&Number.isFinite(Number(b)))?Number(a)===Number(b):a===b;}
 check('已保存情景完整保留冻结的显式假设',equivalent(scenario.spec,before.assumptions),{saved_spec:scenario.spec,expected_sha256:hash(before.assumptions)});
 if(v06){
  const canonical=value=>Array.isArray(value)?value.map(canonical):value&&typeof value==='object'?Object.fromEntries(Object.keys(value).sort().map(key=>[key,canonical(value[key])])):value;
  const imports=first.events.filter(event=>event.type==='tool_request'&&event.data.name==='run_financial_model').map(eventArgs).filter(value=>value.kind==='dcf');
  check('独立DCF通过source_model精确继承情景输入及所选版本',imports.some(value=>value.source_model?.artifact_id===scenario.id&&value.source_model?.revision_id===scenario.revision_id&&value.source_model?.variant==='scenario'&&value.spec===undefined)&&dcf.source_model?.revision_id===scenario.revision_id&&dcf.source_model?.artifact_id===scenario.id&&dcf.source_model?.variant==='scenario'&&JSON.stringify(canonical(dcf.spec))===JSON.stringify(canonical(scenario.result.results.scenario_dcf_spec))&&dcf.dependencies.some(value=>value.kind==='artifact'&&value.id===scenario.id&&value.version===scenario.revision_id),{dcf_id:dcf.id,scenario_id:scenario.id,source_model:dcf.source_model,actual_requests:imports});
 }else check('独立DCF使用情景返回的可重算输入',equivalent(dcf.spec,scenario.result.results.scenario_dcf_spec),{dcf_id:dcf.id,scenario_id:scenario.id});
 const changedSpec=structuredClone(scenario.spec);changedSpec.dcf.discount.wacc=before.host_parameter_edit.after;
 report.host_edit=await api('/api/projects/'+project.id+'/research/models',{kind:scenario.kind,title:scenario.title,spec:changedSpec,dependencies:scenario.dependencies.map(({kind,id})=>({kind,id})),artifact_id:scenario.id,parent_revision_id:scenario.revision_id});
 report.artifacts_after=await artifacts();
 check('宿主只改WACC生成新版本且下游全部标过期',report.host_edit.revision_id!==scenario.revision_id&&report.artifacts_after.filter(item=>[dcf.id,chain.id,memo.id].includes(item.id)).every(item=>item.dependency_status==='stale'),report.artifacts_after.map(({id,kind,revision_id,dependency_status,changed_dependencies})=>({id,kind,revision_id,dependency_status,changed_dependencies})));
 await save();const second=await send(before.tasks[1],2),requests=second.events.filter(event=>event.type==='tool_request'),results=second.events.filter(event=>event.type==='tool_result');
 const readResults=results.filter(event=>event.data.name==='read_research_artifact').map(event=>event.data.result.data);
 if(v06){
  const listResults=results.filter(event=>event.data.name==='list_research_artifacts').flatMap(event=>event.data.result.data.artifacts||[]),actualEvidence=[...listResults,...readResults];
  const covered=report.artifacts_after.filter(item=>[scenario.id,dcf.id,chain.id,memo.id].includes(item.id)).every(item=>actualEvidence.some(seen=>seen.id===item.id&&seen.revision_id===item.revision_id&&seen.dependency_status===item.dependency_status&&JSON.stringify(seen.changed_dependencies)===JSON.stringify(item.changed_dependencies)));
  check('第二段独立Pi会话以真实list或read结果取得四项版本及过期依赖',second.run.status==='completed'&&report.conversation_1!==report.conversation_2&&covered,{run_id:second.run.id,status:second.run.status,accepted_evidence_tools:['list_research_artifacts','read_research_artifact'],observed:actualEvidence.map(({id,revision_id,dependency_status,changed_dependencies})=>({id,revision_id,dependency_status,changed_dependencies}))});
 }else check('第二段独立Pi会话实际读取所有旧成果状态',second.run.status==='completed'&&report.conversation_1!==report.conversation_2&&[scenario.id,dcf.id,chain.id,memo.id].every(id=>readResults.some(result=>result.id===id)),{run_id:second.run.id,status:second.run.status,reads:readResults.map(({id,dependency_status,changed_dependencies})=>({id,dependency_status,changed_dependencies}))});
 check('第二段会话保持只读且没有模型重算或搜索',!requests.some(event=>['run_financial_model','save_research_report','search_web','fetch_research_source'].includes(event.data.name)),requests.map(event=>({name:event.data.name,args:eventArgs(event)})));
 const answer=report.messages_2.filter(message=>message.role==='assistant').map(message=>message.content||'').join('\n');
 check('第二段模型回复说明过期依赖和新旧版本',/stale|过期|失效|需.*更新|待更新/i.test(answer)&&/依赖|上游/.test(answer)&&[dcf.id,chain.id,memo.id].every(id=>answer.includes(id)),{answer,requires_human_semantic_review:true});
 report.implementation_after=await implementationHashes();report.implementation_changed=Object.keys(report.implementation_before).filter(file=>report.implementation_before[file]!==report.implementation_after[file]);
 check('两会话使用同一显式财务预算组',report.runs.every(run=>run.evaluation?.profile==='financial'&&JSON.stringify(run.evaluation).includes(report.budget_group_id)),report.runs.map(run=>({id:run.id,evaluation:run.evaluation,usage:run.usage})));
 report.status=report.checks.every(item=>item.status==='passed')?'passed':'failed';
}catch(error){report.status='failed';report.error=error.message;report.failures.push({at:new Date().toISOString(),message:error.message});console.error('FAIL',error.message);if(activeRun){try{await api('/api/runs/'+activeRun+'/cancel',{});report.observer_cancelled={run_id:activeRun,reason:'Workflow script error; prevent unobserved continuation'};}catch(cancelError){report.cancellation_error=cancelError.message;}}}
finally{report.finished_at=new Date().toISOString();await save();console.log('REPORT',output);if(report.status!=='passed')process.exitCode=1;}
