"""K2 calculation core. Inputs are explicitly scoped, sourced statement quantities.

No retrieval, ingestion or FX conversion. A subject is one entity/period/scope;
metrics are analysis_report quantities, balances have explicit _begin/_end keys.
"""
from datetime import date
from decimal import Decimal, localcontext
from itertools import combinations
import re

from .analysis_report import convert, stated_quantity
from .financial_workpapers import WorkpaperInputError, cell, col, table
from .research_models import financial_quality


def comparison(service,project,document_id=None,company=None,scope='consolidated',periods=None,focus=None):
    """One report supplies current and comparative columns for the same entity."""
    from .financial_workpapers import Statement,load_facts,meta,source
    from .analysis_report import record_quantity
    from .workpaper_annual import Disclosure
    from datetime import timedelta
    st=Statement(service,project,load_facts(service,project,document_id,company),scope,periods)
    disclosure=Disclosure(st);subjects=[]
    by_id={t['table_id']:t for t in disclosure.tabs}
    provenance=[]
    for p in st.periods:
        rev=st.pick('revenue',p,'income')
        if not rev:raise WorkpaperInputError(f'{p} 缺少收入期间来源')
        start,end=meta(rev).get('period_start'),meta(rev).get('period_end')
        if not start or not end:raise WorkpaperInputError(f'{p} 缺少报告起止日期')
        metrics={}
        def add(key,r):
            if not r:return
            q=record_quantity(r);ref=r['source_ref'];t=by_id.get(ref.get('table_id'))
            header=''
            if t and ref.get('column'):
                c=ref['column']-1
                # Search preceding headers, including a balance subsection's dates.
                for row in t['rows'][:ref.get('row',1)]:
                    if c<len(row) and re.match(r'\s*(?:20\d{2}\s*年|本期|上期|本年|上年)',row[c]):header=row[c]
            provenance.append({'key':p+'_'+key,'metric':key,'period':p,'report':disclosure.document.get('original_name'),
                               'document_id':disclosure.doc,'page':ref.get('page'),'table_id':ref.get('table_id'),'column':ref.get('column'),
                               'column_label':header or '见来源计算输入','basis':'同一报告内当期/比较列；没有查询另一份年报'})
            metrics[key]=q
        for k in INCOME+('deducted_profit',):add(k,st.pick(k,p,'income'))
        add('cfo',st.pick('cfo',p,'cashflow'))
        for k in ('assets','equity','parent_equity','liabilities','receivables','inventory','payables'):
            for suffix,when in [('begin',str(date.fromisoformat(start)-timedelta(days=1))),('end',end)]:add(k+'_'+suffix,st.pick(k,when,'balance'))
        for suffix in ('begin','end'):add('cash_'+suffix,st.pick('cash_'+suffix,p,'cashflow'))
        subjects.append({'key':p,'company':st.company,'entity_id':st.company,'period':p,'period_start':start,'period_end':end,
                         'scope':st.scope,'currency':st.currency,'metrics':metrics,'period_source':source(rev),
                         'metadata':{'scope':{'value':st.scope,'source':source(rev)},'currency':{'value':st.currency,'source':source(rev)},
                                     'restated':{'value':meta(rev).get('restatement'),'source':source(rev)}}})
    report=comparison_report(subjects)
    report['tables']['report_columns']=table({k:col(v) for k,v in [('key','行键'),('metric','指标'),('period','期间'),('report','数据所属报告'),('document_id','报告ID'),('page','PDF页'),('table_id','原表ID'),('column','原列号'),('column_label','原列头'),('basis','比较路径')]},provenance)
    report['tables']['missing']=table({k:col(k) for k in ('key','metric','period','reason','candidates')},[{'key':str(i),**r,'candidates':str(r['candidates'])} for i,r in enumerate(st.missing)])
    return report,st.facts


INCOME = ('revenue', 'cogs', 'gross_profit', 'selling', 'administrative',
          'research', 'operating_profit', 'net_profit', 'parent_profit')
BALANCE = ('assets_end', 'cash_end', 'receivables_end', 'inventory_end',
           'liabilities_end', 'payables_end', 'equity_end')
