"""Evaluator-only diagnostic retest; never supplied to the financial agent."""
import csv
import json
import importlib.util
from decimal import Decimal as D
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
TRIAL=ROOT/'data/evaluation/pi-analysis-20261006-followup'
spec=importlib.util.spec_from_file_location('primary_review',ROOT/'scripts/review-analysis-20261006.py')
primary=importlib.util.module_from_spec(spec);spec.loader.exec_module(primary);primary.TRIAL=TRIAL
artifact=primary.artifact;csv_rows=primary.csv_rows;check=primary.check;save=primary.save


def a2():
    rows={r['year']:r for r in csv_rows('A2','yili_forecast_workpaper.csv')};checks=[]
    for column,values in {'revenue_yi':('1193.38','1224.98','1254.38'),'net_profit_yi':('113.09','122.22','131.52'),'eps_yuan':('1.78','1.92','2.07')}.items():
        for year,value in zip(('2025','2026','2027'),values):checks.append(check(column+' '+year,rows[year][column],value))
    save('A2',checks,{'source_institution_and_date':'pass','actual_forecast_separated':'pass','pe_recalculation':'pass','opinion_not_fact':'pass','chart_units':'pass'},
         [{'severity':'material','kind':'overlapping_chart_labels','evidence':'Actual PNG: 33.82 and 35.60 target endpoints overlap and are hard to distinguish; revenue/profit labels also overlap at 2027.'}],
         'Chinese font and correct currency/forecast labels; both axes show correct amounts. Plot has a dual axis and lacks enough label spacing.',
         ['One successful sandbox run, no model correction supplied. Original script and downloads retained.'])


def c2():
    rows={r['年份']:r for r in csv_rows('C2','伊利_预测与估值底稿.csv') if r['年份'] in {'2025','2026','2027'}};checks=[]
    for column,values in {'营业收入（亿元）':('1193.38','1224.98','1254.38'),'归母净利润（亿元）':('113.09','122.22','131.52'),'EPS（元/股）':('1.78','1.92','2.07')}.items():
        for year,value in zip(('2025','2026','2027'),values):checks.append(check(column+' '+year,rows[year][column],value))
    save('C2',checks,{'source_institution_and_date':'pass','actual_forecast_separated':'pass','pe_recalculation':'pass','opinion_not_fact':'pass','answer_requested_values':'9/9','chart_units':'fail','csv_units':'fail','chart_data_matches_image':'fail'},
         [{'severity':'critical','kind':'amount_scale_inconsistency','evidence':'Final chat and Markdown use correct source values, but script rewrites amounts in CNY billions. It plots 119.338 for 2025 revenue then labels 亿元 (correct 1193.38); CSV/chart_data multiply by 100 and label 亿元 (11933.8), instead of the required factor 10. All six requested monetary CSV values are 10x too large; plotted values are 10x too small.'}],
         'Inspected actual PNG: Chinese labels readable and actual/forecast clearly separated; graph, worksheet and answer disagree materially on amount units.',
         ['No finance_charts unit helper used despite availability and guidance. This retest fails the intended delivery correction; do not call it fixed.','One successful sandbox execution does not imply output correctness.'])


def c3():
    model=json.loads(artifact('C3','models.json').read_text(encoding='utf-8'))['model'];spec=model['spec'];rows=model['result']['tables']['forecast'];checks=[]
    for field,values in {'revenue':('119338','122498','125438'),'da':('4822','5316','5724'),'capex':('4500','5000','4000'),'delta_nwc':('5977','99','535')}.items():
        for row,value in zip(rows,values):checks.append(check(field+' '+str(row['year']),row[field],value))
    checks += [check('net debt',spec['bridge']['net_debt'],'24867'),check('NCI',spec['bridge']['non_controlling_interest'],'3828'),check('shares',spec['shares']['count'],'6366')]
    arithmetic=primary.model_math(model)
    save('C3',checks,{'source_inputs':'pass','fcff_reconciliation':'pass','terminal_assumption_explicit_in_report':'pass','target_interval':'pass','calculator_reuse':'pass'},
         [{'severity':'minor','kind':'heatmap_contrast','evidence':'Actual PNG uses dark text on dark green cells and horizontal grid through numbers; values are correct but the darkest cell is hard to read.'}],
         'Inspected both PNGs, CSV, report and script. Correct FCFF and million-CNY scale, correct sensitivity grid and exclusion of 31.36, no unit error or duplicate calculator.',
         ['Terminal ROIC 12% is an explicit steady-state proxy, not an observed perpetual return. Different terminal method from generic baseline legitimately changes valuation.','Two source-citation validation errors and three unsupported-operation calls are preserved and counted. One successful sandbox script reads selected saved model.'])
    target=TRIAL/'judge/C3-review.json';review=json.loads(target.read_text(encoding='utf-8'))
    review['independent_arithmetic']={'passed':sum(x['pass'] for x in arithmetic),'total':len(arithmetic),'checks':arithmetic}
    target.write_text(json.dumps(review,ensure_ascii=False,indent=2),encoding='utf-8')


