"""Explicit CSV cell bindings to the already frozen held-out selector catalog.

Never infer currency from numerical magnitude; unbound entries remain unknown.
"""
import csv
import hashlib
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
STUDY = ROOT / 'data/evaluation/blind-eval-F12-heldout-20261008'
CATALOG = ROOT / 'benchmark/blind-eval/selectors-heldout.json'
spec = importlib.util.spec_from_file_location('selectors_f1', ROOT / 'benchmark/blind-eval/selectors-f1.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def read(p):
    return json.loads(p.read_text('utf-8-sig'))


def dump(p, x):
    p.write_text(json.dumps(x, ensure_ascii=False, indent=2)+'\n', 'utf8')


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


annual = {
    '收入': 'revenue', '营业收入': 'revenue', 'Revenue': 'revenue', 'revenue': 'revenue',
    '营业成本': 'cost', '营业利润': 'operating_profit', 'Operating profit': 'operating_profit', 'operating_profit': 'operating_profit',
    '合并净利润': 'consolidated_profit', 'Consolidated net profit': 'consolidated_profit', 'consolidated_net_profit': 'consolidated_profit',
    '归母净利润': 'parent_profit', 'Parent-attributable net profit': 'parent_profit', 'parent_net_profit': 'parent_profit',
    '扣非归母净利润': 'adjusted_parent_profit', 'Adjusted parent net profit': 'adjusted_parent_profit', 'adjusted_parent_net_profit': 'adjusted_parent_profit',
    '经营现金流净额': 'cfo', 'Operating cash flow': 'cfo', 'ocf': 'cfo',
}
bridge = {
    '合并净利润': 'net_profit', '净利润': 'net_profit', 'Net profit': 'net_profit',
    '资产减值准备': 'impairment', '信用减值（利得）损失': 'credit_losses',
    '固定资产折旧': 'depreciation', '投资性房地产折旧': 'investment_property_depreciation',
    '使用权资产折旧': 'lease_depreciation', '无形资产摊销': 'intangibles', '长期待摊费用摊销': 'deferred_expenses',
    '股份支付费用': 'share_payment', 'Share-based payment': 'share_payment',
    '处置长期资产收益调整': 'disposals', '处置长期资产收益（调整）': 'disposals',
    '公允价值变动收益调整': 'fair_value', '公允价值变动收益（调整）': 'fair_value',
    '财务费用调整': 'finance', '财务费用（间接法调整）': 'finance', '投资收益调整': 'investment', '投资收益（调整）': 'investment',
    '递延所得税资产减少': 'deferred_tax_asset', '递延所得税负债增加': 'deferred_tax_liability',
    '递延收益摊销': 'deferred_income', 'Deferred income amortization': 'deferred_income',
    '存货变动': 'inventory', '存货（增加）减少': 'inventory', 'Inventory change': 'inventory',
    '经营性应收项目变动': 'receivables', '经营性应收项目增加': 'receivables', 'Operating receivables change': 'receivables',
    '经营性应付项目变动': 'payables', '经营性应付项目增加（减少）': 'payables', 'Operating payables change': 'payables',
    '信用减值利得/损失': 'credit_losses', '长期资产处置收益调减': 'disposals',
    '公允价值变动收益调减': 'fair_value', '财务费用调节': 'finance', '投资收益调减': 'investment',
    '存货增加/减少': 'inventory', '经营性应收项目增加/减少': 'receivables', '经营性应付项目增加/减少': 'payables',
}
catalog_keys = {s['key'] for s in read(CATALOG)['checks']}
results = []
for run in read(STUDY / 'experiment.json')['runs']:
    if run['status'] not in ['completed', 'failed', 'cancelled']:
        continue
    label, task = run['label'], run['taskId']
    delivery = read(STUDY / f'{label}-deliverables.json')
    folder = STUDY / f'{label}-artifacts'
    bindings, scope = [], []
    for item in delivery['artifacts']:
        if not item['name'].endswith('.csv') or not item.get('localFile'):
            continue
        f = folder / item['localFile']
        with f.open(encoding='utf-8-sig', newline='') as stream:
            reader = csv.DictReader(stream); headers = reader.fieldnames; rows = list(reader)
        name = item['name']; first = headers[0]

        def bind(key, row, column, unit, evidence=None):
            fullkey = task+'.'+key
            if fullkey not in catalog_keys:
                return
            if evidence is None:
                evidence = column
                if unit == 'CNY_million' and not ('人民币百万元' in column or 'RMB_mn' in column):
                    scope.append({'file':item['localFile'],'row':row[first],'column':column,'status':'unbound_missing_unit_annotation'})
                    return
                if unit == '%' and not ('%' in column or 'pct' in column):
                    return
            assert evidence in f.read_text('utf-8-sig')
            bindings.append({'key':fullkey,'file':item['localFile'],'sha256':sha(f),'format':'csv',
                             'row':{first:row[first]},'column':column,'unit_literal':evidence,'unit_map':{evidence:unit}})

        if task == 'H1' and name in ['annual_summary.csv','annual_amounts.csv','annual_comparison.csv','annual_metrics.csv']:
            for row in rows:
                metric = annual.get(row[first])
                if metric:
                    for year in ['2023','2024']:
                        col = next((h for h in headers if h.startswith(year)),None)
                        if col:bind(metric+'_'+year,row,col,'CNY_million')
                    col = next((h for h in headers if h in ['同比增幅%','同比%','Change_pct','change_pct']),None)
                    if col:bind(metric+'_growth',row,col,'%')
                elif row[first] in ['合并毛利率%','毛利率（%）']:
                    for year in ['2023','2024']:
                        col = next(h for h in headers if h.startswith(year))
                        bind('gross_margin_'+year,row,col,'%',row[first])
                    # Change is pp; if row-specific annotation is absent, leave the unit interpretation to the judge.
        elif task == 'H1' and name in ['cashflow_reconciliation.csv','cash_reconciliation.csv','cashflow_bridge.csv']:
            for row in rows:
                metric=bridge.get(row[first])
                if metric:
                    for year in ['2023','2024']:
                        bind('bridge_'+metric+'_'+year,row,next(h for h in headers if h.startswith(year)),'CNY_million')
                    bind('bridge_change_'+metric,row,headers[3],'CNY_million')
                elif row[first] in ['经营活动现金流净额','Operating cash flow']:
                    for year in ['2023','2024']:bind('cfo_'+year,row,next(h for h in headers if h.startswith(year)),'CNY_million')
                    bind('cfo_change',row,headers[3],'CNY_million')
                else:scope.append({'file':item['localFile'],'row':row[first],'status':'grouped_bridge_independent_review; do not invent a new gold value after answers'})
        elif task == 'H1' and name == 'q4_2024.csv':
            for row in rows:
                if row[first] in annual:bind('Q4_'+annual[row[first]],row,headers[1],'CNY_million')
        elif task == 'H1' and name == 'margins.csv':
            for row in rows:
                if row[first]=='合并口径（收入减营业成本/收入）':
                    for year in ['2023','2024']:bind('gross_margin_'+year,row,year+'%','%')
                    bind('gross_margin_change',row,'同比百分点','pp')
        elif task == 'H2' and name == 'stress_calculation_detail.csv':
            mapping={'2024 operating cash flow reported':'cfo_original','2024 operating payables adjustment reported':'payables_original',
                     'Replace with 2023 operating payables adjustment':'payables_replacement','Stress scenario operating cash flow':'cfo_stress',
                     'Stress minus reported operating cash flow':'cfo_delta','2024 consolidated net profit':'consolidated_profit'}
            for row in rows:
                if row[first] in mapping:bind(mapping[row[first]],row,headers[1],'CNY_million')
        elif task == 'H2' and name == 'stress_scenario.csv':
            for row in rows:
                key={'Reported 2024 OCF':'cfo_original','Stress OCF':'cfo_stress','Difference vs reported':'cfo_delta'}.get(row[first])
                if key:bind(key,row,headers[1],'CNY_million')
                key={'Reported 2024 OCF':'original_coverage','Stress OCF':'stress_coverage'}.get(row[first])
                if key:bind(key,row,headers[2],'ratio')
        elif task == 'H2' and name == 'stress_summary.csv':
            for row in rows:
                if row[first]=='经营性应付项目调节':
                    bind('payables_original',row,headers[1],'CNY_million');bind('payables_replacement',row,headers[2],'CNY_million')
                elif row[first]=='经营现金流净额':
                    for key,column in zip(['cfo_original','cfo_stress','cfo_delta'],headers[1:4]):bind(key,row,column,'CNY_million')
                elif row[first]=='经营现金流/合并净利润':
                    for key,column in zip(['original_coverage','stress_coverage'],headers[1:3]):bind(key,row,column,'ratio',row['备注'])
        elif task == 'H2' and name == 'stress_scenario_detail.csv':
            for row in rows:
                if row[first]=='合并净利润':bind('consolidated_profit',row,headers[1],'CNY_million')
                elif row[first]=='经营性应付项目变动（2024实际）':
                    bind('payables_original',row,headers[1],'CNY_million');bind('payables_replacement',row,headers[2],'CNY_million')
                elif row[first]=='经营活动现金流净额':
                    bind('cfo_original',row,headers[1],'CNY_million');bind('cfo_stress',row,headers[2],'CNY_million')
                elif row[first]=='对合并净利润覆盖倍数':
                    bind('original_coverage',row,headers[1],'ratio',row[first]);bind('stress_coverage',row,headers[2],'ratio',row[first])
        elif task == 'H2' and name == 'bridge_scenario_detail.csv':
            for row in rows:
                if row[first]=='净利润':
                    for col in headers[1:3]:bind('consolidated_profit',row,col,'CNY_million')
                elif row[first]=='经营性应付项目增加/减少-2024值':
                    bind('payables_original',row,headers[1],'CNY_million');bind('payables_replacement',row,headers[2],'CNY_million')
                elif row[first]=='经营活动现金流净额':
                    bind('cfo_original',row,headers[1],'CNY_million');bind('cfo_stress',row,headers[2],'CNY_million')
        elif task == 'H2' and name in ['payables_scenario.csv','payables_stress_scenario.csv']:
            for row in rows:
                actual=row[first] in ['报告披露原值','原值：2024披露']
                columns=([1,2,3,4,5] if name=='payables_scenario.csv' else [3,2,4,1,5])
                for key,index in [('cfo_original' if actual else 'cfo_stress',columns[0]),
                                  ('payables_original' if actual else 'payables_replacement',columns[1]),
                                  ('consolidated_profit',columns[3])]:
                    bind(key,row,headers[index],'CNY_million')
                if not actual:bind('cfo_delta',row,headers[columns[2]],'CNY_million')
                bind('original_coverage' if actual else 'stress_coverage',row,headers[columns[4]],'ratio')
        else:scope.append({'file':item['localFile'],'status':'not_bound_yet; independent review remains required'})
    manifest={'catalog_sha256':sha(CATALOG),'tasks':[task],'bindings':bindings,'scope':scope}
    bp=STUDY/f'{label}-gold-bindings.json';dump(bp,manifest)
    grade=module.grade(CATALOG,bp,folder);dump(STUDY/f'{label}-gold-numeric.json',grade)
    from collections import Counter
    results.append({'label':label,'binding_count':len(bindings),'status_counts':dict(Counter(c['status'] for c in grade['checks'])),
                    'unbound_keys':len(grade['unbound']),'scope':scope})
dump(STUDY/'numeric-summary.json',{'catalog_sha256':sha(CATALOG),'rows':results,'limit':'Numeric consistency only. Missing annotations, grouped bridge cells, prose, images and semantic source labels remain review scope; unbound is not failure or pass.'})
print(json.dumps(results,ensure_ascii=False))
