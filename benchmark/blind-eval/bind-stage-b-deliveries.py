"""Evaluator-reviewed cell locations, bound to unchanged preregistered gold.

Mappings below are explicit semantic row/column identities from inspected
deliveries. This does not search for numbers close to the reference answer.
"""
import csv
import hashlib
import importlib.util
import json
from pathlib import Path
from blind import ROOT, read, dump

spec = importlib.util.spec_from_file_location('selectors_f1', Path(__file__).with_name('selectors-f1.py'))
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
study = ROOT / 'data/evaluation/blind-eval-F14-B-20261008'
catalog = ROOT / 'benchmark/blind-eval/selectors-stage-b-additions.json'
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()


def csv_bind(artifact, row, column, key, unit):
    return {'key': key, 'file': artifact['localFile'], 'sha256': artifact['sha256'],
            'format': 'csv', 'row': row, 'column': column,
            'unit_literal': unit[0], 'unit_map': {unit[0]: unit[1]}}


def x1_csv(artifact):
    name = artifact['name']
    out = []
    def add(row, col, key, token, unit):
        out.append(csv_bind(artifact, row, col, 'X1.' + key, (token, unit)))
    if name == 'yili_2024_growth_profitability.csv':
        for year in ['2023', '2024']:
            for stem, col in {
                'revenue': 'revenue_CNY_mn', 'parent_profit': 'parent_net_profit_CNY_mn',
                'adjusted_parent_profit': 'deducted_parent_net_profit_CNY_mn',
                'parent_equity': 'year_end_parent_equity_CNY_mn',
                'nonrecurring_parent': 'net_nonrecurring_gain_CNY_mn',
            }.items():
                add({'year': year}, col, stem+'_'+year, 'CNY_mn', 'CNY_million')
            for stem, col in {'parent_net_margin_percent': 'parent_net_margin_pct',
                              'adjusted_parent_net_margin_percent': 'deducted_parent_net_margin_pct'}.items():
                add({'year': year}, col, stem+'_'+year, 'pct', '%')
        for key, col, token, unit in [
            ('revenue_growth', 'revenue_yoy_pct', 'pct', '%'),
            ('parent_profit_growth', 'parent_profit_yoy_pct', 'pct', '%'),
            ('adjusted_parent_profit_growth', 'deducted_profit_yoy_pct', 'pct', '%'),
            ('average_equity_2024', 'average_parent_equity_CNY_mn', 'CNY_mn', 'CNY_million'),
            ('simple_average_ROE_2024', 'simple_average_equity_ROE_pct', 'pct', '%'),
            ('weighted_ROE_2024', 'annual_report_weighted_average_ROE_pct', 'pct', '%'),
            ('parent_profit_change', 'parent_profit_change_CNY_mn', 'CNY_mn', 'CNY_million'),
            ('adjusted_parent_profit_change', 'deducted_profit_change_CNY_mn', 'CNY_mn', 'CNY_million'),
            ('nonrecurring_change', 'nonrecurring_change_CNY_mn', 'CNY_mn', 'CNY_million'),
            ('parent_net_margin_percent_change', 'parent_margin_change_pp', 'pp', 'pp'),
            ('adjusted_parent_net_margin_percent_change', 'deducted_margin_change_pp', 'pp', 'pp')]:
            add({'year': '2024'}, col, key, token, unit)
    elif name == 'yili_2024_profitability_detail.csv':
        for metric, key in [('Revenue','revenue'), ('Net income attributable','parent_profit'),
                            ('Adjusted net income','adjusted_parent_profit'), ('Equity attributable','parent_equity')]:
            for year in ['2023','2024']:
                add({'metric':metric}, year+'_mn_CNY', key+'_'+year, 'mn_CNY','CNY_million')
            if key != 'parent_equity':
                add({'metric':metric},'growth_pct',key+'_growth','pct','%')
            if key in ['parent_profit','adjusted_parent_profit']:
                add({'metric':metric},'change_mn_CNY',key+'_change','mn_CNY','CNY_million')
        for year in ['2023','2024']:
            for metric,key in [('attributable','parent_net_margin_percent'),('adjusted','adjusted_parent_net_margin_percent')]:
                add({'metric':year+' '+metric+' net margin'},'value_pct',key+'_'+year,'pct','%')
            add({'metric':year+' nonrecurring net profit difference'},'value_mn_CNY','nonrecurring_parent_'+year,'mn_CNY','CNY_million')
        for metric,key,col,token,unit in [
            ('2024 average attributable equity','average_equity_2024','value_mn_CNY','mn_CNY','CNY_million'),
            ('2024 simple-average-equity ROE','simple_average_ROE_2024','value_pct','pct','%'),
            ('2024 reported weighted average ROE','weighted_ROE_2024','value_pct','pct','%')]:
            add({'metric':metric},col,key,token,unit)
    elif name == '伊利2024增长与股东盈利明细.csv':
        for row,key in [('营业收入','revenue'),('归母净利润','parent_profit'),
                        ('扣非归母净利润','adjusted_parent_profit'),('归母净资产（年末）','parent_equity'),
                        ('净利润减扣非净利润','nonrecurring_parent')]:
            for year in ['2023','2024']:
                add({'项目':row},year,key+'_'+year,'人民币百万元','CNY_million')
        # Percent-suffixed strings are outside the frozen decimal parser's
        # accepted cell format. Preserve them for independent review, unbound.
        add({'项目':'平均归母净资产'},'2024','average_equity_2024','人民币百万元','CNY_million')
        add({'项目':'净利润减扣非净利润'},'同比/差额','nonrecurring_change','人民币百万元','CNY_million')
    elif name in ['income.csv','profit_attribution.csv','deducted_profit.csv','roe.csv']:
        for year in ['2023','2024']:
            period=year+'-FY'
            if name=='income.csv':
                add({'行键':'revenue'},period+'（CNY 百万元）','revenue_'+year,'CNY 百万元','CNY_million')
            elif name=='profit_attribution.csv':
                add({'期间':period},'归母净利润（CNY 百万元）','parent_profit_'+year,'CNY 百万元','CNY_million')
            elif name=='deducted_profit.csv':
                for col,key in [('归母净利润','parent_profit'),('披露扣非归母','adjusted_parent_profit'),
                                ('归母减非经常损益','adjusted_parent_profit'),('非经常损益合计','nonrecurring_parent')]:
                    add({'期间':period},col+'（CNY 百万元）',key+'_'+year,'CNY 百万元','CNY_million')
            else:
                add({'期间':period},'期末归母权益（CNY 百万元）','parent_equity_'+year,'CNY 百万元','CNY_million')
        if name=='roe.csv':
            for col,key,token,unit in [
                ('期初归母权益（CNY 百万元）','parent_equity_2023','CNY 百万元','CNY_million'),
                ('平均归母权益（CNY 百万元）','average_equity_2024','CNY 百万元','CNY_million'),
                ('平均归母权益ROE（%）','simple_average_ROE_2024','%','%'),
                ('披露加权平均ROE（%）','weighted_ROE_2024','%','%')]:
                add({'期间':'2024-FY'},col,key,token,unit)
    return out


