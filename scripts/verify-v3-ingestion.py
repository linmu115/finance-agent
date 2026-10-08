"""Verify N3 copy results and real model-facing document envelopes, without inference."""
import argparse
from collections import Counter
import json
from pathlib import Path
import sys
import threading

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from service.core import FinanceService
from service.store import Store
from service.metric_normalization import source_metric
from service.standard_metrics import workpaper_concepts
from service.accounting_basis import identify,reapply_document_facts

ap=argparse.ArgumentParser();ap.add_argument('--out',type=Path,required=True);a=ap.parse_args()
def save(path,x):path.write_text(json.dumps(x,ensure_ascii=False,indent=2),encoding='utf-8',newline='\n')
core={'revenue','cogs','selling','administrative','research','finance_costs','gross_profit','operating_profit',
      'profit_before_tax','tax','net_profit','parent_profit','deducted_profit','cfo','receivables','other_receivables',
      'inventory','assets','equity','parent_equity','cash_balance','cash_begin','cash_end'}
summary={'model_calls':0,'production_writes':0,'documents':{}}
for name in ('yili','haier'):
    folder=a.out/name;manifest=json.loads((folder/'manifest.json').read_text('utf-8'))
    project,did=manifest['project'],manifest['document']
    service=FinanceService.__new__(FinanceService);service.configs={}
    service.store=Store.__new__(Store);service.store.root=folder/'app-data';service.store.path=service.store.root/'finance.sqlite';service.store.write_lock=threading.RLock()
    before=json.loads((folder/'before-facts.json').read_text('utf-8'))
    with service.store.connect() as db:
        after=[dict(r) for r in db.execute('SELECT * FROM facts WHERE document_id=?',(did,))]
        parsed=json.loads(db.execute('SELECT prepared_json FROM prepared_documents WHERE document_id=?',(did,)).fetchone()[0])
    byid={f['fact_id']:f for f in after};changes=json.loads((folder/'v3-reapply.json').read_text('utf-8'))
    for old in before:
        new=byid[old['fact_id']]
        assert all(old[k]==new[k] for k in old if k not in {'metric','source_json'})
        if old['metric']!=new['metric']:
            assert old['metric'] in json.loads(new['source_json'])['normalization']['metric_aliases']
    assert reapply_document_facts(service,project,did,parsed,identify(parsed),'v3-final-repeat')['updated']==0
    tabs={f'{did}:t{t["index"]}':t for t in parsed['tables']}
    inventories={}
    for phase,fs in [('before',before),('after',after)]:
        unknown=sorted({f['metric'] for f in fs if not workpaper_concepts(f['metric'])})
        core_items=[];detail_items=[]
        for f in fs:
            if f['metric'] not in unknown:continue
            ref=json.loads(f['source_json']);t=tabs.get(ref.get('table_id'))
            if t is None:continue
            target,evidence=source_metric(t,{**f,'source':ref})
            concepts=set(workpaper_concepts(target)) & core
            if concepts:
                item={'metric':f['metric'],'canonical':target,'concepts':sorted(concepts),
                    'table_id':ref['table_id'],'cell':ref.get('cell'),'label_evidence':evidence,
                    'dimensions':ref.get('normalization',{}).get('dimensions',{})}
                (detail_items if set(item['dimensions'])-{'financial_item','source_table','version'} else core_items).append(item)
        inventories[phase]={'unclaimed_ids':unknown,'core_unclaimed_ids':sorted({x['metric'] for x in core_items}),
                            'core_cells':core_items,'sliced_detail_cells':detail_items}
    save(folder/'metric-inventory.json',inventories)
    comparisons={}
    for kind in ('statement_analysis','variance_attribution','anomaly_signals','period_analysis','comparison'):
        old=json.loads((folder/('before-'+kind+'.json')).read_text('utf-8'))
        new=json.loads((folder/('after-'+kind+'.json')).read_text('utf-8'))
        assert old['status']==new['status']=='ok'
        bt,at=old['data']['numeric_tables'],new['data']['numeric_tables']
        comparisons[kind]={k:{'before_rows':len(bt[k]['rows']) if k in bt else 0,'after_rows':len(t['rows']),
                              'rows_equal':k in bt and bt[k]['rows']==t['rows']} for k,t in at.items()}
    if name=='haier':
        statement=json.loads((folder/'after-statement_analysis.json').read_text('utf-8'))['data']['numeric_tables']
        row=next(r for r in statement['deducted_profit']['rows'] if r['key']=='2024-FY')
        assert row['disclosed']=='17804.73280963' and float(row['residual'])==0
        period=json.loads((folder/'after-period_analysis.json').read_text('utf-8'))['data']['numeric_tables']
        assert len(period['quarters']['rows'])==16 and all(r['amount'] is not None for r in period['quarters']['rows'])
        direct_conflicts=[r for k in ('quarters','cumulatives') for r in period[k]['rows'] if '不同数值' in (r.get('missing') or '')]
        assert not direct_conflicts
    # Simulate the recorded stopped/failed run on the private copy only.
    original=service.store.document(project,did)['state']
    with service.store.connect(write=True) as db:db.execute("UPDATE documents SET state='failed' WHERE document_id=?",(did,))
    try:
        listed=next(d for d in service.list_documents(project)['data']['items'] if d['document_id']==did)
        detail=service.get_document(project,did)['data']
        catalog=service.get_data_catalog(project,document_id=did,limit=1)['data']['documents'][0]
        assert listed==detail==catalog
        assert detail['state']=='partial' and detail['ingestion']['analysis_available']
        counts=detail['ingestion']
        assert counts['tables_completed']+counts['tables_pending']+counts['tables_deferred']==counts['tables_total']
        save(folder/'document-model-view.json',{'status':'ok','data':{'documents':[detail]}})
        review=service.get_normalization_details(project,did,limit=2)['data']['metric_review']
        assert review['total']>=len(review['items'])
        save(folder/'metric-review-page.json',review)
    finally:
        with service.store.connect(write=True) as db:db.execute('UPDATE documents SET state=? WHERE document_id=?',(original,did))
    summary['documents'][name]={'facts':len(after),'changed_facts':changes['changed'],'metric_changes':changes['metric_changes'],
        'unclaimed_ids':{p:len(v['unclaimed_ids']) for p,v in inventories.items()},
        'core_unclaimed_ids':{p:v['core_unclaimed_ids'] for p,v in inventories.items()},
        'core_unclaimed_cells':{p:len(v['core_cells']) for p,v in inventories.items()},
        'status_label':detail['status_label'],'document_state':detail['state'],
        'unchanged_values_units_entities_periods_scopes_coordinates':True,'history_exact':changes['history_exact'],
        'repeat_updates':0,'workpapers':comparisons,'metric_review_total':review['total']}
    print(name,{k:v for k,v in summary['documents'][name].items() if k!='workpapers'},flush=True)
save(a.out/'verified-summary.json',summary)