def a3():
    rows=csv_rows('A3','ili_dcf/forecast_and_fcff.csv');checks=[]
    for key,values in {'revenue_mn':('119338','122498','125438'),'da_mn':('4822','5316','5724'),'capex_mn':('4500','5000','4000'),'nwc_cashflow_mn':('-5977','-99','-535'),'reported_fcff_mn':('6482','13088','14637')}.items():
        checks += [check(key+' '+r['year'],r[key],value) for r,value in zip(rows,values)]
    assumptions={r['parameter']:r['value'] for r in csv_rows('A3','ili_dcf/model_inputs.csv')}
    checks += [check(key,assumptions[key],value) for key,value in [('净债务（百万元）','24867'),('少数股东权益（百万元）','3828'),('股份数（百万股）','6366')]]
    flows=primary.growth_dcf('.079','.018')[0]
    checks += [check('FCFF '+r['year'],r['fcff_mn'],value) for r,value in zip(rows,flows)]
    for r in csv_rows('A3','ili_dcf/sensitivity.csv'):
        checks.append(check('price '+r['WACC']+'/'+r['g'],r['Value_per_share'],primary.growth_dcf(r['WACC'],r['g'])[3]))
    save('A3',checks,{'source_inputs':'pass','fcff_reconciliation':'pass','explicit_terminal_method':'pass','net_debt_and_nci':'pass','target_interval':'pass'},
         [{'severity':'material','kind':'application_nested_download','evidence':'Six real files were produced inside /output/ili_dcf, but the application route rejected encoded subdirectories (HTTP 400). This is an application defect, not a financial-agent advantage; evaluator inspected locally hash-verified outputs.'},
          {'severity':'minor','kind':'heatmap_contrast','evidence':'Dark text on dark blue cells is difficult to read, and the red circle overlaps the base-value text.'}],
         'Actual local PNG has correct sensitivity numbers, units and Chinese font; no source caption on the figure (report cites sources).',
         ['One successful sandbox run, no financial correction. Nested output download repair is outside the frozen comparison and must be reported separately.'])


def a4():
    baseline=primary.growth_dcf('.079','.018');updated=primary.growth_dcf('.084','.018','1.2','1.1');checks=[]
    prefix='ili_dcf_update/'
    for r,old,new in zip(csv_rows('A4',prefix+'annual_fcff_comparison.csv'),baseline[0],updated[0]):
        checks += [check('old FCFF '+r['year'],r['fcff_mn'],old),check('new FCFF '+r['year'],r['fcff_mn_updated'],new),check('change FCFF '+r['year'],r['fcff_change_mn'],new-old)]
    for r,values in zip(csv_rows('A4',prefix+'valuation_results.csv'),(baseline,updated)):
        for key,value in zip(('EV_mn','Equity_value_mn','Value_per_share'),values[1:]):checks.append(check(r['version']+' '+key,r[key],value))
    prices=[baseline[3],primary.growth_dcf('.084','.018')[3],primary.growth_dcf('.084','.018','1.2')[3],updated[3]]
    for i,r in enumerate(csv_rows('A4',prefix+'sequential_attribution.csv')):
        checks += [check(r['步骤'],r['每股价值'],prices[i]),check('contribution '+r['步骤'],r['增量归因'],prices[i]-prices[i-1] if i else 0)]
    for r in csv_rows('A4',prefix+'sensitivity_both_versions.csv'):
        capex,da=('1','1') if r['version']=='旧版' else ('1.2','1.1')
        checks.append(check(r['version']+' '+r['WACC']+'/'+r['g'],r['Value_per_share'],primary.growth_dcf(r['WACC'],r['g'],capex,da)[3]))
    input_rows=csv_rows('A4',prefix+'model_inputs_both.csv');old={(r['年度'],r['输入项']):D(r['数值']) for r in input_rows if r['版本']=='旧版'}
    for r in input_rows:
        if r['版本']!='更新版':continue
        value=old[(r['年度'],r['输入项'])];key=r['输入项']
        expected=value+D('.005') if key=='w' else value*(D('1.2') if key=='capex' else D('1.1') if key=='da' else 1)
        checks.append(check('input '+r['年度']+' '+key,r['数值'],expected))
    save('A4',checks,{'only_requested_changes':'pass','sequence_attribution':'pass','same_absolute_grid':'pass','no_reread':'pass'},
         [{'severity':'material','kind':'application_nested_download','evidence':'Nine final outputs exist in a subdirectory but the application returns HTTP 400; this shared application flaw is not evidence of financial-agent superiority.'},
          {'severity':'material','kind':'mistyped_reply_link','evidence':'The final answer sensitivity_difference.csv link contains a malformed shorter run identifier; the attached artifact itself has the correct identifier.'},
          {'severity':'minor','kind':'heatmap_contrast','evidence':'Black text on darkest blue cells is low contrast; no overlapping colorbar in the final PNG.'}],
         'Inspected local final paired PNG: same absolute grid and shared normalization, values correct, Chinese text readable except low contrast.',
         ['Three analysis requests (two succeeded, one failed because optional tabulate is absent) and two invalid status-ID calls retained. No source reread.'])


