"""Copy exactly two authorized documents read-only; replay without a model/HTTP."""
import argparse
import json
from pathlib import Path
import shutil
import sqlite3
import sys
from collections import Counter

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from service.core import FinanceService
from service.cleaning_consistency import document_conflicts
from service.cleaning_consistency import table_semantics
from service.cleaning_queue import record_attempt
from service.source_numbers import identifier_table_exclusion
from service.source_dimensions import apply_source_dimensions
from service.cleaning_rules import context

DOCUMENTS={
    'yili':('374beac2-a970-4972-b210-e91018bbd6e6','d84573bf6b584e7e874faa4c6adf454a'),
    'haier':('d324c744-4113-4213-aa22-af3bb91a3c84','e7b0d9679ddc4b739f8f35ecb6dc6227'),
}
def write(path,value):path.write_text(json.dumps(value,ensure_ascii=False,indent=2),'utf-8')
def shutdown(s):
    for name in ('pool','analysis_pool','embedding_pool','processing_pool'):getattr(s,name).shutdown(wait=True)
def copy_document(source,out,project,did):
    s=FinanceService(out/'app-data');s._schedule_embedding_index=lambda *a:None
    db=sqlite3.connect((source/'finance.sqlite').as_uri()+'?mode=ro',uri=True);db.row_factory=sqlite3.Row
    with s.store.connect(write=True) as target:
        for table,key,value in [('projects','project_id',project)]+[(t,'document_id',did) for t in ('documents','pages','source_tables','facts','fact_history','prepared_documents','document_profiles','normalization_batches')]:
            columns=[r[1] for r in target.execute(f'PRAGMA table_info({table})')]
            for row in db.execute(f'SELECT * FROM {table} WHERE {key}=?',(value,)):
                names=[c for c in columns if c in row.keys()]
                target.execute(f'INSERT INTO {table} ({",".join(names)}) VALUES ({",".join("?" for _ in names)})',[row[c] for c in names])
        for row in db.execute('SELECT * FROM processing_runs WHERE project_id=?',(project,)):
            state=json.loads(row['state_json'])
            if did not in {d['document_id'] for d in state.get('documents',[])}:continue
            names=[r[1] for r in target.execute('PRAGMA table_info(processing_runs)') if r[1] in row.keys()]
            target.execute(f'INSERT INTO processing_runs ({",".join(names)}) VALUES ({",".join("?" for _ in names)})',[row[c] for c in names])
    doc=s.store.document(project,did);path=s.store.root/doc['relative_path'];path.parent.mkdir(parents=True,exist_ok=True)
    shutil.copyfile(source/doc['relative_path'],path);db.close();return s


def rejudge_conflicts(baseline,parsed):
    old=json.loads((baseline/'33-conflicts.json').read_text('utf-8'))
    candidates=json.loads((baseline/'conflict-candidate-items.json').read_text('utf-8'))
    indices={x['index'] for x in candidates}
    saved=json.loads((baseline/'semantic-items.json').read_text('utf-8'))
    items=[x for x in saved if x['table']['index'] not in indices]+candidates
    for item in items:apply_source_dimensions(item['table'],item['facts'],context=context(parsed,item['table']))
    remaining=document_conflicts(items)
    assert len(old)==33 and not remaining
    facts={(f['source']['table_id'],f['source']['row'],f['source']['column'],f['metric'],f['period']):f for i in items for f in i['facts']}
    verdicts=[]
    for issue in old:
        sides=[facts[(issue[side]['table_id'],issue[side]['row'],issue[side]['column'],issue['metric'],issue['period'])]['source']['normalization'] for side in ('left','right')]
        differences={k for k in set(sides[0]['dimensions'])|set(sides[1]['dimensions']) if sides[0]['dimensions'].get(k)!=sides[1]['dimensions'].get(k)}
        category='related_party' if 'related_party' in differences else 'hierarchy' if 'composition' in differences else 'balance_direction' if 'balance_side' in differences else 'unclassified'
        assert category!='unclassified'
        verdicts.append({'original':issue,'verdict':'distinct_economic_identity','category':category,
                         'sides':[{k:s.get(k) for k in ('dimensions','source_dimension_evidence')} for s in sides]})
    return {'original_groups':len(old),'retained_conflicts':len(remaining),'resolved_by':dict(Counter(v['category'] for v in verdicts)),'groups':verdicts}


