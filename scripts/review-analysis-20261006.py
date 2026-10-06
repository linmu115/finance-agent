"""Evaluator-only records for the frozen development comparison.

Numbers are checked against the pre-existing source reference; qualitative
findings are recorded after inspecting the actual answer, files and plot pixels.
Never mounted into the application or passed to either agent arm.
"""
import csv
import json
from decimal import Decimal as D
from pathlib import Path
TRIAL=Path(__file__).resolve().parents[1]/'data/evaluation/pi-analysis-20261006'


def save(label,checks,finance,issues,chart_review,notes=None):
    result={'label':label,'core_numeric':{'passed':sum(c['pass'] for c in checks),'total':len(checks),'checks':checks},
            'finance_checks':finance,'issues':issues,'chart_review':chart_review,'limitations':notes or ['Development sample; numerical checks do not establish whole-document accuracy.']}
    (TRIAL/'judge'/f'{label}-review.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')


def a1():
    with (TRIAL/'A1-artifacts/瑞和_业绩对照.csv').open(encoding='utf-8-sig') as f:rows={r['指标']:r for r in csv.DictReader(f)}
    expected={'收入':('181011','120392'),'毛利率':(str(D(14577)/181011*100),str(D(9111)/120392*100)),
              '经营利润（亏损）':('-32320','-18170'),'合并净利润（亏损）':('-38635','41098'),'经营活动现金流净额':('-32104','-30650')}
    checks=[{'name':name+' '+period,'actual':rows[name][period],'expected':value,'pass':abs(D(rows[name][period])-D(value))<D('0.0000001')}
            for name,values in expected.items() for period,value in zip(('2024H1','2025H1'),values)]
    save('A1',checks,{'noncash_gain_not_operating_improvement':'pass','net_profit_cfo_scope':'pass','cashflow_residual_explicit':'pass','finance_expense_double_count':'not_present','chart_units':'pass'},
         [{'severity':'material','kind':'chart_chinese_glyphs','evidence':'Actual final PNG has missing-glyph boxes for all Chinese titles and labels. Script overwrites shared font.sans-serif defaults with SC/SimHei/YaHei names not installed, excluding the available Noto Sans CJK JP.'}],
         'Inspected final PNG. Bar magnitudes and currency-million units match the CSV, but Chinese text is unreadable. Source/period text also affected.',
         ['No full cash-flow reconciliation supplied; the -8.732 million residual is explicitly unidentified, not a fabricated source item.','Original executed script is delivered; separately named recompute script produces a simpler chart, not the same layout.'])


def b1():
    with (TRIAL/'B1-artifacts/对比底稿.csv').open(encoding='utf-8-sig') as f:rows={r['指标']:r for r in csv.DictReader(f)}
    expected={'Revenue':('181.011','120.392'),'毛利率':(str(D(14577)/181011*100),str(D(9111)/120392*100)),
              'Operating profit/(loss)':('-32.320','-18.170'),'Net profit/(loss)':('-38.635','41.098'),'Operating cash flow':('-32.104','-30.650')}
    checks=[{'name':name+' '+period,'actual':rows[name][period+'_RMB百万元'],'expected':value,'pass':abs(D(rows[name][period+'_RMB百万元'])-D(value))<D('0.0000001')}
            for name,values in expected.items() for period,value in zip(('2024H1','2025H1'),values)]
    save('B1',checks,{'noncash_gain_not_operating_improvement':'pass','net_profit_cfo_scope':'pass','cashflow_residual_explicit':'pass','source_non_cash_adjustments':'pass','explanation_units':'fail'},
         [{'severity':'material','kind':'report_amount_units','evidence':'Delivered Markdown says selling/admin expenses decreased 2942/3070 万元. Source values are -5528 to -2586 and -24053 to -20983 千元: decreases are 294.2/307.0 万元 (report overstates these by 10). The R&D 1206.4 万元 change is correct.'},
          {'severity':'material','kind':'csv_ratio_units','evidence':'Margin rows are percentages but share columns explicitly named RMB百万元 and change_RMB百万元. Final chat labels the margins correctly.'}],
         'Inspected final PNG: Chinese renders; amounts, signed waterfall bases and million-yuan units are correct. Amount axis ends at -30.65 without bottom padding; small contributions lack value labels.',
         ['Core 10/10 measures requested main numbers only; material prose and CSV unit errors remain.','Bridge is partial and labels the remaining -15.960 million as unexplained; no claim of a full source reconciliation.'])


