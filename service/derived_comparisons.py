"""Source-derived comparison columns; amounts survive a local comparison gap."""
import copy
import json
import re
from collections import defaultdict
from decimal import Decimal
from .normalization import decimal_value, unit_info
from .standard_metrics import workpaper_concepts

KINDS={'growth_rate':'_growth_rate','percentage_points':'_change_pp','change_amount':'_change_amount'}
CHANGE=re.compile(r'同比|比上(?:年|期)|较上(?:年|期)|同期增减|变动|增减|增长|\b(?:change|growth|yoy)\b',re.I)


def decoded(value):
    return json.loads(value) if isinstance(value,str) else value or []


def source_columns(columns,width):
    # Leave malformed declarations to materialize's existing mapping diagnostics.
    return [c for c in columns if isinstance(c,dict) and str(c.get('column','')).isdigit()
            and 1<=int(c['column'])<=width]


def column_heading(table,column,first_row):
    headers=table['rows'][:first_row-1]
    def at(c):return ' '.join(str(r[c-1]) for r in headers if len(r)>=c and str(r[c-1]).strip())
    direct=at(column)
    if direct:return direct
    # Sparse PDF extraction can put a merged heading in the next empty cell.
    # Only that empty physical data column can lend its heading to this value.
    for c in (column+1,column+2):
        if any(len(r)>=c and str(r[c-1]).strip() for r in table['rows'][first_row-1:]):break
        if at(c):return at(c)
    return ''


def comparison_kind(header,raw,definition=None):
    kind=(definition or {}).get('semantic_type')
    text=re.sub(r'\s+','',header)
    if CHANGE.search(text):
        if re.search(r'百分点|percentage.?points?',header+' '+str(raw),re.I):return 'percentage_points'
        if re.search(r'变动额|增减额|增长额|change.?amount',text,re.I):return 'change_amount'
        if re.search(r'%|％|比例|增长率|增减率|变动率|percent',text,re.I):return 'growth_rate'
    return kind if kind in KINDS else None


def period_pair(columns,attrs,schema,table,first_row):
    groups=defaultdict(list)
    for c in columns:
        column=int(c['column']);header=column_heading(table,column,first_row)
        if c.get('semantic_type') in KINDS or CHANGE.search(header):continue
        actual,expected=c.get('metric',attrs.get('metric')),attrs.get('metric')
        if actual!=expected and not set(workpaper_concepts(actual)) & set(workpaper_concepts(expected)):continue
        period=c.get('period')
        if not period or period=='unknown':continue
        groups[str(period)].append(c)
    selected=[]
    for candidates in groups.values():
        adjusted=[c for c in candidates if c.get('restatement')=='restated']
        candidates=adjusted or candidates
        if len(candidates)!=1:return None
        selected.append(candidates[0])
    selected.sort(key=lambda c:str(c.get('end') or c['period']),reverse=True)
    if len(selected)<2:return None
    current,previous=selected[:2]
    def window(c):
        p=str(c['period'])
        return 'point' if re.fullmatch(r'\d{4}-\d{2}-\d{2}',p) else p[4:]
    if window(current)!=window(previous):return None
    # Different business slices or scopes are not comparative periods.
    for key in ('company','scope','dimensions_json'):
        if current.get(key,attrs.get(key,schema.get(key)))!=previous.get(key,attrs.get(key,schema.get(key))):return None
    units=[unit_info(c.get('unit') or attrs.get('unit') or schema.get('unit',''))[2] for c in (current,previous)]
    if units[0]!=units[1]:return None
    return current,previous


def literal(raw):
    value=decimal_value(raw)
    if value is not None:return value,None
    match=re.fullmatch(r'\s*(增加|减少|上升|下降)\s*([+\-−]?\d[\d,，]*(?:\.\d+)?)\s*(?:个?百分点|[%％])\s*',str(raw))
    if not match:return None,None
    value=decimal_value(match[2]);negative=match[1] in {'减少','下降'}
    return (-abs(value) if negative else value),{'text':match[2],'start':match.start(2),'end':match.end(2),
                                                'polarity':'negative' if negative else 'as_written'}


