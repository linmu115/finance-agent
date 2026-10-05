"""Host-only source-coordinate and semantic acceptance, never imported by worker."""
import argparse
import json
import re
from collections import Counter,defaultdict
from decimal import Decimal,InvalidOperation
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
PREPARED=ROOT/'data/indexes/b43ae45c-d96b-43b6-ab5b-04306c0eb142/1f94f25a3cb74d528f10ddac0be06a0d.json'

def literal(raw):
    value=re.sub(r'[,，\s%％]','',raw).replace('−','-').replace('﹣','-')
    if value.startswith(('(','（')) and value.endswith((')','）')):value='-'+value[1:-1]
    try:return Decimal(value)
    except InvalidOperation:return None

def expected(table):
    index=table['index'];checks=[]
    for row,values in enumerate(table['rows'][:24],1):
        for column,raw in enumerate(values,1):
            value=literal(raw);currency='CNY';period=None;dimensions=False;scope='consolidated_CAS'
            if index==9 and row>=2 and column in {2,3,4,5}:
                period=str({2:2024,3:2023,4:2024,5:2022}[column])+'-FY'
                currency='percent' if column==4 or row>=5 else 'CNY/share'
                if row>=5 and column==4:
                    value=-Decimal(re.search(r'[\d.]+',raw)[0]);currency='percentage_points'
            elif index==16 and row in {1,2,3,6,7,8,9,10,13,14} and column in range(2,8):
                period='2024-FY';dimensions=True
                currency='CNY' if column in {2,3} else 'percentage_points' if column==7 else 'percent'
                if column==7:value=Decimal(re.search(r'[\d.]+',raw)[0])*(-1 if '减少' in raw else 1)
            elif index in {100,104,108} and column in {3,4} and value is not None and row>1:
                period=str(2024 if column==3 else 2023)+('-12-31' if index==100 else '-FY')
            elif index==173 and column in range(2,9) and row>1 and value is not None:
                period='2023-12-31' if row in {3,12,21} else '2024-12-31' if row in {10,19} else '2024-FY'
                dimensions=column!=8
            elif index==325 and column in {2,3,8,9} and value is not None:
                period='2023-12-31' if column in {2,3} else '2024-12-31';dimensions=True;scope='parent_CAS'
            elif index==78 and row>=3 and column in {2,3,7,8,9,10} and value is not None:
                period='2023-12-31' if column in {2,3} else '2024-12-31' if column in {9,10} else '2024-FY'
                currency='percent' if column in {3,10} else 'shares';scope='issuer'
            elif index==272 and column in {3,6,7} and value is not None:
                period='2024-12-31';dimensions=True
                if column==3:value*=10000
                else:currency='percent'
            if period is not None and value is not None:
                # "期初" has no literal calendar date in these notes. Both the
                # prior closing boundary and the current opening boundary are
                # valid instant representations; neither can be a FY flow or
                # the current closing balance. Explicitly dated statements
                # (including all 66 primary PDF checks) remain exact-date only.
                opening=(index==173 and row in {3,12,21}) or (index==325 and column in {2,3}) or (index==78 and column in {2,3})
                checks.append({'row':row,'column':column,'value':str(value),'currency':currency,'period':period,
                               'accepted_periods':[period,'2024-01-01'] if opening else [period],'scope':scope,'dimensions_required':dimensions})
    return checks

def evaluate(directory):
    tables={t['index']:t for t in json.loads(PREPARED.read_text(encoding='utf-8'))['parsed']['tables']}
    results={}
    for path in sorted(directory.glob('*.json')):
        data=json.loads(path.read_text(encoding='utf-8'))
        if 'facts' not in data:continue
        checks=[];facts=data['facts'];table=tables[data['table']]
        for target in expected(table):
            found=[f for f in facts if f['source']['row']==target['row'] and f['source']['column']==target['column']]
            scopes={'consolidated_CAS','parent_CAS','unspecified'} if target['scope']=='issuer' else {target['scope']}
            currencies={'shares','股'} if target['currency']=='shares' else {target['currency']}
            exact=[f for f in found if Decimal(f['value'])==Decimal(target['value']) and f['currency'] in currencies and f['period'] in target['accepted_periods'] and f['scope'] in scopes and (not target['dimensions_required'] or f['source']['normalization'].get('dimensions'))]
            checks.append({**target,'passed':bool(exact),'actual':[{'metric':f['metric'],'value':f['value'],'currency':f['currency'],'period':f['period'],'scope':f['scope'],'dimensions':f['source']['normalization'].get('dimensions')} for f in found]})
        source_errors=[]
        for f in facts:
            s=f['source'];raw=table['rows'][s['row']-1][s['column']-1]
            if raw!=f['raw_value']:source_errors.append({'row':s['row'],'column':s['column']})
            span=s['normalization'].get('numeric_span')
            if span and raw[span['start']:span['end']]!=span['text']:source_errors.append({'row':s['row'],'column':s['column'],'error':'span'})
        ambiguous=None
        if data['table']==304:
            amounts=[f for f in facts if f['source']['row']==2 and f['source']['column']==3]
            ambiguous={'stored':[{'value':f['value'],'period':f['period'],'currency':f['currency']} for f in amounts],
                       'passed':all(Decimal(f['value'])==Decimal('30000000000') and f['period'].startswith('2025-') and f['currency']=='CNY' for f in amounts) and (bool(amounts) or any(i['reason']=='unresolved_period' for i in data['report']['issues']))}
        results[path.stem]={'mode':data['mode'],'case':data['case'],'facts':len(facts),'checks':len(checks),'passed':sum(c['passed'] for c in checks),
                           'failures':[c for c in checks if not c['passed']],'source_errors':source_errors,'ambiguous_period':ambiguous,'issues':dict(Counter(i['reason'] for i in data['report']['issues']))}
    usage={}
    for path in directory.glob('*-requests.jsonl'):
        counts=defaultdict(int);efforts=defaultdict(lambda:defaultdict(int));pending=set()
        for line in path.read_text(encoding='utf-8').splitlines():
            event=json.loads(line)
            if event['type']=='request':pending.add(event['requestId'])
            if event['type']!='result':continue
            pending.discard(event['requestId'])
            u=event['usage'];counts['calls']+=1;efforts[event['effort']]['calls']+=1
            for field in ('input','cacheRead','output','reasoning'):
                counts[field]+=u.get(field,0);efforts[event['effort']][field]+=u.get(field,0)
            if event['stopReason'] in {'error','aborted','length'}:counts['failed']+=1
            if event['stopReason'] in {'error','aborted'} and not sum(u.get(f,0) for f in ('input','cacheRead','output')):counts['unknown_usage']+=1
        counts['unfinished_requests']=len(pending)
        counts['unknown_usage']+=len(pending)
        counts['known_usd']=(counts['input']*.15+counts['cacheRead']*.003+counts['output']*.6)/1e6
        counts['tokens']=counts['input']+counts['cacheRead']+counts['output']
        usage[path.stem.replace('-requests','')]={'total':dict(counts),'efforts':{k:dict(v) for k,v in efforts.items()}}
    return {'cases':results,'usage':usage,'scope':'Ten fixed source slices; not a full-report cost or an all-facts semantic proof. Repairs included. Host reference never sent to the model.'}

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('directory');args=parser.parse_args();directory=Path(args.directory)
    result=evaluate(directory);(directory/'evaluation.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'usage':result['usage'],'checks':{k:{f:v[f] for f in ('checks','passed','facts','ambiguous_period')} for k,v in result['cases'].items()}}))
