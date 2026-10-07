"""A5: deterministic observation-only delivery/source consistency scanner.

The caller supplies the current turn's registry and actually queried source
responses. No retrieval, writes, model feedback, or historical answer keys.
"""
from collections import Counter, defaultdict
from decimal import Decimal as D, localcontext, ROUND_HALF_UP, ROUND_HALF_EVEN
import csv
import io
import json
import re

from .analysis_report import canonical_unit, unit_info
from .analysis_tables import numeric, header_column
from .delivery_quantities import text_quantities, unit, unit_hits, NUM


METRICS = [
    ('gross_margin',r'毛利率|gross.?margin'),
    ('operating_margin',r'经营利润率|营业利润率|operating.?margin'),
    ('net_margin',r'净利率|net.?margin'),
    ('parent_profit',r'归母净利润|归属.{0,10}净利润|net_profit_parent|attributable[ _]?net[ _]?profit'),
    ('net_profit',r'合并净利润|净利润|净利(?!息)|net[ _]?(?:profit|income)'),
    ('revenue',r'营业收入|收入|revenue|net.?sales'),
    ('gross_profit',r'毛利(?!率)|gross[ _]?profit'),
    ('operating_profit',r'营业利润(?!率)|经营利润(?!率)|operating[ _]?profit'),
    ('finance_net',r'净财务收益|净利息收益|财务净收益|net[ _]?finance[ _]?income|finance_income_net'),
    ('profit_before_tax',r'税前利润|profit[ _]?before[ _]?tax'),
    ('cfo',r'经营活动净现金流|经营活动现金流净额|operating[ _]?cash[ _]?flow|net cash from operating activities|\bCFO\b'),
    ('operations',r'经营产生现金|cash[ _]?generated[ _]?from[ _]?operations'),
    ('eps',r'每股收益|(?<![A-Za-z])EPS(?![A-Za-z])|basic_earnings_per_share|earnings_per_share'),
    ('pv_terminal',r'终值现值|PV[ _(]*(?:of[ _]?)?terminal|terminal[ _]?(?:value[ _]?)?PV'),
    ('pv_explicit',r'显性.{0,6}现值|明确期.{0,5}现值|(?:PV[ _]?explicit|explicit[ _]?PV)|DCF[ _]?(?:of[ _]?)?FCF|DCF\s*\(\d'),
    ('terminal_value',r'未折现终值|终值(?!现值|占比)|terminal[ _]?value'),
    ('equity_value',r'股权价值|equity[ _]?value|equity_RMB'),
    ('ev',r'企业价值|(?<![A-Za-z])EV(?![A-Za-z])|enterprise[ _]?value'),
    ('share_price',r'每股价值|折合每股|每股约|目标价|target[ _]?price|HKD[ _]?per[ _]?share|value[ /_]?(?:per[ _]?)?share'),
    ('fcf',r'unleveraged[ _]?FCF|(?<![A-Za-z])FCF(?![A-Za-z])|自由现金流'),
    ('wacc',r'WACC'),('g',r'永续增长率|增长率|terminal[ _]?growth|(?<![A-Za-z])g(?![A-Za-z])'),
    ('net_cash',r'净现金|net[ _]?cash'),('shares',r'股数|股本|shares'),
]


def metric(text):
    for name,pattern in METRICS:
        if re.search(pattern,str(text),re.I):return name
    return None


def period(text):
    text=str(text)
    m=re.search(r'(?:FY)?(20\d{2})(?:[- /]?(H[12]|Q[1-4]))?[EA]?',text,re.I)
    if m:return m[1]+(m[2].upper() if m[2] else '')
    m=re.search(r'FY(\d{2})[EA]?',text,re.I)
    return '20'+m[1] if m else None


def scenario(text):
    old=bool(re.search(r'旧|原假设|原参数|基准|\bold\b|original|\bbase\b',str(text),re.I))
    new=bool(re.search(r'新|更新|\bnew\b|updated',str(text),re.I))
    if old!=new:return 'old' if old else 'new'
    return None


