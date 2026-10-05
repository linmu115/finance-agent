import {type ExtensionFactory} from '@earendil-works/pi-coding-agent';
import {DEFAULT_CONTEXT_COMPACTION,type ContextCompactionSettings} from './types.js';

export type ContextCompactionPolicy=ContextCompactionSettings;
export {DEFAULT_CONTEXT_COMPACTION};
export interface ResolvedCompactionPolicy extends ContextCompactionPolicy {reserveTokens:number}
export function resolveCompactionPolicy(input:Partial<ContextCompactionPolicy>|undefined,contextWindow:number,maxOutputTokens:number):ResolvedCompactionPolicy{
 // Legacy defaults migrate to model-aware pressure. Explicit custom thresholds stay manual.
 const legacyDefault=!input||input.targetTokens===96000&&input.keepRecentTokens===24000;
 const policy={...DEFAULT_CONTEXT_COMPACTION,...input,mode:input?.mode||(legacyDefault?'auto':'manual')} as ContextCompactionPolicy;
 const capacity=contextWindow-maxOutputTokens-Math.min(65536,Math.floor(contextWindow/16));
 if(policy.enabled&&capacity<1024)throw new Error('上下文窗口需在最大输出之外为工作记忆保留至少 1024 tokens 及请求余量');
 const targetTokens=Math.max(1,Math.floor(Math.min(policy.mode==='auto'?contextWindow*.8:policy.targetTokens,capacity)));
 const recent=policy.mode==='auto'?Math.floor((contextWindow-maxOutputTokens)*.16):policy.keepRecentTokens;
 return {...policy,targetTokens,keepRecentTokens:Math.max(0,Math.min(recent,Math.floor(targetTokens/3))),reserveTokens:contextWindow-targetTokens};
}

// Only a domain hint: Pi owns preparation, summary requests, retry and persistence.
export const FINANCIAL_SUMMARY_HINT='金融工作补充：保留公司、期间、币种单位、合并/母公司/归母及重述口径；区分披露事实、计算结果、假设和缺项。保留任务进度、待核验项以及 document_id/source_id、页码/表格定位、artifact_id/revision_id。关键数值需连同单位、期间、口径、公式和来源保留。已入库批次可用 get_processing_checkpoint 核对，不因摘要遗漏而重做。不得把失败或未核验事项写成完成。';
export function createContextCompactionExtension(options:{audit:(type:string,data:any)=>Promise<unknown>;onState:(state:{reason:string}|undefined)=>void}):ExtensionFactory{
 return pi=>{
  pi.on('session_before_compact',async event=>{
   options.onState({reason:event.reason});
   await options.audit('compaction_started',{reason:event.reason,tokens_before:event.preparation.tokensBefore,settings:event.preparation.settings,native:true});
  });
  pi.on('session_compact',async event=>{
   options.onState(undefined);
   await options.audit('compaction_saved',{reason:event.reason,entry_id:event.compactionEntry.id,first_kept_entry_id:event.compactionEntry.firstKeptEntryId,tokens_before:event.compactionEntry.tokensBefore,native:true,fromExtension:event.fromExtension});
  });
  pi.on('session_compact_failed',async event=>{
   options.onState(undefined);
   await options.audit('compaction_failed',{reason:event.reason,aborted:event.aborted,error:event.errorMessage,native:true});
  });
 };
}
export function focusCompactionContext<T extends {messages:any[]}>(context:T):T{
 return {...context,messages:context.messages.map(message=>message.role==='user'?{...message,content:typeof message.content==='string'?message.content+'\n\n'+FINANCIAL_SUMMARY_HINT:[...message.content,{type:'text',text:FINANCIAL_SUMMARY_HINT}]}:message)};
}