def x1_json(artifact, folder):
    name=artifact['name']
    if name not in ['workpaper.json','chart_data.json','numeric_tables.json']:
        return []
    obj=read(folder/artifact['localFile'])
    prefix=[] if name=='numeric_tables.json' else ['tables']
    tables=obj if not prefix else obj['tables']
    out=[]
    cells=[]
    for year in ['2023','2024']:
        period=year+'-FY'
        cells += [('income','revenue',period,'revenue_'+year),
                  ('profit_attribution',period,'parent','parent_profit_'+year),
                  ('deducted_profit',period,'parent','parent_profit_'+year),
                  ('deducted_profit',period,'disclosed','adjusted_parent_profit_'+year),
                  ('deducted_profit',period,'calculated','adjusted_parent_profit_'+year),
                  ('deducted_profit',period,'nonrecurring','nonrecurring_parent_'+year),
                  ('roe',period,'end','parent_equity_'+year)]
    cells += [('roe','2024-FY','begin','parent_equity_2023'),
              ('roe','2024-FY','average','average_equity_2024'),
              ('roe','2024-FY','computed','simple_average_ROE_2024'),
              ('roe','2024-FY','weighted','weighted_ROE_2024')]
    for table,rowkey,col,key in cells:
        rows=tables[table]['rows']
        matches=[i for i,r in enumerate(rows) if r['key']==rowkey]
        assert len(matches)==1
        index=matches[0]
        base=prefix+[table,'rows',index,col]
        if name in ['numeric_tables.json','chart_data.json']:
            pairs=[(base,prefix+[table,'columns',col,'unit'])]
            # The delivered normalized table also carries the original cell.
            pairs.append((prefix+[table,'evidence',index,col,'value'],prefix+[table,'evidence',index,col,'unit']))
        else:
            pairs=[(base+['value'],base+['unit'])]
        for valuepath,unitpath in pairs:
            out.append({'key':'X1.'+key,'file':artifact['localFile'],'sha256':artifact['sha256'],
                        'format':'json','path':valuepath,'unit_path':unitpath,
                        'unit_map':{'元':'CNY','百万元':'CNY_million','%':'%'}})
    return out