def axis_values(text):
    axes={}
    for k,pattern in [('wacc',r'WACC\s*[=:：]?\s*([\d.]+)(%?)'),('g',r'(?:\bg\b|永续增长率|terminal growth)\s*[=:：]?\s*([\d.]+)(%?)')]:
        m=re.search(pattern,str(text),re.I)
        if m:axes[k]=str(D(m[1])/(100 if m[2] else 1))
    return axes


def quantity(value,units,where,*,label='',when=None,axes=None,origin='table',**extra):
    if value is None or not numeric(value) or units is None:return None
    return {'value':str(value),'unit':list(units),'where':where,'label':label,'metric':metric(label),
            'period':period(when) if when else None,'axes':axes or {},'origin':origin,**extra}


def column_unit(column):
    if not column.get('unit'):
        if re.search(r'(?:RMB|CNY)[ _]?100m',column.get('label',''),re.I):return ('money','CNY','100000000')
        units=list(dict.fromkeys(h[2] for h in unit_hits(column.get('label',''),metric=column.get('label',''))))
        return units[0] if len(units)==1 else None
    u,c=canonical_unit(column['unit']);dimension,scale=unit_info(u)
    return (dimension,column.get('currency') or c or '',str(scale))


def table_quantities(tables):
    result=[]
    indexed_periods={name.rsplit('__',1)[0]:[r.get('value') for r in t['rows']]
                     for name,t in tables.items() if re.search(r'__(years?|periods?)$',name,re.I) and 'index' in t['columns']}
    for name,tab in tables.items():
        columns=tab['columns'];keys=list(columns)
        for i,row in enumerate(tab['rows']):
            texts={k:str(v) for k,v in row.items() if v is not None and (not numeric(v) or re.search('year|period|date|财年|年度|期间|年份',k,re.I)) and k not in ('source','来源')}
            row_label=' '.join(v for k,v in texts.items() if not re.search('unit|单位|source|来源',k,re.I))
            explicit_metric=next((str(row[k]) for k in row if re.fullmatch(r'metric|item|指标|项目|财年/项目',k,re.I)),None)
            when=next((row[k] for k in row if re.search('year|period|^FY$|财年|年度|期间|年份',k,re.I)),None) or period(row_label)
            sibling_periods=indexed_periods.get(name.rsplit('__',1)[0],[])
            if when is None and 'index' in row and len(sibling_periods)==len(tab['rows']):when=sibling_periods[i]
            first_label=columns[keys[0]].get('label',keys[0]) if keys else ''
            rate_axis='wacc' if re.search('WACC',first_label,re.I) else 'g' if re.search('永续增长|terminal.?growth|^g$',first_label,re.I) else None
            for key,col in columns.items():
                if re.fullmatch(r'(?:physical_|source_)?page|页码|页|row_index|column_index',key,re.I):continue
                value=row.get(key);u=column_unit({**col,**tab.get('cell_units',[{}]*len(tab['rows']))[i].get(key,{})})
                if not numeric(value) or u is None:continue
                column_label=col.get('label',key)
                label=column_label if metric(column_label) else explicit_metric or (row_label if metric(row_label) else name)
                row_units=unit(label,metric=label)
                if row_units and row_units[0]!='money' and u[0]=='money':u=row_units
                axes=axis_values(row_label+' '+key)
                if rate_axis and numeric(row.get(keys[0])) and key!=keys[0]:
                    axes[rate_axis]=str(D(str(row[keys[0]])))
                elif rate_axis and key!=keys[0] and re.fullmatch(r'[\d.]+%',str(row.get(keys[0],''))):
                    axes[rate_axis]=str(D(str(row[keys[0]])[:-1])/100)
                q=quantity(value,u,f'{name}.{i}.{key}',label=label,when=when or key,axes=axes,
                           table=name,row=i,column=key,artifact=tab.get('artifact'),scenario=scenario(key) or scenario(row_label) or scenario(name))
                if q:
                    if u[0]=='per_share' and q['metric']!='eps':q['metric']='share_price'
                    if re.search('贡献|差额|差异|变动|变化|change|delta|contribution',label+' '+key+' '+row_label,re.I):
                        q['role']='change'
                        if u[0]=='per_share':q['metric']='share_price_change'
                    if axes and u[0]=='per_share':q['metric']='sensitivity'
                    if re.search('变动|变化|change|delta|差额',key,re.I):q['role']='change'
                    result.append(q)
    return result


