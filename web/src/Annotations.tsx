import { createContext, useContext, useEffect, useLayoutEffect, useMemo, useRef, useState, type ReactNode, type RefObject } from 'react';
import { createPortal } from 'react-dom';
import { Quote, X, ArrowUpRight, Pencil, Trash2, Check, Plus, MessageSquarePlus } from 'lucide-react';
import type { Annotation, Message } from './types';
import { clearHighlights, indexText, locateAnnotation, messageBody, paintHighlights, quoteOccurrence, quoteRange, sourceKey } from './annotation-ranges';
import './conversation-tools.css';

const storageKey = 'finance.annotationDrafts.v1';
export function useAnnotationDraft(projectId: string, conversationId?: string) {
 const key = `${projectId}:${conversationId || 'new'}`;
 const [drafts, setDrafts] = useState<Record<string, Annotation[]>>(() => {
  try {
   const data = JSON.parse(localStorage.getItem(storageKey) || '{}');
   if (!data || Array.isArray(data) || typeof data !== 'object') return {};
   return Object.fromEntries(Object.entries(data).filter(([, items]) => Array.isArray(items) && items.every(item => item && ['id','messageId','text','comment'].every(k => typeof item[k] === 'string') && ['user','assistant'].includes(item.role) && (item.occurrence === undefined || Number.isInteger(item.occurrence) && item.occurrence >= 0)))) as Record<string, Annotation[]>;
  } catch { return {}; }
 });
 const [storageError, setStorageError] = useState('');
 useEffect(() => {
  try { localStorage.setItem(storageKey, JSON.stringify(drafts)); setStorageError(''); }
  catch { setStorageError('浏览器未能保存引用草稿，请保留当前页面，发送前不要刷新。'); }
 }, [drafts]);
 const items = drafts[key] || [];
 const update = (next: Annotation[]) => setDrafts(previous => ({ ...previous, [key]: next }));
 return { items, update, storageError, clearSent: (sent: Annotation[]) => setDrafts(previous => ({ ...previous, [key]: (previous[key] || []).filter(item => !sent.some(s => s.id === item.id)) })) };
}

type Editor = { id: string; sentItems?: Annotation[] };
interface AnnotationActions { open: (id: string, sentItems?: Annotation[]) => void; add: (item: Annotation) => boolean }
const Context = createContext<AnnotationActions | null>(null);
function useActions() { const value = useContext(Context); if (!value) throw new Error('AnnotationWorkspace is required'); return value; }

// One shared editor for the selection action, composer list, source badges, and sent references.
export function AnnotationWorkspace({ items, messages, onChange, disabled, onError, children }: {
 items: Annotation[]; messages: Message[]; onChange: (items: Annotation[]) => void; disabled: boolean; onError: (message: string) => void; children: ReactNode;
}) {
 const [editor, setEditor] = useState<Editor>();
 useEffect(() => { if (!items.length) setEditor(previous => previous?.sentItems ? previous : undefined); }, [items.length]);
 const editorItems = editor?.sentItems || items;
 const open = (id: string, sentItems?: Annotation[]) => setEditor({ id, sentItems });
 const add = (item: Annotation) => {
  if (disabled) return false;
  const existing = items.find(i => sourceKey(i) === sourceKey(item));
  if (existing) { open(existing.id); return true; }
  if (items.length >= 20 || item.text.length > 12000 || items.reduce((n, a) => n + a.text.length + a.comment.length, 0) + item.text.length + item.comment.length > 50000) {
   onError('引用过长或数量已达上限，请缩小选段后再添加。'); return false;
  }
  onChange([...items, item]); open(item.id); return true;
 };
 const close = (restoreFocus = true) => { setEditor(undefined); clearHighlights('finance-reference-active'); if (restoreFocus) document.querySelector<HTMLTextAreaElement>('.composer textarea')?.focus({ preventScroll: true }); };
 return <Context.Provider value={{ open, add }}>{children}
  <ReferenceMarks items={items} messages={messages} />
  {editor && editorItems.length > 0 && <AnnotationDetail key={`${editor.sentItems ? 'sent' : 'pending'}:${editor.id}`} items={editorItems} initialId={editor.id} onClose={close}
   disabled={disabled} sent={!!editor.sentItems} onUpdate={(id, comment) => onChange(items.map(i => i.id === id ? { ...i, comment } : i))}
   onRemove={id => { onChange(items.filter(i => i.id !== id)); if (items.length === 1) close(); }}
   onReuse={item => add({ ...item, id: crypto.randomUUID() })} />}
 </Context.Provider>;
}

