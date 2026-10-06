import {useEffect, useState} from 'react';
import {FileText, RefreshCw, Search, Trash2, ExternalLink} from 'lucide-react';
import {api,errorText,isAbort} from './api';
import type {Source} from './types';
import './attachment-dashboard.css';

type Attachment={id:string;name:string;status:string;createdAt?:string;pageCount?:number;factCount?:number;researchRecordCount?:number;profile?:{kind?:string;publisher?:string;published_at?:string}};
const kinds:Record<string,string>={financial_report:'财报',broker_research:'公司研报',industry_research:'行业研报',mixed:'综合资料',other:'其他资料'};
const states:Record<string,string>={registered:'待处理',uploaded:'待处理',sources_ready:'原文已解析',queued:'排队中',parsing:'解析中',normalizing:'入库中',ready:'已入库',completed:'已完成',needs_review:'有待核验项',failed:'处理失败',cancelled:'已停止'};
export default function AttachmentDashboard({projectId,projectName,onSource,onDeleted}:{projectId:string;projectName?:string;onSource:(source:Source)=>void;onDeleted:(id:string)=>void}){
 const [items,setItems]=useState<Attachment[]>([]),[query,setQuery]=useState(''),[revision,setRevision]=useState(0);
 const [loading,setLoading]=useState(false),[error,setError]=useState(''),[notice,setNotice]=useState('');
 const [confirm,setConfirm]=useState<string>(),[deleting,setDeleting]=useState<string>();
 useEffect(()=>{
  if(!projectId){setItems([]);return;}
  const controller=new AbortController();setLoading(true);setError('');
  api<{documents:Attachment[]}>(`/api/projects/${encodeURIComponent(projectId)}/documents`,{signal:controller.signal})
   .then(result=>{setItems(result.documents);setLoading(false);})
   .catch(e=>{if(!isAbort(e)){setError(errorText(e));setLoading(false);}});
  return ()=>controller.abort();
 },[projectId,revision]);
 async function remove(item:Attachment){
  setDeleting(item.id);setError('');
  try{
   await api(`/api/projects/${encodeURIComponent(projectId)}/documents/${encodeURIComponent(item.id)}`,{method:'DELETE',body:JSON.stringify({confirm_document_id:item.id})});
   setItems(previous=>previous.filter(d=>d.id!==item.id));setConfirm(undefined);setNotice(`已删除「${item.name}」及其入库数据。`);onDeleted(item.id);
  }catch(e){setError(errorText(e));}finally{setDeleting(undefined);}
 }
 const filtered=items.filter(d=>`${d.name} ${d.profile?.publisher||''} ${kinds[d.profile?.kind||'']||''}`.toLowerCase().includes(query.toLowerCase()));
 return <main className="attachment-dashboard">
  <header className="attachment-heading"><div><p>{projectName||'当前项目'}</p><h1>附件看板</h1><span>按资料查看登记与入库情况，管理财报和研报。</span></div><button className="secondary-button" disabled={loading||!!deleting} onClick={()=>setRevision(v=>v+1)}><RefreshCw size={16} className={loading?'spin':''}/>刷新</button></header>
  <div className="attachment-toolbar"><label><Search size={17}/><input aria-label="搜索附件" placeholder="搜索文件名、机构或资料类型" value={query} onChange={e=>setQuery(e.target.value)}/></label><span>{items.length} 份已登记资料</span></div>
  {error&&<p className="error-banner" role="alert">{error}</p>}{notice&&<p className="attachment-notice" role="status">{notice}</p>}
  {!projectId?<p className="attachment-empty">先选择一个项目。</p>:loading?<p className="attachment-empty">正在读取资料…</p>:!filtered.length?<p className="attachment-empty">{items.length?'没有匹配的资料。':'此项目尚未登记附件。在会话中添加财报或研报后，会在这里列出。'}</p>:<div className="attachment-list">
   <div className="attachment-columns" aria-hidden="true"><span>资料</span><span>状态与入库数据</span><span>操作</span></div>
   {filtered.map(item=><article className="attachment-row" key={item.id} aria-label={item.name}>
    <div className="attachment-file"><FileText/><div><strong>{item.name}</strong><p>{kinds[item.profile?.kind||'']||'类型待确认'}{item.pageCount?` · ${item.pageCount} 页`:''}{item.profile?.publisher?` · ${item.profile.publisher}`:''}</p><small>{item.profile?.published_at?`报告日期 ${item.profile.published_at} · `:''}{item.createdAt?`登记于 ${new Date(item.createdAt).toLocaleDateString('zh-CN')}`:''}</small></div></div>
    <div className="attachment-counts"><span>{states[item.status]||item.status}</span><small>财务事实 {item.factCount||0} · 研报记录 {item.researchRecordCount||0}</small></div>
    <div className="attachment-actions"><button className="secondary-button" onClick={()=>onSource({documentId:item.id,page:1,title:item.name})}><ExternalLink size={15}/>原文</button><button className="attachment-delete" disabled={!!deleting} onClick={()=>{setConfirm(item.id);setError('');setNotice('');}}><Trash2 size={15}/>删除</button></div>
    {confirm===item.id&&<div className="attachment-confirm" role="alertdialog" aria-label={`删除 ${item.name}`}><strong>删除这份资料及全部入库数据？</strong><p>将清除原文解析、财务事实、研报预测与观点、历史提取和附件流向记录，以及相关处理产物。历史会话文字和已有备份保留；引用该资料的已保存模型会显示来源缺失。此操作不能在看板中撤销。</p><div><button className="secondary-button" disabled={!!deleting} onClick={()=>setConfirm(undefined)}>取消</button><button className="attachment-delete solid" disabled={!!deleting} onClick={()=>void remove(item)}>{deleting===item.id?'正在删除…':'确认删除'}</button></div></div>}
   </article>)}
  </div>}
 </main>;
}
