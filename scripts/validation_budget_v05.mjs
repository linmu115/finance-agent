// Independent accounting. Total public run usage includes bridge calls; never
// add that total to bridge usage again. Main Pi is the reconciled difference.
export const tokenUsage=u=>({input:Number(u?.input||0)+Number(u?.cacheRead||0)+Number(u?.cacheWrite||0),output:Number(u?.output||0)});
const add=(a,b)=>{a.calls+=b.calls||0;a.input+=b.input||0;a.output+=b.output||0;a.duration_ms+=b.duration_ms||0;};
function phase(request){
 const text=JSON.stringify(request?.messages||[]);
 if(text.includes('[[DEFINITION:'))return 'definition';
 if(text.includes('[[SOURCE:'))return 'temporal_correction';
 if(text.includes('[[GROUP:'))return 'temporal_profile';
 if(text.includes('[[CATALOG]]'))return 'catalog';
 return 'cleaning';
}
export function summarizeBudget(runs,eventMap,elapsedSeconds,budget){
 const total={calls:0,input:0,output:0,duration_ms:0},bridge={calls:0,input:0,output:0,duration_ms:0},phases={},errors=[],failed=[];let pending=0;
 for(const run of runs){
  add(total,{calls:Number(run.usage?.calls||0),input:Number(run.usage?.input||0),output:Number(run.usage?.output||0)});
  const events=eventMap[run.id]||[],requests=new Map(events.filter(e=>e.type==='extraction_request').map(e=>[e.data.requestId,e.data]));
  const seen=new Set();
  for(const event of events.filter(e=>e.type==='extraction_result')){
   const result=event.data;if(seen.has(result.requestId)){errors.push('duplicate_result:'+result.requestId);continue;}seen.add(result.requestId);
   const request=requests.get(result.requestId);if(!request){errors.push('result_without_request:'+result.requestId);continue;}
   const name=phase(request),u={calls:1,...tokenUsage(result.usage),duration_ms:Number(result.durationMs||0)};
   phases[name]??={calls:0,input:0,output:0,duration_ms:0};add(phases[name],u);add(bridge,u);
   if(!result.usage)errors.push('missing_usage:'+result.requestId);
   if(!['stop','toolUse'].includes(result.stopReason))failed.push({run_id:run.id,request_id:result.requestId,phase:name,stop_reason:result.stopReason,at:event.at,usage:u});
  }
  pending+=requests.size-seen.size;
 }
 const main={calls:total.calls-bridge.calls,input:total.input-bridge.input,output:total.output-bridge.output,duration_ms:null,source:'Public aggregate usage minus individually audited bridge results; no double count'};
 if(main.calls<0||main.input<0||main.output<0)errors.push('public_total_less_than_bridge_usage');
 const actual={model_calls:total.calls,input_tokens:total.input,output_tokens:total.output,total_tokens:total.input+total.output,wall_seconds:elapsedSeconds};
 const limits={model_calls:budget.max_model_calls,input_tokens:budget.max_input_tokens,output_tokens:budget.max_output_tokens,total_tokens:budget.max_total_tokens,wall_seconds:budget.max_wall_seconds};
 const reached=Object.keys(limits).filter(key=>actual[key]>=limits[key]).map(key=>({metric:key,limit:limits[key],actual:actual[key],overrun:Math.max(0,actual[key]-limits[key])})),exceeded=reached.filter(v=>v.overrun>0);
 return {actual,limits,cap_reached:reached.length>0,limits_reached:reached,exceeded,main_pi:main,bridge_total:bridge,bridge_phases:phases,pending_bridge_requests:pending,failed_calls:failed,errors,accounting_valid:!errors.length,enforcement:'Observed usage polling; already in-flight requests may overshoot',duration_note:'Bridge phase durations sum model request durations and may overlap; wall_seconds is end-to-end arm duration.'};
}
