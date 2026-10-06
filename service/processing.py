"""Session-owned document tools. Pi supplies a private, run-scoped model bridge."""
from __future__ import annotations
import hashlib
import json
import mimetypes
import os
import queue
import re
import shutil
import subprocess
import sys
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import urlparse

from .normalization import METRICS, unit_kind
from .parser import PARSER_VERSION, parse_document
from .semantic import VERSION, SCHEMA_HASH, STATEMENTS, normalize_document, table_batches, materialize
from .catalog_semantics import canonicalize_project, directory_status
from .completed_document import completed_document
from .definition_semantics import review_project as review_definition_project, overlay_saved_definitions, definition_status
from .temporal_semantics import review_project as review_temporal_project, temporal_review_status, stamp_source_provenance, overlay_saved_corrections
from .store import dumps, utcnow


def envelope(data, refs=None, status="ok"):
    return {"status":status,"data":data,"source_refs":refs or [],"warnings":[],"trace_id":uuid.uuid4().hex}


TERMINAL = {"ready", "needs_review", "completed", "partial", "failed", "cancelled"}


def _source_index(parsed):
    """Fields whose identity is persisted in source pages and source tables."""
    return {"pages": [{key: page.get(key, False if key == "ocr" else None)
                        for key in ("page", "text", "printed_page", "width", "height", "ocr")}
                       for page in sorted(parsed["pages"], key=lambda page: page["page"])],
            "tables": [{key: table.get(key, {} if key == "cells" else None)
                         for key in ("index", "page", "sheet", "bbox", "rows", "cells")}
                        for table in sorted(parsed["tables"], key=lambda table: table["index"])]}


