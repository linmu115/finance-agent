"""Current checkpoint observation for the three development gate projects; SELECT only."""
import json, sqlite3
from datetime import datetime, timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
def readiness():
    specs=[('D1','03b52dde-19da-49c1-949a-ee6d93bf036b','3d9d0befd8374eed9a7488dbd8dd00d2',[],[]),
           ('X3','374beac2-a970-4972-b210-e91018bbd6e6','d84573bf6b584e7e874faa4c6adf454a',[8,11,12,253,254],[]),
           ('X7','d324c744-4113-4213-aa22-af3bb91a3c84','e7b0d9679ddc4b739f8f35ecb6dc6227',[9,11,14,114,115,298],[87,134])]
    result={}
    with sqlite3.connect((ROOT/'data/active/finance.sqlite').as_uri()+'?mode=ro',uri=True) as db:
        db.row_factory=sqlite3.Row;db.execute('BEGIN')
        for task,pid,did,required,alternative in specs:
            states=[json.loads(r['state_json']) for r in db.execute('SELECT state_json FROM processing_runs WHERE project_id=? ORDER BY updated_at DESC',(pid,))]
            matching=[s for s in states if any(d['document_id']==did for d in s['documents'])]
            state=matching[0] if matching else None
            doc=next(d for d in state['documents'] if d['document_id']==did) if state else {}
            done=set(doc.get('completed_tables',[]));deferred=doc.get('deferred_tables',{});issues=doc.get('validation_issues',{})
            items=[{'table':n,'submitted':n in done,'deferred':str(n) in deferred,'validation_issue':issues.get(str(n)),
                    'facts':db.execute("SELECT COUNT(*) FROM facts WHERE document_id=? AND json_extract(source_json,'$.table_id')=?",(did,did+':t'+str(n))).fetchone()[0]} for n in required+alternative]
            eligible=lambda r:r['submitted'] and not r['deferred'] and not r['validation_issue'] and r['facts']>0
            facts=db.execute('SELECT COUNT(*) FROM facts WHERE document_id=?',(did,)).fetchone()[0]
            pages=db.execute('SELECT COUNT(*) FROM pages WHERE document_id=?',(did,)).fetchone()[0]
            active=[r['key'] for r in db.execute("SELECT key FROM app_state WHERE kind='runs' AND project_id=? AND json_extract(value_json,'$.status') IN ('queued','running')",(pid,))]
            ready=bool(facts and pages) and all(eligible(r) for r in items if r['table'] in required) and (not alternative or any(eligible(r) for r in items if r['table'] in alternative))
            result[task]={'project':pid,'document':did,'processing_id':state.get('processing_id') if state else None,'owner_run_id':state.get('owner_run_id') if state else None,
                         'selection':'most recently updated checkpoint for this document; record owner for coordinator cross-check','coverage':state.get('coverage') if state else None,
                         'required_tables':required,'alternative_tables':alternative,'items':items,'facts':facts,'pages':pages,'gate_submitted':ready,'active_runs':active,
                         'deferred_tables':sorted(map(int,deferred)),'unsubmitted_tables':sorted(set(doc.get('tables',[]))-done) if all(isinstance(n,int) for n in doc.get('tables',[])) else None,
                         'review_issues':doc.get('review_issues',[])}
    return {'observed_at':datetime.now(timezone.utc).isoformat(),'method':'read-only consistent transaction; current updated checkpoint, never prior frozen counts','tasks':result,
            'all_required_submitted':all(r['gate_submitted'] for r in result.values()),'all_projects_idle':all(not r['active_runs'] for r in result.values())}
if __name__=='__main__':print(json.dumps(readiness(),ensure_ascii=False))
