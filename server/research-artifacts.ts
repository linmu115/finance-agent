import { mkdir, readFile, writeFile, readdir } from 'node:fs/promises';
import { createHash, randomUUID } from 'node:crypto';
import path from 'node:path';
import { z } from 'zod';
import { DATA } from './config.js';
import { researchStore, type ResearchStore } from './research.js';
import type { FinanceService } from './mcp.js';
import { publishFile } from './immutable-files.js';

const idSchema=z.string().regex(/^[A-Za-z0-9_-]{1,100}$/);
const dependencySchema=z.object({kind:z.enum(['source','document','artifact']),id:idSchema});
const evidenceSchema=z.object({kind:z.enum(['source','document','artifact']),id:idSchema,revision_id:idSchema.optional().describe('仅用于artifact，指定已保存版本；省略时固定该报告第一次读取此成果的版本。'),locator:z.string().min(1).max(400).describe('source使用p1或p1,p2段落ID；document使用page:物理页码；artifact例如tables.scenario[0].scenario_ebit、results.scenario_valuation.value_per_share、results.value_per_share，不能使用results.tables。'),quote:z.string().max(5000).optional().describe('可选：所选字段或段落的逐字原文，不填写自行概括的解释。')}).refine(v=>v.revision_id===undefined||v.kind==='artifact',{message:'revision_id仅适用于成果引用'});
export type Dependency=z.infer<typeof dependencySchema>;
export interface RecordedDependency extends Dependency {version:string}
const sourceModelSchema=z.object({artifact_id:idSchema,revision_id:idSchema.optional(),variant:z.enum(['baseline','scenario']).optional()}).strict();
export interface ImportedModel {artifact_id:string;revision_id:string;variant?:'baseline'|'scenario';spec_sha256:string}
export interface ReferenceCheck {path:string;status:'locator_exists'|'locator_and_quote_match'|'dependency_only_unverified'|'annotation_unverified';kind?:Dependency['kind'];id?:string;locator?:string;revision_id?:string;version?:string;text_sha256?:string}
export interface SourceValidation {schema_version:1;scope:'reference_location_and_literal_quote_only';semantic_accuracy_verified:false;mode:'checked'|'inherited'|'inherited_unverified';references?:ReferenceCheck[];inherited_from?:{artifact_id:string;revision_id:string;original_mode:string|null}}
type EvidenceContext={artifacts:Map<string,ResearchArtifact>;documents:Map<string,string>;pages:Map<string,any>;fixed:RecordedDependency[];checks:ReferenceCheck[]};
const evidenceContext=():EvidenceContext=>({artifacts:new Map(),documents:new Map(),pages:new Map(),fixed:[],checks:[]});
const validationRecord=(mode:SourceValidation['mode'],extra:Partial<SourceValidation>={}):SourceValidation=>({schema_version:1,scope:'reference_location_and_literal_quote_only',semantic_accuracy_verified:false,mode,...extra});
export interface ResearchArtifact {id:string;revision_id:string;parent_revision_id?:string;kind:string;title:string;created_at:string;run_id?:string;dependencies:RecordedDependency[];spec?:any;result?:any;content?:any;source_model?:ImportedModel;source_validation?:SourceValidation;input_bindings?:any[]}
const MODEL_KINDS=['dcf','comparables','manufacturing_scenario','financial_quality','three_statement'] as const;
const common=z.object({title:z.string().trim().min(1).max(200),dependencies:z.array(dependencySchema).max(100).default([]),artifact_id:idSchema.optional(),parent_revision_id:idSchema.optional()});
const modelPath=z.string().regex(/^[A-Za-z0-9_]+(?:\.[A-Za-z0-9_]+)*$/);
const binding=z.object({fact_id:idSchema.optional(),record_id:idSchema.optional(),scale:z.string().min(1).optional()}).refine(v=>!!v.fact_id!==!!v.record_id,{message:'绑定使用fact_id或record_id，二选一'});
const modelInput=common.extend({kind:z.enum(MODEL_KINDS),spec:z.record(z.string(),z.any()).optional(),source_model:sourceModelSchema.optional(),overrides:z.record(modelPath,z.any()).optional(),bindings:z.record(modelPath,binding).optional()}).superRefine((v,ctx)=>{
 if((v.spec===undefined)===(v.source_model===undefined))ctx.addIssue({code:'custom',message:'spec与source_model必须且只能提供一项'});
});
function setModelInput(spec:any,p:string,value:any){
 const parts=modelPath.parse(p).split('.');if(parts.some(x=>['__proto__','prototype','constructor'].includes(x)))throw new Error('不允许的输入路径');
 let parent=spec;for(const key of parts.slice(0,-1)){if(!Object.hasOwn(parent,key))throw new Error('模型输入路径不存在：'+p);parent=parent[key];}
 parent[parts.at(-1)!]=value;
}
function inlineBindings(spec:any):Record<string,z.infer<typeof binding>>{
 const found:Record<string,z.infer<typeof binding>>={};
 function visit(value:any,parts:string[]){
  if(!value||typeof value!=='object')return;
  if(Object.hasOwn(value,'fact_id')||Object.hasOwn(value,'record_id')){
   const key=modelPath.parse(parts.join('.'));found[key]=binding.parse(value);return;
  }
  for(const [key,child] of Object.entries(value)){
   if(parts.length===0&&['source_refs','input_basis'].includes(key))continue;
   visit(child,[...parts,key]);
  }
 }
 visit(spec,[]);return found;
}
const claim=z.object({id:idSchema,text:z.string().min(1),type:z.enum(['fact','calculation','inference','assumption']),evidence:z.array(evidenceSchema),confidence:z.enum(['high','medium','low']).optional()}).refine(c=>!['fact','calculation'].includes(c.type)||c.evidence.length>0,{message:'事实与计算需要至少一个可定位来源'});
const chain=z.object({industry:z.string().min(1),as_of:z.string().min(1),nodes:z.array(z.object({id:idSchema,label:z.string().min(1),role:z.enum(['upstream','company','downstream','macro'])})).min(2),edges:z.array(z.object({from:idSchema,to:idSchema,mechanism:z.string().min(1),direction:z.enum(['positive','negative','conditional','unknown']),evidence:z.array(evidenceSchema),assumptions:z.array(z.object({name:z.string(),value:z.string(),unit:z.string(),basis:z.enum(['disclosed','analyst_assumption']),rationale:z.string()}))})).min(1),claims:z.array(claim).default([]),scenario_model_id:idSchema.optional()});
const memo=z.object({company:z.string().min(1),as_of:z.string().min(1),thesis:z.string().min(1),claims:z.array(claim).min(1),catalysts:z.array(z.string()),risks:z.array(z.string()).min(1),falsification_conditions:z.array(z.object({indicator:z.string().min(1),condition:z.string().min(1),horizon:z.string().min(1),action:z.string().min(1)})).min(1),valuation_artifact_id:idSchema.optional(),conclusion:z.string().min(1)});
const correction=z.object({original_text:z.string().min(1).max(100000),issues:z.array(z.object({id:idSchema,start:z.number().int().nonnegative(),end:z.number().int().positive(),original:z.string().min(1),replacement:z.string(),category:z.enum(['number','unit','period','scope','formula','citation','reasoning']),reason:z.string().min(1),evidence:z.array(evidenceSchema).min(1)})),verified_claims:z.array(claim).default([])});
const reportInput=common.extend({kind:z.enum(['industry_chain','investment_memo','report_correction']),content:z.record(z.string(),z.any())});
const hash=(value:any)=>createHash('sha256').update(JSON.stringify(value)).digest('hex');
export function applyCorrections(input:z.infer<typeof correction>){
 const parsed=correction.parse(input),sorted=[...parsed.issues].sort((a,b)=>a.start-b.start);let cursor=0,output='';
 const ids=new Set<string>();
 for(const issue of sorted){if(ids.has(issue.id))throw new Error('纠错条目 ID 重复');ids.add(issue.id);if(issue.start<cursor||issue.end>parsed.original_text.length||parsed.original_text.slice(issue.start,issue.end)!==issue.original)throw new Error('纠错原文位置重叠或与原文不一致，start/end使用JavaScript UTF-16字符索引');output+=parsed.original_text.slice(cursor,issue.start)+issue.replacement;cursor=issue.end;}
 return {...parsed,revised_text:output+parsed.original_text.slice(cursor),offset_contract:'JavaScript UTF-16, start inclusive, end exclusive'};
}

