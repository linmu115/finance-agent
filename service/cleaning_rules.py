"""Versioned, value-free mappings, applied to the current source and revalidated.

The library contains hashed normalized row selectors and financial metric IDs.
It never contains source quotes, companies, coordinates into old documents,
numeric values, document IDs, or executable model code.
"""
import hashlib
import json
import re
from .normalization import compact, decimal_value, unit_info
from .standard_metrics import standard_metric, normalize_label, VERSION as ROW_VERSION
from .cleaning_batches import header_rows

VERSION = 'cleaning-rules-1/' + ROW_VERSION


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def initialize(db):
    db.execute('CREATE TABLE IF NOT EXISTS cleaning_rules(signature TEXT,version TEXT,rule_id TEXT PRIMARY KEY,mapping_json TEXT NOT NULL,created_at TEXT NOT NULL)')
    db.execute('CREATE INDEX IF NOT EXISTS cleaning_rules_signature ON cleaning_rules(signature,version)')


def context(parsed, table):
    """Use headings preceding this table, including a continued prior page."""
    pages = {p['page']: p['text'] for p in parsed['pages']}
    text = pages[table['page']]
    # A literal amount anchors the table more precisely than a repeated 项目.
    anchors = [str(c).strip() for row in table['rows'] for c in row[1:] if decimal_value(c) is not None and decimal_value(c) != 0 and len(str(c)) > 5]
    locations = [text.find(a) for a in anchors if text.find(a) >= 0]
    prefix = text[:min(locations)] if locations else text
    preceding = '\n'.join(pages[p] for p in sorted(pages) if p < table['page']) + '\n' + prefix
    headings = re.findall(r'(?m)^\s*(?:\d+\s*[、．.]|[一二三四五六七八九十]+[、．])\s*([^\n]+)', preceding)
    topic = next((standard_metric(h) for h in reversed(headings) if standard_metric(h)), None)
    # A subtable such as "其他货币资金明细如下" has its own total.
    subheadings=list(re.finditer(r'(?m)^\s*([^\n：:]+?)(?:明细如下|明细情况)\s*[:：]?',prefix))
    if subheadings:
        subtopic=standard_metric(subheadings[-1][1])
        if subtopic:topic=subtopic
    scopes = re.findall(r'母公司(?:资产负债表|利润表|现金流量表|所有者权益变动表|财务报表)|合并(?:资产负债表|利润表|现金流量表|所有者权益变动表|财务报表)|Consolidated', preceding, re.I)
    scope = 'parent' if scopes and scopes[-1].startswith('母公司') else 'consolidated' if scopes else 'unspecified'
    titles = list(re.finditer(r'资产负债表|利润表|现金流量表|所有者权益变动表|Statement\s+of\s+(?:Financial\s+Position|Comprehensive\s+Income|Profit\s+or\s+Loss|Cash\s+Flows|Changes\s+in\s+Equity)|财务报表项目注释|Notes\s+to', preceding, re.I))
    title = titles[-1].group() if titles else ''
    statement = ('balance' if re.search(r'资产负债表|Financial\s+Position', title, re.I) else
                 'income' if re.search(r'利润表|Income|Profit', title, re.I) else
                 'cashflow' if re.search(r'现金流量表|Cash', title, re.I) else
                 'equity' if re.search(r'权益变动表|Equity', title, re.I) else 'notes')
    return {'topic': topic, 'scope': scope, 'statement': statement, 'text': prefix, 'preceding': preceding}


def priority(parsed, table):
    ctx = context(parsed, table)
    if ctx['statement'] in {'balance', 'income', 'cashflow', 'equity'}: return 0
    if re.search(r'主要会计数据|非经常性损益|现金流量.*补充资料|分季度|分部信息|segment information', ctx['text'], re.I): return 1
    return 2


