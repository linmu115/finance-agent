"""Independent evaluator arithmetic; never imports or executes generated scripts."""
import csv
import json
from decimal import Decimal as D, getcontext
from pathlib import Path

getcontext().prec = 50
ROOT = Path(__file__).resolve().parents[1]
TRIAL = ROOT / 'data/evaluation/pi-analysis-20261005-cpa'
JUDGE = TRIAL / 'judge'

def rows(label, name):
    manifest = json.loads((TRIAL / f'{label}-deliverables.json').read_text(encoding='utf-8'))
    artifact = next(a for a in manifest['artifacts'] if a['name'] == name)
    with (TRIAL / f'{label}-artifacts' / artifact['localFile']).open(encoding='utf-8-sig') as f:
        return list(csv.DictReader(f))

revenue = list(map(D, ['119338', '122498', '125438']))
margins = list(map(D, ['.116', '.12', '.122']))
da = list(map(D, ['4822', '5316', '5724']))
capex = list(map(D, ['4500', '5000', '4000']))
nwc = list(map(D, ['5977', '99', '535']))
def fcff(cap_multiplier='1', da_multiplier='1'):
    return [r*m*D('.877')+a*D(da_multiplier)-c*D(cap_multiplier)-n
            for r, m, a, c, n in zip(revenue, margins, da, capex, nwc)]

def value(w, g, cap_multiplier='1', da_multiplier='1', normalized=False):
    w, g = D(w), D(g)
    f = fcff(cap_multiplier, da_multiplier)
    terminal = (revenue[-1]*(1+g)*margins[-1]*D('.877')*(1-g/D('.10'))
                if normalized else f[-1]*(1+g))
    ev = sum(v/(1+w)**(i+1) for i, v in enumerate(f)) + terminal/(w-g)/(1+w)**3
    eq = ev-D('24867')-D('3828')
    return {'EV': ev, 'equity': eq, 'per_share': eq/D('6366')}

def check(checks, name, actual, expected):
    difference = D(str(actual))-D(str(expected))
    checks.append({'name': name, 'pass': abs(difference)<D('0.00000001'),
                   'difference': str(difference)})

def save(label, checks, **extra):
    result = {'passed': sum(x['pass'] for x in checks), 'total': len(checks),
              'checks': checks, 'method': 'Evaluator Decimal recomputation from declared source inputs; no generated code executed on host.', **extra}
    (JUDGE / f'{label}-independent-recalculation.json').write_text(json.dumps(result, indent=2, ensure_ascii=False)+'\n', encoding='utf-8')
    print(label, result['passed'], '/', result['total'])

checks=[]
for i, r in enumerate(rows('B3', '伊利_DCF_输入与FCFF.csv')):
    check(checks, f'FCFF_{r["year"]}', r['FCFF_calculated_mn'], fcff()[i])
for r in rows('B3', '伊利_DCF_敏感性.csv'):
    v=value(D(r['WACC_pct'])/100, D(r['g_pct'])/100)
    check(checks, f'grid_{r["WACC_pct"]}_{r["g_pct"]}', r['value_per_share_RMB'], v['per_share'])
r=rows('B3', '伊利_DCF_估值摘要.csv')[0]
for k, field in [('EV','EV_mn'), ('equity','equity_value_mn'), ('per_share','value_per_share_RMB')]:
    check(checks, k, r[field], value('.079','.018')[k])
save('B3', checks)

