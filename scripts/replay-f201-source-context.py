"""Scoped F2.0.1 deterministic copy replay; never writes the source database."""
import argparse
from collections import Counter
import json
from pathlib import Path
import shutil
import sqlite3
import sys
import threading

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

DOCS = {
    'carote': ('03b52dde-19da-49c1-949a-ee6d93bf036b', '3d9d0befd8374eed9a7488dbd8dd00d2'),
    'yili': ('374beac2-a970-4972-b210-e91018bbd6e6', 'd84573bf6b584e7e874faa4c6adf454a'),
    'haier': ('d324c744-4113-4213-aa22-af3bb91a3c84', 'e7b0d9679ddc4b739f8f35ecb6dc6227'),
    'moutai': ('n3-round2-moutai-warm', '8806d020dcf04227b4ed356523190a08'),
}
ap = argparse.ArgumentParser()
ap.add_argument('phase', choices=['prepare', 'baseline', 'fixed'])
ap.add_argument('--out', type=Path, required=True)
ap.add_argument('--source', type=Path)
ap.add_argument('--moutai-source', type=Path)
ap.add_argument('--code-root', type=Path, default=ROOT)
ap.add_argument('--label')
ap.add_argument('--source-phase', default='original')
args = ap.parse_args()
sys.path.insert(0,str(args.code_root))
from service.core import FinanceService
from service.store import Store
from service.accounting_basis import identify, reapply_document_facts
assert args.out.resolve().is_relative_to(ROOT / 'tmp')

def save(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), 'utf-8', newline='\n')

def service_at(folder):
    service = FinanceService.__new__(FinanceService)
    service.store = Store.__new__(Store)
    service.store.root = folder
    service.store.path = folder / 'finance.sqlite'
    service.store.write_lock = threading.RLock()
    return service

for name, (project, did) in DOCS.items():
    folder = args.out / name
    if args.phase == 'prepare':
        folder.mkdir(parents=True, exist_ok=False)
        target_root = folder / 'original'
        service = FinanceService(target_root)
        for pool in ('pool', 'analysis_pool', 'embedding_pool', 'processing_pool'):
            getattr(service, pool).shutdown(wait=True)
        source_root = args.moutai_source if name == 'moutai' else args.source
        source = sqlite3.connect((source_root.resolve() / 'finance.sqlite').as_uri() + '?mode=ro', uri=True)
        source.row_factory = sqlite3.Row
        source.execute('BEGIN')
        with service.store.connect(write=True) as target:
            for table, key, value in [('projects', 'project_id', project)] + [
                    (t, 'document_id', did) for t in ('documents', 'pages', 'source_tables', 'facts', 'fact_history',
                                                     'prepared_documents', 'document_profiles', 'normalization_batches')]:
                columns = [r[1] for r in target.execute(f'PRAGMA table_info({table})')]
                for row in source.execute(f'SELECT * FROM {table} WHERE {key}=?', (value,)):
                    fields = [c for c in columns if c in row.keys()]
                    target.execute(f'INSERT INTO {table} ({",".join(fields)}) VALUES ({",".join("?" for _ in fields)})',
                                   [row[c] for c in fields])
        source.close()
        with service.store.connect() as db:
            facts = [dict(r) for r in db.execute('SELECT * FROM facts WHERE document_id=? ORDER BY fact_id', (did,))]
        save(folder / 'before-facts.json', facts)
        print(name, 'copied', len(facts), flush=True)
        continue
    label = args.label or args.phase
    shutil.copytree(folder / args.source_phase, folder / label)
    service = service_at(folder / label)
    before = json.loads((folder / ('before-facts.json' if args.source_phase == 'original' else args.source_phase + '-facts.json')).read_text('utf-8'))
    with service.store.connect() as db:
        parsed = json.loads(db.execute('SELECT prepared_json FROM prepared_documents WHERE document_id=?', (did,)).fetchone()[0])
    basis = identify(parsed)
    revision = 'f201-' + label
    applied = reapply_document_facts(service, project, did, parsed, basis, revision)
    repeat = reapply_document_facts(service, project, did, parsed, basis, revision + '-repeat')
    with service.store.connect() as db:
        after = {r['fact_id']: dict(r) for r in db.execute('SELECT * FROM facts WHERE document_id=?', (did,))}
        history = [json.loads(r[0]) for r in db.execute('SELECT fact_json FROM fact_history WHERE document_id=? AND processing_id=?', (did, revision))]
    changes, field_counts = [], Counter()
    for old in before:
        new = after[old['fact_id']]
        assert all(old[k] == new[k] for k in old if k not in {'metric','scope','period','year','source_json'})
        assert all(old[k] == new[k] for k in ('fact_id', 'value', 'raw_value', 'raw_unit', 'currency', 'company', 'priority', 'quality'))
        a, b = json.loads(old['source_json']), json.loads(new['source_json'])
        assert {k:v for k,v in a.items() if k != 'normalization'} == {k:v for k,v in b.items() if k != 'normalization'}
        if old != new:
            delta = {k:{'before':old[k], 'after':new[k]} for k in old if old[k] != new[k] and k != 'source_json'}
            n1, n2 = a.get('normalization', {}), b.get('normalization', {})
            for key in n1.keys() | n2.keys():
                if n1.get(key) != n2.get(key):
                    delta['normalization.' + key] = {'before':n1.get(key), 'after':n2.get(key)}
            field_counts.update(delta.keys())
            changes.append({'fact_id':old['fact_id'], 'table_id':a['table_id'], 'row':a['row'], 'column':a['column'], 'changes':delta})
    assert repeat['updated'] == 0, repeat
    assert len(after) == len(before)
    assert {r['fact_id']:r for r in history} == {r['fact_id']:r for r in before if r != after[r['fact_id']]}
    save(folder / (label + '-facts.json'), list(after.values()))
    report = {'document':name, 'fact_count':len(before), 'basis':basis, 'applied':applied, 'repeat':repeat,
              'field_counts':dict(field_counts), 'by_table':dict(Counter(x['table_id'] for x in changes)),
              'values_coordinates_entities_unchanged':True, 'history_exact':True, 'model_calls':0, 'changes':changes}
    save(folder / (label + '-report.json'), report)
    print(name, args.phase, len(changes), dict(field_counts), flush=True)
