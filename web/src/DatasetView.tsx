import { useEffect, useState } from 'react';
import { ArrowLeft, Download, ExternalLink, FileText, FlaskConical, LoaderCircle } from 'lucide-react';
import { api, errorText, isAbort } from './api';
import BenchmarkView from './BenchmarkView';

type Catalog = { datasets: { id: string; title: string; description?: string; url: string; files?: { title?: string; name?: string; url: string; pages?: number }[] }[]; reports?: { title: string; url: string }[]; validation?: { command?: string; description?: string; runUrl?: string; statusUrl?: string } };
type ValidationMode = 'quick' | 'full' | 'holdout' | 'financial_v05' | 'generic_v05' | 'correction_v01';
type ValidationRun = { id: string; state: 'running' | 'completed' | 'failed' | 'interrupted'; message?: string; reportUrl?: string; report?: Record<string, unknown> };
function validationMessage(run: ValidationRun) {
  if(run.state==='interrupted')return '首次测试执行已中断或无法确认仍在运行；已产生的记录保留，点击查看不会重新调用模型。';
  if (run.state === 'running') {
    const conversations = run.report?.runs as { stage?: string }[] | undefined;
    return conversations?.length ? conversations.map((item, index) => `会话 ${index + 1}：${item.stage || '处理中'}`).join('；') : '正在准备测试资料和独立会话…';
  }
  if (typeof run.report?.error === 'string') return run.report.error;
  return run.state === 'completed' ? '已完成上传、清洗、共享查询和标准答案比对。' : '检查已结束，下方列出各项结果。';
}
function ValidationSummary({ report }: { report: Record<string, unknown> }) {
  const normalization = report.normalization as { expected_facts?: number; passed_facts?: number; failed_facts?: number; checks?: { id?: string; file?: string; status: string; expected?: { metric?: string; period?: string; value?: string }; errors?: string[] }[] } | undefined;
  const score = report.score as {precision?:number;recall?:number;correction_precision?:number;correction_recall?:number;false_extras?:number;false_or_invalid_corrections?:number;missing?:number} | undefined;
  const pct=(n:number|undefined)=>n===undefined?'—':`${(n*100).toFixed(1)}%`;
  const checks = report.checks as { name: string; status: string }[] | undefined;
  return <div className="validation-results">{score&&<p className="validation-score"><strong>精确率 {pct(score.precision??score.correction_precision)} · 召回率 {pct(score.recall??score.correction_recall)}</strong>{score.false_extras!==undefined&&` · 多抽/重复 ${score.false_extras} 项`}{score.false_or_invalid_corrections!==undefined&&` · 误报或无效修改 ${score.false_or_invalid_corrections} 项`}</p>}{normalization && <p className="validation-score"><strong>{normalization.passed_facts ?? 0} / {normalization.expected_facts ?? 0}</strong> 字段结果符合标准答案 · {normalization.failed_facts ?? 0} 项未通过</p>}{checks?.map((check, index) => <div className="validation-check" key={index}><span>{check.name}</span><b className={check.status === 'failed' ? 'error-text' : ''}>{check.status === 'passed' ? '通过' : check.status === 'failed' ? '未通过' : '运行中'}</b></div>)}{normalization?.checks?.length ? <details><summary>查看 {normalization.checks.length} 项字段比对</summary>{normalization.checks.map((check, index) => <div className="validation-fact-check" key={check.id || index}><span>{check.file} · {check.expected?.metric} · {check.expected?.period}</span><b className={check.status === 'failed' ? 'error-text' : ''}>{check.status === 'passed' ? '通过' : '未通过'}</b>{check.errors?.length ? <p>{check.errors.join('；')}</p> : null}</div>)}</details> : null}</div>;
}
export default function DatasetView({ currentModel, onBack }: { currentModel: string; onBack: () => void }) {
  const [catalog, setCatalog] = useState<Catalog>();
  const [error, setError] = useState('');
  const [history, setHistory] = useState(false);
  const [copied, setCopied] = useState(false);
  const [validation, setValidation] = useState<ValidationRun>();
  const [submitting, setSubmitting] = useState(false);
  const [mode,setMode]=useState<ValidationMode>('financial_v05');
  async function openReport(url: string) {
    setError('');
    try { const result = await api<ValidationRun>(url); setValidation(result); localStorage.setItem('finance.validation', result.id); }
    catch (reason) { setError(errorText(reason)); }
  }
  useEffect(() => {
    if (!validation || validation.state !== 'running') return;
    const timer = setInterval(() => { void api<ValidationRun>(`/api/benchmark/run/${encodeURIComponent(validation.id)}`).then(setValidation).catch(reason => setError(errorText(reason))); }, 2200);
    return () => clearInterval(timer);
  }, [validation?.id, validation?.state]);
  async function run(mode: ValidationMode) {
    setSubmitting(true); setError('');
    try { const result = await api<ValidationRun>(catalog?.validation?.runUrl || '/api/benchmark/run', { method: 'POST', body: JSON.stringify({ mode }) }); localStorage.setItem('finance.validation', result.id); setValidation(result); }
    catch (reason) { setError(errorText(reason)); }
    finally { setSubmitting(false); }
  }
  useEffect(() => {
    const controller = new AbortController();
    void (async () => {
      try {
        const next = await api<Catalog>('/api/benchmark/catalog', { signal: controller.signal }); setCatalog(next);
        const saved = localStorage.getItem('finance.validation');
        const latest = next.reports?.find(report => report.url.startsWith('/api/benchmark/run/'))?.url;
        const selected = latest || (saved ? `/api/benchmark/run/${encodeURIComponent(saved)}` : undefined);
        if (selected) {
          try { setValidation(await api<ValidationRun>(selected, { signal: controller.signal })); }
          catch (reason) {
            if (isAbort(reason)) return;
            localStorage.removeItem('finance.validation');
            if (latest && latest !== selected) setValidation(await api<ValidationRun>(latest, { signal: controller.signal }));
          }
        }
      } catch (reason) { if (!isAbort(reason)) setError(errorText(reason)); }
    })();
    return () => controller.abort();
  }, []);
  if (history) return <div className="dataset-history"><button className="text-button" onClick={() => setHistory(false)}><ArrowLeft />返回数据集与测试</button><BenchmarkView currentModel={currentModel} onBack={() => setHistory(false)} /></div>;
  const command = catalog?.validation?.command || 'node scripts/verify_holdout_v05.mjs --profile financial';
  return <main className="dataset-view"><header className="workspace-heading"><div><div className="workspace-eyebrow">测试资料与可复现结果</div><h1>数据集与测试</h1><p>下载真实财报，通过对话上传，观察清洗、入库、查询和制图的完整过程。</p></div><button className="plain-button" onClick={onBack}><ArrowLeft />返回对话</button></header>
    <nav className="dataset-links" aria-label="测试说明"><a className="text-button" href="/api/benchmark/report/progress" target="_blank" rel="noreferrer"><FileText />本轮升级进度与原始证据<ExternalLink /></a><a className="text-button" href="/api/benchmark/design" target="_blank" rel="noreferrer">Benchmark 设计与评分<ExternalLink /></a></nav>
    {error && <p className="error-banner" role="alert">{error}</p>}
    {!catalog && !error && <div className="chat-loading"><LoaderCircle className="spin" />正在读取数据集…</div>}
    <div className="dataset-cards">{catalog?.datasets.map(dataset => <section className="dataset-card" key={dataset.id}><FileText /><h2>{dataset.title}</h2><p>{dataset.description}</p><a className="primary-button" href={dataset.url} download><Download />下载数据包</a>{dataset.files && <ul>{dataset.files.map(file => <li key={file.url}><a href={file.url} target="_blank" rel="noreferrer">{file.title || file.name || '财报文件'}<ExternalLink /></a>{file.pages && <span>{file.pages} 页</span>}</li>)}</ul>}</section>)}</div>
    <section className="dataset-usage"><h2>怎么检测处理结果</h2><ol><li><b>下载并上传</b><span>把 PDF 添加到任一对话，发送“处理全部财务主表和附注表，入库并更新看板”。</span></li><li><b>检查标准数据</b><span>打开财报看板，查看公司、期间、单位、口径和分部。点击任意数值的“原文”核对对应页面。</span></li><li><b>继续查询与制图</b><span>在同一项目的新对话查询指标，或在看板选择横轴与纵轴，并导出 CSV、SVG 或 PNG。</span></li><li><b>与标准答案比较</b><span>benchmark 包中提供题目、标准答案和评分说明。历史成绩对应其标明的版本，新增实现需要重新运行测试。</span></li></ol></section>
    {catalog?.validation && <section className="dataset-validation"><FlaskConical /><div><h2>运行 benchmark</h2><p>整表测试同时检查漏抽、多抽、单位、期间与口径；研报纠错检查修改是否正确、有据且可执行。<a href="/api/benchmark/design" target="_blank" rel="noreferrer">查看设计与评分方法</a></p><p>{catalog.validation.description || '运行实际上传、Pi 清洗、入库与查询流程，查看逐项结果。'}</p><div className="validation-actions"><select className="plain-button" aria-label="选择测试组" value={mode} disabled={submitting || validation?.state === 'running'} onChange={e=>setMode(e.target.value as ValidationMode)}><option value="financial_v05">整表 v0.5 · 金融工作台</option><option value="generic_v05">整表 v0.5 · 通用 Pi 对照</option><option value="correction_v01">研报纠错 v0.1</option></select><button className="primary-button" disabled={submitting || validation?.state === 'running'} onClick={()=>void run(mode)}>{submitting || validation?.state === 'running'?<LoaderCircle className="spin"/>:<FlaskConical/>}运行或查看首次结果</button><span>首次运行使用已配置的 DeepSeek API</span></div><details><summary>开发回归与历史结果</summary><div className="validation-actions"><button className="plain-button" disabled={submitting || validation?.state === 'running'} onClick={()=>void run('quick')}>快速端到端测试</button><button className="plain-button" disabled={submitting || validation?.state === 'running'} onClick={()=>void run('full')}>完整开发回归</button><button className="plain-button" disabled={submitting || validation?.state === 'running'} onClick={()=>void run('holdout')}>查看旧 v0.4.1 首次结果</button></div></details>{validation && <div className={`validation-progress ${validation.state}`} role="status"><b>{validation.state === 'running' ? '测试正在运行' : validation.state === 'completed' ? '测试运行完成' : validation.state==='interrupted'?'首次测试已中断':'测试未全部通过'}</b><p>{validationMessage(validation)}</p>{validation.reportUrl && <a className="text-button" href={validation.reportUrl} target="_blank" rel="noreferrer">下载测试结果 <Download /></a>}{validation.report && <ValidationSummary report={validation.report} />}</div>}<details className="validation-command"><summary>在项目目录手动运行</summary><div className="benchmark-command"><code>{command}</code><button className="plain-button" onClick={async () => { try { await navigator.clipboard.writeText(command); setCopied(true); } catch { setError('复制失败，请选中并复制测试命令。'); } }}>{copied ? '已复制' : '复制命令'}</button></div></details></div></section>}
    <div className="dataset-links">{catalog?.reports?.filter(report => report.url!=='/api/benchmark/report/progress').map(report => report.url.startsWith('/api/benchmark/run/') ? <button key={report.url} className="text-button" onClick={() => void openReport(report.url)}><FileText />{report.title}</button> : <a key={report.url} className="text-button" href={report.url} target="_blank" rel="noreferrer"><FileText />{report.title}<ExternalLink /></a>)}<button className="text-button" onClick={() => setHistory(true)}>查看历史测试记录</button></div>
  </main>;
}