META = ('fiscal_year_end', 'scope', 'currency', 'accounting_standard', 'restated')


class Subject:
    def __init__(self, raw):
        self.raw = raw
        self.key = raw['key']
        self.currency = raw['currency']
        self.values, self.refs, self.missing = {}, {}, {}
        for key, value in raw['metrics'].items():
            q = stated_quantity(value)
            if q['currency'] != self.currency:
                self.missing[key] = f'{key} 币种 {q["currency"]} 与本列 {self.currency} 不一致，未换汇'
            elif q['value'] is None:
                self.missing[key] = q.get('source', {}).get('missing_reason') or f'缺少 {key}'
            else:
                self.values[key] = Decimal(convert(q['value'], q['unit'], '元'))
            self.refs[key] = q.get('source', {})

    def calc(self, keys, fn, unit='ratio', formula=None, positive=()):
        reason = '; '.join(self.missing.get(k, f'缺少 {k}') for k in keys if k not in self.values)
        if not reason:
            reason = '; '.join(f'{k} 非正，比例无可解释的正分母' for k in positive if self.values[k] <= 0)
        value = None if reason else fn(*(self.values[k] for k in keys))
        return cell(value, unit, self.currency if unit == '元' else None,
                    [self.refs[k] for k in keys if k in self.refs], formula, reason or None)


def comparison_report(subjects):
    """Pure core; subject.metadata stores {value, source} comparability evidence.

    entity_id, period, period_start/end, scope, currency and metrics are required.
    Costs retain the disclosed sign in common size; days use abs(cogs) as a proxy.
    Dupont uses consolidated profit / consolidated equity (or parent statement
    profit / parent statement equity); parent_profit is never substituted.
    """
    with localcontext() as ctx:
        ctx.prec = 50
        return _comparison(subjects)


