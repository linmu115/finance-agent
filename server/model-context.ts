import type { Envelope } from './types.js';
import {numericTableView} from './numeric-tables.js';
const fields=(value:any,keys:string[])=>Object.fromEntries(keys.filter(k=>value?.[k]!==undefined).map(k=>[k,value[k]]));
function reviewSummary(value:any){
 if(!value||typeof value!=='object')return value;
 const summary:any={};
 for(const [key,item] of Object.entries(value)){
  if(item===null||['string','boolean','number'].includes(typeof item))summary[key]=item;
  else if(Array.isArray(item))summary[key+'_count']=item.length;
 }
 return summary;
}
const processingSummary=(v:any)=>({...fields(v,['batches','processing_id','owner_run_id','state','progress','message','errors','created_at','completed_at','fact_count','batch_count','review_issues']),documents:v.documents?.map((x:any)=>fields(x,['document_id','state','message','facts','fact_count','committed_fact_count','table_count','candidate_table_count','batch_count','completed_batches','errors','coverage','review_issues','text_coverage'])),catalog_review:reviewSummary(v.catalog_review),temporal_review:reviewSummary(v.temporal_review),definition_review:reviewSummary(v.definition_review)});
const present=(value:any)=>Object.fromEntries(Object.entries(value).filter(([,v])=>v!==null&&v!==undefined&&v!==''&&!(typeof v==='object'&&Object.keys(v).length===0)));
function analysisSource(ref:any,keepText=false){
 if(!ref||typeof ref!=='object')return ref;
 const location=fields(ref,['document_id','page','table_id','row','column','cell','start','end','offset_unit','research_record_id','source_id','url']);
 // Numeric cells have exact locators and literal numeric spans. Full row text,
 // hashes and processing history stay in the source APIs and original audit.
 const detail=fields(ref.normalization,['review_warnings','semantic_review_note','numeric_span','char_interval','data_kind','period_start','period_end','scale','unit_kind']);
 if(keepText||!ref.table_id)Object.assign(location,fields(ref,['text','quote','bbox']));
 return present({...location,normalization:present(detail)});
}
function citationIndex(items:any[],fallback:any[]=[]){
 const refs=items.flatMap(x=>[x.source_ref,...(x.alternative_sources||[])]).filter(Boolean);
 return [...new Map((refs.length?refs:fallback).map(ref=>{
  const locator=fields(ref,['document_id','page','table_id','row','column','cell','start','end','offset_unit','research_record_id','source_id','url']);
  return [JSON.stringify(locator),locator];
 })).values()];
}
function factView(x:any){
 const {source_json,normalization,normalization_metadata,catalog_review,temporal_review,definition_review,rowid,project_id,priority,normalization_engine,...fact}=x;
 return present({...fact,...(fact.source_ref?{source_ref:analysisSource(fact.source_ref,x.quality==='needs_review'||x.quality==='conflict')}:{}),...(fact.alternative_sources?{alternative_sources:fact.alternative_sources.map((s:any)=>analysisSource(s,true))}:{}),...(temporal_review?{temporal_review:fields(temporal_review,['status','after','reason','review_id'])}:{}),...(definition_review?{definition_review:fields(definition_review,['status','after','reason','review_id'])}:{})});
}
// Only the model-facing view is projected. Full results remain in the audit and API.
export function modelContext(name:string,envelope:Envelope):Envelope {
 if(envelope.status==='error')return envelope;
 if(!envelope.data)return envelope;
 const data=envelope.data;
 if(name==='get_analysis_status')return {...envelope,data:numericTableView(data)};
 if(name==='get_data_catalog')return {...envelope,data:{...data,documents:data.documents?.map((x:any)=>fields(x,['document_id','original_name','state','company','page_count','table_count','fact_count','profile','research_record_count','relative_path','warnings'])),processing:data.processing?.map((v:any)=>({...fields(v,['processing_id','state','message','errors','review_issues']),documents:v.documents?.map((x:any)=>fields(x,['document_id','state','message','review_issues','text_coverage'])),catalog_review:reviewSummary(v.catalog_review),temporal_review:reviewSummary(v.temporal_review),definition_review:reviewSummary(v.definition_review)})),...(data.pagination?.statement&&data.research_catalog?{research_catalog:fields(data.research_catalog,['total_metrics','query_tool'])}:{}),metric_aliases:data.metric_aliases?.map((x:any)=>fields(x,['source_metric','canonical_metric','canonical_label'])),catalog_review:reviewSummary(data.catalog_review),temporal_review:reviewSummary(data.temporal_review),definition_review:reviewSummary(data.definition_review),detail_tools:['get_normalization_details','get_source_table','get_source_page'],projection:'目录保留实际指标/维度/路径/处理摘要；逐格来源与详细规范化记录按需读取。'}};
 if(name==='process_documents'&&(data.instructions||data.state==='routing_required'))return envelope;
 if(name==='process_documents')return {...envelope,data:processingSummary(data)};
 if(name==='query_financial_data'||name==='get_financial_metrics'){
  const items=data.items?.map(factView);
  return {...envelope,...(envelope.source_refs?{source_refs:citationIndex(items||[],envelope.source_refs)}:{}),data:{...data,items}};
 }
 if(name==='query_research_records'){
  // SQL storage, record payload and citation list can contain three copies of
  // the same source. Keep one complete source (including all meaning, warnings
  // and exact quote offsets) per item; the citation list remains a locator.
  const items=data.items?.map((x:any)=>{
   const {source_json,source,project_id,batch_key,record_key,content_hash,source_key,created_at,...record}=x;
   return present({...record,source_ref:analysisSource(x.source_ref??source,x.record_type==='claim'||x.quality==='needs_review')});
  });
  return {...envelope,data:{...data,items},...(envelope.source_refs?{source_refs:citationIndex(items||[],envelope.source_refs)}:{})};
 }
 if(name==='run_financial_model'||name==='save_research_report'){
  const {spec,content,source_validation,delivery,...saved}=data;
  if(!saved.id||!saved.revision_id)return envelope;
  // The model needs the names of what the user already received, not the download addresses.
  const delivered=delivery?.files?{delivered_to_user:delivery.files.map((file:any)=>file.name)}:delivery;
  // A successful write returns its computed result and immutable version.
  // Inputs already appear in the paired tool call and remain readable in full.
  const result=saved.result?{...saved.result}:undefined;
  if(result)delete result.input_assumptions;
  const input_bindings=saved.input_bindings?.map((x:any)=>fields(x,['path','record_id','record_type','value','source_value','scale','period','scope','currency','quality','data_kind','document_id']));
  return {...envelope,data:{...saved,...(result?{result}:{}),...(input_bindings?{input_bindings}:{}),...(source_validation?{source_validation}:{}),...(delivered?{delivery:delivered}:{}),saved_input:{spec_saved:spec!==undefined||saved.saved_input?.spec_saved===true,content_saved:content!==undefined||saved.saved_input?.content_saved===true,read_tool:'read_research_artifact',artifact_id:saved.id,revision_id:saved.revision_id},...(spec?{analysis:{tool:'run_analysis',model_refs:{model:{artifact_id:saved.id,revision_id:saved.revision_id}},read:"json.load(open('/input/models.json'))['model']['result']",delivery:delivery?.files?'This call already delivered the input table with units, the result tables, any differences from the updated version and the calculator bundle to the user (delivery.delivered_to_user). Use run_analysis only to draw charts or write a report from the saved tables; do not recompute, compare or re-export the model.':'Exact input/result CSVs and model_bundle.zip (full calculator + inputs) exported automatically. Write only charts/report using saved tables; no need to reimplement the model.'}}:{}),projection:'返回计算结果及保存版本；不重复刚提交的完整输入，按版本可读全部参数、来源和底稿。'}};
 }
 return envelope;
}

