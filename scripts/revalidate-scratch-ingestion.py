"""Upgrade an explicitly named, copied scratch trial without model calls."""
import argparse
import json
import shutil
import sqlite3
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from service.core import FinanceService
from service.semantic import materialize
from service.script_cleaning import _hash

p=argparse.ArgumentParser();p.add_argument('--input',required=True);p.add_argument('--output',required=True)
a=p.parse_args();source=Path(a.input).resolve();out=Path(a.output).resolve();out.mkdir(parents=True,exist_ok=False)
run=json.loads((source/'run.json').read_text(encoding='utf-8'))
db=sqlite3.connect((source/'app-data/finance.sqlite').as_uri()+'?mode=ro',uri=True);db.row_factory=sqlite3.Row
doc=dict(db.execute('SELECT * FROM documents WHERE document_id=?',(run['documentId'],)).fetchone())
parsed=json.loads(db.execute('SELECT prepared_json FROM prepared_documents WHERE document_id=?',(run['documentId'],)).fetchone()[0])
profile=json.loads(db.execute('SELECT profile_json FROM document_profiles WHERE document_id=?',(run['documentId'],)).fetchone()[0])
s=FinanceService(out/'app-data');s.create_project('revalidate','Deterministic semantic upgrade')
upload=s.store.root/'uploads/source.pdf';shutil.copyfile(source/'app-data'/doc['relative_path'],upload)
did=s.register_document('revalidate',str(upload),doc['original_name'])['data']['document_id']
s._persist_prepared('revalidate',did,parsed);current=s.set_document_profile('revalidate',did,profile)['data']['profile']
for raw, in db.execute('SELECT result_json FROM normalization_batches WHERE document_id=?',(run['documentId'],)):
    old=json.loads(raw);table=next(t for t in parsed['tables'] if t['index']==old['script_table'])
    batch=[{'table':table,'rows':list(range(1,len(table['rows'])+1))}]
    facts,_=materialize(old['extractions'],batch,did,'copied-paid-run')
    detail={k:v for k,v in old.items() if k not in {'source_input_fingerprint','coordinates','issues'}}
    detail.update(profile_revision=current['revision_id'],script_source_hash=_hash(table))
    s._commit_semantic_batch('revalidate',did,'copied-paid-run',batch,facts,old['issues'],detail)
result=s.begin_script_cleaning('revalidate',[did],'source-revalidation','no-model')['data']
with s.store.connect() as target:
    facts=[dict(r) for r in target.execute('SELECT * FROM facts WHERE document_id=?',(did,))]
    batches=[json.loads(r[0]) for r in target.execute('SELECT result_json FROM normalization_batches WHERE document_id=?',(did,))]
for name,value in [('result',result),('facts',facts),('batches',batches)]:
    (out/(name+'.json')).write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'coverage':result['coverage'],'pending_tables':result['pending_tables'],'facts':len(facts),
                  'model_calls':0,'documents':result['documents']},ensure_ascii=False))
for pool in ('pool','analysis_pool','embedding_pool','processing_pool'):getattr(s,pool).shutdown(wait=True)
