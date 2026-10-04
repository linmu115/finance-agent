import { useState, type FormEvent } from 'react';
import { Settings2, MessageSquare, FileText, Globe, X, Eye, EyeOff, LoaderCircle } from 'lucide-react';
import Modal from './Modal';
import ContextCompactionFields from './ContextCompactionFields';
import { api, errorText } from './api';
import { emptySettings, type Settings, type APISection } from './types';

type Tab = 'llm' | 'ocr' | 'search' | 'runtime';
const labels: Record<Tab, string> = { llm: '主模型 API', ocr: '文档与 OCR', search:'联网搜索', runtime: '运行限制' };

function ProviderFields({ value, prefix, onChange }: { value: APISection; prefix: string; onChange: (patch: Partial<APISection>) => void }) {
  const [showKey, setShowKey] = useState(false);
  const isOcr = prefix === 'ocr',isSearch=prefix==='search';
  return <>
    <label htmlFor={`${prefix}-baseUrl`}>API 地址 <span>{isOcr ? '完整 OCR 接口地址' : 'Base URL'}</span></label>
    <input id={`${prefix}-baseUrl`} type="url" autoComplete="off" placeholder={isOcr ? 'https://ocr.example.com/recognize' : 'https://api.example.com/v1'} value={value.baseUrl} onChange={event => onChange({ baseUrl: event.target.value })} />
    {!isOcr && !isSearch && <><label htmlFor={`${prefix}-model`}>模型名称 <span>服务商提供的 Model ID</span></label>
    <input id={`${prefix}-model`} autoComplete="off" placeholder="输入模型名称" value={value.model} onChange={event => onChange({ model: event.target.value })} /></>}
    <label htmlFor={`${prefix}-key`}>API Key <span>{value.hasKey ? '已保存，留空保留' : '本地无鉴权服务可留空'}</span></label>
    <div className="password-field"><input id={`${prefix}-key`} name={`${prefix}-api-key`} type={showKey ? 'text' : 'password'} autoComplete="new-password" spellCheck={false} placeholder={value.hasKey ? '•••••••• · 已保存在本地服务' : '输入 API Key'} value={value.apiKey ?? ''} onChange={event => onChange({ apiKey: event.target.value || undefined })} /><button type="button" className="icon-btn" aria-label={showKey ? '隐藏密钥' : '显示密钥'} onClick={() => setShowKey(!showKey)}>{showKey ? <EyeOff /> : <Eye />}</button></div>
    {value.hasKey && <button type="button" className="text-button key-remove" onClick={() => onChange({ apiKey: '', hasKey: false })}>移除已存密钥</button>}
    {value.apiKey === '' && !value.hasKey && <p className="field-note">保存后将移除该服务的密钥。</p>}
  </>;
}

