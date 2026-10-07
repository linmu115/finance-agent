import {test} from 'node:test';
import assert from 'node:assert/strict';
import {mkdtemp,rm,mkdir,writeFile} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import path from 'node:path';
import {ArtifactStore,ResearchWorkspace,applyCorrections,artifactCsv,reportSchema,artifactField} from '../server/research-artifacts.js';
import {ResearchStore} from '../server/research.js';
import {setTimeout as delay} from 'node:timers/promises';

test('record bindings persist into model reuse; overrides become assumptions and keep prior revision immutable',async()=>{
 const dir=await mkdtemp(path.join(tmpdir(),'research-bound-model-'));try{
 const calls:{name:string;args:any}[]=[];
 const svc:any={call:async(name:string,args:any)=>{
  calls.push({name,args:structuredClone(args)});
  let data:any={version:'v1',text:'披露营业收入120百万元'};
  if(name==='deliver_research_models')data={delivery_id:'0'.repeat(32),attachments:[],results:{}};
  if(name==='apply_model_overrides')data={values:{'base.revenue':'108'}};
  if(name==='resolve_model_inputs'){
   const spec=structuredClone(args.spec);spec.base.revenue='120';
   spec.source_refs={'base.revenue':[{kind:'document',id:'doc1',locator:'page:1'}]};
   spec.input_basis={'base.revenue':{basis:'disclosed',source_kind:'disclosed_actual'}};
   data={spec,bindings:[{path:'base.revenue',record_id:'f1',record_type:'fact',value:'120',scale:'1000000'}]};
  }else if(name==='evaluate_research_model')data={tables:{},results:{value_per_share:args.spec.forecast[0].capex_ratio}};
  else if(name==='compare_research_models')data={changed_inputs:[{path:'forecast.0.capex_ratio',before:args.baseline.forecast[0].capex_ratio,after:args.scenario.forecast[0].capex_ratio}]};
  return {status:'ok',data};
 }};
 const store=new ArtifactStore(dir),ws=new ResearchWorkspace(svc,store);
 const original=await ws.model('p',{kind:'dcf',title:'基准',spec:{currency:'CNY',base:{revenue:'0'},forecast:[{capex_ratio:'0.05'}]},bindings:{'base.revenue':{fact_id:'f1',scale:'1000000'}}});
 assert.equal(original.spec.base.revenue,'120');assert.equal(original.input_bindings[0].record_id,'f1');
 assert.equal(calls.find(c=>c.name==='resolve_model_inputs')!.args.project_id,'p');
 const direct=await ws.model('p',{kind:'dcf',title:'直接输入记录',spec:{currency:'CNY',base:{revenue:{fact_id:'f1',scale:'1000000'}},forecast:[{capex_ratio:'0.05'}]}});
 assert.equal(direct.spec.base.revenue,'120');assert.equal(direct.input_bindings[0].record_id,'f1');
 assert.deepEqual(calls.filter(c=>c.name==='resolve_model_inputs').at(-1)!.args.bindings,{'base.revenue':{fact_id:'f1',scale:'1000000'}});
 await assert.rejects(()=>ws.model('p',{kind:'dcf',title:'冲突',spec:{base:{revenue:{fact_id:'f1'}}},bindings:{'base.revenue':{fact_id:'f2'}}}),/同一输入指定了不同记录/);
 const changed=await ws.model('p',{kind:'dcf',title:'情景',artifact_id:original.id,source_model:{artifact_id:original.id,revision_id:original.revision_id},overrides:{'forecast.0.capex_ratio':'0.08'}});
 assert.equal(changed.parent_revision_id,original.revision_id);
 assert.equal(changed.spec.input_basis['forecast.0.capex_ratio'].basis,'assumption');
 assert.equal(changed.input_bindings[0].record_id,'f1');
 assert.equal((await store.get('p',original.id,original.revision_id)).spec.forecast[0].capex_ratio,'0.05');
 const compare=await ws.compare('p',{baseline:{artifact_id:original.id,revision_id:original.revision_id},scenario:{artifact_id:changed.id,revision_id:changed.revision_id}});
 assert.deepEqual(compare.changed_inputs,[{path:'forecast.0.capex_ratio',before:'0.05',after:'0.08'}]);
 const replacement=await ws.model('p',{kind:'dcf',title:'收入假设',source_model:{artifact_id:original.id,revision_id:original.revision_id},overrides:{'base.revenue':'150'}});
 assert.equal(replacement.input_bindings?.length||0,0);
 assert.equal(replacement.spec.source_refs['base.revenue'],undefined);
 assert.equal(replacement.spec.input_basis['base.revenue'].basis,'assumption');
 const operated=await ws.model('p',{kind:'dcf',title:'来源数值的比例假设',source_model:{artifact_id:original.id,revision_id:original.revision_id},overrides:{'base.revenue':{'*':'.9'}}});
 assert.equal(operated.spec.base.revenue,'108');assert.equal(operated.input_bindings[0].value,'108');
 assert.equal(operated.input_bindings[0].source_input_value,'120');assert.equal(operated.input_bindings[0].record_id,'f1');
 assert.equal(operated.input_bindings[0].modeled_basis,'assumption');assert.ok(operated.spec.source_refs['base.revenue']);
 }finally{await rm(dir,{recursive:true,force:true});}
});