def replay(s,name,project,did,folder,baseline):
    doc,parsed=s._clean_source(project,did)
    states=s._related_cleanings(project,[did]);pid=states[0]['processing_id']
    before=s.get_cleaning_progress(project,pid)['data']
    conflict_report=rejudge_conflicts(baseline/'yili',parsed) if name=='yili' else None
    if name=='yili':
        state=s._clean_state(project,pid)
        _,validated,_=s._clean_result(project,state,'8f8368a0e1544aedad9744386a0cd274')
        assert not any(i['reason']=='document_value_conflict' for t in validated for i in t['issues'])
        conflict_report['full_validator_tables']=[{'table':t['index'],'fact_count':len(t['facts']),'remaining_issues':t['issues']} for t in validated]
    # No sandbox work or inference is needed to exercise the real production
    # begin/commit/settle methods on this isolated copy.
    s._runner=lambda:(_ for _ in ()).throw(AssertionError('sandbox_not_allowed_in_deterministic_replay'))
    begun=s.begin_script_cleaning(project,[did],'deterministic-table-deferral','gpt-6-luna',require_profile=True)['data']
    state=s._clean_state(project,pid)
    # Replay the actual Haier mapping failure from our previous production
    # audit, preserving its nine source coordinates and values. Yili t87 uses
    # its current immutable source and the exact zero-record validator.
    if name=='haier':
        audit=[json.loads(line) for line in (ROOT/'tmp/haier-full-production-20261008/audit.jsonl').read_text('utf-8').splitlines()]
        failed=next(r['data']['details']['failed_tables'] for r in reversed(audit) if r['type']=='tool_error' and r['data'].get('message')=='script_validation_errors_table_125_unmapped_numeric_column')
        record_attempt(state,did,failed)
    else:
        table=next(t for t in parsed['tables'] if t['index']==87)
        issues=table_semantics(table,{},[])
        assert issues and issues[0]['reason']=='numeric_table_without_records'
        record_attempt(state,did,[{'index':87,'issues':issues}])
    s._save_processing(state)
    steps=[]
    for _ in range(3):
        current=s.advance_cleaning_round(project,pid)['data'];steps.append(current)
        assert current['next_batch'] and current['runnable_tables'][did]
        assert not set(current['next_batch']['tables'])&{int(i) for i in current['deferred_tables'][did]}
    exclusions=[t['index'] for t in parsed['tables'] if identifier_table_exclusion(t)]
    done=set(begun['document_progress'][0]['completed_tables'])
    assert not set(before['document_progress'][0]['completed_tables'])-done, 'correct_committed_table_reopened'
    eligible=set(state['documents'][0]['tables'])
    assert set(exclusions)&eligible<=done
    if name=='yili':assert 6 in done and 87 not in done and '87' in steps[0]['deferred_tables'][did]
    else:assert '125' in steps[0]['deferred_tables'][did]
    aliases={alias:s.get_source_table(project,did,alias)['data']['items'][0]['table_id'] for alias in ('125','t125','T125')}
    assert len(set(aliases.values()))==1
    report={'document':name,'model_calls':0,'before':before['coverage'],'after_deterministic_rules':begun['coverage'],
            'facts_before':before['fact_count'],'facts_after':begun['fact_count'],
            'company_identifier_tables_completed':sorted(set(exclusions)&eligible),
            'previously_completed_reopened':sorted(set(before['document_progress'][0]['completed_tables'])-done),
            'first_batch':begun['next_batch'],'settle_steps':[{'next_batch':x['next_batch'],'coverage':x['coverage'],
                'newly_deferred':x['newly_deferred'],'runnable_count':len(x['runnable_tables'][did]),'repair_phase':x['repair_phase']} for x in steps],
            'deferred_tables':steps[-1]['deferred_tables'][did],'aliases':aliases,'conflicts':conflict_report}
    write(folder/'replay-report.json',report)
    return report
def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',required=True);parser.add_argument('--source',default=r'D:\AI\财报agent\data\active')
    parser.add_argument('--baseline',default='tmp/table-deferral-baseline')
    a=parser.parse_args();out=Path(a.output).resolve()
    if not out.is_relative_to(ROOT/'tmp'):raise ValueError('output_must_be_worktree_tmp')
    out.mkdir(parents=True,exist_ok=False)
    reports=[]
    for name,(project,did) in DOCUMENTS.items():
        folder=out/name;folder.mkdir();s=copy_document(Path(a.source),folder,project,did)
        try:
            report=replay(s,name,project,did,folder,Path(a.baseline));reports.append(report)
            print(json.dumps({k:report[k] for k in ('document','before','after_deterministic_rules','facts_before','facts_after','company_identifier_tables_completed','previously_completed_reopened','model_calls')},ensure_ascii=False),flush=True)
        finally:shutdown(s)
    write(out/'report.json',{'model_calls':0,'documents':reports})
if __name__=='__main__':main()
