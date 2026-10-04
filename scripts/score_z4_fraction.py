"""Independent rational upside model, JSON/CSV export and incremental reference.

No production imports. Expected values derive only from frozen declared economic
assumptions; observed application results never supply an expected amount.
"""
import argparse
import csv
import hashlib
import json
from decimal import Decimal, localcontext
from fractions import Fraction as F
from pathlib import Path

p=argparse.ArgumentParser();p.add_argument('--report',required=True,type=Path);p.add_argument('--frozen',required=True,type=Path);p.add_argument('--output',required=True,type=Path);a=p.parse_args()
source=a.report.read_bytes();report=json.loads(source);assumptions=json.loads(a.frozen.read_text(encoding='utf8'))['assumptions'];checks=[]
shock={**assumptions['scenario'],'material_cost_changes':['-0.2']*len(assumptions['baseline'])}

def check(name,actual,expected):
    with localcontext() as context:
        context.prec=70
        reference=Decimal(expected.numerator)/Decimal(expected.denominator)
        try:error=abs(Decimal(str(actual))-reference);passed=error<=Decimal('1e-40')
        except Exception:error=None;passed=False
    checks.append({'name':name,'actual':str(actual),'reference_fraction':str(expected),'reference_decimal':str(reference),'absolute_error':str(error),'passed':passed})

def forecast(apply):
    previous=F(assumptions['base']['net_working_capital']);rows=[];drivers=[]
    for i,row in enumerate(assumptions['baseline']):
        change=F(row['material_cost_per_unit'])*F(shock['exposed_material_share'])*F(shock['material_cost_changes'][i]) if apply else F(0)
        lag=i-shock['lag_years']
        passed=F(assumptions['baseline'][lag]['material_cost_per_unit'])*F(shock['exposed_material_share'])*F(shock['material_cost_changes'][lag])*F(shock['pass_through_rate']) if apply and lag>=0 else F(0)
        price=F(row['unit_price'])+passed
        volume=F(row['volume'])*(1+F(shock['price_elasticity'])*(price/F(row['unit_price'])-1)) if apply else F(row['volume'])
        revenue=volume*price
        ebit=revenue-volume*(F(row['material_cost_per_unit'])+change+F(row['other_variable_cost_per_unit']))-F(row['fixed_cash_opex'])-F(row['da'])
        tax=max(F(0),ebit*F(row['tax_rate']));nwc=revenue*F(row['nwc_ratio'])
        fcff=ebit-tax+F(row['da'])-F(row['capex'])-(nwc-previous)
        rows.append({'year':F(row['year']),'revenue':revenue,'ebit':ebit,'cash_tax':tax,'nopat':ebit-tax,'fcff':fcff,'net_working_capital':nwc,'delta_nwc':nwc-previous});previous=nwc
        drivers.append({'scenario_volume':volume,'scenario_unit_price':price,'price_pass_through_per_unit':passed,'exposed_material_cost_change_per_unit':change})
    return rows,drivers

def value(rows,wacc,growth):
    terminal=assumptions['dcf']['terminal'];tr=rows[-1]['revenue']*(1+growth);nopat=tr*F(terminal['ebit_margin'])*(1-F(terminal['tax_rate']));reinvest=nopat*growth/F(terminal['roic']);fcff=nopat-reinvest;tv=fcff/(wacc-growth)
    pv=sum(row['fcff']/(1+wacc)**i for i,row in enumerate(rows,1));tpv=tv/(1+wacc)**len(rows);ev=pv+tpv;b=assumptions['dcf']['bridge'];equity=ev-F(b['net_debt'])-F(b['non_controlling_interest'])-F(b['preferred_equity'])+F(b['non_operating_assets_ex_cash']);shares=F(assumptions['dcf']['shares']['count'])*F(assumptions['dcf']['shares']['scale'])
    return {'enterprise_value':ev,'equity_value':equity,'value_per_share':equity/shares,'explicit_forecast_pv':pv,'terminal_value':tv,'terminal_pv':tpv,'terminal_revenue':tr,'terminal_nopat':nopat,'terminal_reinvestment':reinvest,'terminal_fcff':fcff}

