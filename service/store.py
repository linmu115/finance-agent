from __future__ import annotations
import json
import re
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

def utcnow():
    return datetime.now(timezone.utc).isoformat()

def dumps(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False)

class Store:
    """Single owning process, short per-thread connections, WAL and bounded lock waits."""
    def __init__(self, root):
        self.root = Path(root).resolve()
        for part in ("uploads", "documents", "artifacts", "exports"):
            (self.root / part).mkdir(parents=True, exist_ok=True)
        self.path = self.root / "finance.sqlite"
        self.write_lock = threading.RLock()
        with self.connect() as db:
            db.executescript("""
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS projects(project_id TEXT PRIMARY KEY,name TEXT NOT NULL,created_at TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS documents(document_id TEXT PRIMARY KEY,project_id TEXT NOT NULL,original_name TEXT NOT NULL,
              sha256 TEXT NOT NULL,relative_path TEXT NOT NULL,media_type TEXT NOT NULL,company TEXT,report_year INTEGER,
              page_count INTEGER DEFAULT 0,state TEXT NOT NULL,parser_version TEXT NOT NULL,warnings_json TEXT NOT NULL DEFAULT '[]',
              created_at TEXT NOT NULL,UNIQUE(project_id,sha256,parser_version),FOREIGN KEY(project_id) REFERENCES projects(project_id));
            CREATE TABLE IF NOT EXISTS pages(document_id TEXT,page INTEGER,text TEXT,printed_page TEXT,width REAL,height REAL,
              ocr INTEGER DEFAULT 0,PRIMARY KEY(document_id,page),FOREIGN KEY(document_id) REFERENCES documents(document_id));
            CREATE TABLE IF NOT EXISTS source_tables(table_id TEXT PRIMARY KEY,document_id TEXT,page INTEGER,sheet TEXT,
              bbox_json TEXT,rows_json TEXT,cells_json TEXT,FOREIGN KEY(document_id) REFERENCES documents(document_id));
            CREATE TABLE IF NOT EXISTS facts(fact_id TEXT PRIMARY KEY,document_id TEXT,project_id TEXT,company TEXT,metric TEXT,
              year INTEGER,period TEXT,scope TEXT,currency TEXT,raw_value TEXT,raw_unit TEXT,value TEXT,source_json TEXT,
              priority INTEGER,quality TEXT,FOREIGN KEY(document_id) REFERENCES documents(document_id));
            CREATE INDEX IF NOT EXISTS facts_lookup ON facts(project_id,metric,year,company);
            CREATE TABLE IF NOT EXISTS chunks(chunk_id TEXT PRIMARY KEY,project_id TEXT,document_id TEXT,page INTEGER,
              source_id TEXT,text TEXT,source_json TEXT);
            CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(chunk_id UNINDEXED, tokens, tokenize='unicode61');
            CREATE TABLE IF NOT EXISTS embedding_cache(cache_key TEXT PRIMARY KEY,project_id TEXT,model TEXT,dimensions INTEGER,
              vector_json TEXT,created_at TEXT);
            CREATE TABLE IF NOT EXISTS jobs(job_id TEXT PRIMARY KEY,project_id TEXT,document_id TEXT,state TEXT,progress REAL,
              message TEXT,error TEXT,created_at TEXT,updated_at TEXT);
            CREATE TABLE IF NOT EXISTS app_state(project_id TEXT,kind TEXT,key TEXT,value_json TEXT,updated_at TEXT,
              PRIMARY KEY(project_id,kind,key),FOREIGN KEY(project_id) REFERENCES projects(project_id));
            CREATE TABLE IF NOT EXISTS analysis_jobs(run_id TEXT PRIMARY KEY,project_id TEXT NOT NULL,state_json TEXT NOT NULL,
              created_at TEXT NOT NULL,updated_at TEXT NOT NULL,FOREIGN KEY(project_id) REFERENCES projects(project_id));
            CREATE TABLE IF NOT EXISTS processing_runs(processing_id TEXT PRIMARY KEY,project_id TEXT NOT NULL,
              owner_run_id TEXT NOT NULL,state_json TEXT NOT NULL,created_at TEXT NOT NULL,updated_at TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS normalization_batches(document_id TEXT NOT NULL,batch_key TEXT NOT NULL,
              processing_id TEXT NOT NULL,result_json TEXT NOT NULL,created_at TEXT NOT NULL,PRIMARY KEY(document_id,batch_key));
            CREATE TABLE IF NOT EXISTS normalization_cache(cache_key TEXT PRIMARY KEY,result_json TEXT NOT NULL,created_at TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS fact_history(history_id TEXT PRIMARY KEY,project_id TEXT NOT NULL,document_id TEXT NOT NULL,
              processing_id TEXT NOT NULL,fact_json TEXT NOT NULL,archived_at TEXT NOT NULL);
            """)
            # A killed parser never masquerades as a ready document; re-ingest retries cleanly.
            db.execute("UPDATE jobs SET state='failed',error='service_restarted',message='服务重启，重新上传可重试' WHERE state IN ('queued','parsing','validating')")
            db.execute("UPDATE documents SET state='failed' WHERE state IN ('queued','parsing','validating')")
            for row in db.execute("SELECT processing_id,state_json FROM processing_runs").fetchall():
                state = json.loads(row["state_json"])
                if state.get("state") in {"queued", "parsing", "normalizing"}:
                    state.update(state="failed", message="运行中断，可在会话中继续处理", errors=[{"code":"service_restarted"}])
                    db.execute("UPDATE processing_runs SET state_json=?,updated_at=? WHERE processing_id=?",(dumps(state),utcnow(),row["processing_id"]))
                    if db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='attachment_flows'").fetchone():
                        for flow in db.execute("SELECT flow_id,record_json FROM attachment_flows WHERE owner_run_id=? AND finished=0",(state.get('owner_run_id'),)).fetchall():
                            record=json.loads(flow['record_json'])
                            record.update(attempt_state='failed',state='failed',snapshot_missing=True,message='运行中断，未保存完整的处理结果快照；已提交数据保留，可在会话中重新处理。',updated_at=utcnow())
                            db.execute('UPDATE attachment_flows SET record_json=?,finished=1 WHERE flow_id=?',(dumps(record),flow['flow_id']))
            db.execute("UPDATE documents SET state='failed' WHERE state='normalizing'")

    @contextmanager
    def connect(self, write=False):
        lock = self.write_lock if write else _NullLock()
        with lock:
            db = sqlite3.connect(self.path, timeout=15)
            db.row_factory = sqlite3.Row
            db.execute("PRAGMA foreign_keys=ON")
            db.execute("PRAGMA busy_timeout=15000")
            try:
                yield db
                db.commit()
            except BaseException:
                db.rollback()
                raise
            finally:
                db.close()

    def project(self, project_id):
        if not isinstance(project_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,100}", project_id):
            raise ValueError("invalid_project_id")
        with self.connect() as db:
            row = db.execute("SELECT * FROM projects WHERE project_id=?", (project_id,)).fetchone()
        if row is None:
            raise ValueError("project_not_found")
        return dict(row)

    def document(self, project_id, document_id):
        self.project(project_id)
        with self.connect() as db:
            row = db.execute("SELECT * FROM documents WHERE document_id=? AND project_id=?", (document_id, project_id)).fetchone()
        if row is None:
            raise ValueError("document_not_found_in_project")
        result = dict(row)
        result["warnings"] = json.loads(result.pop("warnings_json"))
        return result

    def upload_path(self, path):
        candidate = Path(path).resolve(strict=True)
        candidate.relative_to((self.root / "uploads").resolve())
        if not candidate.is_file() or candidate.is_symlink():
            raise ValueError("invalid_upload_path")
        if candidate.stat().st_size > 100 * 1024 * 1024:
            raise ValueError("document_exceeds_100_mib")
        return candidate

    def job_update(self, job_id, state, progress, message="", error=None):
        with self.connect(write=True) as db:
            db.execute("UPDATE jobs SET state=?,progress=?,message=?,error=?,updated_at=? WHERE job_id=?",
                       (state, progress, message, error, utcnow(), job_id))
            db.execute("UPDATE documents SET state=? WHERE document_id=(SELECT document_id FROM jobs WHERE job_id=?)", (state, job_id))

class _NullLock:
    def __enter__(self): return self
    def __exit__(self, *args): return False
