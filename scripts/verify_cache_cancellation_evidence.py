"""Read-only post-run audit of the isolated Pi cache cancellation fixture."""
import argparse
import csv
import hashlib
import json
import sqlite3
from decimal import Decimal
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument('report')
parser.add_argument('--output', required=True)
args = parser.parse_args()
source = Path(args.report).resolve()
original = source.read_bytes()
run = json.loads(original)
data = Path(run['data_dir']).resolve()
db = sqlite3.connect((data / 'finance.sqlite').as_uri() + '?mode=ro', uri=True)
db.row_factory = sqlite3.Row
checks = []


def check(name, passed, evidence=None):
    checks.append(dict(name=name, status='passed' if passed else 'failed', evidence=evidence))


def events(owner):
    return [json.loads(line) for line in (data / 'audit' / (owner + '.jsonl')).read_text('utf-8').splitlines() if line]


def stable(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


identity = next(c['details'] for c in run['checks'] if c['name'] == 'same_cache_key_has_one_inflight_inference')
owner, survivor = identity['owner_run'], identity['waiter_run']
states = {row['key']: json.loads(row['value_json']) for row in db.execute('SELECT key,value_json FROM app_state WHERE kind=? AND project_id=?', ('runs', run['project_id']))}
check('persisted_cancelled_owner_and_completed_survivor', states[owner]['status'] == 'cancelled' and states[survivor]['status'] == 'completed', {owner: states[owner]['status'], survivor: states[survivor]['status']})
cache = [dict(row) for row in db.execute('SELECT * FROM fact_definition_cache')]
check('single_accepted_cache_winner', len(cache) == 1)
payload = json.loads(cache[0]['result_json'])
check('accepted_owner_is_surviving_pi_session', payload['_review_provenance']['owner_run_id'] == survivor, payload['_review_provenance'])
actual = [e for e in events(survivor) if e['type'] == 'extraction_result' and e['data']['stopReason'] == 'stop']
check('one_actual_successful_model_response', len(actual) == 1, {'owner': survivor, 'requests': [e['data']['requestId'] for e in actual]})
extractions = json.loads(actual[0]['data']['content'])['extractions']
raw = []
for item in extractions:
    kind = next(k for k in item if not k.endswith('_attributes'))
    raw.append({'class': kind, 'text': item[kind], 'attributes': item.get(kind + '_attributes', {})})
accepted = [{k: item[k] for k in ('class', 'text', 'attributes')} for item in payload['extractions']]
check('accepted_extractions_match_actual_raw_response', stable(raw) == stable(accepted))
reports = [json.loads(row[0]) for row in db.execute('SELECT report_json FROM fact_definition_reviews WHERE project_id=?', (run['project_id'],))]
winner = next(r for r in reports if r['owner_run_id'] == survivor)
loser = next(r for r in reports if r['owner_run_id'] == owner)
cache_hash = hashlib.sha256(stable(payload).encode('utf-8')).hexdigest()
check('persisted_report_binds_exact_cache_hash_and_owner', len(winner['audits']) == 1 and winner['audits'][0]['cache_key'] == cache[0]['cache_key'] and winner['audits'][0]['result_hash'] == cache_hash and winner['audits'][0]['provenance'] == payload['_review_provenance'], winner['audits'])
check('cancelled_attempt_retains_failure_and_same_cache_identity', loser['status'] == 'cancelled' and loser['groups_reviewed'] == 0 and loser['failures'][0]['cache_key'] == cache[0]['cache_key'], {'status': loser['status'], 'pending': loser['groups_pending']})
document = db.execute('SELECT relative_path FROM documents WHERE document_id=?', (run['document_id'],)).fetchone()
with (data / document[0]).open(encoding='utf-8', newline='') as stream:
    original_rows = list(csv.reader(stream))
facts = [dict(row) for row in db.execute('SELECT fact_id,document_id,raw_value,value FROM facts WHERE project_id=?', (run['project_id'],))]
check('one_fact_matches_original_amount_after_cancellation', len(facts) == 1 and facts[0]['document_id'] == run['document_id'] and Decimal(facts[0]['value']) == Decimal(original_rows[1][1]), facts)
check('original_fixture_report_unchanged', source.read_bytes() == original, hashlib.sha256(original).hexdigest())
result = {'kind': 'independent_controlled_pi_cache_cancellation_evidence', 'status': 'passed' if all(c['status'] == 'passed' for c in checks) else 'failed', 'model_calls': 0, 'source_report': str(source), 'source_report_status_preserved': run['status'], 'checker_correction': 'The public catalog intentionally omits full audit arrays. Read the persisted review and cache directly for ownership verification; the original failed fixture report is retained.', 'limitations': 'The provider response is a fixed fixture and the financial definition intentionally unresolved. This validates cancellation, ownership and persistence, not model semantic accuracy.', 'checks': checks}
with Path(args.output).open('x', encoding='utf-8') as stream:
    json.dump(result, stream, ensure_ascii=False, indent=2)
print(json.dumps({'status': result['status'], 'passed': sum(c['status'] == 'passed' for c in checks), 'total': len(checks), 'output': args.output}))
if result['status'] != 'passed':
    raise SystemExit(1)
