"""K4 pure expectations ledger; no database writes, retrieval, or model calls."""
from collections import defaultdict
from datetime import date
from decimal import Decimal, localcontext
import json

from .analysis_report import convert, record_quantity, stated_quantity, unit_info
from .financial_workpapers import WorkpaperInputError, cell, col, table


BASE_UNIT = {'money':'元','per_share':'元/股','shares':'股','ratio':'ratio',
             'multiple':'倍','days':'天','count':'个','percentage_points':'个百分点'}


def quantity(record):
    q = stated_quantity(record) if 'unit' in record else record_quantity(record)
    dimension = unit_info(q['unit'])[0]
    unit = BASE_UNIT[dimension]
    value = convert(q['value'],q['unit'],unit)
    src = q.get('source') or {k:record[k] for k in ('record_id','fact_id','document_id','source_ref','data_kind') if k in record}
    return dict(value=None if value is None else Decimal(value),unit=unit,currency=q['currency'],source=src,dimension=dimension)


def identity(r, q):
    # Never collapse scope, EPS basis, scenarios, segments or entities by a display label.
    dimensions = {k:v for k,v in (r.get('dimensions') or {}).items() if k != 'source_table'}
    return (r['entity_id'],r['metric'],r['period'],r.get('scope'),r.get('scenario','unspecified'),
            r.get('basis'),json.dumps(dimensions,sort_keys=True,ensure_ascii=False),q['unit'],q['currency'])


def dated(r):
    return date.fromisoformat(r['published_at']) if r.get('published_at') else None


def actual_identity(ident):
    # Actuals have no forecast scenario. Each scenario may compare with that same
    # realized value, while revisions/rankings remain separated by scenario.
    return ident[:4]+ident[5:]


def expectations_report(records, actuals=(), as_of=None):
    """Research records use analyst_forecast; actuals must be primary statement facts.

    published_at and as_of are ISO calendar dates, cutoff inclusive. No cutoff means
    all supplied dated forecasts, never today's implicit date. Actuals are an
    explicitly supplied ex-post comparison; actual publication date stays visible.
    """
    with localcontext() as ctx:
        ctx.prec = 50
        return _expectations(records,actuals,date.fromisoformat(as_of) if as_of else None)


