"""Read-only X7 gates and two disclosed limitations; separate preparation evidence."""
import argparse
from collections import Counter
from contextlib import contextmanager
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
import sqlite3
import sys
from blind import ROOT, read, dump, output
sys.path.insert(0,str(ROOT))
from service.core import FinanceService
from service.store import Store

p=argparse.ArgumentParser();p.add_argument('study');a=p.parse_args();study=output(a.study)
state=read(study/'experiment.json');project=state['config']['tasks'][0]['projectId']
document='e7b0d9679ddc4b739f8f35ecb6dc6227'
data=read(study/'materials-F14-P1.json')[project]
evidence=study/'preparation-evidence';evidence.mkdir(exist_ok=True)
source=Path('D:/AI/财报agent-wt/ingestion-scale/tmp/x7-freeze-pause-haier-20261008')
for name in ['pause-record.json','data-version.json','facts.json','x7-gate.json']:
    shutil.copyfile(source/name,evidence/('N3-'+name))
pause=read(evidence/'N3-pause-record.json')
facts=data['facts']
assert sorted(facts,key=lambda r:r['fact_id'])==sorted(read(evidence/'N3-facts.json'),key=lambda r:r['fact_id'])

class ReadOnlyStore(Store):
    def __init__(self):
        self.path=ROOT/'data/active/finance.sqlite'
        self.root=evidence/'local-workpaper-output'
    @contextmanager
    def connect(self,write=False):
        assert not write,'X7 verifier is read-only'
        db=sqlite3.connect(self.path.as_uri()+'?mode=ro',uri=True);db.row_factory=sqlite3.Row
        try:yield db
        finally:db.close()

store=ReadOnlyStore()
with store.connect() as db:
    processing=json.loads(db.execute('SELECT state_json FROM processing_runs WHERE processing_id=? AND project_id=?',
                                    (pause['processing_id'],project)).fetchone()['state_json'])
dump(evidence/'processing-at-freeze.json',processing)
doc=next(d for d in processing['documents'] if d['document_id']==document)
completed=doc['completed_tables'];deferred=doc.get('deferred_tables',{})
groups={}
for fact in facts:
    src=json.loads(fact['source_json']);groups.setdefault(src.get('table_id'),[]).append(fact)
rows=[]
for number in [9,11,14,114,115,134,298]:
    tid=f'{document}:t{number}'
    source_table=next(t for t in data['source_tables'] if t['table_id']==tid)
    rows.append({'table':number,'submitted':number in completed,'fact_count':len(groups.get(tid,[])),
                 'source_page':source_table['page'],'source_table_present':True,
                 'deferred':deferred.get(str(number)) if isinstance(deferred,dict) else None})
assert all(r['submitted'] and r['fact_count'] and not r['deferred'] for r in rows),'Required table not ready'

service=FinanceService.__new__(FinanceService);service.store=store
workpapers={}
for kind in ['statement_analysis','period_analysis']:
    result=service.financial_workpaper(project,kind,document_id=document,scope='consolidated',periods=['2024-FY','2023-FY'])
    dump(evidence/(kind+'-local-readonly.json'),result)
    assert result['status']=='ok',result.get('error')
    workpapers[kind]=result['data']['numeric_tables']
deducted=workpapers['statement_analysis']['deducted_profit']['rows']
conflicts=[]
for name in ['quarters','cumulatives']:
    for row in workpapers['period_analysis'][name]['rows']:
        if row.get('amount') is None and '保留候选' in str(row.get('missing','')):
            conflicts.append({'table':name,**row})
disclosed_sources=[]
for fact in groups[document+':t9']:
    src=json.loads(fact['source_json']);n=src.get('normalization',{})
    if n.get('dimensions',{}).get('financial_item')=='net_profit_excluding_nonrecurring':
        disclosed_sources.append({'fact_id':fact['fact_id'],'metric':fact['metric'],'period':fact['period'],
                                  'value':fact['value'],'dimensions':n['dimensions'],'cell':src.get('cell')})
record={'at':datetime.now(timezone.utc).isoformat(),'freeze_version':'F1.4',
        'material_sha256':state['phaseFreezes']['1']['sha256'],'required_tables':rows,
        'warranty_alternative_satisfied_by':'t134','original_pages_available':len(data['pages']),
        'facts':len(facts),'facts_equal_N3_pause_snapshot':True,'coverage':pause['coverage'],
        'known_limitations':{'disclosed_deducted_source_rows':disclosed_sources,
                            'deducted_workpaper_rows':deducted,
                            'disclosed_not_adopted':all(r['disclosed'] is None for r in deducted),
                            'calculated_separately_present':all(r['calculated'] is not None for r in deducted),
                            'period_conflict_null_rows':conflicts,'period_conflict_null_count':len(conflicts),
                            'expected_prior_conflict_count':8},
        'model_calls':0,'database_writes':0,
        'preparation_ledger':{'N3_pause_record':'preparation-evidence/N3-pause-record.json',
                              'only_this_ingestion_segment':'Full earlier preparation total unknown; never charge to analysis.'},
        'evaluation_data_excludes_this_check_output':True}
dump(study/'material-gate-and-freeze.json',record)
print(json.dumps({'gate_tables':len(rows),'facts':len(facts),'disclosed_not_adopted':record['known_limitations']['disclosed_not_adopted'],
                  'period_conflict_null_count':len(conflicts),'model_calls':0,'database_writes':0}))
