"""N1 readiness inventory from saved read-only snapshot, not a whole-library grade."""
import json
from decimal import Decimal
from blind import ROOT,read,dump
base=ROOT/'data/evaluation/blind-eval-f1-preparation-20261008'
snapshot=read(base/'materials-readonly-current.json');gold=read(ROOT/'benchmark/blind-eval/reference-phase1.json')
y=snapshot['374beac2-a970-4972-b210-e91018bbd6e6'];sources=[]
for name,src in gold['sources'].items():
 doc=next(d for d in y['documents'] if d['document_id']==src['document_id'])
 pdf=next(d for d in y['source_files'] if d['document_id']==src['document_id'])
 pages=[p['page'] for p in y['pages'] if p['document_id']==src['document_id']]
 sources.append({'source':name,'document_id':doc['document_id'],'state':doc['state'],'pdf_sha_matches_gold':pdf['sha256']==src['sha256'],'required_pages_present':all(p in pages for p in src['visually_verified_pdf_pages']),'financial_facts':sum(f['document_id']==doc['document_id'] for f in y['facts']),'current_research_records':sum(r['document_id']==doc['document_id'] and bool(r['is_current']) for r in y['research_records'])})
core=[]
for source,page,cells in [('may',8,['E25','H25']),('huatai',1,['D6','D8','D10']),('nov',1,['G2','G4','G6'])]:
 for cell in cells:
  found=[]
  for r in y['research_records']:
   s=json.loads(r['source_json']);v=json.loads(r['record_json'])
   if r['document_id']==gold['sources'][source]['document_id'] and r['is_current'] and s.get('page')==page and s.get('cell')==cell and '伊利' in v.get('entity',{}).get('name',''):
    found.append({k:r[k] for k in ['record_id','metric','period','value','currency','scope','data_kind','published_at'] }|{'cell':cell,'page':page,'raw_value':v.get('raw_value'),'raw_unit':v.get('raw_unit'),'quality':v.get('quality')})
  core.append({'source':source,'cell':cell,'records':found})
actuals=[]
expected=[('annual','revenue','2024-FY','115393310976.69'),('annual','net_profit_parent','2024-FY','8452859993.18'),('annual','operating_cash_flow','2024-FY','21739740393.38'),('annual','revenue','2023-FY','125758168916.51'),('annual','net_profit_parent','2023-FY','10428540457.94'),('annual','operating_cash_flow','2023-FY','18290357650.56'),('q3','revenue','2024-9M','88732934445.43'),('q3','net_profit_parent','2024-9M','10868480345.34'),('q3','operating_cash_flow','2024-9M','13869612283.42'),('q3','revenue','2023-9M','97090826912.59'),('q3','net_profit_parent','2023-9M','9380094922.17'),('q3','operating_cash_flow','2023-9M','11708284111.40')]
for name,metric,period,value in expected:
 found=[]
 for f in y['facts']:
  if f['document_id']==gold['sources'][name]['document_id'] and f['metric']==metric and f['period']==period and Decimal(f['value'])==Decimal(value):
   source=json.loads(f['source_json']);found.append({k:f[k] for k in ['fact_id','metric','period','value','currency','scope','raw_unit','quality']}|{'page':source.get('page'),'cell':source.get('cell')})
 actuals.append({'source':name,'metric':metric,'period':period,'expected_CNY':value,'matching_records':found})
q3_periods=sorted({f['period'] for f in y['facts'] if f['document_id']==gold['sources']['q3']['document_id']})
result={'status':'preparation_snapshot_not_F1_freeze','sources':sources,'X5_core_forecast_cells':core,'X5_X6_actual_records':actuals,'q3_periods':q3_periods,'first_phase_source_ready':all(s['pdf_sha_matches_gold'] and s['required_pages_present'] for s in sources),'limitations':['Checking specific numeric/source/period candidates does not prove every row semantic correct.','FY annual is normalizing; full ingestion acceptance remains phase 2 work.','May profit attribution unknown; forecast consolidation/accounting/EPS basis limitations remain explicit in gold.','Guosen and each broker can use original pages where structured rows are ambiguous.','Snapshot predates F1; repeat live freeze after mainline deploy with related project writes paused for the measurement window.'],'product_writes':0,'paid_requests':0}
dump(base/'phase1-material-readiness.json',result)
print(json.dumps({'source_ready':result['first_phase_source_ready'],'matched_forecast_cells':sum(bool(x['records']) for x in core),'expected_forecast_cells':len(core),'actual_matches':sum(bool(x['matching_records']) for x in actuals),'actual_checks':len(actuals),'q3_periods':q3_periods},ensure_ascii=False))
