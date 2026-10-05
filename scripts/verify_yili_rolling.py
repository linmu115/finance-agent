"""Host-side acceptance evidence. Never send these reference answers to the model."""
import json
import argparse
import re
import sqlite3
from collections import Counter, defaultdict
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
import urllib.request
import fitz

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'data/retests/yili-20261004'
DID='1f94f25a3cb74d528f10ddac0be06a0d'


def usage(run_id):
    phases={};events=[];purposes={};stages={}
    for line in (ROOT/'data/audit'/(run_id+'.jsonl')).read_text(encoding='utf-8').splitlines():
        try:event=json.loads(line)
        except json.JSONDecodeError:continue
        events.append(event)
        if event['type']=='extraction_request':
            body='\n'.join(str(m.get('content','')) for m in event['data'].get('messages',[]))
            purposes[event['data']['requestId']]='catalog' if '[[CATALOG]]' in body else 'temporal_profile' if '[[TEMPORAL_REVIEW]]' in body else 'temporal_correction' if '阶段二：对指定原始财务单元格重新理解期间' in body else 'table_cleaning'
        if event['type']!='model_usage':continue
        data=event['data'];u=data.get('usage') or {};key=data['phase']+':'+data.get('reasoningEffort','legacy')
        count=phases.setdefault(key,dict(calls=0,uncached_input=0,cached_input=0,output=0,reasoning=0,failed=0,unknown_usage=0))
        count['calls']+=1
        for target,source in [('uncached_input','input'),('cached_input','cacheRead'),('output','output'),('reasoning','reasoning')]:count[target]+=u.get(source,0)
        stage=stages.setdefault(purposes.get(data.get('requestId'),data['phase']),dict(calls=0,uncached_input=0,cached_input=0,output=0,reasoning=0))
        stage['calls']+=1
        for target,source in [('uncached_input','input'),('cached_input','cacheRead'),('output','output'),('reasoning','reasoning')]:stage[target]+=u.get(source,0)
        count['failed']+=int(data.get('stopReason') in ['length','error','aborted']);count['unknown_usage']+=int(data.get('usageKnown') is False)
    total={k:sum(v[k] for v in phases.values()) for k in next(iter(phases.values()),{})}
    total['all_input']=total.get('uncached_input',0)+total.get('cached_input',0)
    total['total_tokens']=total['all_input']+total.get('output',0)
    # Oct 4 2026 is Sunday; current official Flash off-peak USD rates.
    total['estimated_usd']=(total.get('uncached_input',0)*.15+total.get('cached_input',0)*.003+total.get('output',0)*.6)/1e6
    return {'phases':phases,'stages':stages,'total':total,'compactions':Counter(e['type'] for e in events if e['type'].startswith('compaction_'))},events


