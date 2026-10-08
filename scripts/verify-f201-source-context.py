"""Publish all-field copy deltas and verify the three concrete regressions."""
import copy
import json
from collections import Counter
from pathlib import Path
import sqlite3
import sys
import threading

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from service.core import FinanceService
from service.store import Store
from service.metric_normalization import pending_metric_review
from service.metric_context import column_semantics
from service.standard_metrics import ROWS, CONTEXTUAL_LABELS, normalize_label

source=ROOT/'tmp/f201-accepted-20261009'
out=ROOT/'docs/evidence/f201-source-context-20261009'
out.mkdir(parents=True,exist_ok=True)
def save(path,data):path.write_text(json.dumps(data,ensure_ascii=False,indent=2),'utf-8',newline='\n')
summary={}
for name in ('carote','yili','haier','moutai'):
    folder=source/name
    read=lambda suffix:json.loads((folder/suffix.replace('verified-','final-').replace('upgraded-','final-recovered-')).read_text('utf-8'))
    original={f['fact_id']:f for f in read('before-facts.json')}
    fixed={f['fact_id']:f for f in read('verified-facts.json')}
    upgraded={f['fact_id']:f for f in read('upgraded-facts.json')}
    service=FinanceService.__new__(FinanceService);service.store=Store.__new__(Store)
    service.store.root=folder/'final';service.store.path=service.store.root/'finance.sqlite';service.store.write_lock=threading.RLock()
    with service.store.connect() as db:
        row=db.execute('SELECT document_id,project_id FROM documents').fetchone();did,project=row
        tables={r['table_id']:{'rows':json.loads(r['rows_json'])} for r in db.execute('SELECT * FROM source_tables WHERE document_id=?',(did,))}
    reviews=pending_metric_review(service.store,did);save(out/(name+'-pending.json'),reviews)
    inventory=[];empty=[];ownership=[]
    for fid,f in fixed.items():
        u=upgraded[fid]
        assert all(f[k]==u[k] for k in ('metric','scope','period','year','value','raw_value','raw_unit','currency','company')),(name,fid)
        s=json.loads(f['source_json']);n=s['normalization'];un=json.loads(u['source_json'])['normalization']
        assert n.get('dimensions',{})==un.get('dimensions',{}),(name,fid,'dimensions')
        assert n.get('dimension_roles',{})==un.get('dimension_roles',{}),(name,fid,'roles')
        assert not (n.get('dimensions',{}).get('composition')=='component' and not n['dimensions'].get('component')),(name,fid)
        tid=s['table_id'];table=tables[tid];label=table['rows'][s['row']-1][0]
        if 'inventory' in original[fid]['metric'] or 'inventories' in original[fid]['metric']:
            meaning=column_semantics(table,s['row'],s['column'],n.get('column_label'))
            if set(meaning['measure_kinds']) & {'gross','allowance','net'}:
                assert f['metric']==original[fid]['metric'],(name,fid,'inventory metric changed')
                assert n.get('dimension_roles',{}).get('financial_item')!='descriptive',(name,fid,'inventory role lost')
                assert fid in {r['fact_id'] for r in reviews},(name,fid,'missing review')
                inventory.append({'fact_id':fid,'table_id':tid,'row':s['row'],'column':s['column'],'metric':f['metric'],'column_semantics':meaning})
        if name=='carote' and tid.endswith((':t12',':t16',':t20')):
            expected={('t12',2):'net_profit_parent',('t12',3):'minority_profit',('t16',2):'comprehensive_income_parent',
                      ('t16',3):'comprehensive_income_minority',('t20',9):'minority_interests'}.get((tid.rsplit(':',1)[1],s['row']))
            if expected:
                assert f['metric']==expected,(fid,f['metric'],expected)
                ownership.append({'table_id':tid,'row':s['row'],'column':s['column'],'metric':f['metric'],'value':f['value']})
        if name=='carote' and (tid.rsplit(':',1)[1],s['row']) in {('t55',9),('t55',11),('t1',6),('t2',10)}:
            assert 'component' not in n.get('dimensions',{}),(fid,n)
            empty.append({'fact_id':fid,'table_id':tid,'row':s['row'],'column':s['column'],'dimensions':n.get('dimensions',{})})
    if name=='carote':assert len(empty)==6 and len(ownership)==10
    reports={}
    for label in ('baseline','verified','upgraded'):
        report=read(label+'-report.json')
        # Deduplicate revision metadata only; every changed field remains in
        # the audit and resolves to its complete before/after JSON value.
        shared={}
        for change in report['changes']:
            for field in ('normalization.document_semantics_revision',):
                if field in change['changes']:
                    value=change['changes'][field]
                    key=next((k for k,v in shared.items() if v==value),None)
                    if key is None:key=f'metadata_{len(shared)+1}';shared[key]=value
                    change['changes'][field]={'shared_value':key}
        report['shared_values']=shared
        save(out/(name+'-'+label+'-changes.json'),report)
        reports[label]={k:report[k] for k in ('fact_count','applied','repeat','field_counts','values_coordinates_entities_unchanged','history_exact','model_calls')}
    summary[name]={'reapplications':reports,'inventory_cells_preserved':len(inventory),'pending_review_count':len(reviews),
                   'empty_components':0,'bad_prior_application_recovers_same_metrics_scopes_periods_dimensions':True,
                   'ownership_checks':ownership,'empty_total_checks':empty}
    save(out/(name+'-inventory-checks.json'),inventory)
    if name in ('haier','yili'):
        workpapers={}
        for kind in ('statement_analysis','period_analysis'):
            result=service.financial_workpaper(project,kind,document_id=did,scope='consolidated',periods=['2024-FY','2023-FY'])
            save(folder/(kind+'-full-result.json'),result)
            save(out/(name+'-'+kind+'.json'),{'status':result['status'],'numeric_tables':{
                key:{'columns':table.get('columns'),'rows':table['rows']} for key,table in result.get('data',{}).get('numeric_tables',{}).items()}})
            workpapers[kind]={'status':result['status'],'rows':{k:len(t['rows']) for k,t in result.get('data',{}).get('numeric_tables',{}).items()}}
        summary[name]['workpapers']=workpapers
    print(name,summary[name]['reapplications']['verified']['applied'], 'inventory',len(inventory),'review',len(reviews),flush=True)
save(out/'summary.json',summary)
english=[{'metric':m,'label':s} for m,labels in ROWS.items() for s in labels.split('|') if s.isascii()]
save(out/'label-audit.json',{'english_definitions':len({x['metric'] for x in english}),'english_label_count':len(english),
                           'english_labels':english,'contextual_labels':CONTEXTUAL_LABELS})
