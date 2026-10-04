"""Consistent read-only evidence snapshot; never imports or instantiates Store.

Facts are the discovery root, so a committed partial batch remains observable
even when an older implementation failed before writing its review report.
"""
import argparse
import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


def export(database, project):
    with sqlite3.connect(database.resolve().as_uri() + '?mode=ro', uri=True) as db:
        db.row_factory = sqlite3.Row
        db.execute('BEGIN')
        reviews = [json.loads(row[0]) for row in db.execute(
            'SELECT report_json FROM fact_definition_reviews WHERE project_id=? ORDER BY created_at', (project,))]
        facts = []
        source_fingerprints = {}
        for row in db.execute('SELECT * FROM facts WHERE project_id=?', (project,)):
            ref = json.loads(row['source_json'])
            meta = ref.get('normalization', {})
            if meta.get('source_key') and meta.get('source_fingerprint'):
                source_fingerprints[meta['source_key']] = meta['source_fingerprint']
            if ref.get('normalization', {}).get('definition_review'):
                facts.append(dict(row))
        keys = {json.loads(f['source_json'])['normalization']['definition_review']['cache_key'] for f in facts}
        keys.update(a['cache_key'] for r in reviews for a in r.get('audits', []))
        caches, cache_hashes, missing = {}, {}, []
        for key in sorted(keys):
            row = db.execute('SELECT result_json FROM fact_definition_cache WHERE cache_key=?', (key,)).fetchone()
            if row is None:
                missing.append(key)
                continue
            payload = json.loads(row[0])
            caches[key] = payload
            canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
            cache_hashes[key] = hashlib.sha256(canonical.encode('utf8')).hexdigest()
        source_keys = {json.loads(f['source_json'])['normalization']['source_key'] for f in facts}
        histories = []
        for row in db.execute('SELECT history_id,processing_id,fact_json,archived_at FROM fact_history WHERE project_id=?', (project,)):
            fact = json.loads(row['fact_json'])
            if json.loads(fact['source_json']).get('normalization', {}).get('source_key') in source_keys:
                histories.append({'history_id': row['history_id'], 'processing_id': row['processing_id'],
                                  'fact': fact, 'archived_at': row['archived_at']})
        return {'schema': 'definition-evidence-export-2', 'source': 'host_sqlite_readonly_transaction',
                'captured_at': datetime.now(timezone.utc).isoformat(), 'database': str(database.resolve()),
                'project_id': project, 'facts': facts, 'reviews': reviews, 'caches': caches,
                'cache_hashes': cache_hashes, 'missing_cache_keys': missing, 'histories': histories,
                'source_fingerprints':source_fingerprints,
                'project_document_ids':[r[0] for r in db.execute('SELECT document_id FROM documents WHERE project_id=?',(project,))]}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--project', required=True)
    parser.add_argument('--database', type=Path, default=Path(__file__).resolve().parents[1] / 'data/finance.sqlite')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    text = json.dumps(export(args.database, args.project), ensure_ascii=False)
    if args.output:
        with args.output.open('x', encoding='utf8') as stream:
            stream.write(text)
    else:
        print(text)