def _comparison(raws):
    subjects = [Subject(r) for r in raws]
    if not subjects or len({s.key for s in subjects}) != len(subjects):
        raise WorkpaperInputError('comparison 需要至少一个主体期间，且 key 唯一')
    tabs = {}
    tabs['amounts'] = table({'key':col('指标'), **{s.key:col(f'{s.raw["company"]} {s.raw["period"]}', '元', s.currency, scope=s.raw['scope']) for s in subjects}},
                            [{'key':metric, **{s.key:s.calc((metric,),lambda x:x,'元',metric) for s in subjects}}
                             for metric in sorted({k for s in subjects for k in s.raw['metrics']})])
    columns = {'key': col('指标'), **{s.key: col(f'{s.raw["company"]} {s.raw["period"]}', '%', scope=s.raw['scope']) for s in subjects}}
    for name, metrics, base in [('common_income', INCOME, 'revenue'), ('common_balance', BALANCE, 'assets_end')]:
        rows = []
        for metric in metrics:
            rows.append({'key': metric, **{s.key: s.calc((metric, base), lambda a,b: a/b*100, '%', f'{metric}/{base}*100', (base,)) for s in subjects}})
        tabs[name] = table(columns, rows)

    dupont, cash, days_rows, growth, comparability, observations = [], [], [], [], [], []
    idcols = {'key': col('主体期间'), 'company': col('主体'), 'period': col('报告期间'), 'scope': col('报告口径')}
    for s in subjects:
        r = s.raw
        ident = {'key': s.key, 'company': r['company'], 'period': r['period'], 'scope': r['scope']}
        margin = s.calc(('net_profit', 'revenue'), lambda p,v:p/v, formula='net_profit/revenue', positive=('revenue',))
        turnover = s.calc(('revenue', 'assets_begin', 'assets_end'), lambda v,a,b: v/((a+b)/2) if a+b>0 else None,
                          '倍', 'revenue/average_assets')
        multiplier = s.calc(('assets_begin', 'assets_end', 'equity_begin', 'equity_end'),
                            lambda a,b,c,d: (a+b)/(c+d) if c+d>0 else None, '倍', 'average_assets/average_equity')
        roe = s.calc(('net_profit', 'equity_begin', 'equity_end'), lambda p,a,b:p/((a+b)/2) if a+b>0 else None,
                     formula='net_profit/average_equity')
        for q in (turnover, multiplier, roe):
            if q['value'] is None and not q['source']['missing_reason']:
                q['source']['missing_reason'] = '平均余额非正，比例无可解释的正分母'
        product = None if any(q['value'] is None for q in (margin,turnover,multiplier)) else Decimal(margin['value'])*Decimal(turnover['value'])*Decimal(multiplier['value'])
        refs = [q['source'] for q in (margin,turnover,multiplier)]
        dupont.append({**ident, 'net_margin': margin, 'asset_turnover': turnover, 'equity_multiplier': multiplier, 'roe': roe,
                       'product': cell(product,'ratio',sources=refs,formula='net_margin*asset_turnover*equity_multiplier',reason='缺少可解释的三因子' if product is None else None),
                       'residual': cell(None if product is None or roe['value'] is None else product-Decimal(roe['value']), 'ratio',sources=refs+[roe['source']],formula='product-roe',reason='缺少三因子或 ROE' if product is None or roe['value'] is None else None)})
        # Reuse the established financial_quality formulas and denominator policy.
        begin, end = date.fromisoformat(r['period_start']), date.fromisoformat(r['period_end'])
        days = (end-begin).days+1
        quality_inputs = {'year': end.year, 'days': days}
        for metric, target in [('revenue','revenue'),('net_profit','net_income'),('cfo','cfo'),('cogs','cogs')]+[(x,x) for x in ('receivables_begin','receivables_end','inventory_begin','inventory_end','payables_begin','payables_end')]:
            if metric in s.values:
                quality_inputs[target] = str(abs(s.values[metric]) if metric=='cogs' else s.values[metric])
        quality = financial_quality({'currency':s.currency,'amount_scale':'1','period_basis':'reported_period',
                                     'receivables_sales_basis':'revenue_proxy','payables_cost_basis':'cogs_proxy','periods':[quality_inputs]})['tables']['quality'][0]
        def qc(metric, keys, unit='ratio'):
            missing = [s.missing.get(k, f'缺少 {k}') for k in keys if k not in s.values]
            return cell(quality[metric], unit, sources=[s.refs[k] for k in keys if k in s.refs],
                        formula='financial_quality.'+metric, reason='; '.join(missing) or quality.get(metric+'_reason'))
        cash.append({**ident,'cash_conversion':qc('cash_conversion',('cfo','net_profit')),'cfo_margin':qc('cfo_margin',('cfo','revenue'))})
        days_rows.append({**ident,'days':cell(days,'天',sources=[r.get('period_source',{})]),
                          'dso':qc('dso',('receivables_begin','receivables_end','revenue'),'天'),
                          'dio':qc('dio',('inventory_begin','inventory_end','cogs'),'天'),
                          'dpo':qc('dpo',('payables_begin','payables_end','cogs'),'天'),
                          'cycle':qc('cash_conversion_cycle',('receivables_begin','receivables_end','inventory_begin','inventory_end','payables_begin','payables_end','revenue','cogs'),'天')})
        for field in META:
            evidence = r.get('metadata', {}).get(field)
            comparability.append({'key':s.key+'_'+field,'company':r['company'],'period':r['period'],'field':field,
                                  'value':str(evidence['value']) if evidence and evidence.get('value') is not None else None,
                                  'source':str(evidence.get('source')) if evidence else None,
                                  'note':None if evidence and evidence.get('value') is not None else '缺少可引用披露；不推断'})
        # Compare only the same entity, fiscal window, currency and scope in adjacent years.
        priors = [p for p in subjects if p.raw['entity_id']==r['entity_id'] and p.raw['scope']==r['scope']
                  and p.currency==s.currency and int(p.raw['period_end'][:4])==end.year-1
                  and p.raw['period_start'][5:]==r['period_start'][5:] and p.raw['period_end'][5:]==r['period_end'][5:]]
        prior = priors[0] if len(priors)==1 else None
        for metric in ('revenue','gross_profit','net_profit','parent_profit','cfo'):
            reason = '缺少唯一同主体、相同口径与财年窗口的上年值' if prior is None else None
            current, previous = s.values.get(metric), prior.values.get(metric) if prior else None
            if reason is None and (current is None or previous is None):reason = f'缺少 {metric} 本期或上期'
            if reason is None and previous <= 0:reason = '上期非正，常规增长率不适用；保留原金额'
            refs = [s.refs.get(metric, {})] + ([prior.refs.get(metric,{})] if prior else [])
            value = (current-previous)/previous*100 if reason is None else None
            growth.append({**ident,'key':s.key+'_'+metric,'metric':metric,'previous_period':prior.raw['period'] if prior else None,
                           'growth':cell(value,'%',sources=refs,formula='(current-previous)/previous*100',reason=reason)})
            if value is not None:
                observations.append({'key':s.key+'_'+metric,'finding':f'{r["company"]} {r["period"]} {metric} 同比变化',
                                     'change':cell(value,'%',sources=refs), 'magnitude':abs(value)})
    tabs['dupont'] = table({**idcols,'net_margin':col('净利率（合并利润或母公司报表利润）','%'),
                            'asset_turnover':col('平均资产周转率','倍'),'equity_multiplier':col('平均权益乘数','倍'),
                            'roe':col('平均权益 ROE','%'),'product':col('三因子乘积','%'),'residual':col('乘积减 ROE','%')},dupont)
    tabs['cash_conversion'] = table({**idcols,'cash_conversion':col('CFO/净利润（正利润）','%'),'cfo_margin':col('CFO/收入','%')},cash)
    tabs['operating_days'] = table({**idcols, **{k:col(v,'天') for k,v in [('days','报告天数'),('dso','应收天数（收入代理）'),('dio','存货天数'),('dpo','应付天数（销售成本代理）'),('cycle','现金转换周期')]}},days_rows)
    tabs['growth'] = table({**idcols,'metric':col('指标'),'previous_period':col('可比期间'),'growth':col('同比增长率','%')},growth)
    for row in comparability:
        vals = {x['value'] for x in comparability if x['field']==row['field'] and x['value'] is not None}
        row['difference'] = '存在已披露差异' if len(vals)>1 else ('已披露值相同' if len(vals)==1 and row['value'] is not None else '未知')
    tabs['comparability'] = table({k:col(v) for k,v in [('key','行键'),('company','主体'),('period','期间'),('field','比较口径'),('value','披露值'),('source','来源'),('difference','差异'),('note','缺项')]},comparability)
    for a,b in combinations(subjects,2):
        if (a.raw['period_start'],a.raw['period_end'],a.raw['scope']) != (b.raw['period_start'],b.raw['period_end'],b.raw['scope']):continue
        for metric in ('gross_profit','net_profit'):
            qa = a.calc((metric,'revenue'),lambda p,v:p/v*100,positive=('revenue',))
            qb = b.calc((metric,'revenue'),lambda p,v:p/v*100,positive=('revenue',))
            if qa['value'] is not None and qb['value'] is not None:
                gap = Decimal(qb['value'])-Decimal(qa['value'])
                observations.append({'key':a.key+'_'+b.key+'_'+metric,'finding':f'{b.raw["company"]} 相对 {a.raw["company"]} 的 {metric}/revenue 差异',
                                     'gap_pp':cell(gap,'个百分点',sources=[qa['source'],qb['source']]),'magnitude':abs(gap)})
    observations.sort(key=lambda x:x.pop('magnitude'),reverse=True)
    tabs['observations'] = table({'key':col('行键'),'finding':col('确定性数值关系（按数值幅度降序，单位分列）'),'change':col('同比变化','%'),'gap_pp':col('同期利润率差异','个百分点')},observations)
    return {'title':'同业与跨期比较底稿','body':'杜邦以同一报表口径的净利润和平均总权益计算，未年化；归母利润单列，不代替合并利润。现金转化按正利润分母。周转以收入和销售成本代理，财年天数取实际起止日。金额未隐含换汇，重述和会计准则仅列来源披露。','tables':tabs}
