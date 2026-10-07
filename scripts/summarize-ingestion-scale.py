"""Measure only the explicitly supplied N3 scratch run; never search other data."""
import collections
import json
import sqlite3
import sys
from pathlib import Path

root = Path(sys.argv[1]).resolve()
run = json.loads((root / 'run.json').read_text(encoding='utf-8'))
audit = [json.loads(line) for line in (root / 'app-data/audit' / (run['runId'] + '.jsonl')).read_text(encoding='utf-8').splitlines()]
payloads = [json.loads(line)['payload'] for line in (root / 'payloads.jsonl').read_text(encoding='utf-8').splitlines()]
usages = [x['data'] for x in audit if x['type'] == 'model_usage']
measurements = []
for number, payload in enumerate(payloads):
    messages = payload.get('input', payload.get('messages', []))
    names = {m.get('call_id'): m.get('name') for m in messages if m.get('type') == 'function_call'}
    parts = collections.Counter()
    by_tool = collections.Counter()
    seen = set()
    duplicate = 0
    for message in messages:
        kind = message.get('role', message.get('type'))
        text = json.dumps(message, ensure_ascii=False, separators=(',', ':'))
        if text in seen: duplicate += len(text)
        seen.add(text)
        if kind in {'system', 'developer'}: key = 'system'
        elif kind == 'function_call_output':
            name = names.get(message.get('call_id'), 'unknown')
            key = 'source_content' if name in {'get_source_table', 'get_source_page', 'get_cleaning_batch', 'get_document_index'} else 'history_results'
            by_tool[name] += len(text)
        else: key = 'user_and_assistant_history'
        parts[key] += len(text)
    parts['tool_definitions'] = len(json.dumps(payload.get('tools', []), ensure_ascii=False, separators=(',', ':')))
    measurements.append({'request': number + 1, 'components_chars': dict(parts), 'tool_result_chars': dict(by_tool), 'exact_duplicate_messages_chars': duplicate, 'total_chars': sum(parts.values())})
tool_errors = [x['data'] for x in audit if x['type'] == 'tool_error']
commits = [x['data']['result']['data'] for x in audit if x['type'] == 'tool_result' and x['data']['name'] == 'commit_cleaning_result']
known = [x['usage'] for x in usages if x.get('usageKnown')]
totals = {k: sum(u.get(k, 0) for u in known) for k in ['input', 'cacheRead', 'cacheWrite', 'output', 'reasoning']}
summary = {'expense_category': '资料准备研发', 'model': run['model'], 'requests': len(usages), 'unknown_usage_requests': sum(not u.get('usageKnown') for u in usages),
           'captured_payloads':len(payloads),
           'reasoning_calls': dict(collections.Counter(x.get('reasoningEffort','unknown') for x in usages)),
           'requests_by_phase':dict(collections.Counter(x.get('usagePhase',x.get('phase','unknown')) for x in usages)),
           'tokens': {'total_input': totals['input'] + totals['cacheRead'] + totals['cacheWrite'], 'uncached_input': totals['input'], 'cached_input': totals['cacheRead'], 'output': totals['output'], 'reasoning': totals['reasoning']},
           'currency_cost': None, 'cost_note': 'CPA actual pricing unavailable; model catalog cost is not a CPA invoice.',
           'tool_requests': dict(collections.Counter(x['data']['name'] for x in audit if x['type'] == 'tool_request')),
           'tool_errors': tool_errors, 'last_commit': commits[-1] if commits else None, 'contexts': measurements}
if (root / 'result.json').exists():
    result = json.loads((root / 'result.json').read_text(encoding='utf-8'))
    summary.update(duration_ms=result['durationMs'], status=result['run']['status'], error=result['run'].get('error'), checkpoint=result['checkpoint']['data'], document=result['document'])
