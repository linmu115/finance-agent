"""Known Moutai disclosure-boundary regressions, deliberately outside the holdout."""
import json,hashlib,sqlite3
from pathlib import Path
import fitz
root=Path(__file__).resolve().parents[1]
doc='39de9b118212463bbee6c2ab3c571432'
source=root/'samples/native-pdf/贵州茅台2024年年度报告.pdf'
source_sha=hashlib.sha256(source.read_bytes()).hexdigest()
assert source_sha=='5299f4940e2ce4e91084b73dc457d558b9d335fa76fbfee6227e4254eb7f4a30'
specs=[
 ('main_direct',17,33,3,2,'74843327030.79','主营业务构成中的直销收入'),
 ('all_direct',108,193,12,4,'74911586867.82','全部营业收入分解中的直销收入，包含其他业务'),
 ('main_wholesale',17,33,2,2,'95768511021.23','主营业务构成中的批发代理收入'),
 ('all_wholesale',108,193,11,4,'95987565408.52','全部营业收入分解中的批发代理收入'),
 ('main_domestic',17,33,6,2,'165423308808.24','主营业务构成中的国内收入'),
 ('all_domestic',108,193,8,4,'165695304320.02','全部营业收入分解中的国内收入'),
 ('main_total',108,192,3,2,'170611838052.02','主营业务收入'),
 ('other_total',108,192,4,2,'287314224.32','其他业务收入，主要为酒店及冰淇淋'),
 ('all_total',108,192,5,2,'170899152276.34','全部营业收入'),
 ('lease_noncurrent',106,184,2,2,'313906415.76','长期租赁负债，不含一年内到期部分'),
 ('lease_current',106,182,2,2,'111951112.20','一年内到期的租赁负债'),
 ('lease_all',115,218,3,7,'425857527.96','租赁负债期末余额，包含一年内到期部分'),
 ('grant_income',111,201,3,2,'4539419.20','其他收益中与收益相关的政府补助'),
 ('grant_all',122,232,3,2,'4539419.20','计入当期损益的政府补助合计'),
 ('grant_nonrecurring',142,273,3,2,'4539419.20','排除与正常经营密切相关、按固定标准享有且持续影响损益的政府补助')]
facts=[]
with sqlite3.connect((root/'data/finance.sqlite').as_uri()+'?mode=ro',uri=True) as db,fitz.open(source) as pdf:
 for name,page,table,row,col,value,meaning in specs:
  saved=db.execute('SELECT page,rows_json FROM source_tables WHERE table_id=?',(doc+':t'+str(table),)).fetchone()
  rows=json.loads(saved[1]);raw=rows[row-1][col-1]
  assert saved[0]==page and raw.replace(',','')==value,(name,raw,value)
  assert raw in pdf[page-1].get_text(),name
  facts.append({'id':name,'meaning':meaning,'value':value,'raw_value':raw,'raw_unit':'元','currency':'CNY','scope':'consolidated_CAS','source':{'document_id':doc,'original_page':page,'table_id':doc+':t'+str(table),'row':row,'column':col,'row_text':' | '.join(rows[row-1])}})
 excerpts={str(page):pdf[page-1].get_text() for page in [16,17,106,108,111,115,122,142]}
payload={'kind':'known_development_regression_not_holdout','source_sha256':source_sha,'project_id':'3b4c43c9-51b8-432c-807d-2a15323f7a80','facts':facts,'original_pdf_page_text':excerpts,
 'assertions':[
  {'id':'revenue_business_boundary','different_definition_pairs':[['main_direct','all_direct'],['main_wholesale','all_wholesale'],['main_domestic','all_domestic'],['main_total','all_total']],'requirement':'Same channel or region does not erase main-business versus all-operating-revenue coverage. Query identity must preserve this economic distinction using meaningful metric/measurement dimensions, not only source IDs or page numbers.','source_basis':'Page16 heading continues onto17; page108 separately reports main, other, and total, and explains hotel/ice-cream other business.'},
  {'id':'lease_maturity_boundary','different_definition_pairs':[['lease_noncurrent','lease_current'],['lease_noncurrent','lease_all'],['lease_current','lease_all']],'requirement':'Gross including current maturities, current maturities, and noncurrent balance must remain distinguishable after ignoring movement/counterparty axes. An opening/closing movement dimension alone does not encode liability maturity coverage.','source_basis':'Page106 separately lists current and long-term balances; page115 explicitly includes the portion due within one year. Exact aggregate relation: 313906415.76 + 111951112.20 = 425857527.96.'},
  {'id':'grant_exclusion_boundary','different_definition_pairs':[['grant_income','grant_nonrecurring'],['grant_all','grant_nonrecurring']],'requirement':'Numerical equality in this report is not proof of interchangeable definitions. General income-related grants do not acquire the explicit nonrecurring exclusion clause through a catalog alias.','source_basis':'Pages111/122 are general other-income/government-grant notes; page142 explicitly excludes specified normal-business, standard-based and recurring-effect grants.'}],
 'invariants':['Preserve all source cells and exact raw/normalized amounts, currencies and raw units.','For the later scope-only review, compare dates to a separate snapshot taken after the temporal review and before the scope review; no date edits are authorized by these semantic scope assertions.','Require actual owning Pi output, original source evidence and persisted before/after metadata. A model statement that it finished is not a pass.','Do not change the frozen v0.3/v0.3.1 answers or scores. These known cases are not included in v0.4 holdout.']}
target=root/'benchmark/results/known-disclosure-scope-assertions.json'
with target.open('x',encoding='utf-8') as h:json.dump(payload,h,ensure_ascii=False,indent=2)
print(json.dumps({'output':str(target),'anchors':len(facts),'families':3},ensure_ascii=False))