def source_unit(text):
    matches = list(re.finditer(r'单位\s*[:：]\s*(?:人民币)?\s*(亿元|百万元|万元|千元|元)|(?:RMB|HK\$|USD)\s*[’\']?\s*000', text, re.I))
    if not matches: return None
    unit = matches[-1].group(1) or matches[-1].group()
    currency = unit_info(unit)[2]
    if currency == 'unknown': return None
    return unit, currency


def source_columns(table, parsed, ctx):
    headers = header_rows(table)
    year = parsed.get('report_year')
    if not year: return []
    width = max(map(len, table['rows']), default=0)
    columns = []
    for col in range(1, width):
        text = compact(' '.join(str(row[col]) for row in headers if len(row) > col))
        years = re.findall(r'(?<!\d)((?:19|20)\d{2})(?!\d)', text)
        if re.search(r'附注|^note', text, re.I): continue
        role = 'closing' if re.search(r'期末|年末|本期期末', text) else 'opening' if re.search(r'期初|年初|上年年末', text) else 'current' if re.search(r'本期|本年', text) else 'previous' if re.search(r'上期|上年', text) else None
        if years and len(set(years)) == 1: period_year = int(years[0])
        elif role: period_year = int(year) - (role in {'opening', 'previous'})
        else: continue
        balance = ctx['statement'] == 'balance' or role in {'closing', 'opening'} or '余额' in text
        # Explicit month/day takes precedence; interim performance is H1.
        date_match = re.search(r'(?:年)?(\d{1,2})月(\d{1,2})日', text)
        if date_match: period = f'{period_year}-{int(date_match[1]):02d}-{int(date_match[2]):02d}'
        elif balance:
            interim = bool(re.search(r'30\s+June|6\s*月\s*30', ctx['text'], re.I)) and period_year == int(year)
            period = f'{period_year}-06-30' if interim else f'{period_year}-12-31'
        else:
            interim = bool(re.search(r'six months ended|六个月|半年度|中期', ctx['text'], re.I))
            period = f'{period_year}-H1' if interim else f'{period_year}-FY'
        # Complex subcolumns require a learned mapping or the model. No amount
        # interpretation is inferred from a year shared by a merged header.
        if re.search(r'比例|增减|增长|计提|坏账|减值|账面价值|终止确认', text): continue
        columns.append({'column': col+1, 'period': period})
    return columns


def shape(parsed, table):
    ctx = context(parsed, table)
    headers = header_rows(table)
    pattern = [[re.sub(r'(?:19|20)\d{2}', '<year>', compact(c).casefold()) for c in row] for row in headers]
    # All original text, including header wording, is hashed before storage.
    return digest([VERSION, ctx['statement'], ctx['topic'], max(map(len, table['rows']), default=0), pattern])


def row_key(row):
    return digest(normalize_label(row[0]) if row else '')


