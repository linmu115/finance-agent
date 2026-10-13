"""Deterministic selector and existing A5 CLI integration; no participant model."""
import copy,hashlib,json,runpy,io,uuid
from pathlib import Path
from blind import ROOT,read,dump,document_review,Redactor
HERE=ROOT/'benchmark/blind-eval';OUT=ROOT/'data/evaluation/blind-eval-f1-preparation-20261008/offline-fixtures'
OUT.mkdir(parents=True,exist_ok=True)
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
grade=runpy.run_path(str(HERE/'selectors-f1.py'))['grade']
a5=runpy.run_path(str(HERE/'a5-adapter.py'))
csv=OUT/'result.csv';csv.write_text('metric,value,unit\nrevenue,26660.38,人民币百万元\nwrong,26660.38,港元\nloss,2415.62,人民币百万元\n',encoding='utf8')
catalog=HERE/'selectors-phase1.json'
bindings={'catalog_sha256':sha(catalog),'tasks':['X6'],'bindings':[{'key':'X6.revenue_Q4_2024','file':csv.name,'sha256':sha(csv),'format':'csv','row':{'metric':'revenue'},'column':'value','unit_column':'unit','unit_map':{'人民币百万元':'CNY_million'}},{'key':'X6.revenue_Q4_2024','file':csv.name,'sha256':sha(csv),'format':'csv','row':{'metric':'wrong'},'column':'value','unit_column':'unit','unit_map':{'港元':'HKD'}},{'key':'X6.parent_profit_Q4_2024','file':csv.name,'sha256':sha(csv),'format':'csv','row':{'metric':'loss'},'column':'value','unit_column':'unit','unit_map':{'人民币百万元':'CNY_million'}}]}
dump(OUT/'bindings.json',bindings);result=grade(catalog,OUT/'bindings.json',OUT)
assert [c['status'] for c in result['checks']]==['rounding_consistent','unit_or_currency_mismatch','numeric_mismatch']
assert result['unbound'] and all(x['status']=='unbound_unknown' for x in result['unbound'])
bad=copy.deepcopy(bindings);bad['bindings'][0]['expected']={'value':'wrong'};dump(OUT/'bad-binding.json',bad)
try:grade(catalog,OUT/'bad-binding.json',OUT)
except ValueError as e:assert 'override' in str(e)
else:raise AssertionError('Mutable gold accepted')
dump(OUT/'selector-result.json',result)
tables={'forecast':{'artifact':'forecast.csv','columns':{'year':{},'revenue':{'unit':'百万元','currency':'CNY'},'EPS':{'unit':'元/股','currency':'CNY'}},'rows':[{'year':'2030E','revenue':'1250','EPS':'.72'},{'year':'2031E','revenue':'1700','EPS':'.94'}]}}
answer='|年度|收入（人民币亿元）|EPS（元/股）|\n|---|---|---|\n|2030E|125|0.94|'
label='mock';events=[{'type':'tool_result','data':{'name':'query_financial_data','toolCallId':'s1','result':{'data':{'items':[{'metric':'EPS','value':'.72','period':'2030E','currency':'CNY/share'}]}}}},{'type':'tool_result','data':{'name':'run_analysis','result':{'data':{'numeric_tables':tables}}}}]
(OUT/(label+'-audit.jsonl')).write_text('\n'.join(json.dumps(e) for e in events),encoding='utf8')
(OUT/(label+'-answer.md')).write_text(answer,encoding='utf8');dump(OUT/(label+'-deliverables.json'),{'artifacts':[]})
payload,meta=a5['build_input'](OUT,label);assert len(payload['source_records'])==1;assert payload['tables']==tables;assert meta['source_calls'][0]['toolCallId']=='s1'
scan=a5['invoke'](payload)
assert [c['classification'] for c in scan['checks']]==['order_of_magnitude','wrong_cell'];assert scan['feedback_enabled'] is False
dump(OUT/'a5-input.json',payload);dump(OUT/'a5-result.json',scan)
import fitz,openpyxl
visual=OUT/('documents-'+uuid.uuid4().hex);visual.mkdir()
pdf=fitz.open();page=pdf.new_page();page.insert_text((72,72),'Q4 parent profit -2415.62035216 CNY million')
original_pixels=page.get_pixmap(matrix=fitz.Matrix(1.5,1.5),alpha=False).tobytes('png')
review=document_review(pdf.tobytes(),visual/'report.pdf',Redactor({}));pdf.close()
assert (review/'page-001.png').read_bytes()==original_pixels
assert '-2415.62035216' in (review/'page-001.txt').read_text('utf8')
wb=openpyxl.Workbook();ws=wb.active;ws.title='financial result';ws['A1']='parent profit';ws['B1']=-2415.62035216;ws['B2']='=B1*2';raw=io.BytesIO();wb.save(raw)
review=document_review(raw.getvalue(),visual/'workpaper.xlsx',Redactor({}));cells=read(review/'sheet-001.json')
assert cells['sheet']=='system_component result';assert cells['cells'][1]['value_or_formula']==-2415.62035216;assert cells['cells'][2]['value_or_formula']=='=B1*2';assert cells['cells'][2]['cached_value'] is None
dump(OUT.parent/'document-expansion-test.json',{'passed':True,'PDF_pixels_unchanged':True,'precision_preserved':True,'XLSX_formulas_preserved_unexecuted':True,'XLSX_missing_cache_not_zero':True,'evidence':str(visual.relative_to(ROOT))})
dump(OUT.parent/'selectors-a5-offline-test.json',{'passed':True,'paid_requests':0,'network_requests':0,'checks':['frozen catalog enforced','rounding tolerance','currency mismatch','positive/negative amount mismatch','unbound unknown','gold override rejected','only actual source calls included','full A1 tables forwarded','mainline A5 CLI detects scale and wrong-cell errors','no feedback'], 'a5_cli':'scripts/scan-delivery-consistency.py','a5_result':scan['counts']})
print('Selectors + mainline A5 CLI passed; paid/network requests 0')
