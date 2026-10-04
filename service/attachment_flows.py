"""Per-conversation-attempt evidence snapshots, never a view of the latest document state."""
import json
from .store import dumps, utcnow

TERMINAL={'completed','failed','cancelled','needs_review'}

def initialize(db):
    db.execute('CREATE TABLE IF NOT EXISTS attachment_flows(flow_id TEXT PRIMARY KEY, project_id TEXT, owner_run_id TEXT, document_id TEXT, baseline_json TEXT, record_json TEXT, snapshot_json TEXT, finished INTEGER DEFAULT 0, created_at TEXT)')
    db.execute('CREATE INDEX IF NOT EXISTS flow_owner ON attachment_flows(project_id,owner_run_id)')

def snapshot(db, document_id):
    facts=[dict(r) for r in db.execute('SELECT * FROM facts WHERE document_id=? ORDER BY metric,year,fact_id',(document_id,))]
    for fact in facts: fact['source']=json.loads(fact.pop('source_json') or '{}')
    tables=[dict(r) for r in db.execute('SELECT * FROM source_tables WHERE document_id=?',(document_id,))]
    for table in tables:
        table['rows']=json.loads(table.pop('rows_json') or '[]');table.pop('cells_json',None)
    destination={table:db.execute(f'SELECT count(*) FROM {table} WHERE document_id=?',(document_id,)).fetchone()[0] for table in ['pages','source_tables','chunks','facts']}
    doc=db.execute('SELECT sha256,parser_version FROM documents WHERE document_id=?',(document_id,)).fetchone()
    return {'facts':facts,'tables':tables,'destinations':destination,'source_version':dict(doc) if doc else None}

def record_processing(db, state):
    initialize(db)
    for document in state.get('documents',[]):
        did=document['document_id']; fid=state['processing_id']+':'+did
        old=db.execute('SELECT baseline_json,finished,created_at FROM attachment_flows WHERE flow_id=?',(fid,)).fetchone()
        if old and old['finished']: continue
        initial=json.loads(old['baseline_json']) if old else snapshot(db,did)['facts']
        complete=state['state'] in TERMINAL
        record={**document,'flow_id':fid,'processing_id':state['processing_id'],'owner_run_id':state['owner_run_id'],'attempt_state':state['state'],'message':state.get('message'),'errors':state.get('errors',[]),'created_at':old['created_at'] if old else state['created_at'],'updated_at':state['updated_at']}
        record['mode']='reuse' if document.get('reused') or document.get('reused_shared') else 'review' if state.get('mode')=='existing_source_definition_review' else 'reprocess' if initial else 'process'
        record['verification']='needs_review' if state['state']=='needs_review' or document.get('warnings') or document.get('state')=='needs_review' or state.get('errors') else 'not_manually_verified'
        result=snapshot(db,did) if complete else {}
        if complete:
            before={r['fact_id']:r for r in initial};after={r['fact_id']:r for r in result['facts']}
            record['changes']={'added':len(after.keys()-before.keys()),'removed':len(before.keys()-after.keys()),'changed':sum(after[k]!=before[k] for k in after.keys()&before.keys()),'total':len(after)}
            record['reviews']={k:state[k] for k in ['catalog_review','definition_review','temporal_review'] if k in state}
        db.execute('INSERT INTO attachment_flows VALUES(?,?,?,?,?,?,?,?,?) ON CONFLICT(flow_id) DO UPDATE SET record_json=excluded.record_json,snapshot_json=excluded.snapshot_json,finished=excluded.finished',
                   (fid,state['project_id'],state['owner_run_id'],did,dumps(initial),dumps(record),dumps(result),int(complete),record['created_at']))

def record_read(store, project_id, owner_run_id, document_id, mode='reuse'):
    doc=store.document(project_id,document_id)
    with store.connect(write=True) as db:
        initialize(db)
        # Reading source evidence after processing must not create a second fictitious attempt.
        if db.execute('SELECT 1 FROM attachment_flows WHERE project_id=? AND owner_run_id=? AND document_id=?',(project_id,owner_run_id,document_id)).fetchone(): return
        result=snapshot(db,document_id);fid=owner_run_id+':read:'+document_id
        record={'flow_id':fid,'owner_run_id':owner_run_id,'document_id':document_id,'name':doc['original_name'],'mode':mode,'state':'ready','attempt_state':'completed','progress':1,'fact_count':len(result['facts']),'verification':'not_manually_verified','created_at':utcnow(),'changes':{'added':0,'removed':0,'changed':0,'total':len(result['facts'])}}
        db.execute('INSERT INTO attachment_flows VALUES(?,?,?,?,?,?,?,?,?)',(fid,project_id,owner_run_id,document_id,'[]',dumps(record),dumps(result),1,record['created_at']))

def read(store, project_id, owner_run_ids, flow_id=None, offset=0):
    store.project(project_id)
    if not owner_run_ids: return {'flows':[]}
    if len(owner_run_ids)>10000: raise ValueError('too_many_runs')
    with store.connect(write=True) as db:
        initialize(db)
        where='project_id=? AND owner_run_id IN ('+','.join('?' for _ in owner_run_ids)+')'
        args=[project_id,*owner_run_ids]
        if flow_id:
            where+=' AND flow_id=?';args.append(flow_id)
        columns='*' if flow_id else 'record_json'
        rows=db.execute('SELECT '+columns+' FROM attachment_flows WHERE '+where+' ORDER BY created_at DESC',args).fetchall()
        if not flow_id: return {'flows':[json.loads(r['record_json']) for r in rows]}
        if not rows: raise ValueError('flow_not_found_in_conversation')
        row=rows[0];result=json.loads(row['snapshot_json']);facts=result.get('facts',[])
        offset=max(0,int(offset));page=facts[offset:offset+50]
        for f in page:
            current=db.execute('SELECT value,metric,period,scope FROM facts WHERE fact_id=?',(f['fact_id'],)).fetchone()
            f['current_match']=bool(current and all(current[k]==f[k] for k in current.keys()))
        return {**json.loads(row['record_json']),'facts':page,'fact_total':len(facts),'offset':offset,'tables':[{**{k:v for k,v in t.items() if k!='rows'},'rows':t['rows'][:10],'row_count':len(t['rows'])} for t in result.get('tables',[])], 'finished':bool(row['finished']),'destinations':result.get('destinations'),'source_version':result.get('source_version')}
