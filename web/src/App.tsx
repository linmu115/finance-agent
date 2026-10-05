import { useCallback, useEffect, useRef, useState, type DragEvent, type KeyboardEvent } from 'react';
import { PanelLeft, SquarePen, FolderOpen, ClipboardCheck, Settings2, Plus, ArrowUp, ChevronDown, X, FileText, ChartNoAxesCombined, Table2, Check, Download, LoaderCircle, CircleAlert, MessageSquare, Upload } from 'lucide-react';
import { api, errorText, isAbort, listResult } from './api';
import { emptySettings, type Project, type Conversation, type Message, type Document, type Settings, type Source, type ToolEvent, type Health } from './types';
import MessageView, { FileChip, ToolTrace } from './MessageView';
import SettingsDialog from './SettingsDialog';
import AssetDashboard from './AssetDashboard';
import DatasetView from './DatasetView';
import Modal from './Modal';
import AttachmentFlow from './AttachmentFlow';
import { ProjectRules } from './ProjectControls';
import ApprovalCard from './ApprovalCard';
import { AnnotationRail, AnnotationWorkspace, SelectionReference, useAnnotationDraft } from './Annotations';

interface ActiveRun { projectId?: string; id: string; conversationId: string; messageId: string; stage: string; tools: ToolEvent[]; cancelling?: boolean }
const pendingStatuses = ['queued', 'parsing', 'processing', 'normalizing', 'validating'];
const stages: Record<string, string> = { queued: '等待开始', preparing: '准备分析', parsing: '读取附件', normalizing: '理解字段并清洗入库', waiting_documents: '等待附件解析完成', thinking: '分析任务', generating: '生成回答', running: '正在分析', tool: '执行工具', completed: '分析完成', cancelled: '已停止', failed: '分析失败' };
const acceptedFiles = /\.(xlsx|xls|csv|tsv|pdf)$/i;
function normalizedSettings(settings: Settings): Settings { return { llm: { ...emptySettings.llm, ...settings.llm }, embedding: { ...emptySettings.embedding, ...settings.embedding }, ocr: { ...emptySettings.ocr, ...settings.ocr }, search:{...emptySettings.search,...settings.search},runtime: { ...emptySettings.runtime, ...settings.runtime } }; }