for label in ['A4','B4']:
    checks=[]
    values=[value('.079','.018'),value('.084','.018'),value('.084','.018','1.2'),value('.084','.018','1.2','1.1')]
    stages=[v['per_share'] for v in values]
    if label=='A4':
        forecasts=rows(label,'new_fcff.csv')
        for i,r in enumerate(forecasts):
            check(checks, f'FCFF_{r["year"]}',r['FCFF'],fcff('1.2','1.1')[i])
        attributed=rows(label,'sequential_attribution.csv')
        for i,r in enumerate(attributed):
            check(checks,f'stage_{i}',r['value_per_share'],stages[i])
            if i: check(checks,f'effect_{i}',r['increment_vs_previous'],stages[i]-stages[i-1])
        for filename, expected in [('old_results.csv', values[0]),('new_results.csv', values[-1])]:
            r=rows(label,filename)[0]
            for k,field in [('EV','EV'),('equity','equity_value'),('per_share','value_per_share')]:
                check(checks,filename+'_'+k,r[field],expected[k])
        for r in rows(label,'sensitivity_comparison.csv'):
            for field,c,a in [('old_value_per_share','1','1'),('new_value_per_share','1.2','1.1')]:
                check(checks,f'{field}_{r["WACC"]}_{r["g"]}',r[field],value(r['WACC'],r['g'],c,a)['per_share'])
        old,new=rows(label,'old_inputs.csv'),rows(label,'new_inputs.csv')
        constant=['revenue','EBIT_margin','tax_rate','working_capital_cashflow','g','net_debt','minority_interest','shares_m']
        controlled=all(D(n[k])==D(o[k]) for o,n in zip(old,new) for k in constant)
        controlled=controlled and all(D(n['WACC'])==D('.084') and abs(D(n['DA'])-D(o['DA'])*D('1.1'))<D('1e-8') and D(n['capex'])==D(o['capex'])*D('1.2') for o,n in zip(old,new))
    else:
        forecasts=rows(label,'伊利_DCF_两版输入与FCFF.csv')
        for i,r in enumerate(forecasts):
            check(checks,f'FCFF_{r["year"]}',r['FCFF_new_mn'],fcff('1.2','1.1')[i])
        stage_rows=rows(label,'伊利_DCF_两版估值结果.csv')
        for i,r in enumerate(stage_rows):
            check(checks,f'stage_{i}',r['value_per_share_RMB'],stages[i])
            if i in [0,3]:
                for k,field in [('EV','EV_mn'),('equity','equity_value_mn'),('per_share','value_per_share_RMB')]:
                    check(checks,f'stage_{i}_{k}',r[field],values[i][k])
        for i,r in enumerate(rows(label,'伊利_DCF_顺序归因.csv')):
            check(checks,f'effect_{i+1}',r['归因差额_元股'],stages[i+1]-stages[i])
        for r in rows(label,'伊利_DCF_两版敏感性.csv'):
            c,a=('1','1') if r['version']=='旧版' else ('1.2','1.1')
            check(checks,f'{r["version"]}_{r["WACC_pct"]}_{r["g_pct"]}',r['value_per_share_RMB'],value(D(r['WACC_pct'])/100,D(r['g_pct'])/100,c,a)['per_share'])
        controlled=all(D(r['revenue_mn'])==revenue[i] and D(r['EBIT_margin_pct'])/100==margins[i] and D(r['tax_rate_pct'])==D('12.3') and D(r['change_NWC_cashflow_mn'])==-nwc[i] and abs(D(r['D&A_new_mn'])-da[i]*D('1.1'))<D('1e-8') and D(r['capex_new_mn'])==capex[i]*D('1.2') for i,r in enumerate(forecasts))
        controlled=controlled and all(D(r['net_debt_mn'])==24867 and D(r['minority_interest_mn'])==3828 and D(r['shares_mn'])==6366 and abs(D(r['g_pct'])-D('1.8'))<D('1e-8') for r in stage_rows)
    save(label,checks,only_requested_parameters_changed=controlled,
         expected_stage_values=list(map(str,stages)),
         expected_ordered_effects=[str(stages[i+1]-stages[i]) for i in range(3)],
         terminal_method_preserved='last forecast FCFF times 1+g')

c4_path=JUDGE/'C4-model-tool-results.json'
if c4_path.exists():
    model=json.loads(c4_path.read_text(encoding='utf-8'))
    prior=json.loads((JUDGE/'C3-model-tool-results.json').read_text(encoding='utf-8'))[-1]['data']['result']['data']
    comparison=json.loads((JUDGE/'C4-comparison-tool-results.json').read_text(encoding='utf-8'))
    checks=[]
    expected=[value('.079','.018',normalized=True),value('.084','.018',normalized=True),
              value('.084','.018','1.2',normalized=True),value('.084','.018','1.2','1.1',normalized=True)]
    for i,r in enumerate(model['result']['tables']['forecast']):
        check(checks,f'FCFF_{r["year"]}',r['fcff'],fcff('1.2','1.1')[i])
    for tag,result,ref in [('old',prior['result'],expected[0]),('new',model['result'],expected[-1])]:
        for k,f in [('EV','enterprise_value'),('equity','equity_value'),('per_share','value_per_share')]:
            check(checks,tag+'_'+k,result['results'][f],ref[k])
        for r in result['tables']['sensitivity']:
            c,a=('1','1') if tag=='old' else ('1.2','1.1')
            check(checks,f'{tag}_grid_{r["wacc"]}_{r["growth"]}',r['value_per_share'],value(r['wacc'],r['growth'],c,a,True)['per_share'])
    steps=comparison['decomposition']['steps']
    for i,j in enumerate([None,0,3,6]):
        actual=steps[0]['per_share_before'] if j is None else steps[j]['per_share_after']
        check(checks,f'stage_{i}',actual,expected[i]['per_share'])
    for i,(start,end) in enumerate([(0,1),(1,4),(4,7)]):
        check(checks,f'effect_{i+1}',sum(D(s['contribution']) for s in steps[start:end]),expected[i+1]['per_share']-expected[i]['per_share'])
    old_spec,new_spec=prior['spec'],model['spec']
    expected_spec=json.loads(json.dumps(old_spec))
    expected_spec['discount']['wacc']='0.084'
    for row in expected_spec['forecast']:
        row['capex']=str(D(row['capex'])*D('1.2')).rstrip('0').rstrip('.')
        row['da']=str(D(row['da'])*D('1.1')).rstrip('0').rstrip('.')
    def numeric_tree(x):
        if isinstance(x,dict):return {k:numeric_tree(v) for k,v in x.items() if k not in ['input_basis','source_refs']}
        if isinstance(x,list):return [numeric_tree(v) for v in x]
        if isinstance(x,str):
            try:return D(x)
            except ArithmeticError:return x
        return x
    save('C4',checks,only_requested_parameters_changed=numeric_tree(expected_spec)==numeric_tree(new_spec),
         source_model_is_own_prior=model['source_model']['artifact_id']==prior['id'],
         terminal_method_preserved='2028 normalized NOPAT times 1-g/ROIC',
         expected_stage_values=[str(v['per_share']) for v in expected])
