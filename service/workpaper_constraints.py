"""Machine-readable limits attached to the exact rows used in an answer.

No answer scanning or repair loop here. Consumers retain values/provenance, and
must not promote an unaligned reference gap into a same-basis error or ranking.
"""
import json
from .financial_workpapers import col, table


UNKNOWN = (None, '', 'unspecified', 'unknown')


def issue(dimension, detail, status='unknown', **values):
    return {'dimension': dimension, 'status': status, 'detail': detail, **values}


def constraint(table_name, row_key, columns, issues, *, metric=None, period=None,
               record_ids=(), evidence=(), code='comparison_basis_unaligned'):
    profit = code == 'profit_attribution_unknown'
    return {'id': f'{table_name}:{row_key}:{code}', 'code': code,
            'subject': {'table': table_name, 'row_key': row_key, 'columns': list(columns),
                        'record_ids': [r for r in record_ids if r], 'metric': metric, 'period': period},
            'issues': issues,
            'prohibited_uses': (['label_as_parent_profit', 'parent_profit_comparison'] if profit else
                                ['same_basis_error', 'forecast_accuracy_ranking', 'beat_miss_conclusion']),
            'allowed_uses': ['quoted_source_value', 'qualified_numeric_reference'],
            'message': ('利润归属未明或仅为合并净利润，不得改标归母、计算归母误差或跨归属修正' if profit else
                        '这两个数不能作为同口径误差、预测准确度排名或超/低预期结论；只允许明确标注限制的数值参照'),
            'evidence': list(evidence)}


def revenue_boundary(record):
    label = record.get('label') or record.get('source_ref', {}).get('normalization', {}).get('label') or ''
    if '营业总收入' in label: return 'total_operating_revenue'
    if '主营业务收入' in label: return 'main_business_revenue'
    if '营业收入' in label: return 'operating_revenue'
    return None


def record_issues(left, rights):
    issues = []
    for field in ('scope', 'basis', 'restatement', 'dimensions'):
        if field == 'basis' and left.get('metric') != 'eps': continue
        a = left.get(field)
        if field == 'dimensions': a = {k: v for k, v in (a or {}).items() if k != 'source_table'}
        bs = [r.get(field) for r in rights]
        if field == 'dimensions': bs = [{k: v for k, v in (b or {}).items() if k != 'source_table'} for b in bs]
        if field != 'dimensions' and (a in UNKNOWN or any(b in UNKNOWN for b in bs)):
            issues.append(issue(field, '披露口径尚未明确', left=a, right=bs))
        elif bs and any(a != b for b in bs):
            issues.append(issue(field, '两侧披露口径不同', 'different', left=a, right=bs))
    if left.get('metric') == 'revenue':
        a = revenue_boundary(left); bs = [revenue_boundary(r) for r in rights]
        if a is None or any(b is None for b in bs) or any(a != b for b in bs):
            issues.append(issue('revenue_boundary', '营业收入、营业总收入及主营业务范围尚未对齐',
                                'different' if a and bs and all(bs) and any(a != b for b in bs) else 'unknown', left=a, right=bs))
    return issues


def profit_identity_constraint(table_name, row, record, evidence):
    # An explicit consolidated net-profit metric is also not parent profit.
    if record.get('metric') != 'net_profit': return None
    return constraint(table_name, row['key'], ['value'],
                      [issue('profit_attribution', '原标签或指标未声明归属于母公司股东')],
                      metric='net_profit', period=record.get('period'),
                      record_ids=[record.get('record_id') or record.get('fact_id')], evidence=evidence,
                      code='profit_attribution_unknown')


def attach_constraints(report, constraints):
    merged = {r['id']: r for r in [*report.get('answer_constraints', []), *constraints]}
    report['answer_constraints'] = list(merged.values())
    report['tables']['answer_constraints'] = table(
        {k: col(v) for k, v in [('key', '约束ID'), ('code', '约束类别'), ('subject', '适用数值位置'),
                              ('issues', '未齐维度'), ('prohibited_uses', '禁止用途'), ('message', '回答约束')]},
        [{'key': r['id'], 'code': r['code'], 'subject': json.dumps(r['subject'], ensure_ascii=False),
          'issues': json.dumps(r['issues'], ensure_ascii=False), 'prohibited_uses': json.dumps(r['prohibited_uses']),
          'message': r['message']} for r in merged.values()], '回答中的口径约束')
    report['tables']['answer_constraints']['report_section'] = 'limitations'
    return report