def draft(parsed, table, company, basis, learned=None):
    ctx = context(parsed, table)
    unit = source_unit(ctx['text'])
    if unit is None:
        # A continuation may inherit an explicitly stated unit, never a guessed
        # currency from the company's country or filename.
        unit = source_unit(ctx['preceding'])
    if unit is None: return None
    columns = source_columns(table, parsed, ctx)
    learned = learned or {}
    year = parsed.get('report_year')
    if learned.get('columns') and year:
        columns = [{**{k:v for k,v in c.items() if k != 'period_template'},
                    'period': f"{int(year)+c['period_template'][0]}-{c['period_template'][1]}"} for c in learned['columns']]
    if not columns: return None
    skip = [{'row':i,'reason':'source header'} for i in range(1,len(header_rows(table))+1)]
    rows = []; unknown = []
    for number, row in enumerate(table['rows'], 1):
        if number <= len(skip): continue
        if not any(decimal_value(c) is not None for c in row[1:]):
            # Packed cells must remain visible to the model, not disappear as
            # blank rows. A normal textual section label needs no fact.
            if any(re.search(r'\d[.,]\d|\d\s*[%％]', str(c)) for c in row[1:]): unknown.append(number)
            continue
        attrs = (learned.get('rows') or {}).get(row_key(row))
        if attrs:
            attrs = json.loads(json.dumps(attrs))
        else:
            metric = standard_metric(row[0])
            if not metric and normalize_label(row[0]) in {'合计','总计','total'}:
                # The total of a complex allowance/movement matrix is not the
                # note's asset balance. Only the plain two-period form applies.
                plain=[compact(c) for c in table['rows'][0]]
                if plain in [['项目','期末余额','期初余额'],['项目','期初余额','期末余额']]:metric=ctx['topic']
            attrs = {'metric':metric} if metric else None
        if attrs is None: unknown.append(number); continue
        attrs['label'] = row[0]
        if attrs['metric'] in {'eps','eps_diluted'}: attrs.update(unit='元/股',currency=unit[1]+'/share')
        if attrs['metric'] == 'roe': attrs.update(unit='%',currency='percent')
        rows.append({'row':number,'attributes':attrs})
    schema = {'company':company,'statement':ctx['statement'],'scope':ctx['scope']+'_'+basis['basis'],
              'unit':unit[0],'currency':unit[1],'columns_json':json.dumps(columns,ensure_ascii=False),
              'skipped_rows_json':json.dumps(skip),'label_column':1}
    if learned.get('skipped_columns'): schema['skipped_columns_json'] = json.dumps(learned['skipped_columns'])
    return {'index':table['index'],'schema':schema,'rows':rows,'unmapped_rows':unknown}


def compile_rule(parsed, table, item):
    """Learn only coordinate-independent mappings that can be rebound exactly."""
    if item['issues'] or item['exclusion_reason']: return None
    schema = item['schema']; year = parsed.get('report_year')
    if not year or schema.get('label_column',1) != 1: return None
    columns = json.loads(schema.get('columns_json','[]'))
    if not columns: return None
    converted=[]
    for c in columns:
        if set(c)-{'column','period','unit','currency','metric','semantic_type'}: return None
        period = re.fullmatch(r'(\d{4})-(FY|H1|H2|Q[1-4]|\d{2}-\d{2})',c.get('period',''))
        if not period: return None
        converted.append({k:v for k,v in c.items() if k!='period'}|{'period_template':[int(period[1])-int(year),period[2]]})
    rows={}
    for row in item['mapping']:
        attrs=row['attributes']
        # Values, citations, dimensions containing company identities, custom
        # spans and unresolved cells never cross the document boundary.
        if any(attrs.get(k) for k in ('columns_json','unresolved_cells_json','company','attribution','numeric_span')): return None
        dims=attrs.get('dimensions_json',{})
        if (json.loads(dims) if isinstance(dims,str) else dims): return None
        metric=attrs.get('metric','')
        if not re.fullmatch(r'[a-z][a-z0-9_]*',metric): return None
        rows[row_key(table['rows'][row['row']-1])] = {k:attrs[k] for k in ('metric','unit','currency') if attrs.get(k)}
    if not rows: return None
    skipped=json.loads(schema.get('skipped_columns_json','[]'))
    return {'columns':converted,'rows':rows,'skipped_columns':[{'column':v['column'],'reason':'non-data header column'} for v in skipped]}


def remember(store, parsed, item):
    rule=compile_rule(parsed,item['table'],item)
    if not rule: return None
    signature=shape(parsed,item['table']);rule_id=digest([VERSION,signature,rule])
    from .store import dumps,utcnow
    with store.connect(write=True) as db:
        db.execute('INSERT OR IGNORE INTO cleaning_rules VALUES(?,?,?,?,?)',(signature,VERSION,rule_id,dumps(rule),utcnow()))
    return rule_id


def lookup(store, parsed, table):
    with store.connect() as db:
        rows=db.execute('SELECT rule_id,mapping_json FROM cleaning_rules WHERE signature=? AND version=? ORDER BY created_at DESC',(shape(parsed,table),VERSION)).fetchall()
    return [(r['rule_id'],json.loads(r['mapping_json'])) for r in rows]