def c1():
    manifest=json.loads((TRIAL/'C1-deliverables.json').read_text(encoding='utf-8'))
    latest=[r for r in manifest['artifacts'] if r['name']=='profit_cashflow_comparison.csv'][-1]
    with (TRIAL/'C1-artifacts'/latest['localFile']).open(encoding='utf-8-sig') as f:rows=list(csv.DictReader(f))
    expected={'收入_RMB000':('181011','120392'),'毛利率_pct':(str(D(14577)/181011*100),str(D(9111)/120392*100)),
              '经营亏损_RMB000':('-32320','-18170'),'合并净利润_RMB000':('-38635','41098'),'经营现金流_RMB000':('-32104','-30650')}
    checks=[{'name':name+' '+row['期间'],'actual':row[name],'expected':values[i],'pass':abs(D(row[name])-D(values[i]))<D('0.0000001')}
            for name,values in expected.items() for i,row in enumerate(rows)]
    save('C1',checks,{'noncash_gain_not_operating_improvement':'pass','net_profit_cfo_scope':'pass','cashflow_residual_explicit':'pass','finance_and_tax_classification':'pass','explanation_and_plot_units':'pass'},
         [{'severity':'minor','kind':'chart_detail','evidence':'Final waterfall correctly ends at cash used in operations (-30.649m), but lacks a separate final-total anchor/value label; detailed values are in CSV/chat.'}],
         'Inspected final PNG and final script. Chinese and report colors readable, comparison amounts and signed waterfall bases correct. Main-model response repaired tick count and residual geometry through two small patches.',
         ['More complete partial bridge than A/B: finance costs 3.943m (p41 splits interest on borrowings/directors/leases), investing interest -0.029m, tax credit -0.167m; all classified with p32 cash-flow presentation. Unexplained -19.707m remains explicit.','Financial model/record-binding helpers were not used in this task; source-page reading, custom Python and small-patch repair produced this answer.','One failed sandbox run and one intermediate successful chart preceded the final artifact; both are retained in cost/repair counts.'])


def b2():
    with (TRIAL/'B2-artifacts/yili_forecast_data.csv').open(encoding='utf-8-sig') as f:rows={r['年份']:r for r in csv.DictReader(f)}
    expected={'营业收入_百万元':('119338','122498','125438'),'归母净利润_百万元':('11309','12222','13152'),'EPS_元':('1.78','1.92','2.07')}
    checks=[{'name':name+' '+str(year),'actual':rows[str(year)][name],'expected':v,'pass':D(rows[str(year)][name])==D(v)}
            for name,values in expected.items() for year,v in zip((2025,2026,2027),values)]
    save('B2',checks,{'source_institution_and_date':'pass','actual_forecast_separated':'pass','pe_19_20_times_2025_eps':'pass','logic_and_risks_attributed':'pass'},
         [{'severity':'material','kind':'chart_chinese_glyphs','evidence':'Final PNG Chinese is missing-glyph boxes. Script explicitly selects unavailable Noto Sans CJK SC, replacing the working shared defaults.'},
          {'severity':'material','kind':'chart_label_overlap','evidence':'The 19x=33.82 and 20x=35.60 labels overlap in the actual target-price panel.'}],
         'Inspected actual final PNG: forecast values, A/E identity and PE endpoints align with CSV; Chinese unreadable and price labels overlap.',
         ['Core 9/9 is source-number accuracy only.','Identifies differing current-price/upside references without silently calibrating the PE target.'])


def research_row_checks(label,filename,year_key,columns):
    with (TRIAL/f'{label}-artifacts'/filename).open(encoding='utf-8-sig') as f:rows={r[year_key]:r for r in csv.DictReader(f)}
    checks=[]
    for name,values in columns.items():
        for year,v in zip((2025,2026,2027),values):
            actual=rows[str(year)][name];checks.append({'name':name+' '+str(year),'actual':actual,'expected':v,'pass':D(actual)==D(v)})
    return checks