// The DSH card and hover list attach to the left edge immediately above the composer.
function useComposerPosition(ref: RefObject<HTMLElement | null>, active: boolean) {
 const [position, setPosition] = useState({ left: 8, top: 8 });
 useLayoutEffect(() => {
  if (!active) return;
  const composer = document.querySelector('.composer'), rail = document.querySelector('.annotation-rail:not(.sent)');
  const place = () => {
   const anchor = composer?.getBoundingClientRect(), box = ref.current?.getBoundingClientRect(); if (!anchor || !box) return;
   const top = rail?.getBoundingClientRect().top ?? anchor.top;
   const next = { left: Math.max(8, Math.min(anchor.left, innerWidth - box.width - 8)), top: Math.max(8, top - box.height - 8) };
   setPosition(previous => previous.left === next.left && previous.top === next.top ? previous : next);
  };
  place(); const observer = new ResizeObserver(place);
  if (ref.current) observer.observe(ref.current); if (composer) observer.observe(composer);
  window.addEventListener('resize', place); document.addEventListener('scroll', place, true);
  return () => { observer.disconnect(); window.removeEventListener('resize', place); document.removeEventListener('scroll', place, true); };
 }, [ref, active]);
 return position;
}

export function SelectionReference({ conversationId, disabled }: { conversationId?: string; disabled: boolean }) {
 const { add } = useActions();
 const [capture, setCapture] = useState<{ item: Annotation; x: number; y: number }>();
 const menu = useRef<HTMLDivElement>(null);
 useEffect(() => {
  setCapture(undefined); if (!conversationId || disabled) return;
  const read = (event: Event) => {
   if ((event.target as Element)?.closest?.('[data-annotation-surface]')) return;
   const selection = window.getSelection();
   if (!selection || selection.isCollapsed || !selection.rangeCount) { setCapture(undefined); return; }
   const range = selection.getRangeAt(0);
   const parent = (node: Node) => node.nodeType === Node.TEXT_NODE ? node.parentElement : node as Element;
   const start = parent(range.startContainer)?.closest<HTMLElement>('.message');
   const end = parent(range.endContainer)?.closest<HTMLElement>('.message');
   const text = selection.toString();
   const startBody = parent(range.startContainer)?.closest<HTMLElement>('.markdown,.user-bubble');
   const endBody = parent(range.endContainer)?.closest('.markdown,.user-bubble');
   if (!start || start !== end || !start.closest('.conversation-scroll') || !startBody || startBody !== endBody || !text.trim() || !start.dataset.messageId || ['streaming','running','pending'].includes(start.dataset.status || '')) { setCapture(undefined); return; }
   const rects = range.getClientRects(), rect = rects[rects.length - 1] || range.getBoundingClientRect();
   const viewport = start.closest('.conversation-scroll')!.getBoundingClientRect();
   const bottom = Math.min(innerHeight, viewport.bottom);
   setCapture({ item: { id: crypto.randomUUID(), messageId: start.dataset.messageId, role: start.classList.contains('user') ? 'user' : 'assistant', text, comment: '', occurrence: quoteOccurrence(startBody, range, text) }, x: Math.max(8, Math.min(innerWidth - 228, rect.left)), y: Math.max(Math.max(8, viewport.top + 8), Math.min(bottom - 60, rect.bottom + 62 < bottom ? rect.bottom + 8 : rect.top - 55)) });
  };
  const clear = () => setCapture(undefined);
  const key = (event: KeyboardEvent) => { if (event.key === 'Escape') clear(); else if (event.shiftKey) read(event); };
  const outside = (event: PointerEvent) => { if (!menu.current?.contains(event.target as Node)) clear(); };
  document.addEventListener('pointerup', read); document.addEventListener('keyup', key); document.addEventListener('pointerdown', outside);
  window.addEventListener('resize', clear); document.addEventListener('scroll', clear, true);
  return () => { document.removeEventListener('pointerup', read); document.removeEventListener('keyup', key); document.removeEventListener('pointerdown', outside); window.removeEventListener('resize', clear); document.removeEventListener('scroll', clear, true); };
 }, [conversationId, disabled]);
 if (!capture) return null;
 return createPortal(<div ref={menu} data-annotation-surface className="selection-reference" style={{ left: capture.x, top: capture.y }} role="menu" aria-label="选文操作">
  <button role="menuitem" onPointerDown={e => e.preventDefault()} onClick={() => { if (add(capture.item)) { setCapture(undefined); window.getSelection()?.removeAllRanges(); } }}><MessageSquarePlus />添加到当前会话</button>
 </div>, document.body);
}

