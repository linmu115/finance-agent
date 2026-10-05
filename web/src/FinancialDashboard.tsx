import { useEffect, useMemo, useRef, useState } from 'react';
import { ArrowUpRight, ChartNoAxesCombined, Database, Download, FileText, LoaderCircle, RefreshCw, Upload, X } from 'lucide-react';
import { api, errorText, isAbort } from './api';
import { docStatus } from './MessageView';
import { chartSource } from './chartValues';
import type { Source } from './types';

type Fact = {
  fact_id: string; document_id: string; metric: string; label?: string; statement?: string; company: string;
  year?: number; period: string; scope: string; currency: string; value: string; raw_value?: string; raw_unit?: string;
  normalized_unit?: string; normalization_engine?: string; version?: string; restatement?: string; dimensions?: Record<string, unknown>; source_ref?: Source | string;
  definition?: string; definition_scope?: string;
};
type Catalog = {
  database_path?: string; documents_path?: string; index_path?: string; companies?: string[]; periods?: string[]; scopes?: string[];
  currencies?: string[]; metrics?: { metric: string; label: string; statement?: string; count?: number }[];
  counts?: { documents: number; pages: number; tables: number; facts: number }; processing?: { message?: string; state?: string; progress?: number }[];
};
type DataDocument = { document_id?: string; id?: string; original_name?: string; name?: string; state?: string; status?: string; fact_count?: number; table_count?: number; processing?: { message?: string; progress?: number } };
type Dashboard = { documents: DataDocument[]; facts: Fact[]; catalog: Catalog; total?: number; truncated?: boolean };
const categories = [['all', '全部财务数据'], ['income', '利润表'], ['balance', '资产负债表'], ['cashflow', '现金流量表'], ['ratios', '财务比率'], ['segment', '分部披露'], ['notes', '附注']] as const;
const currencyNames: Record<string, string> = { CNY: '人民币', USD: '美元', HKD: '港币', EUR: '欧元', percent: '百分比（%）', 'CNY/share': '人民币 / 股', 'USD/share': '美元 / 股', '': '无币种' };
const scopeNames: Record<string, string> = { consolidated_CAS: '合并 · 中国准则', parent_CAS: '母公司 · 中国准则', consolidated_IFRS: '合并 · 国际准则', parent_IFRS: '母公司 · 国际准则', unspecified: '未注明口径', consolidated: '合并', parent: '母公司' };
function currencyLabel(value: string) { const perShares = /^([A-Z]{3})\/(\d+)shares?$/.exec(value); return perShares ? `${currencyNames[perShares[1]] || perShares[1]} / ${perShares[2]} 股` : currencyNames[value] || value; }
const colors = ['#343434', '#4c7198', '#a5744b', '#89749e', '#597d8e', '#a36773', '#7d7d58', '#71839b'];
const unique = (items: string[]) => [...new Set(items.filter(Boolean))].sort((a, b) => a.localeCompare(b, 'zh-CN', { numeric: true }));
const dimensionText = (value?: Record<string, unknown>) => Object.entries(value || {}).sort().map(([key, item]) => `${key}=${String(item)}`).join(' · ');
const format = (value: string | number) => String(value).replace(/^([+-]?)(\d+)(\.\d+)?$/, (_, sign: string, integer: string, fraction: string = '') => sign + integer.replace(/\B(?=(\d{3})+(?!\d))/g, ',') + fraction);
const exactValue = (value: string) => value.includes('.') ? value.replace(/0+$/, '').replace(/\.$/, '') : value;
function unit(fact: Fact) { const label: Record<string, string> = { CNY: '元（人民币）', USD: '美元', HKD: '港元', 'CNY/share': '元/股（人民币）', 'USD/share': '美元/股', percent: '%' }; if (fact.normalized_unit) return label[fact.normalized_unit] || currencyLabel(fact.normalized_unit); return (fact.raw_unit?.includes('%') || fact.raw_unit?.includes('％') ? '%' : /股|倍|人|吨/.test(fact.raw_unit || '') ? fact.raw_unit! : fact.currency ? `${fact.currency} 元` : fact.raw_unit || '数值'); }
function download(blob: Blob, name: string) { const url = URL.createObjectURL(blob); const link = document.createElement('a'); link.href = url; link.download = name; link.click(); setTimeout(() => URL.revokeObjectURL(url), 1500); }