def source_quantities(responses):
    result=[]
    def plain(text,where,default=None):
        years=[]
        number=r'\(?[-+]?(?:\d[\d,]*(?:\.\d+)?|\.\d+)\)?%?'
        for ln,line in enumerate(text.splitlines(),1):
            yr=re.findall(r'\b(?:FY)?20\d{2}[EA]?\b|\bFY\d{2}[EA]?\b',line)
            if len(yr)>=2:years=yr;continue
            match=re.fullmatch(r'(.*?)\s+('+number+r'(?:\s+'+number+r')*)\s*',line.strip())
            if not match:
                if not NUM.search(re.sub(r'Figure\s+\d+|YE\s+\d+','',line)):
                    hits=unit_hits(line)
                    monetary=[h[2] for h in hits if h[2][0]=='money']
                    if monetary:default=monetary[-1]
                continue
            label=match[1];name=metric(label)
            if not name:continue
            values=re.findall(number,match[2]);units=unit(label,metric=label) or default
            if units is None:continue
            if re.search(r'EV\s*/|P/E|P/B',label,re.I):units=('multiple','','1')
            if name=='shares':units=('shares','','1000000' if re.search(r'\(m\)|million',label,re.I) else '1')
            if name=='share_price' and units[0]=='money':units=('per_share',units[1],units[2])
            for j,raw in enumerate(values):
                u=('ratio','','.01') if raw.endswith('%') else units
                raw=raw.rstrip('%').replace(',','');raw='-'+raw[1:-1] if raw.startswith('(') else raw
                q=quantity(raw,u,where+f':{ln}:{j}',label=label,when=years[j] if len(values)==len(years) else None,origin='source')
                if q:
                    if u[0]=='per_share' and q['metric']!='eps':q['metric']='share_price'
                    result.append(q)
    def walk(obj,where,scope=None):
        if isinstance(obj,list):
            for i,x in enumerate(obj):walk(x,where+f'[{i}]',scope)
        elif isinstance(obj,dict):
            if obj.get('operation') and 'value' in obj and obj.get('unit'):
                q=quantity(obj['value'],unit(obj['unit']),where,label=obj['operation'],origin='calculation')
                if q:result.append(q)
            if obj.get('metric') and 'value' in obj and obj.get('currency'):
                cur=obj['currency'];units=unit(cur,metric=obj['metric'])
                if cur in ('percent','percentage_points'):units=('ratio','', '.01') if cur=='percent' else ('percentage_points','','1')
                if re.fullmatch('[A-Z]{3}/share',cur):units=('per_share',cur[:3],'1')
                q=quantity(obj['value'],units,where,label=obj['metric'],when=obj.get('period'),origin='source',
                           record_id=obj.get('record_id') or obj.get('fact_id'),scope=obj.get('scope'),data_kind=obj.get('data_kind'))
                if q:result.append(q)
            rows=obj.get('rows')
            if isinstance(rows,list) and rows and isinstance(rows[0],list):
                flattened='\n'.join('  '.join(str(v) for v in row if v is not None and str(v).strip()) for row in rows)
                plain(flattened,where+'.rows',unit(str(obj.get('unit') or '')))
                headers={};default=unit(str(obj.get('unit') or ''),metric='')
                for i,row in enumerate(rows):
                    if not row:continue
                    for j,v in enumerate(row):
                        if re.fullmatch(r'\s*(?:FY)?(?:20)?\d{2}(?:[EA]|H[12])?\s*',str(v)) and period(v):headers[j]=str(v)
                    label=str(row[0]);units=unit(label,metric=label) or default
                    for j,v in enumerate(row[1:],1):
                        raw=str(v).replace(',','').strip();raw='-'+raw[1:-1] if raw.startswith('(') and raw.endswith(')') else raw
                        q=quantity(raw,units,where+f'.rows[{i}][{j}]',label=label,when=headers.get(j),origin='source')
                        if q:result.append(q)
            for k,v in obj.items():
                if k in ('value','rows','source_ref','segments','cell_sources'):continue
                if k=='source_json' and isinstance(v,str):walk(json.loads(v),where+'.source_json')
                elif isinstance(v,(dict,list)):walk(v,where+'.'+k)
                elif isinstance(v,str) and k in ('text','content','markdown','quote','preview'):
                    plain(v,where+'.'+k)
                    # Source tables rendered as fixed-width text: use header years
                    # and numeric column order rather than assigning all cells the first year.
                    years=[]
                    for ln,line in enumerate(v.splitlines(),1):
                        yr=re.findall(r'\b(?:FY)?20\d{2}[EA]?\b|\bFY\d{2}[EA]?\b',line)
                        if len(yr)>=2:years=yr
                        label=re.split(r'\s{2,}',line.strip())[0]
                        hits=list(NUM.finditer(line[len(line)-len(line.lstrip())+len(label):]))
                        units=unit(label,metric=label)
                        if units and metric(label) and years and len(hits)==len(years):
                            for n,y in zip(hits,years):
                                q=quantity(n.group(),units,where+f'.{k}:{ln}',label=label,when=y,origin='source')
                                if q:result.append(q)
                    for q in text_quantities(v,where+'.'+k,source=True)[0]:
                        q.update(origin='source',metric=metric(q.get('row_label') or q['context']),period=None,axes={})
                        result.append(q)
    for i,r in enumerate(responses):walk(r,f'source:{i}')
    return result