function AnnotationDetail({ items, initialId, onClose, onUpdate, onRemove, onReuse, disabled, sent }: {
 items: Annotation[]; initialId: string; onClose: (restoreFocus?: boolean) => void; onUpdate: (id: string, comment: string) => void; onRemove: (id: string) => void; onReuse: (item: Annotation) => void; disabled: boolean; sent: boolean;
}) {
 const [active, setActive] = useState(initialId), [error, setError] = useState('');
 const ref = useRef<HTMLElement>(null), comment = useRef<HTMLTextAreaElement>(null);
 const callbacks = useRef({ onClose }); callbacks.current = { onClose };
 const item = items.find(i => i.id === active) || items[0];
 const position = useComposerPosition(ref, true);
 useEffect(() => {
  const escape = (event: KeyboardEvent) => {
   if (event.key !== 'Escape' || event.isComposing || event.keyCode === 229) return;
   event.preventDefault(); event.stopImmediatePropagation(); callbacks.current.onClose();
  };
  const outside = (event: PointerEvent) => { if (!ref.current?.contains(event.target as Node)) callbacks.current.onClose(false); };
  document.addEventListener('keydown', escape, true); document.addEventListener('pointerdown', outside);
  return () => { document.removeEventListener('keydown', escape, true); document.removeEventListener('pointerdown', outside); clearHighlights('finance-reference-active'); };
 }, []);
 useEffect(() => {
  setError(''); if (!item) return;
  if (!sent) { locateAnnotation(item); comment.current?.focus({ preventScroll: true }); }
  else ref.current?.focus({ preventScroll: true });
 }, [item?.id, sent]);
 if (!item) return null;
 const jump = () => { if (!locateAnnotation(item)) setError('暂时无法定位这段原文，引用快照仍可在这里查看。'); };
 return createPortal(<section ref={ref} style={position} tabIndex={-1} data-annotation-surface className="annotation-popover" role="dialog" aria-modal="false" aria-label="引用详情">
  <button className="annotation-icon annotation-close" aria-label="关闭引用详情" onClick={() => onClose()}><X /></button>
  {items.length > 1 && <nav aria-label="选择引用">{items.map((entry, i) => <button key={entry.id} aria-label={`查看引用 ${i + 1}`} aria-pressed={item.id === entry.id} onClick={() => setActive(entry.id)}><span>{i + 1}</span>{entry.text.slice(0, 18)}</button>)}</nav>}
  <div className="annotation-body"><p className="annotation-origin">引用 {items.indexOf(item) + 1} · {item.role === 'assistant' ? '助手回复' : '你的消息'}{sent ? ' · 已发送' : ''}</p><blockquote>{item.text}</blockquote>
   <label><strong>注释</strong>{sent ? <p className="annotation-comment">{item.comment || '暂无注释'}</p> : <textarea ref={comment} key={item.id} aria-label="引用注释" maxLength={4000} value={item.comment} disabled={disabled} onChange={e => onUpdate(item.id, e.target.value)} placeholder="添加注释…" rows={3} onKeyDown={event => {
    event.stopPropagation(); if (event.nativeEvent.isComposing || event.nativeEvent.keyCode === 229) return;
    if (event.key === 'Enter' && !event.shiftKey && !event.ctrlKey && !event.metaKey && !event.altKey) { event.preventDefault(); if (!event.repeat && !disabled) onClose(); }
   }} />}</label>
   {error && <p className="error-text" role="alert">{error}</p>}
   <footer>{!sent && <small>Enter 保存 · Shift+Enter 换行</small>}<button className="annotation-icon" aria-label="跳转到引用位置" title="跳转到引用位置" onClick={jump}><ArrowUpRight /></button>
    {sent ? <button className="annotation-icon" aria-label="重新添加到当前提问" title="重新添加到当前提问" disabled={disabled} onClick={() => onReuse(item)}><Plus /></button> : <><button className="annotation-icon" aria-label="删除引用" title="删除引用" disabled={disabled} onClick={() => onRemove(item.id)}><Trash2 /></button><button className="annotation-icon annotation-save" aria-label="保存注释" title="保存注释 · Enter" disabled={disabled} onClick={() => onClose()}><Check /></button></>}
   </footer>
  </div>
 </section>, document.body);
}

