"""Versioned, value-free mappings, applied to the current source and revalidated.

The library contains hashed normalized row selectors and financial metric IDs.
It never contains source quotes, companies, coordinates into old documents,
numeric values, document IDs, or executable model code.
"""
import hashlib
import json
import re
from .normalization import compact, decimal_value, unit_info
from .standard_metrics import standard_metric, normalize_label, ROWS, VERSION as ROW_VERSION
from .cleaning_batches import header_rows
from .source_numbers import data_number
from .source_periods import report_month, column_period

VERSION = 'cleaning-rules-5/' + ROW_VERSION

# A model sometimes encodes an issuer/fund name in an English metric ID. Such
# document-specific IDs remain local facts, not shared rule-library contents.
# The library accepts financial vocabulary, not arbitrary identifier strings.
FINANCIAL_WORDS=set('_'.join(ROWS).split('_'))|set('''recurring service fee counterparties counterparty rank allowance aged aging years months one two three four five six seven eight nine ten eleven twelve to under over within assessed individually portfolio portion opening closing fixed balance dedicated factoring dairy prepayment prepaid fund funds fvpl fvtpl fvoci fvtoci subtotal microloans milk medium large certificates transfers carrying buildings quote repurchase frozen desserts convertible machinery dividend subsidiaries by electronic deductible input vat land added liquid carbon emission rights industry decreases third party platform yogurt vehicles reversal self cultivation powder disposals guarantees tools transit refund consumer guarantee required reserves with bills increases out provision changes without title deed consignment accum accumulated settlement subrogation written off temporarily idle cip amortization amortisation stage gross net loans term trust structured deposits others total impairment cost project construction equipment fair value wealth management products financial tax rate principal interests prepaid intangible receivable receivables payable payables'''.split())
FINANCIAL_WORDS.update('''account additions age allowances amount balances book budget building calf capitalization capitalized components corporate cows cumulative decrease derecognized down gains heifers investee losses mature nature or ratio recoverable taxpayer top unrealized write writeoff'''.split())


def reusable_metric(metric):
    parts=metric.split('_')
    return bool(parts) and all(p in FINANCIAL_WORDS or (p.isdigit() and any(w in parts for w in ('aged','aging','rank','portfolio','stage'))) for p in parts)


def source_year(parsed):
    for page in parsed['pages']:
        match=re.search(r'((?:19|20)\d{2})\s*年\s*(?:年度|半年度|中期|第?[一三13]季度)报告',page['text'])
        if match:return int(match[1])
        match=re.search(r'(?:six months|year)\s+ended\s+\d{1,2}\s+[A-Za-z]+\s+((?:19|20)\d{2})',page['text'],re.I)
        if match:return int(match[1])
    return parsed.get('report_year')


def mapping_headers(table):
    """Unlike a display preview, an absent header is an empty list.

    A continued table begins with data; treating its first row as a fallback
    header would falsely validate a skipped financial amount.
    """
    headers=[]
    for row in table['rows']:
        if standard_metric(row[0]) if row else False:break
        if any(data_number(c) for c in row[1:]):break
        numeric=[decimal_value(c) for c in row[1:] if decimal_value(c) is not None]
        if numeric and normalize_label(row[0]) not in {'','项目','item','label','类别','note'}:break
        if any(decimal_value(c) is not None and not (1900<=decimal_value(c)<=2100 and decimal_value(c)==int(decimal_value(c))) for c in row[1:]):break
        if any(sum(decimal_value(line) is not None for line in str(c).splitlines())>1 for c in row[1:]):break
        headers.append(row)
    return headers if any(str(c).strip() for row in headers for c in row[1:]) else []


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
    page=next(p for p in parsed['pages'] if p['page']==table['page'])
    if table.get('bbox') and page.get('words'):
        # Repeated balances can occur both above and below a parent-company
        # heading on one page. Use actual table geometry, not the first global
        # occurrence of that balance, to select the applicable title and unit.
        lines={}
        for word in page['words']:
            if word['bbox'][3]<=table['bbox'][1]+1:
                lines.setdefault(round(word['bbox'][1]/3),[]).append(word)
        prefix='\n'.join(' '.join(w['text'] for w in sorted(words,key=lambda w:w['bbox'][0])) for _,words in sorted(lines.items()))
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
    titles = list(re.finditer(r'(?m)^\s*(?:(?:\d+|[一二三四五六七八九十]+)[、.．]\s*)?(?:合并|母公司)?(?:资产负债表|利润表|现金流量表|所有者权益变动表)\s*$|Statement\s+of\s+(?:Financial\s+Position|Comprehensive\s+Income|Profit\s+or\s+Loss|Cash\s+Flows|Changes\s+in\s+Equity)|财务报表项目注释|Notes\s+to', preceding, re.I))
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
    matches = list(re.finditer(r'单位\s*[:：]\s*(?:人民币)?\s*(亿元|百万元|万元|千元|元)|(?:RMB|HK\$|USD)\s*(?:[’\']?\s*000|thousand|million)', text, re.I))
    if not matches: return None
    unit = matches[-1].group(1) or matches[-1].group()
    currency = unit_info(unit)[2]
    if currency == 'unknown': return None
    return unit, currency