def x3_csv(artifact):
    out=[]
    name=artifact['name']
    def add(row,col,key,unit_token,unit):
        out.append(csv_bind(artifact,row,col,'X3.'+key,(unit_token,unit)))
    bridge={
        '合并净利润':'net_profit','资产减值准备':'impairment','信用减值损失':'credit_losses',
        '固定资产等折旧':'depreciation','使用权资产摊销':'lease_amortisation',
        '无形资产摊销':'intangibles','长期待摊费用摊销':'deferred_expenses',
        '处置长期资产损失':'disposals','固定资产报废损失':'retirements',
        '公允价值变动损失':'fair_value','财务费用':'finance',
        '投资损失（收益以负号填）':'investment','递延所得税资产减少':'deferred_tax_asset',
        '递延所得税负债增加':'deferred_tax_liability','存货减少':'inventory',
        '经营性应收项目减少':'receivables','经营性应付项目增加':'payables','其他':'other'}
    if name=='伊利2024经营现金流调节明细.csv':
        for row,key in bridge.items():
            for year in ['2023','2024']:
                add({'项目':row},year+'金额_百万元','bridge_'+key+'_'+year,'百万元','CNY_million')
            add({'项目':row},'同比贡献_百万元','bridge_change_'+key,'百万元','CNY_million')
        for year in ['2023','2024']:
            add({'项目':'经营活动现金流量净额'},year+'金额_百万元','cfo_'+year,'百万元','CNY_million')
        add({'项目':'经营活动现金流量净额'},'同比贡献_百万元','cfo_change','百万元','CNY_million')
    elif name=='核心指标及归母对照.csv':
        for row,key in [('合并净利润','consolidated_profit'),('经营活动现金流量净额','cfo'),
                        ('归母净利润','parent_profit'),('扣非归母净利润','adjusted_parent_profit')]:
            for year in ['2023','2024']:
                add({'项目':row},year+'元',key+'_'+year,year+'元','CNY')
                add({'项目':row},year+'百万元',key+'_'+year,'百万元','CNY_million')
            add({'项目':row},'同比变化_pct',key+'_growth','pct','%')
        add({'项目':'经营活动现金流量净额'},'同比变动百万元','cfo_change','百万元','CNY_million')
    elif name=='cashflow_reconciliation.csv':
        renames={'处置长期资产损失':'处置长期资产损失(收益)',
                 '公允价值变动损失':'公允价值变动损失(收益)',
                 '投资损失（收益以负号填）':'投资损失(收益)',
                 '递延所得税资产减少':'递延所得税资产减少(增加)',
                 '递延所得税负债增加':'递延所得税负债增加(减少)',
                 '存货减少':'存货减少(增加)','经营性应收项目减少':'经营性应收项目减少(增加)',
                 '经营性应付项目增加':'经营性应付项目增加(减少)'}
        for row,key in bridge.items():
            row=renames.get(row,row)
            for year in ['2023','2024']:
                add({'项目':row},year+'元','bridge_'+key+'_'+year,year+'元','CNY')
                add({'项目':row},year+'百万元','bridge_'+key+'_'+year,'百万元','CNY_million')
            add({'项目':row},'同比贡献百万元','bridge_change_'+key,'百万元','CNY_million')
        for year in ['2023','2024']:
            add({'项目':'经营活动现金流量净额'},year+'元','cfo_'+year,year+'元','CNY')
            add({'项目':'经营活动现金流量净额'},year+'百万元','cfo_'+year,'百万元','CNY_million')
        add({'项目':'经营活动现金流量净额'},'同比贡献百万元','cfo_change','百万元','CNY_million')
    elif name=='利润与现金流同比.csv':
        for row,key in [('合并净利润','consolidated_profit'),('归母净利润','parent_profit'),('扣非归母净利润','adjusted_parent_profit'),('经营现金流','cfo')]:
            for year in ['2023','2024']:
                add({'指标':row},year+'百万元',key+'_'+year,'百万元','CNY_million')
            add({'指标':row},'同比变化%',key+'_growth','%','%')
        add({'指标':'经营现金流'},'同比变化百万元','cfo_change','百万元','CNY_million')
    elif name=='现金流调节明细.csv':
        renames={'公允价值变动损失':'公允价值变动损失/收益','投资损失（收益以负号填）':'投资损失/收益抵销',
                 '递延所得税资产减少':'递延所得税资产变动','递延所得税负债增加':'递延所得税负债变动',
                 '经营性应收项目减少':'经营性应收减少','经营性应付项目增加':'经营性应付增加'}
        for row,key in bridge.items():
            for year in ['2023','2024']:
                add({'项目':renames.get(row,row)},year+'百万元','bridge_'+key+'_'+year,'百万元','CNY_million')
            add({'项目':renames.get(row,row)},'同比变化百万元','bridge_change_'+key,'百万元','CNY_million')
        for year in ['2023','2024']:
            add({'项目':'经营现金流'},year+'百万元','cfo_'+year,'百万元','CNY_million')
        add({'项目':'经营现金流'},'同比变化百万元','cfo_change','百万元','CNY_million')
    elif name=='cashflow_reconciliation_detail.csv':
        renames={'公允价值变动损失':'公允价值变动损失（收益）',
                 '投资损失（收益以负号填）':'投资损失（收益以负号）',
                 '递延所得税资产减少':'递延所得税资产变化','递延所得税负债增加':'递延所得税负债变化',
                 '存货减少':'存货减少（增加为负）','经营性应收项目减少':'经营性应收项目减少（增加为负）',
                 '经营性应付项目增加':'经营性应付项目增加（减少为负）'}
        for row,key in bridge.items():
            row=renames.get(row,row)
            for year in ['2023','2024']:
                add({'项目':row},year+'百万元','bridge_'+key+'_'+year,'百万元','CNY_million')
            add({'项目':row},'同比贡献百万元','bridge_change_'+key,'百万元','CNY_million')
    elif name=='key_metrics.csv':
        for row,key in [('合并净利润','consolidated_profit'),('经营活动现金流量净额','cfo'),
                        ('归母扣非净利润','adjusted_parent_profit')]:
            for year in ['2023','2024']:
                add({'指标':row},year+'百万元',key+'_'+year,'百万元','CNY_million')
            add({'指标':row},'同比变化百分比',key+'_growth','百分比','%')
    return out