export function AnnotationRail({ items, onChange, disabled = false, sent = false }: { items: Annotation[]; onChange?: (items: Annotation[]) => void; disabled?: boolean; sent?: boolean }) {
 const { open } = useActions();
 const [expanded, expand] = useState(false);
 const trigger = useRef<HTMLButtonElement>(null), panel = useRef<HTMLDivElement>(null), timer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
 const suppressFocus = useRef(false);
 const position = useComposerPosition(panel, expanded);
 const keep = () => { clearTimeout(timer.current); if (!sent) expand(true); };
 const leave = () => { clearTimeout(timer.current); timer.current = setTimeout(() => { if (!panel.current?.contains(document.activeElement) && document.activeElement !== trigger.current) expand(false); }, 180); };
 useEffect(() => () => clearTimeout(timer.current), []);
 useEffect(() => {
  if (!expanded) return;
  const outside = (event: PointerEvent) => { if (!panel.current?.contains(event.target as Node) && !trigger.current?.contains(event.target as Node)) expand(false); };
  const escape = (event: KeyboardEvent) => { if (event.key === 'Escape' && !event.isComposing && event.keyCode !== 229) { event.preventDefault(); event.stopImmediatePropagation(); expand(false); suppressFocus.current = true; trigger.current?.focus({ preventScroll: true }); suppressFocus.current = false; } };
  document.addEventListener('pointerdown', outside); document.addEventListener('keydown', escape, true);
  return () => { document.removeEventListener('pointerdown', outside); document.removeEventListener('keydown', escape, true); };
 }, [expanded]);
 if (!items.length) return null;
 return <div className={`annotation-rail ${sent ? 'sent' : ''}`} data-annotation-surface aria-label={sent ? '已发送引用' : '待发送引用'}>
  <button ref={trigger} className="annotation-count" aria-label={sent ? `打开 ${items.length} 条已发送引用` : `${items.length} 条待发送引用`} aria-expanded={sent ? undefined : expanded} aria-haspopup="dialog"
   onMouseEnter={keep} onMouseLeave={leave} onFocus={() => { if (!suppressFocus.current) keep(); }} onBlur={leave} onClick={() => sent ? open(items[0].id, items) : keep()}><Quote /><span>{items.length}</span>{sent && <span>条引用</span>}</button>
  {!sent && expanded && createPortal(<div ref={panel} className="annotation-list" data-annotation-surface style={position} role="dialog" aria-label="待发送引用列表" onMouseEnter={keep} onMouseLeave={leave} onFocus={keep} onBlur={leave}>
   {items.map((item, index) => <article className="annotation-list-item" key={item.id}><header><span>{index + 1}. {item.role === 'assistant' ? '助手回复' : '你的消息'}</span><div>
    <button className="annotation-icon" aria-label={`编辑引用 ${index + 1}`} title="编辑注释" disabled={disabled} onClick={() => { expand(false); open(item.id); }}><Pencil /></button>
    <button className="annotation-icon" aria-label={`跳转到引用 ${index + 1}`} title="跳转到引用位置" onClick={() => { locateAnnotation(item); expand(false); }}><ArrowUpRight /></button>
    <button className="annotation-icon" aria-label={`删除引用 ${index + 1}`} title="删除引用" disabled={disabled} onClick={() => { onChange?.(items.filter(i => i.id !== item.id)); if (items.length === 1) expand(false); }}><Trash2 /></button>
   </div></header><blockquote>{item.text}</blockquote>{item.comment && <p>{item.comment}</p>}</article>)}
  </div>, document.body)}
 </div>;
}

