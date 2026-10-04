"""Independent company-held-out source transcription. Never read model outputs."""
from pathlib import Path
from datetime import datetime, timezone
from decimal import Decimal
import hashlib, json, re, shutil, subprocess
import fitz

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'benchmark/versions/v0.4.1-holdout'
SOURCE=ROOT/'samples/holdout-sources'
if OUT.exists():raise SystemExit('Refusing to overwrite locked materials')
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
selection={'shenhua_2024':[8,9,143],'liugong_2024':[6,7,8,138]}
sources=json.loads((SOURCE/'manifest.json').read_text(encoding='utf8'))['reports']
(OUT/'inputs').mkdir(parents=True);(OUT/'evidence').mkdir()
inputs=[];texts={}
for ident,pages in selection.items():
 source=next(s for s in sources if s['id']==ident);original=SOURCE/source['filename']
 assert sha(original)==source['sha256']
 with fitz.open(original) as d,fitz.open() as excerpt:
  for page in pages:
   excerpt.insert_pdf(d,from_page=page-1,to_page=page-1)
   texts[ident,page]=d[page-1].get_text()
   (OUT/'evidence'/f'{ident}-original-page-{page}.txt').write_text(texts[ident,page],encoding='utf8')
   shutil.copyfile(SOURCE/'visual'/f'{ident}-{page}.png',OUT/'evidence'/f'{ident}-original-page-{page}.png')
  filename=ident+'_holdout.pdf';excerpt.save(OUT/'inputs'/filename,garbage=4,deflate=True)
 inputs.append({'file':filename,'company_id':ident,'sha256':sha(OUT/'inputs'/filename),'source':source,'pages':[{'input_page':i,'original_page':p} for i,p in enumerate(pages,1)]})

gold=[]
def add(company,page,label,raw,period,concept,metric=None,version='original',unit='CNY',scale='1',definition=None):
 assert raw in texts[company,page],(company,page,raw)
 n=raw.replace(',','').replace('(','-').replace(')','').replace('%','')
 instant=len(period)==10;year=period[:4]
 start,end=('' if instant else year+'-01-01'),(period if instant else year+'-12-31')
 if '-Q' in period:
  q=int(period[-1]);start=year+['-01-01','-04-01','-07-01','-10-01'][q-1];end=year+['-03-31','-06-30','-09-30','-12-31'][q-1]
 rawunits=['百万元','人民币百万元','CNY million'] if scale=='1000000' else ['%','百分比','percent'] if unit=='percent' else ['元/股','人民币元/股','CNY/share'] if unit=='CNY/share' else ['元','人民币元','CNY']
 gold.append({'id':f'{company}_{page}_{len(gold)+1:02d}','input_file':company+'_holdout.pdf','company_id':company,'page':selection[company].index(page)+1,'original_page':page,'source_row_label':label,'raw_value':raw,'value':format(Decimal(n)*Decimal(scale),'f'),'concept':concept,'metric':metric,'period':period,'period_start':start,'period_end':end,'scope':'consolidated_CAS','currency':unit,'version':version,'definition_regex':definition,'period_variants':[],'raw_unit_values':rawunits,'source_evidence':f'evidence/{company}-original-page-{page}.txt'})

S='shenhua_2024';L='liugong_2024'
add(S,8,'营业收入','338,375','2024-FY','revenue','revenue',scale='1000000')
add(S,8,'营业收入','343,074','2023-FY','revenue','revenue',scale='1000000')
add(S,8,'归属于本公司股东的净利润','69,648','2022-FY','parent_profit','net_profit_parent',version='restated',scale='1000000')
add(S,8,'归属于本公司股东的净利润','69,626','2022-FY','parent_profit','net_profit_parent',scale='1000000')
add(S,8,'资产总计','658,068','2024-12-31','assets','assets',scale='1000000')
add(S,8,'负债合计','151,761','2023-12-31','liabilities','liabilities',scale='1000000')
add(S,9,'基本每股收益','2.953','2024-FY','basic_eps','eps',unit='CNY/share')
add(S,9,'基本每股收益','3.505','2022-FY','basic_eps','eps',unit='CNY/share',version='restated')
add(S,9,'基本每股收益','3.504','2022-FY','basic_eps','eps',unit='CNY/share')
add(S,9,'加权平均净资产收益率','14.04','2024-FY','weighted_roe','roe',unit='percent')
for raw,period in [('16,928','2024-FY'),('17,578','2023-FY')]:
 add(S,143,'所得税费用',raw,period,'income_tax_expense',scale='1000000',definition=r'所得税.*(?:费用|expense)|income.?tax(?:ation)?.?(?:expense|cost)|tax.?expense')
for raw,period in [('(128)','2024-FY'),('(285)','2023-FY')]:
 add(S,143,'信用减值损失',raw,period,'credit_impairment_loss',scale='1000000',definition=r'信用减值|credit.?impairment|credit.?loss')