// Older persistent Pi sessions may contain the full tool envelopes produced
// before model-only projections existed. Project those at request time without
// rewriting their saved conversation, source evidence, or audit history. This
// only removes duplicated metadata, exactly as for newly returned tool results.
// Pi alone decides when history needs compaction; age and tool counts never
// replace readable evidence with receipts.
export function projectToolHistory<T extends {messages:any[]}>(context:T){
 let changed=0,before=0,after=0;
 const messages=context.messages.map(message=>{
  if(message.role!=='toolResult'||!['get_data_catalog','process_documents','query_financial_data','get_financial_metrics','query_research_records','run_financial_model','save_research_report'].includes(message.toolName)||!Array.isArray(message.content))return message;
  let modified=false;
  const content=message.content.map((block:any)=>{
   if(block.type!=='text'||typeof block.text!=='string')return block;
   try{
    const value=JSON.parse(block.text);if(!value||typeof value!=='object'||Array.isArray(value)||!value.data||typeof value.data!=='object')return block;
    const projected=modelContext(message.toolName,value);
    const text=JSON.stringify(projected);
    // Never inflate an existing compact record or change a non-projectable tool.
    if(text.length>=block.text.length)return block;
    before+=block.text.length;after+=text.length;modified=true;return {...block,text};
   }catch{return block;}
  });
  if(!modified)return message;changed++;return {...message,content};
 });
 return {context:changed?{...context,messages}:context,projection:{version:'3.0',modified_tool_results:changed,before_chars:before,after_chars:after}};
}