export class ArtifactStore {
 private queues=new Map<string,Promise<unknown>>();
 constructor(readonly root=path.join(DATA,'research')){}
 private folder(project:string){return path.join(this.root,idSchema.parse(project),'artifacts');}
 private async revisions(project:string):Promise<ResearchArtifact[]>{let files:string[];try{files=await readdir(this.folder(project));}catch(e:any){if(e.code==='ENOENT')return [];throw e;}return Promise.all(files.filter(x=>x.endsWith('.json')).map(async f=>JSON.parse(await readFile(path.join(this.folder(project),f),'utf8'))));}
 async list(project:string){const revisions=await this.revisions(project),parents=new Set(revisions.map(x=>x.parent_revision_id).filter(Boolean)),map=new Map<string,ResearchArtifact>();for(const a of revisions.filter(x=>!parents.has(x.revision_id))){const prev=map.get(a.id);if(!prev||a.created_at>prev.created_at)map.set(a.id,a);}return [...map.values()].sort((a,b)=>b.created_at.localeCompare(a.created_at));}
 async get(project:string,id:string,revision?:string){idSchema.parse(id);const items=revision?(await this.revisions(project)).filter(x=>x.revision_id===idSchema.parse(revision)):await this.list(project);const found=items.find(x=>x.id===id);if(!found)throw Object.assign(new Error('研究成果不存在'),{status:404});return found;}
 async save(project:string,input:Omit<ResearchArtifact,'id'|'revision_id'|'created_at'>,artifactId?:string){
  let value!:ResearchArtifact;
  const op=(this.queues.get(project)??Promise.resolve()).catch(()=>{}).then(async()=>{
   const id=artifactId?idSchema.parse(artifactId):'research_'+randomUUID();
   if(artifactId){const previous=await this.get(project,id);if(previous.revision_id!==input.parent_revision_id)throw Object.assign(new Error('该成果已有新版本，请刷新后再修改'),{status:409});}
   else if(input.parent_revision_id)throw new Error('新成果不能指定前一版本');
   value={...input,id,revision_id:'revision_'+randomUUID(),created_at:new Date().toISOString()};
   const dir=this.folder(project);await publishFile(path.join(dir,value.revision_id+'.json'),JSON.stringify(value,null,2));
  });this.queues.set(project,op);await op;return value;
 }
}
export const artifactStore=new ArtifactStore();

