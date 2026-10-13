"""N1-only SELECT snapshot, cell replay and separate old/new preparation accounting."""
import json,sqlite3,hashlib
from collections import Counter
from datetime import datetime,timezone
from decimal import Decimal,InvalidOperation
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/'data/evaluation/blind-eval-tsingtao-F1-20261008'
def read(p):return json.loads(p.read_text(encoding='utf-8'))
def dump(name,x):(OUT/name).write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def number(x):
 s=str(x).strip().replace(',','').replace('，','').replace('−','-').replace('％','%')
 if s.startswith(('(','（')) and s.endswith((')','）')):s='-'+s[1:-1]
 if s.endswith('%'):s=s[:-1]
 try:return Decimal(s)
 except InvalidOperation:return None
s=read(OUT/'preparation.json');j=s['job'];run=read(OUT/'run.json');did=j['documentId'];pid=j['projectId']
with sqlite3.connect((ROOT/'data/active/finance.sqlite').as_uri()+'?mode=ro',uri=True) as db:
 db.row_factory=sqlite3.Row;db.execute('BEGIN')
 facts=[dict(r) for r in db.execute('SELECT * FROM facts WHERE project_id=? AND document_id=? ORDER BY fact_id',(pid,did))]
 tables={r['table_id']:json.loads(r['rows_json']) for r in db.execute('SELECT table_id,rows_json FROM source_tables WHERE document_id=?',(did,))}
 batches=[dict(r) for r in db.execute('SELECT * FROM normalization_batches WHERE document_id=? ORDER BY created_at,batch_key',(did,))]
 processes=[json.loads(r['state_json']) for r in db.execute('SELECT state_json FROM processing_runs WHERE project_id=? AND owner_run_id=? ORDER BY created_at',(pid,j['runId']))]
 archived_count=db.execute('SELECT count(*) FROM fact_history WHERE project_id=? AND document_id=?',(pid,did)).fetchone()[0]
for f in facts:f['source']=json.loads(f.pop('source_json'))
for b in batches:b['result']=json.loads(b.pop('result_json'))
latest=processes[-1] if processes else None
replay=[]
for f in facts:
 ref=f['source'];norm=ref.get('normalization',{});table=tables.get(ref.get('table_id'));row=ref.get('row');col=ref.get('column')
 raw=table[row-1][col-1] if table is not None and isinstance(row,int) and isinstance(col,int) and 1<=row<=len(table) and 1<=col<=len(table[row-1]) else None
 span=norm.get('numeric_span');parsed=number(span['text'] if span else raw) if raw is not None else None
 scaled=parsed*Decimal(str(norm['scale'])) if parsed is not None and norm.get('scale') is not None else None
 replay.append({'fact_id':f['fact_id'],'table':ref.get('table_id'),'page':ref.get('page'),'row':row,'column':col,'raw_equal':raw is not None and str(f['raw_value'])==str(raw),'numeric_span_equal':not span or (isinstance(raw,str) and raw[span['start']:span['end']]==span['text']),'scaling_equal':scaled==Decimal(str(f['value'])) if scaled is not None else None,'saved_raw':f['raw_value'],'source_raw':raw,'saved_value':f['value'],'scale':norm.get('scale'),'scope':f['scope'],'period':f['period'],'metric':f['metric']})
