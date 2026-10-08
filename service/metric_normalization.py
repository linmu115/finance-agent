"""Normalize source-backed row IDs without changing amounts or inventing aliases."""
import re
from .standard_metrics import STANDARD_METRICS, CONTEXTUAL_LABELS, exact_standard_metric, normalize_label, workpaper_concepts
from .metric_context import source_metric_context, column_semantics

VERSION = 'source-metric-2'


def source_metric(table, fact, context=None):
    ref = fact['source']
    meta = ref.get('normalization', {})
    if meta.get('statement') == 'equity':
        return None, None
    row, column = ref.get('row'), ref.get('column')
    if not isinstance(row, int) or not isinstance(column, int) or not 1 <= row <= len(table['rows']):
        return None, None
    cells = table['rows'][row - 1]
    semantic_context = source_metric_context(table, row, context)
    resolve = lambda label: exact_standard_metric(label, context=semantic_context)
    # An explicit metric column owns a matrix; period-only columns do not.
    column_label = meta.get('column_label')
    column_metric = resolve(column_label) if column_label else None
    if column_metric:
        for i, header in enumerate(table['rows'][:row - 1], 1):
            if column <= len(header) and normalize_label(header[column - 1]) == normalize_label(column_label):
                evidence = {'axis': 'column', 'row': i, 'column': column, 'label': header[column - 1]}
                if normalize_label(column_label) in CONTEXTUAL_LABELS:
                    evidence['semantic_context'] = semantic_context
                return column_metric, evidence
    meaning = column_semantics(table, row, column, column_label)
    if not meaning['row_metric_safe']:
        return None, {'reason':'列含独立计量含义，行名不能唯一确定该格指标，保留原 ID', 'column_semantics':meaning}
    from .cleaning_rules import mapping_headers
    headings = ' '.join(str(c) for r in mapping_headers(table) for c in r)
    # Parallel tables can have more than one label column. Use the nearest
    # actual standard label to the left of this value, not the opposite side.
    labels = [(c, value, resolve(value)) for c, value in enumerate(cells[:column - 1], 1)]
    labels = [(c, value, metric) for c, value, metric in labels if metric]
    if not labels:
        return None, None
    c, label, metric = labels[-1]
    declared = meta.get('row_label')
    if declared and normalize_label(declared) != normalize_label(label) and resolve(declared) != metric:
        return None, None
    if re.search(r'净利润(?:调节|调整)为', normalize_label(headings)) and not set(workpaper_concepts(metric)) & {'cfo', 'net_profit', 'cash_begin', 'cash_end'}:
        return None, None
    # A growth/composition column on a money row remains a ratio.
    if meta.get('unit_kind') == 'ratio_percent' or fact.get('raw_unit') in {'%', '％', '百分点'}:
        return None, None
    evidence = {'axis': 'row', 'row': row, 'column': c, 'label': label}
    if normalize_label(label) in CONTEXTUAL_LABELS:
        evidence['semantic_context'] = semantic_context
    return metric, evidence


def apply_metric_normalization(table, facts, context=None):
    """F2.0: candidates are read-only; ingestion never rewrites metric IDs."""
    review = []
    for fact in facts:
        metric, evidence = source_metric(table, fact, context)
        if metric != fact['metric']:
            review.append({'metric': fact['metric'], 'canonical_candidate': metric,
                           'table_id': fact['source'].get('table_id'),
                           'row': fact['source'].get('row'), 'column': fact['source'].get('column'),
                           'reason': 'F2.0 已停用指标 ID 改写；仅供待核', 'evidence': evidence})
    return review


def pending_metric_review(store, document_id, table_id=None):
    """Read-time work list, including unrecognized labels; it never blocks commits."""
    import json
    from .cleaning_rules import context
    from .table_identity import table_index
    with store.connect() as db:
        prepared = db.execute('SELECT prepared_json FROM prepared_documents WHERE document_id=?', (document_id,)).fetchone()
        parsed = json.loads(prepared[0]) if prepared else None
        tables = {r['table_id']: {'rows': json.loads(r['rows_json'])} for r in db.execute(
            'SELECT table_id,rows_json FROM source_tables WHERE document_id=?', (document_id,))}
        facts = [dict(r) for r in db.execute('SELECT * FROM current_financial_facts WHERE document_id=?', (document_id,))]
    review = []
    table_contexts = {}
    prepared_tables = {t['index']:t for t in parsed['tables']} if parsed else {}
    for fact in facts:
        ref = json.loads(fact['source_json'])
        tid = ref.get('table_id')
        if tid not in tables or table_id and tid != table_id:
            continue
        if tid not in table_contexts:
            table = prepared_tables.get(table_index(tid,document_id),tables[tid])
            table_contexts[tid] = (table, context(parsed,table) if parsed and 'page' in table else None)
        table, ctx = table_contexts[tid]
        metric, evidence = source_metric(table, {**fact, 'source': ref}, ctx)
        if fact['metric'] in STANDARD_METRICS and not (evidence or {}).get('reason'):
            continue
        review.append({'fact_id': fact['fact_id'], 'metric': fact['metric'], 'table_id': tid,
                       'row': ref.get('row'), 'column': ref.get('column'), 'canonical_candidate': metric,
                       'reason': '原标签可确定标准指标，等待重新应用' if metric else (evidence or {}).get('reason', '原标签不能确定标准指标，保留原 ID'),
                       'evidence': evidence})
    return review
