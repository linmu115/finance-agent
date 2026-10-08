/** Deterministic financial-request entry; Pi still owns the reasoning loop. */
export function needsWorkpaper(profile:string|undefined,query:string){
 if(profile&&profile!=='financial')return false;
 const task=/(?:分析|比较|对比|解释|评估|诊断|解读|为什么|为何|变化|质量|异常|表现|驱动|核对|拆解|归因|给出|是否|怎么看|一致吗|analy[sz]e|compare|explain|assess)/i.test(query);
 if(/(?:入库|清洗|续跑|上传|ingest|cleaning)/i.test(query)&&!task)return false;
 if(/^(?:什么是|如何计算|解释一下概念|what is|how to calculate)/i.test(query.trim()))return false;
 return task&&/(?:财报|年报|季报|中报|业绩|利润|营收|收入|现金|毛利|扣非|资产负债|应收|存货|盈利|偿债|周转|季度|口径|预期|ROE|financial statements?|annual report|earnings|revenue|cash flow|profit)/i.test(query);
}

export function pipelineArguments(query:string,attachments:string[],documents:any[]){
 const args:Record<string,any>={kind:'analysis_pipeline',focus:query};
 if(attachments.length===1){args.document_id=attachments[0];return args;}
 // Only unambiguous, explicitly named document metadata is selected here.
 // The service owns company, period, basis and candidate resolution.
 let candidates=attachments.length?documents.filter(d=>attachments.includes(d.document_id)):documents;
 const years=[...new Set(query.match(/\b20\d{2}\b/g)||[])];
 if(years.length===1)candidates=candidates.filter(d=>String(d.report_year)===years[0]||d.original_name?.includes(years[0]));
 const reportType=/年报|年度报告|annual report/i.test(query)?/年报|年度|annual/i:
  /三季|第三季|Q3/i.test(query)?/三季|第三季|Q3/i:/中报|半年|H1|interim/i.test(query)?/中报|半年|H1|interim/i:
  /一季|第一季|Q1/i.test(query)?/一季|第一季|Q1/i:undefined;
 if(reportType)candidates=candidates.filter(d=>reportType.test(d.original_name||''));
 const named=candidates.filter(d=>query.includes(d.document_id)||query.includes(d.original_name)||d.company&&query.includes(d.company));
 if(named.length)candidates=named;
 if(candidates.length===1)args.document_id=candidates[0].document_id;
 if(years.length===1&&reportType?.test('年报'))args.periods=years[0]+'-FY';
 return args;
}

/** Tool examples are project-bound in the app; direct MCP retains project_id. */
export function appWorkpaperContext(context:any):any{
 if(Array.isArray(context))return context.map(appWorkpaperContext);
 if(!context||typeof context!=='object')return context;
 const result=Object.fromEntries(Object.entries(context).map(([k,v])=>[k,appWorkpaperContext(v)]));
 if(result.arguments&&typeof result.arguments==='object'&&'project_id' in result.arguments){
  delete result.arguments.project_id;
  if(typeof result.call==='string'&&result.call.startsWith('financial_workpaper('))result.call='financial_workpaper('+JSON.stringify(result.arguments)+')';
 }
 return result;
}
