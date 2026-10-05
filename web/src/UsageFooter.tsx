import type {UsageTotals} from './types';

const n=(v:number|undefined)=>Number(v||0).toLocaleString('zh-CN');
const labels:Record<string,string>={main:'主分析',cleaning:'脚本清洗',cleaning_review:'清洗核验',extraction:'清洗与复核',router:'任务路由',document_routing:'资料识别',research_extraction:'研报观点提取',compaction:'上下文整理'};
const price=(u:UsageTotals)=>u.costCnyMin!==undefined?`¥${u.costCnyMin.toFixed(3)}–${(u.costCnyMax??u.costCnyMin).toFixed(3)}`:u.costUsd!==null&&u.costUsd!==undefined?`$${u.costUsd.toFixed(4)}`:'未知';
export default function UsageFooter({usage:u}:{usage:UsageTotals}){
 const partial=!!u.unknownCalls||!!u.cacheUnknownCalls;
 const knownInput=u.cacheKnownInput??u.input;
 const rate=knownInput>0&&u.cacheRead!==undefined?(100*u.cacheRead/knownInput).toFixed(1)+'%':'未知';
 const cost=price(u);
 return <details className="usage-footer" aria-label="本次任务用量">
  <summary><span>{partial?'已知用量':'本次'} {n(u.input+u.output)} tokens</span><span>输入 {n(u.input)}</span><span>输出 {n(u.output)}</span><span>缓存命中 {u.cacheRead===undefined?'未知':n(u.cacheRead)}（{rate}{partial?'，已知部分':''}）</span><span className="usage-details-link">用量详情</span></summary>
  <div className="usage-detail"><p>{n(u.calls)} 次请求 · 未命中输入 {u.uncachedInput===undefined?'未知':n(u.uncachedInput)} · 输出中思考 {n(u.reasoning)}（已包含在输出内）</p>
   <p>费用估算 {cost}{u.unknownCalls||u.costUnknownCalls?'，仅已知部分':''} · {u.priceSource||'没有可核实的分项价格'}</p>
   {!!u.unknownCalls&&<p>{u.unknownCalls} 次请求未返回完整用量；实际消耗可能更高。</p>}
   {!!u.cacheUnknownCalls&&<p>{u.cacheUnknownCalls} 次请求的缓存情况未知，不作为未命中或零费用。</p>}
   {u.phases&&Object.keys(u.phases).length>0&&<div className="table-scroll"><table><thead><tr><th>阶段</th><th>请求</th><th>输入</th><th>命中输入</th><th>输出</th><th>其中思考</th><th>费用估算</th></tr></thead><tbody>{Object.entries(u.phases).map(([key,v])=><tr key={key}><td>{labels[key]||key}</td><td>{n(v.calls)}</td><td>{n(v.input)}</td><td>{n(v.cacheRead)}</td><td>{n(v.output)}</td><td>{n(v.reasoning)}</td><td>{price(v)}</td></tr>)}</tbody></table></div>}
   <p>按本次任务累计，含内部模型调用与重试；命中比例按输入 token 加权计算。阶段按请求所处的处理阶段归类。</p>
  </div>
 </details>;
}