def _expectations(records, actuals, cutoff):
    buckets = defaultdict(lambda: defaultdict(list))
    groups, actual_groups = defaultdict(list), defaultdict(list)
    observation_rows = []
    index = 0
    def desc(r,q):
        nonlocal index
        index += 1
        return {'key':str(index),'entity':r.get('company') or r.get('entity',{}).get('name') or r['entity_id'],
                'entity_id':r['entity_id'],'publisher':r.get('publisher'),'published_at':r.get('published_at'),
                'period':r['period'],'metric':r['metric'],'scope':r.get('scope'),
                'scenario':r.get('scenario','unspecified'),'basis':r.get('basis'),
                'dimensions':json.dumps(r.get('dimensions',{}),sort_keys=True,ensure_ascii=False),
                'record':r.get('record_id') or r.get('fact_id'),
                'value':cell(q['value'],q['unit'],q['currency'],[q['source']])}
    def part(q):return (q['dimension'],q['unit'],q['currency'])
    for r in records:
        if r.get('value') is None and not r.get('metric'):continue  # Prose has no forecast amount.
        q=quantity(r);p=part(q);d=dated(r);row=desc(r,q)
        if r.get('data_kind')!='analyst_forecast':reason='非机构预测，不进入当时预期'
        elif d is None:reason='发布日期不明，不进入当时预期'
        elif cutoff and d>cutoff:reason='晚于预测截止日'
        elif not r.get('publisher'):reason='机构不明，不能分配预测版本'
        elif not r.get('scope'):reason='口径不明，不能与实际值匹配'
        else:reason=None
        row['status']=reason or '纳入'
        buckets[p]['excluded' if reason else 'ledger'].append(row)
        if reason is None:groups[(r['publisher'],identity(r,q))].append((r,q,row))
    for r in actuals:
        if not r.get('fact_id') and r.get('data_kind')!='reported_actual':
            raise WorkpaperInputError('actuals 必须是原财报事实或显式 reported_actual；不能把研报 quoted_actual/预测当作实际值')
        q=quantity(r);actual_groups[actual_identity(identity(r,q))].append((r,q))

    comparisons=[]
    for (publisher,ident),items in groups.items():
        versions=defaultdict(list)
        for item in items:versions[item[0]['published_at']].append(item)
        previous=None
        for publication in sorted(versions):
            same_day=versions[publication]
            unique={item[1]['value'] for item in same_day}
            r,q,base=same_day[0]
            v=next(iter(unique)) if len(unique)==1 else None
            refs=[x[1]['source'] for x in same_day]
            reason='同日同口径预测冲突，未任取一条' if len(unique)>1 else ('该版本缺值' if v is None else None)
            buckets[part(q)]['revisions'].append({**base,'value':cell(v,q['unit'],q['currency'],refs,reason=reason),
                'previous_date':previous['date'] if previous else None,
                'previous':cell(previous['value'] if previous else None,q['unit'],q['currency'],previous['refs'] if previous else [],reason='无更早版本' if not previous else previous['reason']),
                'change':cell(v-previous['value'] if previous and previous['value'] is not None and v is not None else None,q['unit'],q['currency'],refs+(previous['refs'] if previous else []),
                              formula='current_forecast-previous_forecast',reason=reason or (previous['reason'] if previous else '无更早版本')),
                'status':reason or '可比较'})
            previous={'date':publication,'value':v,'refs':refs,'reason':reason,'record':r,'q':q,'base':base}
        latest=previous;r=latest['record'];q=latest['q'];v=latest['value'];p=part(q)
        candidates=actual_groups.get(actual_identity(ident),[])
        actual_values={x[1]['value'] for x in candidates}
        actual=next(iter(actual_values)) if len(actual_values)==1 else None
        reason=latest['reason']
        if not candidates:reason=reason or '缺少相同主体、年度、指标、口径、每股/重述口径和币种的原财报实际值'
        elif len(actual_values)>1:reason=reason or '同口径实际值冲突，未任取一条'
        elif actual is None:reason=reason or '实际值缺失'
        diff=actual-v if reason is None else None
        rate=diff/abs(v)*100 if diff is not None and v!=0 else None
        refs=latest['refs']+[x[1]['source'] for x in candidates]
        actual_dates=sorted({x[0].get('published_at') for x in candidates if x[0].get('published_at')})
        row={**latest['base'],'key':str(len(comparisons)),'value':cell(v,q['unit'],q['currency'],latest['refs'],reason=latest['reason']),
             'actual':cell(actual,q['unit'],q['currency'],[x[1]['source'] for x in candidates],reason=reason if actual is None else None),
             'difference':cell(diff,q['unit'],q['currency'],refs,formula='actual-forecast',reason=reason),
             'difference_rate':cell(rate,'%',sources=refs,formula='(actual-forecast)/abs(forecast)*100',reason=reason or ('预测为零，差异率无定义' if v==0 else None)),
             'absolute_error':cell(abs(diff) if diff is not None else None,q['unit'],q['currency'],refs,formula='abs(actual-forecast)',reason=reason),
             'actual_published_at':', '.join(actual_dates) or None,
             'actual_timing':'回测实际值（披露日晚于预测截止日）' if cutoff and actual_dates and any(date.fromisoformat(d)>cutoff for d in actual_dates) else ('实际披露日期不明' if candidates and not actual_dates else '已提供的原财报实际值'),
             'status':reason or '可比较','rank':None}
        buckets[p]['actual_vs_expected'].append(row)
        comparisons.append((ident,q,row,diff))
    ranked=defaultdict(list)
    for ident,q,row,diff in comparisons:
        if diff is not None:ranked[ident].append((q,row,diff))
    for rows in ranked.values():
        low=min(abs(d) for _,_,d in rows);high=max(abs(d) for _,_,d in rows)
        for q,row,diff in rows:
            labels=[]
            if abs(diff)==high:labels.append('最大偏差')
            if abs(diff)==low:labels.append('最小偏差')
            row['rank']='、'.join(labels) if labels else '中间偏差'
            observation_rows.append({'key':row['key'],'finding':f'{row["entity"]} {row["period"]} {row["metric"]}：{row["publisher"]} {row["published_at"]} 预测与实际差异',
                                     'difference_rate':row['difference_rate'],'rank':row['rank'],
                                     'table':f'actual_vs_expected_{q["currency"] or "unitless"}_{q["dimension"]}'})
    observation_rows.sort(key=lambda r:(r['difference_rate']['value'] is not None,abs(Decimal(r['difference_rate']['value'] or '0'))),reverse=True)
    tabs={}
    common={k:col(v) for k,v in [('key','行键'),('entity','主体'),('entity_id','主体身份'),('publisher','机构'),('published_at','预测发布日期'),
                                ('period','预测/实际期间'),('metric','指标'),('scope','报告口径'),('scenario','情景'),('basis','每股/重述口径'),('dimensions','维度'),('record','原记录'),('status','状态')]}
    for (dimension,unit,currency),families in sorted(buckets.items(),key=lambda pair:str(pair[0])):
        suffix=f'{currency or "unitless"}_{dimension}'
        for family,rows in families.items():
            cols={**common,'value':col('机构预测' if family!='excluded' else '原记录值',unit,currency)}
            if family=='revisions':
                cols.update(previous_date=col('上一版本发布日期'),previous=col('上一版本预测',unit,currency),change=col('本次预测减上次预测',unit,currency))
            if family=='actual_vs_expected':
                cols.update(actual=col('财报实际值',unit,currency),difference=col('实际减预测',unit,currency),
                            difference_rate=col('差异率（绝对预测为分母）','%'),absolute_error=col('绝对偏差',unit,currency),
                            actual_published_at=col('实际披露日期'),actual_timing=col('实际值时间身份'),rank=col('同口径机构绝对偏差排名（并列保留）'))
            tabs[family+'_'+suffix]=table(cols,rows)
    tabs['observations']=table({'key':col('行键'),'finding':col('确定性数值关系（差异率绝对幅度降序）'),
                                'difference_rate':col('差异率','%'),'rank':col('同口径排名'),'table':col('详细数值表')},observation_rows)
    return {'title':'预期差账本','body':f'预测冻结截至 {cutoff.isoformat() if cutoff else "所提供的全部明确发布日期"}（含当日）；日期不明和晚于截止日的记录单列。实际值为显式提供的原财报回测参照，披露日在表中保留，不代表预测截止日已知。修正轨迹不跨机构、主体、期间、口径、情景或币种；差异率=(实际-预测)/abs(预测)，零预测差异率留空。最大/最小按同口径绝对金额偏差排名，只有一家时两者相同，平局保留。','tables':tabs}
