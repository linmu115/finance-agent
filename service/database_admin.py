"""Host-only database operations. The Node host obtains single-use UI approval first."""
import hashlib
import json
import sqlite3
import time
from decimal import Decimal
from uuid import uuid4
from contextlib import closing
from .store import dumps, utcnow

PROTECTED = {'app_state','analysis_jobs','processing_runs','attachment_flows','database_audit','normalization_cache','normalization_batches','prepared_documents'}

def initialize(store):
    with store.connect(write=True) as db:
        db.execute('CREATE TABLE IF NOT EXISTS database_audit(id TEXT PRIMARY KEY, approval_id TEXT UNIQUE, project_id TEXT, operation_json TEXT, result_json TEXT, created_at TEXT)')

def execute(store, project_id, operation, approval_id):
    store.project(project_id)
    if not approval_id or len(approval_id)>100: raise ValueError('approval_required')
    initialize(store)
    kind=operation.get('operation')
    target=operation.get('target_project_id') or project_id
    if kind not in {'sql','read_other_project','update_fact','delete_fact','delete_document','analysis_changes'}: raise ValueError('invalid_database_operation')
    if kind!='sql': store.project(target)
    commands=[]
    if kind=='read_other_project':
        commands=[{'sql':'SELECT * FROM facts WHERE project_id=? ORDER BY document_id,metric,year LIMIT 201','parameters':[target]}]
    elif kind=='sql': commands=[{'sql':operation.get('sql',''),'parameters':operation.get('parameters',[])}]
    elif kind=='analysis_changes':
        commands=operation.get('commands',[])
        if not commands or len(commands)>32: raise ValueError('invalid_analysis_changes')
    elif kind=='update_fact':
        value=str(operation.get('value',''))
        if not Decimal(value).is_finite(): raise ValueError('invalid_fact_value')
        commands=[{'sql':'UPDATE facts SET value=?, quality=? WHERE fact_id=? AND project_id=?','parameters':[value,'user_authorized_edit',operation.get('fact_id'),target]}]
    elif kind=='delete_fact': commands=[{'sql':'DELETE FROM facts WHERE fact_id=? AND project_id=?','parameters':[operation.get('fact_id'),target]}]
    else:
        doc=store.document(target,operation.get('document_id'))
        # Preserve original file and historical evidence for recovery. Remove active rows atomically.
        commands=[{'sql':'DELETE FROM chunks_fts WHERE chunk_id IN (SELECT chunk_id FROM chunks WHERE document_id=?)','parameters':[doc['document_id']]}]
        for table in ['pages','source_tables','facts','chunks','jobs','documents']:
            commands.append({'sql':f'DELETE FROM {table} WHERE document_id=?','parameters':[doc['document_id']]})
    for command in commands:
        if not isinstance(command,dict) or not isinstance(command.get('sql'),str) or len(command['sql'])>20000 or not isinstance(command.get('parameters',[]),list): raise ValueError('invalid_sql_command')
    backup=None
    with store.write_lock:
        with store.connect() as db:
            if db.execute('SELECT 1 FROM database_audit WHERE approval_id=?',(approval_id,)).fetchone(): raise ValueError('approval_already_consumed')
            if kind!='read_other_project':
                folder=store.root/'backups'/'database';folder.mkdir(parents=True,exist_ok=True)
                backup=folder/(str(uuid4())+'.sqlite')
                with closing(sqlite3.connect(backup)) as destination: db.backup(destination)
        with store.connect(write=True) as db:
            # Persist consumption before execution; failed operations cannot reuse approval either.
            db.execute('INSERT INTO database_audit VALUES(?,?,?,?,?,?)',(str(uuid4()),approval_id,project_id,dumps(operation),'{}',utcnow()))
        try:
            with store.connect(write=True) as db:
                db.execute('BEGIN IMMEDIATE')
                stop=time.monotonic()+10
                db.set_progress_handler(lambda: int(time.monotonic()>stop),1000)
                def authorize(action,a,b,database,trigger):
                    a=(a or '').lower();b=(b or '').lower()
                    if action in {sqlite3.SQLITE_ATTACH,sqlite3.SQLITE_DETACH,sqlite3.SQLITE_PRAGMA,sqlite3.SQLITE_TRANSACTION,sqlite3.SQLITE_SAVEPOINT}: return sqlite3.SQLITE_DENY
                    if action==sqlite3.SQLITE_FUNCTION and b in {'load_extension','writefile','readfile','eval'}: return sqlite3.SQLITE_DENY
                    # No changes to runtime/security state, even through triggers or renamed tables.
                    writes={sqlite3.SQLITE_INSERT,sqlite3.SQLITE_UPDATE,sqlite3.SQLITE_DELETE,sqlite3.SQLITE_DROP_TABLE,sqlite3.SQLITE_ALTER_TABLE,sqlite3.SQLITE_CREATE_TRIGGER,sqlite3.SQLITE_DROP_TRIGGER,sqlite3.SQLITE_CREATE_INDEX,sqlite3.SQLITE_DROP_INDEX}
                    if action in writes and ({a,b}&PROTECTED): return sqlite3.SQLITE_DENY
                    if action==sqlite3.SQLITE_READ and a in PROTECTED: return sqlite3.SQLITE_DENY
                    return sqlite3.SQLITE_OK
                if kind in {'sql','analysis_changes'}: db.set_authorizer(authorize)
                results=[]
                try:
                    for command in commands:
                        cursor=db.execute(command['sql'],command.get('parameters',[]))
                        rows=[dict(r) for r in cursor.fetchmany(201)] if cursor.description else []
                        results.append({'rows':rows[:200],'truncated':len(rows)>200,'affected_rows':max(cursor.rowcount,0)})
                finally:
                    db.set_authorizer(None);db.set_progress_handler(None,0)
            result={'results':results,'backup':str(backup.relative_to(store.root)) if backup else None,'approval_id':approval_id}
        except Exception as exc:
            with store.connect(write=True) as db: db.execute('UPDATE database_audit SET result_json=? WHERE approval_id=?',(dumps({'error':str(exc),'backup':str(backup.relative_to(store.root)) if backup else None}),approval_id))
            raise
        with store.connect(write=True) as db: db.execute('UPDATE database_audit SET result_json=? WHERE approval_id=?',(dumps(result),approval_id))
    return result
