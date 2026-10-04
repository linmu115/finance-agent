"""Copy SQLite using its read-only backup API; sanitize only the private copy."""
import argparse
import hashlib
import json
import sqlite3
import shutil
from pathlib import Path

p = argparse.ArgumentParser();p.add_argument('--target', required=True, type=Path);a = p.parse_args()
root = Path(__file__).resolve().parents[1];target = a.target.resolve()
if target.parent != (root / 'tmp').resolve() or not target.name.startswith('z4-isolated-'):
    raise ValueError('Target must be a newly allocated task-specific tmp directory')
if (target / 'finance.sqlite').exists(): raise ValueError('Refuse to replace an existing database')
project = '3b4c43c9-51b8-432c-807d-2a15323f7a80'
with sqlite3.connect((root / 'data/finance.sqlite').as_uri()+'?mode=ro', uri=True) as original:
    original.execute('PRAGMA query_only=ON')
    with sqlite3.connect(target / 'finance.sqlite') as copy:
        original.backup(copy)
        # No copied conversation, run, budget, or analysis is ever recovered.
        removed = {table:copy.execute(f'SELECT count(*) FROM {table}').fetchone()[0]
                   for table in ('app_state','analysis_jobs','jobs')}
        for table in removed: copy.execute(f'DELETE FROM {table}')
        copy.commit()
        rows = copy.execute('SELECT fact_id,value,raw_value,raw_unit,period,source_json FROM facts WHERE project_id=? ORDER BY fact_id',(project,)).fetchall()
        sources = copy.execute('SELECT page,text FROM pages WHERE document_id=? ORDER BY page',('39de9b118212463bbee6c2ab3c571432',)).fetchall()
        snapshot = {'mode':'sqlite_readonly_backup_then_private_copy_sanitization','project_id':project,
                    'facts':len(rows),'facts_sha256':hashlib.sha256(json.dumps(rows,ensure_ascii=False,separators=(',',':')).encode()).hexdigest(),
                    'pages':len(sources),'pages_sha256':hashlib.sha256(json.dumps(sources,ensure_ascii=False,separators=(',',':')).encode()).hexdigest(),
                    'removed_private_copy_state':removed,'settings_copied':False,'real_database_writes':0}
        relative, expected_sha = copy.execute('SELECT relative_path,sha256 FROM documents WHERE document_id=?',('39de9b118212463bbee6c2ab3c571432',)).fetchone()
        original_file=(root/'data'/relative).resolve();destination=(target/relative).resolve()
        if not original_file.is_relative_to((root/'data').resolve()) or not destination.is_relative_to(target):raise ValueError('Source copy path outside authorized DATA roots')
        actual_sha=hashlib.sha256(original_file.read_bytes()).hexdigest()
        if actual_sha!=expected_sha:raise ValueError('Original PDF hash differs from stored document')
        destination.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(original_file,destination)
        snapshot['public_source_pdf']={'relative_path':relative,'sha256':actual_sha,'copied_sha256':hashlib.sha256(destination.read_bytes()).hexdigest()}
print(json.dumps(snapshot))
