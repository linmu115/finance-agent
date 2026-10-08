"""Scoped F1.4 copy/reapplication/workpaper acceptance. No inference or HTTP."""
import argparse
from collections import Counter
import importlib.util
import json
from pathlib import Path
import shutil
import sqlite3
import sys
import threading
import time

ROOT=Path(__file__).resolve().parents[1]
ap=argparse.ArgumentParser()
ap.add_argument('phase',choices=['prepare','before','after'])
ap.add_argument('--code-root',type=Path,default=ROOT)
ap.add_argument('--out',type=Path,required=True)
ap.add_argument('--source',type=Path)
args=ap.parse_args();sys.path.insert(0,str(args.code_root))
from service.core import FinanceService
from service.store import Store
from service.accounting_basis import identify,reapply_document_facts
from service.financial_workpapers import WorkpaperInputError

DOCS={'yili':('374beac2-a970-4972-b210-e91018bbd6e6','d84573bf6b584e7e874faa4c6adf454a', ['4c3e9228d37e49fca132e0e79377b04d']),
      'haier':('d324c744-4113-4213-aa22-af3bb91a3c84','e7b0d9679ddc4b739f8f35ecb6dc6227',[])}
KINDS=('statement_analysis','variance_attribution','anomaly_signals','period_analysis','comparison')
def write(path,x):path.write_text(json.dumps(x,ensure_ascii=False,indent=2),encoding='utf-8',newline='\n')
def service_at(root):
    s=FinanceService.__new__(FinanceService)
    s.store=Store.__new__(Store);s.store.root=root;s.store.path=root/'finance.sqlite';s.store.write_lock=threading.RLock()
    return s

if args.phase=='prepare':
    for name,(project,did,extra) in DOCS.items():
        folder=args.out/name;folder.mkdir(parents=True,exist_ok=False)
        # Empty private database initialization cannot recover any live jobs.
        s=FinanceService(folder/'app-data')
        for pool in ('pool','analysis_pool','embedding_pool','processing_pool'):getattr(s,pool).shutdown(wait=True)
        source=sqlite3.connect((args.source/'finance.sqlite').as_uri()+'?mode=ro',uri=True);source.row_factory=sqlite3.Row;source.execute('BEGIN')
        with s.store.connect(write=True) as target:
            for table,key,values in [('projects','project_id',[project]),('research_entities','project_id',[project])]+[(t,'document_id',[did,*extra]) for t in ('documents','pages','source_tables','facts','fact_history','prepared_documents','document_profiles','normalization_batches')]:
                cols=[r[1] for r in target.execute(f'PRAGMA table_info({table})')]
                for value in values:
                    for row in source.execute(f'SELECT * FROM {table} WHERE {key}=?',(value,)):
                        fields=[c for c in cols if c in row.keys()]
                        target.execute(f'INSERT INTO {table} ({",".join(fields)}) VALUES ({",".join("?" for _ in fields)})',[row[c] for c in fields])
        for docid in [did,*extra]:
            doc=s.store.document(project,docid);dest=s.store.root/doc['relative_path'];dest.parent.mkdir(parents=True,exist_ok=True)
            shutil.copyfile(args.source/doc['relative_path'],dest)
        source.close()
        with s.store.connect() as db:
            facts=[dict(r) for r in db.execute('SELECT * FROM facts WHERE project_id=? AND document_id=? ORDER BY fact_id',(project,did))]
        write(folder/'before-facts.json',facts)
        write(folder/'manifest.json',{'project':project,'document':did,'extra_documents':extra,'facts':len(facts),'model_calls':0})
        print(name,'snapshot',len(facts),flush=True)
    sys.exit(0)

for name,(project,did,_) in DOCS.items():
    folder=args.out/name;s=service_at(folder/'app-data')
    if args.phase=='after':
        before=json.loads((folder/'before-facts.json').read_text('utf-8'))
        with s.store.connect() as db:parsed=json.loads(db.execute('SELECT prepared_json FROM prepared_documents WHERE document_id=?',(did,)).fetchone()[0])
        applied=reapply_document_facts(s,project,did,parsed,identify(parsed),'f14-replay')
        repeat=reapply_document_facts(s,project,did,parsed,identify(parsed),'f14-repeat')
        with s.store.connect() as db:
            after={r['fact_id']:dict(r) for r in db.execute('SELECT * FROM facts WHERE project_id=? AND document_id=?',(project,did))}
            history=[json.loads(r[0]) for r in db.execute("SELECT fact_json FROM fact_history WHERE processing_id='f14-replay' AND document_id=?",(did,))]
        assert repeat['updated']==0,repeat
        changes=[]
        for old in before:
            new=after[old['fact_id']]
            assert all(old[k]==new[k] for k in ('fact_id','metric','value','raw_value','raw_unit','currency','company','priority','quality'))
            a,b=json.loads(old['source_json']),json.loads(new['source_json'])
            assert {k:v for k,v in a.items() if k!='normalization'}=={k:v for k,v in b.items() if k!='normalization'}
            if old!=new:
                changes.append({'fact_id':old['fact_id'],'table':a['table_id'],'cell':a['cell'],'value':old['value'],
                 'before':{k:old[k] for k in ('scope','period')},'after':{k:new[k] for k in ('scope','period')},
                 'evidence':b['normalization'].get('source_semantics')})
        assert len(changes)==len(history)
        assert applied['updated'] in (0,len(changes))
        assert {h['fact_id']:h for h in history}=={o['fact_id']:o for o in before if o!=after[o['fact_id']]}
        write(folder/'reapply.json',{'applied_this_invocation':applied,'changed_since_snapshot':len(changes),'repeat':repeat,'changed_by_table':dict(Counter(x['table'] for x in changes)),
          'unchanged':len(before)-len(changes),'values_coordinates_entities_unchanged':True,'history_exact':True,'changes':changes})
        write(folder/'after-facts.json',list(after.values()))
        print(name,'reapply',applied,'repeat',repeat,flush=True)
    results=[]
    for kind in KINDS:
        t=time.monotonic();result=s.financial_workpaper(project,kind,document_id=did,scope='consolidated',periods=['2024-FY','2023-FY'])
        write(folder/(args.phase+'-'+kind+'.json'),result)
        tables=result.get('data',{}).get('numeric_tables',{})
        row={'kind':kind,'status':result['status'],'error':result.get('data',{}).get('error'),'seconds':round(time.monotonic()-t,3),
          'rows':{k:len(v['rows']) for k,v in tables.items()},
          'numeric_cells':{k:sum(r.get(c) is not None for r in v['rows'] for c,m in v['columns'].items() if m.get('unit') or m.get('per_cell_unit')) for k,v in tables.items()}}
        results.append(row);write(folder/(args.phase+'-workpapers.json'),results)
        print(name,args.phase,row,flush=True)