def source_columns(table, parsed, ctx):
    headers = mapping_headers(table)
    if not headers and ctx['statement'] in {'balance','income','cashflow','equity'}:
        for prior in reversed([t for t in parsed['tables'] if t['index']<table['index']]):
            old=context(parsed,prior)
            if (old['statement'],old['scope'])!=(ctx['statement'],ctx['scope']):break
            if mapping_headers(prior) and max(map(len,prior['rows']),default=0)==max(map(len,table['rows']),default=0):
                headers=mapping_headers(prior);break
    year = source_year(parsed)
    if not year: return []
    width = max(map(len, table['rows']), default=0)
    date_context=ctx['text']+' '+' '.join(str(c) for row in headers for c in row)
    columns = []
    for col in range(1, width):
        labels=[str(row[col]) for row in headers if len(row)>col]
        if any(re.fullmatch(r'\s*(?:19|20)\d{2}\s*',s) for s in labels):
            # A prose introduction can mention both comparative years above
            # the actual date/year header. The separate year row disambiguates.
            labels=[s for s in labels if len(set(re.findall(r'(?:19|20)\d{2}',s)))<=1]
        text = compact(' '.join(labels))
        if re.search(r'附注|^note', text, re.I): continue
        period = column_period(text,date_context,ctx['statement'],report_month(parsed),year)
        if period['period']=='unknown' and not any(len(row)>col and data_number(row[col]) for row in table['rows'][len(mapping_headers(table)):]):continue
        # Complex subcolumns require a learned mapping or the model. No amount
        # interpretation is inferred from a year shared by a merged header.
        if re.search(r'比例|增减|增长|计提|坏账|减值|账面价值|终止确认', text): continue
        columns.append({'column': col+1, **period})
    return columns


EQUITY_MOVEMENTS={
 '上年年末余额':'equity_prior_year_closing', '本年期初余额':'equity_opening',
 '本期期末余额':'equity_closing','本期增减变动金额':'equity_movement',
 '会计政策变更':'accounting_policy_change','前期差错更正':'prior_period_error_correction',
 '同一控制下企业合并':'common_control_combination','综合收益总额':'comprehensive_income',
 '所有者投入和减少资本':'owners_contributions_and_withdrawals',
 '所有者投入的普通股':'ordinary_share_contributions','其他权益工具持有者投入资本':'other_equity_instrument_contributions',
 '股份支付计入所有者权益的金额':'share_based_payments',
 '利润分配':'profit_distribution','提取盈余公积':'surplus_reserve_appropriation',
 '提取一般风险准备':'general_risk_reserve_appropriation',
 '对所有者(或股东)的分配':'distribution_to_owners',
 '所有者权益内部结转':'internal_equity_transfers',
 '资本公积转增资本(或股本)':'capital_reserve_capitalization','盈余公积转增资本(或股本)':'surplus_reserve_capitalization',
 '盈余公积弥补亏损':'surplus_reserve_loss_offset',
 '设定受益计划变动额结转留存收益':'defined_benefit_transfer_to_retained_earnings',
 '其他综合收益结转留存收益':'oci_transfer_to_retained_earnings',
 '专项储备':'special_reserve_movement','本期提取':'special_reserve_appropriation','本期使用':'special_reserve_utilization',
}