class ProcessingMixin:
    def _init_processing(self):
        self.processing_pool = ThreadPoolExecutor(max_workers=4, thread_name_prefix="pi-document-tool")
        self.processing_lock = threading.RLock()
        self.index_lock = threading.RLock()
        self.processing_flags = {}
        self.processing_documents = {}
        with self.store.connect(write=True) as db:
            db.execute("""CREATE TABLE IF NOT EXISTS prepared_documents(
                document_id TEXT PRIMARY KEY,sha256 TEXT NOT NULL,parser_version TEXT NOT NULL,
                prepared_json TEXT NOT NULL,updated_at TEXT NOT NULL)""")
            db.execute("""CREATE TABLE IF NOT EXISTS source_parse_history(
                snapshot_id TEXT PRIMARY KEY,project_id TEXT NOT NULL,document_id TEXT NOT NULL,
                parser_version TEXT NOT NULL,source_json TEXT NOT NULL,created_at TEXT NOT NULL)""")

    def _batch_input_fingerprint(self, batch):
        payload={"parser_version":PARSER_VERSION,"tables":[{
            "table":{key:part["table"].get(key) for key in ("index","page","sheet","bbox","rows","cells","source_rows")},
            "selected_rows":part["rows"]} for part in batch]}
        return hashlib.sha256(json.dumps(payload,ensure_ascii=False,sort_keys=True,separators=(",",":"),allow_nan=False).encode()).hexdigest()

    def register_document(self, project_id, path, original_name):
        """Persist attachment only. No parsing, LLM call, or fact writes."""
        self.store.project(project_id)
        source = self.store.upload_path(path)
        if not isinstance(original_name,str) or Path(original_name).name != original_name or len(original_name)>240:
            raise ValueError("invalid_original_name")
        ext = Path(original_name).suffix.lower()
        if ext not in {".pdf",".xlsx",".xls",".csv",".tsv",".json",".png",".jpg",".jpeg",".webp"}:
            raise ValueError("unsupported_document_type")
        sha = hashlib.sha256(source.read_bytes()).hexdigest()
        with self.ingest_lock:
            with self.store.connect() as db:
                prior = db.execute("SELECT document_id FROM documents WHERE project_id=? AND sha256=? ORDER BY created_at DESC LIMIT 1",(project_id,sha)).fetchone()
            if prior:
                return envelope(self.get_document(project_id,prior[0])["data"] | {"deduplicated":True})
            document_id = uuid.uuid4().hex
            target = self.store.root/"documents"/project_id/(document_id+ext)
            target.parent.mkdir(parents=True,exist_ok=True)
            shutil.copyfile(source,target)
            with self.store.connect(write=True) as db:
                db.execute("INSERT INTO documents(document_id,project_id,original_name,sha256,relative_path,media_type,state,parser_version,created_at) VALUES(?,?,?,?,?,?,?,?,?)",
                           (document_id,project_id,original_name,sha,str(target.relative_to(self.store.root)),mimetypes.guess_type(original_name)[0] or "application/octet-stream","registered",PARSER_VERSION,utcnow()))
        self._write_navigation(project_id)
        return envelope(self.get_document(project_id,document_id)["data"] | {"deduplicated":False},status="accepted")

    def start_document_processing(self, project_id, document_ids, owner_run_id, runtime):
        self.store.project(project_id)
        if not isinstance(document_ids,list) or not 1 <= len(document_ids) <= 40:
            raise ValueError("invalid_document_ids")
        if not isinstance(owner_run_id,str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,150}",owner_run_id):
            raise ValueError("invalid_owner_run_id")
        # This is a Pi-local endpoint, never a separate API-provider configuration.
        if not isinstance(runtime,dict): raise ValueError("pi_runtime_required")
        review_existing_only=runtime.get("review_existing_only",False)
        if not isinstance(review_existing_only,bool):raise ValueError("invalid_review_existing_only")
        if review_existing_only and (runtime.get("force") or not runtime.get("review_metrics")):
            raise ValueError("existing_review_requires_metrics_without_force")
        parsed_url=urlparse(runtime.get("base_url", ""))
        if parsed_url.scheme!="http" or parsed_url.hostname not in {"127.0.0.1","localhost","::1"} or not runtime.get("api_key") or not runtime.get("model"):
            raise ValueError("pi_runtime_bridge_required")
        docs=[self.store.document(project_id,i) for i in dict.fromkeys(document_ids)]
        if any((self._document_profile(project_id,d['document_id']) or {}).get('kind','financial_report')!='financial_report' for d in docs):
            raise ValueError('research_requires_script_ingestion')
        processing_id=uuid.uuid4().hex
        state={"processing_id":processing_id,"owner_run_id":owner_run_id,"project_id":project_id,
               "state":"queued","progress":0,"message":"会话已开始处理附件","documents":[],"fact_count":0,
               "coverage":{"tables_total":0,"tables_completed":0,"batches_total":0,"batches_completed":0},"errors":[],"created_at":utcnow()}
        state["mode"]="existing_source_definition_review" if review_existing_only else "document_processing"
        with self.processing_lock:
            if any(str(self.processing_documents.get((project_id,d["document_id"]),"")).startswith("rematerialize_") for d in docs):raise ValueError("document_maintenance_active")
            for doc in docs:
                shared=self.processing_documents.get((project_id,doc["document_id"]))
                state["documents"].append({"document_id":doc["document_id"],"name":doc["original_name"],"state":"queued","progress":0,"fact_count":0,"shared_processing_id":shared})
                if not shared:self.processing_documents[(project_id,doc["document_id"])]=processing_id
            self.processing_flags[processing_id]=threading.Event()
            self._save_processing(state)
            # Copy bridge credentials into worker memory only; no config persisted in state.
            self.processing_pool.submit(self._processing_worker,project_id,processing_id,dict(runtime))
        return envelope(state,status="accepted")

    def _save_processing(self, state, refresh_attachment_snapshot=False):
        from .attachment_flows import record_processing
        state["updated_at"]=utcnow()
        with self.store.connect(write=True) as db:
            db.execute("INSERT INTO processing_runs VALUES(?,?,?,?,?,?) ON CONFLICT(processing_id) DO UPDATE SET state_json=excluded.state_json,updated_at=excluded.updated_at",
                       (state["processing_id"],state["project_id"],state["owner_run_id"],dumps(state),state["created_at"],state["updated_at"]))
            record_processing(db, state, refresh_snapshot=refresh_attachment_snapshot)

    def get_processing_status(self, project_id, processing_id):
        self.store.project(project_id)
        with self.store.connect() as db:
            row=db.execute("SELECT state_json FROM processing_runs WHERE project_id=? AND processing_id=?",(project_id,processing_id)).fetchone()
        if not row:raise ValueError("processing_not_found_in_project")
        return envelope(json.loads(row[0]))

    def cancel_processing(self, project_id, processing_id):
        state=self.get_processing_status(project_id,processing_id)["data"]
        if state.get('mode')=='script_cleaning' and state['state'] not in TERMINAL:
            for run_id in state.get('jobs',{}):
                self.cancel_analysis(project_id,run_id)
            state.update(state='cancelled',message='脚本清洗已停止；已提交检查点保留')
            self._save_processing(state)
            return envelope(state | {'cancel_requested':True})
        with self.processing_lock:
            flag=self.processing_flags.get(processing_id)
            if flag:flag.set()
        # A shared document's original owner remains untouched.
        return envelope(state | {"cancel_requested":bool(flag)})

    def _review_existing_definitions(self, project_id, processing_id, runtime, state, flag):
        from .existing_review import validate_existing_review
        try:
            verified=validate_existing_review(self,project_id,[d["document_id"] for d in state["documents"]],runtime["review_metrics"])
            if flag.is_set():raise InterruptedError("cancelled")
            state["verified_source_documents"]=verified
            for item in state["documents"]:
                item.update(verified[item["document_id"]],state="ready",progress=1,reused_original_sources=True,
                            normalization={"requests":0,"skipped_materialization":True,"reused_original_sources":True})
            state["fact_count"]=sum(item["fact_count"] for item in state["documents"])
            def progress(message):
                state.update(state="normalizing",message=message)
                self._save_processing(state)
            progress("核验历史来源完成，通过当前 Pi 会话仅复核所选指标定义")
            report=review_definition_project(self,project_id,runtime["review_metrics"],runtime|{"processing_id":processing_id,"owner_run_id":state["owner_run_id"]},progress,flag.is_set)
            state["definition_review"]={key:value for key,value in report.items() if key not in {"source_fingerprints","audits","failed_attempts"}}
            state.update(state="completed" if report["status"]=="reviewed" else "needs_review",progress=1,message="已有来源指标定义复核完成；原解析和期间结果保留")
        except InterruptedError:raise
        except Exception as exc:
            code=str(exc) if isinstance(exc,ValueError) and re.fullmatch(r"[a-z0-9_]+",str(exc)) else type(exc).__name__
            state["definition_review"]={key:value for key,value in getattr(exc,"definition_report",{"status":"failed","error":code}).items()
                                        if key not in {"source_fingerprints","audits","failed_attempts"}}
            state["errors"].append({"code":"existing_definition_review_failed","error":code})
            state.update(state="failed",progress=1,message="已有来源定义复核失败："+code+"。未重新解析或清洗原文。")

    def _processing_worker(self, project_id, processing_id, runtime):
        state=self.get_processing_status(project_id,processing_id)["data"]
        flag=self.processing_flags[processing_id]
        try:
            if runtime.get("review_existing_only"):
                self._review_existing_definitions(project_id,processing_id,runtime,state,flag)
                return
            for ordinal, item in enumerate(state["documents"]):
                if flag.is_set():raise InterruptedError("cancelled")
                document_id=item["document_id"]
                shared=item.get("shared_processing_id")
                reused_shared=False
                while shared:
                    while True:
                        if flag.is_set():raise InterruptedError("cancelled")
                        other=self.get_processing_status(project_id,shared)["data"]
                        shared_doc=next(d for d in other["documents"] if d["document_id"]==document_id)
                        item.update({k:v for k,v in shared_doc.items() if k!="shared_processing_id"})
                        state.update(state="normalizing",message="复用另一会话正在处理的同一资料",progress=(ordinal+item["progress"])/len(state["documents"]))
                        self._save_processing(state)
                        if shared_doc["state"] in TERMINAL or other["state"] in TERMINAL:break
                        flag.wait(.25)
                    if item["state"] in {"ready","needs_review","completed"}:
                        reused_shared=True
                        break
                    # The dependent session can finish with its own bridge if the
                    # original owner stops; stopping A must not terminate B.
                    with self.processing_lock:
                        active=self.processing_documents.get((project_id,document_id))
                        if active and active not in {shared,processing_id}:
                            shared=active;item["shared_processing_id"]=active
                            continue
                        self.processing_documents[(project_id,document_id)]=processing_id
                        item.update(shared_processing_id=None,state="queued",progress=0,resumed_from=shared)
                        item.pop("error",None)
                        self._save_processing(state)
                    shared=None
                if reused_shared:continue
                doc=self.store.document(project_id,document_id)
                committed=completed_document(self,project_id,doc,runtime)
                if committed is not None:
                    item.update(committed)
                    state["fact_count"]=sum(d["fact_count"] for d in state["documents"])
                    state["coverage"]={key:sum(d.get("coverage",{}).get(key,0) for d in state["documents"]) for key in committed["coverage"]}
                    with self.store.connect(write=True) as db:db.execute("UPDATE documents SET state=? WHERE document_id=?",(committed["state"],document_id))
                    self._save_processing(state)
                    continue
                def update(stage, progress, message):
                    item.update(state=stage,progress=progress)
                    state.update(state=stage,message=message,progress=(ordinal+progress)/len(state["documents"]))
                    with self.store.connect(write=True) as db:db.execute("UPDATE documents SET state=? WHERE document_id=?",(stage,document_id))
                    self._save_processing(state)
                try:
                    parsed=self._read_prepared(project_id,doc)
                    if parsed is None:
                        update("parsing",.01,"读取 "+doc["original_name"])
                        options=dict(self.configs.get(project_id,{})); options["embedding"]={"enabled":False}
                        path=self.store.root/doc["relative_path"]
                        parse=self._parse_native_pdf if path.suffix.lower()==".pdf" else parse_document
                        parsed=parse(path,doc["original_name"],lambda p,m:update("parsing",p*.25,m),flag.is_set,options)
                        if flag.is_set():raise InterruptedError("cancelled")
                        self._persist_prepared(project_id,document_id,parsed)
                    batches=table_batches(parsed)
                    candidate_tables={part["table"]["index"] for b in batches for part in b}
                    coverage={"tables_total":len(candidate_tables),"tables_completed":0,"batches_total":len(batches),"batches_completed":0}
                    item["coverage"]=coverage
                    update("normalizing",.25,"通过当前 Pi 会话理解财务表格")
                    completed_tables=set(); completed_chunks={}
                    totals={t:sum(any(p["table"]["index"]==t for p in b) for b in batches) for t in candidate_tables}
                    def commit(batch, facts, issues, detail):
                        if flag.is_set():raise InterruptedError("cancelled")
                        self._commit_semantic_batch(project_id,document_id,processing_id,batch,facts,issues,detail)
                        for part in batch:
                            t=part["table"]["index"];completed_chunks[t]=completed_chunks.get(t,0)+1
                            if completed_chunks[t]>=totals[t]:completed_tables.add(t)
                        coverage.update(batches_completed=coverage["batches_completed"]+1,tables_completed=len(completed_tables))
                        item["fact_count"]=self.get_document(project_id,document_id)["data"]["fact_count"]
                        state["fact_count"]=sum(d["fact_count"] for d in state["documents"])
                        state["coverage"]={k:sum(d.get("coverage",{}).get(k,0) for d in state["documents"]) for k in coverage}
                        self._save_processing(state)
                        self._write_navigation(project_id)
                    def cache_get(key):
                        if runtime.get("force"):return None
                        with self.store.connect() as db:row=db.execute("SELECT result_json FROM normalization_cache WHERE cache_key=?",(key,)).fetchone()
                        return json.loads(row[0]) if row else None
                    def cache_put(key,value):
                        payload={"extractions":value,"extraction_processing_id":processing_id,"schema_hash":SCHEMA_HASH,"model":runtime["model"]}
                        # Explicit reprocessing uses its own new output; shared
                        # cached results retain their original immutable owner.
                        if runtime.get("force"):return payload
                        with self.store.connect(write=True) as db:
                            db.execute("INSERT OR IGNORE INTO normalization_cache VALUES(?,?,?)",(key,dumps(payload),utcnow()))
                            accepted=db.execute("SELECT result_json FROM normalization_cache WHERE cache_key=?",(key,)).fetchone()
                        return json.loads(accepted[0])
                    with self.store.connect() as db:
                        saved_batches={row["batch_key"]:(json.loads(row["result_json"]),row["processing_id"]) for row in db.execute("SELECT batch_key,result_json,processing_id FROM normalization_batches WHERE document_id=?",(document_id,))}
                    def resume_get(batch):
                        coordinates=[(f"{document_id}:t{p['table']['index']}",r) for p in batch for r in p["rows"]]
                        key=hashlib.sha256(dumps(coordinates).encode()).hexdigest()
                        saved=saved_batches.get(key)
                        if not saved:return None
                        detail,origin=saved
                        if detail.get("schema_hash")!=SCHEMA_HASH or detail.get("model")!=runtime["model"] or not isinstance(detail.get("extractions"),list):return None
                        if detail.get("source_input_fingerprint")!=self._batch_input_fingerprint(batch):return None
                        if detail.get("repair_error") or detail.get("request_error") or detail.get("status")=="failed":return None
                        # Revalidate older saved mappings with the current
                        # structural checker; retry only newly discovered gaps.
                        _,current_issues=materialize(detail['extractions'],batch,document_id,runtime['model'])
                        if any(i['reason']=='incomplete_column_override' for i in current_issues):return None
                        return detail|{"extraction_processing_id":detail.get("extraction_processing_id") or origin}
                    def commit_failure(batch,error,detail):
                        self._commit_semantic_batch(project_id,document_id,processing_id,batch,[],[error],detail)
                        item["failed_batches"]=item.get("failed_batches",0)+1
                        self._save_processing(state)
                    model_runtime=runtime | {"processing_id":processing_id,"catalog_loader":lambda:self.get_data_catalog(project_id)["data"]["metrics"]}
                    _, report=normalize_document(parsed,document_id,model_runtime,lambda p,m:update("normalizing",.25+p*.74,m),flag.is_set,cache_get,cache_put,on_batch=commit,resume_get=resume_get,on_failure=commit_failure)
                    item["normalization"]=report
                    item["fact_count"]=self.get_document(project_id,document_id)["data"]["fact_count"]
                    endstate=("partial" if item["fact_count"] else "failed") if report.get("failures") else "needs_review" if report["issues"] or parsed["warnings"] else "ready"
                    if report.get("failures"):
                        state["errors"].append({"document_id":document_id,"code":"model_batches_failed","batches":report["failures"]})
                    warnings=list(parsed["warnings"])
                    if report["issues"]:warnings.append(f"{len(report['issues'])} 处语义映射仍需补充")
                    with self.store.connect(write=True) as db:db.execute("UPDATE documents SET state=?,warnings_json=? WHERE document_id=?",(endstate,dumps(warnings),document_id))
                    item.update(state=endstate,progress=1)
                except InterruptedError:raise
                except Exception as exc:
                    code=str(exc) if isinstance(exc,ValueError) and re.fullmatch(r"[a-z0-9_]+",str(exc)) else type(exc).__name__
                    item.update(state="failed",error=code)
                    state["errors"].append({"document_id":document_id,"code":code})
                    with self.store.connect(write=True) as db:db.execute("UPDATE documents SET state='failed' WHERE document_id=?",(document_id,))
                finally:
                    with self.processing_lock:
                        if self.processing_documents.get((project_id,document_id))==processing_id:self.processing_documents.pop((project_id,document_id),None)
                self._save_processing(state)
            if any(d.get("fact_count",0) for d in state["documents"]) and not flag.is_set():
                try:
                    def catalog_progress(message):
                        state.update(state="normalizing",message=message)
                        self._save_processing(state)
                    state["catalog_review"]=canonicalize_project(self.store,project_id,runtime|{"processing_id":processing_id,"owner_run_id":state["owner_run_id"]},catalog_progress,flag.is_set)
                except InterruptedError:raise
                except Exception as exc:
                    code=str(exc) if isinstance(exc,ValueError) and re.fullmatch(r"[a-z0-9_]+",str(exc)) else type(exc).__name__
                    state["catalog_review"]={"status":"failed","error":code}
                    state["errors"].append({"code":"catalog_review_failed","error":code})
            # Later review consumes the metric identities above. Reviewing an
            # unfinished directory wastes paid work when aliases change on resume.
            catalog_ready=state.get("catalog_review",{}).get("status") in {"reviewed","empty"}
            if any(d.get("fact_count",0) for d in state["documents"]) and catalog_ready and not flag.is_set():
                if runtime.get("review_metrics"):
                    try:
                        def definition_progress(message):
                            state.update(state="normalizing",message=message)
                            self._save_processing(state)
                        definition_report=review_definition_project(self,project_id,runtime["review_metrics"],runtime|{"processing_id":processing_id,"owner_run_id":state["owner_run_id"]},definition_progress,flag.is_set)
                        state["definition_review"]={key:value for key,value in definition_report.items() if key not in {"source_fingerprints","audits","failed_attempts"}}
                    except InterruptedError:raise
                    except Exception as exc:
                        code=str(exc) if isinstance(exc,ValueError) and re.fullmatch(r"[a-z0-9_]+",str(exc)) else type(exc).__name__
                        state["definition_review"]={key:value for key,value in getattr(exc,"definition_report",{"status":"failed","error":code}).items()
                                                    if key not in {"source_fingerprints","audits","failed_attempts"}}
                        state["errors"].append({"code":"definition_review_failed","error":code})
            review_ready=catalog_ready and state.get("definition_review",{}).get("status") not in {"failed","pending"}
            if any(d.get("fact_count",0) for d in state["documents"]) and not review_ready and not flag.is_set():
                state["temporal_review"]={"status":"pending","reason":"prerequisite_review_incomplete"}
            if any(d.get("fact_count",0) for d in state["documents"]) and review_ready and not flag.is_set():
                try:
                    def temporal_progress(message):
                        state.update(state="normalizing",message=message)
                        self._save_processing(state)
                    temporal_report=review_temporal_project(self,project_id,runtime|{"processing_id":processing_id,"owner_run_id":state["owner_run_id"]},temporal_progress,flag.is_set)
                    # Full snapshot keys and raw audit cache references stay in the
                    # persisted review, rather than filling Pi's tool context.
                    state["temporal_review"]={k:v for k,v in temporal_report.items() if k not in {"source_fingerprints","profile_audits","correction_audits","target_source_keys"}}
                except InterruptedError:raise
                except Exception as exc:
                    code=str(exc) if isinstance(exc,ValueError) and re.fullmatch(r"[a-z0-9_]+",str(exc)) else type(exc).__name__
                    state["temporal_review"]={"status":"failed","error":code}
                    state["errors"].append({"code":"temporal_review_failed","error":code})
            state.update(state=("partial" if any(d.get("fact_count",0) for d in state["documents"]) else "failed") if state["errors"] else "needs_review" if any(d["state"]=="needs_review" for d in state["documents"]) or state.get("catalog_review",{}).get("status")=="pending" or state.get("temporal_review",{}).get("status") in {"needs_review","pending"} or state.get("definition_review",{}).get("status")=="needs_review" else "completed",progress=1,
                         message="财报处理完成" if not state["errors"] else "部分资料处理失败，可在当前会话重试",fact_count=sum(d["fact_count"] for d in state["documents"]))
            if state.get("temporal_review",{}).get("reason")=="prerequisite_review_incomplete":
                state["message"]="目录或定义复核尚未完成；已保存检查点，继续时先补齐该阶段"
        except InterruptedError:
            state.update(state="cancelled",message="本会话已停止处理，已提交数据保留")
            for item in state["documents"]:
                if item["state"] not in TERMINAL and not item.get("shared_processing_id"):
                    item["state"]="cancelled"
                    with self.store.connect(write=True) as db:db.execute("UPDATE documents SET state='cancelled' WHERE document_id=?",(item["document_id"],))
        finally:
            self._save_processing(state)
            self._write_navigation(project_id)
            with self.processing_lock:
                self.processing_flags.pop(processing_id,None)
                for item in state["documents"]:
                    key=(project_id,item["document_id"])
                    if self.processing_documents.get(key)==processing_id:self.processing_documents.pop(key,None)

    def _prepared_path(self, project_id, document_id):
        return self.store.root/"indexes"/project_id/(document_id+".json")

    def _parse_native_pdf(self, path, name, progress, cancelled, options):
        events=queue.Queue()
        env={k:v for k,v in os.environ.items() if k in {"PATH","SystemRoot","SYSTEMROOT","WINDIR","TEMP","TMP","PYTHONPATH","NUMBER_OF_PROCESSORS"}}
        env.update(PYTHONIOENCODING="utf-8",PYTHONUNBUFFERED="1",PYMUPDF_SUGGEST_LAYOUT_ANALYZER="0")
        process=subprocess.Popen([sys.executable,"-m","service.parser_worker"],cwd=Path(__file__).resolve().parents[1],stdin=subprocess.PIPE,stdout=subprocess.PIPE,
                                 stderr=subprocess.DEVNULL,text=True,encoding="utf-8",env=env,
                                 creationflags=subprocess.CREATE_NO_WINDOW if os.name=="nt" else 0)
        def read():
            try:
                for line in process.stdout:
                    try:events.put(json.loads(line))
                    except json.JSONDecodeError:continue
            finally:events.put({"type":"closed"})
        reader=threading.Thread(target=read,daemon=True);reader.start()
        try:
            process.stdin.write(dumps({"path":str(path),"name":name,"options":options})+"\n");process.stdin.flush();process.stdin.close()
            while True:
                if cancelled():raise InterruptedError("cancelled")
                try:event=events.get(timeout=.1)
                except queue.Empty:continue
                if event["type"]=="progress":progress(event["progress"],event["message"])
                elif event["type"]=="result":return event["parsed"]
                elif event["type"]=="error":raise ValueError("pdf_parser_"+re.sub(r"[^a-z0-9_]","",event["code"].lower()))
                elif event["type"]=="closed":raise ValueError("pdf_parser_exited_without_result")
        finally:
            if process.poll() is None:process.terminate()
            process.wait(timeout=10)
            reader.join(timeout=2)
            process.stdout.close()

    def _render_source_page(self, original, target, page):
        env={k:v for k,v in os.environ.items() if k in {"PATH","SystemRoot","SYSTEMROOT","WINDIR","TEMP","TMP","PYTHONPATH","NUMBER_OF_PROCESSORS"}}
        env.update(PYTHONIOENCODING="utf-8",PYTHONUNBUFFERED="1",PYMUPDF_SUGGEST_LAYOUT_ANALYZER="0")
        result=subprocess.run([sys.executable,"-m","service.parser_worker"],cwd=Path(__file__).resolve().parents[1],
                              input=dumps({"operation":"render_page","path":str(original),"target":str(target),"page":page})+"\n",
                              stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,text=True,encoding="utf-8",env=env,timeout=45,
                              creationflags=subprocess.CREATE_NO_WINDOW if os.name=="nt" else 0)
        if result.returncode or not target.is_file():raise ValueError("pdf_preview_worker_failed")

    def _read_prepared(self, project_id, doc):
        self.store.document(project_id,doc["document_id"])
        with self.store.connect() as db:
            saved=db.execute("SELECT sha256,parser_version,prepared_json FROM prepared_documents WHERE document_id=?",(doc["document_id"],)).fetchone()
        if saved:
            if saved["sha256"]==doc["sha256"] and saved["parser_version"]==PARSER_VERSION:return json.loads(saved["prepared_json"])
            return None
        path=self._prepared_path(project_id,doc["document_id"])
        if path.exists():
            payload=json.loads(path.read_text(encoding="utf-8"))
            if payload.get("sha256")==doc["sha256"] and payload.get("parser_version")==PARSER_VERSION:return payload["parsed"]
        return None

    def _persist_prepared(self, project_id, document_id, parsed):
        # Serialize first: an invalid parse cannot partially replace live sources.
        serialized=dumps(parsed)
        source_index=_source_index(parsed)
        path=self._prepared_path(project_id,document_id)
        previous_file=path.read_text(encoding="utf-8") if path.exists() else None
        with self.store.connect(write=True) as db:
            doc=db.execute("SELECT * FROM documents WHERE project_id=? AND document_id=?",(project_id,document_id)).fetchone()
            if not doc:raise ValueError("document_not_found_in_project")
            old_tables=[dict(row) for row in db.execute("SELECT * FROM source_tables WHERE document_id=? ORDER BY table_id",(document_id,))]
            old_pages=[dict(row) for row in db.execute("SELECT * FROM pages WHERE document_id=? ORDER BY page",(document_id,))]
            previous=db.execute("SELECT prepared_json,parser_version FROM prepared_documents WHERE document_id=?",(document_id,)).fetchone()
            old_index=_source_index({"pages":old_pages,"tables":[{
                "index":int(row["table_id"].rsplit(":t",1)[1]),"page":row["page"],"sheet":row["sheet"],
                "bbox":json.loads(row["bbox_json"]),"rows":json.loads(row["rows_json"]),"cells":json.loads(row["cells_json"])} for row in old_tables]})
            changed=old_index!=source_index
            if previous:
                previous_parsed=json.loads(previous["prepared_json"])
                # Source IDs and document-wide context may affect semantics even
                # when the visible row strings have not changed.
                changed=changed or any(previous_parsed.get(key)!=parsed.get(key) for key in ("company","report_year"))
                old_ids={table["index"]:table.get("source_rows") for table in previous_parsed["tables"]}
                changed=changed or old_ids!={table["index"]:table.get("source_rows") for table in parsed["tables"]}
            if changed and (old_tables or old_pages):
                snapshot_id="parser_revision_"+uuid.uuid4().hex
                saved_batches=[dict(row) for row in db.execute("SELECT * FROM normalization_batches WHERE document_id=?",(document_id,))]
                snapshot={"document":dict(doc),"prepared":json.loads(previous["prepared_json"]) if previous else None,
                          "prepared_file":previous_file,"pages":old_pages,"source_tables":old_tables,"normalization_batches":saved_batches,
                          "replacement_parser_version":PARSER_VERSION,
                          "research_page_reviews":[dict(r) for r in db.execute('SELECT * FROM research_page_reviews WHERE document_id=?',(document_id,))],
                          "research_record_ids":[r[0] for r in db.execute('SELECT record_id FROM research_records WHERE document_id=? AND is_current=1',(document_id,))]}
                db.execute("INSERT INTO source_parse_history VALUES(?,?,?,?,?,?)",(snapshot_id,project_id,document_id,
                           previous["parser_version"] if previous else doc["parser_version"],dumps(snapshot),utcnow()))
                for record in db.execute("SELECT * FROM facts WHERE document_id=?",(document_id,)).fetchall():
                    db.execute("INSERT INTO fact_history VALUES(?,?,?,?,?,?)",(uuid.uuid4().hex,project_id,document_id,snapshot_id,dumps(dict(record)),utcnow()))
                db.execute("DELETE FROM facts WHERE document_id=?",(document_id,))
                db.execute("DELETE FROM normalization_batches WHERE document_id=?",(document_id,))
                db.execute('UPDATE research_records SET is_current=0 WHERE document_id=?',(document_id,))
                db.execute('DELETE FROM research_page_reviews WHERE document_id=?',(document_id,))
                db.execute('DELETE FROM document_profiles WHERE document_id=?',(document_id,))
            db.execute("DELETE FROM chunks_fts WHERE chunk_id IN (SELECT chunk_id FROM chunks WHERE document_id=?)",(document_id,))
            for table in ("chunks","source_tables","pages"):db.execute(f"DELETE FROM {table} WHERE document_id=?",(document_id,))
            # documents.parser_version belongs to the original registration's
            # unique key. The active parser version lives in prepared_documents;
            # updating that old key can collide with an existing later upload.
            db.execute("UPDATE documents SET company=?,report_year=?,page_count=?,warnings_json=? WHERE document_id=?",(parsed["company"],parsed["report_year"],len(parsed["pages"]),dumps(parsed["warnings"]),document_id))
            for page in parsed["pages"]:
                db.execute("INSERT INTO pages VALUES(?,?,?,?,?,?,?)",(document_id,page["page"],page["text"],page.get("printed_page"),page.get("width"),page.get("height"),int(page.get("ocr",False))))
                segments=page.get("segments") or [{"text":page["text"][s:s+1600]} for s in range(0,len(page["text"]),1400)]
                for segment in segments:
                    if segment["text"].strip():self._insert_chunk(db,project_id,document_id,page["page"],segment["text"],{"document_id":document_id,"page":page["page"],**({"source_id":segment["source_id"]} if segment.get("source_id") else {})})
            for table in parsed["tables"]:
                table_id=f"{document_id}:t{table['index']}"
                db.execute("INSERT INTO source_tables VALUES(?,?,?,?,?,?,?)",(table_id,document_id,table["page"],table.get("sheet"),dumps(table.get("bbox")),dumps(table["rows"]),dumps(table.get("cells",{}))))
                for r,row in enumerate(table["rows"],1):
                    if any(row):
                        ref={"document_id":document_id,"page":table["page"],"table_id":table_id,"row":r}
                        if table.get("sheet"):ref["sheet"]=table["sheet"]
                        if table.get("source_rows") and r<=len(table["source_rows"]):ref["source_id"]=table["source_rows"][r-1]
                        self._insert_chunk(db,project_id,document_id,table["page"]," | ".join(row),ref)
            db.execute("INSERT INTO prepared_documents VALUES(?,?,?,?,?) ON CONFLICT(document_id) DO UPDATE SET sha256=excluded.sha256,parser_version=excluded.parser_version,prepared_json=excluded.prepared_json,updated_at=excluded.updated_at",
                       (document_id,doc["sha256"],PARSER_VERSION,serialized,utcnow()))
            # Rebuilding an identical source index must retain its structured
            # excerpts; a genuinely changed parse was invalidated above.
            for record in db.execute('SELECT record_id,record_json FROM research_records WHERE document_id=? AND is_current=1',(document_id,)).fetchall():
                self._index_research_record(db,project_id,document_id,record[0],json.loads(record[1]))
        # The DB is authoritative and publishes prepared data with its source
        # index atomically. This JSON is a navigable, atomically replaced copy.
        path.parent.mkdir(parents=True,exist_ok=True)
        temporary=path.with_name(path.name+"."+uuid.uuid4().hex+".tmp")
        try:
            temporary.write_text(dumps({"sha256":doc["sha256"],"parser_version":PARSER_VERSION,"parsed":parsed}),encoding="utf-8")
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)
        self._write_navigation(project_id)

    def _commit_semantic_batch(self, project_id, document_id, processing_id, batch, facts, issues, detail):
        coordinates=[(f"{document_id}:t{p['table']['index']}",r) for p in batch for r in p["rows"]]
        key=hashlib.sha256(dumps(coordinates).encode()).hexdigest()
        source_fingerprint=self._batch_input_fingerprint(batch)
        if detail.get("source_input_fingerprint") not in {None,source_fingerprint}:
            raise ValueError("semantic_source_input_changed")
        profile=self._document_profile(project_id,document_id)
        all_facts=facts
        research_facts=[f for f in facts if f['source']['normalization'].get('data_kind','disclosed_actual')!='disclosed_actual']
        if profile and profile['kind']!='financial_report' and len(research_facts)!=len(facts):
            raise ValueError('research_cannot_be_primary_disclosure')
        research_records=[self._research_fact(project_id,document_id,f,profile) for f in research_facts]
        facts=[f for f in facts if f not in research_facts]
        with self.store.connect(write=True) as db:
            current_profile=db.execute('SELECT revision_id FROM document_profiles WHERE project_id=? AND document_id=?',(project_id,document_id)).fetchone()
            if (current_profile[0] if current_profile else None)!=(profile or {}).get('revision_id') or ('profile_revision' in detail and detail['profile_revision']!=(profile or {}).get('revision_id')):
                raise ValueError('document_profile_changed_restart_processing')
            document_sha=db.execute("SELECT sha256 FROM documents WHERE project_id=? AND document_id=?",(project_id,document_id)).fetchone()[0]
            for part in batch:
                table=part["table"]
                stored=db.execute("SELECT page,sheet,bbox_json,rows_json,cells_json FROM source_tables WHERE document_id=? AND table_id=?",
                                  (document_id,f"{document_id}:t{table['index']}")).fetchone()
                if not stored or (stored["page"],stored["sheet"],json.loads(stored["bbox_json"]),json.loads(stored["rows_json"]),json.loads(stored["cells_json"]))!=(table["page"],table.get("sheet"),table.get("bbox"),table["rows"],table.get("cells",{})):
                    raise ValueError("semantic_source_input_changed")
            stamp_source_provenance(document_sha,all_facts,detail)
            overlay_saved_corrections(db,project_id,document_id,facts,detail)
            overlay_saved_definitions(db,project_id,facts)
            for table_id,r in coordinates:
                table_index=int(table_id.rsplit(":t",1)[1])
                row_issues=[issue for issue in issues if issue.get("table")==table_index and (issue.get("row") in {None,r})]
                new_columns={f["source"]["column"] for f in facts if f["source"]["table_id"]==table_id and f["source"]["row"]==r}
                old=db.execute("SELECT * FROM facts WHERE document_id=? AND json_extract(source_json,'$.table_id')=? AND json_extract(source_json,'$.row')=?",(document_id,table_id,r)).fetchall()
                for record in old:
                    previous_ref=json.loads(record["source_json"])
                    if row_issues and previous_ref.get("column") not in new_columns:
                        previous_ref["retained_after_processing"]={"processing_id":processing_id,"issues":row_issues}
                        db.execute("UPDATE facts SET quality='previous_version_unresolved',source_json=? WHERE fact_id=?",(dumps(previous_ref),record["fact_id"]))
                        continue
                    db.execute("INSERT INTO fact_history VALUES(?,?,?,?,?,?)",(uuid.uuid4().hex,project_id,document_id,processing_id,dumps(dict(record)),utcnow()))
                    db.execute("DELETE FROM facts WHERE fact_id=?",(record["fact_id"],))
            for fact in facts:
                fact["source"]["normalization"]["processing_id"]=processing_id
                db.execute("INSERT INTO facts VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",(uuid.uuid4().hex,document_id,project_id,fact["company"],fact["metric"],fact["year"],fact["period"],fact["scope"],fact["currency"],fact["raw_value"],fact["raw_unit"],fact["value"],dumps(fact["source"]),fact["priority"],fact["quality"]))
            for part in batch:
                table_id=f"{document_id}:t{part['table']['index']}"
                # Script commits are complete source tables, so replacing a
                # research batch is atomic with financial writes and checkpoints.
                self._replace_research_batch(db,project_id,document_id,profile,'table:'+str(part['table']['index']),[r for r in research_records if r['source']['table_id']==table_id])
            result={**detail,"status":"failed" if detail.get("request_error") else "needs_review" if issues else "completed","source_input_fingerprint":source_fingerprint,"parser_version":PARSER_VERSION,
                    "coordinates":coordinates,"fact_count":len(facts),"research_record_count":len(research_records),"issues":issues}
            db.execute("INSERT OR REPLACE INTO normalization_batches VALUES(?,?,?,?,?)",(document_id,key,processing_id,dumps(result),utcnow()))
            companies={f["company"] for f in facts if f.get("company")}
            if len(companies)==1:
                db.execute("UPDATE documents SET company=? WHERE document_id=?",(next(iter(companies)),document_id))

    def get_processing_checkpoint(self, project_id, document_id=None, offset=0, limit=20):
        """Reconstruct progress from committed source batches, never a chat summary."""
        documents=[self.store.document(project_id,document_id)] if document_id else self.list_documents(project_id)["data"]["items"]
        limit=max(1,min(int(limit),50));offset=max(0,int(offset));items=[]
        for doc in documents:
            did=doc["document_id"];parsed=self._read_prepared(project_id,doc)
            with self.store.connect() as db:
                saved={r[0]:json.loads(r[1]) for r in db.execute("SELECT batch_key,result_json FROM normalization_batches WHERE document_id=?",(did,))}
            counts={"total":0,"completed":0,"needs_review":0,"failed":0,"pending":0};remaining=[]
            for batch in table_batches(parsed) if parsed else []:
                coords=[(f"{did}:t{p['table']['index']}",r) for p in batch for r in p["rows"]]
                key=hashlib.sha256(dumps(coords).encode()).hexdigest();record=saved.get(key)
                if not record:
                    # Script commits cover a whole source table. Legacy checkpoints
                    # remain row-batched; resolve them to that durable table receipt.
                    table=batch[0]['table'];table_hash=hashlib.sha256(dumps(table).encode()).hexdigest()
                    record=next((r for r in saved.values() if r.get('script_table')==table['index'] and r.get('script_source_hash')==table_hash and r.get('document_sha256')==doc['sha256']),None)
                current=record and record.get("source_input_fingerprint")==self._batch_input_fingerprint(batch)
                if record and record.get('script_version'):current=record.get('script_source_hash')==hashlib.sha256(dumps(batch[0]['table']).encode()).hexdigest() and record.get('document_sha256')==doc['sha256']
                current_issues=materialize(record.get('extractions',[]),batch,did,record.get('model',''))[1] if current else []
                gap=any(i['reason']=='incomplete_column_override' for i in current_issues)
                status=("failed" if record.get("request_error") or record.get("repair_error") or gap else "needs_review" if current_issues or record.get("issues") else "completed") if current else "pending"
                counts["total"]+=1;counts[status]+=1
                if status!="completed":remaining.append({"batch_key":key,"status":status,"table_id":coords[0][0],"rows":batch[0]["rows"],"page":batch[0]["table"]["page"],"issue_count":max(len(current_issues),len(record.get("issues",[]))) if current else 0})
            items.append({"document_id":did,"name":doc["original_name"],"state":doc["state"],"source_sha256":doc["sha256"],"counts":counts,"remaining":remaining[offset:offset+limit],"offset":offset,"limit":limit,"remaining_total":len(remaining),"next_offset":offset+limit if offset+limit<len(remaining) else None})
        return envelope({"documents":items,"resume_tool":"process_documents","resume_arguments":{"document_ids":[d["document_id"] for d in documents],"force":False},"detail_tool":"get_normalization_details","note":"completed表示批次已提交；needs_review表示已提交但有疑点。默认恢复仅重试failed/pending，已提交疑点可按表读取复核。"})

    def _expanded_fact(self, record):
        item=dict(record);ref=json.loads(item.pop("source_json"));meta=ref.get("normalization",{})
        superseded=bool(meta.get("directory_alias_superseded_by_definition") and meta.get("definition_review",{}).get("source_fingerprint")==meta.get("source_fingerprint"))
        return item|{"source_ref":ref,"label":meta.get("label") or METRICS.get(item["metric"],[item["metric"]])[0],"statement":meta.get("statement","notes"),
                     "period_start":meta.get("period_start",""),"period_end":meta.get("period_end",""),"dimensions":meta.get("dimensions",{}),"dimension_labels":meta.get("dimension_labels",{}),"unit_conversion":meta.get("unit_conversion"),
                     "original_metric":meta.get("original_metric",item["metric"]),"canonical_alias":None if superseded else meta.get("canonical_alias"),"previous_canonical_alias":meta.get("canonical_alias") if superseded else None,"temporal_correction":meta.get("temporal_correction"),
                     "definition_review":meta.get("definition_review"),"definition":meta.get("definition_review",{}).get("after",{}).get("definition"),"definition_scope":meta.get("definition_review",{}).get("after",{}).get("definition_scope"),
                     "version":meta.get("restatement","original"),"restatement":meta.get("restatement","original"),"normalization_engine":meta.get("engine","legacy_rules"),
                     "unit_kind":meta.get("unit_kind") or unit_kind(item["currency"]),"numeric_span":meta.get("numeric_span"),
                     "normalized_unit":"%" if item["currency"]=="percent" else "个百分点" if item["currency"]=="percentage_points" else item["currency"] if item["currency"]!="unknown" else item["raw_unit"]}

    def _resolve_metric_aliases(self, project_id, values):
        with self.store.connect() as db:
            if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='metric_aliases'").fetchone():return values
            aliases=dict(db.execute("SELECT source_metric,canonical_metric FROM metric_aliases WHERE project_id=?",(project_id,)).fetchall())
            current={r[0] for r in db.execute("SELECT DISTINCT metric FROM facts WHERE project_id=?",(project_id,))}
        resolved=[]
        for value in values:
            target=aliases.get(value)
            if target and target in current:
                if value in current:resolved.append(value)
                resolved.append(target)
            else:resolved.append(value)
        return list(dict.fromkeys(resolved))

    def rematerialize_documents(self, project_id, document_ids):
        """Host maintenance: replay saved model mappings with zero inference calls."""
        from .maintenance import rematerialize_documents
        return envelope(rematerialize_documents(self,project_id,document_ids))

    def query_financial_data(self, project_id, filters=None, limit=200, offset=0):
        self.store.project(project_id);filters=filters or {}
        if not isinstance(filters,dict):raise ValueError("invalid_filters")
        limit=max(1,min(int(limit),200));offset=max(0,int(offset))
        sql=" FROM current_financial_facts f WHERE f.project_id=?";args=[project_id]
        for singular,plural,column in [("company","companies","company"),("metric","metrics","metric"),("period","periods","period"),("year","years","year"),("scope","scopes","scope"),("currency","currencies","currency"),("document_id","document_ids","document_id"),("quality","qualities","quality")]:
            values=filters.get(plural,filters.get(singular))
            if values==[]:
                sql+=" AND 0";continue
            if values is not None and values!="":
                if not isinstance(values,list):values=[values]
                if len(values)>200:raise ValueError("too_many_filter_values")
                if column=="metric":values=self._resolve_metric_aliases(project_id,values)
                sql+=f" AND f.{column} IN ("+",".join("?" for _ in values)+")";args.extend(values)
        for names,path in [(("statement","statements"),"statement"),(("version","restatement"),"restatement")]:
            values=next((filters[n] for n in names if n in filters),None)
            if values==[]:
                sql+=" AND 0";continue
            if values:
                if not isinstance(values,list):values=[values]
                sql+=f" AND COALESCE(json_extract(f.source_json,'$.normalization.{path}'),?) IN ("+",".join("?" for _ in values)+")"
                args.extend(["notes" if path=="statement" else "original",*values])
        dimensions=filters.get("dimensions",{})
        if not isinstance(dimensions,dict):raise ValueError("invalid_dimensions")
        for key,value in dimensions.items():
            if not re.fullmatch(r"[\w\u4e00-\u9fff]+",key):raise ValueError("invalid_dimension_key")
            sql+=" AND json_extract(f.source_json,?)=?";args.extend(["$.normalization.dimensions."+key,value])
        with self.store.connect() as db:
            total=db.execute("SELECT count(*)"+sql,args).fetchone()[0]
            records=db.execute("SELECT f.*"+sql+" ORDER BY company,metric,period,f.priority DESC,f.rowid LIMIT ? OFFSET ?",args+[limit,offset]).fetchall()
        items=[self._expanded_fact(r) for r in records]
        return envelope({"items":items,"total":total,"limit":limit,"offset":offset},[f["source_ref"] for f in items])

    def get_data_catalog(self, project_id, query=None, statement=None, offset=0, limit=None, document_id=None, company=None):
        self.store.project(project_id)
        documents=self.list_documents(project_id)["data"]["items"]
        where='project_id=?';args=[project_id]
        if document_id:
            self.store.document(project_id,document_id)
            where+=' AND document_id=?';args.append(document_id)
            documents=[d for d in documents if d['document_id']==document_id]
        if company:where+=' AND company=?';args.append(company)
        with self.store.connect() as db:
            metrics=[dict(r) for r in db.execute("SELECT metric,COALESCE(json_extract(source_json,'$.normalization.label'),metric) label,COALESCE(json_extract(source_json,'$.normalization.statement'),'notes') statement,count(*) count FROM current_financial_facts WHERE "+where+" GROUP BY metric,label,statement ORDER BY statement,metric",args)]
            for metric in metrics:
                if metric["label"]==metric["metric"] and metric["metric"] in METRICS:metric["label"]=METRICS[metric["metric"]][0]
            if query:
                terms=str(query).casefold().split()
                metrics=[m for m in metrics if any(t in (m["metric"]+" "+m["label"]).casefold() for t in terms)]
            if statement:metrics=[m for m in metrics if m["statement"]==statement]
            total_metrics=len(metrics);offset=max(0,int(offset))
            if limit is not None:limit=max(1,min(int(limit),80));metrics=metrics[offset:offset+limit]
            selected_metrics={m["metric"] for m in metrics}
            counts={"documents":len(documents),"facts":db.execute("SELECT count(*) FROM current_financial_facts WHERE "+where,args).fetchone()[0]}
            research_sql=" FROM research_records r LEFT JOIN document_profiles p USING(document_id) WHERE r.project_id=? AND r.is_current=1 AND (r.profile_revision IS NULL OR r.profile_revision=p.revision_id)"
            research_args=[project_id]
            if document_id:research_sql+=' AND r.document_id=?';research_args.append(document_id)
            if company:research_sql+=" AND json_extract(r.record_json,'$.entity.name')=?";research_args.append(company)
            counts['research_records']=db.execute('SELECT count(*)'+research_sql,research_args).fetchone()[0]
            research_metrics=[dict(r) for r in db.execute('SELECT r.metric,r.data_kind,count(*) count'+research_sql+' AND r.metric IS NOT NULL GROUP BY r.metric,r.data_kind ORDER BY r.metric,r.data_kind',research_args)]
            if query:research_metrics=[m for m in research_metrics if any(t in (m['metric']+' '+m['data_kind']).casefold() for t in str(query).casefold().split())]
            research_total=len(research_metrics)
            if limit is not None:research_metrics=research_metrics[offset:offset+limit]
            counts["pages"]=sum(d["page_count"] or 0 for d in documents);counts["tables"]=sum(d["table_count"] for d in documents)
            distinct={plural:[r[0] for r in db.execute(f"SELECT DISTINCT {column} FROM current_financial_facts WHERE "+where+f" ORDER BY {column}",args)] for plural,column in [("companies","company"),("periods","period"),("scopes","scope"),("currencies","currency")]}
            metric_aliases=[]
            if db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='metric_aliases'").fetchone():
                for record in db.execute("SELECT source_metric,canonical_metric,canonical_label,review_hash,evidence_json FROM metric_aliases WHERE project_id=? ORDER BY source_metric",(project_id,)):
                    alias=dict(record)
                    if (limit is not None or document_id or company) and alias["source_metric"] not in selected_metrics and alias["canonical_metric"] not in selected_metrics:continue
                    alias["evidence"]=json.loads(alias.pop("evidence_json"));metric_aliases.append(alias)
            distinct["metric_aliases"]=metric_aliases
            dimensions={};dimension_labels={};versions=set()
            for record in db.execute("SELECT metric,source_json FROM current_financial_facts WHERE "+where,args):
                if limit is not None and record[0] not in selected_metrics:continue
                meta=json.loads(record[1]).get("normalization",{});versions.add(meta.get("restatement","original"))
                for key,value in meta.get("dimensions",{}).items():dimensions.setdefault(key,set()).add(str(value))
                for key,label in meta.get("dimension_labels",{}).items():
                    value=meta.get("dimensions",{}).get(key)
                    if value is not None:dimension_labels.setdefault(key,{})[str(value)]=label
            distinct.update(versions=sorted(versions),dimensions={k:sorted(v) for k,v in dimensions.items()},dimension_labels=dimension_labels)
            runs=[json.loads(r[0]) for r in db.execute("SELECT state_json FROM processing_runs WHERE project_id=? ORDER BY created_at DESC LIMIT 20",(project_id,))]
        return envelope({"project_id":project_id,"database_path":str(self.store.path),"documents_path":str(self.store.root/"documents"/project_id),
                         "index_path":str(self.store.root/"indexes"/project_id/"catalog.yaml"),"documents":documents,"metrics":metrics,"counts":counts,
                         "research_catalog":{"metrics":research_metrics,"total_metrics":research_total,"offset":offset,"next_offset":offset+len(research_metrics) if offset+len(research_metrics)<research_total else None,"query_tool":"query_research_records"},
                         "pagination":{"total":total_metrics,"offset":offset,"limit":limit,"next_offset":offset+len(metrics) if offset+len(metrics)<total_metrics else None,"query":query,"statement":statement,"document_id":document_id,"company":company},"dimensions_scope":"current_metric_page" if limit is not None else "project",
                         "statements":[{"id":k,"label":v} for k,v in STATEMENTS.items()],"indexing":"hybrid_rrf" if self.configs.get(project_id,{}).get("embedding",{}).get("enabled") else "keyword+yaml","embedding_enabled":bool(self.configs.get(project_id,{}).get("embedding",{}).get("enabled")),"processing":runs,"catalog_review":directory_status(self.store,project_id),"temporal_review":temporal_review_status(self.store,project_id),"definition_review":definition_status(self.store,project_id),**distinct})

    def get_dashboard(self, project_id):
        catalog=self.get_data_catalog(project_id)["data"]
        result=self.query_financial_data(project_id,limit=200)["data"]
        return envelope({"documents":catalog["documents"],"facts":result["items"],"catalog":catalog,"total":result["total"],"limit":result["limit"],"offset":result["offset"],"truncated":result["total"]>len(result["items"])})

    def get_normalization_details(self, project_id, document_id, table_id=None, limit=20, offset=0, review_only=False, query=None):
        if review_only:
            from .evidence_review import review_details
            return envelope(review_details(self.store,project_id,document_id,query,offset,limit,table_id))
        doc=self.get_document(project_id,document_id)["data"]
        limit=max(1,min(int(limit),20));offset=max(0,int(offset))
        with self.store.connect() as db:
            where=" WHERE document_id=?";args=[document_id]
            if table_id:
                if not db.execute("SELECT 1 FROM source_tables WHERE document_id=? AND table_id=?",(document_id,table_id)).fetchone():raise ValueError("table_not_found_in_document")
                where+=" AND EXISTS(SELECT 1 FROM json_each(result_json,'$.coordinates') WHERE json_extract(value,'$[0]')=?)";args.append(table_id)
            total=db.execute("SELECT count(*) FROM normalization_batches"+where,args).fetchone()[0]
            summary=dict(db.execute("SELECT count(*) batch_count,COALESCE(sum(json_extract(result_json,'$.fact_count')),0) fact_count,COALESCE(sum(json_array_length(result_json,'$.issues')),0) issue_count FROM normalization_batches WHERE document_id=?",(document_id,)).fetchone())
            batches=[dict(r) for r in db.execute("SELECT batch_key,processing_id,result_json,created_at FROM normalization_batches"+where+" ORDER BY created_at LIMIT ? OFFSET ?",args+[limit,offset])]
            versions=db.execute("SELECT count(*) FROM fact_history WHERE document_id=?",(document_id,)).fetchone()[0]
        for b in batches:b["result"]=json.loads(b.pop("result_json"))
        return envelope({"document":doc,"batches":batches,"total":total,"limit":limit,"offset":offset,"summary":summary,"archived_fact_count":versions,"engine":doc.get('normalization_engine','unprocessed'),"version":VERSION})

    def get_document_index(self, project_id, document_id, section="overview", query=None,
                           offset=0, limit=40, page_start=None, page_end=None, include_preview=False):
        """Page through navigation without projecting the complete catalog into a turn."""
        import yaml
        doc=self.store.document(project_id,document_id)
        if section not in {"overview","pages","tables"}:raise ValueError("invalid_document_index_section")
        if query is not None and not isinstance(query,str):raise ValueError("invalid_document_index_query")
        if not isinstance(include_preview,bool):raise ValueError("invalid_document_index_preview")
        for page in (page_start,page_end):
            if page is not None and (not isinstance(page,int) or isinstance(page,bool) or page<1):raise ValueError("invalid_page_range")
        if page_start is not None and page_end is not None and page_start>page_end:raise ValueError("invalid_page_range")
        limit=max(1,min(int(limit),100));offset=max(0,int(offset))
        path=self.store.root/"indexes"/project_id/"catalog.yaml"
        if not path.exists():self._write_navigation(project_id)
        catalog=yaml.safe_load(path.read_text(encoding="utf-8"))
        document=next((d for d in catalog["documents"] if d["document_id"]==document_id),None)
        if document is None:raise ValueError("document_index_not_found")
        pages=document.get("pages",[]);tables=document.get("tables",[])
        headings={item["page"]:item.get("heading","") for item in pages}
        terms=(query or "").casefold().split()
        def matches(item,kind):
            page=item["page"]
            if page_start is not None and page<page_start:return False
            if page_end is not None and page>page_end:return False
            fields=[item.get("heading","")] if kind=="pages" else [item.get("table_id",""),item.get("sheet") or "",headings.get(page,""),json.dumps(item.get("preview",[]),ensure_ascii=False)]
            text=" ".join(" ".join(str(value).split()) for value in fields).casefold()
            return all(term in text for term in terms)
        navigation={"document_id":document_id};pagination={}
        for kind,items in (("pages",pages),("tables",tables)):
            if section not in {"overview",kind}:continue
            matched=[item for item in items if matches(item,kind)]
            window=matched[offset:offset+limit]
            if kind=="pages":
                navigation[kind]=[{"page":item["page"],"heading":item.get("heading","")} for item in window]
            else:
                navigation[kind]=[{"table_id":item["table_id"],"page":item["page"],
                                   **({"sheet":item["sheet"]} if item.get("sheet") else {}),
                                   **({"preview":item.get("preview",[])} if include_preview else {})} for item in window]
            has_more=offset+len(window)<len(matched)
            pagination[kind]={"total":len(matched),"returned":len(window),"offset":offset,"limit":limit,
                              "has_more":has_more,"next_offset":offset+len(window) if has_more else None}
        return envelope({"document_id":document_id,"index_path":str(path),
                         "original_path":str(self.store.root/doc["relative_path"]),"section":section,
                         "query":query,"page_start":page_start,"page_end":page_end,"include_preview":include_preview,
                         "totals":{"pages":len(pages),"tables":len(tables)},"pagination":pagination,
                         "index_yaml":yaml.safe_dump(navigation,allow_unicode=True,sort_keys=False)})

    def _write_navigation(self, project_id):
        import yaml
        with self.index_lock:
            catalog=self.get_data_catalog(project_id)["data"]
            navigation={k:v for k,v in catalog.items() if k!="processing"}
            for doc in navigation["documents"]:
                with self.store.connect() as db:
                    pages=db.execute("SELECT page,text FROM pages WHERE document_id=? ORDER BY page",(doc["document_id"],)).fetchall()
                    tables=db.execute("SELECT table_id,page,sheet,rows_json FROM source_tables WHERE document_id=? ORDER BY page,table_id",(doc["document_id"],)).fetchall()
                doc["original_path"]=str(self.store.root/doc["relative_path"])
                doc["text_index_path"]=str(self._prepared_path(project_id,doc["document_id"]))
                doc["pages"]=[{"page":p["page"],"heading":" / ".join(p["text"].strip().splitlines()[:3])[:180]} for p in pages]
                doc["tables"]=[{"table_id":t["table_id"],"page":t["page"],"sheet":t["sheet"],"preview":json.loads(t["rows_json"])[:2]} for t in tables]
            path=self.store.root/"indexes"/project_id/"catalog.yaml";path.parent.mkdir(parents=True,exist_ok=True)
            temporary=path.with_suffix(".tmp")
            temporary.write_text(yaml.safe_dump(navigation,allow_unicode=True,sort_keys=False),encoding="utf-8")
            temporary.replace(path)