baseline,_=forecast(False);upside,drivers=forecast(True)
scenario=report['artifacts']['scenario'];dcf=report['artifacts']['dcf'];edited=report['edited_scenario']
for label,rows in [('baseline',baseline),('scenario',upside)]:
    for i,row in enumerate(rows):
        for key,number in row.items():check(f'{label}.forecast.{i}.{key}',scenario['result']['tables'][label+'_forecast'][i][key],number)
    for artifact,wacc,prefix in [(scenario,F('0.1'),'initial'),(edited,F('0.11'),'edited')]:
        for key,number in value(rows,wacc,F('0.02')).items():check(f'{prefix}.{label}.valuation.{key}',artifact['result']['results'][label+'_valuation'][key],number)
for i,row in enumerate(drivers):
    for key,number in row.items():check(f'upside.drivers.{i}.{key}',scenario['result']['tables']['scenario'][i][key],number)
for i,row in enumerate(upside):
    for key,number in row.items():check(f'dcf.forecast.{i}.{key}',dcf['result']['tables']['forecast'][i][key],number)
for key,number in value(upside,F('0.1'),F('0.02')).items():check(f'dcf.valuation.{key}',dcf['result']['results'][key],number)
for i,cell in enumerate(dcf['result']['tables']['sensitivity']):
    for key in ('enterprise_value','equity_value','value_per_share'):check(f'dcf.sensitivity.{i}.{key}',cell[key],value(upside,F(cell['wacc']),F(cell['growth']))[key])
with Path(report['exports']['csv']).open(encoding='utf-8-sig',newline='') as stream:csv_rows=list(csv.DictReader(stream))
export=json.loads(Path(report['exports']['json']).read_text(encoding='utf8'))
if len(csv_rows)!=len(upside):checks.append({'name':'csv_full_row_count','passed':False,'actual':len(csv_rows),'expected':len(upside)})
for i,row in enumerate(upside):
    for key,number in row.items():
        check(f'csv_export.{i}.{key}',csv_rows[i].get(key) if i<len(csv_rows) else None,number)
        check(f'json_export.{i}.{key}',export['result']['tables']['forecast'][i][key],number)
for label,actual in [('cost_down_ebit',upside[0]['ebit']>baseline[0]['ebit']),('lag_zero_first_year_price_change',drivers[0]['price_pass_through_per_unit']==0),('next_year_price_decrease',drivers[1]['price_pass_through_per_unit']<0),('elastic_volume_increase',drivers[1]['scenario_volume']>F(assumptions['baseline'][1]['volume'])),('higher_wacc_lower_equity',value(upside,F('0.11'),F('0.02'))['equity_value']<value(upside,F('0.1'),F('0.02'))['equity_value'])]:checks.append({'name':label,'passed':actual})
result={'kind':'independent_fraction_z4_upside','status':'passed' if all(c['passed'] for c in checks) else 'failed','model_calls':0,'production_imports':False,'financial_source_accuracy_claim':False,'tolerance':'1e-40','passed':sum(c['passed'] for c in checks),'total':len(checks),'inputs':{'frozen_path':str(a.frozen),'frozen_sha256':hashlib.sha256(a.frozen.read_bytes()).hexdigest(),'only_economic_change':{'material_cost_changes':shock['material_cost_changes']}},'checks':checks,'hand_check_first_year':{'baseline_ebit':str(baseline[0]['ebit']),'upside_ebit':str(upside[0]['ebit']),'upside_fcff':str(upside[0]['fcff'])},'upside_equity_fraction':str(value(upside,F('0.1'),F('0.02'))['equity_value']),'limitations':'Synthetic declared assumptions only; exact arithmetic does not establish real-company semantic extraction, evidence interpretation, or investment validity.'}
with a.output.open('x',encoding='utf8') as stream:json.dump(result,stream,ensure_ascii=False,indent=2)
print(json.dumps({'status':result['status'],'passed':result['passed'],'total':result['total']}))