def gold():
    items=[]
    def add(label,page,values,years=(2024,2023),instant=False,currency='CNY'):
        for year,value in zip(years,values):items.append(dict(label=label,page=page,year=year,period=str(year)+('-12-31' if instant else '-FY'),value=value,currency=currency,scope='consolidated_CAS'))
    add('营业收入',7,['115393310976.69','125758168916.51','122698004080.99'],(2024,2023,2022))
    add('归属于上市公司股东的净利润',7,['8452859993.18','10428540457.94','9431064679.78'],(2024,2023,2022))
    add('扣除非经常性损益',7,['6011274945.92','10026171076.03','8585692731.44'],(2024,2023,2022))
    add('经营活动产生的现金流量净额',7,['21739740393.38','18290357650.56','13420320580.36'],(2024,2023,2022))
    add('总资产',7,['153718003927.97','151620252657.98','130965302299.22'],(2024,2023,2022),True)
    add('净资产',7,['53179935140.80','53539331413.16','50267883832.15'],(2024,2023,2022),True)
    add('基本每股收益',7,['1.33','1.64','1.48'],(2024,2023,2022),currency='CNY/share')
    add('稀释每股收益',7,['1.33','1.64','1.48'],(2024,2023,2022),currency='CNY/share')
    add('扣除非经常性损益后的基本每股收益',7,['0.95','1.57','1.34'],(2024,2023,2022),currency='CNY/share')
    add('加权平均净资产收益率',7,['15.81','20.20','19.23'],(2024,2023,2022),currency='percent')
    add('扣除非经常性损益后的加权平均净资产收益率',7,['11.24','19.36','17.39'],(2024,2023,2022),currency='percent')
    add('存货',87,['10744674420.37','12511775911.77'],instant=True)
    add('资产总计',87,['153718003927.97','151620252657.98'],instant=True)
    add('负债合计',88,['96710353251.06','94299895215.57'],instant=True)
    add('所有者权益',88,['57007650676.91','57320357442.41'],instant=True)
    add('营业收入',91,['115393310976.69','125758168916.51'])
    add('营业成本',91,['76298833033.93','84788592077.34'])
    add('投资收益',91,['2417330849.26','-31088785.68'])
    add('资产减值损失',91,['-4675845573.44','-1525699477.87'])
    add('营业利润',91,['10181768860.25','11873304166.44'])
    add('净利润',92,['8463710355.65','10284306198.28'])
    add('少数股东损益',92,['10850362.47','-144234259.66'])
    add('经营活动产生的现金流量净额',94,['21739740393.38','18290357650.56'])
    add('购建固定资产',95,['3978318320.96','6955597704.25'])
    add('合计',9,['2441585047.26','402369381.91','845371948.34'],(2024,2023,2022))
    for quarter,value in enumerate(['5922814507.71','1608319620.91','3337346216.72','-2415620352.16'],1):
        items.append(dict(label='归属于上市公司股东的净利润',page=8,year=2024,period=f'2024-Q{quarter}',value=value,currency='CNY',scope='consolidated_CAS'))
    return items


