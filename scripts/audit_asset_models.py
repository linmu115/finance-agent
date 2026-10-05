"""Read saved live models, independently recalculate their results, never mutate the app."""
import json
from copy import deepcopy
from decimal import Decimal, getcontext
from pathlib import Path
from urllib.request import urlopen

getcontext().prec = 40
ROOT = Path(__file__).resolve().parents[1] / 'data/acceptance/asset-dashboard'
project = json.loads((ROOT/'manifest.json').read_text(encoding='utf-8'))['project']['id']
base = f'http://127.0.0.1:3001/api/projects/{project}/research'
def get(path):
    with urlopen(base+path, timeout=30) as response:
        return json.load(response)
def dec(value):
    return Decimal(str(value))
artifacts = [get('/artifacts/'+item['id']) for item in get('/artifacts')['artifacts']]
(ROOT/'saved-models.json').write_text(json.dumps(artifacts,ensure_ascii=False,indent=2),encoding='utf-8')
checks = []
def equal(name, actual, expected, tolerance='0.00000001'):
    checks.append({'name':name,'actual':actual,'expected':str(expected),
                   'ok':actual is not None and abs(dec(actual)-dec(expected))<=dec(tolerance)})
def condition(name, ok, detail=None):
    checks.append({'name':name,'ok':bool(ok),'detail':detail})

dcfs = [a for a in artifacts if a['kind']=='dcf']
quality = [a for a in artifacts if a['kind']=='financial_quality']
condition('two_saved_dcf_scenarios',len(dcfs)>=2)
condition('saved_quality_model',len(quality)>=1)
for a in dcfs:
    s=a['spec']; result=a['result']; prefix=a['title']; wacc=dec(s['discount']['wacc'])
    previous_sales=dec(s['base']['revenue']); previous_nwc=dec(s['base']['net_working_capital']); present_value=Decimal(0)
    for i,f in enumerate(s['forecast'],1):
        revenue=dec(f['revenue']) if 'revenue' in f else previous_sales*(1+dec(f['revenue_growth']))
        ebit=dec(f['ebit']) if 'ebit' in f else revenue*dec(f['ebit_margin']) if 'ebit_margin' in f else revenue*(dec(f['gross_margin'])-dec(f['opex_ratio']))
        tax=(max(Decimal(0),ebit) if s['cash_tax_policy']=='floor_at_zero' else ebit)*dec(f['tax_rate'])
        def amount(name,ratio):
            return dec(f[name]) if name in f else revenue*dec(f[ratio])
        nwc=amount('net_working_capital','nwc_ratio')
        fcff=ebit-tax+amount('da','da_ratio')-amount('capex','capex_ratio')-(nwc-previous_nwc)
        exponent=dec(i) if s['discount']['cashflow_timing']=='year_end' else dec(i)-dec('0.5')
        pv=fcff/(1+wacc)**exponent
        stored=result['tables']['forecast'][i-1]
        equal(prefix+f'.{f["year"]}.fcff',stored['fcff'],fcff)
        equal(prefix+f'.{f["year"]}.pv',stored['pv_fcff'],pv)
        present_value+=pv;previous_sales=revenue;previous_nwc=nwc
    t=s['terminal']; growth=dec(t['growth'])
    terminal_cf=previous_sales*(1+growth)*dec(t['ebit_margin'])*(1-dec(t['tax_rate']))*(1-growth/dec(t['roic']))
    enterprise=present_value+terminal_cf/(wacc-growth)/(1+wacc)**len(s['forecast'])
    b=s['bridge'];equity=enterprise-dec(b['net_debt'])-dec(b['non_controlling_interest'])-dec(b['preferred_equity'])+dec(b['non_operating_assets_ex_cash'])
    price=equity*dec(s['amount_scale'])/dec(s['shares']['count'])/dec(s['shares']['scale'])
    for field,expected in [('enterprise_value',enterprise),('equity_value',equity),('value_per_share',price)]:
        equal(prefix+'.'+field,result['results'][field],expected)
    condition(prefix+'.source_locations_checked',a.get('source_validation',{}).get('mode')=='checked')
    condition(prefix+'.explicit_wacc_assumption',s.get('input_basis',{}).get('discount.wacc',{}).get('basis')=='assumption')
    condition(prefix+'.source_references_present',bool(s.get('source_refs')))
    for parameter in ('terminal.ebit_margin','terminal.tax_rate'):
        condition(prefix+'.'+parameter+'.classified_as_assumption',s.get('input_basis',{}).get(parameter,{}).get('basis')=='assumption')
    for i,period in enumerate([2025,2026,2027]):
        f=s['forecast'][i]
        equal(prefix+f'.{period}.original_pdf_revenue',f.get('revenue'),[119338,122498,125438][i])
        equal(prefix+f'.{period}.original_pdf_da',f.get('da'),[4822,5316,5724][i])
        equal(prefix+f'.{period}.original_pdf_capex',f.get('capex'),[4500,5000,4000][i])
        expected_ebit=dec([119338,122498,125438][i])-dec([77658,79519,81158][i])-dec([755,775,794][i])-dec([21942,22252,22754][i])-dec([4368,4479,4582][i])-dec([776,796,815][i])
        equal(prefix+f'.{period}.operating_ebit_components',f.get('ebit'),expected_ebit)
