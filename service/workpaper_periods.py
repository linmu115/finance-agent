"""Period workpaper and the shared retrieval adapter used by analyst kinds."""
import json
import re

from .analysis_report import record_quantity
from .financial_workpapers import ALIASES, Statement, cell, col, dimensions_ok, load_facts, meta, table
from .period_algebra import change, derive_period_series, observation, quarter_window
from .workpaper_annual import Disclosure, quarter, row_kind
from .workpaper_period_selection import canonical_period, normalize_periods, normalize_period_records

FLOW_METRICS=('revenue','net_profit','parent_profit','deducted_profit','cfo')


def column_context(t, row, column):
    """Preserve original multirow column headings, including adjustment labels."""
    parts=[]
    for cells in t['rows'][:max(row-1,0)]:
        value=str(cells[column-1]) if column and column<=len(cells) else ''
        if re.search(r'20\d{2}|本期|上期|本年|上年|季度|累计|年初|调整[前后]|重述[前后]',value) and not re.fullmatch(r'[\d, .%-]+',value):
            parts.append(value)
    return ' / '.join(dict.fromkeys(parts))


def period_inputs(st, disclosure=None, additional_facts=()):
    """Public adapter: Statement + source tables -> period_algebra observations.

    Reads the current report's quarterly table even if normalization missed it.
    The caller supplies any additional *same-project* facts; this never discovers
    unrelated projects or writes a database. Return (inputs, unknown_rows).
    """
    d=disclosure or Disclosure(st);tabs={t['table_id']:t for t in d.tabs};items=[];unknown=[]
    facts=[*st.facts,*additional_facts]
    actual_scope=next(r['scope'] for r in st.facts if r['metric'] in ALIASES['revenue'])
    for r in facts:
        if r['company']!=st.company or r['scope']!=actual_scope or not dimensions_ok(r):continue
        metric=next((k for k in FLOW_METRICS if r['metric'] in ALIASES[k]),None)
        if not metric:continue
        n=meta(r);ref=r['source_ref'];t=tabs.get(ref.get('table_id'))
        header=column_context(t,ref.get('row',1),ref.get('column')) if t else n.get('period_label','')
        # Percentage change columns are never amounts, even if a metric alias matches.
        if r['currency']!=st.currency:continue
        version=n.get('restatement','unspecified')
        if re.search('调整后|重述后',header):version='restated'
        elif re.search('调整前|重述前',header):version='original'
        q=record_quantity(r);q['source']['source_ref']={**ref,'column_label':header,'report':d.document.get('original_name') if r['document_id']==d.doc else None}
        items.append(observation(metric,q,entity=r['company'],scope=r['scope'],start=n.get('period_start'),end=n.get('period_end'),
            period=r['period'],label=header or n.get('period_label',''),document_id=r['document_id'],restatement=version,
            basis_id=None))
    for t in d.tabs:
        if not t['rows'] or not d.applies(t):continue
        cols={quarter(h):(c,h) for c,h in enumerate(t['rows'][0]) if quarter(h)}
        if len(cols)!=4:continue
        for i,row in enumerate(t['rows'][1:],1):
            metric=row_kind(row[0])
            if metric is None:
                unknown.append({'label':row[0],'reason':'季度指标未识别','source':{'document_id':d.doc,'page':t['page'],'table_id':t['table_id'],'row':i+1,'raw_row':row}});continue
            for number,(c,header) in cols.items():
                start,end=quarter_window(int(d.year),int(number));q=d.quantity(t,i,c,header)
                mapped=[x for x in items if x['quantity']['source'].get('source_ref',{}).get('table_id')==t['table_id'] and x['quantity']['source'].get('source_ref',{}).get('row')==i+1 and x['quantity']['source'].get('source_ref',{}).get('column')==c+1]
                version=mapped[0]['restatement'] if mapped else 'unspecified'
                items.append(observation(metric,q,entity=st.company,scope=actual_scope,start=start,end=end,document_id=d.doc,
                    restatement=version,basis_id=None))
    adjusted=[x for x in items if x['document_id']==d.doc and x['restatement']=='restated']
    if adjusted:
        same_year=any(x['end'] and x['end'][:4]==d.year for x in adjusted)
        for x in items:
            if x['document_id']!=d.doc:continue
            # Current-year amounts and last-year adjusted comparatives share
            # the current report's basis. An explicitly mixed current-year
            # quarter/YTD pair cannot acquire that permission automatically.
            current=x['end'] and x['end'][:4]==d.year and not same_year
            x['basis_id']=d.doc+(':current' if x['restatement']=='restated' or current else ':before')
    return items,[*unknown,*d.unknown]


