import type {LlmConfig} from './types.js';

export interface UsageTotals {
 input:number; output:number; calls:number; costUsd:number|null;
 uncachedInput?:number; cacheRead?:number; cacheWrite?:number; reasoning?:number;
 unknownCalls?:number; cacheUnknownCalls?:number; costUnknownCalls?:number; cacheKnownInput?:number;
 costCnyMin?:number; costCnyMax?:number; priceSource?:string;
 phases?:Record<string,UsageTotals>;
}
export const emptyUsage=():UsageTotals=>({input:0,output:0,calls:0,costUsd:null,uncachedInput:0,cacheRead:0,cacheWrite:0,reasoning:0,unknownCalls:0,cacheUnknownCalls:0,costUnknownCalls:0,phases:{}});
const number=(value:unknown)=>typeof value==='number'&&Number.isFinite(value)&&value>=0?value:0;
export function addUsage(target:UsageTotals,raw:any,known:boolean,phase:string,config?:Partial<LlmConfig>){
 const entries=[target];if(target.phases)(entries.push(target.phases[phase]??=({...emptyUsage(),phases:undefined})));
 const miss=number(raw?.input),hit=number(raw?.cacheRead),write=number(raw?.cacheWrite),output=number(raw?.output);
 const cacheKnown=known&&typeof raw?.cacheRead==='number';
 const manual=write===0&&config?.inputPricePerMillionUsd!==undefined&&config?.outputPricePerMillionUsd!==undefined&&(!hit||config?.cacheReadPricePerMillionUsd!==undefined);
 const catalog=number(raw?.cost?.total);
 const cost=known?(manual?(miss*config!.inputPricePerMillionUsd!+hit*(config!.cacheReadPricePerMillionUsd??0)+output*config!.outputPricePerMillionUsd!)/1e6:catalog>0?catalog:null):null;
 let officialFlash=false;try{officialFlash=!manual&&new URL(config?.baseUrl||'').hostname==='api.deepseek.com'&&config?.model==='deepseek-flash';}catch{}
 for(const t of entries){
  t.calls++;t.input+=miss+hit+write;t.output+=output;
  t.uncachedInput=(t.uncachedInput||0)+miss;t.cacheRead=(t.cacheRead||0)+hit;t.cacheWrite=(t.cacheWrite||0)+write;
  t.reasoning=(t.reasoning||0)+number(raw?.reasoning);
  t.cacheKnownInput=(t.cacheKnownInput||0)+(cacheKnown?miss+hit+write:0);
  t.unknownCalls=(t.unknownCalls||0)+(known?0:1);t.cacheUnknownCalls=(t.cacheUnknownCalls||0)+(cacheKnown?0:1);
  t.costUnknownCalls=(t.costUnknownCalls||0)+(cost===null&&!(officialFlash&&known)?1:0);
  if(cost!==null)t.costUsd=(t.costUsd??0)+cost;
  if(officialFlash&&known){
   // A tariff range avoids guessing Chinese holidays, billing currency or account discounts.
   const low=(miss+hit*.02+output*4)/1e6;
   t.costCnyMin=(t.costCnyMin||0)+low;t.costCnyMax=(t.costCnyMax||0)+low*2;
   t.priceSource='DeepSeek Flash 官方空闲至高峰标价区间（2026-10-05）；非账单，不含联网费';
  }else if(cost!==null)t.priceSource=manual?'自定义分项价格估算；非账单':'Pi 模型目录标价估算；非账单，未扣时段优惠';
 }
}
export function aggregateAudit(rows:any[],config?:Partial<LlmConfig>){
 const totals=emptyUsage(),seen=new Set<string>();
 for(const row of rows){if(row.type!=='model_usage')continue;const d=row.data;if(!d?.requestId||seen.has(d.requestId))continue;seen.add(d.requestId);addUsage(totals,d.usage,d.usageKnown!==false,d.usagePhase||d.phase||'main',config);}
 return totals;
}
