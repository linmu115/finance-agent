"""Source-local semantic checks. No model call and no cross-document access."""
import json
import re
from decimal import Decimal
from .normalization import decimal_value, unit_info
from .research_ingestion import norm, series_dimensions
from .source_numbers import numeric_cells


def coordinates(fact):
    ref=fact['source']
    return {k:ref.get(k) for k in ('table_id','page','row','column','cell','bbox')} | {
        'value':fact['value'],'raw_value':fact['raw_value'],'raw_unit':fact['raw_unit']}


def panel_boundary(table):
    """Repeated year headers identify independent, horizontally adjacent panels."""
    for row in table['rows']:
        years={}
        for c,raw in enumerate(row,1):
            year=re.match(r'^\s*((?:19|20)\d{2})(?:[AEae]|\s|$)',str(raw))
            if year:
                y=year[1]
                if y in years and c-years[y]>=2:
                    # A separate subject label sits in (or is merged into) the
                    # column immediately before the second panel's first year.
                    if re.search(r'[\u4e00-\u9fff]',str(row[c-2])):
                        return c-1
                years[y]=c
    return None


def table_semantics(table, schema, facts, page_text=''):
    issues=[];index=table['index'];rows=table['rows']
    text='\n'.join(' | '.join(map(str,r)) for r in rows)
    if not facts:
        title=str(rows[0][0]) if rows and rows[0] else ''
        financial=bool(re.search(r'利润表|资产负债表|现金流量表|盈利能力|费用率|每股指标|偿债能力|估值指标',title))
        values=numeric_cells(table)
        # Chart axes and document indexes are not financial observations. These
        # exceptions require source evidence, never just a model-written reason.
        graphic=bool(re.search(r'PE.?Bands|PB.?Bands|沪深\s*300|走势图',text,re.I))
        if values and all(re.fullmatch(r'-?\d+(?:\.\d+)?%',str(v['raw_value'])) for v in values):
            ticks=[decimal_value(str(v['raw_value'])) for v in values]
            steps=[ticks[i]-ticks[i-1] for i in range(1,len(ticks))]
            long_prose=all(not str(rows[v['row']-1][0]).strip() or len(str(rows[v['row']-1][0]))>35
                           or bool(re.search(r'[，。；：]',str(rows[v['row']-1][0]))) for v in values)
            graphic=graphic or bool(steps and long_prose and min(steps)*max(steps)>0 and max(steps)-min(steps)<=1
                                    and re.search(r'沪深\s*300',page_text))
        index_only=bool(re.search(r'报告日期|报告名称|报告标题|报告类型',text))
        index_only=index_only or bool(re.search(r'\bCONTENTS\b|目\s*录',page_text,re.I)
                                     and values and all(re.fullmatch(r'\d{1,3}',str(v['raw_value'])) for v in values))
        if financial or (values and not graphic and not index_only):
            issues.append({'table':index,'page':table['page'],'reason':'numeric_table_without_records',
                           'source_heading':title,'numeric_cell_count':len(values),'numeric_samples':values[:8],
                           'instruction':'数值表不能以缺口说明计为完成。映射原格；若解析只剩表头，依据本页原文重建表体后重新处理。'})
    boundary=panel_boundary(table)
    peer_header=any(re.search(r'公司(?:简称|名称|代码)|证券(?:简称|代码)',str(c)) for row in rows[:5] for c in row)
    for f in facts:
        ref=f['source'];meta=ref['normalization'];r=ref['row'];c=ref['column'];row=rows[r-1]
        if boundary and c>boundary and (meta.get('dimensions') or {}).get('financial_item')==meta.get('row_metric') and meta.get('row_metric')!=f['metric']:
            issues.append({'table':index,'row':r,'column':c,'reason':'parallel_panel_dimension_inheritance',
                           'left_label':row[0],'panel_label':row[boundary-1],'dimension':meta['dimensions']['financial_item'],
                           'instruction':'并排子表拥有独立行标签；此行设置 row_subject=false 并为各列保留本侧指标，或拆成独立逻辑行，不能继承左侧指标维度。'})
        if peer_header:
            subject=str(row[0]);aggregate=bool(re.fullmatch(r'\s*(?:平均(?:值|数)?|中(?:位|间)(?:值|数)?|[Mm]ean|[Mm]edian|[Aa]verage)\s*',subject))
            if aggregate:
                if meta.get('entity_kind','company')=='company' or norm(subject) not in norm(f['company']):
                    issues.append({'table':index,'row':r,'column':c,'reason':'peer_aggregate_assigned_to_company',
                                   'source_subject':subject,'company':f['company'],
                                   'instruction':'平均值/中位数属于可比组统计，主体用原文统计组名称并标 entity_kind=other，不能归到报告公司。'})
            elif not any(norm(name) in norm(subject) for name in [f['company']] if name):
                # A row that actually carries a security code identifies its own
                # company, independently of the issuer on the page header.
                if re.search(r'\b\d{5,6}\b',subject):
                    issues.append({'table':index,'row':r,'column':c,'reason':'peer_row_company_mismatch',
                                   'source_subject':subject,'company':f['company']})
    grouped={}
    for issue in issues:
        column=issue.get('column')
        key=json.dumps({k:v for k,v in issue.items() if k!='column'},ensure_ascii=False,sort_keys=True)
        if key not in grouped:grouped[key]=issue | ({'columns':[]} if column is not None else {})
        if column is not None:grouped[key]['columns'].append(column)
    return list(grouped.values())


