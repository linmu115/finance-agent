"""Compact pre-analysis handoff; complete, sourced tables stay handle-readable."""
from collections import defaultdict
from decimal import Decimal
import importlib.util
import json

from .analysis_report import cell_column, format_cell, compile_report
from .financial_workpapers import WorkpaperInputError, col, table, publish
from .workpaper_analyst import AnalystData
from .workpaper_variance import variance_attribution
from .workpaper_signals import anomaly_signals


def read_table(service, project, read=None, **_options):
    service.store.project(project)
    read = read or {}
    handle = read.get('handle', '')
    from .delivery_files import delivery_manifest, delivery_path
    delivery = delivery_manifest(service.store.root, project, handle)
    if not delivery: raise WorkpaperInputError('当前项目不存在此底稿句柄')
    path = delivery_path(delivery, 'numeric_tables.json')
    tables = json.loads(path.read_text('utf-8'))
    name = read.get('table')
    if name not in tables: raise WorkpaperInputError('请选择原表：' + ', '.join(tables))
    source = tables[name]; offset, limit = int(read.get('offset', 0)), int(read.get('limit', 50))
    if offset < 0 or limit <= 0: raise WorkpaperInputError('offset >= 0，limit > 0')
    total = len(source['rows']); end = offset + limit
    selected = {**source, 'rows': source['rows'][offset:end], 'evidence': source.get('evidence', [])[offset:end]}
    return {'kind': 'read_table', 'handle': handle, 'table': name, 'total': total, 'offset': offset,
            'next_offset': end if end < total else None, 'table_data': selected}


def compact_context(tables, selection, handle, project):
    def values(name, row, columns):
        t = tables[name]; i = t['rows'].index(row)
        output = {}
        for c in columns:
            item = {'ref': f'{name}.{row["key"]}.{c}', 'display': format_cell(row.get(c), cell_column(t, i, c), with_unit=True)}
            if row.get(c) is None:
                evidence = t['evidence'][i].get(c, {})
                item['reason'] = evidence.get('reason') or evidence.get('source', {}).get('missing_reason') or '见该格完整来源链'
            output[c] = item
        return output
    def rows(name): return tables.get(name, {}).get('rows', [])
    ps = selection['periods'][:2]
    metrics = []
    specs = [('statement_income', {'revenue', 'gross_profit', 'operating_profit'}, ps),
             ('statement_profit_attribution', set(ps), ['consolidated', 'parent']),
             ('statement_ratios', {'gross_profit_margin', 'net_profit_margin'}, [*ps, 'change_pp']),
             ('statement_cash', {p + '_cfo' for p in ps}, ['amount']),
             ('statement_deducted_profit', set(ps), ['disclosed', 'share']),
             ('statement_roe', set(ps), ['weighted', 'computed'])]
    for name, keys, columns in specs:
        for row in rows(name):
            if row['key'] in keys:
                metrics.append({'metric': row.get('metric') or row['key'], 'values': values(name, row, columns)})
    profit = {'table': 'variance_profit_bridge', 'columns': ['key', 'item', 'role', 'contribution'],
              'rows': [[r['key'], r['item'], r['role'], values('variance_profit_bridge', r, ['contribution'])['contribution']['display']]
                       for r in rows('variance_profit_bridge') if r['role'] != 'checkpoint']}
    cash = []
    for name in ('statement_indirect_contributions', 'statement_bridge'):
        cash.append({'table': name, 'columns': ['key', 'period', 'item', 'direction', 'amount'],
                     'rows': [[r['key'], r['period'], r.get('category') or r['item'], r.get('direction', ''),
                               values(name, r, ['amount'])['amount']['display']] for r in rows(name)]})
    # Rank concrete monetary contributions; checkpoints/residuals are not drivers.
    drivers = [r for r in rows('variance_profit_bridge') if r['role'] == 'step' and r.get('contribution') is not None]
    drivers.sort(key=lambda r: abs(Decimal(r['contribution'])), reverse=True)
    changes = [f'variance_profit_bridge.{r["key"]}.contribution' for r in drivers[:3]]
    signals = [{'key': r['key'], 'signal': r['signal'], **values('signals_signals', r, ['value']),
                'baseline': r['baseline'], 'threshold': r['threshold']} for r in rows('signals_signals') if r['triggered'] == '是']
    groups = defaultdict(list)
    for row in rows('pipeline_gaps'): groups[row['table']].append(row)
    missing = [{'table': name, 'cells_or_source_issues': len(items), 'details': 'pipeline_gaps',
                'reason': '原表映射缺项；逐行原文、坐标及原因可读' if name == 'source_tables' else
                          '未定位到该披露表' if name not in tables else '存在缺失或不可算项；每格具体原因可读'}
               for name, items in groups.items()]
    inventory = {name: len(t['rows']) for name, t in tables.items()}
    return {'schema_version': 'workpaper-pipeline-v1', 'status': 'partial' if missing else 'ready',
            'selection': selection, 'key_metrics': metrics, 'bridges': {'profit': profit, 'cash': cash},
            'major_changes': changes, 'major_changes_basis': '已知利润桥步骤中绝对金额前三项；完整步骤和残差在利润桥，金额贡献不等于因果',
            'triggered_signals': signals,
            'management_evidence': [], 'signal_followups': [], 'comparability_constraints': [],
            'missing': missing,
            'source_evidence': {'table': 'variance_drivers_evidence', 'rows': len(rows('variance_drivers_evidence')),
                                'basis': '计算贡献与管理层原句分列；对齐状态由 management_evidence 扩展给出'},
            'full_tables': {'handle': handle, 'tables': inventory, 'read': {'tool': 'financial_workpaper',
                'arguments': {'project_id': project, 'kind': 'read_table', 'read': {'handle': handle, 'table': 'variance_drivers_evidence', 'offset': 0, 'limit': 50}}}},
            'extensions': {k: 'pending' for k in ('management_evidence', 'signal_followups', 'comparability_constraints')}}


