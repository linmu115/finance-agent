"""Scoped, read-only development snapshot; reapplication only in a private DB."""
import argparse
import json
from pathlib import Path
import shutil
import sqlite3
import sys
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from service.core import FinanceService
from service.accounting_basis import identify, reapply_document_facts
from scripts.replay_v3_workpapers import DOCS

ap = argparse.ArgumentParser()
ap.add_argument('--source', type=Path, required=True)
ap.add_argument('--out', type=Path, required=True)
args = ap.parse_args()
args.out.mkdir(parents=True, exist_ok=False)
s = FinanceService(args.out)
for pool in ('pool', 'analysis_pool', 'embedding_pool', 'processing_pool'):
    getattr(s, pool).shutdown(wait=True)
source = sqlite3.connect((args.source.resolve() / 'finance.sqlite').as_uri() + '?mode=ro', uri=True)
source.row_factory = sqlite3.Row
source.execute('BEGIN')
manifest = {'captured_at': datetime.now(timezone.utc).isoformat(), 'source_mode': 'ro', 'paid_calls': 0, 'documents': {}}
with s.store.connect(write=True) as target:
    for name in ('yili', 'haier', 'carote'):
        project, did = DOCS[name]
        for table, key, value in [('projects', 'project_id', project), ('research_entities', 'project_id', project)] + [
            (t, 'document_id', did) for t in ('documents', 'pages', 'source_tables', 'facts', 'fact_history',
                                             'prepared_documents', 'document_profiles', 'normalization_batches')]:
            columns = [r[1] for r in target.execute(f'PRAGMA table_info({table})')]
            for row in source.execute(f'SELECT * FROM {table} WHERE {key}=?', (value,)):
                fields = [c for c in columns if c in row.keys()]
                target.execute(f'INSERT INTO {table} ({",".join(fields)}) VALUES ({",".join("?" for _ in fields)})', [row[c] for c in fields])
        doc = dict(target.execute('SELECT * FROM documents WHERE document_id=?', (did,)).fetchone())
        dest = args.out / doc['relative_path']; dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(args.source / doc['relative_path'], dest)
        manifest['documents'][name] = {'project': project, 'document': did, 'original_name': doc['original_name'],
            'facts': target.execute('SELECT COUNT(*) FROM facts WHERE document_id=?', (did,)).fetchone()[0]}
source.close()
for name, item in manifest['documents'].items():
    with s.store.connect() as db:
        parsed = json.loads(db.execute('SELECT prepared_json FROM prepared_documents WHERE document_id=?', (item['document'],)).fetchone()[0])
        before_history = db.execute('SELECT COUNT(*) FROM fact_history WHERE document_id=?', (item['document'],)).fetchone()[0]
    item['reapply'] = reapply_document_facts(s, item['project'], item['document'], parsed, identify(parsed), 'f20-private-replay')
    item['repeat'] = reapply_document_facts(s, item['project'], item['document'], parsed, identify(parsed), 'f20-private-repeat')
    with s.store.connect() as db:
        item['new_history'] = db.execute('SELECT COUNT(*) FROM fact_history WHERE document_id=?', (item['document'],)).fetchone()[0] - before_history
    print(name, json.dumps(item, ensure_ascii=False), flush=True)
(args.out / 'snapshot-manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