export default function App() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [projectId, setProjectId] = useState('');
  const [projectConversations, setProjectConversations] = useState<Record<string, Conversation[]>>({});
  const [expandedProjects, setExpandedProjects] = useState<Record<string, boolean>>(() => {
    try {
      const saved = JSON.parse(localStorage.getItem('finance.expandedProjects') || '{}');
      return saved && typeof saved === 'object' && !Array.isArray(saved) ? Object.fromEntries(Object.entries(saved).filter(([, value]) => typeof value === 'boolean')) as Record<string, boolean> : {};
    } catch { return {}; }
  });
  const [conversationLoading, setConversationLoading] = useState<Record<string, boolean>>({});
  const [conversationErrors, setConversationErrors] = useState<Record<string, string>>({});
  const [conversationId, setConversationId] = useState<string>();
  const [messages, setMessages] = useState<Message[]>([]);
  const [documents, setDocuments] = useState<Document[]>([]);
  const [pendingDocuments, setPendingDocuments] = useState<Document[]>([]);
  const [settings, setSettings] = useState<Settings>(emptySettings);
  const [health, setHealth] = useState<Health>();
  const [draft, setDraft] = useState('');
  const [error, setError] = useState('');
  const [toast, setToast] = useState('');
  const [booting, setBooting] = useState(true);
  const [retryBoot, setRetryBoot] = useState(0);
  const [loadingChat, setLoadingChat] = useState(false);
  const [sending, setSending] = useState(false);
  const [uploading, setUploading] = useState(0);
  const [runs, setRuns] = useState<Record<string, ActiveRun>>({});
  const [sidebar, setSidebar] = useState(true);
  const [mobileSidebar, setMobileSidebar] = useState(false);
  const [showSettings, setShowSettings] = useState(false);
  const [showModel, setShowModel] = useState(false);
  const [showAttach, setShowAttach] = useState(false);
  const [showFlow,setShowFlow]=useState(false);
  const [rulesProject,setRulesProject]=useState<Project>();
  const [factSelection,setFactSelection]=useState<{documentId:string;metric:string;factId:string}>();
  const [source, setSource] = useState<Source>();
  const annotationDraft = useAnnotationDraft(projectId, conversationId);
  const [view, setView] = useState<'chat' | 'dashboard' | 'benchmark'>('chat');
  const [showProjectDialog, setShowProjectDialog] = useState(false);
  useEffect(()=>{setFactSelection(undefined);},[projectId]);
  const [projectName, setProjectName] = useState('');
  const [projectBusy, setProjectBusy] = useState(false);
  const [projectError, setProjectError] = useState('');
  const [dragging, setDragging] = useState(false);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const streamsRef = useRef(new Map<string, EventSource>());
  const runsRef = useRef<Record<string, ActiveRun>>({});
  const liveMessages = useRef(new Map<string, Message>());
  const slotRef = useRef(crypto.randomUUID() as string);
  const conversationRef = useRef<string | undefined>(undefined);
  const projectRef = useRef(projectId);
  const toastTimer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  const dragCounter = useRef(0);
  const followScroll = useRef(true);
  const sendingRef = useRef(new Set<string>());
  const chatRequest = useRef(0);
  const pendingNavigation = useRef<{ projectId: string; conversationId?: string } | undefined>(undefined);
  const listRequests = useRef<Record<string, number>>({});
  const conversations = projectConversations[projectId] || [];
  const currentProject = projects.find(project => project.id === projectId);
  const run = conversationId ? runs[conversationId] : undefined;
  const activeHere = Boolean(run);
  const backgroundRuns = Object.values(runs).filter(item => item.conversationId !== conversationId && (!item.projectId || item.projectId === projectId));
  const empty = messages.length === 0 && !loadingChat;

  const notify = useCallback((text: string) => { setToast(text); clearTimeout(toastTimer.current); toastTimer.current = setTimeout(() => setToast(''), 4200); }, []);
  const refreshDocuments = useCallback(async (id = projectRef.current) => {
    if (!id) return;
    try {
      const result = await api<Document[] | { documents: Document[] }>(`/api/projects/${encodeURIComponent(id)}/documents`);
      if (projectRef.current !== id) return;
      const docs = listResult<Document>(result, 'documents');
      setDocuments(docs);
      setPendingDocuments(previous => previous.map(doc => docs.find(item => item.id === doc.id) || doc));
    } catch (error) { setError(errorText(error)); }
  }, []);
  const refreshConversations = useCallback(async (id = projectRef.current) => {
    if (!id) return;
    const request = (listRequests.current[id] || 0) + 1;
    listRequests.current[id] = request;
    setConversationLoading(previous => ({ ...previous, [id]: true }));
    setConversationErrors(previous => ({ ...previous, [id]: '' }));
    try {
      const result = await api<Conversation[] | { conversations: Conversation[] }>(`/api/projects/${encodeURIComponent(id)}/conversations`);
      if (listRequests.current[id] === request) setProjectConversations(previous => ({ ...previous, [id]: listResult<Conversation>(result, 'conversations') }));
    } catch (error) {
      if (listRequests.current[id] === request) setConversationErrors(previous => ({ ...previous, [id]: errorText(error) }));
    } finally {
      if (listRequests.current[id] === request) setConversationLoading(previous => ({ ...previous, [id]: false }));
    }
  }, []);

  useEffect(() => { localStorage.setItem('finance.expandedProjects', JSON.stringify(expandedProjects)); }, [expandedProjects]);
  useEffect(() => {
    for (const project of projects) if (expandedProjects[project.id] && !projectConversations[project.id] && !listRequests.current[project.id]) void refreshConversations(project.id);
  }, [projects, expandedProjects, projectConversations, refreshConversations]);

  useEffect(() => {
    const controller = new AbortController();
    setBooting(true); setError('');
    Promise.allSettled([
      api<Project[] | { projects: Project[] }>('/api/projects', { signal: controller.signal }),
      api<Settings>('/api/settings', { signal: controller.signal }),
      api<Health>('/api/health', { signal: controller.signal }),
    ]).then(([projectResult, settingsResult, healthResult]) => {
      if (controller.signal.aborted) return;
      if (projectResult.status === 'fulfilled') { const items = listResult<Project>(projectResult.value, 'projects'); setProjects(items); const remembered = localStorage.getItem('finance.project'); const preferred = items.find(item => item.id === remembered) || items.filter(item => /财报研究/.test(item.name) && (item.documentCount ?? item.document_count ?? 0) > 0).sort((a, b) => (b.createdAt || '').localeCompare(a.createdAt || ''))[0] || [...items].sort((a, b) => (b.documentCount ?? b.document_count ?? 0) - (a.documentCount ?? a.document_count ?? 0))[0]; setProjectId(preferred?.id || ''); }
      else setError(errorText(projectResult.reason));
      if (settingsResult.status === 'fulfilled') setSettings(normalizedSettings(settingsResult.value));
      if (healthResult.status === 'fulfilled') setHealth(healthResult.value);
      setBooting(false);
    });
    return () => controller.abort();
  }, [retryBoot]);

  useEffect(() => {
    projectRef.current = projectId;
    if (projectId) localStorage.setItem('finance.project', projectId);
    slotRef.current = crypto.randomUUID(); setSending(false);
    conversationRef.current = undefined; setConversationId(undefined); setMessages([]); setPendingDocuments([]); setDraft(''); setSource(undefined); setDocuments([]); setLoadingChat(false);
    if (!projectId) return;
    setExpandedProjects(previous => previous[projectId] === undefined ? { ...previous, [projectId]: true } : previous);
    const controller = new AbortController();
    const navigation = pendingNavigation.current;
    pendingNavigation.current = undefined;
    if (navigation?.projectId === projectId && navigation.conversationId) void openConversation(navigation.conversationId);
    Promise.all([
      refreshConversations(projectId),
      api<Document[] | { documents: Document[] }>(`/api/projects/${encodeURIComponent(projectId)}/documents`, { signal: controller.signal }),
    ]).then(([, docs]) => { if (!controller.signal.aborted) setDocuments(listResult<Document>(docs, 'documents')); }).catch(error => { if (!isAbort(error)) setError(errorText(error)); });
    return () => { controller.abort(); chatRequest.current++; };
  }, [projectId]);

  useEffect(() => {
    for (const chat of conversations) if (chat.activeRunId && !streamsRef.current.has(chat.activeRunId)) subscribeRun({ id: chat.activeRunId, projectId, conversationId: chat.id, messageId: `live-${chat.activeRunId}`, stage: 'running', tools: [] });
  }, [projectId, projectConversations]);

  useEffect(() => {
    if (!documents.some(doc => pendingStatuses.includes(doc.status))) return;
    const interval = setInterval(() => void refreshDocuments(), 2200);
    return () => clearInterval(interval);
  }, [documents, refreshDocuments]);
  useEffect(() => {
    if (scrollRef.current && followScroll.current) scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
  }, [messages, run?.stage, run?.tools.length, loadingChat]);
  useEffect(() => {
    const input = inputRef.current;
    if (input) { input.style.height = 'auto'; input.style.height = `${Math.min(input.scrollHeight, 180)}px`; }
  }, [draft]);
  useEffect(() => () => { streamsRef.current.forEach(stream => stream.close()); streamsRef.current.clear(); clearTimeout(toastTimer.current); }, []);

  function newChat() {
    if (projectRef.current) setExpandedProjects(previous => ({ ...previous, [projectRef.current]: true }));
    slotRef.current = crypto.randomUUID(); setSending(false);
    chatRequest.current++; conversationRef.current = undefined;
    setConversationId(undefined); setMessages([]); setPendingDocuments([]); setDraft(''); setError(''); setLoadingChat(false); setView('chat'); setMobileSidebar(false); setSource(undefined);
    followScroll.current = true; setTimeout(() => inputRef.current?.focus(), 0);
  }
  useEffect(() => {
    function keydown(event: globalThis.KeyboardEvent) {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'k' && !document.querySelector('dialog[open]')) { event.preventDefault(); newChat(); }
      if (event.key === 'Escape') { setShowModel(false); setShowAttach(false); setMobileSidebar(false); }
    }
    document.addEventListener('keydown', keydown);
    return () => document.removeEventListener('keydown', keydown);
  }, []);

  async function finalRefresh(id: string, ownerProject = projectRef.current) {
    try {
      const latest = await api<Conversation>(`/api/conversations/${encodeURIComponent(id)}`);
      if (conversationRef.current === id) setMessages(latest.messages || []);
      await refreshConversations(ownerProject); void refreshDocuments(ownerProject);
    } catch (error) { setError(errorText(error)); }
  }
  function subscribeRun(next: ActiveRun) {
    if (streamsRef.current.has(next.id)) return;
    const update = (patch: Partial<ActiveRun>) => { const current = runsRef.current[next.conversationId]; if (!current || current.id !== next.id) return; runsRef.current = { ...runsRef.current, [next.conversationId]: { ...current, ...patch } }; setRuns(runsRef.current); };
    runsRef.current = { ...runsRef.current, [next.conversationId]: next }; setRuns(runsRef.current);
    liveMessages.current.set(next.id, { id: next.messageId, role: 'assistant', content: '', status: 'streaming' });
    if (conversationRef.current === next.conversationId) setMessages(previous => previous.map(message => message.id === next.messageId ? { ...message, content: '', status: 'streaming' } : message));
    const stream = new EventSource(`/api/runs/${encodeURIComponent(next.id)}/events`);
    streamsRef.current.set(next.id, stream);
    let finished = false;
    let networkFailures = 0;
    const completed = () => { if (finished) return; finished = true; stream.close(); streamsRef.current.delete(next.id); const remaining = { ...runsRef.current }; if (remaining[next.conversationId]?.id === next.id) delete remaining[next.conversationId]; runsRef.current = remaining; setRuns(remaining); liveMessages.current.delete(next.id); void finalRefresh(next.conversationId, next.projectId); };
    const parse = (event: Event) => {
      try { return JSON.parse((event as MessageEvent).data); } catch { return undefined; }
    };
    stream.addEventListener('open', () => { networkFailures = 0; });
    stream.addEventListener('status', event => { const value = parse(event); if (value) update({ stage: value.stage || value.status || 'running' }); });
    stream.addEventListener('answer_start',event=>{
      const message=parse(event)?.message as Message|undefined;if(!message)return;
      next.messageId=message.id;liveMessages.current.set(next.id,message);
      if(conversationRef.current===next.conversationId)setMessages(previous=>[...previous.filter(m=>m.id!==message.id),message]);
    });
    stream.addEventListener('input',event=>{
      const message=parse(event)?.message as Message|undefined;if(!message||conversationRef.current!==next.conversationId)return;
      setMessages(previous=>previous.some(m=>m.id===message.id)?previous.map(m=>m.id===message.id?message:m):[...previous,message]);
    });
    stream.addEventListener('delta', event => {
      const value = parse(event); if (!value) return;
      const current=liveMessages.current.get(next.id)!;
      const id=value.messageId||next.messageId;const prior=current.id===id?current:{id,role:'assistant' as const,content:'',status:'streaming'};
      const live = { ...prior, content: prior.content + (value.text || '') };
      liveMessages.current.set(next.id, live);
      if (conversationRef.current === next.conversationId) setMessages(previous => previous.some(message=>message.id===live.id)?previous.map(message=>message.id===live.id?live:message):[...previous,live]);
    });
    stream.addEventListener('tool', event => { const value = parse(event) as ToolEvent | undefined; if (!value) return; const tools = runsRef.current[next.conversationId]?.tools || []; update({ tools: [...tools.filter(tool => value.status !== 'progress' || tool.name !== value.name || tool.status !== 'progress').slice(-99), value], stage: value.status === 'progress' ? value.summary || 'tool' : 'tool' }); void refreshDocuments(next.projectId); });
    stream.addEventListener('message', event => {
      const value = parse(event); const message = value?.message as Message | undefined;
      if (!message || conversationRef.current !== next.conversationId) return;
      setMessages(previous => previous.some(item=>item.id===message.id)?previous.map(item=>item.id===message.id?message:item):[...previous,message]);
    });
    stream.addEventListener('done', () => completed());
    stream.addEventListener('error', event => {
      const value = parse(event);
      if (value) { if (conversationRef.current === next.conversationId) setError(value.message || value.error?.message || '分析运行失败。'); completed(); return; }
      networkFailures++;
      update({ stage: networkFailures >= 3 ? '连接尚未恢复，服务器任务继续运行' : '连接中断，正在重连…' });
      if (stream.readyState === EventSource.CLOSED) { streamsRef.current.delete(next.id); if (conversationRef.current === next.conversationId) setError('连接已关闭，重新打开此对话可恢复运行进度。'); }
    });
  }

  function chooseProject(id: string, chatId?: string) {
    if (id === projectRef.current) { if (chatId) void openConversation(chatId); return; }
    pendingNavigation.current = { projectId: id, conversationId: chatId };
    setView('chat'); setProjectId(id);
  }
  function toggleProject(id: string) {
    const expanded = !expandedProjects[id];
    setExpandedProjects(previous => ({ ...previous, [id]: expanded }));
    if (expanded) void refreshConversations(id);
    chooseProject(id);
  }
  function newProjectChat(id: string) {
    setExpandedProjects(previous => ({ ...previous, [id]: true }));
    if (id === projectRef.current) newChat();
    else { chooseProject(id); setMobileSidebar(false); }
  }
  async function openConversation(id: string) {
    slotRef.current = id; setSending(sendingRef.current.has(id));
    const request = ++chatRequest.current;
    conversationRef.current = id; setConversationId(id); setView('chat'); setMobileSidebar(false); setMessages([]); setPendingDocuments([]); setDraft(''); setSource(undefined); setError(''); setLoadingChat(true); followScroll.current = true;
    try {
      const result = await api<Conversation>(`/api/conversations/${encodeURIComponent(id)}`);
      if (request !== chatRequest.current) return;
      const live = result.activeRunId ? liveMessages.current.get(result.activeRunId) : undefined;
      setMessages(live ? [...(result.messages || []).filter(message => message.id !== live.id && !['streaming', 'pending', 'running'].includes(message.status || '')), live] : result.messages || []);
      if (result.activeRunId && !streamsRef.current.has(result.activeRunId)) {
        const assistant = [...(result.messages || [])].reverse().find(message => message.role === 'assistant' && ['streaming', 'running', 'pending'].includes(message.status || ''));
        subscribeRun({ id: result.activeRunId, projectId: result.projectId, conversationId: id, messageId: assistant?.id || `live-${result.activeRunId}`, stage: 'running', tools: [] });
      }
    } catch (error) { if (request === chatRequest.current) setError(errorText(error)); }
    finally { if (request === chatRequest.current) setLoadingChat(false); }
  }

  async function send(mode:'steer'|'followUp'='steer') {
    if (sendingRef.current.has(slotRef.current) || uploading || !projectId || (!draft.trim() && !pendingDocuments.length && !annotationDraft.items.length)) return;
    const references = [...annotationDraft.items]; const content = draft.trim() || (references.length ? '请结合这些引用及补充说明回答。' : ''); const files = [...pendingDocuments]; const targetProject = projectId; const targetSlot = slotRef.current;
    setSending(true); sendingRef.current.add(targetSlot); setError('');
    try {
      let id = conversationRef.current;
      if (!id) {
        const result = await api<Conversation>(`/api/projects/${encodeURIComponent(targetProject)}/conversations`, { method: 'POST', body: JSON.stringify({ title: content.slice(0, 40) || files[0]?.name || '新对话' }) });
        id = result.id; if (slotRef.current === targetSlot) { conversationRef.current = id; setConversationId(id); }
        listRequests.current[targetProject] = (listRequests.current[targetProject] || 0) + 1;
        setConversationLoading(previous => ({ ...previous, [targetProject]: false }));
        setProjectConversations(previous => ({ ...previous, [targetProject]: [result, ...(previous[targetProject] || []).filter(chat => chat.id !== result.id)] }));
        setExpandedProjects(previous => ({ ...previous, [targetProject]: true }));
      }
      const result = await api<{ runId: string; messageId: string; userMessageId: string; inputStatus?:string }>(`/api/conversations/${encodeURIComponent(id)}/messages`, { method: 'POST', body: JSON.stringify({ mode, content: content || '请处理这批财报，清洗全部财务主表和附注表，入库并更新项目看板。', documentIds: files.map(doc => doc.id), annotations: references.map(({role: _role, ...item}) => item) }) });
      if (conversationRef.current === id) {
        setMessages(previous => [...previous.filter(m=>m.id!==result.userMessageId), { id: result.userMessageId, role: 'user', status:result.inputStatus, content: content || '请处理这批财报，清洗全部财务主表和附注表，入库并更新项目看板。', attachments: files, annotations: references, createdAt: new Date().toISOString() }]);
        setDraft(''); setPendingDocuments([]); followScroll.current = true;
      }
      annotationDraft.clearSent(references);
      subscribeRun({ id: result.runId, projectId: targetProject, conversationId: id, messageId: result.messageId || `live-${result.runId}`, stage: 'queued', tools: [] });
    } catch (error) { setError(errorText(error)); }
    finally { sendingRef.current.delete(targetSlot); if (slotRef.current === targetSlot) setSending(false); }
  }

  async function cancel() {
    if (!run || run.cancelling) return;
    runsRef.current = { ...runsRef.current, [run.conversationId]: { ...run, cancelling: true } }; setRuns(runsRef.current);
    try { await api(`/api/runs/${encodeURIComponent(run.id)}/cancel`, { method: 'POST' }); notify('已发送停止请求。'); }
    catch (error) { setError(errorText(error)); runsRef.current = { ...runsRef.current, [run.conversationId]: { ...run, cancelling: false } }; setRuns(runsRef.current); }
  }
  async function upload(files: FileList | File[]) {
    setShowAttach(false); setDragging(false); dragCounter.current = 0;
    if (!projectId) { notify('请先创建一个项目，再添加资料。'); setShowProjectDialog(true); return; }
    const items = Array.from(files); const valid = items.filter(file => acceptedFiles.test(file.name) && file.size > 0 && file.size <= 50 * 1024 * 1024);
    if (valid.length !== items.length) notify('仅支持非空的 Excel、CSV、TSV、PDF；单文件不超过 50 MB。');
    if (!valid.length) return;
    const target = projectId; const targetChat = conversationRef.current;
    setUploading(previous => previous + valid.length); setError('');
    try {
      for(let offset=0;offset<valid.length;offset+=8){
      const form = new FormData(); valid.slice(offset,offset+8).forEach(file => form.append('files', file));
      const result = await api<{ documents: Document[] }>(`/api/projects/${encodeURIComponent(target)}/uploads`, { method: 'POST', body: form });
      if (projectRef.current === target) {
        setDocuments(previous => [...previous.filter(doc => !result.documents.some(item => item.id === doc.id)), ...result.documents]);
        if (conversationRef.current === targetChat) setPendingDocuments(previous => [...previous.filter(doc => !result.documents.some(item => item.id === doc.id)), ...result.documents]);
        else notify('文件已添加到原项目；可在原会话中继续引用。');
        void refreshDocuments(target);
      }
      }
    } catch (error) { setError(errorText(error)); }
    finally { setUploading(previous => Math.max(0, previous - valid.length)); if (fileRef.current) fileRef.current.value = ''; }
  }
  function onDrop(event: DragEvent) { event.preventDefault(); void upload(event.dataTransfer.files); }
  function onInputKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) { if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing && event.keyCode !== 229) { event.preventDefault(); if (!event.repeat) void send(event.altKey?'followUp':'steer'); } }
  function selectDocument(doc: Document) { setSource({documentId: doc.id, page: 1}); setShowFlow(true); }
  function selectSource(next: Source) { setSource(next); setShowFlow(true); }
  async function createProject() {
    if (!projectName.trim() || projectBusy) return;
    setProjectBusy(true); setProjectError('');
    try { const project = await api<Project>('/api/projects', { method: 'POST', body: JSON.stringify({ name: projectName.trim() }) }); setProjects(previous => [...previous, project]); setExpandedProjects(previous => ({ ...previous, [project.id]: true })); chooseProject(project.id); setProjectName(''); setShowProjectDialog(false); }
    catch (error) { setProjectError(errorText(error)); }
    finally { setProjectBusy(false); }
  }
  function exportChat() {
    const title = conversations.find(chat => chat.id === conversationId)?.title || '财报分析';
    const content = `# ${title}\n\n${messages.map(message => `## ${message.role === 'user' ? '用户' : '金融研究'}\n\n${message.content}\n${message.annotations?.map((item, i) => `\n引用 ${i + 1}（${item.role === 'assistant' ? '助手回复' : '用户消息'}）\n> ${item.text.replace(/\n/g, '\n> ')}\n补充说明：${item.comment || '无'}\n`).join('') || ''}${message.sources?.map((item, index) => `\n[${index + 1}] ${item.name || item.title || item.sourceId || '原文'} ${item.page ? `第 ${item.page} 页` : ''}\n${item.quote || ''}`).join('') || ''}`).join('\n\n')}`;
    const url = URL.createObjectURL(new Blob([content], { type: 'text/markdown;charset=utf-8' })); const anchor = document.createElement('a'); anchor.href = url; anchor.download = `${title.replace(/[\\/:*?"<>|]/g, '_')}.md`; anchor.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
  }

  return <AnnotationWorkspace key={`${projectId}:${conversationId}:${view}`} items={annotationDraft.items} messages={messages} onChange={annotationDraft.update} disabled={sending || loadingChat} onError={notify}><div className={`app ${sidebar ? '' : 'sidebar-collapsed'} ${mobileSidebar ? 'mobile-sidebar' : ''} ${showFlow && view !== 'benchmark' ? 'drawer-open flow-open' : ''}`} onDragEnter={event => { if (event.dataTransfer.types.includes('Files')) { event.preventDefault(); dragCounter.current++; setDragging(true); } }} onDragLeave={event => { if (event.dataTransfer.types.includes('Files') && --dragCounter.current <= 0) setDragging(false); }} onDragOver={event => { if (event.dataTransfer.types.includes('Files')) event.preventDefault(); }} onDrop={onDrop}>
    <button className="mobile-scrim" aria-label="关闭导航" onClick={() => setMobileSidebar(false)} />
    <aside className="sidebar"><div className="sidebar-top"><button className="brand" aria-label="金融研究首页" onClick={newChat}><span className="brandmark">研</span></button><button className="icon-btn" aria-label="收起侧边栏" onClick={() => { setSidebar(false); setMobileSidebar(false); }}><PanelLeft /></button></div>
      <button className="side-link" onClick={newChat}><SquarePen /><span>新对话</span><kbd>Ctrl K</kbd></button><button className={`side-link ${view === 'dashboard' ? 'active' : ''}`} onClick={() => { setView('dashboard'); setMobileSidebar(false); }}><ChartNoAxesCombined /><span>资产看板</span></button><button className={`side-link ${view === 'benchmark' ? 'active' : ''}`} onClick={() => { setView('benchmark'); setMobileSidebar(false); }}><ClipboardCheck /><span>数据集与测试</span></button>
      <div className="side-section">项目<button className="icon-btn" aria-label="新建项目" onClick={() => setShowProjectDialog(true)}><Plus /></button></div>
      <nav className="project-tree" aria-label="项目与会话">
        {projects.map(project => <section className={`project-group ${project.id === projectId ? 'selected' : ''}`} key={project.id} data-project-id={project.id}>
          <div className="project-row">
            <button className="project-toggle" aria-expanded={!!expandedProjects[project.id]} aria-controls={`project-chats-${project.id}`} aria-current={project.id === projectId ? 'true' : undefined} title={project.name} onClick={() => toggleProject(project.id)}><ChevronDown className="project-chevron" /><FolderOpen /><span>{project.name}</span>{Object.values(runs).some(item => item.projectId === project.id) && <span className="progress-dot" />}</button>
            <button className="icon-btn project-rules" aria-label={`编辑项目约定与技能：${project.name}`} onClick={() => setRulesProject(project)}><Settings2 /></button><button className="icon-btn project-new-chat" aria-label={`在 ${project.name} 中新建对话`} title="新建对话" onClick={() => newProjectChat(project.id)}><Plus /></button>
          </div>
          {expandedProjects[project.id] && <div id={`project-chats-${project.id}`} className="project-chats" role="group" aria-label={`${project.name} 的会话`}>
            {(projectConversations[project.id] || []).map(chat => <button className={`chat-item ${chat.id === conversationId && view === 'chat' ? 'active' : ''}`} key={chat.id} onClick={() => chooseProject(project.id, chat.id)} aria-current={chat.id === conversationId && view === 'chat' ? 'page' : undefined} title={chat.title || '新对话'}><MessageSquare /><span className="chat-title">{chat.title || '新对话'}</span>{(runs[chat.id] || chat.activeRunId) && <span className="progress-dot" />}</button>)}
            {conversationLoading[project.id] && <div className="project-list-note" role="status">正在读取会话…</div>}
            {conversationErrors[project.id] && <button className="project-list-retry" onClick={() => void refreshConversations(project.id)}>读取失败，点击重试</button>}
            {!conversationLoading[project.id] && !conversationErrors[project.id] && !projectConversations[project.id]?.length && <div className="project-list-note">暂无会话，点击 + 开始</div>}
          </div>}
        </section>)}
        {!projects.length && <div className="no-chats">{booting ? '正在读取项目…' : '创建项目后开始研究'}</div>}
      </nav>
      <div className="side-bottom"><button className="api-entry" onClick={() => { setShowSettings(true); setMobileSidebar(false); }}><Settings2 /><span><b>API 配置</b><small>{settings.llm.model || '清洗、分析与对话共用模型'}</small></span><span className="entry-arrow">›</span></button><div className="local-profile"><span className="avatar">本</span><span>本地工作空间<small>{booting ? '正在连接服务' : health ? '服务已连接' : '服务状态待确认'}</small></span></div></div>
    </aside><div className="shell"><header className="topbar"><div className="top-left"><button className="icon-btn show-sidebar" aria-label="展开侧边栏" onClick={() => { setSidebar(true); setMobileSidebar(true); }}><PanelLeft /></button><div className="model-select-wrap"><button className="model-button" aria-haspopup="menu" aria-expanded={showModel} onClick={() => { setShowModel(!showModel); setShowAttach(false); }}><span>金融研究</span><span className="model-label">{settings.llm.model || '选择模型'}</span><ChevronDown /></button>{showModel && <><button className="popover-scrim" aria-label="关闭模型菜单" onClick={() => setShowModel(false)} /><div className="popover model-menu"><div className="popover-label">当前主模型</div><div className="current-model">{settings.llm.model || '尚未配置'}</div><button className="menu-item" onClick={() => { setShowSettings(true); setShowModel(false); }}><Settings2 />配置模型与 API</button><p>财报清洗、查表、制图和回答共用该模型。</p></div></>}</div></div><div className="top-actions">{messages.length > 0 && view === 'chat' && <button className="icon-btn" aria-label="导出当前对话" title="导出当前对话" onClick={exportChat}><Download /></button>}<button className="top-link" onClick={() => setShowSettings(true)}><Settings2 /><span>API 配置</span></button><button className="icon-btn attachment-flow-entry" aria-label="附件流向" title="附件流向" aria-expanded={showFlow && view !== 'benchmark'} onClick={() => { setShowFlow(!showFlow); setSource(undefined); if (view === 'benchmark') setView('chat'); }}><PanelLeft /></button></div></header>
      {view === 'dashboard' ? <AssetDashboard key={projectId} initialSelection={factSelection} projectId={projectId} projectName={currentProject?.name} onChat={prompt => { newChat(); if (prompt) setDraft(prompt); }} onSource={selectSource} /> : view === 'benchmark' ? <DatasetView currentModel={settings.llm.model} onBack={() => setView('chat')} /> : <main className={`chat-area ${empty ? 'empty' : ''}`}>
        {error && <div className="error-banner" role="alert"><CircleAlert /><span>{error}</span>{!health && <button className="text-button" onClick={() => setRetryBoot(retryBoot + 1)}>重试连接</button>}<button className="icon-btn" aria-label="关闭错误提示" onClick={() => setError('')}><X /></button></div>}
        {backgroundRuns.length > 0 && <button className="background-run" onClick={() => void openConversation(backgroundRuns[0].conversationId)}><LoaderCircle className="spin" />{backgroundRuns.length} 段对话正在运行 · 当前对话可独立使用</button>}
        <div className="conversation-scroll" ref={scrollRef} onScroll={() => { const element = scrollRef.current; if (element) followScroll.current = element.scrollHeight - element.scrollTop - element.clientHeight < 120; }}>
          {booting || loadingChat ? <div className="chat-loading"><LoaderCircle className="spin" /><p>{booting ? '连接本地工作空间…' : '读取对话…'}</p></div> : empty ? <div className="welcome"><span className="welcome-mark">研</span><h1>今天想研究什么？</h1><p>添加财报即可清洗入库，也可以直接查询、分析和制图。</p>{!projects.length && <button className="plain-button" onClick={() => setShowProjectDialog(true)}><Plus />创建第一个项目</button>}</div> : <div className="messages" role="log" aria-label="对话消息">{messages.map(message => <MessageView key={message.id} message={message} documents={documents} onDocument={selectDocument} onSource={selectSource} onToast={notify} />)}{activeHere && run && <div className="run-progress" aria-live="polite"><div className="progress-line"><span className="progress-dot" />{run.cancelling ? '正在停止…' : stages[run.stage] || run.stage}</div><ToolTrace tools={run.tools} /></div>}</div>}
        </div>
        <div className="composer-wrap"><ApprovalCard conversationId={conversationId} onOpenConversation={id => void openConversation(id)} /><AnnotationRail items={annotationDraft.items} onChange={annotationDraft.update} disabled={sending} />{annotationDraft.storageError && <p className="error-text" role="alert">{annotationDraft.storageError}</p>}<div className="composer"><div className="attachments">{pendingDocuments.map(doc => <FileChip key={doc.id} document={doc} onClick={() => selectDocument(doc)} onRemove={() => setPendingDocuments(previous => previous.filter(item => item.id !== doc.id))} />)}{uploading > 0 && <div className="upload-progress"><LoaderCircle className="spin" />正在上传 {uploading} 个文件…</div>}</div><textarea ref={inputRef} rows={1} placeholder="发消息，或添加财报、Excel、CSV…" aria-label="发送给金融 Agent 的消息" value={draft} disabled={booting || loadingChat || sending} onChange={event => setDraft(event.target.value)} onKeyDown={onInputKeyDown} onPaste={event => { if (event.clipboardData.files.length) { event.preventDefault(); void upload(event.clipboardData.files); } }} /><div className="composer-actions"><div className="composer-left"><button className="icon-btn attach-button" aria-label="添加附件" aria-haspopup="menu" aria-expanded={showAttach} disabled={booting} onClick={() => { setShowAttach(!showAttach); setShowModel(false); }}><Plus /></button><span className="composer-context">{currentProject?.name || '请选择项目'}</span></div>{run&&<><button className="plain-button" title="当前任务完成后再处理（Alt+Enter）" disabled={sending||uploading>0||(!draft.trim()&&!pendingDocuments.length&&!annotationDraft.items.length)} onClick={()=>void send('followUp')}>排队</button><button className="icon-btn" aria-label="停止生成" disabled={run.cancelling} onClick={()=>void cancel()}><span className="stop-square" /></button></>}<button className="send-button" aria-label={run?'发送补充':'发送消息'} title={run?'补充到当前任务（Enter）':'发送消息'} disabled={(!draft.trim() && !pendingDocuments.length && !annotationDraft.items.length) || sending || uploading > 0 || booting || loadingChat || !projectId} onClick={() => void send()}>{sending ? <LoaderCircle className="spin" /> : <ArrowUp />}</button></div>{showAttach && <><button className="popover-scrim" aria-label="关闭附件菜单" onClick={() => setShowAttach(false)} /><div className="popover attach-menu"><button className="menu-item" onClick={() => fileRef.current?.click()}><Upload /><span>从电脑添加文件<small>Excel、CSV、TSV、PDF · 单文件 50 MB</small></span></button></div></>}</div>
          {empty && <div className="quick-actions">{[[Table2, '解析表格', '请解析附件，列出工作表、字段、期间和单位。'], [FileText, '对比财报', '比较不同年度的财务表现，并标明原文证据。'], [Check, '核查数据', '检查表格中的单位、同比计算和会计口径是否一致。'], [ChartNoAxesCombined, '生成图表', '根据项目资料，绘制营业收入和归母净利润的年度趋势图。']].map(([Icon, label, prompt]) => { const ActionIcon = Icon as typeof Table2; return <button key={String(label)} onClick={() => { setDraft(String(prompt)); inputRef.current?.focus(); }}><ActionIcon />{String(label)}</button>; })}</div>}
          <div className="composer-footer"><p className="composer-disclaimer">附件发送后由本会话处理；项目内共享财务数据。</p></div>
        </div></main>}
      {showFlow && view !== 'benchmark' && projectId && <AttachmentFlow key={conversationId||projectId} projectId={projectId} conversationId={conversationId} documents={documents} pending={pendingDocuments} source={source} onClearSource={()=>setSource(undefined)} onClose={()=>setShowFlow(false)} onSource={selectSource} onFacts={selection=>{setFactSelection(selection);setView('dashboard');setShowFlow(false);}} />}
    </div><input type="file" ref={fileRef} multiple accept=".xlsx,.xls,.csv,.tsv,.pdf" hidden onChange={event => { if (event.target.files) void upload(event.target.files); }} />
    {dragging && <div className="drop-overlay"><div><Upload /><h2>松开即可添加文件</h2><p>Excel、CSV、TSV、PDF · 添加到当前对话</p></div></div>}{toast && <div className="toast" role="status">{toast}</div>}
    {view === 'chat' && <SelectionReference conversationId={conversationId} disabled={sending || loadingChat} />}{rulesProject && <ProjectRules project={rulesProject} onClose={()=>setRulesProject(undefined)} />}
    {showSettings && <SettingsDialog initial={settings} onClose={() => setShowSettings(false)} onSaved={setSettings} />}
    {showProjectDialog && <Modal className="project-dialog" label="创建项目" onClose={() => { if (!projectBusy) setShowProjectDialog(false); }}><header className="settings-header"><h2>创建项目</h2><button className="icon-btn" aria-label="关闭创建项目" disabled={projectBusy} onClick={() => setShowProjectDialog(false)}><X /></button></header><form className="project-form" onSubmit={event => { event.preventDefault(); void createProject(); }}><p className="muted">每个项目独立保存资料与对话。</p><label htmlFor="project-name">项目名称</label><input id="project-name" autoFocus maxLength={100} placeholder="例如：消费行业年度财报分析" value={projectName} onChange={event => setProjectName(event.target.value)} disabled={projectBusy} />{projectError && <p className="error-text" role="alert">{projectError}</p>}<footer className="settings-footer"><button type="button" className="plain-button" disabled={projectBusy} onClick={() => setShowProjectDialog(false)}>取消</button><button type="submit" className="primary-button" disabled={!projectName.trim() || projectBusy}>{projectBusy ? '创建中…' : '创建项目'}</button></footer></form></Modal>}
  </div></AnnotationWorkspace>;
}