def a2():
    checks=research_row_checks('A2','伊利预测底稿.csv','年份',{'营业收入_亿元':('1193.38','1224.98','1254.38'),'归母净利润_亿元':('113.09','122.22','131.52'),'EPS_元':('1.78','1.92','2.07')})
    save('A2',checks,{'source_institution_and_date':'pass','actual_forecast_separated':'pass','pe_recalculation':'pass','opinion_not_fact':'pass','chart_units':'pass'},[],
         'Inspected final PNG: Chinese and source legible; revenue/profit/EPS values and 亿 units correct; zero-based profit bars; forecast-only charts explicitly labeled as forecasts.')


def c2():
    checks=research_row_checks('C2','forecast_data.csv','year',{'revenue_mn':('119338','122498','125438'),'net_profit_mn':('11309','12222','13152'),'eps_yuan':('1.78','1.92','2.07')})
    save('C2',checks,{'source_institution_and_date':'pass','actual_forecast_separated':'pass','pe_recalculation':'pass','opinion_not_fact':'pass','chart_units':'fail'},
         [{'severity':'critical','kind':'chart_amount_scale','evidence':'Script divides source million-CNY amounts by 1000 (billion yuan), then labels both revenue and net-profit axes 亿元. E.g. 2025 revenue plots 119.338 instead of 1193.38 亿元, profit 11.309 instead of 113.09. Main CSV source mn fields and report/chat table are correct.'}],
         'Inspected actual final PNG: font, actual/forecast style and layout readable, but two monetary panels understate displayed values by 10 under their axis labels.',
         ['Theme was used; unit-conversion helpers were not. A helper passing deterministic tests is not proof the agent actually used it.','Original trial retained. Any correction/retest must be reported separately, not replace this result.'])


def artifact(label,name):
    manifest=json.loads((TRIAL/f'{label}-deliverables.json').read_text(encoding='utf-8'))
    selected=[x for x in manifest['artifacts'] if x['name']==name][-1]
    return TRIAL/f'{label}-artifacts'/(selected.get('localFile') or selected['evaluatorLocalFile'])


def csv_rows(label,name):
    with artifact(label,name).open(encoding='utf-8-sig') as f:return list(csv.DictReader(f))


def check(name,actual,expected,tolerance='0.000001'):
    return {'name':name,'actual':str(actual),'expected':str(expected),'pass':abs(D(str(actual))-D(str(expected)))<=D(tolerance)}


def model_math(model):
    """Independent Decimal arithmetic, no imports from production calculator."""
    spec,res=model['spec'],model['result'];rows=res['tables']['forecast'];checks=[];flows=[]
    for row in rows:
        flow=D(row['ebit'])-D(row['cash_tax'])+D(row['da'])-D(row['capex'])-D(row['delta_nwc'])
        checks.append(check('FCFF '+str(row['year']),row['fcff'],flow));flows.append(flow)
    def valuation(w,g):
        term=spec['terminal'];last=rows[-1]
        terminal_fcff=D(last['revenue'])*(1+g)*D(term.get('ebit_margin',last['ebit_margin']))*(1-D(term['tax_rate']))*(1-g/D(term['roic']))
        ev=sum(f/(1+w)**D(row['discount_exponent']) for f,row in zip(flows,rows))+terminal_fcff/(w-g)/(1+w)**len(rows)
        b=spec['bridge'];eq=ev-D(b['net_debt'])-D(b.get('non_controlling_interest',0))-D(b.get('preferred_equity',0))+D(b.get('non_operating_assets_ex_cash',0))
        price=eq*D(spec['amount_scale'])/(D(spec['shares']['count'])*D(spec['shares']['scale']))
        return ev,eq,price
    actual=res['results'];v=valuation(D(spec['discount']['wacc']),D(spec['terminal']['growth']))
    for key,value in zip(('enterprise_value','equity_value','value_per_share'),v):checks.append(check(key,actual[key],value))
    for r in res['tables']['sensitivity']:
        checks.append(check('sensitivity '+r['wacc']+'/'+r['growth'],r['value_per_share'],valuation(D(r['wacc']),D(r['growth']))[2]))
    return checks