def analysis_pipeline(service, project, document_id=None, company=None, scope='consolidated', periods=None, focus=None):
    a = AnalystData(service, project, document_id, company, scope, periods, focus)
    reports = {'statement_analysis': a.base,
               'variance_attribution': variance_attribution(service, project, _analysis=a)[0],
               'anomaly_signals': anomaly_signals(service, project, _analysis=a)[0]}
    tables, gaps = {}, []
    for kind, prefix in [('statement_analysis', 'statement'), ('variance_attribution', 'variance'), ('anomaly_signals', 'signals')]:
        report = reports[kind]
        for name, t in report['tables'].items():
            target = prefix + '_' + name
            tables[target] = {**t, 'report_section': {'statement': 'key_data', 'variance': 'variance_attribution', 'signals': 'anomaly_signals'}[prefix]}
            for row in t['rows']:
                if row.get('role') == 'residual' and row.get('contribution', {}).get('value') is not None and Decimal(row['contribution']['value']) != 0:
                    gaps.append({'table': target, 'ref': f'{target}.{row["key"]}.contribution',
                                 'reason': '非零桥接残差；已知项目未覆盖全部变动，不能作为已解释驱动'})
                for c, q in row.items():
                    if isinstance(q, dict) and 'value' in q and q['value'] is None:
                        reason = q.get('source', {}).get('missing_reason') or '缺少计算输入，见该格完整来源链'
                        gaps.append({'table': target, 'ref': f'{target}.{row["key"]}.{c}', 'reason': reason})
    for gap in a.st.source_gaps:
        gaps.append({'table': 'source_tables', 'ref': json.dumps(gap, ensure_ascii=False), 'reason': gap['reason']})
    # A missing bridge/quarter table is itself missing evidence, not zero rows proving no problem.
    for name, reason in [('indirect_bridge', '原表中未定位到同口径间接法补充资料桥'), ('quarterly', '未披露或未识别年度季度表')]:
        if name not in a.base['tables']: gaps.append({'table': 'statement_' + name, 'ref': '', 'reason': reason})
    unique = {(g['table'], g['ref'], g['reason']): g for g in gaps}
    tables['pipeline_gaps'] = table({k: col(k) for k in ('key', 'table', 'ref', 'reason')},
                                  [{'key': str(i), **g} for i, g in enumerate(unique.values())])
    tables['pipeline_gaps']['report_section'] = 'limitations'
    # publish keeps the original observations field for existing report delivery.
    tables['observations'] = table({'key': col('key'), 'finding': col('finding'), 'basis': col('basis')}, [])
    raw = {'title': a.st.company + ' 紧凑分析底稿', 'periods': a.ps, 'selection': a.st.selection,
           'body': '来源为结构化事实或标记的原表直读。原文驱动证据与计算贡献分别保留；缺项不配零。', 'tables': tables}
    data = publish(service, project, 'analysis_pipeline', raw, a.records)
    context = compact_context(data['numeric_tables'], a.st.selection, data['delivery']['id'], project)
    if importlib.util.find_spec('service.workpaper_depth') is not None:
        from .workpaper_depth import enrich_workpaper_context
        extension = enrich_workpaper_context(service, project, selection=a.st.selection,
                    reports={kind: compile_report(report, a.records) for kind, report in reports.items()}, context=context)
        for key in ('management_evidence', 'signal_followups', 'comparability_constraints', 'extensions'):
            if key in extension: context[key] = extension[key]
    # Only context is injected. This response also carries complete A1 host data.
    return {'kind': 'analysis_pipeline', 'context': context, 'handle': data['delivery']['id'],
            'numeric_tables': data['numeric_tables'], 'report': data['report'], 'delivery': data['delivery']}