def equity_draft(parsed,table,company,basis,ctx,unit):
    headers=mapping_headers(table);inherited=headers
    if not headers:
        for previous in reversed([t for t in parsed['tables'] if t['index']<table['index']]):
            prevctx=context(parsed,previous)
            if (prevctx['statement'],prevctx['scope'])!=(ctx['statement'],ctx['scope']):break
            if mapping_headers(previous):inherited=mapping_headers(previous);break
    years={int(y) for row in inherited for c in row for y in re.findall(r'(20\d{2})\s*年度',str(c))}
    if len(years)!=1:return None
    year=years.pop();columns=[]
    for c in range(1,max(map(len,table['rows']),default=0)):
        labels=[normalize_label(row[c]) for row in inherited if len(row)>c and str(row[c]).strip()]
        metric=next((standard_metric(label) for label in reversed(labels) if standard_metric(label)),None)
        if labels and labels[-1]=='小计':metric='equity_parent'
        if labels and labels[-1]=='优先股':metric='preferred_shares'
        if labels and labels[-1]=='永续债':metric='perpetual_bonds'
        if metric:columns.append({'column':c+1,'metric':metric,'period':f'{year}-FY'})
    def section_after(raw,current):
        label=normalize_label(raw)
        if re.match(r'^\s*[（(][一二三四五六]',str(raw)):
            return 'equity' if label=='其他' else EQUITY_MOVEMENTS.get(label,current)
        if label=='本期增减变动金额':return 'equity_movement'
        return current
    rows=[];unknown=[];section='opening_adjustments'
    if not headers:
        previous_tables=[]
        for previous in reversed([t for t in parsed['tables'] if t['index']<table['index']]):
            prevctx=context(parsed,previous)
            if (prevctx['statement'],prevctx['scope'])!=(ctx['statement'],ctx['scope']):break
            previous_tables.append(previous)
            if mapping_headers(previous):break
        for previous in reversed(previous_tables):
            for row in previous['rows']:section=section_after(row[0],section)
    for n,row in enumerate(table['rows'],1):
        if n<=len(headers):continue
        label=normalize_label(row[0])
        movement=EQUITY_MOVEMENTS.get(label)
        section=section_after(row[0],section)
        if label=='其他':movement=section+'_other'
        if not any(decimal_value(c) is not None for c in row[1:]):continue
        if not movement:unknown.append(n);continue
        period=f'{year-1}-12-31' if movement=='equity_prior_year_closing' else f'{year}-01-01' if movement=='equity_opening' else f'{year}-12-31' if movement=='equity_closing' else f'{year}-FY'
        rows.append({'row':n,'attributes':{'metric':movement,'label':row[0],
                    'columns_json':json.dumps([{**c,'period':period} for c in columns])}})
    return {'index':table['index'],'schema':{'company':company,'statement':'equity','scope':ctx['scope']+'_'+basis['basis'],
            'unit':unit[0],'currency':unit[1],'columns_json':json.dumps(columns),
            'skipped_rows_json':json.dumps([{'row':i,'reason':'source header'} for i in range(1,len(headers)+1)])},
            'rows':rows,'unmapped_rows':unknown}


def shape(parsed, table):
    ctx = context(parsed, table)
    headers = mapping_headers(table)
    pattern = [[re.sub(r'(?:19|20)\d{2}', '<year>', compact(c).casefold()) for c in row] for row in headers]
    # All original text, including header wording, is hashed before storage.
    return digest([VERSION, report_month(parsed), ctx['statement'], ctx['topic'], max(map(len, table['rows']), default=0), pattern])


def row_key(row):
    return digest(normalize_label(row[0]) if row else '')


