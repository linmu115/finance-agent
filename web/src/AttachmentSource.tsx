import { useEffect, useState } from 'react';
import { ArrowLeft, ChevronLeft, ChevronRight, Download, FileText } from 'lucide-react';
import { api, errorText, safeArtifactUrl } from './api';
import { DataTable } from './MessageView';
import type { Document, Source } from './types';

/** Original content is a detail view inside AttachmentFlow, never a project file browser. */
export default function AttachmentSource({ projectId, source, onBack }: { projectId: string; source: Source; onBack: () => void }) {
 const documentId = source.documentId || source.document_id || (source.sourceId?.includes(':p') ? source.sourceId.split(':p')[0] : undefined);
 const [detail, setDetail] = useState<Document>(), [tables, setTables] = useState<any[]>([]);
 const [tab, setTab] = useState<'original'|'tables'>('original');
 const [page, setPage] = useState(source.page || source.pageNumber || 1);
 const [text, setText] = useState(''), [imageUrl, setImageUrl] = useState<string>(), [error, setError] = useState('');
 const [loading, setLoading] = useState(false);
 useEffect(() => { setPage(source.page || source.pageNumber || 1); setTab('original'); }, [source]);
 useEffect(() => {
  setDetail(undefined); setTables([]); setError('');
  if (!documentId) return;
  const c = new AbortController(), root = `/api/projects/${projectId}/documents/${documentId}`;
  Promise.all([api<Document>(root, { signal: c.signal }), api<{ items?: any[] }>(root + '/tables', { signal: c.signal })]).then(([d, t]) => { if (!c.signal.aborted) { setDetail(d); setTables(t.items || []); } }).catch(e => { if (!c.signal.aborted) setError(errorText(e)); });
  return () => c.abort();
 }, [projectId, documentId]);
 useEffect(() => {
  setText(''); setImageUrl(undefined);
  if (!documentId || tab !== 'original') return;
  const c = new AbortController(); setLoading(true); setError('');
  api<{ text?: string; imageUrl?: string; page?: { text?: string } }>(`/api/projects/${projectId}/documents/${documentId}/pages/${page}`, { signal: c.signal }).then(r => { if (!c.signal.aborted) { setText(r.text || r.page?.text || '此页没有可提取的文本，请查看原件。'); setImageUrl(safeArtifactUrl(r.imageUrl)); } }).catch(e => { if (!c.signal.aborted) setError(errorText(e)); }).finally(() => { if (!c.signal.aborted) setLoading(false); });
  return () => c.abort();
 }, [projectId, documentId, page, tab]);
 const url = documentId ? `/api/projects/${projectId}/documents/${documentId}/file` : undefined;
 return <div className="attachment-source"><button className="text-button" onClick={onBack}><ArrowLeft />返回附件流向</button><h3>{detail?.name || source.name || source.title || '附件原文'}</h3>
  <div className="flow-actions">{url && <><a className="plain-button" href={url} download={detail?.name}><Download />下载原件</a><a className="plain-button" href={`${url}#page=${page}`} target="_blank" rel="noreferrer"><FileText />打开原始文档</a></>}</div>
  {(source.quote || source.text) && <blockquote>{source.quote || source.text}<small>{source.sheet}{source.cell ? ` · ${source.cell}` : ''}{source.row ? ` · 第 ${source.row} 行` : ''}</small></blockquote>}
  <nav className="flow-source-tabs" aria-label="原文与提取信息"><button aria-pressed={tab === 'original'} onClick={() => setTab('original')}>原文</button><button aria-pressed={tab === 'tables'} onClick={() => setTab('tables')}>提取表格 · {tables.length}</button></nav>
  {error && <p className="error-text" role="alert">{error}</p>}
  {tab === 'original' ? <><div className="page-controls"><button className="icon-btn" aria-label="上一页" disabled={page <= 1 || loading} onClick={() => setPage(p => p - 1)}><ChevronLeft /></button><span>第 {page} 页{detail?.pageCount ? ` / ${detail.pageCount}` : ''}</span><button className="icon-btn" aria-label="下一页" disabled={loading || !detail?.pageCount || page >= detail.pageCount} onClick={() => setPage(p => p + 1)}><ChevronRight /></button></div>{imageUrl && <a href={imageUrl} target="_blank" rel="noreferrer"><img className="doc-img" src={imageUrl} alt={`第 ${page} 页原文`} /></a>}<pre className="page-text">{loading ? '正在读取原文…' : text}</pre></> : tables.length ? tables.map((t, i) => { const rows = t.preview || t.rows || []; return <section key={t.table_id || i}><h4>{t.sheet || `来源表 ${i + 1}`}</h4><p className="muted">{t.row_count ?? rows.length} 行 · 预览前 {Math.min(rows.length, 10)} 行</p><DataTable columns={(rows[0] || []).map(String)} rows={rows.slice(1, 10)} /></section>; }) : <p className="muted">这份附件暂没有提取表格。</p>}
 </div>;
}
