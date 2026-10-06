import {useEffect, useState} from 'react';
import {FileText, MessageSquare} from 'lucide-react';
import {api, errorText, isAbort} from './api';
import type {Source} from './types';
import './evidence-review.css';

export type ReviewSummary = {pages_preserved:number;tables_preserved:number;tables_with_decisions:number;pages_with_decisions:number;review_items:number;extraction_issues:number;page_issues:number;facts_needing_review:number;records_needing_review:number};
type ReviewItem = {kind:string;message:string;label?:string;value?:string;raw_value?:string;raw_unit?:string;data_kind?:string;source:{document_id:string;page?:number;table_id?:string;row?:number;column?:number};fact_id?:string;record_id?:string};
type ReviewData = {summary:ReviewSummary;items:ReviewItem[];total:number;next_offset:number|null};
const reasons:Record<string,string> = {semantic_review_pending:'复杂内容尚未可靠提取',unresolved_period:'期间待确认',unresolved_currency:'币种待确认',unstandardized_unit:'原单位尚未标准化',unclassified_data_kind:'实际值或预测身份待确认',price_eps_pe_requires_reconciliation:'股价、每股收益与市盈率需对照核验',cross_market_currency_requires_confirmation:'跨市场币种需核对'};
const kinds:Record<string,string> = {extraction:'提取疑点',page:'正文疑点',fact:'披露数据',research_record:'研报记录'};
export const reviewMessage = (message:string) => message.split('；').map(part=>reasons[part]||part).join('；');

export default function EvidenceReview({projectId,documentId,title,summary,refreshToken,onSource,onChat}:{projectId:string;documentId:string;title:string;summary?:ReviewSummary;refreshToken?:number;onSource:(source:Source)=>void;onChat:(prompt:string)=>void}) {
  const [open,setOpen]=useState(false),[offset,setOffset]=useState(0),[query,setQuery]=useState(''),[data,setData]=useState<ReviewData>(),[error,setError]=useState(''),[loading,setLoading]=useState(false);
  useEffect(()=>{
    if(!open)return;
    const controller=new AbortController();setLoading(true);setError('');
    api<ReviewData>(`/api/projects/${encodeURIComponent(projectId)}/documents/${encodeURIComponent(documentId)}/normalization?review_only=true&offset=${offset}&limit=10&query=${encodeURIComponent(query)}`,{signal:controller.signal})
      .then(result=>{
        if(!result?.summary||!Array.isArray(result.items))throw new Error('服务尚未加载新的核验功能，请重启当前服务后重试。');
        setData(result);setLoading(false);
      }).catch(reason=>{if(!isAbort(reason)){setData(undefined);setError(errorText(reason));setLoading(false);}});
    return()=>controller.abort();
  },[open,projectId,documentId,offset,query,summary?.review_items,refreshToken]);
  return <details className="evidence-review" onToggle={event=>setOpen(event.currentTarget.open)}>
    <summary>信息保留与待核验项{summary?` · ${summary.review_items} 条线索`:''}</summary>
    {open&&<>
      {summary&&<p>原文 {summary.pages_preserved} 页、原表 {summary.tables_preserved} 张已保留。疑点只影响相关数据的采用，不阻止其他分析。</p>}
      {summary&&summary.review_items>0&&<p>同一处内容可能同时有提取意见和记录疑点；线索条数不是错误数，也不代表准确率。</p>}
      <label>查找疑点<input aria-label={`查找 ${title} 的疑点`} placeholder="期间、单位、指标或原因" value={query} onChange={e=>{setQuery(e.target.value);setOffset(0);}}/></label>
      {error&&<p role="alert">{error}</p>}
      {loading?<p aria-live="polite">正在读取…</p>:data?.items.map((item,index)=><article key={`${offset}-${index}`}>
        <div className="evidence-review-label"><strong>{item.label||kinds[item.kind]||'待核验信息'}</strong>{item.source.page&&<span>第 {item.source.page} 页{item.source.row?` · 第 ${item.source.row} 行`:''}</span>}</div>
        <p>{reviewMessage(item.message)}</p>
        {item.raw_value!=null&&<p>原值：{item.raw_value} {item.raw_unit||''}{item.value!=null?`；候选值：${item.value}`:''}</p>}
        <div className="asset-row-actions">
          <button className="text-button" disabled={!item.source.page} onClick={()=>onSource({...item.source,tableId:item.source.table_id,documentId,title})}><FileText/>核对原文</button>
          <button className="text-button" onClick={()=>onChat('请先结合我的问题判断下列疑点是否影响所需数据；只对相关单位、期间或口径做局部核验，原值与未决信息继续保留。无法确认的部分明确作为假设或说明限制，其他分析继续。\n\n'+JSON.stringify({document:title,...item},null,2)+'\n\n我的问题：')}><MessageSquare/>带入会话</button>
        </div>
      </article>)}
      {!loading&&data&&!data.total&&<p>{query?'没有匹配的疑点。':'当前没有已登记的待核验项；这不代表全文内容已逐项验证。'}</p>}
      {data&&<div className="evidence-review-pagination"><span>{data.total} 条线索</span><button className="text-button" disabled={loading||!offset} onClick={()=>setOffset(Math.max(0,offset-10))}>上一页</button><button className="text-button" disabled={loading||data.next_offset==null} onClick={()=>setOffset(data.next_offset!)}>下一页</button></div>}
    </>}
  </details>;
}
