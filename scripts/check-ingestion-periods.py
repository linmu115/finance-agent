"""Source acceptance: expected literals transcribed from rendered PDF pages."""
import argparse
from collections import Counter
from decimal import Decimal
import json
from pathlib import Path
import re
import fitz

# Page, metric, 2024 value, 2023 value. Q3 PDF pp7-10 and 13 were visually
# reviewed: all five tables/continuations belong to January-September.
SAMPLES=[
 (7,'total_operating_revenue','89,039,388,538.88','97,404,475,913.37'),
 (7,'revenue','88,732,934,445.43','97,090,826,912.59'),
 (7,'total_operating_cost','78,861,832,375.69','87,019,341,810.84'),
 (8,'income_tax_expense','1,606,949,379.21','1,547,744,049.58'),
 (8,'net_profit','10,896,767,162.20','9,370,223,499.38'),
 (8,'net_profit_parent','10,868,480,345.34','9,380,094,922.17'),
 (9,'cash_received_from_sales','94,743,756,737.74','101,735,054,498.37'),
 (9,'taxes_paid','5,224,476,083.67','4,973,427,798.65'),
 (9,'operating_cash_flow','13,869,612,283.42','11,708,284,111.40'),
 (10,'investing_cash_flow','-5,076,062,812.82','-12,545,592,646.38'),
 (10,'financing_cash_flow','-5,345,393,020.73','13,078,932,528.98'),
 (10,'net_change_in_cash','3,430,938,490.76','12,350,793,534.99'),
 (13,'revenue','79,392,045,094.85','87,270,752,369.55'),
 (13,'cost_of_revenue','57,218,992,736.61','64,471,448,355.88'),
 (13,'net_profit','10,749,764,397.35','7,934,479,462.06'),
]


def key(f):
    ref=json.loads(f['source_json'])
    return (ref['table_id'],ref['row'],ref['column'],f['metric'],f['value'])


def main():
    p=argparse.ArgumentParser();p.add_argument('replay');p.add_argument('pdf');a=p.parse_args()
    root=Path(a.replay);folder=root/'q3'
    read=lambda name:json.loads((folder/name).read_text(encoding='utf-8'))
    before=read('before-facts.json');after=read('after-facts.json');parsed=read('parsed.json')
    by={key(f):f for f in after};assert len(before)==len(after)==610
    assert all(key(f) in by for f in before)
    changes=[(f,by[key(f)]) for f in before if f['period']!=by[key(f)]['period']]
    assert len(changes)==211
    assert Counter((x['period'],y['period']) for x,y in changes)=={('2024-FY','2024-9M'):105,('2023-FY','2023-9M'):106}
    samples=[]
    with fitz.open(a.pdf) as pdf:
        for page,metric,current,previous in SAMPLES:
            for year,raw in [(2024,current),(2023,previous)]:
                candidates=[f for f in after if json.loads(f['source_json'])['page']==page and f['metric']==metric and f['period']==f'{year}-9M']
                assert len(candidates)==1,(page,metric,year)
                f=candidates[0];ref=json.loads(f['source_json']);meta=ref['normalization']
                assert Decimal(f['value'])==Decimal(raw.replace(',','')),(page,metric,year,raw,f['value'])
                assert raw in re.sub(r'\s+','',pdf[page-1].get_text())
                assert meta['period_start']==f'{year}-01-01' and meta['period_end']==f'{year}-09-30'
                samples.append({'page':page,'metric':metric,'period':f['period'],'scope':f['scope'],
                                'table_id':ref['table_id'],'row':ref['row'],'column':ref['column'],
                                'expected_literal':raw,'value':f['value'],'start':meta['period_start'],
                                'end':meta['period_end'],'source_match':True})
    tables={t['index']:t for t in parsed['tables']}
    for f in after:
        ref=json.loads(f['source_json']);table=tables[int(ref['table_id'].split(':t')[-1])]
        assert table['rows'][ref['row']-1][ref['column']-1]==f['raw_value']
    report={'model_calls':0,'input_tokens':0,'output_tokens':0,'facts_before':610,'facts_after':610,
            'corrected_periods':211,'unchanged_periods':399,'changes':{'2024-FY -> 2024-9M':105,'2023-FY -> 2023-9M':106},
            'source_review':{'passed':len(samples),'total':len(samples),'samples':samples},'raw_cell_replay':{'passed':610,'total':610}}
    (root/'period-acceptance.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in report.items() if k!='source_review'}|{'source_review_passed':len(samples)},ensure_ascii=False))


if __name__=='__main__':main()