def _enrich_text(q,lines):
    header=q.get('table_header');row=q.get('row_label','');ci=q.get('table_column')
    context=q['context'];column=header[ci] if header and ci is not None and 0<=ci<len(header) else ''
    q['metric']=metric(column) or metric(row)
    q['period']=period(row) or period(column)
    if re.search(r'(?:20|FY)\d{2}E?[-–至](?:20|FY)?\d{2}',row):q['period']=None
    if q['unit'][0]=='per_share' and q['metric']!='eps':q['metric']='share_price'
    q['axes']=axis_values(row+' '+column)
    if header and re.search(r'WACC.*(?:g|增长)|(?:g|增长).*WACC',header[0],re.I):
        first='wacc' if re.match(r'\s*WACC',header[0],re.I) else 'g'
        second='g' if first=='wacc' else 'wacc'
        if ci:
            for axis,text in [(first,row),(second,column)]:
                m=re.search(r'([\d.]+)\s*(%)?',text)
                if m:q['axes'][axis]=str(D(m[1])/(100 if m[2] else 1))
            if q['unit'][0]=='per_share':q['metric']='sensitivity'
        else:q.update(metric=first,role='grid_axis',axes={})
    if header and re.search('变化|变动|差额|同比|贡献',column):
        q['role']='change'
        if q['unit'][0]=='percentage_points' and q['metric']:q['metric']+='_change'
        if q['unit'][0]=='per_share':q['metric']='share_price_change'
    if not header:
        # For prose, choose the nearest preceding compatible metric phrase.
        line=lines[q['line']-1];start=q['normalizedColumn']-1
        preceding=q.get('prefix',line[:start])
        preceding=re.split(r'[。；;]|(?<!\d)，',preceding)[-1]
        found=[]
        for name,pattern in METRICS:
            for m in re.finditer(pattern,preceding,re.I):found.append((m.end(),name))
        if found:q['metric']=max(found,key=lambda x:x[0])[1]
        if q['unit'][:2]==['per_share','HKD']:q['metric']='share_price'
        if q['unit'][0]=='money' and re.search('差异|差额|差约|低约|高约',preceding[-20:]) and re.search('DCF|EV|股权|估值',line,re.I):q['metric']='valuation_gap'
        if q['unit'][0]=='percentage_points' and q['metric'] in ('gross_margin','operating_margin','net_margin'):q['metric']+='_change'
        if re.search(r'下降|减少|回落|下滑|下降约|减少约',preceding[-10:]) and not q['value'].startswith('-'):
            q['surface_value']=q['value'];q['value']='-'+q['value'];q['sign_basis']='explicit_decline_verb'
        if q['metric']=='valuation_gap':
            q['surface_value']=q['value'];q['value']=str(abs(D(q['value'])));q['comparison_basis']='absolute_gap'
        if re.search('贡献|差额|差异|变化|变动|累计下降',preceding[-20:]) and q['unit'][0]=='per_share':q.update(metric='share_price_change',role='change')
        if q['metric'] in ('wacc','g') and re.search('敏感性|网格|sensitivity',line,re.I):q['role']='grid_axis'
    q['scenario']=scenario(column) or scenario(row) or scenario(q.get('section',''))
    q['origin']='delivery';return q