function validateSettings(settings: Settings, testing?: Tab) {
  for (const section of ['llm', 'embedding', 'ocr'] as const) {
    const value = settings[section];
    if (section === 'embedding') continue;
    if (section === 'ocr' && settings.ocr.mode !== 'api') continue;
    if (!value.baseUrl && !value.model && testing !== section && section === 'llm') continue;
    if (!value.baseUrl.trim() || (section !== 'ocr' && !value.model.trim())) throw new Error(`${labels[section]}：${section === 'ocr' ? '请填写完整 OCR 接口地址。' : '请填写 API 地址和模型名称。'}`);
    let url: URL;
    try { url = new URL(value.baseUrl); } catch { throw new Error(`${labels[section]}：请输入完整的 API 地址。`); }
    const local = ['localhost', '127.0.0.1', '[::1]'].includes(url.hostname);
    if (url.protocol !== 'https:' && !(url.protocol === 'http:' && local)) throw new Error(`${labels[section]}：远程服务需要 HTTPS；本地服务支持 HTTP。`);
    if (url.username || url.password || url.hash || url.search) throw new Error(`${labels[section]}：API 地址不能包含用户名、密码、查询参数或片段。`);
  }
  const { maxToolCalls, timeoutSeconds, budgetCny } = settings.runtime;
  if (!Number.isInteger(maxToolCalls) || maxToolCalls < 1 || maxToolCalls > 100) throw new Error('工具调用上限需要为 1 至 100 的整数。');
  if (!Number.isInteger(timeoutSeconds) || timeoutSeconds < 10 || timeoutSeconds > 120) throw new Error('单次代码执行时限需要为 10 至 120 秒的整数。');
  if (budgetCny !== undefined && (!Number.isFinite(budgetCny) || budgetCny <= 0)) throw new Error('费用预算需要大于 0；不设置时留空。');
  if (settings.llm.maxTokens !== undefined && (!Number.isInteger(settings.llm.maxTokens) || settings.llm.maxTokens < 128 || settings.llm.maxTokens > 131072)) throw new Error('最大输出 token 需要为 128 至 131072 的整数。');
  if (settings.llm.contextWindow !== undefined && (!Number.isInteger(settings.llm.contextWindow) || settings.llm.contextWindow < Math.max(4096, settings.llm.maxTokens || 128) || settings.llm.contextWindow > 2000000)) throw new Error('上下文窗口需要为 4096 至 2000000 的整数，且不小于最大输出。');
  for (const price of [settings.llm.inputPricePerMillionUsd, settings.llm.outputPricePerMillionUsd]) if (price !== undefined && (!Number.isFinite(price) || price < 0)) throw new Error('模型价格应为大于或等于 0 的数字。');
  if (budgetCny !== undefined && (settings.llm.inputPricePerMillionUsd === undefined || settings.llm.outputPricePerMillionUsd === undefined || !settings.runtime.usdToCny || settings.runtime.usdToCny <= 0)) throw new Error('启用人民币预算前，请在主模型高级设置填写输入、输出价格，并在运行限制填写美元兑人民币折算率。');
  const policy = settings.runtime.contextCompaction;
  if (policy) {
    if (!Number.isInteger(policy.targetTokens) || policy.targetTokens < 4096 || policy.targetTokens > 2000000) throw new Error('上下文整理阈值需要为 4096 至 2000000 的整数。');
    if (!Number.isInteger(policy.keepRecentTokens) || policy.keepRecentTokens < 1024 || policy.keepRecentTokens >= policy.targetTokens) throw new Error('近期保留量至少为 1024，且小于整理阈值。');
    if (!Number.isInteger(policy.summaryMaxTokens) || policy.summaryMaxTokens < 512 || policy.summaryMaxTokens > 32768 || policy.summaryMaxTokens >= policy.targetTokens) throw new Error('摘要输出需要为 512 至 32768 的整数，且小于整理阈值。');
  }
}

function normalizeSettings(settings: Settings): Settings {
  return { llm: { ...emptySettings.llm, ...settings.llm, apiKey: undefined }, embedding: { ...emptySettings.embedding, ...settings.embedding, enabled: false, apiKey: undefined }, ocr: { ...emptySettings.ocr, ...settings.ocr, apiKey: undefined },search:{...emptySettings.search,...settings.search,apiKey:undefined}, runtime: { ...emptySettings.runtime, ...settings.runtime } };
}