def c4():
    models=json.loads(artifact('C4','models.json').read_text(encoding='utf-8'))
    base,new=models['base'],models['scenario'];checks=[]
    for name,model in models.items():
        checks += [{**c,'name':name+' '+c['name']} for c in primary.model_math(model)]
    checks.append(check('WACC change',D(new['spec']['discount']['wacc'])-D(base['spec']['discount']['wacc']),'.005'))
    for left,right in zip(base['result']['tables']['forecast'],new['result']['tables']['forecast']):
        for key in ('revenue','ebit','cash_tax','delta_nwc','da','capex'):
            factor=D('1.1') if key=='da' else D('1.2') if key=='capex' else D(1)
            checks.append(check(str(left['year'])+' '+key,right[key],D(left[key])*factor))
    comparison=json.loads(artifact('C4','comparisons.json').read_text(encoding='utf-8'))['change']
    steps=comparison['decomposition']['steps']
    old,new_value=D(base['result']['results']['value_per_share']),D(new['result']['results']['value_per_share'])
    checks.append(check('attribution sum',sum(D(s['contribution']) for s in steps),new_value-old))
    expected=['discount.wacc',*[f'forecast.{i}.capex' for i in range(3)],*[f'forecast.{i}.da' for i in range(3)]]
    checks += [
        {'name':'same absolute grid','actual':new['spec']['sensitivity'],'expected':base['spec']['sensitivity'],'pass':new['spec']['sensitivity']==base['spec']['sensitivity']},
        {'name':'ordered attribution','actual':[s['path'] for s in steps],'expected':expected,'pass':[s['path'] for s in steps]==expected},
        {'name':'only seven numerical inputs changed','actual':sorted(c['path'] for c in comparison['changed_inputs']),'expected':sorted(expected),'pass':sorted(c['path'] for c in comparison['changed_inputs'])==sorted(expected)},
    ]
    for r,left,right in zip(csv_rows('C4','伊利_DCF_FCFF变化.csv'),base['result']['tables']['forecast'],new['result']['tables']['forecast']):
        checks += [check('CSV baseline FCFF '+str(left['year']),r['baseline_fcff_CNY_mn'],left['fcff']),
                   check('CSV updated FCFF '+str(left['year']),r['scenario_fcff_CNY_mn'],right['fcff']),
                   check('CSV FCFF change '+str(left['year']),r['change_CNY_mn'],D(right['fcff'])-D(left['fcff']))]
    save('C4',checks,{'source_inputs':'inherited_C3_pass','relative_update_math':'pass','same_absolute_grid':'pass','sequence_attribution':'pass','no_reread':'pass','calculator_reuse':'pass','report_matches_model':'pass'},
         [{'severity':'minor','kind':'heatmap_contrast','evidence':'Actual paired PNG has dark text on the darkest green cells and horizontal grid lines through some labels. Colorbar is outside the charts; no overlap.'},
          {'severity':'minor','kind':'redundant_csv_name','evidence':'The extra file 伊利_DCF两版逐年预测输入结果.csv contains baseline rows only despite its name. Both complete versions are separately delivered in base/scenario input and forecast CSVs and models.json.'}],
         'Inspected final PNG, script, report and CSV: same absolute grid and normalization, correct units and numbers. One sandbox execution directly reads saved model revisions and comparison.',
         ['A correct update under an explicit ROIC terminal method need not match the generic baseline last-FCFF-growth valuation.','Remaining chart contrast and redundant-file labeling issues are retained; no claim of perfect delivery.'])


if __name__=='__main__':
    if (TRIAL/'A2-deliverables.json').exists():a2()
    if (TRIAL/'C2-deliverables.json').exists():c2()
    if (TRIAL/'C3-deliverables.json').exists():c3()
    if (TRIAL/'A3-deliverables.json').exists():a3()
    if (TRIAL/'A4-deliverables.json').exists():a4()
    if (TRIAL/'C4-deliverables.json').exists():c4()