def x4_csv(artifact):
    # This delivery omits explicit currency/share units in its EPS/price CSV
    # columns. Those cells stay unbound; independent review can read the report.
    out=[]
    if artifact['name']=='yili_forecast_reconciliation.csv':
        for year in ['2025','2026','2027']:
            for col,key in [('revenue_yoy_pct_reported','revenue_growth'),
                            ('revenue_growth_calc_pct','revenue_growth'),
                            ('net_income_yoy_pct_reported','parent_profit_growth'),
                            ('profit_growth_calc_pct','parent_profit_growth')]:
                out.append(csv_bind(artifact,{'year':year},col,'X4.'+key+'_'+year,('pct','%')))
    elif artifact['name']=='伊利预测自洽核验.csv':
        for year in ['2025','2026','2027']:
            for col,key,unit in [('收入_百万元','revenue',('百万元','CNY_million')),
                                 ('归母净利润_百万元','parent_profit',('百万元','CNY_million')),
                                 ('收入增速_计算%','revenue_growth',('%','%')),
                                 ('归母净利增速_计算%','parent_profit_growth',('%','%'))]:
                out.append(csv_bind(artifact,{'年度':year},col,'X4.'+key+'_'+year,unit))
    elif artifact['name']=='forecast_check.csv':
        for year in ['2025','2026','2027']:
            for col,key,unit in [('revenue_RMB_mn','revenue',('RMB_mn','CNY_million')),
                                 ('net_profit_parent_RMB_mn','parent_profit',('RMB_mn','CNY_million')),
                                 ('revenue_growth_reported_pct','revenue_growth',('pct','%')),
                                 ('revenue_growth_calculated_pct','revenue_growth',('pct','%')),
                                 ('net_profit_growth_reported_pct','parent_profit_growth',('pct','%')),
                                 ('net_profit_growth_calculated_pct','parent_profit_growth',('pct','%'))]:
                out.append(csv_bind(artifact,{'year':year},col,'X4.'+key+'_'+year,unit))
        # EPS_RMB has no per-share unit in this CSV; independent review required.
    elif artifact['name']=='forecast_reconciliation.csv':
        for year in ['2025','2026','2027']:
            for col,key,unit in [('revenue_RMB_mn','revenue',('RMB_mn','CNY_million')),
                                 ('parent_profit_RMB_mn','parent_profit',('RMB_mn','CNY_million')),
                                 ('EPS_report_CNY_share','EPS',('CNY_share','CNY/share')),
                                 ('EPS_calc_CNY_share','EPS',('CNY_share','CNY/share')),
                                 ('revenue_growth_report_pct','revenue_growth',('pct','%')),
                                 ('revenue_growth_calc_pct','revenue_growth',('pct','%')),
                                 ('profit_growth_report_pct','parent_profit_growth',('pct','%')),
                                 ('profit_growth_calc_pct','parent_profit_growth',('pct','%'))]:
                out.append(csv_bind(artifact,{'year':year},col,'X4.'+key+'_'+year,unit))
    return out


