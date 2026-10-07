/** Full tables stay in the host/audit. Only the model view has a row budget. */
export const NUMERIC_TABLE_CHAR_BUDGET=24000;
export function numericTableView(data:any,budget=NUMERIC_TABLE_CHAR_BUDGET){
 if(!data.numeric_tables)return data;
 let used=0;
 const numeric_tables=Object.fromEntries(Object.entries(data.numeric_tables).map(([name,raw])=>{
  const table=raw as any,{rows=[],display_rows=[],row_keys=[],cell_units=[],...meta}=table;
  const kept:any={...meta,rows:[],display_rows:[],row_keys:[],cell_units:[]};
  used+=JSON.stringify(meta).length;
  let count=0;
  for(let i=0;i<rows.length;i++){
   const size=JSON.stringify([rows[i],display_rows[i],row_keys[i],cell_units[i]]).length;
   if(used+size>budget)break;
   used+=size;count++;kept.rows.push(rows[i]);kept.display_rows.push(display_rows[i]??{});kept.row_keys.push(row_keys[i]??String(i));kept.cell_units.push(cell_units[i]??{});
  }
  if(count<rows.length)kept.truncation={remaining_rows:rows.length-count,total_rows:rows.length,message:`已截断：剩余 ${rows.length-count} 行，用 get_artifact 读取。`,read:{run_id:data.run_id,name:table.artifact,rows:{start:table.origin==='csv'?count:0},...(table.origin==='csv'?{}:{note:`JSON 对象按文本行读取，目标表 ${name}`})}};
  return [name,kept];
 }));
 return {...data,numeric_tables};
}