add(S,143,'营业利润','88,362','2024-FY','operating_profit',scale='1000000',definition=r'营业利润|operating.?(?:profit|income)')
add(L,6,'营业收入','30,062,709,198.12','2024-FY','revenue','revenue')
add(L,6,'营业收入','27,519,122,309.99','2023-FY','revenue','revenue')
add(L,6,'归属于上市公司股东的净利润','1,327,039,490.08','2024-FY','parent_profit','net_profit_parent')
add(L,7,'总资产','47,907,158,015.10','2024-12-31','assets','assets')
add(L,7,'总资产','46,578,044,988.89','2023-12-31','assets','assets')
add(L,7,'基本每股收益','0.6824','2024-FY','basic_eps','eps',unit='CNY/share')
add(L,7,'营业收入','7,938,822,313.26','2024-Q1','revenue','revenue')
add(L,7,'营业收入','7,206,777,514.24','2024-Q4','revenue','revenue')
for q,raw in enumerate(['-41,337,175.89','1,163,064,871.35','-44,150,439.69','244,429,009.47'],1):
 add(L,8,'经营活动产生的现金流量净额',raw,f'2024-Q{q}','operating_cash_flow','operating_cash_flow')
add(L,138,'货币资金','8,359,707,174.85','2024-12-31','cash_funds',definition=r'货币资金|cash.?(?:funds|and.?cash.?equivalents)|monetary.?(?:funds|assets)')
add(L,138,'应收账款','10,246,089,993.94','2024-12-31','accounts_receivable',definition=r'应收账款|accounts?.?receivable|trade.?receivables?')
add(L,138,'应收账款','8,176,134,587.50','2023-12-31','accounts_receivable',definition=r'应收账款|accounts?.?receivable|trade.?receivables?')
assert len(gold)==30
(OUT/'gold.jsonl').write_text(''.join(json.dumps(g,ensure_ascii=False)+'\n' for g in gold),encoding='utf8')
relations=[{'id':'profit_tax_credit_loss_are_distinct','company_id':S,'concepts':['operating_profit','income_tax_expense','credit_impairment_loss'],'rule':'distinct_semantic_definitions_not_only_distinct_source_coordinates'},
           {'id':'cash_and_receivables_are_distinct','company_id':L,'concepts':['cash_funds','accounts_receivable'],'rule':'distinct_semantic_definitions_not_only_distinct_source_coordinates'}]
(OUT/'relations.json').write_text(json.dumps(relations,ensure_ascii=False,indent=2),encoding='utf8')
shutil.copyfile(SOURCE/'historical-name-scan.json',OUT/'evidence/historical-name-scan.json')
# Exact identifiers/SHA were not present before these files were authored. Digit
# substrings in old floating-point coordinates are not company identifiers.
audit={}
for term in ['中国神华','柳工',r'(?<!\d)(?:601088|000528)(?!\d)',*[s['sha256'] for s in sources]]:
 p=subprocess.run(['rg','--pcre2','-l',term,'benchmark','data','tests','server','service','samples/native-pdf','--glob','!versions/v0.4.1-holdout/**','--glob','!*.pdf','--glob','!*.png','--glob','!*.pyc','--glob','!*.sqlite*'],cwd=ROOT,capture_output=True,text=True,encoding='utf8')
 hits=[x for x in p.stdout.splitlines() if 'v0.4.1-holdout' not in x]
 assert not hits,(term,hits)
 audit[term]={'matching_historical_files':hits,'exit_code':p.returncode}
(OUT/'evidence/company-holdout-audit.json').write_text(json.dumps({'at':datetime.now(timezone.utc).isoformat(),'checks':audit,'raw_substring_matches_review':'Ticker substrings only occur inside FinQA floating-point scores and historic PDF coordinates; standalone ticker regex has zero hits. Company names have zero historical hits.','scope':'Repository benchmark, application, source samples and live data audit/index export text; SQLite data not itself searched; no absolute guarantee about pretrained-model corpora.'},ensure_ascii=False,indent=2),encoding='utf8')
manifest={'version':'v0.4.1-holdout','status':'locked_before_first_model_run','locked_at':datetime.now(timezone.utc).isoformat(),'supersedes_withdrawn_proposal':'v0.4-holdout',
 'sampling':'Company-held-out purposive stratified challenge. Two new companies selected before model predictions, one energy and one machinery manufacturer. General published financial statements, annual/quarterly periods, prior restatements, units, signed values and ordinary asset classification. Not tailored to the three known Moutai disclosure-definition failures; not random.',
 'pollution_limit':'Public reports may occur in pretraining. Historical repository checks establish these company reports were not used in this project before holdout preparation, not contamination-free blindness.',
 'input_count':2,'source_pages':7,'scored_cells':30,'inputs':inputs,'gold_sha256':sha(OUT/'gold.jsonl'),'relations_sha256':sha(OUT/'relations.json'),
 'coverage':['new companies and industries','three-year multirow restatement columns','annual and individual-quarter flows','year-end balances','CNY million and base CNY','CNY/share and percent','parenthesized and minus-signed negatives','unknown ordinary financial concepts','cross-page quarter headings','grounded source citations'],
 'not_covered':['exhaustive extraction precision/recall','OCR','foreign currencies','full-report completeness','industry-wide accuracy','official competition grading'],
 'protocol':['One formal run after all production/scorer/model/input/gold hashes are frozen.','Gold remains host-side; only unannotated original page PDFs and a generic processing request enter Pi.','Thirty fixed cells scored by exact decimal plus period/units/currency/scope/version/concept/source.','Preserve every failure/retry and all first-run artifacts.','Any implementation correction after seeing outcomes demotes this suite to development; choose new untouched companies for another holdout.']}
(OUT/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf8')
print(json.dumps({'version':manifest['version'],'count':len(gold),'gold_sha256':manifest['gold_sha256'],'inputs':[{'file':i['file'],'sha256':i['sha256']} for i in inputs]},ensure_ascii=False))