def quality(db_path):
    with sqlite3.connect('file:'+str(db_path)+'?mode=ro',uri=True) as db:
        db.row_factory=sqlite3.Row
        doc=dict(db.execute('SELECT * FROM documents WHERE document_id=?',(DID,)).fetchone())
        facts=[dict(r) for r in db.execute('SELECT * FROM facts WHERE document_id=?',(DID,))]
        tables={r['table_id']:json.loads(r['rows_json']) for r in db.execute('SELECT table_id,rows_json FROM source_tables WHERE document_id=?',(DID,))}
        batches=[json.loads(r[0]) for r in db.execute('SELECT result_json FROM normalization_batches WHERE document_id=?',(DID,))]
    for f in facts:f['source']=json.loads(f.pop('source_json'))
    pdf=fitz.open(ROOT/'data'/doc['relative_path']);checks=[]
    for g in gold():
        # Independent literal transcript of the PDF, not the extracted DB values.
        text=pdf[g['page']-1].get_text().replace(',','').replace('−','-')
        literal=g['value'] in text
        found=[f for f in facts if f['source'].get('page')==g['page'] and Decimal(f['value'])==Decimal(g['value']) and g['label'] in re.sub(r'\s+','',f['source'].get('text',''))]
        exact=[f for f in found if f['period']==g['period'] and f['currency']==g['currency'] and f['scope']==g['scope']]
        checks.append({**g,'pdf_literal_verified':literal,'passed':literal and bool(exact),'found':[{'metric':f['metric'],'period':f['period'],'scope':f['scope'],'currency':f['currency'],'value':f['value'],'cell':f['source'].get('cell')} for f in found]})
    source_errors=[];arithmetic_errors=[];arithmetic_unverified=[]
    for f in facts:
        s=f['source'];rows=tables.get(s.get('table_id'),[]);row=s.get('row',0);column=s.get('column',0)
        if not (0<row<=len(rows) and 0<column<=len(rows[row-1])) or rows[row-1][column-1]!=f['raw_value']:
            source_errors.append({'fact_id':f['fact_id'],'table':s.get('table_id'),'row':row,'column':column})
        meta=s.get('normalization',{});span=meta.get('numeric_span');raw=f['raw_value']
        try:
            if span:
                if raw[span['start']:span['end']]!=span['text']:raise ValueError('span differs from original cell')
                raw=span['text']
            clean=re.sub(r'[,，\s%％]','',raw).replace('−','-').replace('﹣','-').replace('（','(').replace('）',')')
            if clean.startswith('(') and clean.endswith(')'):clean='-'+clean[1:-1]
            value=Decimal(clean)
            if span and span.get('polarity')=='negative':value=-abs(value)
            expected=value*Decimal(meta['scale'])
            if expected!=Decimal(f['value']):arithmetic_errors.append({'fact_id':f['fact_id'],'raw':f['raw_value'],'scale':meta['scale'],'expected':str(expected),'actual':f['value']})
        except (InvalidOperation,KeyError,ValueError):arithmetic_unverified.append(f['fact_id'])
    warnings=[i for b in batches for i in b.get('issues',[])]
    return {'document_state':doc['state'],'page_count':len(pdf),'fact_count':len(facts),'table_count':len(tables),'committed_batches':len(batches),
        'gold_total':len(checks),'gold_passed':sum(c['passed'] for c in checks),'gold_checks':checks,'source_coordinate_errors':source_errors,
        'arithmetic_errors':arithmetic_errors,'arithmetic_unverified':arithmetic_unverified,
        'issues':dict(Counter(i.get('reason','unknown') for i in warnings)),'issue_count':len(warnings),'failed_batches':sum(bool(b.get('repair_error') or b.get('request_error')) for b in batches)}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--metadata',default=str(OUT/'run.json'))
    parser.add_argument('--output-prefix',default='')
    parser.add_argument('--include-run-id',action='append',default=[])
    args=parser.parse_args()
    if args.output_prefix and not re.fullmatch(r'[a-zA-Z0-9_-]+',args.output_prefix):parser.error('output prefix must be a simple name')
    meta=json.loads(Path(args.metadata).read_text(encoding='utf-8'))
    with urllib.request.urlopen(meta['base']+'/api/runs/'+meta['runId'],timeout=20) as response:run=json.load(response)
    with urllib.request.urlopen(meta['base']+'/api/conversations/'+meta['conversation_id'],timeout=20) as response:chat=json.load(response)
    current,events=usage(meta['runId']);baseline,_=usage(meta['original_run_id'])
    related={rid:usage(rid)[0] for rid in dict.fromkeys([*args.include_run_id,meta['runId']])}
    combined={k:sum(record['total'].get(k,0) for record in related.values()) for k in current['total']}
    with sqlite3.connect('file:'+str(ROOT/'data/finance.sqlite')+'?mode=ro',uri=True) as db:
        processing=[json.loads(r[0]) for r in db.execute('SELECT state_json FROM processing_runs WHERE owner_run_id=?',(meta['runId'],))]
    extraction_requests=[e['data'] for e in events if e['type']=='model_request' and e['data'].get('phase')=='extraction']
    main_requests=[e['data'] for e in events if e['type']=='model_request' and e['data'].get('phase')=='main']
    result={'at':datetime.now(timezone.utc).isoformat(),'run':run,'usage':current,'baseline_usage':baseline,'quality':quality(ROOT/'data/finance.sqlite'),
        'related_runs':related,'combined_usage':combined,'processing':processing,
        'request_bounds':{'extraction_calls':len(extraction_requests),'extraction_max_characters':max((r.get('contextCharacters',0) for r in extraction_requests),default=0),'main_max_characters':max((r.get('contextCharacters',0) for r in main_requests),default=0)},
        'request_efforts':dict(Counter(e['data'].get('sentReasoningEffort','off') for e in events if e['type']=='model_request')),
        'price_source':'https://api-docs.deepseek.com/quick_start/pricing/','price_note':'Provider token counts at official Sunday off-peak rates. Estimated model cost, not an account bill; excludes search fees.'}
    (OUT/(args.output_prefix+'acceptance.json')).write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    answers=[m['content'] for m in chat['messages'] if m.get('role')=='assistant']
    (OUT/(args.output_prefix+'answer.md')).write_text(answers[-1] if answers else '',encoding='utf-8')
    short={'run_id':run['id'],'status':run['status'],'stage':run['stage'],'usage':current['total'],'quality':{k:v for k,v in result['quality'].items() if k not in {'gold_checks','source_coordinate_errors','arithmetic_errors','arithmetic_unverified'}}}
    print(json.dumps(short,ensure_ascii=True,indent=2))


if __name__=='__main__':main()