export default function FinancialDashboard({ embedded=false, refreshToken=0, companies, initialSelection, projectId, projectName, onChat, onSource }: { embedded?:boolean; refreshToken?:number; companies?:string[]; initialSelection?:{documentId:string;metric:string;factId:string}; projectId: string; projectName?: string; onChat: (prompt?: string) => void; onSource: (source: Source) => void }) {
  const [data, setData] = useState<Dashboard>();
  const [facts, setFacts] = useState<Fact[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [refresh, setRefresh] = useState(0);
  const [category, setCategory] = useState('all');
  const [company, setCompany] = useState('');
  const [period, setPeriod] = useState('');
  const [periodType, setPeriodType] = useState('all');
  const [scope, setScope] = useState('');
  const [currency, setCurrency] = useState('');
  const [version, setVersion] = useState('');
  const [dimension, setDimension] = useState('');
  const [documentId, setDocumentId] = useState('');
  const [metrics, setMetrics] = useState<string[]>([]);
  const [xAxis, setXAxis] = useState<'period' | 'company'>('period');
  const [chartType, setChartType] = useState<'line' | 'bar'>('bar');
  const [selected, setSelected] = useState<Fact>();
  const [page, setPage] = useState(0);
  const svgRef = useRef<SVGSVGElement>(null);
  const catalog = data?.catalog || {};
  const filters = useMemo(() => ({ ...(category !== 'all' ? { statement: category } : {}), ...(company ? { company } : {}), ...(period ? { period } : periodType !== 'all' ? { periods: (catalog.periods || []).filter(item => periodType === 'annual' ? /FY|^\d{4}$/.test(item) : periodType === 'quarter' ? /Q[1-4]/.test(item) : periodType === 'interim' ? /H[12]|[369]M/.test(item) : periodType === 'range' ? /^\d{4}-\d{2}-\d{2}\/\d{4}-\d{2}-\d{2}$/.test(item) : /^\d{4}-\d{2}-\d{2}$/.test(item)) } : {}), ...(scope ? { scope } : {}), ...(currency ? { currency } : {}), ...(version ? { version } : {}), ...(documentId ? { document_id: documentId } : {}), ...(dimension ? { dimensions: Object.fromEntries([dimension.split('=', 2)]) } : {}) }), [category, company, period, scope, currency, version, dimension, documentId, periodType, JSON.stringify(catalog.periods || [])]);
  useEffect(() => { setCategory('all'); setCompany(''); setPeriod(''); setPeriodType('all'); setScope(''); setCurrency(''); setVersion(''); setDimension(''); setDocumentId(''); setMetrics([]); setData(undefined); setFacts([]); setSelected(undefined); }, [projectId]);
  useEffect(()=>{if(initialSelection){setDocumentId(initialSelection.documentId);setMetrics([initialSelection.metric]);}},[initialSelection,projectId]);
  useEffect(() => {
    if (!projectId) { setLoading(false); return; }
    const controller = new AbortController();
    api<Dashboard>(`/api/projects/${encodeURIComponent(projectId)}/dashboard`, { signal: controller.signal })
      .then(result => { setData(result); setError(''); })
      .catch(reason => { if (!isAbort(reason)) { setError(errorText(reason)); setLoading(false); } });
    return () => controller.abort();
  }, [projectId, refresh, refreshToken]);
  const availableMetrics = useMemo(() => {
    const found = new Map<string, string>();
    for (const item of catalog.metrics || []) if (category === 'all' || item.statement === category) found.set(item.metric, item.label || item.metric);
    if (!catalog.metrics) for (const item of data?.facts || []) if (category === 'all' || item.statement === category) found.set(item.metric, item.label || item.metric);
    return [...found].sort((a, b) => a[1].localeCompare(b[1], 'zh-CN'));
  }, [catalog.metrics, data?.facts, category]);
  useEffect(() => { if (availableMetrics.length) setMetrics(previous => { const valid = previous.filter(metric => availableMetrics.some(([id]) => id === metric)); return valid.length ? valid.length === previous.length ? previous : valid : [availableMetrics.find(([id]) => id === 'revenue')?.[0] || availableMetrics[0][0]]; }); else setMetrics(previous => previous.length ? [] : previous); }, [availableMetrics]);
  useEffect(()=>{if(initialSelection&&availableMetrics.some(([id])=>id===initialSelection.metric))setMetrics([initialSelection.metric]);},[initialSelection,availableMetrics]);
  const focusedFact=useRef('');
  useEffect(()=>{if(initialSelection&&focusedFact.current!==initialSelection.factId){const fact=facts.find(f=>f.fact_id===initialSelection.factId);if(fact){setSelected(fact);focusedFact.current=fact.fact_id;}}},[initialSelection,facts]);
  const metricKey = JSON.stringify(metrics);
  const hasData = Boolean(data);
  useEffect(() => {
    if (!projectId || !hasData) return;
    if (!metrics.length) { setFacts([]); setTotal(0); setLoading(false); return; }
    const controller = new AbortController(); setLoading(true); setSelected(undefined);
    const queryFilters = { ...filters, metrics, ...(companies ? {companies: company && companies.includes(company) ? [company] : companies} : {}) };
    async function loadComplete() {
      // A new batch may commit between pages. Retry one coherent read instead of
      // combining overlapping pages from different totals into a partial chart.
      for (let attempt = 0; attempt < 2; attempt++) {
        const collected = new Map<string, Fact>(); let offset = 0; let expected: number | undefined; let changed = false;
        while (true) {
          const result = await api<{ items: Fact[]; total: number; limit?: number }>(`/api/projects/${encodeURIComponent(projectId)}/financial-data?limit=5000&offset=${offset}&filters=${encodeURIComponent(JSON.stringify(queryFilters))}`, { signal: controller.signal });
          if (expected !== undefined && expected !== result.total) { changed = true; break; }
          expected = result.total;
          for (const item of result.items) collected.set(item.fact_id, item);
          offset += result.items.length;
          if (offset >= expected) break;
          if (!result.items.length) throw new Error('数据分页尚未返回完整结果，请刷新看板。');
        }
        if (!changed && collected.size === expected) { setFacts([...collected.values()]); setTotal(expected); setError(''); return; }
      }
      throw new Error('财报正在提交新数据，请刷新以读取完整筛选结果。');
    }
    void loadComplete().catch(reason => { if (!isAbort(reason)) { setError(errorText(reason)); setFacts([]); setTotal(0); } }).finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [projectId, filters, refresh, metricKey, hasData, JSON.stringify(companies), refreshToken]);
  useEffect(() => { if (loading) return; const timer = setInterval(() => setRefresh(value => value + 1), 6000); return () => clearInterval(timer); }, [loading]);
  useEffect(() => setPage(0), [filters, metrics]);
  const shown = facts.filter(fact => !metrics.length || metrics.includes(fact.metric));
  const dimensions = unique([...(data?.facts || []), ...facts].flatMap(fact => Object.entries(fact.dimensions || {}).map(([key, value]) => `${key}=${String(value)}`)));
  const versions = unique([...(data?.facts || []), ...facts].map(fact => fact.version || fact.restatement || ''));
  const units = unique(shown.map(fact => `${fact.currency || ''} ${unit(fact)}`));
  const xs = unique(shown.map(fact => String(fact[xAxis])));
  const groups = new Map<string, { name: string; values: Map<string, Fact[]> }>();
  for (const fact of shown) {
    const parts = [fact.label || fact.metric, xAxis === 'period' ? fact.company : fact.period, scopeNames[fact.scope] || fact.scope, fact.version || fact.restatement, dimensionText(fact.dimensions)].filter(Boolean);
    const key = JSON.stringify([fact.metric, xAxis === 'period' ? fact.company : fact.period, fact.scope, fact.currency, unit(fact), fact.version || fact.restatement || '', dimensionText(fact.dimensions)]);
    let group = groups.get(key); if (!group) { group = { name: parts.join(' · '), values: new Map() }; groups.set(key, group); }
    const x = String(fact[xAxis]); group.values.set(x, [...(group.values.get(x) || []), fact]);
  }
  const series = [...groups.values()];
  let roundedDisclosures = 0;
  const conflicting = series.some(group => [...group.values.entries()].some(([x,values]) => {
    const chosen=chartSource(values);
    if(!chosen)return true;
    if(new Set(values.map(fact=>exactValue(fact.value))).size>1)roundedDisclosures++;
    group.values.set(x,[chosen,...values.filter(value=>value!==chosen)]);
    return false;
  }));
  const chartIssue = loading ? '正在读取完整筛选数据…' : !shown.length ? '选择有数据的财务分类与指标后，图表会显示在这里。' : units.length > 1 ? '当前指标包含不同币种或计量单位，请筛选币种或分别选择同单位指标。' : conflicting ? '同一横轴位置存在不同数值，请进一步筛选口径、版本、维度或来源文件；明细保留了全部记录。' : series.length > 16 ? '当前系列较多，请筛选公司、期间、口径或维度，将系列缩小到 16 组以内。' : xs.length > 40 ? '横轴超过 40 项，请缩小公司或期间范围。' : total > facts.length ? `当前筛选共 ${total} 条，仅加载 ${facts.length} 条；请缩小范围后制图，CSV 可导出全部筛选结果。` : '';
  const W = 960, H = 370, left = 100, right = 30, top = 26, bottom = 72;
  const numeric = shown.map(fact => Number(fact.value)).filter(Number.isFinite);
  const min = numeric.reduce((value, item) => Math.min(value, item), 0), max = numeric.reduce((value, item) => Math.max(value, item), 0), range = max - min || 1;
  const y = (value: number) => top + (max - value) / range * (H - top - bottom);
  const step = (W - left - right) / Math.max(1, xs.length), x = (index: number) => left + step * (index + .5);
  function selectSource(fact: Fact) { const source = typeof fact.source_ref === 'object' ? fact.source_ref : { sourceId: fact.source_ref }; onSource({ ...source, documentId: source?.documentId || source?.document_id || fact.document_id, title: `${fact.company} · ${fact.label || fact.metric} · ${fact.period}` }); }
  async function exportChart(png = false) {
    if (!svgRef.current) return;
    const ns = 'http://www.w3.org/2000/svg';
    const exported = document.createElementNS(ns, 'svg');
    const exportHeight = H + 80 + Math.ceil(series.length / 2) * 20;
    exported.setAttribute('xmlns', ns); exported.setAttribute('viewBox', `0 0 ${W} ${exportHeight}`); exported.setAttribute('width', String(W)); exported.setAttribute('height', String(exportHeight));
    const background = document.createElementNS(ns, 'rect'); background.setAttribute('width', String(W)); background.setAttribute('height', String(exportHeight)); background.setAttribute('fill', '#fff'); exported.append(background);
    function caption(text: string, atX: number, atY: number, size: number, color: string) { const element = document.createElementNS(ns, 'text'); element.setAttribute('x', String(atX)); element.setAttribute('y', String(atY)); element.setAttribute('font-size', String(size)); element.setAttribute('font-family', 'Microsoft YaHei, Arial, sans-serif'); element.setAttribute('fill', color); element.textContent = text; exported.append(element); }
    caption(metrics.map(metric => availableMetrics.find(([id]) => id === metric)?.[1] || metric).join(' / '), 30, 30, 18, '#222');
    caption(`${projectName || '财报数据'} · 横轴：${xAxis === 'period' ? '期间' : '公司'} · 单位：${unit(shown[0])}`, 30, 52, 11, '#888');
    const plot = svgRef.current.cloneNode(true) as SVGSVGElement; plot.setAttribute('x', '0'); plot.setAttribute('y', '62'); plot.setAttribute('width', String(W)); plot.setAttribute('height', String(H)); exported.append(plot);
    series.forEach((group, index) => { const atX = 30 + index % 2 * (W / 2), atY = H + 80 + Math.floor(index / 2) * 20; const marker = document.createElementNS(ns, 'rect'); marker.setAttribute('x', String(atX)); marker.setAttribute('y', String(atY - 8)); marker.setAttribute('width', '8'); marker.setAttribute('height', '8'); marker.setAttribute('fill', colors[index % colors.length]); exported.append(marker); caption(group.name, atX + 14, atY, 9, '#777'); });
    const blob = new Blob([new XMLSerializer().serializeToString(exported)], { type: 'image/svg+xml;charset=utf-8' });
    if (!png) { download(blob, '财报图表.svg'); return; }
    const url = URL.createObjectURL(blob); const image = new Image();
    image.onload = () => { const canvas = document.createElement('canvas'); canvas.width = W * 2; canvas.height = exportHeight * 2; const ctx = canvas.getContext('2d'); if (ctx) { ctx.fillStyle = '#ffffff'; ctx.fillRect(0, 0, canvas.width, canvas.height); ctx.drawImage(image, 0, 0, canvas.width, canvas.height); canvas.toBlob(result => { if (result) download(result, '财报图表.png'); }); } URL.revokeObjectURL(url); };
    image.onerror = () => { URL.revokeObjectURL(url); setError('图表导出失败，请使用 SVG 下载。'); }; image.src = url;
  }
  const csv = `/api/projects/${encodeURIComponent(projectId)}/financial-data?format=csv&filters=${encodeURIComponent(JSON.stringify({ ...filters, ...(metrics.length ? { metrics } : {}), ...(companies ? {companies: company && companies.includes(company) ? [company] : companies} : {}) }))}`;
  const activeDocs = (data?.documents || []).filter(doc => ['queued', 'parsing', 'normalizing', 'processing', 'validating'].includes(doc.state || doc.status || ''));
  return <section className={`financial-dashboard ${embedded ? 'embedded' : ''}`}>
    <header className="workspace-heading"><div><div className="workspace-eyebrow">{projectName || '当前项目'} / 共享数据</div><h1>财报看板</h1><p>按财务分类查看数据，选择指标与坐标轴，点击数值追溯原文。</p></div><div className="workspace-actions"><button className="plain-button" onClick={() => setRefresh(value => value + 1)}><RefreshCw className={loading ? 'spin' : ''} />刷新</button><button className="primary-button" onClick={() => onChat()}><Upload />在对话中添加财报</button></div></header>
    {error && <p className="error-banner" role="alert">{error}</p>}
    <div className="dashboard-summary">{[['财报资料', catalog.counts?.documents || 0, '份'], ['原文页面', catalog.counts?.pages || 0, '页'], ['标准数据', catalog.counts?.facts || 0, '条'], ['正在处理', activeDocs.length, '份']].map(([label, value, suffix]) => <div key={label}><span>{label}</span><strong>{value}<small>{suffix}</small></strong></div>)}</div>
    {activeDocs.length > 0 && <div className="dashboard-processing" aria-live="polite"><LoaderCircle className="spin" /><div><b>会话正在处理财报，已入库的数据会逐步显示</b><span>{catalog.processing?.map(job => job.message).filter(Boolean).join('；') || activeDocs.map(doc => `${doc.original_name || doc.name} · ${docStatus(doc.state || doc.status || '')}`).join('；')}</span></div></div>}
    {data?.facts.some(fact => fact.normalization_engine === 'legacy_rules') && <div className="dashboard-legacy"><div><b>此项目包含旧版提取记录</b><span>重新清洗后，模型会补全字段、期间与分类，并更新共享看板。</span></div><button className="plain-button" onClick={() => onChat('请重新清洗当前项目的全部财报资料，使用 LangExtract 理解全部财务主表和附注表，保留原始来源和处理版本，更新数据库及看板。')}>在对话中重新清洗</button></div>}
    <nav className="statement-tabs" aria-label="财务报表分类">{categories.map(([id, label]) => <button key={id} className={category === id ? 'active' : ''} aria-pressed={category === id} onClick={() => setCategory(id)}>{label}</button>)}</nav>
    <div className="dashboard-filters"><label data-asset-scoped={companies!==undefined}>公司<select aria-label="公司" value={company} onChange={event => setCompany(event.target.value)}><option value="">全部公司</option>{(companies || catalog.companies || unique(facts.map(fact => fact.company))).map(item => <option key={item}>{item}</option>)}</select></label><label>期间<select aria-label="期间" value={period} onChange={event => setPeriod(event.target.value)}><option value="">全部期间</option>{(catalog.periods || unique(facts.map(fact => fact.period))).map(item => <option key={item}>{item}</option>)}</select></label><label>期间类型<select aria-label="期间类型" value={periodType} onChange={event => { setPeriodType(event.target.value); setPeriod(''); }}><option value="all">全部期间类型</option><option value="annual">年度</option><option value="quarter">季度</option><option value="interim">累计 / 中期</option><option value="point">时点</option><option value="range">跨年 / 自定义区间</option></select></label><label>会计口径<select aria-label="会计口径" value={scope} onChange={event => setScope(event.target.value)}><option value="">全部口径</option>{(catalog.scopes || unique(facts.map(fact => fact.scope))).map(item => <option key={item} value={item}>{scopeNames[item] || item}</option>)}</select></label><label>币种<select aria-label="币种" value={currency} onChange={event => setCurrency(event.target.value)}><option value="">全部币种</option>{(catalog.currencies || unique(facts.map(fact => fact.currency))).filter(Boolean).map(item => <option key={item} value={item}>{currencyLabel(item)}</option>)}</select></label><label>数据版本<select aria-label="数据版本" value={version} onChange={event => setVersion(event.target.value)}><option value="">全部版本</option>{versions.map(item => <option key={item}>{item}</option>)}</select></label><label>分部 / 维度<select aria-label="分部 / 维度" value={dimension} onChange={event => setDimension(event.target.value)}><option value="">全部维度</option>{dimensions.map(item => <option key={item}>{item}</option>)}</select></label><label className="document-filter">来源文件<select aria-label="来源文件" value={documentId} onChange={event => setDocumentId(event.target.value)}><option value="">全部文件</option>{(data?.documents || []).map(doc => <option key={doc.document_id || doc.id} value={doc.document_id || doc.id}>{doc.original_name || doc.name}</option>)}</select></label></div>
    {!loading && !catalog.counts?.facts && !facts.length ? <div className="dashboard-empty"><Database /><h2>上传财报后，标准数据会出现在这里</h2><p>在任一对话中添加附件并发送，Pi 会话会读取主表与附注、清洗入库，并更新同项目的共享看板。</p><button className="primary-button" onClick={() => onChat()}>打开对话 <ArrowUpRight /></button></div> : <>
      <section className="dashboard-chart"><div className="chart-settings"><label>横轴<select aria-label="横轴" value={xAxis} onChange={event => setXAxis(event.target.value as 'period' | 'company')}><option value="period">期间</option><option value="company">公司</option></select></label><div className="metric-control"><span>纵轴指标 <small>最多 3 个</small></span><div className="metric-selects">{metrics.map((metric, index) => <div key={index}><select aria-label={`纵轴指标 ${index + 1}`} value={metric} onChange={event => setMetrics(previous => previous.map((item, at) => at === index ? event.target.value : item))}>{availableMetrics.filter(([id]) => id === metric || !metrics.includes(id)).map(([id, label]) => <option key={id} value={id}>{label}</option>)}</select>{metrics.length > 1 && <button className="icon-btn" aria-label={`移除指标 ${index + 1}`} onClick={() => setMetrics(previous => previous.filter((_, at) => at !== index))}><X /></button>}</div>)}{metrics.length < Math.min(3, availableMetrics.length) && <button className="text-button" onClick={() => setMetrics(previous => [...previous, availableMetrics.find(([id]) => !previous.includes(id))![0]])}>+ 添加指标</button>}</div></div><div className="chart-switch" role="group" aria-label="图表类型"><button aria-pressed={chartType === 'bar'} onClick={() => setChartType('bar')}>柱状</button><button aria-pressed={chartType === 'line'} onClick={() => setChartType('line')}>折线</button></div></div>
      <div className="chart-title"><h2>{metrics.map(metric => availableMetrics.find(([id]) => id === metric)?.[1] || metric).join(' / ') || '财务指标'}</h2><span>{units.length === 1 ? unit(shown[0]) : '选择同单位指标'} · 点击图中数据查看明细</span></div>
      {chartIssue ? <div className="chart-empty"><ChartNoAxesCombined /><p>{chartIssue}</p></div> : <div className="financial-chart-wrap"><svg ref={svgRef} viewBox={`0 0 ${W} ${H}`} xmlns="http://www.w3.org/2000/svg" role="img" aria-label={`${metrics.join('、')} 财务图表`} style={{ fontFamily: 'Microsoft YaHei, Arial, sans-serif', background: 'white' }}><rect width={W} height={H} fill="white" />{Array.from({ length: 5 }, (_, i) => max - range * i / 4).map((value, i) => <g key={i}><line x1={left} x2={W - right} y1={y(value)} y2={y(value)} stroke="#eaeaea" /><text x={left - 12} y={y(value) + 4} textAnchor="end" fill="#777" fontSize="11">{Intl.NumberFormat('zh-CN', { notation: 'compact', maximumFractionDigits: 2 }).format(value)}</text></g>)}<line x1={left} x2={W - right} y1={y(0)} y2={y(0)} stroke="#aaa" />{xs.map((item, i) => <text key={item} x={x(i)} y={H - bottom + 28} textAnchor="middle" fill="#666" fontSize="11">{item.length > 16 ? item.slice(0, 15) + '…' : item}</text>)}{series.map((group, si) => <g key={group.name}>{chartType === 'line' && <path d={xs.map((item, xi) => { const value = group.values.get(item)?.[0]; return value ? `${xi === 0 || !group.values.has(xs[xi - 1]) ? 'M' : 'L'}${x(xi)},${y(Number(value.value))}` : ''; }).join(' ')} fill="none" stroke={colors[si % colors.length]} strokeWidth="2" />}{xs.map((item, xi) => { const fact = group.values.get(item)?.[0]; if (!fact) return null; const value = Number(fact.value), barWidth = Math.max(2, Math.min(42, step * .7 / series.length)), at = x(xi) - series.length * barWidth / 2 + si * barWidth; const label = `${group.name} ${item} ${format(fact.value)} ${unit(fact)}`; return chartType === 'bar' ? <rect key={item} role="button" tabIndex={0} aria-label={label} x={at} y={Math.min(y(0), y(value))} width={barWidth - 1} height={Math.max(1, Math.abs(y(0) - y(value)))} fill={colors[si % colors.length]} rx="2" onClick={() => setSelected(fact)} onKeyDown={event => { if (event.key === 'Enter') setSelected(fact); }}><title>{label}</title></rect> : <circle key={item} role="button" tabIndex={0} aria-label={label} cx={x(xi)} cy={y(value)} r="5" fill={colors[si % colors.length]} onClick={() => setSelected(fact)} onKeyDown={event => { if (event.key === 'Enter') setSelected(fact); }}><title>{label}</title></circle>; })}</g>)}<text x={left} y={H - 14} fill="#888" fontSize="10">单位：{unit(shown[0])} · {projectName || '财报数据'}</text></svg></div>}
      {!chartIssue && <div className="chart-legend">{series.map((group, index) => <span key={group.name}><i style={{ background: colors[index % colors.length] }} />{group.name}</span>)}</div>}<footer className="chart-footer"><span>{roundedDisclosures ? '同口径披露存在舍入差异，图表采用更精确的原值；全部来源保留在明细中。' : '相同坐标的相同数值合并显示，全部来源保留在明细中。'}</span><button className="text-button" disabled={Boolean(chartIssue)} onClick={() => void exportChart()}><Download />SVG</button><button className="text-button" disabled={Boolean(chartIssue)} onClick={() => void exportChart(true)}><Download />PNG</button></footer></section>
      {selected && <div className="selected-fact"><div><strong>{selected.label || selected.metric}</strong><span>{selected.company} · {selected.period} · {scopeNames[selected.scope] || selected.scope}</span><b>{format(selected.value)} <small>{unit(selected)}</small></b><span>原文：{selected.raw_value || selected.value} {selected.raw_unit || ''}{dimensionText(selected.dimensions) ? ` · ${dimensionText(selected.dimensions)}` : ''}</span>{selected.definition_scope && <span>口径说明：{selected.definition_scope}</span>}</div><button className="plain-button" onClick={() => selectSource(selected)}><FileText />查看原文</button><button className="plain-button" onClick={() => onChat('请基于这条已披露财务数据继续分析，保留期间、单位、会计口径、数据版本和来源，必要时查询更多同口径数据。\n\n'+JSON.stringify(selected,null,2)+'\n\n我的问题：')}>就此分析</button><button className="icon-btn" aria-label="关闭数据详情" onClick={() => setSelected(undefined)}><X /></button></div>}
      <section className="dashboard-data"><div className="section-heading"><h2>数据明细 <span>{shown.length} 条{total > facts.length ? ` / 筛选共 ${total} 条` : ''}</span></h2><a className="plain-button" href={csv} download onClick={event => { event.preventDefault(); if (loading) return; void fetch(csv).then(async response => { if (!response.ok) throw new Error(`导出失败（HTTP ${response.status}）`); download(await response.blob(), "财报数据.csv"); }).catch(reason => setError(errorText(reason))); }}><Download />导出当前筛选 CSV</a></div><div className="table-scroll"><table><thead><tr>{['公司 / 指标', '期间', '标准数值', '单位', '会计口径', '版本 / 维度', '来源'].map(label => <th key={label}>{label}</th>)}</tr></thead><tbody>{shown.slice(page * 30, page * 30 + 30).map(fact => <tr key={fact.fact_id}><td><button className="data-label" onClick={() => setSelected(fact)}><b>{fact.label || fact.metric}</b><small>{fact.company}</small></button></td><td>{fact.period}</td><td className="numeric" title={fact.value}>{fact.value}</td><td>{unit(fact)}</td><td>{scopeNames[fact.scope] || fact.scope}</td><td>{fact.version || fact.restatement || '原披露'}<small className="dimension-text">{dimensionText(fact.dimensions)}</small></td><td><button className="text-button" onClick={() => selectSource(fact)}><FileText />原文</button></td></tr>)}</tbody></table></div><div className="data-pagination"><span>{shown.length ? `${page * 30 + 1}–${Math.min(shown.length, page * 30 + 30)} / ${shown.length}` : '暂无匹配数据'}</span><button className="plain-button" disabled={!page} onClick={() => setPage(value => value - 1)}>上一页</button><button className="plain-button" disabled={(page + 1) * 30 >= shown.length} onClick={() => setPage(value => value + 1)}>下一页</button></div></section>
    </>}
    <details className="storage-details"><summary><Database />资料与数据存在哪里</summary><dl><dt>财务数据库</dt><dd>{catalog.database_path || '等待项目数据目录'}</dd><dt>原始资料</dt><dd>{catalog.documents_path || '—'}</dd><dt>全文与 YAML 索引</dt><dd>{catalog.index_path || '—'}</dd></dl><div className="storage-documents">{data?.documents.map(doc => <div key={doc.document_id || doc.id}><FileText /><span>{doc.original_name || doc.name}</span><small>{docStatus(doc.state || doc.status || '')} · {doc.fact_count || 0} 条数据</small></div>)}</div></details>
  </section>;
}