def x5_csv(artifact,folder):
    out=[]
    def add(row,col,key,percent=False):
        b={'key':'X5.'+key,'file':artifact['localFile'],'sha256':artifact['sha256'],
           'format':'csv','row':row,'column':col}
        if percent:
            b.update(unit_literal='%',unit_map={'%':'%'})
        else:
            b.update(unit_column='单位',unit_map={'人民币百万元':'CNY_million','元/股':'CNY/share'})
        out.append(b)
    if artifact['name']=='yili_2024_forecast_actual_detail.csv':
        for date,prefix in [('2024-11-04','nov'),('2024-10-30','huatai')]:
            for metric,key in [('Revenue','revenue'),('Parent net profit / report net profit','parent_profit'),('EPS','EPS')]:
                row={'report_date':date,'metric':metric}
                for col,gold in [('forecast',prefix+'_'+key+'_forecast'),('actual',key+'_actual'),('actual_minus_forecast',prefix+'_'+key+'_delta')]:
                    out.append({'key':'X5.'+gold,'file':artifact['localFile'],'sha256':artifact['sha256'],'format':'csv','row':row,'column':col,'unit_column':'unit','unit_map':{'RMB million':'CNY_million','RMB/share':'CNY/share'}})
                out.append(csv_bind(artifact,row,'variance_pct_vs_forecast','X5.'+prefix+'_'+key+'_deviation',('pct','%')))
        for metric,key in [('Parent net profit / report net profit','may_profit_unspecified'),('EPS','may_EPS')]:
            out.append({'key':'X5.'+key,'file':artifact['localFile'],'sha256':artifact['sha256'],'format':'csv','row':{'report_date':'2024-05-12','metric':metric},'column':'forecast','unit_column':'unit','unit_map':{'RMB million':'CNY_million','RMB/share':'CNY/share'}})
    elif artifact['name']=='yili_2024_forecast_vs_actual.csv':
        with (folder/artifact['localFile']).open(encoding='utf-8-sig') as f:
            header=next(csv.reader(f))
        if 'institution' in header:
            for date,prefix in [('2024-11-04','nov'),('2024-10-30','huatai')]:
                for field in ['revenue','parent_profit']:
                    for col,key in [(field+'_forecast_mn',prefix+'_'+field+'_forecast'),
                                    (field+'_actual',field+'_actual'),
                                    (field+'_variance_actual_minus_forecast',prefix+'_'+field+'_delta')]:
                        out.append(csv_bind(artifact,{'report_date':date},col,'X5.'+key,('百万元','CNY_million')))
                for field,key in [('revenue','revenue'),('parent_profit','parent_profit'),('eps','EPS')]:
                    out.append(csv_bind(artifact,{'report_date':date},field+'_variance_pct_vs_forecast','X5.'+prefix+'_'+key+'_deviation',('pct','%')))
            return out
        for institution,date,prefix in [('光大证券','2024-11-04','nov'),('华泰研究','2024-10-30','huatai')]:
            for metric,key in [('营业收入','revenue'),('归母净利润','parent_profit'),('EPS','EPS')]:
                row={'机构':institution,'报告日期':date,'指标':metric}
                add(row,'预测值',prefix+'_'+key+'_forecast')
                add(row,'差额(实际-预测)',prefix+'_'+key+'_delta')
                add(row,'偏离率(实际-预测)/预测%',prefix+'_'+key+'_deviation',True)
                add(row,'实际值',key+'_actual')
        for metric,key in [('归母净利润','may_profit_unspecified'),('EPS','may_EPS')]:
            add({'机构':'光大证券','报告日期':'2024-05-12','指标':metric},'预测值',key)
    elif artifact['name']=='everbright_forecast_revision.csv':
        with (folder/artifact['localFile']).open(encoding='utf-8-sig') as f:
            header=next(csv.reader(f))
        if 'metric' in header:
            return out  # This version omits explicit money/share units.
        for metric,key,prefix in [('归母净利润','parent_profit','may_profit_unspecified'),('EPS','EPS','may_EPS')]:
            add({'指标':metric},'5月预测',prefix)
            add({'指标':metric},'11月预测','nov_'+key+'_forecast')
        add({'指标':'EPS'},'调整额(11月-5月)','may_to_nov_EPS_delta')
        add({'指标':'营业收入'},'11月预测','nov_revenue_forecast')
    elif artifact['name']=='forecast_actual_detail.csv':
        for date,prefix in [('2024-11-04','nov'),('2024-10-30','huatai')]:
            for field,key in [('revenue','revenue'),('parent_profit','parent_profit'),('eps','EPS')]:
                out.append(csv_bind(artifact,{'report_date':date},'deviation_pct_'+field,
                                    'X5.'+prefix+'_'+key+'_deviation',('pct','%')))
    return out


