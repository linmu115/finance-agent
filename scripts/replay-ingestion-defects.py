"""Deterministic replay of the two explicitly authorized production documents.

Production is opened SQLite read-only. All service calls use an isolated copy;
no HTTP, Docker execution, credentials, or model requests are involved.
"""
import argparse
import json
import shutil
import sqlite3
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from service.core import FinanceService

PROJECT='374beac2-a970-4972-b210-e91018bbd6e6'
DOCS={'annual':'d84573bf6b584e7e874faa4c6adf454a','q3':'4c3e9228d37e49fca132e0e79377b04d'}
PIDS={'annual':['59a9b61cf6364453a5fb749e0412a8f0','9c3a91a93b374266b56655c49d3ff634'],
      'q3':['611400eadef34ddd94492704a4115178','b65c16a621b549c0bcbcf00910f777cc']}


def write(path,value):
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8')


def copy_document(source,out,kind):
    did=DOCS[kind]
    s=FinanceService(out/'app-data')
    s._schedule_embedding_index=lambda *a:None
    db=sqlite3.connect((source/'finance.sqlite').as_uri()+'?mode=ro',uri=True);db.row_factory=sqlite3.Row
    with s.store.connect(write=True) as target:
        for table,key,values in [('projects','project_id',[PROJECT]),('documents','document_id',[did]),
                                ('pages','document_id',[did]),('source_tables','document_id',[did]),
                                ('facts','document_id',[did]),('prepared_documents','document_id',[did]),
                                ('document_profiles','document_id',[did]),('normalization_batches','document_id',[did]),
                                ('processing_runs','processing_id',PIDS[kind])]:
            for value in values:
                rows=db.execute(f'SELECT * FROM {table} WHERE {key}=?',(value,)).fetchall()
                columns=[r[1] for r in target.execute(f'PRAGMA table_info({table})')]
                for row in rows:
                    names=[c for c in columns if c in row.keys()]
                    target.execute(f'INSERT INTO {table} ({",".join(names)}) VALUES ({",".join("?" for _ in names)})',[row[c] for c in names])
    doc=s.store.document(PROJECT,did)
    path=s.store.root/doc['relative_path'];path.parent.mkdir(parents=True,exist_ok=True)
    shutil.copyfile(source/doc['relative_path'],path)
    db.close()
    return s


def shutdown(s):
    for pool in ('pool','analysis_pool','embedding_pool','processing_pool'):getattr(s,pool).shutdown(wait=True)


def main():
    p=argparse.ArgumentParser();p.add_argument('--source',default=r'D:\AI\财报agent\data\active');p.add_argument('--output',required=True)
    a=p.parse_args();out=Path(a.output).resolve()
    if not out.is_relative_to(ROOT/'tmp'):raise ValueError('output_must_be_in_worktree_tmp')
    out.mkdir(parents=True,exist_ok=False)
    for kind in DOCS:
        folder=out/kind;folder.mkdir()
        s=copy_document(Path(a.source).resolve(),folder,kind);did=DOCS[kind]
        try:
            doc,parsed=s._clean_source(PROJECT,did);write(folder/'parsed.json',parsed)
            with s.store.connect() as db:
                before=[dict(r) for r in db.execute('SELECT * FROM facts WHERE document_id=?',(did,))]
                batches=[dict(r) for r in db.execute('SELECT * FROM normalization_batches WHERE document_id=?',(did,))]
            write(folder/'before-facts.json',before);write(folder/'before-batches.json',batches)
            if kind=='annual':
                t116=next(r for r in batches if json.loads(r['result_json']).get('script_table')==116)
                # Replay precisely the durable change that the second snapshot missed.
                with s.store.connect(write=True) as db:db.execute('DELETE FROM normalization_batches WHERE document_id=? AND batch_key=?',(did,t116['batch_key']))
                prior=[s.get_cleaning_progress(PROJECT,pid)['data'] for pid in PIDS[kind]]
                with s.store.connect(write=True) as db:
                    db.execute('INSERT INTO normalization_batches VALUES(?,?,?,?,?)',tuple(t116.values()))
                current=[s.get_cleaning_progress(PROJECT,pid)['data'] for pid in PIDS[kind]]
                write(folder/'commit-transition.json',{'before':prior,'after':current})
            result=s.begin_script_cleaning(PROJECT,[did],'n3-deterministic-replay','no-model')['data']
            write(folder/'result.json',result)
            repeat=s.begin_script_cleaning(PROJECT,[did],'n3-deterministic-repeat','no-model')['data']
            write(folder/'repeat.json',repeat)
            with s.store.connect() as db:
                after=[dict(r) for r in db.execute('SELECT * FROM facts WHERE document_id=?',(did,))]
                checkpoints=[dict(r) for r in db.execute('SELECT processing_id,owner_run_id FROM processing_runs')]
            write(folder/'after-facts.json',after);write(folder/'checkpoints.json',checkpoints)
            print(json.dumps({'kind':kind,'coverage':result['coverage'],'facts_before':len(before),'facts_after':len(after),
                              'processing_id':result['processing_id'],'repeat_id':repeat['processing_id'],'checkpoints':len(checkpoints),'model_calls':0},ensure_ascii=False),flush=True)
        finally:shutdown(s)


if __name__=='__main__':main()
