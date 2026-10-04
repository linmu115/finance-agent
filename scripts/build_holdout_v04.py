"""Prepare an independently transcribed, source-verified challenge set before inference."""
import hashlib
import json
from pathlib import Path
from datetime import datetime, timezone
import fitz

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'benchmark/versions/v0.4-holdout'
if OUT.exists():raise SystemExit('Refusing to overwrite locked holdout material')
(OUT/'inputs').mkdir(parents=True)
(OUT/'evidence').mkdir()
sources=json.loads((ROOT/'samples/native-pdf/manifest.json').read_text(encoding='utf-8'))['reports']
selection={'yili_2024':[7,199],'haier_2024':[10,11,193,194,202]}
inputs=[];texts={}
sha=lambda path:hashlib.sha256(path.read_bytes()).hexdigest()
for report_id,pages in selection.items():
    source=next(r for r in sources if r['id']==report_id)
    original=ROOT/'samples/native-pdf'/source['filename']
    assert sha(original)==source['sha256']
    filename=report_id+'_holdout.pdf'
    with fitz.open(original) as document,fitz.open() as excerpt:
        for index,page in enumerate(pages,1):
            excerpt.insert_pdf(document,from_page=page-1,to_page=page-1)
            text=document[page-1].get_text();texts[(report_id,page)]=text
            (OUT/'evidence'/f'{report_id}-original-page-{page}.txt').write_text(text,encoding='utf-8')
        excerpt.save(OUT/'inputs'/filename,garbage=4,deflate=True)
    inputs.append({'file':filename,'company_id':report_id,'sha256':sha(OUT/'inputs'/filename),'source':source,
                   'pages':[{'input_page':i,'original_page':p,'context_only':report_id=='haier_2024' and p==193} for i,p in enumerate(pages,1)]})

gold=[]
def add(company,page,label,raw,period,concept,metric=None,version='original',unit='CNY',definition=None,variants=None):
    assert raw in texts[(company,page)],(company,page,raw)
    input_page=selection[company].index(page)+1
    instant=len(period)==10
    item={'id':f'{company}_{page}_{len(gold)+1:02d}','input_file':company+'_holdout.pdf','company_id':company,
          'page':input_page,'original_page':page,'source_row_label':label,'raw_value':raw,'value':raw.replace(',',''),
          'concept':concept,'metric':metric,'period':period,'period_start':'' if instant else period[:4]+'-01-01',
          'period_end':period if instant else period[:4]+'-12-31','scope':'consolidated_CAS','currency':unit,
          'version':version,'definition_regex':definition,'period_variants':variants or [],
          'source_evidence':'evidence/'+f'{company}-original-page-{page}.txt'}
    gold.append(item)

Y='yili_2024';H='haier_2024'
add(Y,7,'营业收入','115,393,310,976.69','2024-FY','revenue','revenue')
add(Y,7,'营业收入','125,758,168,916.51','2023-FY','revenue','revenue')
add(Y,7,'总资产','153,718,003,927.97','2024-12-31','assets','assets')
add(Y,7,'归属于上市公司股东的净利润','8,452,859,993.18','2024-FY','parent_profit','net_profit_parent')
add(Y,7,'基本每股收益','1.33','2024-FY','basic_eps','eps',unit='CNY/share')
add(Y,7,'加权平均净资产收益率','15.81','2024-FY','weighted_roe','roe',unit='percent')
gross=r'应付租赁款|租赁.*(?:总额|全部|含.*(?:流动|到期))|gross|total|before.*(?:current|deduct)'
net=r'长期|非流动|扣除.*(?:一年|流动)|non.?current|long.?term|exclude|net'
current=r'一年内到期|流动部分|current|within.?one.?year'
for label,values,concept,definition in [
 ('应付租赁款',['380,065,792.96','378,253,025.68'],'lease_gross',gross),
 ('一年内到期的租赁负债',['-117,130,579.80','-140,736,182.96'],'lease_current_deduction',current),
 ('合计',['262,935,213.16','237,516,842.72'],'lease_noncurrent',net)]:
    for index,raw in enumerate(values):
        p='2024-12-31' if index==0 else '2023-12-31'
        add(Y,199,label,raw,p,concept,definition=definition,variants=['2024-01-01'] if index else None)
for label,metric,values,periods in [
 ('营业收入','revenue',['285,981,225,203.93','274,204,520,847.97','261,427,783,050.10'],['2024-FY','2023-FY','2023-FY']),
 ('总资产','assets',['290,113,822,824.61','261,067,684,897.49','253,379,859,977.97'],['2024-12-31','2023-12-31','2023-12-31'])]:
    for index,(raw,p) in enumerate(zip(values,periods)):add(H,10,label,raw,p,metric,metric,version='restated' if index==1 else 'original')
