"""Deterministic omissions and semantic-ID diagnostics before script commit."""
import json
import re
from .normalization import metric_id, decimal_value
from .semantic import numeric_candidate
from .cleaning_batches import column_totals


def decode(value, default):
    return json.loads(value) if isinstance(value, str) and value else value or default


def metric_candidates(label, header=''):
    canonical = metric_id(label)
    english = re.sub(r'[^a-z0-9]+', '_', label.casefold()).strip('_')
    base = canonical or (english if english and english[0].isalpha() else None)
    if not base: return []
    if re.search(r'构成|佔比|占比|proportion|composition|percentage of', header, re.I): return [base + '_share']
    if re.search(r'百分点|percentage.points?', header, re.I): return [base + '_change_pp']
    if re.search(r'变动额|增减额|change.*amount', header, re.I): return [base + '_change_amount']
    if re.search(r'增减|增长|change|growth', header, re.I): return [base + '_growth_rate']
    return [base]


def mapping_issues(table, schema, rows, exclusion_reason=None, page_text='', facts=()):
    index = table['index']
    if schema.get('statement') == 'nonfinancial':
        navigation=bool(re.search(r'^\s*(?:Contents|目\s*录)\b',page_text,re.I))
        amount_cells=[str(c) for row in table.get('rows',[]) for c in row[1:]
                      if any((v:=decimal_value(line)) is not None and not (1900<=v<=2100 and v==int(v)) for line in str(c).splitlines())
                      or re.search(r'(?:RMB|HK\$|CNY|人民币)\s*\d[\d,]*',str(c),re.I)]
        if (amount_cells and not navigation) or re.search(r'复杂|待核验|待专项|合并单元格|非标准财务|complex|needs.review|merged.cell', exclusion_reason or '', re.I):
            return [{'table': index, 'reason': 'financial_complexity_is_not_exclusion', 'instruction': '复杂财务表必须映射；局部无法判断用 unresolved_cells 留原格及具体原因。只有确属封面/目录/独立表头等非财务内容才能排除。'}]
        return []
    issues = []
    first_label=next((str(r[0]).splitlines()[0] for r in table['rows'] if r and str(r[0]).strip()),'')
    total_metric=metric_id(first_label)
    if total_metric:
        for total in column_totals(table):
            for fact in facts:
                ref=fact['source'];span=ref['normalization'].get('numeric_span')
                literal=span['text'] if span else fact['raw_value']
                if fact['metric']==total_metric and ref['column']==total['column'] and decimal_value(literal)!=decimal_value(total['total_text']):
                    issues.append({'table':index,'row':ref['row'],'column':ref['column'],'reason':'group_total_mapped_to_component',
                                   'metric':total_metric,'source_group_heading':first_label,'arithmetic':total,
                                   'instruction':'原文首标签为组标题，列末数字等于前项之和。当前把组总量指标映射到一笔分项；依据原文修正各分项与合计对应顺序。'})
    for mapped in rows:
        number, attrs = mapped['row'], mapped['attributes']
        row = table['rows'][number - 1]
        label = str(attrs.get('label') or row[0])
        columns = decode(attrs.get('columns_json'), []) or decode(schema.get('columns_json'), [])
        ignored = decode(attrs.get('skipped_columns_json'), []) + decode(schema.get('skipped_columns_json'), [])
        ignored = {int(c['column']) for c in ignored if c.get('reason')}
        declared = {int(c['column']) for c in columns if str(c.get('column', '')).isdigit()}
        label_column = int(schema.get('label_column', 1))
        unresolved = decode(attrs.get('unresolved_cells_json'), [])
        unresolved_columns = set()
        for cell in unresolved:
            c = cell.get('column')
            if type(c) is not int or not 1 <= c <= len(row) or not str(cell.get('reason', '')).strip():
                issues.append({'table': index, 'row': number, 'reason': 'invalid_unresolved_cell'})
                continue
            unresolved_columns.add(c)
            issues.append({'table': index, 'row': number, 'column': c, 'reason': 'unresolved_cell_semantics', 'severity': 'review', 'raw_value': row[c-1], 'label': label, 'detail': cell['reason']})
        for c, raw in enumerate(row, 1):
            if c == label_column or c in ignored | declared | unresolved_columns or not numeric_candidate(str(raw)): continue
            header = ' / '.join(str(r[c-1]) for r in table['rows'][:min(number-1, 5)] if len(r) >= c)
            issues.append({'table': index, 'row': number, 'column': c, 'reason': 'unmapped_numeric_column', 'raw_value': raw, 'label': label, 'header': header,
                           'metric_candidates': metric_candidates(label, header), 'instruction': '映射金额、构成比例、百分点或变动列；附注编号等非数据列用 skip_columns 给出理由。真正歧义用 unresolved_cells 保存原格和具体原因。'})
        metrics = [(attrs.get('metric', ''), label)] + [(c.get('metric', ''), str(c.get('label') or label)) for c in columns]
        for metric, metric_label in metrics:
            if metric in {'amount','value','number','data','financial_metric'}:
                issues.append({'table':index,'row':number,'reason':'generic_metric_masks_financial_meaning','metric':metric,'row_metric':attrs.get('metric'),'label':label,
                               'metric_candidates':metric_candidates(label),
                               'instruction':'列级 metric 会覆盖行级财务指标。若行级已经是 cash/bank_deposits 等含义，删除金额列的通用 metric/label，让它继承行级指标；否则按原文财务含义命名。'})
            if re.search(r'^(?:.*_)?(?:row|r|line|item|metric|t\d+_r)_?\d+(?:_|$)', str(metric), re.I):
                issues.append({'table': index, 'row': number, 'reason': 'row_number_metric_id', 'metric': metric, 'label': metric_label,
                               'metric_candidates': metric_candidates(metric_label), 'instruction': '指标 ID 必须表达原文财务含义，不能用行号命名；主体、地区等明细放 dimensions。'})
    return issues
