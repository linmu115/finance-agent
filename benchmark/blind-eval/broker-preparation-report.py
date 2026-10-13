"""Read saved product evidence and current broker records; never resume a job."""
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'data/evaluation/blind-eval-ingestion-20261007'
KEYS = ['everbright_20240512', 'huatai_20241030', 'everbright_20241104']
ledger = json.loads((OUT / 'preparation.json').read_text('utf8'))
db = sqlite3.connect((ROOT / 'data/active/finance.sqlite').as_uri() + '?mode=ro', uri=True)
db.row_factory = sqlite3.Row
jobs = []
for job in ledger['jobs']:
    if job['key'] not in KEYS:
        continue
    policies, coverage, checkpoint, errors = [], None, None, []
    for attempt in job['attempts']:
        for line in (OUT / 'audit' / (attempt['runId'] + '.jsonl')).read_text('utf8').splitlines():
            event = json.loads(line)
            data = event['data']
            if event['type'] == 'model_request':
                policy = {key: data.get(key) for key in ['model', 'reasoningEffort', 'sentReasoningEffort', 'usagePhase']}
                if policy not in policies:
                    policies.append(policy)
            if event['type'] != 'tool_result':
                continue
            result = data.get('result', {})
            body = result.get('data', {}) if isinstance(result, dict) else {}
            if isinstance(result, dict) and result.get('status') == 'error':
                errors.append({'at': event['at'], 'tool': data['name'], 'result': result})
            if body.get('coverage'):
                coverage = {'at': event['at'], 'tool': data['name'], **{key: body.get(key) for key in ['processing_id', 'state', 'coverage', 'pending_tables', 'pending_pages', 'research_record_count']}}
            if data['name'] == 'get_processing_checkpoint':
                checkpoint = {'at': event['at'], 'data': body}
    did = job['document']['id']
    profile = db.execute('SELECT * FROM document_profiles WHERE document_id=?', (did,)).fetchone()
    text_coverage = None
    if profile:
        pages = [dict(row) for row in db.execute('SELECT page,review_json FROM research_page_reviews WHERE document_id=? AND profile_revision=? AND source_hash=? ORDER BY page', (did, profile['revision_id'], profile['source_hash']))]
        for page in pages:
            page.update(json.loads(page.pop('review_json')))
        finished = [p['page'] for p in pages if p.get('content_state') not in {'failed', 'partial', 'unresolved'}]
        text_coverage = {'total': job['document']['pageCount'], 'finished': len(finished), 'pending': sorted(set(range(1, job['document']['pageCount'] + 1)) - set(finished)), 'pages': pages}
    rows = [dict(row) for row in db.execute('SELECT r.record_id,r.record_type,r.data_kind,r.metric,r.period,r.value,r.currency,r.scope,r.publisher,r.published_at,r.source_json,r.record_json,e.name entity_name FROM research_records r JOIN research_entities e USING(entity_id) WHERE r.document_id=? AND r.is_current=1 AND e.name IN (?,?) ORDER BY r.period,r.metric', (did, '伊利股份', '伊利'))]
    for row in rows:
        row['source'] = json.loads(row.pop('source_json'))
        row['record'] = json.loads(row.pop('record_json'))
    complete = bool(job.get('preparationComplete') and coverage and coverage['coverage']['tables_completed'] == coverage['coverage']['tables_total'] and text_coverage and not text_coverage['pending'])
    conversation = json.loads((OUT / 'conversations' / (job['conversationId'] + '.json')).read_text('utf8'))
    jobs.append({'key': job['key'], 'projectId': job['projectId'], 'documentId': did, 'conversationId': job['conversationId'], 'runStatus': job['status'], 'documentStatus': job['document']['status'], 'pageCount': job['document']['pageCount'], 'recordCount': job['document'].get('researchRecordCount'), 'complete_coverage_verified': complete, 'coverage_note': 'Coverage only; semantic correctness is separate. Unknown coverage is not completion.', 'latest_product_coverage': coverage, 'latest_product_checkpoint': checkpoint, 'current_text_coverage': text_coverage, 'profile': json.loads(profile['profile_json']) if profile else None, 'current_Yili_records': rows, 'model_policies': policies, 'tool_errors': errors, 'attempts': job['attempts'], 'final_assistant': [m.get('content') for m in conversation['messages'] if m['role'] == 'assistant'][-1:], 'manual_continuations_this_request': max(0, len(job['attempts']) - 1), 'audit_files': [str((OUT / 'audit' / (a['runId'] + '.jsonl')).relative_to(ROOT)) for a in job['attempts']]})
db.close()
attempts = [a for job in jobs for a in job['attempts']]
usage = {'providerBilledCost': None, 'fee_note': 'CPA billed rate/cost unknown; model-directory cost is not the bill. Preparation only, excludes all analysis and judging.', 'attemptCount': len(attempts)}
for key in ['input', 'output', 'uncachedInput', 'cacheRead', 'cacheWrite', 'reasoning', 'calls', 'unknownCalls', 'cacheUnknownCalls', 'costUnknownCalls']:
    known = [a['usage'][key] for a in attempts if (a.get('usage') or {}).get(key) is not None]
    usage[key] = {'knownSum': sum(known) if known else None, 'unknownAttempts': len(attempts) - len(known)}
report = {'observedAt': datetime.now(timezone.utc).isoformat(), 'purpose': 'three_broker_full_preparation_separate_accounting', 'runtime_evidence_at': ledger['updatedAt'], 'read_mode': 'saved API/audit snapshots and SQLite mode=ro SELECT only; no service constructor or model calls', 'authorized_model': 'cpa-local/gpt-6-luna', 'recovery_policy': 'No manual continuation after early completion or stall. Preserve original checkpoint and report.', 'all_three_coverage_complete': len(jobs) == 3 and all(j['complete_coverage_verified'] for j in jobs), 'jobs': jobs, 'usage': usage}
(OUT / 'broker-preparation-report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
print(json.dumps({'jobs': [{'key': j['key'], 'status': j['runStatus'], 'complete': j['complete_coverage_verified'], 'coverage': j['latest_product_coverage']['coverage'] if j['latest_product_coverage'] else None, 'records': j['recordCount']} for j in jobs], 'usage': usage}, ensure_ascii=False))