def _base(q):return D(q['value'].replace(',','').replace('−','-').replace('–','-'))*D(q['unit'][2])


def _display_match(q,source,factor=D(1)):
    target=D(q['value'].replace(',','').replace('−','-').replace('–','-'))
    value=_base(source)*factor/D(q['unit'][2])
    if target==value:return 'exact'
    quantum=D(1).scaleb(target.as_tuple().exponent)
    return 'rounding_consistent' if any(value.quantize(quantum,rounding=mode)==target for mode in (ROUND_HALF_UP,ROUND_HALF_EVEN)) else None


def _compatible(a,b):
    return a['unit'][:2]==b['unit'][:2] and (not a.get('scenario') or not b.get('scenario') or a['scenario']==b['scenario'])


def derived_quantities(registry,sources):
    result=[]
    for q in registry:
        for axis,value in q.get('axes',{}).items():
            result.append(quantity(value,('ratio','','1'),q['where']+':axis:'+axis,metric=axis,role='grid_axis',origin='derived'))
    # Differences of same metric with explicit periods; used only for change claims.
    groups=defaultdict(dict)
    for q in registry:
        if q.get('metric') in ('gross_margin','operating_margin','net_margin') and q['unit'][0]=='ratio' and q.get('period') and not q.get('role'):
            groups[q['metric']][q['period']]=q
    for name,items in groups.items():
        if len(items)<2:continue
        periods=sorted(items);old,new=items[periods[-2]],items[periods[-1]]
        result.append(quantity(str((_base(new)-_base(old))*100),('percentage_points','','1'),'derived:'+new['where']+'-'+old['where'],label='',origin='derived',metric=name+'_change',inputs=[new,old]))
    for calc in registry:
        if calc.get('metric') not in ('ev','equity_value') or calc.get('role'):continue
        for stated in sources:
            if stated.get('metric')==calc['metric'] and _compatible(calc,stated):
                result.append(quantity(str(abs(_base(calc)-_base(stated))),('money',calc['unit'][1],'1'),
                                       'derived:'+calc['where']+'-'+stated['where'],label='',origin='derived',metric='valuation_gap',inputs=[calc,stated]))
    return [q for q in result if q]