def a3():
    rows=csv_rows('A3','伊利_DCF预测与FCFF对照.csv')
    summary={r['metric']:D(r['value']) for r in csv_rows('A3','伊利_DCF估值汇总.csv')}
    checks=[]
    expected={'revenue_mn':('119338','122498','125438'),'da_mn':('4822','5316','5724'),
              'capex_mn':('4500','5000','4000'),'change_nwc_cash_use_mn':('5977','99','535'),'reported_fcff_mn':('6482','13088','14637')}
    for key,values in expected.items():
        checks += [check(key+' '+r['year'],r[key],v) for r,v in zip(rows,values)]
    checks += [check(k,summary[k],v) for k,v in [('net_debt_mn','24867'),('minority_interest_mn','3828'),('shares_mn','6366')]]
    flows=[D(r['revenue_mn'])*D(r['ebit_margin'])*(1-D('.123'))+D(r['da_mn'])-D(r['capex_mn'])-D(r['change_nwc_cash_use_mn']) for r in rows]
    checks += [check('FCFF '+r['year'],r['fcff_calc_mn'],v) for r,v in zip(rows,flows)]
    for r in csv_rows('A3','伊利_DCF敏感性.csv'):
        w,g=D(r['WACC']),D(r['g'])
        ev=sum(v/(1+w)**(i+1) for i,v in enumerate(flows))+flows[-1]*(1+g)/(w-g)/(1+w)**3
        checks.append(check('per share '+str(w)+'/'+str(g),r['value_per_share'],(ev-D(24867)-D(3828))/D(6366)))
    save('A3',checks,{'source_inputs':'pass','fcff_reconciliation':'pass','explicit_terminal_method':'pass','nci_and_net_debt':'pass','target_interval':'pass'},
         [{'severity':'minor','kind':'heatmap_contrast','evidence':'Black text is difficult to read on the darkest blue sensitivity cell; both delivered PNGs omit a source caption (sources are in the report).'}],
         'Inspected both PNGs: Chinese legible, correct scales, FCFF comparison matches CSV, sensitivity axes correct.',
         ['Uses last-year FCFF growth for terminal value, unlike the financial tool ROIC method; price differences alone are not errors.','First Python attempt failed; full rewrite then succeeded, both included in usage.'])


def c3():
    models=json.loads(artifact('C3','models.json').read_text(encoding='utf-8'))
    model=models['base'];spec=model['spec'];res=model['result'];rows=res['tables']['forecast']
    checks=[]
    # Check against the supplied source, not against the model invented assumptions.
    for field,values in {'revenue':('119338','122498','125438'),'da':('4822','5316','5724'),'capex':('4500','5000','4000'),'delta_nwc':('5977','99','535')}.items():
        for row,v in zip(rows,values):checks.append(check(field+' '+str(row['year']),row[field],v))
    checks += [check('net debt',spec['bridge']['net_debt'],'24867'),check('NCI',spec['bridge']['non_controlling_interest'],'3828'),check('shares',spec['shares']['count'],'6366')]
    arithmetic=model_math(model)
    save('C3',checks,{'source_inputs':'fail','fcff_reconciliation':'fail','explicit_assumptions':'pass','model_formula_under_own_assumptions':'separately_replayed','target_interval_under_own_assumptions':'pass'},
         [{'severity':'critical','kind':'missed_available_source_inputs','evidence':'Page 36/table t23 contains D&A, capex, NWC, FCFF, 2024 cash/debt and NCI. Agent reads pp27-32 and misses these data, substitutes 3% D&A, 4% capex, zero NWC/NCI and gross debt 75602 as net debt. This is incomplete task fulfillment even though substitutes are labeled assumptions.'},
          {'severity':'material','kind':'duplicate_calculator_broken','evidence':'Saved model and automatic original-calculator bundle exist, but agent rewrites DCF twice; its separately delivered standalone calculator still has a SyntaxError (n opat). Actual executed_script.py runs and original calculator bundle remains usable.'},
          {'severity':'minor','kind':'heatmap_contrast','evidence':'Dark green text on dark green cells makes several sensitivity labels hard to read; horizontal grid crosses the values.'}],
         'Inspected final PNG: Chinese and ten-billion-yuan axis are correct under its own assumptions; financial completeness failed upstream.',
         ['Source checks measure values requested and actually available, not whether guessed assumptions compute correctly.','One invented artifact ID error, six patch preflight errors and five failed sandbox attempts retained.','FCFF text query does not match free_cash_flow_firm; multiword query is treated as a single literal by the current interface. Agent also omits page 36 available in raw index.'])
    path=TRIAL/'judge/C3-review.json';review=json.loads(path.read_text(encoding='utf-8'))
    review['independent_arithmetic']={'passed':sum(x['pass'] for x in arithmetic),'total':len(arithmetic),'checks':arithmetic}
    path.write_text(json.dumps(review,ensure_ascii=False,indent=2),encoding='utf-8')


