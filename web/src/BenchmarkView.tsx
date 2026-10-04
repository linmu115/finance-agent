import { useEffect, useMemo, useState } from 'react';
import { ClipboardCheck, RefreshCw, LoaderCircle, Download, ArrowLeft, Check, X, Minus, Clock3, ChevronRight, Copy, FileCheck2, Monitor, Database, BrainCircuit, ShieldCheck } from 'lucide-react';
import { api, errorText, safeArtifactUrl } from './api';
import type { BenchmarkResults } from './types';

type RecordValue = Record<string, unknown>;
type Tab = 'overview' | 'model' | 'components';
const statusLabels: Record<string, string> = { passed: '通过', partial: '部分完成', pass: '通过', failed: '未通过', fail: '未通过', blocked: '阻塞', skipped: '未执行', not_run: '未执行', completed: '已完成', running: '运行中', pending: '待执行', queued: '排队中', cancelled: '已取消' };
const categoryLabels: Record<string, string> = { cn_extract: '中文字段提取', cn_calculate: '财务计算', cn_audit: '真实性核查', cn_abstain: '证据不足拒答', cn_ocr: '扫描页识别', finqa_single: 'FinQA 单步推理', finqa_multi: 'FinQA 多步推理' };
const fieldLabels: Record<string, string> = { frontend: '前端', parser: '文档解析', model: '模型', path: '证据文件', file: '证据文件', report: '报告', url: '证据地址', details: '说明', detail: '说明', message: '说明', summary: '说明', result: '结果', expected: '预期', actual: '实际', reason: '原因', status: '状态', passed: '通过', total: '总数', failed: '失败', count: '数量', scope: '验证范围', limitation: '限制', limitations: '限制', evidence: '证据', check: '检查', checked: '已检查', required: '要求', name: '名称', sha256: 'SHA-256', container_runs: '容器运行编号', visual_check: '图像视觉核对', service_events: '服务核验事件数', container_probe: '容器检查', injection_actually_returned_by_tool: '工具实际读到注入内容', tools_remained_allowlisted: '工具保持在许可范围', all_requests_host_bound_to_project: '请求绑定当前项目', task_terminal: '任务最终状态', runId: '运行编号', run_id: '运行编号', project_id: '项目编号', evidence_path: '证据文件', audit_path: '审计记录', contamination: '数据隔离', replay: '重放', command: '验收命令', errors: '错误', accuracy: '准确率', answer_accuracy: '答案准确率', grounded_accuracy: '有依据的答案准确率', citation_precision: '引用精确率', citation_recall: '引用召回率' };
const object = (value: unknown): RecordValue => value && typeof value === 'object' && !Array.isArray(value) ? value as RecordValue : {};
const array = (value: unknown): unknown[] => Array.isArray(value) ? value : [];
const str = (value: unknown, fallback = '—') => value == null || value === '' ? fallback : String(value);
const num = (value: unknown): number | undefined => typeof value === 'number' && Number.isFinite(value) ? value : undefined;
const percentage = (value: unknown) => num(value) === undefined ? '—' : `${(Number(value) * 100).toFixed(1)}%`;
const status = (value: unknown) => value === true ? 'passed' : value === false ? 'failed' : str(value, 'not_run');
function modelName(value: unknown): string { const data = object(value); return typeof value === 'string' ? value : str(data.id || data.model || data.name, ''); }
function humanModel(value: unknown): string { const name = modelName(value); return name === 'deepseek-flash' ? 'DeepSeek V4.1 Flash' : name === 'deepseek-pro' ? 'DeepSeek V4.1 Pro' : name || '未记录模型'; }
function formatTime(value: unknown): string { if (!value) return '尚未记录'; const date = new Date(String(value)); return Number.isNaN(date.getTime()) ? String(value) : date.toLocaleString('zh-CN', { hour12: false }); }
function timeOf(record: RecordValue): number {
  const raw = record.updatedAt || record.finishedAt || record.createdAt || record.created_at || record.timestamp;
  const parsed = raw ? Date.parse(String(raw)) : NaN;
  if (!Number.isNaN(parsed)) return parsed;
  const match = str(record.name, '').match(/(\d{4}-\d{2}-\d{2})T(\d{2})-(\d{2})-(\d{2})-(\d{3})Z/);
  return match ? Date.parse(`${match[1]}T${match[2]}:${match[3]}:${match[4]}.${match[5]}Z`) : 0;
}
function StatusBadge({ value }: { value: unknown }) {
  const state = status(value);
  const Icon = ['passed', 'pass', 'completed'].includes(state) ? Check : ['failed', 'fail', 'blocked'].includes(state) ? X : ['running', 'queued'].includes(state) ? LoaderCircle : state === 'pending' ? Clock3 : Minus;
  return <span className={`verification-state state-${state}`}><Icon className={['running', 'queued'].includes(state) ? 'spin' : ''} />{statusLabels[state] || state}</span>;
}
function DetailText({ value, depth = 0 }: { value: unknown; depth?: number }) {
  if (value == null) return <span className="muted">尚未记录</span>;
  if (typeof value === 'boolean') return <span>{value ? '是' : '否'}</span>;
  if (typeof value !== 'object') return <span className="detail-prose">{String(value)}</span>;
  if (Array.isArray(value)) return <ul className="detail-list">{value.slice(0, 12).map((item, index) => <li key={index}><DetailText value={item} depth={depth + 1} /></li>)}{value.length > 12 && <li className="muted">其余 {value.length - 12} 项见导出的完整报告。</li>}</ul>;
  if (depth > 3) return <span className="muted">详细结构请查看报告文件。</span>;
  const entries = Object.entries(value as RecordValue).filter(([key]) => !['predictions', 'traces', 'apiKey', 'rawResponse', 'answer', 'prompt', 'tool_calls', 'events', 'settings'].includes(key));
  return <dl className="compact-details">{entries.slice(0, 12).map(([key, item]) => <div key={key}><dt>{fieldLabels[key] || key}</dt><dd><DetailText value={item} depth={depth + 1} /></dd></div>)}</dl>;
}
function Evidence({ value }: { value: unknown }) {
  const [copied, setCopied] = useState(false);
  const values = Array.isArray(value) ? value : value == null ? [] : [value];
  if (!values.length) return <span className="muted">尚无证据记录</span>;
  async function copy(text: string) { try { await navigator.clipboard.writeText(text); setCopied(true); setTimeout(() => setCopied(false), 1500); } catch { setCopied(false); } }
  return <div className="evidence-list">{values.slice(0, 5).map((item, index) => {
    const entry = object(item);
    const path = typeof item === 'string' ? item : typeof entry.path === 'string' ? entry.path : typeof entry.url === 'string' ? entry.url : undefined;
    if (!path) return <DetailText key={index} value={item} />;
    const url = safeArtifactUrl(path);
    return <div className="evidence-path" key={index}>{url ? <a href={url} target="_blank" rel="noreferrer">{path}</a> : <code>{path}</code>}<button type="button" className="icon-btn" aria-label="复制证据路径" title={copied ? '已复制' : '复制证据路径'} onClick={() => void copy(path)}>{copied ? <Check /> : <Copy />}</button>{entry.sha256 != null && <details className="evidence-hash"><summary>指纹</summary><code>{str(entry.sha256)}</code></details>}</div>;
  })}{values.length > 5 && <span className="muted">另有 {values.length - 5} 条证据，见完整报告。</span>}</div>;
}
function Metric({ label, value, note }: { label: string; value: string; note?: string }) { return <div className="acceptance-metric"><span>{label}</span><strong>{value}</strong>{note && <small>{note}</small>}</div>; }
function CaseTable({ cases }: { cases: RecordValue[] }) {
  return <div className="table-scroll acceptance-table"><table><thead><tr><th>编号</th><th>验收项目</th><th>状态</th><th>核验依据</th></tr></thead><tbody>{cases.map((item, index) => <tr key={str(item.id, String(index))}><td><span className="case-id">{str(item.id, String(index + 1))}</span></td><td><strong>{str(item.name, '未命名验收项')}</strong>{(item.details != null || item.criterion != null) && <details className="case-details"><summary>查看验收标准与说明</summary>{item.criterion != null && <p className="case-criterion"><b>验收标准</b><br /><DetailText value={item.criterion} /></p>}{item.details != null && <DetailText value={item.details} />}</details>}</td><td><StatusBadge value={item.status} /></td><td><Evidence value={item.evidence} /></td></tr>)}</tbody></table></div>;
}
function ComponentCards({ components }: { components: RecordValue[] }) {
  return <div className="component-cards">{components.map((item, index) => {
    const name = str(item.name, '组件'); const kind = /模型|推理|Agent|DeepSeek|llm/i.test(name) ? '真实模型链路' : /解析|财报|数据|pipeline|parser/i.test(name) ? '文档与数据' : /前端|界面|浏览器|frontend|browser/i.test(name) ? '前端与交互' : '系统与边界'; const Icon = kind === '真实模型链路' ? BrainCircuit : kind === '文档与数据' ? Database : kind === '前端与交互' ? Monitor : ShieldCheck;
    return <article className="component-card" key={name + index}><header><Icon /><StatusBadge value={item.status} /></header><div className="component-kind">{kind}</div><h3>{name}</h3>{num(item.total) !== undefined && <div className="component-count"><b>{num(item.passed) ?? '—'}</b><span>/ {Number(item.total)} 项</span></div>}<Evidence value={item.evidence} /></article>;
  })}</div>;
}
function Overview({ report, components, activeModel }: { report?: RecordValue; components: RecordValue[]; activeModel: string }) {
  const cases = array(report?.cases).map(object); const passed = cases.filter(item => status(item.status) === 'passed').length; const failed = cases.filter(item => ['failed', 'blocked'].includes(status(item.status))).length; const notRun = cases.filter(item => ['not_run', 'pending', 'skipped'].includes(status(item.status))).length; const partial = cases.filter(item => status(item.status) === 'partial').length;
  return <>{report ? <><div className="acceptance-overview"><div><div className="eyebrow">当前项目总体验收</div><h2>{str(report.name, '系统功能验收')}</h2><p>模型：{humanModel(report.model || activeModel)}<span className="inline-divider">·</span>更新于 {formatTime(report.updatedAt || report.createdAt)}</p></div><StatusBadge value={report.status} /></div><div className="acceptance-metrics"><Metric label="逐项通过" value={`${passed} / ${cases.length}`} note="以每个验收项的证据为准" /><Metric label="未通过或阻塞" value={String(failed)} /><Metric label="尚未执行" value={String(notRun)} note={partial ? `另有 ${partial} 项部分完成，未计为通过` : undefined} /></div></> : <div className="acceptance-note"><ClipboardCheck /><div><b>总体验收报告尚未生成</b><p>报告生成后展示 S01–S12 的逐点结论；已有组件和财报结果可在相应标签查看。</p></div></div>}
    {components.length > 0 && <section className="verification-section"><div className="section-heading"><h2>各层验证结果</h2><span>组件通过不自动等于整体验收通过</span></div><ComponentCards components={components} /></section>}
    {cases.length > 0 && <section className="verification-section"><div className="section-heading"><h2>逐项验收</h2><span>{cases.length} 项 · 可展开查看说明与证据</span></div><CaseTable cases={cases} /></section>}
    {report?.limitations != null && <section className="verification-limits"><h3>已知限制与未完成项</h3><DetailText value={report.limitations} /></section>}
  </>;
}
function ModelRound({ run }: { run: RecordValue }) {
  const metrics = Object.entries(object(run.metrics));
  const totalN = metrics.reduce((sum, [, value]) => sum + (num(object(value).n) || 0), 0);
  const correctWeight = metrics.reduce((sum, [, value]) => sum + (num(object(value).n) || 0) * (num(object(value).answer_accuracy) || 0), 0);
  const answer = num(run.answer_accuracy) ?? (totalN ? correctWeight / totalN : undefined);
  return <div className="model-round"><div className="model-round-heading"><h3>第 {str(run.round, '1')} 轮</h3><span>收到 {str(run.received_predictions ?? run.selectedCases, '—')} 份作答{num(run.evaluated_cases) !== undefined ? ` / 划分共 ${run.evaluated_cases} 题` : ''}</span><StatusBadge value={run.dataset_gate_pass === undefined ? run.status : run.dataset_gate_pass ? 'passed' : 'failed'} /></div>
    {run.subset === true && <p className="subset-note">这是调试子集，未覆盖全部题目；分类分母可能包含完整划分，不作为正式达标结论。</p>}
    <div className="acceptance-metrics compact"><Metric label="答案准确率" value={percentage(answer)} /><Metric label="有依据的答案准确率" value={percentage(run.grounded_accuracy)} /><Metric label="引用精确率" value={percentage(run.citation_precision)} /><Metric label="引用召回率" value={percentage(run.citation_recall)} /></div>
    {metrics.length > 0 && <div className="table-scroll benchmark-metric-table"><table><thead><tr><th>能力类别</th><th>题数</th><th>答案准确率</th><th>有依据的准确率</th><th>目标</th><th>结论</th></tr></thead><tbody>{metrics.map(([key, raw]) => { const item = object(raw); return <tr key={key}><td>{categoryLabels[key] || key}</td><td>{str(item.n)}</td><td>{percentage(item.answer_accuracy)}</td><td>{percentage(item.grounded_accuracy)}</td><td>{percentage(item.target_answer_accuracy)}</td><td><StatusBadge value={item.pass === true ? 'passed' : item.pass === false ? 'failed' : 'not_run'} /></td></tr>; })}</tbody></table></div>}
    <div className="run-resource-line"><span>耗时 {num(run.wallTimeMs) !== undefined ? `${(Number(run.wallTimeMs) / 1000).toFixed(1)} 秒` : '未记录'}</span><span>模型请求 {str(run.modelCalls)} 次</span><span>输入 {num(run.inputTokens)?.toLocaleString('zh-CN') ?? '—'} tokens</span><span>输出 {num(run.outputTokens)?.toLocaleString('zh-CN') ?? '—'} tokens</span>{Boolean(run.runtime_gate) && <span>系统验收单独核验</span>}</div>
  </div>;
}
function ModelBatch({ record, defaultOpen = false }: { record: RecordValue; defaultOpen?: boolean }) {
  const nestedRuns = array(record.runs).map(object).filter(item => Object.keys(object(item.metrics)).length);
  const rounds = nestedRuns.length ? nestedRuns : record.metrics ? [record] : [];
  const split = record.split === 'dev' ? '开发集' : record.split === 'acceptance' ? '冻结验收集' : str(record.split, '数据划分未记录');
  const state = record.status || (record.dataset_gate_pass === true ? 'passed' : 'not_run');
  return <details className="model-batch" open={defaultOpen}><summary><div className="batch-chevron"><ChevronRight /></div><div className="batch-title"><strong>{humanModel(record.model)}<span className="batch-split">{split}{record.subset === true ? ' · 调试子集' : ''}</span></strong><small>{str(record.name, '财报评测')}</small></div><StatusBadge value={state} /></summary><div className="batch-body"><div className="batch-meta"><span>题库 v{str(record.benchmarkVersion, '0.1')}</span><span>运行时间 {formatTime(record.createdAt || record.finishedAt || (timeOf(record) ? new Date(timeOf(record)).toISOString() : undefined))}</span>{record.repeat != null && <span>计划重复 {str(record.repeat)} 轮</span>}{record.repeatConsistency != null && <span>重复一致性 {typeof record.repeatConsistency === 'number' ? percentage(record.repeatConsistency) : str(record.repeatConsistency)}</span>}</div>
      {rounds.length ? rounds.map((run, index) => <ModelRound run={{ model: record.model, split: record.split, subset: record.subset, ...run }} key={index} />) : <div className="batch-pending">{['running', 'queued'].includes(str(state)) ? <><LoaderCircle className="spin" /><p>真实模型评测正在运行，完成一轮后会显示指标。</p></> : <><Clock3 /><p>该批次尚未提供逐轮指标。</p></>}</div>}
      <details className="reproduction-details"><summary>复现信息与完整记录</summary><dl><div><dt>模型标识</dt><dd>{modelName(record.model)}</dd></div>{Boolean(record.configHash) && <div><dt>配置指纹</dt><dd><code>{str(record.configHash)}</code></dd></div>}{Boolean(record.promptHash) && <div><dt>提示词指纹</dt><dd><code>{str(record.promptHash)}</code></dd></div>}{Boolean(record.piVersion) && <div><dt>Pi 版本</dt><dd>{str(record.piVersion)}</dd></div>}</dl><p>逐题预测、长调用记录和原始响应保留在报告文件中；本页仅展示汇总与验收依据。</p></details>
    </div></details>;
}
function ComponentResult({ record }: { record: RecordValue }) {
  const checks = array(record.cases).length ? array(record.cases).map(object) : Object.entries(object(record.checks)).map(([id, value]) => ({ id, name: fieldLabels[id] || id, status: typeof value === 'boolean' ? value ? 'passed' : 'failed' : object(value).status || 'not_run', details: typeof value === 'object' ? value : undefined }));
  const runs = array(record.runs).map(object);
  const source = record.evidence || record.evidence_path || record.audit_path;
  return <article className="component-result"><header><div><h3>{str(record.name, '组件验证')}</h3><p>{record.mode === 'deterministic_pipeline' ? '程序解析与数据库查询 · 不计为模型推理成绩' : str(record.scope, '独立功能验证')}</p></div><StatusBadge value={record.status} /></header>
    {(record.total != null || record.passed != null) && <div className="component-summary"><b>{str(record.passed)} / {str(record.total)}</b><span>检查通过</span>{record.repeat_values_and_citations_identical != null && <span>重复数据与引用一致：{record.repeat_values_and_citations_identical ? '是' : '否'}</span>}</div>}
    {runs.some(item => item.run_id || item.passed != null) && <div className="table-scroll"><table><thead><tr><th>运行</th><th>通过 / 总数</th><th>答案准确率</th><th>证据准确率</th><th>处理页数</th><th>耗时</th></tr></thead><tbody>{runs.map((run, index) => <tr key={index}><td>{str(run.run_id, `第 ${index + 1} 轮`)}</td><td>{str(run.passed)} / {str(run.total)}</td><td>{percentage(run.accuracy)}</td><td>{percentage(run.evidence_accuracy)}</td><td>{str(run.physical_pages_processed)}</td><td>{num(run.elapsed_seconds)?.toFixed(1) ?? '—'} 秒</td></tr>)}</tbody></table></div>}
    {checks.length > 0 && <div className="component-checks">{checks.map((check, index) => <div key={index}><span>{str(check.name || check.id, `检查 ${index + 1}`)}</span><StatusBadge value={check.status} /></div>)}</div>}
    {source != null && <Evidence value={source} />}
    {(record.limitations || record.limitation) != null && <p className="component-limit"><DetailText value={record.limitations || record.limitation} /></p>}
  </article>;
}