active_batches=[b for b in batches if not b['result'].get('superseded_by')]
issues=[i for b in active_batches for i in b['result'].get('issues',[])]
cells={(i['table'],i['row'],i['column']) for i in issues if all(i.get(k) is not None for k in ['table','row','column'])}
events=[json.loads(l) for l in (OUT/'audit.jsonl').read_text(encoding='utf-8').splitlines()]
oldkeys=['input','output','uncachedInput','cacheRead','cacheWrite','reasoning','calls','unknownCalls','cacheUnknownCalls','costUnknownCalls']
oldusage=[a.get('usage') for a in s['oldLedger']['attempts']]
oldtotals={k:{'known_sum':sum(u[k] for u in oldusage if u is not None and u.get(k) is not None),'unknown_runs':sum(u is None or u.get(k) is None for u in oldusage)} for k in oldkeys}
coverage=latest.get('coverage') if latest else j.get('latestCoverage')
summary={'observed_at':datetime.now(timezone.utc).isoformat(),'read_mode':'SQLite URI mode=ro SELECT-only consistent snapshot; no Store constructor, no product writes','run_id':j['runId'],'run_status':run['status'],'run_error':run.get('error'),'finished_at':run.get('finishedAt'),'preparation_complete':bool(coverage and coverage['tables_completed']==coverage['tables_total'] and coverage.get('pages_reviewed',0)==coverage.get('pages_total',0)),'coverage':coverage,'duration_ms':j.get('elapsedMs'),'document_id':did,'project_id':pid,'parsed_tables':j.get('document',j['before'])['tableCount'],'facts':len(facts),'scopes':dict(Counter(f['scope'] for f in facts)),'accounting_basis':dict(Counter(json.dumps(f['source'].get('normalization',{}).get('accounting_basis'),ensure_ascii=False,sort_keys=True) for f in facts)),'source_processing_ids':dict(Counter(f['source'].get('normalization',{}).get('processing_id','not_recorded') for f in facts)),'review_cells_any_reason':len(cells),'issue_counts':dict(Counter(i['reason'] for i in issues)),'raw_cell_replay':{'total':len(replay),'passed':sum(r['raw_equal'] and r['numeric_span_equal'] for r in replay),'failed':sum(not(r['raw_equal'] and r['numeric_span_equal']) for r in replay)},'scaling_replay':{'passed':sum(r['scaling_equal'] is True for r in replay),'failed':sum(r['scaling_equal'] is False for r in replay),'unverified':sum(r['scaling_equal'] is None for r in replay)},'semantic_acceptance':'not_established_by_replay_or_coverage','old_10_attempts_usage':oldtotals,'new_usage':run.get('usage'),'CPA_billed_cost':None,'expense_category':'material_preparation_only','auto_continuations':sum(e['type']=='ingestion_continuation' for e in events),'manual_followups':0,'terminal_ingestion_events':[e for e in events if e['type']=='ingestion_stalled'],'reasoning_requests':dict(Counter(e['data'].get('sentReasoningEffort','unknown') for e in events if e['type']=='model_request')),'model_request_count':sum(e['type']=='model_request' for e in events),'processing_state':latest,'old_ledger_unchanged':hashlib.sha256((ROOT/s['oldLedger']['path']).read_bytes()).hexdigest()==s['oldLedger']['sha256']}
summary['coverage_complete']=summary.pop('preparation_complete')
summary['host_terminal']=run['status'] in ['completed','failed','cancelled']
summary['preparation_complete']=summary['host_terminal'] and run['status']=='completed' and summary['coverage_complete']
summary['batch_accounting']={'all_batches':len(batches),'active_not_superseded':len(active_batches),'superseded':len(batches)-len(active_batches),'archived_fact_versions':archived_count,'review_issue_scope':'Only non-superseded saved batches; deferred/unsubmitted issues separately retained in processing_state.'}
summary['remaining']=[{'document_id':d['document_id'],'pending_tables':sorted(set(d['tables'])-set(d['completed_tables'])),'deferred_tables':d.get('deferred_tables',{}),'core_coverage':d.get('coverage'),'validation_issues':d.get('validation_issues',{})} for d in (latest or {}).get('documents',[])]
summary['repair_phase']=bool((latest or {}).get('repair_phase'))
summary['fact_quality']=dict(Counter(f['quality'] for f in facts))
summary['companies']=dict(Counter(f['company'] for f in facts))
summary['currencies']=dict(Counter(f['currency'] for f in facts))
summary['periods']=dict(Counter(str(f['year'])+':'+f['period'] for f in facts))
coordinates=Counter((f['source'].get('table_id'),f['source'].get('row'),f['source'].get('column')) for f in facts)
summary['multiply_mapped_source_cells']=[{'table':k[0],'row':k[1],'column':k[2],'record_count':n} for k,n in coordinates.items() if n>1]
summary['duplicate_cell_note']='Multiple metrics from one source cell require semantic review; this count alone does not establish an erroneous duplicate.'
summary['previous_58a_resume_usage']=read(ROOT/'data/evaluation/blind-eval-tsingtao-resume-20261008/run.json').get('usage')
for name,v in [('quality-summary.json',summary),('facts.json',facts),('source-tables.json',tables),('normalization-batches.json',batches),('processing-states.json',processes),('raw-cell-replay.json',replay)]:dump(name,v)
print(json.dumps({k:summary[k] for k in ['run_status','coverage','facts','scopes','review_cells_any_reason','raw_cell_replay','scaling_replay','old_ledger_unchanged']},ensure_ascii=False))

