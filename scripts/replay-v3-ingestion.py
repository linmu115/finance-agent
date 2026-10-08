"""N3 copied-database acceptance. No service restart, production write or inference."""
import argparse
from collections import Counter
import json
from pathlib import Path
import sys
import threading

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from service.core import FinanceService
from service.store import Store
from service.accounting_basis import identify, reapply_document_facts
from service.standard_metrics import workpaper_concepts

parser = argparse.ArgumentParser()
parser.add_argument('--out', type=Path, required=True)
args = parser.parse_args()

def save(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8', newline='\n')

for name in ('yili', 'haier'):
    folder = args.out / name
    manifest = json.loads((folder / 'manifest.json').read_text('utf-8'))
    project, did = manifest['project'], manifest['document']
    service = FinanceService.__new__(FinanceService)
    service.store = Store.__new__(Store)
    service.store.root = folder / 'app-data'
    service.store.path = service.store.root / 'finance.sqlite'
    service.store.write_lock = threading.RLock()
    with service.store.connect() as db:
        parsed = json.loads(db.execute('SELECT prepared_json FROM prepared_documents WHERE document_id=?', (did,)).fetchone()[0])
    before = json.loads((folder / 'before-facts.json').read_text('utf-8'))
    applied = reapply_document_facts(service, project, did, parsed, identify(parsed), 'v3-ingestion-replay')
    repeat = reapply_document_facts(service, project, did, parsed, identify(parsed), 'v3-ingestion-repeat')
    with service.store.connect() as db:
        after = {r['fact_id']: dict(r) for r in db.execute('SELECT * FROM facts WHERE document_id=?', (did,))}
        history = [json.loads(r[0]) for r in db.execute("SELECT fact_json FROM fact_history WHERE processing_id='v3-ingestion-replay' AND document_id=?", (did,))]
    changes = []
    for old in before:
        new = after[old['fact_id']]
        assert all(old[k] == new[k] for k in ('fact_id', 'value', 'raw_value', 'raw_unit', 'currency', 'company', 'priority', 'quality'))
        a, b = json.loads(old['source_json']), json.loads(new['source_json'])
        assert {k:v for k,v in a.items() if k != 'normalization'} == {k:v for k,v in b.items() if k != 'normalization'}
        if old != new:
            changes.append({'fact_id': old['fact_id'], 'table_id': a['table_id'], 'cell': a['cell'],
                            'before_metric': old['metric'], 'after_metric': new['metric'],
                            'changed_fields': [k for k in old if old[k] != new[k]],
                            'normalization': b['normalization']})
    assert repeat['updated'] == 0, repeat
    assert len(after) == len(before)
    assert {x['fact_id']:x for x in history} == {old['fact_id']:old for old in before if old != after[old['fact_id']]}
    report = {'dataset': name, 'facts': len(after), 'applied': applied, 'repeat': repeat,
              'changed': len(changes), 'by_table': dict(Counter(x['table_id'] for x in changes)),
              'metric_changes': sum(x['before_metric'] != x['after_metric'] for x in changes),
              'unclaimed_before': sorted({f['metric'] for f in before if not workpaper_concepts(f['metric'])}),
              'unclaimed_after': sorted({f['metric'] for f in after.values() if not workpaper_concepts(f['metric'])}),
              'values_coordinates_entities_unchanged': True, 'history_exact': True, 'model_calls': 0,
              'changes': changes}
    save(folder / 'v3-reapply.json', report)
    save(folder / 'after-facts.json', list(after.values()))
    print(name, {k:report[k] for k in ('facts', 'applied', 'repeat', 'metric_changes')}, flush=True)
    for kind in ('statement_analysis', 'variance_attribution', 'anomaly_signals', 'period_analysis', 'comparison'):
        result = service.financial_workpaper(project, kind, document_id=did, scope='consolidated', periods=['2024-FY', '2023-FY'])
        save(folder / ('after-' + kind + '.json'), result)
        tables = result.get('data', {}).get('numeric_tables', {})
        print(name, kind, result['status'], {k: len(t['rows']) for k,t in tables.items()}, flush=True)