export default function BenchmarkView({ onBack, currentModel = '' }: { onBack: () => void; currentModel?: string }) {
  const [data, setData] = useState<BenchmarkResults>({ runs: [], runtime: [] });
  const [busy, setBusy] = useState(true); const [error, setError] = useState(''); const [tab, setTab] = useState<Tab>('overview'); const [refresh, setRefresh] = useState(0);
  useEffect(() => {
    const controller = new AbortController(); setBusy(true); setError('');
    api<BenchmarkResults>('/api/benchmark/results', { signal: controller.signal }).then(result => { if (!controller.signal.aborted) setData({ runs: Array.isArray(result.runs) ? result.runs : [], runtime: Array.isArray(result.runtime) ? result.runtime : [] }); }).catch(error => { if (!controller.signal.aborted) setError(errorText(error)); }).finally(() => { if (!controller.signal.aborted) setBusy(false); });
    return () => controller.abort();
  }, [refresh]);
  const reports = useMemo(() => [...data.runtime, ...data.runs].sort((a, b) => timeOf(b) - timeOf(a)), [data]);
  const acceptance = reports.find(record => Array.isArray(record.cases) && Array.isArray(record.components));
  const components = array(acceptance?.components).map(object);
  const candidates = reports.filter(record => record.model && (record.metrics || record.split || record.promptHash));
  const batches = candidates.filter(record => !record.metrics || !candidates.some(other => other !== record && Array.isArray(other.runs) && str(record.name, '').startsWith(str(other.name, '___') + ' round')));
  const activeModel = currentModel || modelName(acceptance?.model) || modelName(batches[0]?.model);
  const currentBatches = batches.filter(record => modelName(record.model) === activeModel);
  const previousBatches = batches.filter(record => modelName(record.model) !== activeModel);
  const componentReports = reports.filter(record => record !== acceptance && !candidates.includes(record) && !str(record.name, '').includes('predictions') && !record.test_layer && (record.status || record.total != null));
  function download() {
    const url = URL.createObjectURL(new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' })); const anchor = document.createElement('a'); anchor.href = url; anchor.download = 'finance-acceptance-results.json'; anchor.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
  return <main className="benchmark-page"><div className="benchmark-heading"><div><button className="text-button back-link" onClick={onBack}><ArrowLeft />返回对话</button><div className="eyebrow">质量与可复现性</div><h1>验收中心</h1><p>每项结论对应实际记录；组件测试、模型评测和系统验收分别展示。</p></div><div className="benchmark-actions"><button className="plain-button" disabled={busy} onClick={() => setRefresh(refresh + 1)}>{busy ? <LoaderCircle className="spin" /> : <RefreshCw />}刷新结果</button><button className="plain-button" disabled={!reports.length} onClick={download}><Download />导出记录</button></div></div>
    <div className="benchmark-tabs" role="tablist" aria-label="验收结果分类"><button role="tab" aria-selected={tab === 'overview'} className={tab === 'overview' ? 'active' : ''} onClick={() => setTab('overview')}>总体验收<span>{array(acceptance?.cases).length}</span></button><button role="tab" aria-selected={tab === 'model'} className={tab === 'model' ? 'active' : ''} onClick={() => setTab('model')}>财报模型评测<span>{currentBatches.length}</span></button><button role="tab" aria-selected={tab === 'components'} className={tab === 'components' ? 'active' : ''} onClick={() => setTab('components')}>组件结果<span>{componentReports.length}</span></button></div>
    {error && <div className="error-banner" role="alert">{error}</div>}
    {busy && !reports.length ? <div className="page-empty"><LoaderCircle className="spin" /><p>读取实际验收记录…</p></div> : <div className="benchmark-content" role="tabpanel" aria-label={tab === 'overview' ? '总体验收' : tab === 'model' ? '财报模型评测' : '组件结果'}>
      {tab === 'overview' && <Overview report={acceptance} components={components} activeModel={activeModel} />}
      {tab === 'model' && <><div className="section-heading model-section-heading"><div><h2>真实模型评测</h2><p>当前模型：{humanModel(activeModel)}<span className="model-code">{activeModel}</span></p></div><BrainCircuit /></div>{currentBatches.length ? currentBatches.map((record, index) => <ModelBatch key={str(record.name, String(index))} record={record} defaultOpen={index === 0} />) : <div className="page-empty"><FileCheck2 /><h2>尚无当前模型的评测记录</h2><p>完成真实模型评测后，这里展示答案、引用以及分类门槛。</p></div>}{previousBatches.length > 0 && <details className="older-model-runs"><summary>历史其他模型 · {previousBatches.length} 个批次 · 不计入当前模型验收</summary>{previousBatches.map((record, index) => <ModelBatch key={str(record.name, String(index))} record={record} />)}</details>}</>}
      {tab === 'components' && <>{components.length > 0 && <ComponentCards components={components} />}<div className="section-heading"><h2>独立验证记录</h2><span>仅代表对应验证范围</span></div>{componentReports.length ? componentReports.map((record, index) => <ComponentResult key={str(record.name, String(index))} record={record} />) : <div className="page-empty"><ClipboardCheck /><h2>尚无组件验证记录</h2><p>前端、文档解析和安全边界的检查报告会分别列出。</p></div>}</>}
    </div>}
  </main>;
}
