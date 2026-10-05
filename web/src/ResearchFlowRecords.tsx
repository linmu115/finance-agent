import type {Source} from './types';
const kinds:Record<string,string>={quoted_actual:'研报引用实际值',analyst_forecast:'机构预测',industry_statistic:'行业统计',company_guidance:'公司指引',assumption:'假设',unclassified:'类型待核验',opinion:'研究观点',risk:'风险',catalyst:'催化因素'};
const scopes:Record<string,string>={unspecified:'口径未注明',consolidated_CAS:'合并 · 中国准则',parent_CAS:'母公司 · 中国准则',consolidated_IFRS:'合并 · 国际准则',parent_IFRS:'母公司 · 国际准则'};
const checks:Record<string,string>={unstandardized_unit:'原单位尚未标准化',unresolved_period:'期间待确认',unresolved_currency:'币种待确认',cross_market_currency_requires_confirmation:'跨市场数据的币种待确认',unclassified_data_kind:'资料类型待确认',price_eps_pe_requires_reconciliation:'股价、EPS 与 PE 需核对基准日及口径'};
export default function ResearchFlowRecords({items,onSource}:{items:any[];onSource:(source:Source)=>void}){
 if(!items?.length)return null;
 return <section aria-label="研报提取记录">
  <h3>预测、行业数据与观点</h3><p className="muted">本次处理的来源快照。机构预测按报告署期保留版本，原文摘录与模型归纳分别展示。</p>
  {items.map(r=><div className="flow-fact" key={r.record_id}>
   <b>{r.entity?.name} · {r.label||kinds[r.data_kind]||r.data_kind}</b>
   <p>{kinds[r.data_kind]||r.data_kind} · {r.publisher||'归属机构未知'} · {r.published_at||'发布日期未知'}</p>
   {r.record_type==='observation'?<>
    <p>{r.period==='unknown'?r.source?.normalization?.period_label||'期间待确认':r.period} · {scopes[r.scope]||r.scope} · {r.currency==='unknown'?'保留原单位':r.currency}{r.scenario!=='unspecified'?' · '+r.scenario:''}</p>
    <p>原值：{r.raw_value} {r.raw_unit} → 入库值：<strong>{r.value}</strong></p>
   </>:<>
    <p>{r.text}</p><blockquote>{r.source?.quote}</blockquote>
    <small>{r.attribution?.kind==='quoted'?`报告引用：${r.attribution.speaker||r.attribution.institution||'归属待核验'}`:r.attribution?.kind==='unknown'?'观点归属待核验':'报告作者观点'}</small>
   </>}
   {r.quality==='needs_review'&&<p className="field-note">待核验：{(r.source?.normalization?.review_warnings||[]).map((c:string)=>checks[c]||c).join('；')||'详见本次处理记录及原文。'}</p>}
   <div className="flow-actions"><button className="plain-button" onClick={()=>onSource({...r.source,documentId:r.document_id})}>核对原文</button></div>
  </div>)}
 </section>;
}