databases = list((root / 'app-data').glob('*.sqlite*'))
dbfile = next((p for p in databases if p.suffix in {'.sqlite', '.sqlite3'}), None)
if dbfile:
    db = sqlite3.connect(dbfile.as_uri() + '?mode=ro', uri=True)
    db.row_factory = sqlite3.Row
    facts = [dict(row) for row in db.execute('SELECT * FROM facts WHERE document_id=?', (run['documentId'],))]
    research = [dict(row) for row in db.execute('SELECT * FROM research_records WHERE document_id=? AND is_current=1', (run['documentId'],))]
    observations = []
    for record in research:
        if record['record_type'] == 'observation':
            item=json.loads(record['record_json'])
            observations.append({**item,'fact_id':record['record_id'],'source_json':record['source_json']})
    states=[json.loads(row[0]) for row in db.execute('SELECT state_json FROM processing_runs WHERE owner_run_id=? ORDER BY created_at', (run['runId'],))]
    summary['processing_coverage'] = states[-1].get('coverage') if states else None
    reuse={k:set() for k in ('signature_hits','completed_tables','standard_tables')}
    model_tables=set()
    for state in states:
        for document in state.get('documents',[]):
            if document['document_id']!=run['documentId']:continue
            for key in reuse:reuse[key].update(document.get('rule_reuse',{}).get(key,[]))
        for job in state.get('jobs',{}).values():
            if job['document_id']==run['documentId'] and not job.get('rule_payload'):
                model_tables.update(job.get('candidate_tables',[]))
    summary['rule_reuse']={k:sorted(v) for k,v in reuse.items()}|{'model_tables':sorted(model_tables)}
    if db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='cleaning_rules'").fetchone():
        summary['library_rules']=db.execute('SELECT count(*) FROM cleaning_rules').fetchone()[0]
    summary['scopes']=dict(collections.Counter(f['scope'] for f in facts))
    summary['research_observations'] = len(observations)
    summary['research_claims'] = sum(r['record_type']=='claim' for r in research)
    summary['automatic_continuations'] = sum(x['type']=='ingestion_continuation' for x in audit)
    summary['stalled'] = any(x['type']=='ingestion_stalled' for x in audit)
    tables = {row['table_id']: json.loads(row['rows_json']) for row in db.execute('SELECT * FROM source_tables WHERE document_id=?', (run['documentId'],))}
    replay = []
    for fact in facts + observations:
        ref = json.loads(fact['source_json'])
        raw = tables[ref['table_id']][ref['row'] - 1][ref['column'] - 1]
        span = ref.get('normalization', {}).get('numeric_span')
        span_ok = not span or raw[span['start']:span['end']] == span['text']
        replay.append({'fact_id': fact['fact_id'], 'table': ref['table_id'], 'row': ref['row'], 'column': ref['column'], 'ok': fact['raw_value'] == raw and span_ok, 'raw_value': fact['raw_value'], 'expected': raw, 'span_ok': span_ok})
    summary['facts'] = len(facts)
    summary['facts_by_quality']=dict(collections.Counter(f.get('quality','unknown') for f in facts))
    saved=[json.loads(row[0]) for row in db.execute('SELECT result_json FROM normalization_batches WHERE document_id=?',(run['documentId'],))]
    issues=[i for batch in saved for i in batch.get('issues',[])]
    summary['recorded_issues']=dict(collections.Counter(i['reason'] for i in issues))
    summary['unresolved_cells']=len({(i.get('table'),i.get('row'),i.get('column')) for i in issues if i['reason']=='unresolved_cell_semantics'})
    summary['excluded_tables']=sum(any(e['class']=='table_schema' and e['attributes'].get('statement')=='nonfinancial' for e in b.get('extractions',[])) for b in saved)
    summary['tables_with_recorded_issues']=sum(bool(b.get('issues')) for b in saved)
    summary['generic_metric_facts']=sum(f['metric'] in {'amount','value','number','data','financial_metric'} for f in facts)
    summary['raw_cell_replay'] = {'passed': sum(x['ok'] for x in replay), 'total': len(replay), 'failures': [x for x in replay if not x['ok']]}
    (root / 'facts.json').write_text(json.dumps(facts, ensure_ascii=False, indent=2), encoding='utf-8')
    (root / 'research-records.json').write_text(json.dumps([json.loads(r['record_json']) for r in research], ensure_ascii=False, indent=2), encoding='utf-8')
    (root / 'raw-cell-replay.json').write_text(json.dumps(replay, ensure_ascii=False, indent=2), encoding='utf-8')
(root / 'measurements.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps({k: v for k, v in summary.items() if k not in {'contexts','checkpoint','document','last_commit','tool_errors'}}, ensure_ascii=False, indent=2))
print('last context:', json.dumps(measurements[-1] if measurements else {}, ensure_ascii=False))
