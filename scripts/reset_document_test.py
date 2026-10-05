"""Explicit, hash-guarded fresh-input test reset. Run with the application stopped.

Keeps the original PDF and user conversations. Backs up the complete SQLite DB,
old audit, parser files and a deletion manifest before replacing derived data.
"""
import argparse
import hashlib
import json
import shutil
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


def reset(root, document_id, expected_sha, apply=False):
    root=Path(root).resolve();database=root/'finance.sqlite'
    with sqlite3.connect(database) as db:
        db.row_factory=sqlite3.Row
        doc=dict(db.execute('SELECT * FROM documents WHERE document_id=?',(document_id,)).fetchone())
        source=(root/doc['relative_path']).resolve();source.relative_to(root)
        assert hashlib.sha256(source.read_bytes()).hexdigest()==doc['sha256']==expected_sha,'PDF identity changed'
        for r in db.execute("SELECT value_json FROM app_state WHERE kind='runs'"):
            assert json.loads(r[0]).get('status') not in {'running','queued'},'An application task is active'
        processing=[];owners=[]
        for row in db.execute('SELECT * FROM processing_runs WHERE project_id=?',(doc['project_id'],)):
            state=json.loads(row['state_json']);ids=[d['document_id'] for d in state['documents']]
            if document_id in ids:
                assert set(ids)=={document_id},'Mixed-document attempt requires a narrower reset'
                processing.append(row['processing_id']);owners.append(row['owner_run_id'])
        keys=[json.loads(r[0]).get('cache_key') for r in db.execute('SELECT result_json FROM normalization_batches WHERE document_id=?',(document_id,))]
        keys=list({k for k in keys if k})
        tables=['facts','fact_history','normalization_batches','pages','source_tables','chunks','jobs','prepared_documents','source_parse_history','attachment_flows']
        existing={r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")};tables=[t for t in tables if t in existing]
        counts={t:db.execute(f'SELECT count(*) FROM {t} WHERE document_id=?',(document_id,)).fetchone()[0] for t in tables}
        untouched=[tuple(r) for r in db.execute('SELECT * FROM facts WHERE document_id<>? ORDER BY fact_id',(document_id,))]
        untouched_hash=hashlib.sha256(json.dumps(untouched,ensure_ascii=False).encode()).hexdigest()
        manifest={'document':doc,'counts':counts,'processing_ids':processing,'owner_runs':owners,'cache_keys':keys,'other_facts_hash':untouched_hash,'applied':apply}
        if not apply:return manifest
        backup=root/'backups'/('yili-retest-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'));backup.mkdir(parents=True,exist_ok=False)
        with sqlite3.connect(backup/'finance.sqlite') as target:db.backup(target)
        for owner in owners:
            audit=root/'audit'/(owner+'.jsonl')
            if audit.exists():shutil.copy2(audit,backup/audit.name)
        index=root/'indexes'/doc['project_id']/(document_id+'.json')
        catalog=index.parent/'catalog.yaml'
        for file in (index,catalog):
            if file.exists():shutil.copy2(file,backup/file.name)
        manifest['backup']=str(backup)
        (backup/'reset-manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
        with db:
            db.execute('DELETE FROM chunks_fts WHERE chunk_id IN (SELECT chunk_id FROM chunks WHERE document_id=?)',(document_id,))
            for table in tables:db.execute(f'DELETE FROM {table} WHERE document_id=?',(document_id,))
            for key in keys:db.execute('DELETE FROM normalization_cache WHERE cache_key=?',(key,))
            for pid in processing:db.execute('DELETE FROM processing_runs WHERE processing_id=?',(pid,))
            db.execute("UPDATE documents SET state='registered',page_count=0,warnings_json='[]' WHERE document_id=?",(document_id,))
            after=[tuple(r) for r in db.execute('SELECT * FROM facts WHERE document_id<>? ORDER BY fact_id',(document_id,))]
            assert hashlib.sha256(json.dumps(after,ensure_ascii=False).encode()).hexdigest()==untouched_hash
        # Exact derived file only; directory and other document indexes stay intact.
        index.unlink(missing_ok=True)
        if catalog.exists():
            import yaml
            navigation=yaml.safe_load(catalog.read_text(encoding='utf-8'))
            if isinstance(navigation,dict) and isinstance(navigation.get('documents'),list):
                navigation['documents']=[entry for entry in navigation['documents'] if entry.get('document_id')!=document_id]
                catalog.write_text(yaml.safe_dump(navigation,allow_unicode=True,sort_keys=False),encoding='utf-8')
        assert hashlib.sha256(source.read_bytes()).hexdigest()==expected_sha
        return manifest


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--data',default='data');parser.add_argument('--document-id',required=True);parser.add_argument('--sha256',required=True);parser.add_argument('--apply',action='store_true')
    args=parser.parse_args();result=reset(args.data,args.document_id,args.sha256,args.apply);result['cache_key_count']=len(result.pop('cache_keys'));print(json.dumps(result,ensure_ascii=True,indent=2))
