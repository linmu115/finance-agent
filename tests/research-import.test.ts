import {test} from 'node:test';
import assert from 'node:assert/strict';
import {mkdtemp,rm} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import path from 'node:path';
import {createHash} from 'node:crypto';
import {ArtifactStore,ResearchWorkspace,ARTIFACT_TOOLS,reportSchema} from '../server/research-artifacts.js';
import {ResearchStore} from '../server/research.js';

const spec=(revenue='120')=>({currency:'CNY',amount_scale:'1',base_year:2024,base:{revenue:'100'},forecast:[{year:2025,revenue,ebit:'12'}],discount:{wacc:'0.1'},source_refs:{'base.revenue':[{kind:'document',id:'d1',locator:'page:1'}]},input_basis:{'forecast.0.revenue':{basis:'derived',rationale:'由上游情景假设计算，非披露预测事实'}},scenario_assumptions:{pass_through_rate:'0.5',lag_years:1}});
const result=(revenue='120')=>({results:{baseline_dcf_spec:spec('125'),scenario_dcf_spec:spec(revenue)},tables:{scenario:[{scenario_ebit:'12'}]}});
const memo=(evidence:any[])=>({company:'Synthetic only',as_of:'2024-12-31',thesis:'Conditional thesis',claims:[{id:'claim1',type:'calculation',text:'A saved calculation',evidence}],catalysts:[],risks:['Assumptions may change'],falsification_conditions:[{indicator:'margin',condition:'below assumption',horizon:'next year',action:'recompute'}],conclusion:'Verify assumptions'});

async function fixture(run:(v:any)=>Promise<void>){
 const directory=await mkdtemp(path.join(tmpdir(),'research-import-'));
 try{
  const artifacts=new ArtifactStore(directory),sources=new ResearchStore(directory),calls:any[]=[];
  const state={documentVersion:'doc_v1',onEvaluate:null as null|((args:any)=>Promise<void>)};
  const service:any={call:async(name:string,args:any)=>{
   calls.push({name,args:structuredClone(args)});
   if(name==='get_research_document_version')return {status:'ok',data:{version:state.documentVersion}};
   if(name==='evaluate_research_model'){if(state.onEvaluate)await state.onEvaluate(args);return {status:'ok',data:{input_assumptions:structuredClone(args.spec),results:{equity_value:'120'},tables:{}}};}
   if(name==='get_source_page')return {status:'ok',data:{text:'Synthetic page 120'}};
   throw new Error('Unexpected service method '+name);
  }};
  const workspace=new ResearchWorkspace(service,artifacts,sources);
  const scenario=await artifacts.save('p',{kind:'manufacturing_scenario',title:'Scenario',dependencies:[{kind:'document',id:'d1',version:'doc_v1'}],result:result()});
  await run({artifacts,sources,calls,state,workspace,scenario,service});
 }finally{
  const resolved=path.resolve(directory);assert.equal(path.dirname(resolved),path.resolve(tmpdir()));
  await rm(resolved,{recursive:true,force:true});
 }
}

test('scenario import copies every input and provenance field, pins historic revision and inherited evidence',async()=>fixture(async({artifacts,workspace,scenario,calls,state}:any)=>{
 const next=await artifacts.save('p',{...scenario,parent_revision_id:scenario.revision_id,result:result('130')},scenario.id);
 state.documentVersion='doc_v2';
 const imported=await workspace.model('p',{title:'DCF from historical scenario',kind:'dcf',source_model:{artifact_id:scenario.id,revision_id:scenario.revision_id,variant:'scenario'},dependencies:[{kind:'document',id:'d1'},{kind:'artifact',id:scenario.id}]},'pi-run');
 assert.deepEqual(imported.spec,scenario.result.results.scenario_dcf_spec);
 assert.deepEqual(calls.find((c:any)=>c.name==='evaluate_research_model').args.spec,imported.spec);
 assert.deepEqual(imported.dependencies,[{kind:'artifact',id:scenario.id,version:scenario.revision_id},{kind:'document',id:'d1',version:'doc_v1'}]);
 assert.deepEqual(imported.source_model,{artifact_id:scenario.id,revision_id:scenario.revision_id,variant:'scenario',spec_sha256:createHash('sha256').update(JSON.stringify(imported.spec)).digest('hex')});
 assert.equal(imported.run_id,'pi-run');assert.equal(imported.dependency_status,'stale');
 assert.equal(imported.changed_dependencies.find((d:any)=>d.id===scenario.id).current_version,next.revision_id);
 assert.equal(imported.changed_dependencies.find((d:any)=>d.id==='d1').current_version,'doc_v2');
 imported.spec.input_basis['forecast.0.revenue'].rationale='edited object';
 assert.deepEqual((await artifacts.get('p',scenario.id,scenario.revision_id)).result,scenario.result);
}));

