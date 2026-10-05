import type { Envelope } from './types.js';
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
const processingSummary=(v:any)=>({...fields(v,['batches','processing_id','owner_run_id','state','progress','message','errors','created_at','completed_at','fact_count','batch_count']),documents:v.documents?.map((x:any)=>fields(x,['document_id','state','message','facts','fact_count','committed_fact_count','table_count','candidate_table_count','batch_count','completed_batches','errors','coverage'])),catalog_review:reviewSummary(v.catalog_review),temporal_review:reviewSummary(v.temporal_review),definition_review:reviewSummary(v.definition_review)});
function sourceReceipt(ref:any){
 if(!ref||typeof ref!=='object'||!ref.normalization)return ref;
 const {normalization,...source}=ref;
 // The expanded fact carries its current meaning and conversion. Retain exact
 // source coordinates and provenance identity here instead of repeating the
 // entire normalization/review history in each copy of the same citation.
 return {...source,normalization:fields(normalization,['engine','version','model','source_key','source_fingerprint','original_extraction_hash','processing_id','char_interval'])};
}
function factView(x:any){
 const {source_json,normalization,normalization_metadata,catalog_review,temporal_review,definition_review,...fact}=x;
 return {...fact,...(fact.source_ref?{source_ref:sourceReceipt(fact.source_ref)}:{}),...(fact.alternative_sources?{alternative_sources:fact.alternative_sources.map(sourceReceipt)}:{}),...(temporal_review?{temporal_review:fields(temporal_review,['status','after','reason','review_id'])}:{}),...(definition_review?{definition_review:fields(definition_review,['status','after','reason','review_id'])}:{})};
}
// Only the model-facing view is projected. Full results remain in the audit and API.
export function modelContext(name:string,envelope:Envelope):Envelope {
 if(envelope.status==='error')return envelope;
 if(!envelope.data)return envelope;
 const data=envelope.data;
 if(name==='get_data_catalog')return {...envelope,data:{...data,documents:data.documents?.map((x:any)=>fields(x,['document_id','original_name','state','company','page_count','table_count','fact_count','profile','research_record_count','sha256','relative_path','normalization_engine','warnings'])),processing:data.processing?.map(processingSummary),metric_aliases:data.metric_aliases?.map((x:any)=>fields(x,['source_metric','canonical_metric','canonical_label'])),catalog_review:reviewSummary(data.catalog_review),temporal_review:reviewSummary(data.temporal_review),definition_review:reviewSummary(data.definition_review),detail_tools:['get_normalization_details','get_source_table','get_source_page'],projection:'目录保留实际指标/维度/路径/处理摘要；逐格来源与详细规范化记录按需读取。'}};
 if(name==='process_documents'&&(data.instructions||data.state==='routing_required'))return envelope;
 if(name==='process_documents')return {...envelope,data:processingSummary(data)};
 if(name==='query_financial_data'||name==='get_financial_metrics'){
  const items=data.items?.map(factView);
  return {...envelope,...(envelope.source_refs?{source_refs:envelope.source_refs.map(sourceReceipt)}:{}),data:{...data,items}};
 }
 if(name==='query_research_records'){
  // SQL storage, record payload and citation list can contain three copies of
  // the same source. Keep one complete source (including all meaning, warnings
  // and exact quote offsets) per item; the citation list remains a locator.
  const items=data.items?.map((x:any)=>{
   const {source_json,source,...record}=x;
   return {...record,source_ref:x.source_ref??source};
  });
  return {...envelope,data:{...data,items},...(envelope.source_refs?{source_refs:envelope.source_refs.map((ref:any)=>fields(ref,['document_id','page','table_id','row','column','cell','start','end','offset_unit','research_record_id']))}:{})};
 }
 if(name==='run_financial_model'||name==='save_research_report'){
  const {spec,content,source_validation,...saved}=data;
  if(!saved.id||!saved.revision_id)return envelope;
  // A successful write returns its computed result and immutable version.
  // Inputs already appear in the paired tool call and remain readable in full.
  return {...envelope,data:{...saved,...(source_validation?{source_validation}:{}),saved_input:{spec_saved:spec!==undefined,content_saved:content!==undefined,read_tool:'read_research_artifact',artifact_id:saved.id,revision_id:saved.revision_id},projection:'返回完整计算结果及保存的版本；完整输入、参数依据和报告正文按版本读取。'}};
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