def packed_standard(table, columns, company, basis, ctx, unit):
    # Standard labels are declared once; the SDK pairs literal source spans,
    # including dash placeholders, and refuses a different logical row count.
    if ctx['statement']!='cashflow':return None
    lines=[line.strip() for row in table['rows'][len(mapping_headers(table)):] for line in str(row[0]).splitlines() if line.strip()]
    metrics=[]
    for line in lines:
        if re.fullmatch(r'Cash flows from (?:operating|investing|financing) activities',line,re.I):continue
        metric=standard_metric(line)
        if not metric:return None
        metrics.append({'metric':metric,'label':line})
    if not metrics:return None
    from .cleaning_sdk import Cleaner
    cleaner=Cleaner.__new__(Cleaner);cleaner.source={'company':company};cleaner.tables={table['index']:table};cleaner.results={}
    cleaner.map_series(table['index'],columns,metrics,data_rows=range(len(mapping_headers(table))+1,len(table['rows'])+1),
                       statement=ctx['statement'],scope=ctx['scope']+'_'+basis['basis'],currency=unit[1],unit=unit[0])
    result=cleaner.results[table['index']]
    return None if result.get('mapping_error') else result|{'unmapped_rows':[]}


def draft(parsed, table, company, basis, learned=None):
    ctx = context(parsed, table)
    unit = source_unit(ctx['text'])
    if unit is None:unit=source_unit(' '.join(str(c) for row in mapping_headers(table) for c in row))
    if unit is None:
        # A continuation may inherit an explicitly stated unit, never a guessed
        # currency from the company's country or filename.
        unit = source_unit(ctx['preceding'])
    if unit is None: return None
    if ctx['statement']=='equity':return equity_draft(parsed,table,company,basis,ctx,unit)
    columns = source_columns(table, parsed, ctx)
    learned = learned or {}
    year = source_year(parsed)
    if learned.get('columns') and year:
        columns = rebind_periods(bind_columns(learned['columns'],year),columns)
    if not columns: return None
    if any('\n' in str(row[0]) for row in table['rows'][len(mapping_headers(table)):]):
        packed=packed_standard(table,columns,company,basis,ctx,unit)
        if packed:return packed
    skip = [{'row':i,'reason':'source header'} for i in range(1,len(mapping_headers(table))+1)]
    rows = []; unknown = [];finance_subsection=False
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
            selectors=attrs.pop('dimension_columns',{})
            dimensions=attrs.pop('dimensions',{})|{key:row[column-1] for key,column in selectors.items()}
            if dimensions:attrs['dimensions_json']=json.dumps(dimensions,ensure_ascii=False)
            if attrs.get('columns'):attrs['columns_json']=json.dumps(rebind_periods(bind_columns(attrs.pop('columns'),year),columns))
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
        if ctx['statement']=='income':
            if attrs['metric']=='finance_expenses':finance_subsection=True
            elif finance_subsection and attrs['metric'] in {'interest_expense','interest_income'}:
                attrs['dimensions_json']=json.dumps({'statement_section':'finance_expenses'})
            else:finance_subsection=False
        if attrs['metric'] in {'eps','eps_diluted'}: attrs.update(unit='元/股',currency=unit[1]+'/share')
        if attrs['metric'] == 'roe': attrs.update(unit='%',currency='percent')
        rows.append({'row':number,'attributes':attrs})
    schema = {'company':company,'statement':ctx['statement'],'scope':ctx['scope']+'_'+basis['basis'],
              'unit':unit[0],'currency':unit[1],'columns_json':json.dumps(columns,ensure_ascii=False),
              'skipped_rows_json':json.dumps(skip),'label_column':1}
    headers=mapping_headers(table)
    note_columns=[i+1 for i,c in enumerate(headers[0] if headers else []) if re.fullmatch(r'附注|notes?',compact(c),re.I)]
    if not headers and ctx['statement'] in {'balance','income','cashflow'}:
        for prior in reversed([t for t in parsed['tables'] if t['index']<table['index']]):
            old=context(parsed,prior)
            if (old['statement'],old['scope'])!=(ctx['statement'],ctx['scope']):break
            previous=mapping_headers(prior)
            if previous:
                note_columns=[i+1 for i,c in enumerate(previous[0]) if re.fullmatch(r'附注|notes?',compact(c),re.I)];break
    if note_columns:schema['skipped_columns_json']=json.dumps([{'column':c,'reason':'note reference'} for c in note_columns])
    if learned.get('skipped_columns'): schema['skipped_columns_json'] = json.dumps(learned['skipped_columns'])
    return {'index':table['index'],'schema':schema,'rows':rows,'unmapped_rows':unknown}