export class ResearchWorkspace {
 constructor(private service:FinanceService,readonly artifacts=artifactStore,readonly sources:ResearchStore=researchStore){}
 private async version(project:string,d:Dependency,current=false):Promise<string>{
  if(d.kind==='source')return current?this.sources.latestVersion(project,d.id):(await this.sources.get(project,d.id)).sha256;
  if(d.kind==='artifact')return (await this.artifacts.get(project,d.id)).revision_id;
  return (await this.service.call('get_research_document_version',{project_id:project,document_id:d.id})).data.version;
 }
 private async dependencies(project:string,dependencies:Dependency[],ownId?:string,fixed:RecordedDependency[]=[]){
  const recorded=new Map<string,RecordedDependency>();
  const add=(d:RecordedDependency)=>{
   const parsed=dependencySchema.parse(d);if(parsed.kind==='artifact'&&parsed.id===ownId)throw new Error('成果不能依赖自身');
   if(typeof d.version!=='string'||!d.version)throw new Error('固定来源缺少版本：'+parsed.id);
   const key=parsed.kind+':'+parsed.id,previous=recorded.get(key);
   if(previous&&previous.version!==d.version)throw new Error('同一来源的固定版本冲突：'+parsed.id);
   if(!previous)recorded.set(key,{...parsed,version:d.version});
  };
  // Fixed records come from an immutable saved artifact or a source just read by
  // this operation. Inherited refs must not silently upgrade them to latest.
  fixed.forEach(add);
  for(const d of dependencies){if(d.kind==='artifact'&&d.id===ownId)throw new Error('成果不能依赖自身');if(!recorded.has(d.kind+':'+d.id))add({...d,version:await this.version(project,d)});}
  return [...recorded.values()];
 }
 private async artifactSnapshot(project:string,id:string,revision:string|undefined,context:EvidenceContext){
  let selected=context.artifacts.get(id);
  if(selected&&revision&&selected.revision_id!==revision)throw new Error('同一来源的固定版本冲突：'+id);
  if(!selected){selected=await this.artifacts.get(project,id,revision);context.artifacts.set(id,selected);}
  return selected;
 }
 private async resolveEvidence(project:string,raw:any,referencePath:string,context:EvidenceContext){
  const ref=evidenceSchema.parse(raw);let text='',version='';
  if(ref.kind==='source'){
   const snapshot=await this.sources.get(project,ref.id),ids=ref.locator.split(',').map(x=>x.trim()),paragraphs=snapshot.paragraphs.filter(x=>ids.includes(x.id));
   if(paragraphs.length!==new Set(ids).size)throw new Error('网页引用段落不存在：'+ref.locator);
   text=paragraphs.map(x=>x.text).join('\n');version=snapshot.sha256;
  }else if(ref.kind==='document'){
   const match=/^page:([1-9]\d*)$/.exec(ref.locator);if(!match)throw new Error('文档引用请用 page:物理页码');
   let original=context.documents.get(ref.id);
   if(!original){original=await this.version(project,{kind:'document',id:ref.id});context.documents.set(ref.id,original);}
   const key=ref.id+':'+match[1];let page=context.pages.get(key);
   if(!page){page=(await this.service.call('get_source_page',{project_id:project,document_id:ref.id,page:Number(match[1])})).data;if(!page||typeof page!=='object')throw new Error('引用文档页不存在：'+ref.locator);context.pages.set(key,page);}
   text=page.text??page.page?.text??'';version=original;
  }else{
   const selected=await this.artifactSnapshot(project,ref.id,ref.revision_id,context);
   ref.revision_id=selected.revision_id;raw.revision_id=selected.revision_id;
   text=JSON.stringify(artifactField(selected,ref.locator));version=selected.revision_id;
  }
  if(typeof text!=='string')throw new Error('引用位置没有可核对文本：'+ref.locator);
  const quote=ref.quote?.replace(/\s/g,'');
  if(quote&&!text.replace(/\s/g,'').includes(quote))throw new Error('引用文字未在所选来源位置找到：'+ref.locator);
  context.fixed.push({kind:ref.kind,id:ref.id,version});
  context.checks.push({path:referencePath,status:quote?'locator_and_quote_match':'locator_exists',kind:ref.kind,id:ref.id,locator:ref.locator,...(ref.revision_id?{revision_id:ref.revision_id}:{}),version,text_sha256:hash(text)});
  return ref;
 }
 private async finishEvidence(project:string,context:EvidenceContext){
  // Document state is mutable, unlike archived web/artifact revisions. One check
  // per cited document prevents a mixed snapshot being recorded as one version.
  for(const [id,version] of context.documents)if(await this.version(project,{kind:'document',id})!==version)throw new Error('引用文档在核验期间发生变化，请重新读取后保存：'+id);
 }
 private async modelReferences(project:string,value:any,referencePath:string,context:EvidenceContext,refs:Dependency[],inherited=false){
  if(!value||typeof value!=='object')return;
  if(Array.isArray(value)){for(let i=0;i<value.length;i++)await this.modelReferences(project,value[i],referencePath+'/'+i,context,refs,inherited);return;}
  const candidates:Dependency[]=[];
  if(Object.hasOwn(value,'kind')&&(Object.hasOwn(value,'id')||Object.hasOwn(value,'locator')))candidates.push(dependencySchema.parse({kind:value.kind,id:value.id}));
  if(!candidates.length){
   if(typeof value.document_id==='string')candidates.push(dependencySchema.parse({kind:'document',id:value.document_id}));
   if(typeof value.source_id==='string'&&value.source_id.startsWith('web_'))candidates.push(dependencySchema.parse({kind:'source',id:value.source_id}));
   if(typeof value.artifact_id==='string')candidates.push(dependencySchema.parse({kind:'artifact',id:value.artifact_id}));
  }
  for(const dependency of candidates){
   refs.push(dependency);
   if(inherited){
    const original=context.fixed.find(d=>d.kind===dependency.kind&&d.id===dependency.id);
    if(!original)throw new Error('导入来源未记录固定版本，不能重新绑定最新证据：'+dependency.id);
    if(dependency.kind==='artifact'&&value.revision_id!==undefined&&value.revision_id!==original.version)throw new Error('导入引用版本与原依赖不一致：'+dependency.id);
    continue;
   }
   if(Object.hasOwn(value,'locator')){
    const normalized={...value,...dependency};
    await this.resolveEvidence(project,normalized,referencePath,context);
    if(normalized.revision_id)value.revision_id=normalized.revision_id;
   }else{
    let version:string|undefined;
    if(dependency.kind==='artifact'&&value.revision_id!==undefined){const selected=await this.artifactSnapshot(project,dependency.id,idSchema.parse(value.revision_id),context);version=selected.revision_id;context.fixed.push({...dependency,version});}
    context.checks.push({path:referencePath,status:'dependency_only_unverified',...dependency,...(version?{version,revision_id:version}:{})});
   }
  }
  if(!inherited&&!candidates.length&&typeof value.type==='string')context.checks.push({path:referencePath,status:'annotation_unverified'});
  for(const [key,child] of Object.entries(value))if(child&&typeof child==='object')await this.modelReferences(project,child,referencePath+'/'+key.replaceAll('~','~0').replaceAll('/','~1'),context,refs,inherited);
 }
 async status(project:string,artifact:ResearchArtifact,visited=new Set<string>()):Promise<any>{
  if(visited.has(artifact.id))return {...artifact,dependency_status:'stale',changed_dependencies:[{reason:'cyclic_dependency'}]};
  const ancestors=new Set(visited).add(artifact.id),changed=[];
  for(const d of artifact.dependencies){try{const current=await this.version(project,d,true);if(current!==d.version)changed.push({...d,current_version:current,reason:'changed'});else if(d.kind==='artifact'){const downstream=await this.status(project,await this.artifacts.get(project,d.id),ancestors);if(downstream.dependency_status==='stale')changed.push({...d,reason:'upstream_stale'});}}catch{changed.push({...d,reason:'missing'});}}
  return {...artifact,dependency_status:changed.length?'stale':'current',changed_dependencies:changed};
 }
 async list(project:string){return Promise.all((await this.artifacts.list(project)).map(a=>this.status(project,a)));}
 async get(project:string,id:string,revision?:string){return this.status(project,await this.artifacts.get(project,id,revision));}
 async model(project:string,input:unknown,runId?:string){
  const v=modelInput.parse(input),refs:Dependency[]=[],context=evidenceContext();
  let spec=v.spec?structuredClone(v.spec):undefined,sourceModel:ImportedModel|undefined,sourceValidation:SourceValidation|undefined,inputBindings:any[]=[];
  if(v.source_model){
   const selected=await this.artifacts.get(project,v.source_model.artifact_id,v.source_model.revision_id);
   const importedScenario=selected.kind==='manufacturing_scenario'&&v.kind==='dcf'&&v.source_model.variant;
   if(v.source_model.variant&&!importedScenario)throw new Error('variant仅用于制造业情景导入DCF');
   if(v.artifact_id===selected.id&&v.kind!==selected.kind)throw new Error('不同类型模型请新建成果，不能更改原成果类型');
   if(!importedScenario&&selected.kind!==v.kind)throw new Error('source_model类型不匹配；制造业情景导入DCF须选择baseline或scenario');
   const candidate=importedScenario?selected.result?.results?.[v.source_model.variant+'_dcf_spec']:selected.spec;
   if(!candidate||typeof candidate!=='object'||Array.isArray(candidate))throw new Error('所选模型版本没有可复用输入');
   spec=structuredClone(candidate);
   inputBindings=importedScenario?[]:structuredClone(selected.input_bindings||[]);
   sourceModel={artifact_id:selected.id,revision_id:selected.revision_id,variant:v.source_model.variant,spec_sha256:hash(spec)};
   if(v.artifact_id!==selected.id)context.fixed.push({kind:'artifact',id:selected.id,version:selected.revision_id});
   else v.parent_revision_id??=selected.revision_id;
   context.fixed.push(...selected.dependencies);
   sourceValidation=validationRecord(selected.source_validation?'inherited':'inherited_unverified',{inherited_from:{artifact_id:selected.id,revision_id:selected.revision_id,original_mode:selected.source_validation?.mode??null}});
  }
  if(!spec)throw new Error('缺少模型输入');
  for(const [key,value] of Object.entries(v.overrides||{})){
   setModelInput(spec,key,value);
   inputBindings=inputBindings.filter(x=>x.path!==key&&!x.path.startsWith(key+'.'));
   for(const map of ['source_refs','input_basis'])for(const existing of Object.keys(spec[map]||{}))if(existing===key||existing.startsWith(key+'.'))delete spec[map][existing];
   spec.input_basis??={};spec.input_basis[key]={basis:'assumption',source_kind:'assumption',rationale:'本次显式修改；未绑定新来源时作为分析假设。'};
  }
  const bindings=inlineBindings(spec);
  for(const [key,value] of Object.entries(v.bindings||{})){
   if(bindings[key]&&JSON.stringify(bindings[key])!==JSON.stringify(value))throw new Error('同一输入指定了不同记录：'+key);
   bindings[key]=value;
  }
  if(Object.keys(bindings).length){
   const bound=(await this.service.call('resolve_model_inputs',{project_id:project,spec,bindings})).data;
   if(!bound?.spec)throw new Error('模型数据绑定失败：'+(bound?.error||'未知错误'));
   spec=bound.spec as Record<string,any>;inputBindings=[...inputBindings.filter(x=>!Object.hasOwn(bindings,x.path)),...bound.bindings];
   const freshRefs=spec.source_refs;
   const fresh=Object.fromEntries(Object.keys(bindings).map(key=>[key,freshRefs[key]]));
   await this.modelReferences(project,fresh,'/source_refs',context,refs);
  }
  const unchangedRefs=Object.fromEntries(Object.entries(spec.source_refs||{}).filter(([key])=>!Object.hasOwn(bindings,key)));
  await this.modelReferences(project,unchangedRefs,'/source_refs',context,refs,!!sourceModel);
  await this.finishEvidence(project,context);
  if(!sourceModel)sourceValidation=validationRecord('checked',{references:context.checks});
  else if(context.checks.length)sourceValidation={...sourceValidation!,references:context.checks};
  const dependencies=await this.dependencies(project,[...v.dependencies,...refs],v.artifact_id,context.fixed);
  const result=(await this.service.call('evaluate_research_model',{project_id:project,kind:v.kind,spec})).data;
  const record=await this.artifacts.save(project,{kind:v.kind,title:v.title,spec,result,dependencies,parent_revision_id:v.parent_revision_id,run_id:runId,source_validation:sourceValidation,...(inputBindings.length?{input_bindings:inputBindings}:{}),...(sourceModel?{source_model:sourceModel}:{})},v.artifact_id);
  return this.status(project,record);
 }
 async compare(project:string,input:any){
  const reference=z.object({artifact_id:idSchema,revision_id:idSchema.optional()}).strict();
  const v=z.object({baseline:reference,scenario:reference,order:z.array(modelPath).optional()}).parse(input);
  const baseline=await this.artifacts.get(project,v.baseline.artifact_id,v.baseline.revision_id),scenario=await this.artifacts.get(project,v.scenario.artifact_id,v.scenario.revision_id);
  if(baseline.kind!==scenario.kind||!baseline.spec||!scenario.spec)throw new Error('比较需要两份同类型的金融模型');
  const result=(await this.service.call('compare_research_models',{project_id:project,kind:baseline.kind,baseline:baseline.spec,scenario:scenario.spec,order:v.order})).data;
  const model_refs={base:{artifact_id:baseline.id,revision_id:baseline.revision_id},scenario:{artifact_id:scenario.id,revision_id:scenario.revision_id}};
  return {...result,baseline:model_refs.base,scenario:model_refs.scenario,
   analysis:{tool:'run_analysis',model_refs,comparisons:{change:{baseline:'base',scenario:'scenario',...(v.order?{order:v.order}:{})}},read:'models.json and comparisons.json; input/result/difference CSV and full calculator ZIP are exported automatically; script only draws and explains these results'}};
 }
 async report(project:string,input:unknown,runId?:string){
  const v=reportInput.parse(input);let content:any=v.kind==='industry_chain'?chain.parse(v.content):v.kind==='investment_memo'?memo.parse(v.content):applyCorrections(correction.parse(v.content));
  if(v.kind==='industry_chain'){
   const nodes=new Set(content.nodes.map((n:any)=>n.id));if(nodes.size!==content.nodes.length)throw new Error('产业链节点 ID 重复');
   for(const edge of content.edges)if(!nodes.has(edge.from)||!nodes.has(edge.to)||edge.from===edge.to)throw new Error('产业链关系必须连接两个有效节点');
   for(const edge of content.edges)if(!edge.evidence.length&&!edge.assumptions.length)throw new Error('产业链关系需要来源或明确的分析假设');
  }
  const refs:{ref:any;path:string}[]=[],context=evidenceContext();
  const walk=(x:any,p='/content')=>{if(!x||typeof x!=='object')return;if(Array.isArray(x)){x.forEach((item,i)=>walk(item,p+'/'+i));return;}if(Array.isArray(x.evidence))x.evidence.forEach((ref:any,i:number)=>refs.push({ref,path:p+'/evidence/'+i}));Object.entries(x).filter(([k])=>k!=='evidence').forEach(([k,y])=>walk(y,p+'/'+k));};walk(content);
  for(const {ref,path:referencePath} of refs)await this.resolveEvidence(project,ref,referencePath,context);
  await this.finishEvidence(project,context);
  const deps=[...v.dependencies,...refs.map(({ref:{kind,id}})=>({kind,id}))];
  if(content.scenario_model_id)deps.push({kind:'artifact',id:content.scenario_model_id});if(content.valuation_artifact_id)deps.push({kind:'artifact',id:content.valuation_artifact_id});
  const dependencies=await this.dependencies(project,deps,v.artifact_id,context.fixed);
  const record=await this.artifacts.save(project,{kind:v.kind,title:v.title,content,dependencies,parent_revision_id:v.parent_revision_id,run_id:runId,source_validation:validationRecord('checked',{references:context.checks})},v.artifact_id);return this.status(project,record);
 }
}
export function artifactCsv(artifact:ResearchArtifact,table:string){
 const rows=artifact.result?.tables?.[table];if(!Array.isArray(rows))throw new Error('请选择有效结果表');
 const columns=[...new Set(rows.flatMap((r:any)=>Object.keys(r)))];const cell=(v:any)=>'"'+String(typeof v==='object'&&v!==null?JSON.stringify(v):v??'').replace(/"/g,'""')+'"';
 return '\uFEFF'+[columns.map(cell).join(','),...rows.map((r:any)=>columns.map(k=>cell(r[k as string])).join(','))].join('\r\n');
}
export function artifactField(artifact:ResearchArtifact,locator:string){
 const normalized=locator.replace(/^\$\.?/,'').replace(/\[(\d+)\]/g,'.$1');
 if(!/^[A-Za-z0-9_]+(?:\.[A-Za-z0-9_]+)*$/.test(normalized))throw new Error('成果引用字段路径无效');
 const keys=normalized.split('.');let value:any=artifact;
 // Calculator output is nested in result; model-facing result/table paths are accepted.
 if(!Object.hasOwn(artifact,keys[0])&&artifact.result&&Object.hasOwn(artifact.result,keys[0]))value=artifact.result;
 for(const key of keys){if(['__proto__','prototype','constructor'].includes(key)||!value||typeof value!=='object'||!Object.hasOwn(value,key))throw new Error('成果引用字段不存在：'+locator);value=value[key];}
 return value;
}
const str={type:'string'},obj={type:'object',additionalProperties:true};
const commonProps={title:str,dependencies:{type:'array',items:{type:'object',properties:{kind:{enum:['source','document','artifact']},id:str},required:['kind','id']}},artifact_id:{...str,description:'仅在更新已经保存的成果时填写返回过的ID。新建时省略，由程序生成，不自造ID。'},parent_revision_id:{...str,description:'已有成果的父版本；新建时省略。'}};
const modelRef={type:'object',additionalProperties:false,properties:{artifact_id:str,revision_id:str,variant:{enum:['baseline','scenario']}},required:['artifact_id']};
const savedModelRef={...modelRef,properties:{artifact_id:str,revision_id:str}};
export const ARTIFACT_TOOLS=[
 {name:'run_financial_model',description:'计算并保存金融模型，返回版本和可直接传给run_analysis的model_refs；导出和制图复用计算结果，无需重写DCF代码。新模型提供spec，数值位置直接用{fact_id:"查询得到的ID"}或{record_id:"研报记录ID"}，例如base:{revenue:{fact_id:"f1"}}；无须抄数值或另填bindings。也兼容bindings={"base.revenue":{fact_id:"f1"}}；数值、单位换算、实际/预测身份和单元格来源由程序带入。金额默认按spec.amount_scale、股数按shares.scale、百分数转小数；scale仅在需要显式覆盖时填写。复用已存模型用source_model加overrides={"forecast.0.capex":"新值"}，只改变化参数，不重抄spec；制造业情景导入DCF才需variant。同一artifact_id更新时保存新版本。输入格式可查get_research_model_schema。',inputSchema:{type:'object',properties:{...commonProps,kind:{enum:MODEL_KINDS},spec:obj,source_model:modelRef,overrides:obj,bindings:{type:'object',additionalProperties:{type:'object',properties:{fact_id:str,record_id:str,scale:str},oneOf:[{required:['fact_id'],not:{required:['record_id']}},{required:['record_id'],not:{required:['fact_id']}}]}}},required:['title','kind'],oneOf:[{required:['spec'],not:{required:['source_model']}},{required:['source_model'],not:{required:['spec']}}]}},
 {name:'compare_financial_models',description:'比较两份同类型模型的真实输入变化与数值结果差异。baseline/scenario={artifact_id,revision_id?}；程序读取保存输入，不必手抄。需要DCF贡献分解时，order列出全部变化路径的替换顺序（例如forecast.0.capex_ratio、forecast.0.da_ratio）；交互影响归于后替换项，不冒充唯一经济因果。',inputSchema:{type:'object',properties:{baseline:savedModelRef,scenario:savedModelRef,order:{type:'array',items:str}},required:['baseline','scenario']}},
 {name:'save_research_report',description:'保存产业链/投资备忘录/研报纠错。先get_research_report_schema。事实、推断、假设要区分；纠错必须定位原文并给出替换文本，宿主应用改动。保存后可在研究成果查看。',inputSchema:{type:'object',properties:{...commonProps,kind:{enum:['industry_chain','investment_memo','report_correction']},content:obj},required:['title','kind','content']}},
 {name:'get_research_report_schema',description:'获取研究报告严格结构与字段含义；无模型调用。',inputSchema:{type:'object',properties:{kind:{enum:['industry_chain','investment_memo','report_correction']}},required:['kind']}},
 {name:'list_research_artifacts',description:'查看项目研究成果及依赖更新状态。stale表示原始数据或上游模型改变，应读取差异并重新计算/分析；不自动改写旧结论。',inputSchema:{type:'object',properties:{}}},
 {name:'read_research_artifact',description:'读取研究成果完整假设、公式、数据、来源依赖与版本，按需修改生成新版本。',inputSchema:{type:'object',properties:{artifact_id:str,revision_id:str},required:['artifact_id']}}
];
export function reportSchema(kind:string){return z.toJSONSchema(kind==='industry_chain'?chain:kind==='investment_memo'?memo:kind==='report_correction'?correction:z.never());}