export default function SettingsDialog({ initial, onClose, onSaved }: { initial: Settings; onClose: () => void; onSaved: (settings: Settings) => void }) {
  const [tab, setTab] = useState<Tab>('llm');
  const [draft, setDraft] = useState<Settings>(() => normalizeSettings(initial));
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<{ text: string; error?: boolean }>();
  function update<K extends keyof Settings>(section: K, patch: Partial<Settings[K]>) {
    setDraft(previous => ({ ...previous, [section]: { ...previous[section], ...patch } }));
    setResult(undefined);
  }
  async function save(test = false) {
    setResult(undefined);
    try { validateSettings(draft, test ? tab : undefined); } catch (error) { setResult({ text: errorText(error), error: true }); return; }
    setBusy(true);
    try {
      const payload = structuredClone(draft);
      for (const section of ['llm', 'embedding', 'ocr'] as const) {
        payload[section].baseUrl = payload[section].baseUrl.trim().replace(/\/$/, '');
        payload[section].model = payload[section].model.trim();
      }
      const response = await api<Settings | { settings: Settings }>('/api/settings', { method: 'PUT', body: JSON.stringify(payload) });
      const saved = 'settings' in response ? response.settings : response;
      const cleaned = normalizeSettings(saved);
      setDraft(cleaned); onSaved(cleaned);
      if (test) {
        const check = await api<{ ok?: boolean; message?: string; latencyMs?: number; error?: { message?: string } }>(tab==='search'?'/api/settings/search/test':'/api/settings/test', { method: 'POST', body: JSON.stringify({ section: tab }) });
        const failed = check.ok === false || Boolean(check.error);
        setResult({ text: check.message || check.error?.message || (failed ? '连接检查未通过。' : `连接成功${check.latencyMs ? ` · ${check.latencyMs} ms` : ''}。`), error: failed });
      } else setResult({ text: '设置已保存。密钥由本地服务保管，不写入浏览器存储。' });
    } catch (error) { setResult({ text: errorText(error), error: true }); }
    finally { setBusy(false); }
  }
  function submit(event: FormEvent) { event.preventDefault(); void save(); }
  const testAvailable = tab === 'llm' || tab==='search' || tab === 'ocr' && draft.ocr.mode === 'api';
  return <Modal className="settings-dialog" label="API 与运行设置" onClose={() => { if (!busy) onClose(); }}><div className="settings-layout">
    <nav className="settings-nav" aria-label="设置分类"><h2>设置</h2>{([['llm', MessageSquare], ['ocr', FileText], ['search',Globe], ['runtime', Settings2]] as const).map(([id, Icon]) => <button type="button" key={id} className={`settings-tab ${tab === id ? 'active' : ''}`} aria-current={tab === id ? 'page' : undefined} onClick={() => { setTab(id); setResult(undefined); }}><Icon />{labels[id]}</button>)}<div className="optional-services"><p>资料检索使用全文关键词与 YAML 目录索引。<br />当前阶段不调用 Embedding 服务。</p></div><p className="settings-version">金融研究<br />本地工作空间</p></nav>
    <div className="settings-main"><header className="settings-header"><h2>{labels[tab]}</h2><button type="button" className="icon-btn" aria-label="关闭设置" disabled={busy} onClick={onClose}><X /></button></header>
    <form autoComplete="off" onSubmit={submit} noValidate><fieldset disabled={busy} className="settings-pane">
      {tab==='search'&&<><p className="settings-description">对话中的联网搜索、公告阅读和产业链研究共用此服务。原文会保存到项目，供后续引用。</p><label htmlFor="search-provider">搜索服务</label><select id="search-provider" value={draft.search.provider} onChange={event=>update('search',{provider:event.target.value as 'tavily'|'brave',baseUrl:event.target.value==='tavily'?'https://api.tavily.com':'https://api.search.brave.com'})}><option value="tavily">Tavily</option><option value="brave">Brave Search</option></select><ProviderFields prefix="search" value={{...draft.search,model:''}} onChange={patch=>update('search',patch)}/><label htmlFor="search-count">每次搜索结果数</label><input id="search-count" type="number" min="1" max="20" value={draft.search.maxResults} onChange={event=>update('search',{maxResults:Number(event.target.value)})}/><p className="settings-help">搜索与主模型分别配置。测试会发出一次小查询；已保存的来源可离线读取。</p></>}
      {tab === 'llm' && <><p className="settings-description">DeepSeek 通过 Pi 运行核心处理财报清洗、字段映射、查询、分析与回答，统一使用此处配置。</p><label htmlFor="llm-provider">接口协议</label><select id="llm-provider" value={draft.llm.provider} onChange={event => update('llm', { provider: event.target.value })}><option value="openai-compatible">OpenAI 兼容接口</option></select><ProviderFields prefix="llm" value={draft.llm} onChange={patch => update('llm', patch)} /><details className="advanced-settings"><summary>高级设置 · 上下文与价格</summary><label htmlFor="llm-context">上下文窗口 <span>tokens</span></label><input id="llm-context" type="number" min="4096" max="2000000" value={draft.llm.contextWindow ?? 128000} onChange={event => update('llm', { contextWindow: Number(event.target.value) })} /><label htmlFor="llm-output">最大输出 <span>tokens</span></label><input id="llm-output" type="number" min="128" max="131072" value={draft.llm.maxTokens ?? 8192} onChange={event => update('llm', { maxTokens: Number(event.target.value) })} /><label htmlFor="llm-input-price">输入价格 <span>美元 / 百万 tokens，可选</span></label><input id="llm-input-price" type="number" min="0" step="0.01" placeholder="未知，留空" value={draft.llm.inputPricePerMillionUsd ?? ''} onChange={event => update('llm', { inputPricePerMillionUsd: event.target.value ? Number(event.target.value) : undefined })} /><label htmlFor="llm-output-price">输出价格 <span>美元 / 百万 tokens，可选</span></label><input id="llm-output-price" type="number" min="0" step="0.01" placeholder="未知，留空" value={draft.llm.outputPricePerMillionUsd ?? ''} onChange={event => update('llm', { outputPricePerMillionUsd: event.target.value ? Number(event.target.value) : undefined })} /><p className="field-note">按服务商当前报价填写。未填写时费用显示为未知。</p></details><p className="settings-help">保存后可发起真实连接检查。检查会向已配置的服务商发送一个小请求，可能产生少量费用。</p></>}
      {tab === 'ocr' && <><p className="settings-description">Excel 和 CSV 直接读取单元格；OCR 用于扫描页和图片中的文字。</p><label htmlFor="ocr-mode">识别方式</label><select id="ocr-mode" value={draft.ocr.mode} onChange={event => update('ocr', { mode: event.target.value as 'local' | 'api' })}><option value="local">本地解析与 OCR</option><option value="api">外部 OCR 服务 API</option></select>{draft.ocr.mode === 'api' && <ProviderFields prefix="ocr" value={draft.ocr} onChange={patch => update('ocr', patch)} />}<div className="format-list"><div><b>Excel / CSV / TSV</b><span>保留工作表、行列和单元格位置，数值进入结构化数据库。</span></div><div><b>文字 PDF</b><span>读取原文、页码和表格，并保存可引用的来源。</span></div><div><b>扫描 PDF</b><span>使用已配置的 OCR；识别失败会显示失败原因，不填造数据。</span></div></div>{draft.ocr.mode === 'api' && <p className="settings-help">扫描页会发送给此服务。接口需接受 JSON 字段 image_base64、language，返回 text 字符串；按需使用 Bearer API Key 鉴权。</p>}</>}
      {tab === 'runtime' && <><p className="settings-description">限制单次分析消耗。自由分析代码在独立容器中执行。</p><label htmlFor="runtime-calls">工具调用上限</label><input id="runtime-calls" type="number" min="1" max="100" value={draft.runtime.maxToolCalls} onChange={event => update('runtime', { maxToolCalls: Number(event.target.value) })} /><label htmlFor="runtime-timeout">单次代码执行时限 <span>秒</span></label><input id="runtime-timeout" type="number" min="10" max="120" value={draft.runtime.timeoutSeconds} onChange={event => update('runtime', { timeoutSeconds: Number(event.target.value) })} /><label htmlFor="runtime-budget">费用预算 <span>元，可选</span></label><input id="runtime-budget" type="number" min="0.01" step="0.01" value={draft.runtime.budgetCny ?? ''} placeholder="不设置" onChange={event => update('runtime', { budgetCny: event.target.value ? Number(event.target.value) : undefined })} /><label htmlFor="runtime-exchange">美元兑人民币折算率 <span>启用费用预算时必填</span></label><input id="runtime-exchange" type="number" min="0.01" step="0.01" value={draft.runtime.usdToCny ?? ''} placeholder="使用你确定的折算率" onChange={event => update('runtime', { usdToCny: event.target.value ? Number(event.target.value) : undefined })} /><p className="settings-help">预算核算需要同时填写主模型输入、输出报价和折算率；缺少价格时费用显示为未知。容器默认断网，限制资源，执行时限不超过 120 秒。</p></>}
      {tab === 'runtime' && <ContextCompactionFields value={draft.runtime.contextCompaction} onChange={contextCompaction => update('runtime', { contextCompaction })} />}
    </fieldset><div className={`settings-result ${result?.error ? 'error-text' : ''}`} role="status" aria-live="polite">{result?.text}</div><footer className="settings-footer">{testAvailable && <button type="button" className="plain-button" disabled={busy} onClick={() => void save(true)}>{busy && <LoaderCircle className="spin" />}保存并测试连接</button>}<button type="submit" className="primary-button" disabled={busy}>{busy ? '处理中…' : '保存设置'}</button></footer></form></div>
  </div></Modal>;
}