def x5_json(artifact,folder):
    out=[]
    if artifact['name']=='calculation.json':
        obj=read(folder/artifact['localFile'])
        def add(path,key,token,unit):
            out.append({'key':'X5.'+key,'file':artifact['localFile'],'sha256':artifact['sha256'],
                        'format':'json','path':path,'unit_literal':token,'unit_map':{token:unit}})
        for i,row in enumerate(obj['comparisons']):
            if row['report_date'] not in ['2024-11-04','2024-10-30']:
                continue
            prefix={'2024-11-04':'nov','2024-10-30':'huatai'}[row['report_date']]
            for field,key in [('revenue','revenue'),('parent_profit','parent_profit'),('eps','EPS')]:
                add(['comparisons',i,'deviation_pct_'+field],prefix+'_'+key+'_deviation','pct','%')
            for field in ['revenue','parent_profit']:
                for column,suffix in [('forecast_','forecast'),('delta_','delta')]:
                    add(['comparisons',i,column+field],prefix+'_'+field+'_'+suffix,'百万元','CNY_million')
                add(['comparisons',i,'actual_'+field],field+'_actual','百万元','CNY_million')
        for field in ['revenue','parent_profit']:
            add(['actual',field],field+'_actual','百万元','CNY_million')
    # These are separately delivered source-backed annual actuals, not forecasts.
    for b in x1_csv(artifact)+x1_json(artifact,folder):
        if b['key'] in ['X1.revenue_2024','X1.parent_profit_2024']:
            b['key']={'X1.revenue_2024':'X5.revenue_actual','X1.parent_profit_2024':'X5.parent_profit_actual'}[b['key']]
            out.append(b)
    return out


