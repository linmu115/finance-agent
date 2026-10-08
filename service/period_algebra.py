"""Public, deterministic period algebra over sourced quantities.

Amounts are flows, never balances, EPS or percentages. Dates, not a Q3 label,
decide whether an input is a quarter or year-to-date. No service/DB dependency.
"""
from calendar import monthrange
from datetime import date, timedelta
from decimal import Decimal, localcontext
import re

from .analysis_report import convert
from .financial_workpapers import cell


def quarter_window(year, quarter):
    month = quarter * 3
    return f'{year}-{month-2:02d}-01', f'{year}-{month:02d}-{monthrange(year,month)[1]}'


def identify_period(period='', start=None, end=None, label=''):
    """Return dates + kind; an undated Q2/Q3 label alone is ambiguous."""
    year = re.search(r'20\d{2}', str(period))
    year = int(year[0]) if year else None
    if not start or not end:
        if year and re.search(r'FY|全年|年度|H1|半年|上半年', period+' '+label, re.I):
            start=f'{year}-01-01';end=f'{year}-06-30' if re.search('H1|半年',period+' '+label,re.I) else f'{year}-12-31'
        elif year and (m:=re.search(r'Q([1-4])',period,re.I)):
            q=int(m[1])
            if q==1 or re.search('单季|本季度|季度初',label):start,end=quarter_window(year,q)
            elif re.search('累计|年初至|前三季|前[一二三四1234]季',label):
                start=f'{year}-01-01';end=quarter_window(year,q)[1]
    if not start or not end:
        return {'start':start,'end':end,'kind':'unknown','reason':'缺少明确起止日期；Q2/Q3 标签不能区分单季与累计'}
    a,b=date.fromisoformat(start),date.fromisoformat(end)
    if a>b:raise ValueError('period start is after end')
    if a==b:kind='instant'
    elif a.year==b.year and (start,end)==quarter_window(a.year,(b.month+2)//3):kind='quarter'
    elif a.year==b.year and a.month==a.day==1 and b.month in (6,9,12) and b.day==monthrange(b.year,b.month)[1]:kind='annual' if b.month==12 else 'ytd'
    else:kind='other'
    return {'start':start,'end':end,'kind':kind,'reason':None}


def observation(metric, quantity, *, entity, scope, start, end, document_id,
                restatement='unspecified', basis_id=None, period='', label='', additive=True):
    return {'metric':metric,'entity':entity,'scope':scope,'currency':quantity.get('currency'),
            **identify_period(period,start,end,label),'document_id':document_id,
            'restatement':restatement or 'unspecified','basis_id':basis_id,'additive':additive,
            'quantity':quantity}


def basis_check(items):
    """An explicit common basis_id can tie current and restated comparatives."""
    for field in ('entity','scope','currency','metric'):
        if len({x[field] for x in items})>1:return f'{field} 不一致，未计算'
    versions={x['restatement'] for x in items}
    ids={x.get('basis_id') for x in items}
    if len(ids)==1 and None not in ids:return None
    if 'restated' in versions and versions!={'restated'}:
        return '重述与未重述/未标注口径混用，缺少共同口径依据，未计算'
    if len(ids-{None})>1:return '来源明确指向不同会计口径，未计算'
    return None


def _calculate(items, formula, fn, reason=None, unit='元'):
    reason=reason or basis_check(items)
    if any(x['quantity']['value'] is None for x in items):reason=reason or '输入存在未知值'
    if unit=='元' and any(not x['additive'] or x['kind']=='instant' for x in items):reason=reason or '余额或非可加指标不能按期间加减'
    values=[Decimal(convert(x['quantity']['value'],x['quantity']['unit'],'元')) for x in items] if not reason else []
    with localcontext() as ctx:
        ctx.prec=40
        value=fn(values) if not reason else None
    # Preserve quantities, period windows and version evidence, not just fact IDs.
    return cell(value,unit,items[0]['currency'] if items and unit=='元' else None,
                [{'period':{k:v for k,v in x.items() if k!='quantity'},'quantity':x['quantity']} for x in items],formula,reason)


def select_observation(items, preferred_document_id=None):
    """Prefer the current report's comparative; then its adjusted-after column.

    Candidates must describe one metric/window. Conflicting values are retained
    in the result source instead of selecting an arbitrary physical occurrence.
    """
    if not items:return None
    preferred=[x for x in items if x['document_id']==preferred_document_id]
    chosen=preferred or items
    restated=[x for x in chosen if x['restatement']=='restated']
    if restated:chosen=restated
    signature={(x['start'],x['end'],x['metric']) for x in chosen}
    if len(signature)!=1:raise ValueError('select_observation requires one metric and window')
    reason=basis_check(chosen)
    values={str(convert(x['quantity']['value'],x['quantity']['unit'],'元')) if x['quantity']['value'] is not None else None for x in chosen}
    if len(values)>1:reason='同一优先报告、期间和口径存在不同数值；保留候选，未擅选'
    if reason:
        return {**chosen[0],'quantity':_calculate(chosen,'选择同口径来源',lambda v:v[0],reason)}
    result={**chosen[0],'quantity':{**chosen[0]['quantity'],'source':{**chosen[0]['quantity']['source'],
            'selection':'优先当前报告比较列，再取调整后列','alternatives':[x['quantity']['source'] for x in items if x not in chosen]}}}
    return result


def sum_periods(items):
    """Sum adjacent flow windows. Gaps and overlaps produce an unknown cell."""
    if not items:raise ValueError('sum_periods needs period inputs')
    items=sorted(items,key=lambda x:x['start'] or '')
    reason=None
    for a,b in zip(items,items[1:]):
        if not a['end'] or not b['start'] or date.fromisoformat(a['end'])+timedelta(days=1)!=date.fromisoformat(b['start']):
            reason='期间存在缺口或重叠，不能作为连续累计数'
    q=_calculate(items,'连续期间之和',sum,reason)
    return {**items[0],**identify_period(start=items[0]['start'],end=items[-1]['end']),
            'quantity':q,'restatement':items[0]['restatement']}


def single_quarter(current, previous=None):
    """Qn = YTDn - YTD(n-1); Q1 is itself. No missing values become zero."""
    if current['kind']=='quarter' and current['start'][5:]=='01-01' and previous is None:return current
    reason=None
    if previous is None:return {**current,'quantity':cell(None,currency=current['currency'],sources=[current['quantity']['source']],reason='缺少前一累计期，不能推导单季')}
    items=[current,previous]
    if current['kind'] not in ('annual','ytd') or previous['kind'] not in ('ytd','quarter') or current['start']!=previous['start']:
        reason='必须使用同一起点的相邻累计期间'
    start=str(date.fromisoformat(previous['end'])+timedelta(days=1)) if previous['end'] else None
    window=identify_period(start=start,end=current['end']) if start and start<=current['end'] else {'start':start,'end':current['end'],'kind':'unknown'}
    if window['kind']!='quarter':reason=reason or '累计差额没有对应完整单季度'
    q=_calculate(items,'本期累计-前一累计期',lambda v:v[0]-v[1],reason)
    return {**current,**window,'quantity':q}


def change(current, previous, mode='yoy'):
    """Return delta and growth; nonpositive denominators retain delta only."""
    if mode not in ('qoq','yoy','ytd_yoy'):raise ValueError('mode must be qoq, yoy or ytd_yoy')
    reason=None
    a,b=current,previous
    if not all(x['start'] and x['end'] for x in (a,b)):reason='缺少可比期间'
    elif mode=='qoq':
        if a['kind']!=b['kind'] or a['kind']!='quarter' or date.fromisoformat(b['end'])+timedelta(days=1)!=date.fromisoformat(a['start']):reason='环比需要相邻单季度'
    else:
        if (a['start'][5:],a['end'][5:])!=(b['start'][5:],b['end'][5:]) or int(a['start'][:4])!=int(b['start'][:4])+1:reason='同比需要相邻年度相同起止窗口'
        if mode=='ytd_yoy' and (a['start'][5:]!='01-01' or b['start'][5:]!='01-01'):reason='累计同比需要年初起累计口径'
    delta=_calculate([a,b],'本期-可比期',lambda v:v[0]-v[1],reason)
    base=b['quantity']['value']
    rate_reason=reason or ('基期非正，常规增长率不适用；保留金额差额' if base is not None and Decimal(base)<=0 else None)
    growth=_calculate([a,b],'(本期-可比期)/可比期*100',lambda v:(v[0]-v[1])/v[1]*100,rate_reason,'%')
    return {'delta':delta,'growth':growth,'mode':mode}


def derive_period_series(items, preferred_document_id=None):
    """N4 entry point. Return sourced quarters/cumulatives/reconciliations.

    Each input is observation(...). Does not write files or query a database.
    Missing quarter inputs stay absent; reported vs derived amounts are both
    preserved in reconciliation rows. Current-report disclosures take priority.
    """
    quarters=[];cumulatives=[];checks=[];issues=[];missing=[]
    for x in items:
        if x['kind'] in ('unknown','other','instant'):issues.append(x)
    groups=sorted({(x['entity'],x['scope'],x['currency'],x['metric'],int(x['start'][:4])) for x in items if x['start'] and x['kind'] in ('quarter','ytd','annual')})
    for entity,scope,currency,metric,year in groups:
        group=[x for x in items if (x['entity'],x['scope'],x['currency'],x['metric'])==(entity,scope,currency,metric) and x['start'] and x['start'][:4]==str(year)]
        prior=None;resolved=[]
        for q in range(1,5):
            start,end=quarter_window(year,q)
            direct=select_observation([x for x in group if (x['start'],x['end'])==(start,end)],preferred_document_id)
            cum=select_observation([x for x in group if (x['start'],x['end'])==(f'{year}-01-01',end)],preferred_document_id)
            if cum is None and len(resolved)==q-1 and direct is not None:cum=sum_periods([*resolved,direct])
            derived=single_quarter(cum,prior) if cum and (q==1 or prior) else None
            if direct and derived and q>1:
                gap=_calculate([direct,derived],'披露单季-累计差额推导单季',lambda v:v[0]-v[1])
                checks.append({'metric':metric,'period':f'{year}-Q{q}','disclosed':direct,'derived':derived,'residual':gap})
            chosen=direct or derived
            if derived and direct and derived['document_id']==preferred_document_id and direct['document_id']!=preferred_document_id:chosen=derived
            if chosen:quarters.append({**chosen,'period':f'{year}-Q{q}'});resolved.append(chosen)
            else:missing.append({'metric':metric,'period':f'{year}-Q{q}',
                'reason':'没有披露单季，且缺少本期累计或前一累计期；未用跨期金额/增长率补算',
                'available_windows':[{'start':x['start'],'end':x['end'],'source':x['quantity']['source']} for x in group]})
            if cum:cumulatives.append({**cum,'period':f'{year}-YTD{q}'})
            prior=cum
    return {'quarters':quarters,'cumulatives':cumulatives,'reconciliations':checks,'unrecognized_periods':issues,'missing':missing}