add(H,10,'经营活动产生的现金流量净额','26,535,780,568.36','2023-FY','operating_cash_flow','operating_cash_flow',version='restated')
add(H,10,'经营活动产生的现金流量净额','25,262,376,228.30','2023-FY','operating_cash_flow','operating_cash_flow')
add(H,11,'基本每股收益','2.02','2024-FY','basic_eps','eps')
gold[-1]['currency']='CNY/share'
add(H,11,'加权平均净资产收益率','17.70','2024-FY','weighted_roe','roe',unit='percent')
add(H,194,'租赁负债','5,832,149,696.39','2024-12-31','lease_gross',definition=gross)
add(H,194,'减：一年内到期的租赁负债','1,351,253,699.03','2024-12-31','lease_current_deduction',definition=current)
add(H,194,'合计','4,480,895,997.36','2024-12-31','lease_noncurrent',definition=net)
add(H,202,'与收益相关的政府补助','1,575,833,075.28','2024-FY','income_related_grants',definition=r'与收益相关|income.?related|related.?to.?income')
add(H,202,'与收益相关的政府补助','1,591,337,200.11','2023-FY','income_related_grants',definition=r'与收益相关|income.?related|related.?to.?income')
add(H,202,'与资产相关的政府补助','128,449,305.44','2024-FY','asset_related_grants',definition=r'与资产相关|asset.?related|related.?to.?assets')
add(H,202,'合计','1,704,282,380.72','2024-FY','other_income_total',definition=r'其他收益|other.?income|政府补助.*合计|government.?grants.?total')
add(H,202,'处置长期股权投资产生的投资收益','-26,833,481.45','2024-FY','long_term_equity_disposal_income',definition=r'处置.*长期股权|disposal.*long.?term.*equity')
assert len(gold)==30
(OUT/'gold.jsonl').write_text(''.join(json.dumps(g,ensure_ascii=False)+'\n' for g in gold),encoding='utf-8')
relations=[{'id':'yili_lease_maturity','company_id':Y,'concepts':['lease_gross','lease_current_deduction','lease_noncurrent'],'rule':'distinct_semantic_definitions_not_only_distinct_source_coordinates'},
           {'id':'haier_lease_maturity','company_id':H,'concepts':['lease_gross','lease_current_deduction','lease_noncurrent'],'rule':'distinct_semantic_definitions_not_only_distinct_source_coordinates'},
           {'id':'haier_grant_types','company_id':H,'concepts':['income_related_grants','asset_related_grants','other_income_total'],'rule':'distinct_semantic_definitions_not_only_distinct_source_coordinates'}]
(OUT/'relations.json').write_text(json.dumps(relations,ensure_ascii=False,indent=2),encoding='utf-8')
manifest={'version':'v0.4-holdout','status':'locked_before_first_model_run','locked_at':datetime.now(timezone.utc).isoformat(),
 'sampling':'Purposive stratified challenge set: two locally available 2024 reports unused for this iteration of model-driven implementation tuning; summary multirow restatements, ratios, lease maturity decomposition and grants/investment notes. Pages chosen by accounting concept coverage and native-text legibility, never by model predictions. Not random sampling.',
 'pollution_limit':'Public annual reports may be in pretraining. File-download and native-text usability inspection predate this selection. Claim only implementation-frozen, not previously tuned source regression transfer; never claim contamination-free blindness or general population accuracy.',
 'protocol':['Keep v0.3/v0.3.1 as development regression, with all prior failures preserved.','Freeze production, runtime model/configuration and all input/gold/scorer hashes before one real public-conversation run.','Gold and relations stay on the host, outside model inputs.','Score every one of the 30 cells with exact decimals plus period, unit, currency, scope, version, meaning and native source reference. No partial tolerance for wrong scale or sign.','Count missing cells, contradictory same-cell records, failed runs and retries explicitly.','If implementation changes after viewing outcomes, demote this suite to development regression and select a new untouched source set. Never revise these answers to match predictions.'],
 'input_count':2,'source_pages':7,'scored_cells':30,'inputs':inputs,
 'gold_sha256':sha(OUT/'gold.jsonl'),'relations_sha256':sha(OUT/'relations.json'),
 'coverage':['new companies','native multirow adjusted/unadjusted prior columns','annual flows vs year-end balances','CNY vs CNY/share vs percent','negative and positive displayed deduction conventions','lease gross/current/noncurrent meanings','income-related vs asset-related grants','negative disposal income','source-grounded citations'],
 'not_covered':['full-report completeness','OCR','foreign currencies in this holdout','broad industry representativeness','all difficult accounting concepts','official competition grading']}
(OUT/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'directory':str(OUT),'cells':len(gold),'gold_sha256':manifest['gold_sha256'],'inputs':[{'file':i['file'],'sha256':i['sha256']} for i in inputs]},ensure_ascii=False))