def half_rounding_unit(fact):
    meta=fact['source']['normalization'];span=meta.get('numeric_span')
    raw=str(span['text'] if span else fact['raw_value']).replace(',','').replace('，','')
    match=re.search(r'\d+(?:\.(\d+))?',raw)
    if not match:return Decimal(0)
    factor=unit_info(fact['raw_unit'],fact['metric'])[1]
    return (factor or Decimal(1))*Decimal(10)**(-len(match[1] or ''))/2


def signed_presentation_equivalent(left,right,left_item,right_item):
    if Decimal(left['value'])!=-Decimal(right['value']):return False
    def text(item):return (item.get('page_text','')+'\n'+'\n'.join(' '.join(r) for r in item['table']['rows'])).casefold()
    a,b=text(left_item),text(right_item);metric=left['metric']
    # Opposite signs alone are never sufficient. The labels must explicitly
    # declare opposite loss/gain presentation conventions.
    labels=[str(item['table']['rows'][fact['source']['row']-1][0]) for fact,item in ((left,left_item),(right,right_item))]
    if (any(re.search(r'损失.*[负－−-].*号',s) for s in labels) and
        any(re.search(r'收益.*[负－−-].*号',s) for s in labels)):return True
    if re.search(r'(?:gain|loss)',metric):
        charged=lambda s:bool(re.search(r'charg(?:ed|ing)\s*/\s*\(?credit|charging\s+(?:and|or)\s+credit|charging.*crediting',s))
        if charged(a)!=charged(b):return True
    if metric=='contract_liabilities':
        net_presentation=lambda s:bool(re.search(r'contract assets',s) and re.search(r'less:?\s*allowance',s))
        if net_presentation(a)!=net_presentation(b) and ('total liabilities' in a)!=('total liabilities' in b):return True
    return False


def document_conflicts(items):
    """Compare economic identities across tables AND independent table panels.

    Ignore only a proven, erroneous inherited panel dimension in the comparison
    key; keep it in source records and report it separately. Otherwise that very
    error would hide the cashflow/profit conflict this check is intended to find.
    """
    groups={};issues=[]
    for item in items:
        table=item['table'];boundary=panel_boundary(table)
        for f in item['facts']:
            meta=f['source']['normalization'];dims=dict(meta.get('dimensions') or {})
            if dims.get('asset_class')==f['metric']:dims.pop('asset_class')
            if boundary and f['source']['column']>boundary and dims.get('financial_item')==meta.get('row_metric') and meta.get('row_metric')!=f['metric']:
                dims.pop('financial_item',None)
            dimensions=series_dimensions(json.dumps({'entity':{'name':f['company']},'metric':f['metric'],'label':meta.get('label'),'dimensions':dims}))
            attribution=meta.get('attribution') or {'kind':'author'}
            key=json.dumps([norm(f['company']),f['metric'],f['period'],f['scope'],f['currency'],dimensions,
                            meta.get('restatement','original'),meta.get('data_kind','disclosed_actual'),meta.get('scenario') or 'unspecified',attribution],sort_keys=True)
            for old,old_item in groups.get(key,[]):
                old_table=old_item['table']['index']
                if old_table==table['index'] and (not boundary or (old['source']['column']>boundary)==(f['source']['column']>boundary)):continue
                if abs(Decimal(old['value'])-Decimal(f['value'])) <= half_rounding_unit(old)+half_rounding_unit(f):continue
                if signed_presentation_equivalent(old,f,old_item,item):continue
                issue={'reason':'document_value_conflict','company':f['company'],'metric':f['metric'],'period':f['period'],
                       'scope':f['scope'],'left':coordinates(old),'right':coordinates(f),
                       'instruction':'同文档同主体、指标、期间和口径出现不相容数值；修正来源行标签、主体或真实口径。冲突双方都留在剩余工作。'}
                for index in {old_table,table['index']}:issues.append(issue|{'table':index})
            groups.setdefault(key,[]).append((f,item))
    return issues