def x6_csv(artifact):
    out=[]
    name=artifact['name']
    def add(row,col,key,token,unit):
        out.append(csv_bind(artifact,row,col,'X6.'+key,(token,unit)))
    metrics={'营业收入':'revenue','归母净利润':'parent_profit','经营现金流净额':'cfo',
             '经营活动现金流量净额':'cfo','扣非归母净利润':'adjusted_parent_profit'}
    if name=='q4_yili_2024.csv':
        for row in ['revenue','parent_profit','cfo','deducted_profit']:
            key='adjusted_parent_profit' if row=='deducted_profit' else row
            for col,suffix in [('Q4_2024_derived_CNY_mn','Q4_2024'),('Q4_2024_annual_report_quarter_CNY_mn','Q4_2024'),('Q3_2024_single_quarter_CNY_mn','Q3_2024')]:
                add({'metric':row},col,key+'_'+suffix,'CNY_mn','CNY_million')
            add({'metric':row},'Q4_qoq_pct',key+'_QoQ','pct','%')
            if row!='deducted_profit':
                add({'metric':row},'Q4_2023_derived_CNY_mn',key+'_Q4_2023','CNY_mn','CNY_million')
                add({'metric':row},'Q4_yoy_pct',key+'_YoY','pct','%')
    elif name=='yili_q4_2024_workpaper.csv':
        for row,key in {k:v for k,v in metrics.items() if k!='经营现金流净额'}.items():
            for col,suffix in [('Q4_24_derived_CNY_m','Q4_2024'),('Q4_24_reported_CNY_m','Q4_2024'),('Q3_24_CNY_m','Q3_2024')]:
                add({'metric':row},col,key+'_'+suffix,'CNY_m','CNY_million')
            add({'metric':row},'QoQ_pct',key+'_QoQ','pct','%')
            if key!='adjusted_parent_profit':
                add({'metric':row},'Q4_23_derived_CNY_m',key+'_Q4_2023','CNY_m','CNY_million')
                add({'metric':row},'YoY_pct',key+'_YoY','pct','%')
    elif name in ['quarterly_analysis.csv','yili_2024q4_analysis.csv']:
        rows=metrics if name=='quarterly_analysis.csv' else {k:v for k,v in metrics.items() if k!='经营现金流净额'}
        if name=='quarterly_analysis.csv':rows={k:v for k,v in metrics.items() if k!='经营活动现金流量净额'}
        for row,key in rows.items():
            add({'指标':row},'Q4环比%' if name=='quarterly_analysis.csv' else '环比%',key+'_QoQ','%','%')
            if key!='adjusted_parent_profit':
                add({'指标':row},'Q4同比%' if name=='quarterly_analysis.csv' else '同比%',key+'_YoY','%','%')
        # These custom CSVs lack an explicit currency amount unit. No unit is guessed.
    elif name=='calculation_inputs.csv':
        for label,key in [('收入','revenue'),('归母净利','parent_profit'),('扣非归母净利','adjusted_parent_profit'),('经营现金流','cfo')]:
            for row,period in [('2024Q4披露','Q4_2024'),('2024Q3','Q3_2024')]:
                add({'输入项':row+label},'数值（人民币百万元）',key+'_'+period,'人民币百万元','CNY_million')
    elif name=='quarters.csv':
        for key in ['revenue','parent_profit','cfo','adjusted_parent_profit']:
            for period,suffix in [('2024-Q4','Q4_2024'),('2024-Q3','Q3_2024')]:
                add({'指标':'deducted_profit' if key=='adjusted_parent_profit' else key,'期间':period},'金额（CNY 百万元）',key+'_'+suffix,'CNY 百万元','CNY_million')
    return out


for run in read(study/'experiment.json')['runs']:
    if run['label'] not in ['F1_X1','P1_X1','P1_X3','F1_X3','F1_X4','P1_X4','P1_X5','F1_X5','F1_X6','P1_X6','P2_X1','F2_X1','F2_X3','P2_X3','P2_X4','F2_X4','F2_X5','P2_X5','P2_X6','F2_X6'] or not (study/(run['label']+'-deliverables.json')).exists():
        continue
    catalog=ROOT/'benchmark/blind-eval'/('selectors-phase1.json' if run['taskId'] in ['X4','X5','X6'] else 'selectors-stage-b-additions.json')
    folder=study/(run['label']+'-artifacts')
    bindings=[]
    for artifact in read(study/(run['label']+'-deliverables.json'))['artifacts']:
        if not artifact.get('localFile'):
            continue
        if run['taskId']=='X1':
            bindings.extend(x1_csv(artifact))
            bindings.extend(x1_json(artifact,folder))
        elif run['taskId']=='X3':
            bindings.extend(x3_csv(artifact))
        elif run['taskId']=='X4':
            bindings.extend(x4_csv(artifact))
        elif run['taskId']=='X5':
            bindings.extend(x5_csv(artifact,folder))
            bindings.extend(x5_json(artifact,folder))
        elif run['taskId']=='X6':
            bindings.extend(x6_csv(artifact))
    dest=study/(run['label']+'-numeric-bindings.json')
    dump(dest,{'catalog_sha256':sha(catalog),'tasks':[run['taskId']],'bindings':bindings})
    result=module.grade(catalog,dest,folder)
    dump(study/(run['label']+'-numeric-checks.json'),result)
    print(json.dumps({'label':run['label'],'bound_cells':len(result['checks']),
                      'unbound_gold_keys':len(result['unbound'])}))