function ReferenceMarks({ items, messages }: { items: Annotation[]; messages: Message[] }) {
 const { open } = useActions();
 const entries = useMemo(() => {
  const seen = new Set<string>();
  return [{ items, sent: false }, ...messages.slice().reverse().filter(m => m.annotations?.length).map(m => ({ items: m.annotations!, sent: true }))].flatMap(group => group.items.map((item, index) => ({ item, number: index + 1, sentItems: group.sent ? group.items : undefined }))).filter(entry => {
   const key = sourceKey(entry.item); if (seen.has(key)) return false; seen.add(key); return true;
  });
 }, [items, messages]);
 const [marks, setMarks] = useState<{ entry: typeof entries[number]; left: number; top: number }[]>([]);
 useEffect(() => {
  const scroller = document.querySelector<HTMLElement>('.conversation-scroll'), content = scroller?.querySelector('.messages');
  if (!scroller || !content || !entries.length) { setMarks([]); clearHighlights('finance-references'); return; }
  let frame = 0, cache = new WeakMap<HTMLElement, ReturnType<typeof indexText>>();
  const paint = () => {
   frame = 0; const bounds = scroller.getBoundingClientRect(); const ranges: Range[] = [], next: typeof marks = [];
   const drawer = document.querySelector('.flow-drawer')?.getBoundingClientRect();
   const visibleRight = drawer && drawer.left < bounds.right ? drawer.left : bounds.right;
   for (const entry of entries) {
    const body = messageBody(entry.item); if (!body) continue;
    const bodyBox = body.getBoundingClientRect(); if (bodyBox.bottom < bounds.top || bodyBox.top > bounds.bottom) continue;
    let index = cache.get(body); if (!index) { index = indexText(body); cache.set(body, index); }
    const range = quoteRange(body, entry.item, index); if (!range) continue; ranges.push(range);
    const rects = [...range.getClientRects()].filter(rect => rect.width && rect.height), rect = rects.at(-1); if (!rect) continue;
    const top = rect.top + rect.height / 2 - 9;
    if (top < Math.max(bounds.top, 0) || top + 19 > Math.min(bounds.bottom, innerHeight)) continue;
    if (rect.right + 4 > visibleRight - 19) continue;
    const left = Math.max(bounds.left + 2, Math.min(rect.right + 4, visibleRight - 23, innerWidth - 23));
    let shift = left;
    for (const prior of next) if (Math.abs(prior.top - top) < 18 && Math.abs(prior.left - shift) < 21) shift = Math.max(bounds.left + 2, prior.left - 22);
    next.push({ entry, left: shift, top });
   }
   paintHighlights('finance-references', ranges); setMarks(next);
  };
  const schedule = () => { if (!frame) frame = requestAnimationFrame(paint); };
  const observer = new MutationObserver(() => { cache = new WeakMap(); schedule(); }); observer.observe(content, { childList: true, characterData: true, subtree: true });
  const resize = new ResizeObserver(schedule); resize.observe(scroller); resize.observe(content);
  scroller.addEventListener('scroll', schedule); window.addEventListener('resize', schedule); schedule();
  return () => { cancelAnimationFrame(frame); observer.disconnect(); resize.disconnect(); scroller.removeEventListener('scroll', schedule); window.removeEventListener('resize', schedule); clearHighlights('finance-references'); };
 }, [entries]);
 return createPortal(<div data-annotation-surface className="annotation-source-marks">{marks.map(mark => <button key={sourceKey(mark.entry.item)} className="annotation-source-badge" style={{ left: mark.left, top: mark.top }} aria-label={`打开选段引用 ${mark.entry.number}`} title="查看选段引用" onClick={() => open(mark.entry.item.id, mark.entry.sentItems)}>{mark.entry.number}</button>)}</div>, document.body);
}