test('omitted import revision fixes the version actually read even when source changes during evaluation',async()=>fixture(async({artifacts,workspace,scenario,state}:any)=>{
 state.onEvaluate=async()=>{await artifacts.save('p',{...scenario,parent_revision_id:scenario.revision_id,result:result('140')},scenario.id);};
 const imported=await workspace.model('p',{title:'Snapshot import',kind:'dcf',source_model:{artifact_id:scenario.id,variant:'scenario'}});
 assert.equal(imported.spec.forecast[0].revenue,'120');assert.equal(imported.source_model.revision_id,scenario.revision_id);
 assert.equal(imported.dependencies.find((d:any)=>d.kind==='artifact').version,scenario.revision_id);
 assert.equal(imported.dependency_status,'stale');
}));

test('baseline selection resolves only its saved DCF spec',async()=>fixture(async({workspace,scenario}:any)=>{
 const imported=await workspace.model('p',{title:'Baseline DCF',kind:'dcf',source_model:{artifact_id:scenario.id,variant:'baseline'}});
 assert.deepEqual(imported.spec,scenario.result.results.baseline_dcf_spec);assert.equal(imported.spec.forecast[0].revenue,'125');
 assert.equal(imported.dependency_status,'current');
}));

test('source import preserves the original web snapshot hash after the URL changes',async()=>fixture(async({artifacts,workspace,scenario,sources}:any)=>{
 const download=(body:string)=>async()=>({body:Buffer.from(body),url:'https://example.com/disclosure',contentType:'text/plain',headers:{}});
 const old=await sources.saveSnapshot('p','https://example.com/disclosure',{download:download('Old statement')});
 const linkedSpec={...spec(),source_refs:{base:[{kind:'source',id:old.source_id,locator:'p1'}]}};
 const linked=await artifacts.save('p',{...scenario,parent_revision_id:scenario.revision_id,dependencies:[{kind:'source',id:old.source_id,version:old.sha256}],result:{results:{scenario_dcf_spec:linkedSpec}}},scenario.id);
 const newer=await sources.saveSnapshot('p','https://example.com/disclosure',{download:download('New statement')});
 assert.notEqual(old.sha256,newer.sha256);
 const imported=await workspace.model('p',{title:'Historical source retained',kind:'dcf',source_model:{artifact_id:linked.id,variant:'scenario'}});
 assert.equal(imported.dependencies.find((d:any)=>d.kind==='source').version,old.sha256);
 assert.equal(imported.dependency_status,'stale');
 assert.equal((await sources.get('p',old.source_id)).paragraphs[0].text,'Old statement');
}));

test('model import refuses missing selector, ambiguous inputs, wrong kind and unavailable saved spec before evaluation',async()=>fixture(async({workspace,artifacts,scenario,calls}:any)=>{
 const source_model={artifact_id:scenario.id,variant:'scenario'};
 for(const input of [
  {title:'a',kind:'dcf'},
  {title:'a',kind:'dcf',spec:{},source_model},
  {title:'a',kind:'dcf',source_model:{artifact_id:scenario.id}},
  {title:'a',kind:'dcf',source_model:{...source_model,variant:'arbitrary.path'}},
  {title:'a',kind:'comparables',source_model},
  {title:'a',kind:'dcf',source_model:{...source_model,revision_id:'missing_revision'}},
 ])await assert.rejects(()=>workspace.model('p',input));
 await assert.rejects(()=>workspace.model('other-project',{title:'a',kind:'dcf',source_model}));
 const notScenario=await artifacts.save('p',{kind:'dcf',title:'Wrong source',dependencies:[],result:result()});
 await assert.rejects(()=>workspace.model('p',{title:'a',kind:'dcf',source_model:{artifact_id:notScenario.id,variant:'scenario'}}),/制造业情景/);
 const empty=await artifacts.save('p',{kind:'manufacturing_scenario',title:'Missing output',dependencies:[],result:{}});
 await assert.rejects(()=>workspace.model('p',{title:'a',kind:'dcf',source_model:{artifact_id:empty.id,variant:'scenario'}}),/未保存可导入/);
 assert.equal(calls.filter((c:any)=>c.name==='evaluate_research_model').length,0);
}));