test('report corrections apply exact offsets and preserve truthful unmodified content',()=>{
 const original='收入为100万元。现金流改善属于分析判断。';
 const result=applyCorrections({original_text:original,issues:[{id:'i1',start:3,end:6,original:'100',replacement:'120',category:'number',reason:'原表披露120',evidence:[{kind:'document',id:'d',locator:'page:1'}]}],verified_claims:[]});
 assert.equal(result.revised_text,'收入为120万元。现金流改善属于分析判断。');
 assert.throws(()=>applyCorrections({...result,issues:[{...result.issues[0],start:2}]}));
 assert.throws(()=>applyCorrections({...result,issues:[result.issues[0],{...result.issues[0],id:'i2'}]}));
 for(const kind of ['industry_chain','investment_memo','report_correction'])assert.equal((reportSchema(kind) as any).type,'object');
});

test('revision compare-and-swap accepts one concurrent edit and retains original',async()=>{
 const dir=await mkdtemp(path.join(tmpdir(),'research-artifact-'));try{
 const store=new ArtifactStore(dir);const a=await store.save('p',{kind:'dcf',title:'模型',dependencies:[],spec:{wacc:'0.1'}});
 const edits=await Promise.allSettled([store.save('p',{...a,title:'修改一',parent_revision_id:a.revision_id},a.id),store.save('p',{...a,title:'修改二',parent_revision_id:a.revision_id},a.id)]);
 assert.equal(edits.filter(x=>x.status==='fulfilled').length,1);assert.equal(edits.filter(x=>x.status==='rejected').length,1);
 assert.equal((await store.get('p',a.id,a.revision_id)).title,'模型');assert.equal((await store.list('p')).length,1);
 await assert.rejects(()=>store.get('another',a.id));
 }finally{await rm(dir,{recursive:true,force:true});}
});

test('changed document invalidates only downstream artifacts, recompute creates auditable version',async()=>{
 const dir=await mkdtemp(path.join(tmpdir(),'research-update-'));try{
 const store=new ArtifactStore(dir);let version='v1';
 const svc:any={call:async(name:string,args:any)=>({status:'ok',data:name==='deliver_research_models'?{delivery_id:'0'.repeat(32),attachments:[],results:{}}:name==='get_research_document_version'?{version}:name==='evaluate_research_model'?{tables:{forecast:[{year:2026,revenue:'123.456'}]},results:{equity_value:'200'}}:{text:'原始披露'}})};
 const ws=new ResearchWorkspace(svc,store);
 const model=await ws.model('p',{title:'基准估值',kind:'dcf',spec:{},dependencies:[{kind:'document',id:'doc1'}]},'run1');
 const independent=await ws.model('p',{title:'无关模型',kind:'dcf',spec:{},dependencies:[]});
 const memo=await ws.report('p',{title:'备忘录',kind:'investment_memo',content:{company:'案例',as_of:'2026-01-01',thesis:'判断',claims:[{id:'c1',type:'inference',text:'需要观察',evidence:[]}],catalysts:[],risks:['利润率下跌'],falsification_conditions:[{indicator:'利润率',condition:'低于10%',horizon:'下一财年',action:'重估'}],valuation_artifact_id:model.id,conclusion:'持续验证'}});
 assert.equal(model.dependency_status,'current');version='v2';
 assert.equal((await ws.get('p',model.id)).dependency_status,'stale');assert.equal((await ws.get('p',memo.id)).changed_dependencies[0].reason,'upstream_stale');assert.equal((await ws.get('p',independent.id)).dependency_status,'current');
 const recomputed=await ws.model('p',{title:model.title,kind:'dcf',spec:{},artifact_id:model.id,parent_revision_id:model.revision_id,dependencies:[{kind:'document',id:'doc1'}]});assert.equal(recomputed.dependency_status,'current');assert.notEqual(recomputed.revision_id,model.revision_id);assert.equal((await ws.get('p',memo.id)).dependency_status,'stale');
 assert.match(artifactCsv(recomputed,'forecast'),/123.456/);
 }finally{await rm(dir,{recursive:true,force:true});}
});

