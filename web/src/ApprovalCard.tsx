import { useEffect, useRef, useState } from 'react';
import { ShieldCheck, ChevronRight } from 'lucide-react';
import { api, errorText } from './api';
import './conversation-tools.css';

interface Approval { id: string; digest: string; conversationId: string; operation: Record<string, any> }
const labels: Record<string, string> = { sql: '执行 SQL', update_fact: '修改财务数值', delete_fact: '删除财务记录', delete_document: '删除资料及其数据', read_other_project: '读取其他项目', analysis_changes: '提交分析程序的数据库变更' };

function RequestCard({ item, count, onResolved }: { item: Approval; count: number; onResolved: (id: string) => void }) {
 const [busy, setBusy] = useState(false), [error, setError] = useState('');
 const lock = useRef(false), card = useRef<HTMLElement>(null);
 const op = item.operation;
 useEffect(() => {
  const active = document.activeElement;
  if (!active?.matches('input,textarea,[contenteditable="true"]') && !document.querySelector('dialog[open],.annotation-popover')) card.current?.focus();
 }, []);
 async function decide(allow: boolean) {
  if (lock.current) return;
  lock.current = true; setBusy(true); setError('');
  try {
   await api(`/api/approvals/${item.id}`, { method: 'POST', body: JSON.stringify({ digest: item.digest, allow }) });
   onResolved(item.id);
  } catch (e) { setError(errorText(e)); }
  finally { lock.current = false; setBusy(false); }
 }
 return <section className="approval-card" ref={card} tabIndex={0} role="region" aria-label="数据库操作授权" onKeyDown={e => {
  if (e.nativeEvent.isComposing || e.keyCode === 229 || e.repeat || e.ctrlKey || e.metaKey || e.altKey || e.shiftKey) return;
  if ((e.target as HTMLElement).matches('input,textarea,[contenteditable="true"]')) return;
  if (e.key === 'Escape') { e.preventDefault(); e.stopPropagation(); void decide(false); }
  if (e.key === 'Enter' && e.target === e.currentTarget) { e.preventDefault(); e.stopPropagation(); void decide(true); }
 }}>
  <header><ShieldCheck /><div><strong>{labels[op.operation] || '数据库操作'}需要授权</strong><small>{op.current_project}{count > 1 ? ` · 当前会话还有 ${count - 1} 项等待确认` : ' · 仅对本次操作生效'}</small></div></header>
  <p className="approval-reason">{op.reason}</p><p className="approval-scope"><b>作用范围</b>{op.scope}</p>
  <details><summary>查看具体操作与参数</summary><div className="approval-operation">
   {op.note && <p>{op.note}</p>}{op.sql && <pre>{op.sql}</pre>}
   {op.commands?.map((c: any, i: number) => <pre key={i}>{c.sql}{'\n参数：' + JSON.stringify(c.parameters || [])}</pre>)}
   {op.parameters && <pre>参数：{JSON.stringify(op.parameters)}</pre>}
   {Object.entries({ fact_id: '记录 ID', document_id: '资料 ID', value: '新值', analysis_run_id: '分析任务', artifact_sha256: '变更文件指纹' }).filter(([key]) => op[key] !== undefined).map(([key, label]) => <p key={key}><b>{label}：</b>{String(op[key])}</p>)}
  </div></details>
  {error && <p role="alert" className="error-text">{error}</p>}
  <footer><span>聚焦卡片后可用快捷键</span><button disabled={busy} className="plain-button" onKeyDown={e => { if (e.repeat && e.key === 'Enter') e.preventDefault(); }} onClick={() => void decide(false)}>拒绝 <kbd>Esc</kbd></button><button disabled={busy} className="primary-button" onKeyDown={e => { if ((e.repeat || e.nativeEvent.isComposing) && e.key === 'Enter') e.preventDefault(); }} onClick={() => void decide(true)}>{busy ? '正在提交…' : '同意本次'} <kbd>Enter</kbd></button></footer>
 </section>;
}

export default function ApprovalCard({ conversationId, onOpenConversation }: { conversationId?: string; onOpenConversation: (id: string) => void }) {
 const [requests, setRequests] = useState<Approval[]>([]);
 const resolved = useRef(new Set<string>());
 useEffect(() => {
  let stopped = false, timer: ReturnType<typeof setTimeout>;
  const controller = new AbortController();
  const load = async () => {
   try { const r = await api<{ requests: Approval[] }>('/api/approvals', { signal: controller.signal }); if (!stopped) setRequests(r.requests.filter(item => !resolved.current.has(item.id))); } catch { /* Existing application connection state remains available. */ }
   if (!stopped) timer = setTimeout(load, 1000);
  };
  void load(); return () => { stopped = true; clearTimeout(timer); controller.abort(); };
 }, []);
 const current = requests.filter(r => r.conversationId === conversationId);
 if (current[0]) return <RequestCard key={current[0].id} item={current[0]} count={current.length} onResolved={id => { resolved.current.add(id); setRequests(previous => previous.filter(r => r.id !== id)); }} />;
 if (requests.length) return <button className="approval-other" onClick={() => onOpenConversation(requests[0].conversationId)}><ShieldCheck />其他会话有 {requests.length} 项操作等待授权<ChevronRight /></button>;
 return null;
}
