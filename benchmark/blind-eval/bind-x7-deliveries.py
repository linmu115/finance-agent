"""Explicit X7 cell bindings to frozen gold; no numeric search or gold changes."""
import csv, hashlib, importlib.util, json
from pathlib import Path
from blind import ROOT, read, dump
spec=importlib.util.spec_from_file_location('selectors_f1',Path(__file__).with_name('selectors-f1.py'))
grade=importlib.util.module_from_spec(spec);spec.loader.exec_module(grade)
study=ROOT/'data/evaluation/blind-eval-F14-X7-20261008'
catalog=ROOT/'benchmark/blind-eval/selectors-stage-c-X7.json'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()

for run in read(study/'experiment.json')['runs']:
    folder=study/(run['label']+'-artifacts');bindings=[]
    for artifact in read(study/(run['label']+'-deliverables.json'))['artifacts']:
        name=artifact['name'];file=folder/artifact['localFile']
        def add(row,col,key,token,unit):
            bindings.append({'key':'X7.'+key,'file':artifact['localFile'],'sha256':artifact['sha256'],
                             'format':'csv','row':row,'column':col,'unit_literal':token,'unit_map':{token:unit}})
        metrics={'收入':'revenue','营业收入':'revenue','归母净利润':'parent_profit','经营现金流':'cfo','经营活动现金流净额':'cfo','归母净资产':'parent_equity','总资产':'assets'}
        if name in ['haier_key_metrics.csv','haier_restatement_growth.csv']:
            for row,key in {'收入':'revenue','归母净利润':'parent_profit','经营现金流':'cfo'}.items():
                for col,basis in [('按调整后增速%','adjusted'),('按调整前增速%','original')]:
                    add({'指标':row},col,key+'_growth_using_'+basis+'_percent','%','%')
            # Amount columns have no explicit amount unit. Difference columns use
            # the opposite subtraction order to the gold: leave for semantic review.
        elif name=='haier_warranty_reclass.csv':
            for row,key in [('毛利率变化百分点','gross_margin'),('销售费用率变化百分点','sales_expense_ratio')]:
                add({'项目':row},'数值','warranty_'+key+'_adjustment_pp','百分点','pp')
        elif name=='growth_comparison.csv':
            rows=list(csv.DictReader(file.open(encoding='utf-8-sig')))
            if '口径' in rows[0]:
                for row in rows:
                    key=metrics[row['指标']];basis='adjusted' if row['口径']=='调整后' else 'original';where={'指标':row['指标'],'口径':row['口径']}
                    add(where,'2023基数人民币百万元',key+'_2023_'+basis,'人民币百万元','CNY_million')
                    add(where,'2024人民币百万元',key+'_2024','人民币百万元','CNY_million')
                    add(where,'2024同比%',key+'_growth_using_'+basis+'_percent','%','%')
            else:
                for row in rows:
                    key=metrics[row['指标']]
                    for col,basis in [('增速_调整后基数_%','adjusted'),('增速_调整前基数_%','original')]:
                        add({'指标':row['指标']},col,key+'_growth_using_'+basis+'_percent','%','%')
                    add({'指标':row['指标']},'选错列影响_百分点',key+'_growth_difference_pp','百分点','pp')
        elif name in ['haier_nonrecurring.csv','nonrecurring_items.csv'] and run['profile']=='prepared':
            rows=list(csv.DictReader(file.open(encoding='utf-8-sig')))
            for row in rows:
                key='government_grants' if row['项目'].startswith('政府补助') else 'net_parent_contribution' if row['项目']=='非经常性损益合计' else None
                if key:
                    for year in ['2023','2024']:add({'项目':row['项目']},year+'人民币元',key+'_'+year,'人民币元','CNY')
        elif name=='restatement_adjustments.csv':
            for row,key in {k:v for k,v in metrics.items() if k in ['收入','归母净利润','经营现金流','归母净资产','总资产']}.items():
                for col,suffix in [('2023调整后人民币百万元','2023_adjusted'),('2023调整前人民币百万元','2023_original'),('调整额(后-前)人民币百万元','adjustment_2023')]:
                    add({'指标':row},col,key+'_'+suffix,'人民币百万元','CNY_million')
        elif name=='adjustments.csv':
            for row in ['revenue','parent_profit','deducted_profit','cfo','parent_equity','assets']:
                key='adjusted_parent_profit' if row=='deducted_profit' else row
                for col,suffix in [('调整前（CNY 百万元）','2023_original'),('调整后（CNY 百万元）','2023_adjusted'),('调整后减前（CNY 百万元）','adjustment_2023')]:
                    add({'指标':row},col,key+'_'+suffix,'CNY 百万元','CNY_million')
            for col,suffix,token,unit in [('调整前（%）','2023_original','%','%'),('调整后（%）','2023_adjusted','%','%'),('调整后减前（个百分点）','2023_adjustment_pp','个百分点','pp')]:
                add({'指标':'weighted_roe'},col,'weighted_ROE_'+suffix,token,unit)
        elif name=='margin_roe.csv':
            for row,suffix in [('2023调整前','2023_original'),('2023调整后','2023_adjusted'),('2024','2024')]:
                add({'比较期间':row},'归母净利率_%','parent_margin_'+suffix,'%','%')
                add({'比较期间':row},'披露加权ROE_%','weighted_ROE_'+('reported_percent_2024' if suffix=='2024' else suffix),'%','%')
        elif name=='margin_and_roe.csv':
            for row,key in [('2023归母净利率','parent_margin'),('披露加权平均ROE','weighted_ROE')]:
                for col,suffix,token,unit in [('调整后%','2023_adjusted','%','%'),('调整前%','2023_original','%','%'),('后减前百分点','2023_adjustment_pp','百分点','pp')]:
                    add({'指标':row},col,key+'_'+suffix,token,unit)
            for col in ['调整后%','调整前%']:add({'指标':'2024归母净利率'},col,'parent_margin_2024','%','%')
        elif name=='eps_roe.csv':
            for col,suffix in [('调整后','2023_adjusted'),('调整前','2023_original')]:
                add({'指标':'加权平均ROE（%）'},col,'weighted_ROE_'+suffix,'%','%')
            # Difference unit is not explicit in this file; no pp guess.
        elif name=='warranty_ratios.csv':
            for row,before,after,change in [('毛利率','same_scope_before_this_policy_gross_margin_percent','reported_adjusted_gross_margin_percent','gross_margin_adjustment_pp'),('销售费用率','same_scope_before_this_policy_sales_ratio_percent','reported_adjusted_sales_ratio_percent','sales_expense_ratio_adjustment_pp')]:
                for col,key,token,unit in [('重分类前_%',before,'%','%'),('重分类后_%',after,'%','%'),('变化_百分点',change,'百分点','pp')]:add({'项目':row},col,'warranty_'+key,token,unit)
        elif name=='warranty_reclassification.csv':
            rows=list(csv.DictReader(file.open(encoding='utf-8-sig')))
            if '单位' in rows[0]:
                for row,key,token,unit in [('2023政策重分类金额','cost_adjustment_CNY','人民币百万元','CNY_million'),('以2023调整后收入为分母的毛利率影响','gross_margin_adjustment_pp','百分点','pp'),('以2023调整后收入为分母的销售费用率影响','sales_expense_ratio_adjustment_pp','百分点','pp'),('营业利润影响(纯重分类)','operating_profit_effect_CNY','人民币百万元','CNY_million')]:add({'项目':row},'值','warranty_'+key,token,unit)
            elif '金额或百分点' in rows[0]:
                for row,key in [('毛利率影响（百分点）','gross_margin'),('销售费用率影响（百分点）','sales_expense_ratio')]:add({'项目':row},'金额或百分点','warranty_'+key+'_adjustment_pp','百分点','pp')
        elif name=='column_comparison.csv':
            for row,key in [('收入(百万元)','revenue'),('归母净利润(百万元)','parent_profit'),('经营现金流(百万元)','cfo')]:
                for col,suffix in [('2024年','2024'),('2023调整后口径比较','2023_adjusted'),('2023调整前口径比较','2023_original')]:add({'指标':row},col,key+'_'+suffix,'人民币百万元','CNY_million')
            for row,key in [('收入增速','revenue'),('归母净利润增速','parent_profit'),('经营现金流增速','cfo')]:
                for col,basis in [('2024年','adjusted'),('2023调整后口径比较','adjusted'),('2023调整前口径比较','original')]:add({'指标':row},col,key+'_growth_using_'+basis+'_percent','%','%')
            for row,key in [('归母净利率','parent_margin'),('披露加权ROE','weighted_ROE')]:
                for col,suffix in [('2024年','2024'),('2023调整后口径比较','2023_adjusted'),('2023调整前口径比较','2023_original')]:add({'指标':row},col,key+'_'+('reported_percent_2024' if key=='weighted_ROE' and suffix=='2024' else suffix),'%','%')
            # Change-row column labels do not identify the intended comparison;
            # do not silently remap their apparent values to expected gold.
        elif name in ['workpaper.json','numeric_tables.json','chart_data.json']:
            obj=read(file);prefix=[] if name=='numeric_tables.json' else ['tables'];tables=obj if not prefix else obj['tables'];cells=[]
            for year in ['2023','2024']:
                period=year+'-FY';suffix=year if year=='2024' else '2023_adjusted'
                cells += [('income','revenue',period,'revenue_'+suffix),('profit_attribution',period,'parent','parent_profit_'+suffix),('cash',period+'_cfo','amount','cfo_'+suffix),('roe',period,'end','parent_equity_'+suffix),('roe',period,'weighted','weighted_ROE_'+('reported_percent_2024' if year=='2024' else suffix)),('deducted_profit',period,'disclosed','adjusted_parent_profit_'+suffix),('deducted_profit',period,'calculated','adjusted_parent_profit_'+suffix),('deducted_profit',period,'nonrecurring','net_parent_contribution_'+year)]
            cells += [('growth','revenue','change','revenue_growth_using_adjusted_percent'),('growth','parent_profit','change','parent_profit_growth_using_adjusted_percent'),('ratios','gross_profit_margin','2023-FY','warranty_reported_adjusted_gross_margin_percent'),('ratios','selling_margin','2023-FY','warranty_reported_adjusted_sales_ratio_percent')]
            for table,rowkey,col,key in cells:
                indices=[i for i,r in enumerate(tables[table]['rows']) if r['key']==rowkey];assert len(indices)==1
                i=indices[0];base=prefix+[table,'rows',i,col]
                pairs=[(base+['value'],base+['unit'])] if name=='workpaper.json' else [(base,prefix+[table,'columns',col,'unit']),(prefix+[table,'evidence',i,col,'value'],prefix+[table,'evidence',i,col,'unit'])]
                for valuepath,unitpath in pairs:bindings.append({'key':'X7.'+key,'file':artifact['localFile'],'sha256':artifact['sha256'],'format':'json','path':valuepath,'unit_path':unitpath,'unit_map':{'元':'CNY','百万元':'CNY_million','%':'%'}})
    dest=study/(run['label']+'-numeric-bindings.json');dump(dest,{'catalog_sha256':sha(catalog),'tasks':['X7'],'bindings':bindings})
    result=grade.grade(catalog,dest,folder);dump(study/(run['label']+'-numeric-checks.json'),result)
    print(json.dumps({'label':run['label'],'bound':len(result['checks']),'unbound':len(result['unbound'])}))