test('conflicting inherited fixed versions and self import are rejected without silent upgrade',async()=>fixture(async({workspace,artifacts,scenario,calls}:any)=>{
 const bad=await artifacts.save('p',{...scenario,parent_revision_id:scenario.revision_id,dependencies:[{kind:'document',id:'d1',version:'v1'},{kind:'document',id:'d1',version:'v2'}]},scenario.id);
 await assert.rejects(()=>workspace.model('p',{title:'Conflicted',kind:'dcf',source_model:{artifact_id:bad.id,variant:'scenario'}}),/固定版本冲突/);
 await assert.rejects(()=>workspace.model('p',{title:'Self',kind:'dcf',source_model:{artifact_id:scenario.id,revision_id:scenario.revision_id,variant:'scenario'},artifact_id:scenario.id,parent_revision_id:bad.revision_id}),/不能依赖自身/);
 assert.equal(calls.filter((c:any)=>c.name==='evaluate_research_model').length,0);
}));

test('historical report evidence checks and records the requested artifact revision',async()=>fixture(async({artifacts,workspace,scenario}:any)=>{
 await artifacts.save('p',{...scenario,parent_revision_id:scenario.revision_id,result:result('130')},scenario.id);
 const evidence={kind:'artifact',id:scenario.id,revision_id:scenario.revision_id,locator:'results.scenario_dcf_spec.forecast[0].revenue',quote:'120'};
 const saved=await workspace.report('p',{title:'Historical report',kind:'investment_memo',content:{...memo([evidence]),valuation_artifact_id:scenario.id},dependencies:[{kind:'artifact',id:scenario.id}]});
 assert.equal(saved.dependencies[0].version,scenario.revision_id);assert.equal(saved.content.claims[0].evidence[0].revision_id,scenario.revision_id);
 assert.equal(saved.dependency_status,'stale');
 await assert.rejects(()=>workspace.report('p',{title:'Wrong quote',kind:'investment_memo',content:memo([{...evidence,quote:'130'}])}),/引用文字未在/);
}));

test('report omitting revision pins first actual read and reuses it across all citations despite concurrent edit',async()=>fixture(async({artifacts,workspace,scenario}:any)=>{
 const originalGet=artifacts.get.bind(artifacts);let injected=false;
 artifacts.get=async(project:string,id:string,revision?:string)=>{
  const selected=await originalGet(project,id,revision);
  if(!injected&&id===scenario.id&&!revision){injected=true;await artifacts.save('p',{...scenario,parent_revision_id:scenario.revision_id,result:result('130')},scenario.id);}
  return selected;
 };
 const evidence=[{kind:'artifact',id:scenario.id,locator:'results.scenario_dcf_spec.forecast[0].revenue',quote:'120'},{kind:'artifact',id:scenario.id,locator:'tables.scenario[0].scenario_ebit',quote:'12'}];
 const saved=await workspace.report('p',{title:'Pin on first read',kind:'investment_memo',content:memo(evidence)});
 assert.equal(saved.dependencies[0].version,scenario.revision_id);
 assert.ok(saved.content.claims[0].evidence.every((e:any)=>e.revision_id===scenario.revision_id));
 assert.equal(evidence[0].revision_id,undefined);
 assert.equal(saved.dependency_status,'stale');
}));

test('report rejects wrong project or artifact revision and contradictory fixed revisions',async()=>fixture(async({artifacts,workspace,scenario}:any)=>{
 const newer=await artifacts.save('p',{...scenario,parent_revision_id:scenario.revision_id,result:result('130')},scenario.id);
 const e={kind:'artifact',id:scenario.id,revision_id:scenario.revision_id,locator:'results.scenario_dcf_spec.forecast[0].revenue',quote:'120'};
 await assert.rejects(()=>workspace.report('other-project',{title:'x',kind:'investment_memo',content:memo([e])}));
 await assert.rejects(()=>workspace.report('p',{title:'x',kind:'investment_memo',content:memo([{...e,revision_id:'not-found'}])}));
 await assert.rejects(()=>workspace.report('p',{title:'x',kind:'investment_memo',content:memo([e,{...e,revision_id:newer.revision_id,quote:'130'}])}),/固定版本冲突/);
 await assert.rejects(()=>workspace.report('p',{title:'x',kind:'investment_memo',content:memo([{kind:'document',id:'d1',revision_id:'r1',locator:'page:1'}])}),/revision_id/);
}));

test('public schema shows exact import selectors, one-of input and practical citation paths',()=>{
 const model=ARTIFACT_TOOLS.find(t=>t.name==='run_financial_model')!;
 assert.deepEqual((model.inputSchema as any).properties.source_model.required,['artifact_id','variant']);
 assert.equal((model.inputSchema as any).oneOf.length,2);
 const report=JSON.stringify(reportSchema('investment_memo'));
 assert.match(report,/revision_id/);assert.match(report,/tables\.scenario\[0\]\.scenario_ebit/);
 assert.match(report,/逐字原文/);
});