def classify(q,pool):
    candidates=[s for s in pool if _compatible(q,s) and s.get('artifact')!=q.get('artifact',q.get('file'))]
    semantic=[s for s in candidates if q.get('metric') and s.get('metric')==q['metric']]
    if q.get('period'):
        dated=[s for s in semantic if s.get('period')==q['period']]
        semantic=dated or [s for s in semantic if not s.get('period')]
    if q.get('axes'):
        semantic=[s for s in semantic if all(D(s.get('axes',{}).get(k,'NaN'))==D(v) for k,v in q['axes'].items())]
    if q.get('role')=='change':semantic=[s for s in semantic if s.get('role')=='change' or s.get('origin')=='derived']
    if q.get('role')=='grid_axis':semantic=[s for s in semantic if s.get('role')=='grid_axis']
    aligned=bool(semantic)
    # Source forecasts can expose a registry/CSV which repeats the same wrong year.
    primary=[s for s in semantic if s.get('origin')=='source' and s.get('period') and q.get('metric') in ('revenue','net_profit','parent_profit','eps')]
    compare=primary or semantic or candidates
    exact=[];rounded=[]
    for s in compare:
        status=_display_match(q,s)
        if status=='exact':exact.append(s)
        elif status=='rounding_consistent':rounded.append(s)
    selected=exact or rounded
    base={'claim':q,'aligned':aligned,'match_scope':'semantic_period_or_coordinates' if aligned else 'numeric_only',
          'expected':[],'evidence':selected,'issue':False}
    if selected:return {**base,'classification':'exact' if exact else 'rounding_consistent'}
    powers=[]
    for s in compare:
        if not _base(q) or not _base(s) or _base(q)*_base(s)<0:continue
        exponent=(_base(q)/_base(s)).adjusted()
        for power in (exponent,exponent+1):
            if power and _display_match(q,s,D(10)**power):powers.append({'power':power,'source':s})
    if aligned and powers:return {**base,'classification':'order_of_magnitude','issue':True,'expected':powers,'reason':'同语义/期间数值仅在十进制缩放后吻合'}
    elsewhere=[s for s in candidates if s not in compare and _display_match(q,s)]
    if aligned and elsewhere:return {**base,'classification':'wrong_cell','issue':True,'expected':compare,'elsewhere':elsewhere,'reason':'已对齐行列不符，值可匹配其他期间或坐标单元格'}
    precision=D(q['value'].replace(',','')).as_tuple().exponent
    unique={((_base(s)/D(q['unit'][2])).quantize(D(1).scaleb(precision),rounding=ROUND_HALF_UP),tuple(s['unit'][:2])) for s in compare}
    return {**base,'classification':'unmatched','issue':aligned and len(unique)==1,'expected':compare if aligned else [],
            'reason':'对齐值不符' if aligned and len(unique)==1 else '同语义候选不唯一' if aligned else '本轮数值表和查询返回中无可对应值；不等于财务错误'}


def scan_delivery(answer='',tables=None,source_records=(),attachments=()):
    """Return JSON-serializable checks. Attachments: {name, text, format: md|csv}."""
    with localcontext() as ctx:
        ctx.prec=80
        registry=table_quantities(tables or {});sources=source_quantities(source_records)
        pool=registry+sources+derived_quantities(registry,sources)
        claims=[];omitted=[]
        documents=[{'name':'answer.md','text':answer,'format':'md'},*attachments]
        for doc in documents:
            name=doc['name'];text=doc['text']
            if doc.get('format')=='csv':
                reader=csv.DictReader(io.StringIO(text));rows=list(reader);headers=reader.fieldnames or []
                columns={h:header_column(h) for h in headers};cell_units=[]
                unit_key=next((h for h in headers if re.match('^(unit|单位)',h,re.I)),None)
                for row in rows:
                    units=unit(row.get(unit_key,'')) if unit_key else None
                    metadata={}
                    if units:
                        dim,cur,scale=units
                        canonical=next((u for u in ('元','千元','万元','百万元','亿元','十亿元','股','百万股','亿股','元/股','ratio','%','个百分点','倍') if unit_info(u)==(dim,D(scale))),None)
                        if canonical:
                            for h in headers:
                                if numeric(row.get(h)) and not period(h) and not re.search('year|period|财年|年度|期间',h,re.I):metadata[h]={'unit':canonical,'currency':cur or None}
                    cell_units.append(metadata)
                for q in table_quantities({name:{'columns':columns,'rows':rows,'cell_units':cell_units}}):
                    q.update(file=name,artifact=doc.get('artifact',name),line=q['row']+2,origin='delivery');claims.append(q)
            else:
                found,missing=text_quantities(text,name)
                for q in found:q.update(file=name);claims.append(_enrich_text(q,text.splitlines()))
                omitted.extend({'file':name,**x} for x in missing)
        checks=[classify(q,pool) for q in claims]
        return {'schema_version':1,'mode':'observation_only','feedback_enabled':False,
                'counts':dict(Counter(c['classification'] for c in checks)),'issue_count':sum(c['issue'] for c in checks),
                'reference_counts':{'registry':len(registry),'queried_sources':len(sources),'derived':len(pool)-len(registry)-len(sources)},
                'checks':checks,'unparsed_or_unit_unknown':omitted,
                'limitations':['数值匹配不能证明因果、利息方向或完整金融解释正确。','numeric_only 表示语义未对齐，不能作为正确率。',
                               '未匹配且无法唯一对齐的项是未知，不作为确定错误。','仅检查调用方传入的本轮来源和产物；不访问其他项目或评审答案。']}