test('claims and source quotes cannot cite nonmatching original text',async()=>{
 const dir=await mkdtemp(path.join(tmpdir(),'research-citations-'));try{
 const svc:any={call:async()=>({status:'ok',data:{text:'营业收入为120万元',version:'v1'}})},ws=new ResearchWorkspace(svc,new ArtifactStore(dir));
 await assert.rejects(()=>ws.report('p',{title:'纠错',kind:'report_correction',content:{original_text:'100',issues:[{id:'x',start:0,end:3,original:'100',replacement:'120',category:'number',reason:'原文',evidence:[{kind:'document',id:'d',locator:'page:1',quote:'营业收入为999万元'}]}]}}),/引用文字未在/);
 }finally{await rm(dir,{recursive:true,force:true});}
});
test('latest revision follows ancestry even with equal timestamps and adversarial enumeration',async()=>{
 const dir=await mkdtemp(path.join(tmpdir(),'research-chain-'));try{
 const folder=path.join(dir,'p','artifacts');await mkdir(folder,{recursive:true});
 const a={id:'a',revision_id:'r1',created_at:'2026-01-01',kind:'dcf',title:'first',dependencies:[]};
 for(const [filename,value] of [['1.json',a],['2.json',{...a,revision_id:'r3',parent_revision_id:'r2',title:'third'}],['3.json',{...a,revision_id:'r2',parent_revision_id:'r1',title:'second'}]] as const)await writeFile(path.join(folder,filename),JSON.stringify(value));
 assert.equal((await new ArtifactStore(dir).get('p','a')).revision_id,'r3');
 }finally{await rm(dir,{recursive:true,force:true});}
});
test('artifact quote locator resolves exact existing value rather than arbitrary entire result',()=>{
 const a:any={result:{results:{equity_value:'120'},tables:{forecast:[{revenue:'100'}]}}};
 assert.equal(artifactField(a,'results.equity_value'),'120');assert.equal(artifactField(a,'$.result.tables.forecast[0].revenue'),'100');
 assert.throws(()=>artifactField(a,'results.not_present'));assert.throws(()=>artifactField(a,'result.__proto__.constructor'));
});
test('model source_refs become dependencies and changed URL content marks old evidence stale',async()=>{
 const dir=await mkdtemp(path.join(tmpdir(),'research-web-update-'));try{
 const sources=new ResearchStore(dir),store=new ArtifactStore(dir),svc:any={call:async(name:string)=>({status:'ok',data:name==='deliver_research_models'?{delivery_id:'0'.repeat(32),attachments:[],results:{}}:name==='get_research_document_version'?{version:'doc1'}:{tables:{},results:{}}})},ws=new ResearchWorkspace(svc,store,sources);
 const fetchText=(text:string)=>async()=>({body:Buffer.from(text),url:'https://example.com/announcement',contentType:'text/plain',headers:{}});
 const old=await sources.saveSnapshot('p','https://example.com/announcement',{download:fetchText('收入120万元')});
 const model=await ws.model('p',{title:'source linked',kind:'dcf',spec:{source_refs:{base:[{source_id:old.source_id,document_id:'d'}]}}});
 assert.deepEqual(model.dependencies.map((x:any)=>x.kind).sort(),['document','source']);assert.equal(model.dependency_status,'current');
 await delay(3);await sources.saveSnapshot('p','https://example.com/announcement',{download:fetchText('收入130万元')});
 const changed=await ws.get('p',model.id);assert.equal(changed.dependency_status,'stale');assert.equal(changed.changed_dependencies[0].id,old.source_id);
 assert.equal((await sources.read('p',old.source_id)).paragraphs[0].text,'收入120万元');
 }finally{await rm(dir,{recursive:true,force:true});}
});
