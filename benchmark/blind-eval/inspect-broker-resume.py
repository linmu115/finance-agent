"""Read-only quality/usage evidence for the three authorized resumed brokers."""
import json
import sqlite3
from collections import Counter
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'data/evaluation/blind-eval-broker-resume-20261008'
state = json.loads((OUT / 'preparation.json').read_text('utf8'))
def dump(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
def number(text):
    text = str(text).strip().replace(',', '').replace('，', '').replace('−', '-').replace('％', '%')
    if text.startswith('(') and text.endswith(')'):
        text = '-' + text[1:-1]
    if text.startswith('（') and text.endswith('）'):
        text = '-' + text[1:-1]
    if text.endswith('%'):
        text = text[:-1]
    try:
        return Decimal(text)
    except InvalidOperation:
        return None

db = sqlite3.connect((ROOT / 'data/active/finance.sqlite').as_uri() + '?mode=ro', uri=True)
db.row_factory = sqlite3.Row
db.execute('BEGIN')
results = []
for job in state['jobs']:
    key, did, rid = job['key'], job['documentId'], job['runId']
    dest = OUT / key
    run = json.loads((dest / 'run.json').read_text('utf8'))
    audit = [json.loads(line) for line in (dest / 'audit.jsonl').read_text('utf8').splitlines()]
    records = []
    for row in db.execute('SELECT record_id,record_json FROM research_records WHERE document_id=? AND project_id=? AND is_current=1', (did, job['projectId'])):
        records.append({'record_id': row['record_id'], **json.loads(row['record_json'])})
    tables = {row['table_id']: json.loads(row['rows_json']) for row in db.execute('SELECT table_id,rows_json FROM source_tables WHERE document_id=?', (did,))}
    observations = [r for r in records if r['record_type'] == 'observation']
    replay = []
    for record in observations:
        ref = record['source']
        raw = tables[ref['table_id']][ref['row'] - 1][ref['column'] - 1]
        norm = ref.get('normalization', {})
        span = norm.get('numeric_span')
        span_ok = not span or raw[span['start']:span['end']] == span['text']
        parsed = number(span['text'] if span else raw)
        scaled = parsed * Decimal(norm['scale']) if parsed is not None and norm.get('scale') is not None else None
        value_ok = scaled == Decimal(str(record['value'])) if scaled is not None and record.get('value') is not None else None
        replay.append({'record_id': record['record_id'], 'table': ref['table_id'], 'page': ref['page'], 'row': ref['row'], 'column': ref['column'], 'raw_equal': record['raw_value'] == raw, 'span_ok': bool(span_ok), 'source_raw': raw, 'saved_raw': record['raw_value'], 'scaled_value': str(scaled) if scaled is not None else None, 'saved_value': record['value'], 'scaling_equal': value_ok})
    processing = [json.loads(row['state_json']) for row in db.execute('SELECT state_json FROM processing_runs WHERE owner_run_id=? ORDER BY created_at', (rid,))]
    latest = processing[-1] if processing else None
    saved = [json.loads(row['result_json']) for row in db.execute('SELECT result_json FROM normalization_batches WHERE document_id=?', (did,))]
    issues = [i for batch in saved for i in batch.get('issues', [])]
    review_cells = {(i['table'], i['row'], i['column']) for i in issues if all(i.get(k) is not None for k in ['table', 'row', 'column'])}
    unresolved_cells = {(i['table'], i['row'], i['column']) for i in issues if i.get('reason') == 'unresolved_cell_semantics' and all(i.get(k) is not None for k in ['table', 'row', 'column'])}
    profile = db.execute('SELECT * FROM document_profiles WHERE document_id=?', (did,)).fetchone()
    pages = []
    if profile:
        for row in db.execute('SELECT page,review_json FROM research_page_reviews WHERE document_id=? AND profile_revision=? AND source_hash=? ORDER BY page', (did, profile['revision_id'], profile['source_hash'])):
            pages.append({'page': row['page'], **json.loads(row['review_json'])})
    finished_pages = {p['page'] for p in pages if p.get('content_state') not in {'partial', 'failed', 'unresolved'}}
    yili = [r for r in records if r.get('entity', {}).get('name') in ['伊利股份', '伊利', '内蒙古伊利实业集团股份有限公司']]
    forecast = [r for r in yili if r.get('data_kind') == 'analyst_forecast' and r.get('period') == '2024-FY']
    start = datetime.fromisoformat(run['createdAt'].replace('Z', '+00:00'))
    end = datetime.fromisoformat(run['finishedAt'].replace('Z', '+00:00')) if run.get('finishedAt') else None
    model_requests = [e['data'] for e in audit if e['type'] == 'model_request']
    coverage = latest.get('coverage') if latest else None
    complete = bool(coverage and coverage['tables_completed'] == coverage['tables_total'] and coverage['pages_reviewed'] == coverage['pages_total'])
    summary = {'key': key, 'project_id': job['projectId'], 'document_id': did, 'run_id': rid, 'run_status': run['status'], 'stop_reason': run.get('error'), 'duration_ms': round((end - start).total_seconds()*1000) if end else None, 'automatic_continuations': sum(e['type'] == 'ingestion_continuation' for e in audit), 'manual_followups': 0, 'coverage': coverage, 'coverage_complete': complete, 'pending_tables': {d['document_id']: sorted(set(d['tables'])-set(d['completed_tables'])) for d in latest['documents']} if latest else None, 'pages_pending': sorted(set(range(1,job['document']['pageCount']+1))-finished_pages), 'records': len(records), 'observations': len(observations), 'claims': len(records)-len(observations), 'review_cells_any_reason': len(review_cells), 'unresolved_semantic_cells': len(unresolved_cells), 'issue_counts': dict(Counter(i['reason'] for i in issues)), 'raw_cell_replay': {'total':len(replay), 'passed':sum(r['raw_equal'] and r['span_ok'] for r in replay), 'failed':sum(not(r['raw_equal'] and r['span_ok']) for r in replay)}, 'deterministic_scaling': {'passed':sum(r['scaling_equal'] is True for r in replay), 'failed':sum(r['scaling_equal'] is False for r in replay), 'unverified':sum(r['scaling_equal'] is None for r in replay), 'note':'Replays saved scale and numeric span; does not establish that the selected metric, currency or scale is semantically correct.'}, 'current_yili_2024_forecasts':forecast, 'research_quality_counts': dict(Counter(r.get('quality','unknown') for r in records)), 'profile':json.loads(profile['profile_json']) if profile else None, 'reasoning_request_counts':dict(Counter(r.get('sentReasoningEffort','unknown') for r in model_requests)), 'request_phase_counts':dict(Counter(r.get('usagePhase') or r.get('phase') or 'unknown' for r in model_requests)), 'new_usage':run.get('usage'), 'prior_attempts':job['priorAttempts'], 'terminal_ingestion_events':[e for e in audit if e['type'] in ['ingestion_stalled','ingestion_continuation']], 'tool_errors':[e for e in audit if e['type']=='tool_error'], 'coverage_note':'Completed table/page records can include exclusions or unresolved cells; completion alone is not semantic acceptance.'}
    for filename,value in [('research-records.json',records),('source-tables.json',tables),('processing-states.json',processing),('normalization-batches.json',saved),('raw-cell-replay.json',replay),('page-reviews.json',pages),('quality.json',summary)]:
        dump(dest/filename,value)
    results.append(summary)
db.close()
usage_fields = ['input','output','uncachedInput','cacheRead','cacheWrite','reasoning','calls','unknownCalls','cacheUnknownCalls','costUnknownCalls']
totals = {}
for phase, usages in [('prior', [a.get('usage') for j in results for a in j['prior_attempts']]), ('new', [j['new_usage'] for j in results])]:
    totals[phase] = {k:{'knownSum':sum(u[k] for u in usages if u and u.get(k) is not None), 'unknownRuns':sum(not u or u.get(k) is None for u in usages)} for k in usage_fields}
report = {'observed_at':datetime.now(timezone.utc).isoformat(), 'snapshot_api_at':state.get('updatedAt'), 'read_mode':'SQLite URI mode=ro, SELECT-only snapshot; no Store/FinanceService constructor or model calls', 'deployed_commit':state['deployedCommit'], 'usage_old_and_new':totals, 'CPA_billed_cost':None, 'expense_category':'material_preparation_only', 'all_three_coverage_complete':len(results)==3 and all(j['coverage_complete'] for j in results), 'documents':results}
dump(OUT/'quality-summary.json',report)
print(json.dumps([{k:j[k] for k in ['key','run_status','automatic_continuations','coverage','review_cells_any_reason','unresolved_semantic_cells','raw_cell_replay','deterministic_scaling','records','duration_ms']} for j in results],ensure_ascii=False))
