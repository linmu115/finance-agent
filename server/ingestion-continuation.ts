// Business progress only. Pi still owns turns, retries, queues and compaction.
export function ingestionRemaining(snapshots:any[]){
 const documents=new Map<string,any>();
 for(const state of snapshots)for(const documentId of Object.keys(state.pending_tables||{}))documents.set(documentId,state);
 const keys=new Set<string>(),work:any[]=[];
 for(const [documentId,state] of documents){
  const tables=state.pending_tables?.[documentId]||[],pages=state.pending_pages?.[documentId]||[];
  const scripts=(state.pending_scripts||[]).filter((s:any)=>s.document_id===documentId);
  for(const t of tables)keys.add(`${documentId}:table:${t}`);
  for(const p of pages)keys.add(`${documentId}:page:${p}`);
  // Visiting an untouched table is real coverage progress even when its local
  // mapping fails. Once all remaining tables have been tried, failed retries
  // no longer count and the existing no-progress stop still applies.
  for(const t of state.unattempted_tables?.[documentId]||[])keys.add(`${documentId}:unattempted:${t}`);
  for(const s of scripts)keys.add(`${documentId}:script:${s.table}`);
  if(tables.length||pages.length||scripts.length)work.push({processing_id:state.processing_id,document_id:documentId,pending_tables:tables,pending_pages:pages,pending_scripts:scripts,next_batch:state.next_batch});
 }
 return {keys,work};
}

export function madeIngestionProgress(before:Set<string>,after:Set<string>){
 return [...before].some(key=>!after.has(key));
}
