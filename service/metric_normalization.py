"""Normalize source-backed row IDs without changing amounts or inventing aliases."""
import re
from .standard_metrics import STANDARD_METRICS, exact_standard_metric, normalize_label, workpaper_concepts

VERSION = 'source-metric-1'


def source_metric(table, fact):
    ref = fact['source']
    meta = ref.get('normalization', {})
    if meta.get('statement') == 'equity':
        return None, None
    row, column = ref.get('row'), ref.get('column')
    if not isinstance(row, int) or not isinstance(column, int) or not 1 <= row <= len(table['rows']):
        return None, None
    cells = table['rows'][row - 1]
    # An explicit metric column owns a matrix; period-only columns do not.
    column_label = meta.get('column_label')
    column_metric = exact_standard_metric(column_label) if column_label else None
    if column_metric:
        for i, header in enumerate(table['rows'][:row - 1], 1):
            if column <= len(header) and normalize_label(header[column - 1]) == normalize_label(column_label):
                return column_metric, {'axis': 'column', 'row': i, 'column': column, 'label': header[column - 1]}
    from .cleaning_rules import mapping_headers
    headings = ' '.join(str(c) for r in mapping_headers(table) for c in r)
    period_column = bool(column_label and re.fullmatch(
        r'(?:(?:20\d{2}(?:年(?:\d{1,2}月(?:\d{1,2}日)?)?)?)|本期|上期|本年|上年|期初|期末|年初|年末|报告期|本报告期|末|初|数|金额|余额|发生额|账面价值|账面余额|年度|调整前|调整后|重述前|重述后|[()（）/\-])+',
        normalize_label(column_label)))
    # These measured matrices have several different monetary measures, not
    # just comparative periods. A row alone cannot define their cell metric.
    if not period_column and re.search(r'变动|影响金额|购买|购入|出售|售出|赎回|初始投资|计提|转回|核销', normalize_label(headings)):
        return None, None
    # Parallel tables can have more than one label column. Use the nearest
    # actual standard label to the left of this value, not the opposite side.
    labels = [(c, value, exact_standard_metric(value)) for c, value in enumerate(cells[:column - 1], 1)]
    labels = [(c, value, metric) for c, value, metric in labels if metric]
    if not labels:
        return None, None
    c, label, metric = labels[-1]
    declared = meta.get('row_label')
    if declared and normalize_label(declared) != normalize_label(label) and exact_standard_metric(declared) != metric:
        return None, None
    column_label = meta.get('column_label') or ''
    # Measured regressions: change/purchase/provision columns and adjusted
    # differences are not the balance/expense named by the row axis.
    if normalize_label(column_label) != normalize_label(declared or label) and re.search(
            r'变动|增减|调整数|调整金额|购买|购入|出售|售出|赎回|初始投资|转回|计提|核销|处置|重分类|影响|不含|未包含', column_label):
        return None, None
    if re.search(r'净利润(?:调节|调整)为', normalize_label(headings)) and not set(workpaper_concepts(metric)) & {'cfo', 'net_profit', 'cash_begin', 'cash_end'}:
        return None, None
    # A growth/composition column on a money row remains a ratio.
    if meta.get('unit_kind') == 'ratio_percent' or fact.get('raw_unit') in {'%', '％', '百分点'}:
        return None, None
    return metric, {'axis': 'row', 'row': row, 'column': c, 'label': label}


def apply_metric_normalization(table, facts):
    review = []
    for fact in facts:
        if fact['metric'] in STANDARD_METRICS:
            continue
        metric, evidence = source_metric(table, fact)
        meta = fact['source'].setdefault('normalization', {})
        if not metric:
            review.append({'metric': fact['metric'], 'table_id': fact['source'].get('table_id'),
                           'row': fact['source'].get('row'), 'column': fact['source'].get('column'),
                           'reason': '原行或列标签不能精确确定标准指标，保留原 ID'})
            continue
        if fact['metric'] != metric:
            aliases = meta.setdefault('metric_aliases', [])
            if fact['metric'] not in aliases:
                aliases.append(fact['metric'])
            fact['metric'] = metric
            meta['metric_normalization'] = {'version': VERSION, 'canonical_metric': metric, 'evidence': evidence}
    return review


def pending_metric_review(store, document_id, table_id=None):
    """Read-time work list, including unrecognized labels; it never blocks commits."""
    import json
    with store.connect() as db:
        tables = {r['table_id']: {'rows': json.loads(r['rows_json'])} for r in db.execute(
            'SELECT table_id,rows_json FROM source_tables WHERE document_id=?', (document_id,))}
        facts = [dict(r) for r in db.execute('SELECT * FROM current_financial_facts WHERE document_id=?', (document_id,))]
    review = []
    for fact in facts:
        ref = json.loads(fact['source_json'])
        tid = ref.get('table_id')
        if tid not in tables or table_id and tid != table_id or fact['metric'] in STANDARD_METRICS:
            continue
        metric, evidence = source_metric(tables[tid], {**fact, 'source': ref})
        review.append({'fact_id': fact['fact_id'], 'metric': fact['metric'], 'table_id': tid,
                       'row': ref.get('row'), 'column': ref.get('column'), 'canonical_candidate': metric,
                       'reason': '原标签可确定标准指标，等待重新应用' if metric else '原标签不能确定标准指标，保留原 ID',
                       'evidence': evidence})
    return review