def load_period_series(service, project, document_id=None, company=None, scope='consolidated', periods=None):
    """N4 service entry point. Returns typed cells without publishing a delivery.

    result['quarters'] / ['cumulatives'] contain metric, period, dates, scope,
    currency, restatement and quantity. Missing quarters are absent. See design
    handoff for the pure derive_period_series API and its input schema.
    """
    st=Statement(service,project,load_facts(service,project,document_id,company),scope,document_id=document_id,company=company)
    d=Disclosure(st)
    # Only this project and the already selected issuer; current report wins.
    others=normalize_period_records([r for r in load_facts(service,project,company=st.company) if r['document_id']!=d.doc])
    inputs,unknown=period_inputs(st,d,others)
    result=derive_period_series(inputs,d.doc)
    available={canonical_period(x.get('period',x['end']),x['start'],x['end']):(x['start'],x['end'])
               for x in [*inputs,*result['quarters'],*result['cumulatives']] if x.get('kind') in ('quarter','ytd','annual')}
    selected=normalize_periods(periods,available,available)
    years={int(p[:4]) for p in selected}
    for key in ('quarters','cumulatives','reconciliations','missing'):
        result[key]=[x for x in result[key] if int(x['period'][:4]) in years]
    result.update(company=st.company,currency=st.currency,document_id=d.doc,periods=selected,unknown_rows=unknown,records=[*st.facts,*others],inputs=inputs)
    return result


def period_analysis(service, project, document_id=None, company=None, scope='consolidated', periods=None, focus=None):
    result=load_period_series(service,project,document_id,company,scope,periods)
    tabs={};currency=result['currency'];findings=[];changes=[]
    for name in ('quarters','cumulatives'):
        rows=[]
        for i,x in enumerate(result[name]):
            q=x['quantity'];reason=q['source'].get('missing_reason')
            rows.append({'key':str(i),'metric':x['metric'],'period':x['period'],'start':x['start'],'end':x['end'],
                         'amount':q,'basis':x['restatement'],'origin':'推导' if q['source'].get('data_kind')=='calculation' else '披露','missing':reason})
        tabs[name]=table({**{k:col(v) for k,v in [('key','行键'),('metric','指标'),('period','期间'),('start','开始'),('end','结束')]},
            'amount':col('金额','百万元',currency),'basis':col('重述标记'),'origin':col('取值类型'),'missing':col('缺项/冲突')},rows)
        for x in result[name]:
            modes=('qoq','yoy') if name=='quarters' else ('ytd_yoy',)
            for mode in modes:
                candidates=[p for p in result[name] if (p['entity'],p['scope'],p['metric'],p['currency'])==(x['entity'],x['scope'],x['metric'],x['currency'])]
                if mode=='qoq':
                    from datetime import date,timedelta
                    candidates=[p for p in candidates if p['end']==str(date.fromisoformat(x['start'])-timedelta(days=1))]
                else:candidates=[p for p in candidates if p['start'][5:]==x['start'][5:] and p['end'][5:]==x['end'][5:] and int(p['start'][:4])==int(x['start'][:4])-1]
                prior=candidates[0] if len(candidates)==1 else None
                change_values=change(x,prior,mode) if prior else {'delta':cell(None,currency=currency,reason='缺少可比期金额'),'growth':cell(None,'%',reason='缺少可比期金额；未由披露增长率倒算')}
                key=f'{name}_{len(changes)}'
                changes.append({'key':key,'metric':x['metric'],'period':x['period'],'comparison':prior['period'] if prior else None,'mode':mode,**{k:change_values[k] for k in ('delta','growth')}})
                if change_values['growth']['value'] is not None:
                    findings.append({'key':key,'finding':f'{x["period"]} {x["metric"]} {mode} {change_values["growth"]["value"]}%','basis':'changes.'+key})
    tabs['changes']=table({**{k:col(v) for k,v in [('key','行键'),('metric','指标'),('period','期间'),('comparison','可比期'),('mode','比较方法')]},'delta':col('金额变化','百万元',currency),'growth':col('增长率','%')},changes)
    checks=[]
    for i,r in enumerate(result['reconciliations']):
        checks.append({'key':str(i),'metric':r['metric'],'period':r['period'],'disclosed':r['disclosed']['quantity'],'derived':r['derived']['quantity'],'residual':r['residual']})
        findings.append({'key':'check_'+str(i),'finding':f'{r["period"]} {r["metric"]} 披露单季减累计差额推导值：{r["residual"]["value"] if r["residual"]["value"] is not None else "未知"} 元','basis':'reconciliation.'+str(i)})
    tabs['reconciliation']=table({'key':col('行键'),'metric':col('指标'),'period':col('单季'),**{k:col(v,'百万元',currency) for k,v in [('disclosed','披露单季'),('derived','累计差额推导'),('residual','披露减推导')]}},checks)
    tabs['observations']=table({'key':col('行键'),'finding':col('数值关系'),'basis':col('底稿位置')},findings)
    unknown=[*result['unknown_rows'],*[{'label':x['metric'],'reason':x.get('reason') or '非标准流量期间','source':x['quantity']['source']} for x in result['unrecognized_periods']]]
    tabs['unrecognized']=table({'key':col('行键'),'label':col('原指标'),'reason':col('原因'),'source':col('原文与来源')},[{'key':str(i),**r,'source':json.dumps(r['source'],ensure_ascii=False)} for i,r in enumerate(unknown)])
    tabs['missing']=table({k:col(v) for k,v in [('key','行键'),('metric','指标'),('period','缺失单季'),('reason','所缺输入')]},
        [{'key':str(i),**{k:r[k] for k in ('metric','period','reason')}} for i,r in enumerate(result['missing'])])
    return {'title':result['company']+' 期间推导与季报底稿','periods':result['periods'],'body':'按起止日识别单季和累计；优先当前报告比较列及调整后数。单季=累计差额；所有输入和口径随来源链保存。非正基期只列金额变化，常规增长率未知。无比较金额时不从百分比倒算。','tables':tabs},result['records']
