"""Structural scheduling and lossless model views, independent of the Pi loop."""
import json
import re
from collections import OrderedDict
from .normalization import decimal_value
from .semantic import numeric_candidate


def numeric_tables(parsed):
    return [t for t in parsed['tables'] if any(numeric_candidate(c) for row in t['rows'] for c in row)]


def table_view(table):
    # Rows carry all literal content. Geometry is needed only for merged cells;
    # all original bboxes/cell metadata remain in get_source_table and the SDK.
    merged = {key: value for key, value in table.get('cells', {}).items() if value.get('merged_range')}
    return {'index': table['index'], 'page': table['page'], 'rows': [{'row':i,'cells':row} for i,row in enumerate(table['rows'],1)], 'column_totals':column_totals(table),
            **({'sheet': table['sheet']} if table.get('sheet') else {}),
            **({'merged_cells': merged} if merged else {})}


def column_totals(table):
    """Exact arithmetic hints, never a guess about a metric's financial meaning."""
    totals=[];rows=table['rows'];start=len(header_rows(table))
    for column in range(2,max(map(len,rows),default=0)+1):
        values=[]
        for number,row in enumerate(rows[start:],start+1):
            if len(row)<column:continue
            raw=str(row[column-1])
            for line in raw.splitlines():
                value=decimal_value(line)
                if value is not None:values.append((number,value,line))
        if len(values)>=3 and values[-1][1]==sum(v for _,v,_ in values[:-1]) and values[-1][1]!=0:
            totals.append({'column':column,'total_row':values[-1][0],'total_text':values[-1][2],
                           'relationship':'last numeric item equals the sum of all preceding numeric items in this column',
                           'terms':len(values)-1,'meaning':'Use original labels to distinguish group heading, components and total.'})
    return totals


def header_rows(table):
    headers = []
    for row in table['rows'][:4]:
        values = [decimal_value(str(c)) for c in row[1:]]
        # Numeric years alone are headers; amounts identify the first data row.
        packed = any(sum(decimal_value(line) is not None for line in str(c).splitlines()) > 1 for c in row[1:])
        if packed or any(v is not None and not (1900 <= v <= 2100 and v == int(v)) for v in values):
            break
        headers.append(row)
    return headers or table['rows'][:1]


def section(text):
    compact = re.sub(r'\s+', ' ', text).casefold()
    if re.search(r'notes to.*financial|财务报表附注|财务报告.*附注', compact): return 'notes'
    if re.search(r'statement of|资产负债表|利润表|现金流量表|权益变动表', compact): return 'statements'
    # Page headers identify the broad section; do not infer financial semantics.
    lines = [re.sub(r'\s+', ' ', s).strip() for s in text.splitlines() if s.strip()]
    return re.sub(r'\d+', '#', lines[0] if lines else '').casefold()


def structural_batches(parsed, indices=None, budget_chars=24000):
    pages = {p['page']: p['text'] for p in parsed['pages']}
    wanted = set(indices) if indices is not None else None
    groups = OrderedDict()
    for table in numeric_tables(parsed):
        if wanted is not None and table['index'] not in wanted: continue
        header = header_rows(table)
        pattern = [[re.sub(r'\b(?:19|20|21)\d{2}\b', '<year>', re.sub(r'\s+', ' ', str(c)).strip()).casefold() for c in row] for row in header]
        key = (section(pages.get(table['page'], '')), max(map(len, table['rows']), default=0), json.dumps(pattern, ensure_ascii=False))
        groups.setdefault(key, []).append(table)
    batches = []
    for (chapter, columns, _), tables in groups.items():
        current, size = [], 0
        for table in tables:
            proposed=current+[table['index']]
            chars = len(json.dumps(batch_view(parsed,{'tables':proposed},''), ensure_ascii=False, separators=(',', ':')))
            if current and chars > budget_chars:
                batches.append({'tables': current, 'source_chars': size, 'section': chapter, 'columns': columns})
                current, size = [], 0
                chars=len(json.dumps(batch_view(parsed,{'tables':[table['index']]},''), ensure_ascii=False, separators=(',', ':')))
            current.append(table['index']); size = chars
        if current: batches.append({'tables': current, 'source_chars': size, 'section': chapter, 'columns': columns})
    return batches


def batch_view(parsed, batch, document_id):
    tables = [t for t in parsed['tables'] if t['index'] in set(batch['tables'])]
    pages = {p['page']: p['text'] for p in parsed['pages']}
    # Keep headings/units/prose; table rows already contain the cell text. Only
    # exact normalized table lines are deduplicated, never unknown evidence.
    contexts = []
    for page in dict.fromkeys(t['page'] for t in tables):
        cells = {re.sub(r'\s+', '', str(c)) for t in tables if t['page'] == page for r in t['rows'] for c in r if str(c).strip()}
        lines = [line for line in pages[page].splitlines() if line.strip() and re.sub(r'\s+', '', line) not in cells]
        contexts.append({'page': page, 'text': '\n'.join(lines), 'projection': 'Exact standalone cell lines occur once in tables.rows; full page available via get_source_page.'})
    return {**batch, 'document_id': document_id, 'tables': [table_view(t) for t in tables], 'page_contexts': contexts,
            'full_source_tools': ['get_source_table', 'get_source_page'], 'coordinates': 'index is zero based; row and column are one based'}
