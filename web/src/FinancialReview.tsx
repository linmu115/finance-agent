type Check = { status: string; message: string; year?: number };
type Usage = { path: string; usage: string; source_basis: string; source_kind?: string; rationale: string };

/** Keep detailed checks available without turning a financial answer into a log. */
export default function FinancialReview({ result }: { result: { checks?: Check[]; input_usage?: Usage[] } }) {
  const checks = result.checks || [], usage = result.input_usage || [];
  if (!checks.length && !usage.length) return null;
  const pending = checks.filter(check => check.status === 'needs_review').length;
  const incomplete = checks.filter(check => check.status === 'not_checked').length;
  const names: Record<string, string> = { growth: '永续增长率', roic: '长期投入资本回报率', ebit_margin: '长期 EBIT 利润率', tax_rate: '长期税率' };
  const sources: Record<string, string> = { disclosed: '来源列示', derived: '计算推导', assumption: '研究设定', unclassified: '依据未分类' };
  const sourceKinds: Record<string, string> = { disclosed_actual: '披露实际值', analyst_forecast: '机构预测', management_guidance: '管理层指引', assumption: '研究假设', unknown: '来源身份未分类' };
  return <details className="rw-detail" aria-label="模型核验依据">
    <summary>核验依据与假设{pending > 0 ? ` · ${pending} 项需复核` : ''}{incomplete > 0 ? ` · ${incomplete} 项依据不完整` : ''}</summary>
    {checks.map((check, i) => <p key={i} className="rw-muted">{check.year ? `${check.year} 年：` : ''}{check.message}</p>)}
    {usage.length > 0 && <div className="rw-table-scroll"><table><thead><tr><th>参数</th><th>来源依据</th><th>本次用途</th></tr></thead><tbody>{usage.map(item => <tr key={item.path}><td>{names[item.path.split('.').at(-1) || ''] || item.path}</td><td>{sourceKinds[item.source_kind || ''] || sources[item.source_basis] || '依据未分类'}</td><td>长期估值假设{item.rationale&&<small className="rw-muted"> · {item.rationale}</small>}</td></tr>)}</tbody></table></div>}
  </details>;
}
