import { useState } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { FileText, Copy, Check, Download, ExternalLink, Table2, CircleAlert } from 'lucide-react';
import { safeArtifactUrl, api, errorText } from './api';
import Modal from './Modal';
import { AnnotationRail } from './Annotations';
import type { Message, Source, Artifact, Document, ToolEvent } from './types';

export function docStatus(status: string) {
  return ({ registered: '已附加 · 发送后处理', uploaded: '已附加 · 发送后处理', queued: '等待处理', parsing: '正在解析', processing: '正在处理', normalizing: '模型正在清洗', validating: '正在入库', indexed: '已建立索引', sources_ready: '已建立原文索引', cancelled: '已停止', ready: '已入库', needs_review: '已入库 · 部分待处理', failed: '解析失败', error: '解析失败' } as Record<string, string>)[status] || status || '等待解析';
}
export function FileChip({ document, onClick, onRemove }: { document: Document; onClick: () => void; onRemove?: () => void }) {
  return <div className="file-chip"><button className="file-chip-main" onClick={onClick}><FileText /><span className="file-chip-text"><b>{document.name}</b><small>{docStatus(document.status)}{document.pageCount ? ` · ${document.pageCount} 页` : ''}</small></span></button>{onRemove && <button className="icon-btn remove-file" aria-label={`移除附件 ${document.name}`} onClick={onRemove}>×</button>}</div>;
}
function tableCell(value: unknown): string {
  if (value == null) return '—';
  if (typeof value === 'object') return JSON.stringify(value);
  return String(value);
}
export function DataTable({ columns, rows }: { columns: string[]; rows: unknown[][] }) {
  return <div className="table-scroll"><table><thead><tr>{columns.map((column, index) => <th key={index}>{column}</th>)}</tr></thead><tbody>{rows.map((row, index) => <tr key={index}>{row.map((cell, cellIndex) => <td key={cellIndex}>{tableCell(cell)}</td>)}</tr>)}</tbody></table></div>;
}
function ArtifactView({ artifact }: { artifact: Artifact }) {
  const url = safeArtifactUrl(artifact.url);
  const image = artifact.mimeType?.startsWith('image/') || artifact.type === 'image' || /\.png$/i.test(artifact.name);
  const table = artifact.columns && artifact.rows;
  return <div className="artifact-card">{image && url && <a href={url} target="_blank" rel="noreferrer"><img className="artifact-image" src={url} alt={artifact.name || '分析图表'} loading="lazy" /></a>}{table && <DataTable columns={artifact.columns!} rows={artifact.rows!.slice(0, 100)} />}<div className="artifact-footer"><span><Table2 />{artifact.name || '分析产物'}</span>{url ? <a href={url} download={artifact.name} className="text-button"><Download />下载</a> : <span className="muted">暂无下载地址</span>}</div></div>;
}
export function ToolTrace({ tools }: { tools: ToolEvent[] }) {
  if (!tools.length) return null;
  const calls = new Map<string, ToolEvent>();
  tools.forEach((tool, index) => { const prior = tool.status === 'progress' ? [...calls.entries()].reverse().find(([, item]) => item.name === tool.name && ['started', 'running', 'progress'].includes(item.status))?.[0] : undefined; calls.set(tool.toolCallId || prior || (tool.status === 'progress' ? `progress-${tool.name}` : `event-${index}`), tool); });
  const toolNames: Record<string, string> = { prepare_document_sources: '建立原文索引', process_documents: '清洗财报并入库', get_data_catalog: '查看项目数据目录', get_document_index: '查看文档索引', query_financial_data: '查询财务数据', get_normalization_details: '查看清洗记录', list_documents: '读取附件清单', get_document: '读取文档信息', search_evidence: '检索财报原文', get_source_page: '读取原文页面', get_source_table: '读取原始表格', get_financial_metrics: '查询财务指标', calculate_financial_metrics: '计算财务指标', run_analysis: '统计分析与制图', get_analysis_status: '查看分析进度', get_artifact: '读取图表与文件', search_web: '搜索公开资料', fetch_research_source: '读取并保存网络原文', read_research_source: '读取来源快照', list_research_sources: '查看研究来源', get_research_model_schema: '查看金融模型输入', run_financial_model: '计算金融模型', get_research_report_schema: '查看研究成果结构', save_research_report: '保存研究成果', list_research_artifacts: '查看项目研究成果', read_research_artifact: '读取成果和依赖' };
  const entries = [...calls.values()];
  return <details className="trace"><summary>工具执行记录 · {entries.length} 次调用</summary><ol>{entries.map((tool, index) => <li key={index}><b title={tool.name}>{toolNames[tool.name] || tool.name}</b><span className={tool.status === 'error' || tool.status === 'failed' ? 'error-text' : ''}>{({ started: '执行中', running: '执行中', progress: '处理中', completed: '完成', done: '完成', success: '完成', error: '失败', failed: '失败' } as Record<string, string>)[tool.status] || tool.status}</span>{tool.summary && <p>{tool.summary}</p>}</li>)}</ol></details>;
}
export default function MessageView({ message, documents, onDocument, onSource, onToast }: { message: Message; documents: Document[]; onDocument: (doc: Document) => void; onSource: (source: Source) => void; onToast: (text: string) => void }) {
  const [copied, setCopied] = useState(false);
  const [webSource,setWebSource]=useState<any>();
  const [sourceError,setSourceError]=useState('');
  async function openSource(source:Source){
    if(!source.url){onSource(source);return;}
    setSourceError('');setWebSource({title:source.title||'来源',url:source.url,loading:true});
    try{const url=safeArtifactUrl(source.snapshotUrl);if(!url)throw new Error('此来源没有可读取的本地快照');setWebSource(await api(url));}catch(error){setSourceError(errorText(error));}
  }
  const files = message.attachments ? message.attachments.map(item => typeof item === 'string' ? documents.find(doc => doc.id === item) || { id: item, name: '项目附件', status: '已附加' } : item) : documents.filter(doc => message.documentIds?.includes(doc.id));
  async function copy() {
    try { await navigator.clipboard.writeText(message.content); setCopied(true); window.setTimeout(() => setCopied(false), 1800); }
    catch { onToast('复制失败，请选中文字后复制，或下载对话。'); }
  }
  if (message.role === 'system') return null;
  return <article className={`message ${message.role}`} data-message-id={message.id} data-status={message.status || 'saved'} aria-label={message.role === 'user' ? '你的消息' : '金融研究的回复'}>
    {message.role === 'user' ? <>{files.length > 0 && <div className="user-files">{files.map(doc => <FileChip key={doc.id} document={doc} onClick={() => onDocument(doc)} />)}</div>}<div className="user-bubble">{message.content || '请解析附件。'}</div>{message.annotations?.length ? <AnnotationRail items={message.annotations} sent /> : null}</> : <>
      <div className="assistant-header"><span className="assistant-mark">研</span>金融研究</div>
      <div className="markdown"><ReactMarkdown remarkPlugins={[remarkGfm]} components={{
        table: ({ children }) => <div className="table-scroll"><table>{children}</table></div>,
        a: ({ href, children }) => <a href={href} target={href?.startsWith('#') ? undefined : '_blank'} rel="noreferrer">{children}<ExternalLink className="inline-icon" /></a>,
        img: ({ src, alt }) => { const url = safeArtifactUrl(typeof src === 'string' ? src : undefined); return url ? <img src={url} alt={alt || '分析图表'} loading="lazy" /> : <span className="muted">[图片：{alt || '外部图片不自动加载'}]</span>; },
      }}>{message.content}</ReactMarkdown></div>
      {message.status === 'failed' && <div className="message-error"><CircleAlert />本次分析未完成。请检查服务配置或错误信息后重试。</div>}
      {message.status === 'cancelled' && <p className="muted">已停止生成；以上是停止前的内容。</p>}
      {message.sources && message.sources.length > 0 && <div className="sources-row"><span>来源</span>{message.sources.map((source, index) => <button className="source-pill" key={`${source.sourceId || source.id || index}:${source.tableId || ""}:${index}`} onClick={() => void openSource(source)}><FileText />{index + 1}. {source.name || source.title || documents.find(doc => doc.id === (source.documentId || source.document_id))?.name || '原文'}{source.page || source.pageNumber ? ` · 第 ${source.page || source.pageNumber} 页` : ''}</button>)}</div>}
      {webSource&&<Modal className="settings-dialog" label="保存的来源原文" onClose={()=>setWebSource(undefined)}><div style={{padding:24,maxHeight:'80vh',overflow:'auto'}}><button className="plain-button" onClick={()=>setWebSource(undefined)}>关闭</button><h2>{webSource.title}</h2><p><a href={webSource.url} target="_blank" rel="noreferrer">打开原网址 <ExternalLink className="inline-icon"/></a></p><p className="muted">发布：{webSource.published_at||'原网页未明确标注'} · 获取：{webSource.retrieved_at||'—'}</p>{webSource.content_representation==='provider_extracted_text'&&<p className="muted">搜索服务提取的正文快照 · 可离线复查，未保存原始网页文件</p>}{sourceError?<p className="error-text">{sourceError}</p>:webSource.loading?<p>读取快照…</p>:webSource.paragraphs?.map((p:any)=><p key={p.id}><small className="muted">[{p.id}] </small>{p.text}</p>)}</div></Modal>}
      {message.artifacts?.map(artifact => <ArtifactView key={artifact.id || artifact.name} artifact={artifact} />)}
      {message.tools && <ToolTrace tools={message.tools} />}
      {message.content && <div className="message-actions"><button className="icon-btn" aria-label="复制回复" title="复制回复" onClick={() => void copy()}>{copied ? <Check /> : <Copy />}</button>{message.createdAt && <time dateTime={message.createdAt}>{new Date(message.createdAt).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })}</time>}</div>}
    </>}
  </article>;
}