def complete_comparison_columns(table,schema,attrs,row,first_row):
    """Only add positively typed missing comparisons; never rewrite mapped cells."""
    attrs.pop('derived_comparisons_json',None)  # Always rederive this program-owned decision.
    columns=decoded(attrs.get('columns_json')) or decoded(schema.get('columns_json'))
    valid=source_columns(columns,len(table['rows'][row-1]))
    pair=period_pair(valid,attrs,schema,table,first_row)
    if not pair:return
    current,previous=pair
    # A source-backed pair must actually contain both values on this row.
    if any(literal(table['rows'][row-1][int(c['column'])-1])[0] is None for c in pair):return
    declared={int(c['column']) for c in valid}
    unresolved={x['column'] for x in decoded(attrs.get('unresolved_cells_json'))}
    additions=[];deferred=[]
    for column,raw in enumerate(table['rows'][row-1],1):
        if column in declared|unresolved or column==int(schema.get('label_column',1)):continue
        header=column_heading(table,column,first_row)
        if not CHANGE.search(re.sub(r'\s+','',header)):continue
        if not re.search(r'\d',str(raw)):continue
        kind=comparison_kind(header,raw);value,span=literal(raw)
        evidence={'current_column':int(current['column']),'previous_column':int(previous['column']),'header':header}
        if not kind or value is None:
            deferred.append({'column':column,'detail':'可由两期金额推导的派生列；原文列类型或数值表达未确定，保留原格，未物化为事实',**evidence})
            continue
        definition={**copy.deepcopy(current),'column':column,'metric':attrs['metric']+KINDS[kind],
                    'label':str(attrs.get('label') or table['rows'][row-1][0])+' '+header,
                    'semantic_type':kind,'derived_comparison':evidence}
        definition.pop('numeric_span',None)
        if span:definition['numeric_span']=span
        if kind!='change_amount':
            definition.update(unit='个百分点' if kind=='percentage_points' else '%',
                              currency='percentage_points' if kind=='percentage_points' else 'percent')
        additions.append(definition)
    if additions:attrs['columns_json']=json.dumps([*columns,*additions],ensure_ascii=False)
    if deferred:attrs['derived_comparisons_json']=json.dumps(deferred,ensure_ascii=False)


def rounding_error(fact):
    meta=fact['source']['normalization'];span=meta.get('numeric_span')
    text=span['text'] if span else fact['raw_value']
    match=re.search(r'\d[\d,，]*(?:\.(\d+))?',str(text))
    places=len(match[1]) if match and match[1] else 0
    return Decimal('0.5')*Decimal(10)**(-places)*Decimal(meta['scale'])


def comparison_checks(table,schema,rows,facts):
    """Compare reported values at their disclosure precision; preserve discrepancies."""
    issues=[]
    if not rows:return issues
    first=min(x['row'] for x in rows)
    bycell=defaultdict(list)
    for f in facts:bycell[(f['source']['row'],f['source']['column'])].append(f)
    for mapped in rows:
        r,attrs=mapped['row'],mapped['attributes']
        columns=source_columns(decoded(attrs.get('columns_json')) or decoded(schema.get('columns_json')),len(table['rows'][r-1]))
        pair=period_pair(columns,attrs,schema,table,first)
        for column in columns:
            c=int(column['column']);raw=table['rows'][r-1][c-1];header=column_heading(table,c,first)
            kind=comparison_kind(header,raw,column)
            if not kind:continue
            targets=bycell.get((r,c),[])
            if not targets:continue
            check={'semantic_type':kind,'source_header':header,'status':'unverified'}
            operands=[bycell.get((r,int(x['column'])),[]) for x in pair] if pair else []
            if len(operands)!=2 or any(len(x)!=1 for x in operands):
                check['reason']='缺少唯一的两期已映射同口径金额'
            else:
                current,previous=(x[0] for x in operands)
                a,b=Decimal(current['value']),Decimal(previous['value'])
                ea,eb=rounding_error(current),rounding_error(previous)
                check['operands']=[{'cell':f['source']['cell'],'period':f['period'],'value':f['value']} for f in (current,previous)]
                if current['currency']!=previous['currency']:
                    check['reason']='两期单位或币种不同'
                elif kind=='percentage_points' and current['currency']!='percent':
                    check['reason']='百分点比较需要两期比例输入'
                elif kind=='growth_rate' and b-eb<=0:
                    check['reason']='比较基期非正或披露精度范围包含零，未猜测增长率口径'
                else:
                    if kind=='growth_rate':
                        expected=(a-b)/b*100
                        bounds=[(x/y-1)*100 for x in (a-ea,a+ea) for y in (b-eb,b+eb)]
                    else:
                        expected=a-b;bounds=[a-b-ea-eb,a-b+ea+eb]
                    lo,hi=min(bounds),max(bounds)
                    check.update(expected=str(expected),expected_interval=[str(lo),str(hi)])
                    for target in targets:
                        actual=Decimal(target['value']);et=rounding_error(target)
                        unit_ok=target['currency']==({'growth_rate':'percent','percentage_points':'percentage_points'}.get(kind,current['currency']))
                        result={**check,'reported':str(actual),'status':'consistent' if unit_ok and actual+et>=lo and actual-et<=hi else 'mismatch'}
                        target['source']['normalization']['derived_comparison_check']=result
                        if result['status']=='mismatch':
                            target['source']['normalization'].setdefault('review_warnings',[]).append('derived_comparison_mismatch')
                            issues.append({'table':table['index'],'row':r,'column':c,'reason':'derived_comparison_mismatch','severity':'review','evidence':result})
                    continue
            for target in targets:target['source']['normalization']['derived_comparison_check']=check
            issues.append({'table':table['index'],'row':r,'column':c,'reason':'derived_comparison_unverified','severity':'review','evidence':check})
    return issues