def b3():
    rows=csv_rows('B3','伊利_DCF_预测输入与FCFF对照.csv');summary=csv_rows('B3','伊利_DCF_估值汇总.csv')[0]
    checks=[]
    expected={'revenue_mn_rmb':('119338','122498','125438'),'D&A_mn_rmb':('4822','5316','5724'),
              'capex_mn_rmb':('4500','5000','4000'),'working_capital_cashflow_mn_rmb':('-5977','-99','-535'),'reported_FCFF_mn_rmb':('6482','13088','14637')}
    for key,values in expected.items():checks += [check(key+' '+r['year'],r[key],v) for r,v in zip(rows,values)]
    checks += [check(k,summary[k],v) for k,v in [('net_debt_mn_rmb','24867'),('minority_interest_2024_mn_rmb','3828'),('shares_mn','6366')]]
    flows=[D(r['revenue_mn_rmb'])*D(r['EBIT_margin'])*(1-D('.123'))+D(r['D&A_mn_rmb'])-D(r['capex_mn_rmb'])+D(r['working_capital_cashflow_mn_rmb']) for r in rows]
    checks += [check('FCFF '+r['year'],r['calculated_FCFF_mn_rmb'],v) for r,v in zip(rows,flows)]
    for r in csv_rows('B3','伊利_DCF_敏感性.csv'):
        w,g=D(r['WACC']),D(r['g']);ev=sum(v/(1+w)**(i+1) for i,v in enumerate(flows))+flows[-1]*(1+g)/(w-g)/(1+w)**3
        checks.append(check('per share '+str(w)+'/'+str(g),r['value_per_share_rmb'],(ev-D(24867)-D(3828))/D(6366)))
    save('B3',checks,{'source_inputs':'pass','fcff_reconciliation':'pass','explicit_terminal_method':'pass','nci_and_net_debt':'pass','target_interval':'pass'},
         [{'severity':'minor','kind':'heatmap_contrast_and_caption','evidence':'Dark text on darkest blue cell is hard to read. Plot axis correctly says ten-billion CNY; general footer instead says million CNY (the underlying worksheet scale).'}],
         'Inspected final PNG: correct numbers and axes, Chinese legible after several retries; precise references retained in Markdown.',
         ['All eight script runs retained, including three failures and font repair attempts.','One failure imports unavailable finance_charts after common tool description advertises it; this baseline-interface defect prevents treating that avoidable cost as financial-agent advantage.'])


def growth_dcf(w,g,capex='1',da='1'):
    flows=[D(rev)*D(margin)*(1-D('.123'))+D(depreciation)*D(da)-D(capital)*D(capex)-D(nwc)
           for rev,margin,depreciation,capital,nwc in zip(('119338','122498','125438'),('.116','.12','.122'),('4822','5316','5724'),('4500','5000','4000'),('5977','99','535'))]
    w,g=D(w),D(g);ev=sum(f/(1+w)**(i+1) for i,f in enumerate(flows))+flows[-1]*(1+g)/(w-g)/(1+w)**3
    return flows,ev,ev-D(24867)-D(3828),(ev-D(24867)-D(3828))/D(6366)