if len(dcfs)==2:
    low,high=sorted(dcfs,key=lambda a:dec(a['spec']['discount']['wacc']))
    a,b=deepcopy(low['spec']),deepcopy(high['spec'])
    for s in [a,b]:
        s['discount'].pop('wacc')
        s.pop('input_basis',None);s.pop('source_refs',None)
    condition('only_wacc_changes_in_stress_inputs',a==b)
    condition('higher_wacc_reduces_value',dec(high['result']['results']['value_per_share'])<dec(low['result']['results']['value_per_share']))
for a in quality:
    s=a['spec'];rows=a['result']['tables']['quality'];scale=dec(s['amount_scale'])
    condition('quality_preserves_H1',s['period_basis']=='H1')
    expected={2024:('181011000','-38635000','-32104000',182),2025:('120392000','41098000','-30650000',181)}
    for row in rows:
        year=int(row['year']);revenue,profit,cfo,days=expected[year]
        for name,value in [('revenue',revenue),('net_income',profit),('cfo',cfo)]:
            equal(f'quality.{year}.{name}.original_pdf',dec(row[name])*scale,value)
        equal(f'quality.{year}.days',row['days'],days)
        equal(f'quality.{year}.cash_profit_gap',dec(row['cash_profit_gap'])*scale,dec(cfo)-dec(profit))
        equal(f'quality.{year}.cfo_margin',row['cfo_margin'],dec(cfo)/dec(revenue))
        if year==2025:equal('quality.2025.revenue_yoy',row['revenue_yoy'],dec(revenue)/dec('181011000')-1)
        condition(f'quality.{year}.no_pretax_gain_as_recurring_net',row.get('recurring_net_income') is None)
    condition('quality.source_references_present',bool(s.get('source_refs')))
    condition('quality.operating_anchor_excludes_finance',s.get('profit_bridge',{}).get('finance_expense_treatment')=='excluded')
    for bridge in a['result']['tables']['attribution']:
        equal('quality.complete_profit_bridge_reconciles',bridge.get('reported_operating_profit_residual'),0)
output={'checks':checks,'passed':sum(c['ok'] for c in checks),'total':len(checks),
        'models':[{'id':a['id'],'title':a['title'],'kind':a['kind'],'results':a['result']['results']} for a in artifacts if a.get('result')],
        'scope':'Recalculates saved model arithmetic independently and checks selected inputs against original PDFs. Assumptions and source economic meaning still require substantive review.'}
(ROOT/'model-audit.json').write_text(json.dumps(output,ensure_ascii=False,indent=2,default=str),encoding='utf-8')
print(json.dumps({'passed':output['passed'],'total':output['total'],'failures':[c for c in checks if not c['ok']]},ensure_ascii=False,default=str))
