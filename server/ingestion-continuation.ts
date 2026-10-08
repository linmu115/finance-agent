// Pi owns continuation; business progress comes from durable document commits.
export type IngestionProgress=Record<string,{completed_tables:number[],fact_count:number,table_statuses:Record<string,string>,pages_reviewed:number,research_record_count:number}>;
export function ingestionRemaining(snapshots:any[]){
 const documents=new Map<string,any>();
 // Backend refreshes every historical snapshot from the same document ledger.
 // Stable selection keeps one processing ID, independently of Set iteration.
 for(const state of [...snapshots].sort((a,b)=>String(a.processing_id).localeCompare(String(b.processing_id))))
  for(const documentId of Object.keys(state.pending_tables||{}))if(!documents.has(documentId))documents.set(documentId,state);
 const keys=new Set<string>(),work:any[]=[],progress:IngestionProgress={};let hasRunnableTables=false,repair=false;
 for(const [documentId,state] of documents){
  const tables=state.pending_tables?.[documentId]||[],pages=state.pending_pages?.[documentId]||[];
  const scripts=(state.pending_scripts||[]).filter((s:any)=>s.document_id===documentId);
  const d=(state.document_progress||[]).find((d:any)=>d.document_id===documentId);
  const runnable=state.runnable_tables?.[documentId]??tables;
  hasRunnableTables ||= runnable.length>0;repair ||= !!state.repair_phase&&runnable.length>0;
  if(d)progress[documentId]={completed_tables:d.completed_tables||[],fact_count:d.fact_count||0,table_statuses:d.table_statuses||{},pages_reviewed:d.text_coverage?.pages_reviewed||0,research_record_count:d.research_record_count||0};
  for(const t of tables)keys.add(`${documentId}:table:${t}`);
  for(const p of pages)keys.add(`${documentId}:page:${p}`);
  if(tables.length||pages.length||scripts.length)work.push({processing_id:state.processing_id,document_id:documentId,pending_tables:tables,pending_pages:pages,pending_scripts:scripts,next_batch:state.next_batch,
   repair_phase:!!state.repair_phase,deferred_count:Object.keys(state.deferred_tables?.[documentId]||{}).length,
   ...(!runnable.length?{deferred_tables:state.deferred_tables?.[documentId]||{}}:{})});
 }
 return {keys,work,progress,hasRunnableTables,repair};
}

export function continueIngestion(remaining:ReturnType<typeof ingestionRemaining>,prior?:IngestionProgress){
 if(!remaining.keys.size)return false;
 // Table deferral advances scheduling even when a local mapping submits no
 // facts. Page-only work still uses its actual durable coverage advancement.
 return remaining.hasRunnableTables || (remaining.work.some(w=>w.pending_pages.length>0)&&(!prior||madeIngestionProgress(prior,remaining.progress)));
}

export function madeIngestionProgress(before:IngestionProgress,after:IngestionProgress){
 return Object.entries(after).some(([id,current])=>{
  const prior=before[id];if(!prior)return current.completed_tables.length>0||current.fact_count>0||current.pages_reviewed>0;
  return current.fact_count>prior.fact_count||current.pages_reviewed>prior.pages_reviewed||current.research_record_count>prior.research_record_count||
   current.completed_tables.some(t=>!prior.completed_tables.includes(t))||
   Object.entries(current.table_statuses).some(([t,status])=>status==='completed'&&prior.table_statuses[t]==='needs_review');
 });
}