def a4():
    baseline=growth_dcf('.079','.018');updated=growth_dcf('.084','.018','1.2','1.1');checks=[]
    for r,old,new in zip(csv_rows('A4','伊利_DCF局部更新_FCFF变化.csv'),baseline[0],updated[0]):
        checks.extend((check('old FCFF '+r['year'],r['baseline_FCFF_mn'],old),check('new FCFF '+r['year'],r['updated_FCFF_mn'],new),check('change FCFF '+r['year'],r['delta_FCFF_mn'],new-old)))
    for r,old,new in zip(csv_rows('A4','伊利_DCF局部更新_估值结果.csv'),baseline[1:],updated[1:]):
        checks.extend((check('old '+r['metric'],r['baseline'],old),check('new '+r['metric'],r['updated'],new),check('delta '+r['metric'],r['delta'],new-old)))
    prices=[baseline[3],growth_dcf('.084','.018')[3],growth_dcf('.084','.018','1.2')[3],updated[3]]
    for i,r in enumerate(csv_rows('A4','伊利_DCF局部更新_顺序归因.csv')):
        checks.extend((check(r['step'],r['per_share'],prices[i]),check('contribution '+r['step'],r['incremental_effect'],prices[i]-prices[i-1] if i else 0)))
    for r in csv_rows('A4','伊利_DCF局部更新_敏感性对照.csv'):
        checks.extend((check('old '+r['WACC']+'/'+r['g'],r['baseline_per_share'],growth_dcf(r['WACC'],r['g'])[3]),check('new '+r['WACC']+'/'+r['g'],r['updated_per_share'],growth_dcf(r['WACC'],r['g'],'1.2','1.1')[3])))
    for r in csv_rows('A4','伊利_DCF局部更新_完整输入对照.csv'):
        factor=D('1.2') if r['input']=='capex_mn' else D('1.1') if r['input']=='DA_mn' else 1
        checks.append(check('input '+r['year']+' '+r['input'],r['updated'],D(r['baseline'])*factor))
    save('A4',checks,{'only_requested_changes':'pass','sequence_attribution':'pass','same_absolute_grid':'pass','no_reread':'pass'},
         [{'severity':'material','kind':'colorbar_overlap','evidence':'Actual final colorbar lies inside the right heatmap, and colorbar label overlaps the right-middle cell value.'},
          {'severity':'minor','kind':'heatmap_contrast','evidence':'Black text on dark blue cells is low contrast.'}],
         'Inspected final paired PNG and script: correct shared normalization, same axes/grid, financial values consistent; colorbar layout visibly fails.',
         ['No source reread. Appends update to previous analysis with a patch, preserves baseline constants and exports both inputs/results.'])


def b4():
    baseline=growth_dcf('.079','.018');updated=growth_dcf('.084','.018','1.2','1.1');checks=[]
    for r,old,new in zip(csv_rows('B4','伊利_DCF_新旧差异.csv'),baseline[0],updated[0]):
        checks.extend((check('old FCFF '+r['year'],r['base_FCFF_mn_rmb'],old),check('new FCFF '+r['year'],r['updated_FCFF_mn_rmb'],new),check('change FCFF '+r['year'],r['delta_FCFF_mn_rmb'],new-old)))
    for r,values in zip(csv_rows('B4','伊利_DCF_新旧估值结果.csv'),(baseline,updated)):
        for key,value in zip(('EV_mn_rmb','equity_value_mn_rmb','value_per_share_rmb'),values[1:]):checks.append(check(r['case']+' '+key,r[key],value))
    prices=[baseline[3],growth_dcf('.084','.018')[3],growth_dcf('.084','.018','1.2')[3],updated[3]]
    for i,r in enumerate(csv_rows('B4','伊利_DCF_更新顺序归因.csv')):
        checks.extend((check(r['stage'],r['value_per_share_rmb'],prices[i]),check('contribution '+r['stage'],r['incremental_change_per_share_rmb'],prices[i]-prices[i-1] if i else 0)))
    for r in csv_rows('B4','伊利_DCF_两版敏感性.csv'):
        capex,da=('1','1') if r['case']=='基准' else ('1.2','1.1')
        checks.append(check(r['case']+' '+r['WACC']+'/'+r['g'],r['value_per_share_rmb'],growth_dcf(r['WACC'],r['g'],capex,da)[3]))
    rows=csv_rows('B4','伊利_DCF_新旧输入.csv')
    old=[r for r in rows if r['case']=='基准'];new=[r for r in rows if r['case']=='更新后']
    for a,b in zip(old,new):
        for k in ('revenue_mn_rmb','EBIT_margin','EBIT_mn_rmb','tax_rate','D&A_mn_rmb','capex_mn_rmb','working_capital_cashflow_mn_rmb'):
            factor=D('1.2') if k=='capex_mn_rmb' else D('1.1') if k=='D&A_mn_rmb' else 1
            checks.append(check('input '+a['year']+' '+k,b[k],D(a[k])*factor))
    save('B4',checks,{'only_requested_changes':'pass','sequence_attribution':'pass','same_absolute_grid':'pass','no_reread':'pass'},
         [{'severity':'material','kind':'colorbar_overlap','evidence':'Final PNG places colorbar inside right heatmap, covering part of the middle column and the panel title.'},
          {'severity':'minor','kind':'heatmap_contrast','evidence':'Dark text on dark blue cells has poor contrast.'}],
         'Inspected final paired PNG: same financial grid/norm and correct values; colorbar visibly overlaps right panel.',
         ['No source reread; three repairs after initial attempt, including one failed script. All costs retained.'])


