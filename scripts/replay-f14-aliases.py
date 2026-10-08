"""Rerun five workpapers on fixed F1.4 copies without rematerialization."""
import argparse
from contextlib import contextmanager
import json
from pathlib import Path
import sqlite3
import sys
import time

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from service.core import FinanceService
from service.store import Store

ap=argparse.ArgumentParser();ap.add_argument('phase',choices=['before','after']);ap.add_argument('--out',type=Path,required=True)
a=ap.parse_args();a.out.mkdir(parents=True,exist_ok=True)
def save(path,x):path.write_text(json.dumps(x,ensure_ascii=False,indent=2),encoding='utf8',newline='\n')

class ReadOnlyStore(Store):
    def __init__(self,path,root):self.path=path.resolve();self.root=root
    @contextmanager
    def connect(self,write=False):
        assert not write,'alias replay does not write database'
        db=sqlite3.connect(self.path.as_uri()+'?mode=ro',uri=True);db.row_factory=sqlite3.Row
        try:yield db
        finally:db.close()

result=[]
for name in ('yili','haier'):
    base=ROOT/'tmp/f14-replay-20261008'/name;manifest=json.loads((base/'manifest.json').read_text('utf8'))
    folder=a.out/name;folder.mkdir(exist_ok=True)
    service=FinanceService.__new__(FinanceService);service.store=ReadOnlyStore(base/'app-data/finance.sqlite',folder/'artifacts')
    with service.store.connect() as db:
        facts=[dict(r) for r in db.execute('SELECT * FROM facts ORDER BY fact_id')]
        history=[dict(r) for r in db.execute('SELECT * FROM fact_history ORDER BY rowid')]
    for kind in ('statement_analysis','variance_attribution','anomaly_signals','period_analysis','comparison'):
        start=time.monotonic()
        r=service.financial_workpaper(manifest['project'],kind,document_id=manifest['document'],scope='consolidated',periods=['2024-FY','2023-FY'])
        save(folder/(a.phase+'-'+kind+'.json'),r)
        tables=r.get('data',{}).get('numeric_tables',{})
        row={'dataset':name,'kind':kind,'status':r['status'],'seconds':round(time.monotonic()-start,3),
             'tables':{k:{'rows':len(t['rows']),'numeric_cells':sum(x.get(c) is not None for x in t['rows'] for c,m in t['columns'].items() if m.get('unit') or m.get('per_cell_unit'))} for k,t in tables.items()}}
        result.append(row);print(name,kind,r['status'],flush=True)
    with service.store.connect() as db:
        assert facts==[dict(r) for r in db.execute('SELECT * FROM facts ORDER BY fact_id')]
        assert history==[dict(r) for r in db.execute('SELECT * FROM fact_history ORDER BY rowid')]
save(a.out/(a.phase+'-summary.json'),{'model_calls':0,'database_writes':0,'facts_and_history_unchanged':True,'workpapers':result})
