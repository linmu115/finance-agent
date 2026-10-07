/** Full tables stay in the host/audit. Only the model view has a row budget. */
export const NUMERIC_TABLE_CHAR_BUDGET=24000;
export function registerNumericTables(registry:Record<string,any>,data:any){
 const tables=data.numeric_tables??data.report?.tables??data.result?.report?.tables;
 if(tables)Object.assign(registry,structuredClone(tables));
 return registry;
}
export function referenceInventory(tables:Record<string,any>){
 return Object.fromEntries(Object.entries(tables).map(([name,t])=>[name,{columns:Object.fromEntries(Object.entries(t.columns).map(([k,c])=>{const col=c as any;return [k,{unit:col.unit??null,currency:col.currency??null,...(col.per_cell_unit?{per_cell_unit:true}:{})}];})),row_keys:t.row_keys??t.rows.map((r:any,i:number)=>t.row_key?String(r[t.row_key]):String(i))}]));
}
export function numericTableView(data:any,budget=NUMERIC_TABLE_CHAR_BUDGET){
 if(!data.numeric_tables)return data;
 let used=0;
 const numeric_tables=Object.fromEntries(Object.entries(data.numeric_tables).map(([name,raw])=>{
  const table=raw as any,{rows=[],display_rows=[],row_keys=[],cell_units=[],evidence,...meta}=table;
  const kept:any={...meta,rows:[],display_rows:[],row_keys:[],cell_units:[]};
  used+=JSON.stringify(meta).length;
  let count=0;
  for(let i=0;i<rows.length;i++){
   const size=JSON.stringify([rows[i],display_rows[i],row_keys[i],cell_units[i]]).length;
   if(used+size>budget)break;
   used+=size;count++;kept.rows.push(rows[i]);kept.display_rows.push(display_rows[i]??{});kept.row_keys.push(row_keys[i]??String(i));kept.cell_units.push(cell_units[i]??{});
  }
  if(count<rows.length){
   const read=data.id?(name.startsWith('dcf_update')&&data.changes?.from?{tool:'compare_financial_models',baseline:data.changes.from,scenario:{artifact_id:data.id,revision_id:data.revision_id},order:data.changes.decomposition?.order}:{tool:'read_research_artifact',artifact_id:data.id,revision_id:data.revision_id}):{tool:'get_artifact',run_id:data.run_id,name:table.artifact,rows:{start:table.origin==='csv'?count:0},...(table.origin==='csv'?{}:{note:`JSON 对象按文本行读取，目标表 ${name}`})};
   kept.truncation={remaining_rows:rows.length-count,total_rows:rows.length,message:`已截断：剩余 ${rows.length-count} 行，用 ${read.tool} 读取。`,read};
  }
  return [name,kept];
 }));
 return {...data,numeric_tables,references:referenceInventory(data.numeric_tables),answer_bindings:{cell:'{{表名.行键或行号.列名}}',table:'{{table:表名}}',chart:'{{chart:文件名}}'}};
}