def c4():
    models=json.loads(artifact('C4','models.json').read_text(encoding='utf-8'))
    base,new=models['base'],models['scenario'];checks=[]
    for name,model in models.items():
        checks += [{**c,'name':name+' '+c['name']} for c in model_math(model)]
    checks.append(check('WACC change',D(new['spec']['discount']['wacc'])-D(base['spec']['discount']['wacc']),'.005'))
    for left,right in zip(base['result']['tables']['forecast'],new['result']['tables']['forecast']):
        for key in ('revenue','ebit','cash_tax','delta_nwc','da','capex'):
            factor=D('1.1') if key=='da' else D('1.2') if key=='capex' else D(1)
            checks.append(check(str(left['year'])+' '+key,right[key],D(left[key])*factor))
    comparison=json.loads(artifact('C4','comparisons.json').read_text(encoding='utf-8'))['change']
    steps=comparison['decomposition']['steps']
    old,new_value=D(base['result']['results']['value_per_share']),D(new['result']['results']['value_per_share'])
    checks.append(check('attribution sum',sum(D(s['contribution']) for s in steps),new_value-old))
    checks.append({'name':'same absolute grid','actual':new['spec']['sensitivity'],'expected':base['spec']['sensitivity'],'pass':new['spec']['sensitivity']==base['spec']['sensitivity']})
    expected=['discount.wacc',*[f'forecast.{i}.capex_ratio' for i in range(3)],*[f'forecast.{i}.da_ratio' for i in range(3)]]
    checks.append({'name':'ordered attribution','actual':[s['path'] for s in steps],'expected':expected,'pass':[s['path'] for s in steps]==expected})
    for r,left,right in zip(csv_rows('C4','伊利DCF_年度FCFF对照.csv'),base['result']['tables']['forecast'],new['result']['tables']['forecast']):
        checks += [check('CSV baseline FCFF '+str(left['year']),r['基准FCFF（百万元）'],left['fcff']),check('CSV new FCFF '+str(left['year']),r['更新FCFF（百万元）'],right['fcff'])]
    save('C4',checks,{'relative_update_math':'pass','same_absolute_grid':'pass','sequence_attribution':'pass','no_reread':'pass','report_matches_model':'fail','source_completeness':'inherited_C3_failure'},
         [{'severity':'material','kind':'report_amount_units','evidence':'Markdown divides million-CNY EV and equity by 1000 but labels 亿元: EV 173.78 vs correct 1737.78 亿元, a factor-of-ten error. Chat and CSV retain correct million-CNY values.'},
          {'severity':'material','kind':'report_baseline_fcff','evidence':'Markdown puts updated FCFF values into both baseline and updated columns (e.g. 9556.556 twice); actual baseline 2025 FCFF is 10153.246. Exact model, CSV and final chat values are correct.'},
          {'severity':'material','kind':'colorbar_overlap','evidence':'Actual PNG colorbar covers the right panel; dark green text is almost invisible on the darkest cells; default horizontal grid crosses labels.'}],
         'Inspected final PNG, script, Markdown and CSV. Correct numerical update under its inherited assumptions; numeric presentation defects remain.',
         ['One sandbox run directly uses saved model revisions and comparison; no duplicate DCF calculator.', 'Initial C3 omitted available data; C4 preserves those inputs as requested, so correct local updates do not rehabilitate the original model.'])


if __name__=='__main__':
    a1()
    if (TRIAL/'B1-artifacts/对比底稿.csv').exists():b1()
    if (TRIAL/'C1-deliverables.json').exists():c1()
    if (TRIAL/'B2-artifacts/yili_forecast_data.csv').exists():b2()
    if (TRIAL/'A2-artifacts/伊利预测底稿.csv').exists():a2()
    if (TRIAL/'C2-artifacts/forecast_data.csv').exists():c2()
    if (TRIAL/'A3-deliverables.json').exists():a3()
    if (TRIAL/'C3-deliverables.json').exists():c3()
    if (TRIAL/'B3-deliverables.json').exists():b3()
    if (TRIAL/'A4-deliverables.json').exists():a4()
    if (TRIAL/'B4-deliverables.json').exists():b4()
    if (TRIAL/'C4-deliverables.json').exists():c4()
