/** Enforce explicit workpaper restrictions only on their identified bindings. */
export function registerWorkpaperConstraints(registry:Record<string,any>,data:any){
 const tables=data.numeric_tables||{};
 for(const [id,c] of Object.entries(registry))if(c.affected_refs.some((ref:string)=>ref.split('.')[0] in tables))delete registry[id];
 for(const c of data.answer_constraints||[]){
  const s=c.subject;
  registry[c.id]={id:c.id,affected_refs:(s.row_keys||[s.row_key]).flatMap((r:string)=>s.columns.map((col:string)=>`${s.table}.${r}.${col}`)),
   forbidden_claims:c.prohibited_uses,required_qualification:c.message};
 }
 for(const c of data.context?.comparability_constraints||[])registry[c.id]=c;
}

const forbidden:Record<string,RegExp>={
 label_as_parent_profit:/归母(?:净)?利(?:润)?|归属于(?:母公司|上市公司)/g,
 parent_profit_comparison:/归母.{0,12}(?:误差|增速|增长|差额|同比|比较)/g,
 same_basis_error:/(?:同口径.{0,12})?(?:预测误差|预测偏差|误差率)/g,
 forecast_accuracy_ranking:/预测.{0,8}(?:准确|排名|最准)|准确度.{0,8}排名/g,
 beat_miss_conclusion:/超(?:出)?预期|低于预期|不及预期|符合预期/g,
 same_basis_comparison:/同口径(?:比较|对比|增长|增速|差额)/g,
 unqualified_cross_period_growth:/同比(?:增长|下降|增加|减少)|增长率|增速/g,
 same_basis_revision:/同口径.{0,8}(?:修正|调整|上调|下调)/g,
};
export function workpaperConstraintIssues(body:string,registry:Record<string,any>){
 const issues:any[]=[];
 for(const line of body.split(/[。！？；\n]/)){
  const refs=[...line.matchAll(/\{\{([^{}]+)\}\}/g)].map(m=>m[1].trim());
  const prose=line.replace(/\{\{[^{}]+\}\}/g,'数值');
  for(const c of Object.values(registry)){
   if(!c.affected_refs.some((ref:string)=>refs.includes(ref)||refs.includes('table:'+ref.split('.')[0])))continue;
   for(const kind of c.forbidden_claims){
    const pattern=forbidden[kind];if(!pattern)continue;
    const hit=[...prose.matchAll(pattern)].find(m=>!/(?:不能|不得|不可|不应|并非|不是|不构成|无法|不作|不做)[^，,：:]{0,24}$/.test(prose.slice(0,m.index)));
    if(hit){issues.push({kind:'workpaper_basis',source:'回答',text:line.trim(),constraint_id:c.id,message:c.required_qualification});break;}
   }
  }
 }
 return issues;
}