def rebind_periods(columns,source):
    periods={c['column']:{k:c[k] for k in ('period','start','end') if k in c} for c in source}
    return [{k:v for k,v in c.items() if k not in {'period','start','end'}} |
            periods.get(c['column'],{'period':'unknown'}) for c in columns]


def bind_columns(columns,year):
    result=[]
    for c in columns:
        bound={k:v for k,v in c.items() if not k.endswith('_template')}
        for field in ('period','start','end'):
            if field+'_template' in c:
                offset,suffix=c[field+'_template'];bound[field]=f'{int(year)+offset}-{suffix}'
        result.append(bound)
    return result


def column_rule(columns,year,schema):
    converted=[]
    for c in columns:
        if set(c)-{'column','period','unit','currency','metric','semantic_type','label','start','end'}:return None
        period=re.fullmatch(r'(\d{4})-(FY|H1|H2|9M|Q[1-4]|\d{2}-\d{2})',c.get('period',''))
        if not period:return None
        rule={k:v for k,v in c.items() if k not in {'period','label','start','end'}}|{'period_template':[int(period[1])-int(year),period[2]]}
        if rule.get('metric') and not reusable_metric(rule['metric']):return None
        for field in ('start','end'):
            if c.get(field):
                date=re.fullmatch(r'(\d{4})-(\d{2}-\d{2})',c[field])
                if not date:return None
                rule[field+'_template']=[int(date[1])-int(year),date[2]]
        for field in ('unit','currency'):
            if rule.get(field)==schema.get(field):rule.pop(field,None)
        converted.append(rule)
    return converted


def compile_rule(parsed, table, item):
    """Learn only coordinate-independent mappings that can be rebound exactly."""
    if item['issues'] or item['exclusion_reason']: return None
    schema = item['schema']; year = source_year(parsed)
    if not year or schema.get('label_column',1) != 1: return None
    columns = json.loads(schema.get('columns_json','[]'))
    converted=column_rule(columns,year,schema)
    if converted is None:return None
    rows={}
    for row in item['mapping']:
        attrs=row['attributes']
        # Values, citations, dimensions containing company identities, custom
        # spans and unresolved cells never cross the document boundary.
        if any(attrs.get(k) for k in ('unresolved_cells_json','company','attribution','numeric_span')): return None
        dims=attrs.get('dimensions_json',{})
        dims=json.loads(dims) if isinstance(dims,str) else dims
        source_row=table['rows'][row['row']-1];selectors={};semantic_dimensions={}
        for key,value in dims.items():
            # A row subject is rebound from the new table's label, never copied
            # out of the original company/customer/account name.
            matches=[i+1 for i,c in enumerate(source_row) if str(c)==value and decimal_value(c) is None]
            if len(matches)==1:selectors[key]=matches[0]
            elif value in {'portfolio','individual','joint_venture','associate','gross','net','allowance','current','noncurrent','finance_expenses'} or (key=='asset_class' and value in ROWS):semantic_dimensions[key]=value
            else:return None
        metric=attrs.get('metric','')
        if not re.fullmatch(r'[a-z][a-z0-9_]*',metric) or not reusable_metric(metric): return None
        selector=row_key(table['rows'][row['row']-1])
        target={k:attrs[k] for k in ('metric','unit','currency') if attrs.get(k)}
        for field in ('unit','currency'):
            if target.get(field)==schema.get(field):target.pop(field,None)
        if selectors:target['dimension_columns']=selectors
        if semantic_dimensions:target['dimensions']=semantic_dimensions
        if attrs.get('columns_json'):
            actual=json.loads(attrs['columns_json']) if isinstance(attrs['columns_json'],str) else attrs['columns_json']
            override=column_rule(actual,year,schema)
            if override is None:return None
            target['columns']=override
        # Repeated labels can denote different financial sections. A single
        # label selector cannot encode both; never overwrite the earlier one.
        if selector in rows and rows[selector]!=target:return None
        rows[selector]=target
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
