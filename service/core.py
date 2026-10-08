from __future__ import annotations
import hashlib
import json
import math
import mimetypes
import os
import re
import shutil
import threading
import time
import uuid
from contextvars import copy_context
from .evaluation_isolation import isolation_key, visible
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal, localcontext
from pathlib import Path
from urllib.parse import urlparse

from .normalization import METRICS, decimal_value, metric_id, number_text, tokens
from .parser import PARSER_VERSION, extract_facts, parse_document
from .store import Store, dumps, utcnow
from .snapshots import write_input
from .processing import ProcessingMixin
from .script_cleaning import ScriptCleaningMixin
from .research_ingestion import ResearchIngestionMixin
from .asset_dashboard import AssetDashboardMixin
from .analysis_edits import AnalysisEditError, apply_edits

def response(data=None, source_refs=None, warnings=None, status="ok"):
    return {"status":status,"data":data if data is not None else {},"source_refs":source_refs or [],
            "warnings":warnings or [],"trace_id":uuid.uuid4().hex}

def safe_api_url(url):
    parsed = urlparse(url)
    if parsed.username or parsed.password or not parsed.hostname or parsed.query or parsed.fragment:
        raise ValueError("invalid_api_url")
    if parsed.scheme != "https" and not (parsed.scheme == "http" and parsed.hostname in {"localhost","127.0.0.1","::1"}):
        raise ValueError("api_requires_https_or_loopback")
    return url.rstrip("/")

class FinanceService(AssetDashboardMixin, ResearchIngestionMixin, ScriptCleaningMixin, ProcessingMixin):
    def __init__(self, data_dir):
        self.store = Store(data_dir)
        self.configs = {}  # Secrets stay in memory; app host restores encrypted configuration.
        self.config_lock = threading.Lock()
        self.pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="document-parser")
        self.analysis_pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="analysis")
        self.embedding_pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="embedding-index")
        self.embedding_lock = threading.RLock()
        self.embedding_jobs = {}
        self.embedding_states = {}
        self.analysis_flags = {}
        self.analysis_futures = {}
        self.analysis_children = {}
        self.cancel_flags = {}
        self.ingest_lock = threading.Lock()
        self.sandbox = None
        self._init_processing()

    def create_project(self, project_id, name):
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,100}", project_id or ""):
            raise ValueError("invalid_project_id")
        if not isinstance(name,str) or not name.strip() or len(name)>200:
            raise ValueError("invalid_project_name")
        with self.store.connect(write=True) as db:
            db.execute("INSERT INTO projects(project_id,name,created_at) VALUES(?,?,?) ON CONFLICT(project_id) DO UPDATE SET name=excluded.name",
                       (project_id,name,utcnow()))
        return response(self.store.project(project_id))

    def list_projects(self):
        with self.store.connect() as db:
            items = [dict(r) for r in db.execute("SELECT p.*,(SELECT count(*) FROM documents d WHERE d.project_id=p.project_id) document_count FROM projects p ORDER BY created_at")]
        return response({"items":items})

    def _describe_documents(self, project_id, document_id=None):
        """Documents of a project (or one of them) with their table, fact and research counts.

        Each count is one grouped query for the whole listing instead of several queries per document.
        """
        self.store.project(project_id)
        if document_id is None:
            scope,args="document_id IN (SELECT document_id FROM documents WHERE project_id=?)",(project_id,)
        else:
            scope,args="document_id=?",(document_id,)
        with self.store.connect() as db:
            rows=db.execute("SELECT * FROM documents WHERE project_id=?"+(" AND document_id=?" if document_id else "")+" ORDER BY created_at DESC",(project_id,*((document_id,) if document_id else ()))).fetchall()
            tables=dict(db.execute("SELECT document_id,count(*) FROM source_tables WHERE "+scope+" GROUP BY document_id",args).fetchall())
            facts={r[0]:(r[1],r[2]) for r in db.execute("SELECT document_id,count(*),COALESCE(sum(json_extract(source_json,'$.normalization.engine') IN ('LangExtract','PythonScript','DeterministicRules')),0) FROM current_financial_facts WHERE "+scope+" GROUP BY document_id",args)}
            engines={}
            for owner,engine in db.execute("SELECT DISTINCT document_id,json_extract(result_json,'$.engine') FROM normalization_batches WHERE "+scope,args):
                if engine:engines.setdefault(owner,set()).add(engine)
            research=dict(db.execute("SELECT r.document_id,count(*) FROM research_records r LEFT JOIN document_profiles p USING(document_id) WHERE r.project_id=? AND r."+scope+" AND r.is_current=1 AND (r.profile_revision IS NULL OR r.profile_revision=p.revision_id) GROUP BY r.document_id",(project_id,*args)).fetchall())
            profiles={r['document_id']:{**json.loads(r['profile_json']),'revision_id':r['revision_id'],'source_hash':r['source_hash']} for r in db.execute("SELECT * FROM document_profiles WHERE project_id=? AND "+scope,(project_id,*args))}
        documents=[]
        for row in rows:
            doc=dict(row);doc["warnings"]=json.loads(doc.pop("warnings_json"));key=doc["document_id"]
            doc["table_count"]=tables.get(key,0)
            doc["fact_count"],doc["normalized_fact_count"]=facts.get(key,(0,0))
            doc["legacy_fact_count"]=doc["fact_count"]-doc["normalized_fact_count"]
            found=engines.get(key,set())
            doc["normalization_engine"]=next(iter(found)) if len(found)==1 else 'mixed' if found else "legacy_rules" if doc["fact_count"] else "unprocessed"
            doc['research_record_count']=research.get(key,0)
            doc['profile']=profiles.get(key)
            documents.append(doc)
        return documents

    def list_documents(self, project_id):
        return response({"items":self._describe_documents(project_id)})

    def get_document(self, project_id, document_id):
        self.store.document(project_id,document_id)
        doc=self._describe_documents(project_id,document_id)[0]
        return response(doc, warnings=doc["warnings"])

    def configure_processing(self, project_id, embedding=None, ocr=None):
        self.store.project(project_id)
        current = dict(self.configs.get(project_id,{}))
        for name, config in (("embedding",embedding),("ocr",ocr)):
            if config is None:
                continue
            if not isinstance(config,dict):
                raise ValueError("config_requires_object")
            allowed = {"enabled","base_url","endpoint","model","api_key","dimensions","mode","max_chunks"}
            if set(config) - allowed:
                raise ValueError("unsupported_config_field")
            clean = dict(config)
            url = clean.get("base_url") or clean.get("endpoint")
            if url:
                clean["base_url"] = safe_api_url(url)
            if name=="embedding" and clean.get("enabled"):
                if not url or not clean.get("model"):
                    raise ValueError("embedding_requires_endpoint_and_model")
                if clean.get("dimensions") is not None and not 1 <= int(clean["dimensions"]) <= 65536:
                    raise ValueError("invalid_embedding_dimensions")
            if name=="ocr" and clean.get("mode","local") not in {"local","disabled","api"}:
                raise ValueError("invalid_ocr_mode")
            current[name] = clean
        with self.config_lock:
            self.configs[project_id] = current
        self._schedule_embedding_index(project_id)
        public = {name:{k:v for k,v in cfg.items() if k!="api_key"} | {"has_api_key":bool(cfg.get("api_key"))} for name,cfg in current.items()}
        return response(public)

    def ingest_document(self, project_id, path, original_name):
        self.store.project(project_id)
        source = self.store.upload_path(path)
        if not isinstance(original_name,str) or Path(original_name).name!=original_name or len(original_name)>240:
            raise ValueError("invalid_original_name")
        ext = Path(original_name).suffix.lower()
        if ext not in {".pdf",".xlsx",".xls",".csv",".tsv",".json",".png",".jpg",".jpeg",".webp"}:
            raise ValueError("unsupported_document_type")
        sha = hashlib.sha256(source.read_bytes()).hexdigest()
        with self.ingest_lock:
            with self.store.connect() as db:
                prior = db.execute("SELECT document_id,state FROM documents WHERE project_id=? AND sha256=? AND parser_version=?",
                                   (project_id,sha,PARSER_VERSION)).fetchone()
                if prior and prior["state"] not in {"failed","cancelled"}:
                    job = db.execute("SELECT * FROM jobs WHERE project_id=? AND document_id=? ORDER BY created_at DESC LIMIT 1",(project_id,prior["document_id"])).fetchone()
                    return response(dict(job) | {"deduplicated":True}, status="accepted" if prior["state"] in {"queued","parsing","validating"} else "ok")
            document_id = prior["document_id"] if prior else uuid.uuid4().hex
            destination = self.store.root/"documents"/project_id/(document_id+ext)
            destination.parent.mkdir(parents=True,exist_ok=True)
            shutil.copyfile(source,destination)
            job_id = uuid.uuid4().hex
            with self.store.connect(write=True) as db:
                if prior:
                    # chunk_id is not indexed in the full-text table: one statement is one pass, one per chunk is a pass each.
                    db.execute("DELETE FROM chunks_fts WHERE chunk_id IN (SELECT chunk_id FROM chunks WHERE document_id=?)",(document_id,))
                    for table in ("facts","chunks","source_tables","pages"):
                        db.execute(f"DELETE FROM {table} WHERE document_id=?",(document_id,))
                    db.execute("UPDATE documents SET state='queued',warnings_json='[]' WHERE document_id=?",(document_id,))
                else:
                    db.execute("""INSERT INTO documents(document_id,project_id,original_name,sha256,relative_path,media_type,
                                state,parser_version,created_at) VALUES(?,?,?,?,?,?,?,?,?)""",
                               (document_id,project_id,original_name,sha,str(destination.relative_to(self.store.root)),
                                mimetypes.guess_type(original_name)[0] or "application/octet-stream","queued",PARSER_VERSION,utcnow()))
                db.execute("INSERT INTO jobs VALUES(?,?,?,?,?,?,?,?,?)",
                           (job_id,project_id,document_id,"queued",0,"等待解析",None,utcnow(),utcnow()))
            self.cancel_flags[job_id] = threading.Event()
            self.pool.submit(self._parse_job,project_id,document_id,job_id,destination,original_name)
        return response({"job_id":job_id,"document_id":document_id,"state":"queued","progress":0},status="accepted")

    def _parse_job(self, project_id, document_id, job_id, path, name):
        try:
            flag = self.cancel_flags[job_id]
            self.store.job_update(job_id,"parsing",0.01,"正在读取原文")
            parsed = parse_document(path,name,
                                    lambda p,m:self.store.job_update(job_id,"parsing",p,m),flag.is_set,
                                    dict(self.configs.get(project_id,{})))
            if flag.is_set():
                raise InterruptedError("cancelled")
            self.store.job_update(job_id,"validating",.9,"正在校验单位、期间与来源")
            facts = extract_facts(parsed,document_id)
            with self.store.connect(write=True) as db:
                db.execute("UPDATE documents SET company=?,report_year=?,page_count=?,warnings_json=? WHERE document_id=?",
                           (parsed["company"],parsed["report_year"],len(parsed["pages"]),dumps(parsed["warnings"]),document_id))
                for page in parsed["pages"]:
                    db.execute("INSERT INTO pages VALUES(?,?,?,?,?,?,?)",(document_id,page["page"],page["text"],page.get("printed_page"),page.get("width"),page.get("height"),int(page.get("ocr",False))))
                    segments = page.get("segments")
                    if segments is None:
                        segments = [{"text":page["text"][start:start+1400],"source_id":None} for start in range(0,len(page["text"]),1200)]
                    for seg in segments:
                        if not seg["text"].strip(): continue
                        ref = {"document_id":document_id,"page":page["page"]}
                        if seg.get("source_id"): ref["source_id"] = seg["source_id"]
                        self._insert_chunk(db,project_id,document_id,page["page"],seg["text"],ref)
                for table in parsed["tables"]:
                    table_id=f"{document_id}:t{table['index']}"
                    db.execute("INSERT INTO source_tables VALUES(?,?,?,?,?,?,?)",
                               (table_id,document_id,table["page"],table.get("sheet"),dumps(table.get("bbox")),dumps(table["rows"]),dumps(table.get("cells",{}))))
                    for row_index,row in enumerate(table["rows"]):
                        if not any(row):continue
                        ref={"document_id":document_id,"page":table["page"],"table_id":table_id,"row":row_index+1}
                        if table.get("sheet"):ref["sheet"]=table["sheet"]
                        if table.get("source_rows"):ref["source_id"]=table["source_rows"][row_index]
                        self._insert_chunk(db,project_id,document_id,table["page"]," | ".join(row),ref)
                for fact in facts:
                    db.execute("INSERT INTO facts VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                               (uuid.uuid4().hex,document_id,project_id,parsed["company"],fact["metric"],fact["year"],fact["period"],fact["scope"],fact["currency"],
                                fact["raw_value"],fact["raw_unit"],fact["value"],dumps(fact["source"]),fact["priority"],fact["quality"]))
            if flag.is_set():
                raise InterruptedError("cancelled")
            state = "needs_review" if parsed["warnings"] or any(f["quality"]=="ocr_review" for f in facts) else "ready"
            self.store.job_update(job_id,state,1,f"已解析 {len(parsed['pages'])} 页、{len(parsed['tables'])} 表、{len(facts)} 条财务候选")
            self._schedule_embedding_index(project_id)
        except InterruptedError:
            self.store.job_update(job_id,"cancelled",0,"任务已取消")
        except Exception as exc:
            # Do not persist arbitrary request objects/URLs that may contain credentials.
            error = str(exc) if isinstance(exc,ValueError) and re.fullmatch("[a-z0-9_]+",str(exc)) else type(exc).__name__
            diagnostics = getattr(exc, "local_ocr_diagnostics", None)
            if diagnostics is not None:
                # This diagnostic is produced only by the local OCR branch, without
                # request configuration or frame locals. Never expose it as model evidence.
                try:
                    folder = self.store.root / "diagnostics"
                    folder.mkdir(exist_ok=True)
                    (folder / ("ingestion-" + job_id + ".json")).write_text(
                        dumps({"job_id": job_id, "document_id": document_id, "project_id": project_id,
                               "parser_version": PARSER_VERSION, "created_at": utcnow(), **diagnostics}), encoding="utf-8")
                except OSError:
                    pass  # Diagnostic I/O must not prevent the actual job becoming failed.
            self.store.job_update(job_id,"failed",0,"解析失败",error)
        finally:
            self.cancel_flags.pop(job_id,None)

    def _insert_chunk(self, db, project_id, document_id, page, text, ref):
        chunk_id=uuid.uuid4().hex
        db.execute("INSERT INTO chunks VALUES(?,?,?,?,?,?,?)",(chunk_id,project_id,document_id,page,ref.get("source_id"),text,dumps(ref)))
        db.execute("INSERT INTO chunks_fts(chunk_id,tokens) VALUES(?,?)",(chunk_id,tokens(text)))

    def get_ingestion_status(self, project_id, job_id):
        self.store.project(project_id)
        with self.store.connect() as db:
            row=db.execute("SELECT * FROM jobs WHERE job_id=? AND project_id=?",(job_id,project_id)).fetchone()
        if not row:raise ValueError("job_not_found_in_project")
        return response(dict(row))

    def cancel_ingestion(self, project_id, job_id):
        state = self.get_ingestion_status(project_id,job_id)["data"]
        if job_id in self.cancel_flags:self.cancel_flags[job_id].set()
        return response(state|{"cancel_requested":job_id in self.cancel_flags})

    def _source_tables(self, project_id, document_id, table_id=None):
        """Complete tables with their per-row source references, in page order."""
        self.store.document(project_id,document_id)
        with self.store.connect() as db:
            if table_id:
                records=db.execute("SELECT * FROM source_tables WHERE document_id=? AND table_id=?",(document_id,table_id)).fetchall()
            else:
                records=db.execute("SELECT * FROM source_tables WHERE document_id=? ORDER BY page,table_id",(document_id,)).fetchall()
            source_records=db.execute("SELECT source_json FROM chunks WHERE project_id=? AND document_id=? AND source_id IS NOT NULL AND source_id!='' ORDER BY rowid",(project_id,document_id)).fetchall()
        if table_id and not records:raise ValueError("table_not_found_in_document")
        row_sources={}
        for source_record in source_records:
            ref=json.loads(source_record["source_json"])
            if ref.get("table_id") and isinstance(ref.get("row"),int):
                row_sources[(ref["table_id"],ref["row"])]=ref
        tables=[]
        for record in records:
            item=dict(record)
            for field in ("bbox","rows","cells"):item[field]=json.loads(item.pop(field+"_json"))
            item["row_source_refs"]=[]
            for row_number in range(1,len(item["rows"])+1):
                ref={"document_id":document_id,"page":item["page"],"table_id":item["table_id"],"row":row_number}
                if item.get("sheet"):ref["sheet"]=item["sheet"]
                item["row_source_refs"].append(row_sources.get((item["table_id"],row_number),ref))
            item["source_rows"]=[ref.get("source_id") for ref in item["row_source_refs"]]
            tables.append(item)
        return tables

    def get_source_table(self, project_id, document_id, table_id=None):
        tables=self._source_tables(project_id,document_id,table_id)
        if not table_id:
            for item in tables:
                item["row_count"]=len(item["rows"])
                item["preview"]=item.pop("rows")[:5]
                item["row_source_refs"]=item["row_source_refs"][:5]
                item["source_rows"]=item["source_rows"][:5]
                item.pop("cells",None)
        refs=[{"document_id":document_id,"page":t["page"],"table_id":t["table_id"]} for t in tables]
        refs.extend(ref for t in tables for ref in t["row_source_refs"] if ref.get("source_id"))
        return response({"items":tables},refs)

    def get_source_page(self, project_id, document_id, page):
        doc=self.store.document(project_id,document_id)
        if not isinstance(page,int) or page<1:raise ValueError("invalid_page")
        with self.store.connect() as db:
            row=db.execute("SELECT * FROM pages WHERE document_id=? AND page=?",(document_id,page)).fetchone()
            chunks=db.execute("SELECT source_id,text,source_json FROM chunks WHERE project_id=? AND document_id=? AND page=? AND source_id IS NOT NULL AND source_id!='' ORDER BY rowid",(project_id,document_id,page)).fetchall()
        if not row:raise ValueError("page_not_found")
        data=dict(row)
        data["segments"]=[{"source_id":chunk["source_id"],"text":chunk["text"],"source_ref":json.loads(chunk["source_json"])} for chunk in chunks]
        original=self.store.root/doc["relative_path"]
        if original.suffix.lower()==".pdf":
            target=self.store.root/"artifacts"/project_id/document_id/f"page-{page}.png"
            target.parent.mkdir(parents=True,exist_ok=True)
            if not target.exists():
                self._render_source_page(original,target,page)
            data["image_relative_path"]=str(target.relative_to(self.store.root))
        elif original.suffix.lower() in {".png",".jpg",".jpeg",".webp"}:
            data["image_relative_path"]=doc["relative_path"]
        return response(data,[{"document_id":document_id,"page":page,"printed_page":data.get("printed_page")},*[s["source_ref"] for s in data["segments"]]])

    def get_financial_metrics(self, project_id, metrics, company=None, years=None, document_id=None, scope=None, offset=0, limit=None):
        self.store.project(project_id)
        if not isinstance(metrics,list) or not 1<=len(metrics)<=30:raise ValueError("invalid_metrics")
        with self.store.connect() as db:
            catalog={r[0] for r in db.execute("SELECT DISTINCT metric FROM current_financial_facts WHERE project_id=?",(project_id,))}
            labels={r[0]:r[1] for r in db.execute("SELECT json_extract(source_json,'$.normalization.label'),metric FROM current_financial_facts WHERE project_id=?",(project_id,))}
        resolved=self._resolve_metric_aliases(project_id,metrics)
        canonical=[m if m in catalog else metric_id(m) or labels.get(m) for m in resolved]
        if None in canonical:raise ValueError("unknown_metric_use_data_catalog")
        if document_id:self.store.document(project_id,document_id)
        query="SELECT f.* FROM current_financial_facts f JOIN documents d USING(document_id) WHERE f.project_id=? AND f.metric IN ("+",".join("?"*len(canonical))+")"
        args=[project_id,*canonical]
        if company:query+=" AND f.company LIKE ?";args.append("%"+company+"%")
        if years:
            if len(years)>30 or any(not isinstance(y,int) or not 1900<=y<=2200 for y in years):raise ValueError("invalid_years")
            query+=" AND f.year IN ("+",".join("?"*len(years))+")";args.extend(years)
        if document_id:query+=" AND f.document_id=?";args.append(document_id)
        if scope:
            if scope not in {"consolidated_CAS","parent_CAS","consolidated_IFRS","parent_IFRS","unspecified"}:raise ValueError("invalid_scope")
            query+=" AND f.scope=?";args.append(scope)
        query+=" ORDER BY f.priority DESC,f.rowid"
        with self.store.connect() as db:records=[dict(r) for r in db.execute(query,args)]
        selected, warnings={},[]
        for record in records:
            record=self._expanded_fact(record)
            ref=record["source_ref"]
            key=(record["company"],record["metric"],record["period"],record["scope"],record["currency"],record["version"],dumps(record["dimensions"]))
            if key in selected:
                selected[key]["alternative_sources"].append(ref)
                if record["priority"]==selected[key]["priority"] and record["value"]!=selected[key]["value"]:
                    selected[key]["quality"]="conflict"
                    selected[key].setdefault("conflicting_values",[]).append(record["value"])
                    warnings.append("conflicting_financial_values_require_review")
                continue
            selected[key]=record|{"alternative_sources":[]}
        items=list(selected.values())
        total=len(items);offset=max(0,int(offset))
        if limit is not None:limit=max(1,min(int(limit),80));items=items[offset:offset+limit]
        return response({"items":items,"total":total,"offset":offset,"limit":limit,"next_offset":offset+len(items) if offset+len(items)<total else None,"available_metrics":sorted(catalog | set(METRICS)) if limit is None else canonical,"catalog_tool":"get_data_catalog"},[r["source_ref"] for r in items],list(dict.fromkeys(warnings)),
                        "ok" if items else "insufficient_evidence")

    def financial_workpaper(self, project_id, kind='statement_analysis', **options):
        from .financial_workpapers import financial_workpaper, report_sources, WorkpaperInputError
        try:
            data = financial_workpaper(self, project_id, kind, **options)
            return response(data, report_sources(data['report']))
        except WorkpaperInputError as exc:
            return response({'error': str(exc)}, status='insufficient_evidence')

    def calculate_financial_metrics(self, project_id, operation, inputs):
        self.store.project(project_id)
        if not isinstance(inputs,dict):raise ValueError("inputs_require_object")
        refs=[];resolved={}
        def num(key, val=None):
            if val is None:val=inputs.get(key)
            if isinstance(val,dict) and ('fact_id' in val or 'record_id' in val):
                from .model_inputs import read_record
                with self.store.connect() as db:
                    row=read_record(db,project_id,val)
                refs.append(json.loads(row["source_json"]))
                resolved[key]={k:row[k] for k in ('fact_id','record_id','value','currency','period','scope','data_kind') if k in row}
                val=row["value"]
            number=decimal_value(val)
            if number is None:raise ValueError("invalid_numeric_input_"+key)
            return number
        with localcontext() as ctx:
            ctx.prec=40
            if operation in {"yoy","percentage_change"}:
                current,previous=num("current"),num("previous")
                if previous==0:return response({"reason_code":"zero_denominator"},warnings=["同比基期为零"],status="insufficient_evidence")
                value=(current-previous)/previous*100;formula="(current - previous) / previous * 100";unit="%"
            elif operation in {"ratio","margin","cash_conversion","debt_ratio"}:
                numerator,denominator=num("numerator"),num("denominator")
                if denominator==0:return response({"reason_code":"zero_denominator"},status="insufficient_evidence")
                multiplier=100 if operation in {"margin","debt_ratio"} else 1
                value=numerator/denominator*multiplier;formula="numerator / denominator"+(" * 100" if multiplier==100 else "");unit="%" if multiplier==100 else "ratio"
            elif operation in {"add","subtract","multiply","divide"}:
                a,b=num("a"),num("b")
                if operation=="divide" and b==0:return response({"reason_code":"zero_denominator"},status="insufficient_evidence")
                value={"add":lambda:a+b,"subtract":lambda:a-b,"multiply":lambda:a*b,"divide":lambda:a/b}[operation]()
                formula=f"a {dict(add='+',subtract='-',multiply='*',divide='/')[operation]} b";unit=inputs.get("unit","number")
            elif operation=="sum":
                if not isinstance(inputs.get("values"),list) or not 1<=len(inputs["values"])<=10000:raise ValueError("invalid_values")
                vals=[num('values.'+str(i),v) for i,v in enumerate(inputs['values'])]
                value=sum(vals,Decimal(0));formula="sum(values)";unit=inputs.get("unit","number")
            else:raise ValueError("unsupported_operation")
        return response({"operation":operation,"value":number_text(value),"unit":unit,"formula":formula,"inputs":inputs,'resolved_inputs':resolved},refs)

    def search_evidence(self, project_id, query, company=None, year=None, limit=8, filters=None, offset=0):
        self.store.project(project_id)
        if not isinstance(query,str) or not query.strip() or len(query)>3000:raise ValueError("invalid_search_query")
        limit=max(1,min(int(limit),30));offset=max(0,int(offset));window=max(100,offset+limit+1)
        terms=list(dict.fromkeys(tokens(query).split()))[:60]
        match=" OR ".join('"'+t.replace('"','""')+'"' for t in terms)
        sql="""SELECT c.*,bm25(chunks_fts) AS rank FROM chunks_fts JOIN chunks c ON c.chunk_id=chunks_fts.chunk_id
                 JOIN documents d ON d.document_id=c.document_id WHERE chunks_fts MATCH ? AND c.project_id=?"""
        args=[match,project_id]
        clauses,filter_args=self._evidence_filters(company,year,filters)
        sql+=clauses+' ORDER BY rank LIMIT ?';args+=[*filter_args,window]
        with self.store.connect() as db:
            rows=[dict(r) for r in db.execute(sql,args)] if match else []
        scores={r["chunk_id"]:1/(60+i) for i,r in enumerate(rows,1)}
        by_id={r["chunk_id"]:r for r in rows}
        warnings=[]
        cfg=self.configs.get(project_id,{}).get("embedding",{})
        retrieval="fts5"
        if cfg.get("enabled"):
            self._schedule_embedding_index(project_id)
            try:
                query_vec=self._embeddings(project_id,[query],cfg)[0]
                with self.store.connect() as db:
                    query2="SELECT c.*,d.company,d.report_year FROM chunks c JOIN documents d USING(document_id) WHERE c.project_id=?"
                    query_args=[project_id]
                    query2+=clauses;query_args+=filter_args
                    candidates=[dict(r) for r in db.execute(query2,query_args)]
                    ranked=[]
                    for row in candidates:
                        key=self._embedding_key(project_id,row["text"],cfg)
                        cached=db.execute("SELECT vector_json FROM embedding_cache WHERE cache_key=? AND project_id=?",(key,project_id)).fetchone()
                        if cached:
                            vec=json.loads(cached[0])
                            if len(vec)==len(query_vec):
                                dot=sum(x*y for x,y in zip(query_vec,vec))
                                denom=math.sqrt(sum(x*x for x in query_vec)*sum(x*x for x in vec))
                                ranked.append((dot/denom if denom else 0,row))
                    for i,(_,row) in enumerate(sorted(ranked,key=lambda x:x[0],reverse=True)[:window],1):
                        scores[row["chunk_id"]]=scores.get(row["chunk_id"],0)+1/(60+i)
                        by_id[row["chunk_id"]]=row
                if ranked:retrieval="hybrid_rrf"
                if len(ranked)<len(candidates):warnings.append(f"embedding_index_partial:{len(ranked)}/{len(candidates)}; automatic_indexing")
            except Exception as exc:
                warnings.append("embedding_unavailable:"+type(exc).__name__)
        items=[]
        for chunk_id in sorted(scores,key=lambda k:(-scores[k],k))[offset:offset+limit]:
            row=by_id[chunk_id]
            ref=json.loads(row["source_json"])
            items.append({"chunk_id":chunk_id,"text":row["text"],"score":scores[chunk_id],"source_ref":ref})
        if filters and filters.get('as_of'):warnings.append('undated_documents_excluded')
        return response({"items":items,"retrieval":retrieval,'offset':offset,'limit':limit,'next_offset':offset+limit if offset+limit<len(scores) else None,"embedding_state":dict(self.embedding_states.get(project_id,{}))},[i["source_ref"] for i in items],warnings,
                        status="ok" if items else "insufficient_evidence")

    def _embedding_key(self, project_id, text, cfg):
        return hashlib.sha256(dumps([project_id,cfg.get("base_url"),cfg.get("model"),cfg.get("dimensions"),text]).encode()).hexdigest()

    def _schedule_embedding_index(self, project_id):
        """Configured upload -> background index -> search. Configuration namespaces never mix."""
        cfg=dict(self.configs.get(project_id,{}).get("embedding",{}))
        if not cfg.get("enabled"):
            return
        generation=self._embedding_key(project_id,"__configuration__",cfg)
        with self.embedding_lock:
            prior=self.embedding_jobs.get((project_id,generation))
            if prior and not prior.done():return
            state=self.embedding_states.get(project_id,{})
            # A failure has a short backoff rather than firing paid API requests on every search.
            if state.get("generation")==generation and state.get("state")=="failed" and time.monotonic()-state.get("_failed_at",0)<30:return
            self.embedding_states[project_id]={"state":"queued","generation":generation,"indexed":0}
            self.embedding_jobs[(project_id,generation)]=self.embedding_pool.submit(self._automatic_embedding_index,project_id,generation,cfg)

    def _automatic_embedding_index(self, project_id, generation, cfg):
        indexed=0
        try:
            while self._embedding_key(project_id,"__configuration__",self.configs.get(project_id,{}).get("embedding",{}))==generation:
                result=self._index_embeddings(project_id,500,cfg)
                indexed+=result["data"]["indexed"]
                remaining=result["data"]["remaining"]
                if self._embedding_key(project_id,"__configuration__",self.configs.get(project_id,{}).get("embedding",{}))!=generation:
                    break
                self.embedding_states[project_id]={"state":"ready" if remaining==0 else "indexing","generation":generation,
                                                   "indexed":indexed,"remaining":remaining,"total_chunks":result["data"]["total_chunks"]}
                if remaining==0:break
        except Exception as exc:
            if self._embedding_key(project_id,"__configuration__",self.configs.get(project_id,{}).get("embedding",{}))==generation:
                self.embedding_states[project_id]={"state":"failed","generation":generation,"indexed":indexed,
                                                   "error":type(exc).__name__,"_failed_at":time.monotonic()}

    def _embeddings(self, project_id, texts, cfg):
        import httpx
        base=cfg.get("base_url") or cfg.get("endpoint")
        endpoint=base if base.endswith("/embeddings") else base.rstrip("/")+"/embeddings"
        headers={"Authorization":"Bearer "+cfg["api_key"]} if cfg.get("api_key") else {}
        body={"model":cfg["model"],"input":texts}
        if cfg.get("dimensions"):body["dimensions"]=int(cfg["dimensions"])
        with httpx.Client(timeout=45,trust_env=False) as client:
            result=client.post(endpoint,headers=headers,json=body)
            result.raise_for_status()
            data=result.json()
        vectors=[r["embedding"] for r in sorted(data["data"],key=lambda r:r["index"])]
        if len(vectors)!=len(texts):raise ValueError("embedding_count_mismatch")
        for vector in vectors:
            if not isinstance(vector,list) or not 1<=len(vector)<=65536 or not all(isinstance(v,(int,float)) and math.isfinite(v) for v in vector):raise ValueError("invalid_embedding_vector")
            if cfg.get("dimensions") and len(vector)!=int(cfg["dimensions"]):raise ValueError("embedding_dimensions_mismatch")
        if len({len(v) for v in vectors}) != 1:raise ValueError("embedding_dimensions_mismatch")
        with self.store.connect(write=True) as db:
            for text,vector in zip(texts,vectors):
                db.execute("INSERT OR REPLACE INTO embedding_cache VALUES(?,?,?,?,?,?)",
                           (self._embedding_key(project_id,text,cfg),project_id,cfg["model"],len(vector),dumps(vector),utcnow()))
        return vectors

    def index_embeddings(self, project_id, max_chunks=500):
        self.store.project(project_id)
        cfg=self.configs.get(project_id,{}).get("embedding",{})
        if not cfg.get("enabled"):return response({"indexed":0},warnings=["embedding_not_configured"],status="insufficient_evidence")
        return self._index_embeddings(project_id,max_chunks,dict(cfg))

    def _index_embeddings(self, project_id, max_chunks, cfg):
        max_chunks=max(1,min(int(max_chunks),5000))
        with self.store.connect() as db:
            active,args=self._evidence_filters()
            rows=db.execute("SELECT c.text FROM chunks c JOIN documents d USING(document_id) WHERE c.project_id=?"+active,[project_id,*args]).fetchall()
            missing=[r[0] for r in rows if not db.execute("SELECT 1 FROM embedding_cache WHERE cache_key=? AND project_id=?",(self._embedding_key(project_id,r[0],cfg),project_id)).fetchone()]
        selected=list(dict.fromkeys(missing))[:max_chunks]
        for i in range(0,len(selected),24):self._embeddings(project_id,selected[i:i+24],cfg)
        return response({"indexed":len(selected),"remaining":max(0,len(set(missing))-len(selected)),"total_chunks":len(rows)})

    def get_app_state(self, project_id, kind, key):
        self._app_args(project_id,kind,key)
        with self.store.connect() as db:
            row=db.execute("SELECT value_json,updated_at FROM app_state WHERE project_id=? AND kind=? AND key=?",(project_id,kind,key)).fetchone()
        return response({"value":json.loads(row[0]) if row else None,"updated_at":row[1] if row else None})

    def put_app_state(self, project_id, kind, key, value):
        self._app_args(project_id,kind,key)
        encoded=dumps(value)
        if len(encoded)>4_000_000:raise ValueError("app_state_too_large")
        with self.store.connect(write=True) as db:
            db.execute("INSERT INTO app_state VALUES(?,?,?,?,?) ON CONFLICT(project_id,kind,key) DO UPDATE SET value_json=excluded.value_json,updated_at=excluded.updated_at",
                       (project_id,kind,key,encoded,utcnow()))
        return response({"key":key,"saved":True})

    def list_app_state(self, project_id, kind):
        self._app_args(project_id,kind,"_")
        with self.store.connect() as db:
            rows=db.execute("SELECT key,value_json,updated_at FROM app_state WHERE project_id=? AND kind=? ORDER BY updated_at DESC",(project_id,kind)).fetchall()
        return response({"items":[{"key":r["key"],"value":json.loads(r["value_json"]),"updated_at":r["updated_at"]} for r in rows]})

    def _app_args(self, project_id, kind, key):
        self.store.project(project_id)
        if kind not in {"conversations","runs","evaluation_budgets"}:raise ValueError("invalid_app_state_kind")
        if not isinstance(key,str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,120}",key):raise ValueError("invalid_app_state_key")

    def _runner(self):
        if self.sandbox is None:
            from sandbox import create_runner
            self.sandbox=create_runner(self.store.root/"analysis",shared_inputs=self.store.root/"exports")
        return self.sandbox

    def run_analysis(self, project_id, code=None, document_ids=None, timeout_seconds=120, raw_only=False, financial_tools=True,
                     model_refs=None, comparisons=None, source_run_id=None, edits=None, report=None, params=None, params_order=None):
        self.store.project(project_id)
        previous=None
        if source_run_id:
            self._analysis_state(project_id,source_run_id)
            from .model_delivery import safe_name
            previous=self.store.root/'exports'/project_id/safe_name(source_run_id)
            if code is None:code=(previous/'analysis.py').read_text(encoding='utf-8')
            metadata=json.loads((previous/'analysis_inputs.json').read_text(encoding='utf-8')) if (previous/'analysis_inputs.json').exists() else {}
            if document_ids is None:document_ids=metadata.get('document_ids')
            if model_refs is None:model_refs=metadata.get('model_refs')
            if comparisons is None:comparisons=metadata.get('comparisons')
            if report is None:report=metadata.get('report')
        if code is None and report is not None:code='pass'
        if edits and not source_run_id:raise ValueError('edits_require_source_run_id')
        code=apply_edits(code,edits)
        parameter_plan=None
        if params is not None:
            if not source_run_id:raise ValueError('params_require_source_run_id')
            if document_ids != metadata.get('document_ids') or (model_refs or {}) != (metadata.get('model_refs') or {}) or (comparisons or {}) != (metadata.get('comparisons') or {}):
                raise ValueError('params 复用 source_run_id 的资料和模型快照；更换资料先建立新的基准运行，再比较参数。')
            from .analysis_parameters import override_parameters
            original_code=code
            code,changes=override_parameters(code,params,params_order)
            parameter_plan={'source_run_id':source_run_id,'original_code':original_code,'params':params,'changes':changes,'order':params_order}
        elif params_order is not None:raise ValueError('params_order_requires_params')
        if not isinstance(raw_only,bool):raise ValueError("invalid_analysis_input_mode")
        if not isinstance(code,str) or not 1<=len(code)<=100000:raise ValueError("invalid_analysis_code")
        if isinstance(timeout_seconds,bool) or not isinstance(timeout_seconds,int) or not 1<=timeout_seconds<=120:
            raise ValueError("analysis_timeout_must_be_1_to_120")
        ids=document_ids or [d["document_id"] for d in self.list_documents(project_id)["data"]["items"]]
        run_id=uuid.uuid4().hex
        export=self.store.root/"exports"/project_id/run_id
        export.mkdir(parents=True,exist_ok=True)
        (export/'analysis_inputs.json').write_text(dumps({'document_ids':ids,'model_refs':model_refs or {},'comparisons':comparisons or {},'source_run_id':source_run_id,'report':report,'params':params,'params_order':params_order}),encoding='utf-8')
        if parameter_plan:
            inputs={}
            for name in ('tables.json','facts.json','pages.json','research_records.json'):
                inputs[name]=write_input(self.store.root/'exports',project_id,export/name,(previous/name).read_bytes())
        else:
            records=[];pages=[]
            for document_id in ids:
                doc=self.store.document(project_id,document_id)
                records.extend(self._source_tables(project_id,document_id))
                prepared=self._read_prepared(project_id,doc)
                if prepared:
                    pages.extend({"document_id":document_id,"sha256":doc["sha256"],"page":page["page"],"text":page["text"],
                                  "width":page.get("width"),"height":page.get("height"),"words":page.get("words",[]),
                                  "ocr":page.get("ocr",False),"ocr_lines":page.get("ocr_lines",[])} for page in prepared["pages"])
                else:
                    with self.store.connect() as db:
                        pages.extend({**dict(row),"sha256":doc["sha256"],"words":[]} for row in db.execute("SELECT document_id,page,text,width,height,ocr FROM pages WHERE document_id=? ORDER BY page",(document_id,)))
            # Project-wide inputs repeat from run to run; identical content is stored once and linked.
            shared=lambda name,value:write_input(self.store.root/"exports",project_id,export/name,dumps(value).encode("utf-8"))
            table_path=shared("tables.json",records)
            facts=[]
            while not raw_only:
                batch=self.query_financial_data(project_id,{"document_ids":ids},limit=10000,offset=len(facts))["data"]
                facts.extend(batch["items"])
                if len(facts)>=batch["total"]:break
            facts_path=shared("facts.json",facts)
            pages_path=shared("pages.json",pages)
            research=[]
            if not raw_only:
                for document_id in ids:
                    start=0
                    while True:
                        found=self.query_research_records(project_id,{'document_id':document_id},start,200)['data']
                        research.extend(found['items'])
                        if found['next_offset'] is None:break
                        start=found['next_offset']
            research_path=shared('research_records.json',research)
            inputs={"tables.json":table_path,"facts.json":facts_path,"pages.json":pages_path,'research_records.json':research_path}
        script=export/'analysis.py';script.write_text(code,encoding='utf-8');inputs['analysis.py']=script
        plot_runtime=export/'plot_runtime.py';shutil.copyfile(Path(__file__).with_name('plot_runtime.py'),plot_runtime);inputs['plot_runtime.py']=plot_runtime
        for name in ('analysis_report.py','model_units.py','analysis_report.md'):
            target=export/name;shutil.copyfile(Path(__file__).with_name(name),target);inputs[name]=target
        if report is not None:
            target=export/'analysis_report.json';target.write_text(dumps(report),encoding='utf-8');inputs['analysis_report.json']=target
        if not raw_only and financial_tools:
            # Trusted, versioned helpers are read-only inputs, never host execution.
            # Keep the generic Pi comparison free of domain-specific templates.
            for name in ("finance_charts.py", "finance_charts.md"):
                target=export/name
                shutil.copyfile(Path(__file__).with_name(name),target)
                inputs[name]=target
            from .model_delivery import select_models,prepare_delivery
            models=select_models(self.store.root,project_id,model_refs or {})
            inputs.update(prepare_delivery(export,models,comparisons or {}))
        if parameter_plan:
            # Parameter changes retain the source data snapshot and use current helpers.
            for name in ('models.json','comparison_requests.json','comparisons.json','model_bundle.zip','finance_model_code.zip'):
                prior=previous/name
                if prior.is_file() and name in inputs:
                    # Fresh exports may be hard links to shared snapshots. Remove only
                    # this new link before replacing it; never write through a snapshot.
                    target=export/name;target.unlink(missing_ok=True)
                    inputs[name]=write_input(self.store.root/'exports',project_id,target,prior.read_bytes())
            for name in ('analysis_tables.py','analysis_comparison.py','scenario_tables.py'):
                target=export/name;shutil.copyfile(Path(__file__).with_name(name),target);inputs[name]=target
        runner=self._runner()
        available=runner.availability()
        if not available.get("available"):
            result={"run_id":run_id,"project_id":project_id,"state":"runner_unavailable","status":"runner_unavailable","availability":available}
            self._save_analysis_state(project_id,run_id,result)
            return response(result,status="error")
        self._save_analysis_state(project_id,run_id,{"run_id":run_id,"project_id":project_id,"status":"queued","artifacts":[]})
        self.analysis_flags[run_id]=threading.Event()
        from .plot_runtime import LAUNCH
        launch=LAUNCH if raw_only or not financial_tools else LAUNCH.replace('setup()\n','setup()\nimport finance_charts\nfinance_charts.configure()\nfrom plot_runtime import deliver_models\ndeliver_models()\n')
        self.analysis_futures[run_id]=self.analysis_pool.submit(copy_context().run,self._analysis_job,runner,project_id,run_id,launch,
                                                              inputs,timeout_seconds,parameter_plan)
        return response({"run_id":run_id,"state":"queued",'source_run_id':source_run_id,
                         'model_refs':model_refs or {},'model_data':'/input/models.json' if model_refs else None,
                         'model_bundle':'model_bundle.zip' if model_refs else None},status="accepted")

    def _save_analysis_state(self, project_id, run_id, state):
        state=dict(state);state["state"]=state.get("status",state.get("state"))
        with self.store.connect(write=True) as db:
            prior=db.execute("SELECT state_json FROM analysis_jobs WHERE run_id=? AND project_id=?",(run_id,project_id)).fetchone()
            saved=json.loads(prior[0]) if prior else None
            if saved is not None and not visible(saved):raise ValueError('analysis_not_found_in_project')
            key=saved.get('isolation_key') if saved is not None else isolation_key.get()
            state.pop('isolation_key',None)
            if key is not None:state['isolation_key']=key
            db.execute("INSERT INTO analysis_jobs VALUES(?,?,?,?,?) ON CONFLICT(run_id) DO UPDATE SET state_json=excluded.state_json,updated_at=excluded.updated_at",
                       (run_id,project_id,dumps(state),utcnow(),utcnow()))
        return state

    def _analysis_state(self, project_id, run_id):
        self.store.project(project_id)
        with self.store.connect() as db:
            row=db.execute("SELECT state_json FROM analysis_jobs WHERE run_id=? AND project_id=?",(run_id,project_id)).fetchone()
        if not row:raise ValueError("analysis_not_found_in_project")
        state=json.loads(row[0])
        if not visible(state):raise ValueError("analysis_not_found_in_project")
        return state

    def _analysis_job(self, runner, project_id, run_id, code, inputs, timeout, parameter_plan=None):
        flag=self.analysis_flags[run_id]
        try:
            if flag.is_set():
                result={"run_id":run_id,"project_id":project_id,"status":"cancelled","artifacts":[]}
            else:
                if parameter_plan:result=self._parameter_analysis(runner,project_id,run_id,code,inputs,timeout,parameter_plan,flag)
                else:result=runner.run(code,inputs,project_id=project_id,run_id=run_id,timeout_seconds=timeout)
        except Exception as exc:
            result={"run_id":run_id,"project_id":project_id,"status":"failed","error":"runner_exception:"+type(exc).__name__+': '+str(exc),"artifacts":[]}
        self._save_analysis_state(project_id,run_id,result)
        self.analysis_flags.pop(run_id,None)
        self.analysis_children.pop(run_id,None)
        return result

    def _parameter_analysis(self, runner, project_id, run_id, launch, inputs, timeout, plan, flag):
        from .analysis_parameters import override_parameters
        from .analysis_tables import collect_tables
        def tables(state):
            paths={item['name']:runner.artifact_path(state['run_id'],item['name'],project_id=project_id)
                for item in state.get('artifacts',[]) if Path(item['name']).suffix.lower() in ('.csv','.json')}
            values=collect_tables(paths)[0]
            if 'scenario_bindings.json' in paths:
                context=json.loads(paths['scenario_bindings.json'].read_text(encoding='utf8'))
                return {name:values[qualified] for name,qualified in context['scenario']['tables'].items()}
            return values
        baseline=self._analysis_state(project_id,plan['source_run_id'])
        if baseline.get('status')!='succeeded':raise ValueError('参数比较需要成功的 source_run_id；原运行失败时先用 edits 修复脚本')
        before=tables(baseline);steps=[];prefix={};step_ids=[];export=inputs['analysis.py'].parent
        for index,name in enumerate((plan['order'] or [])[:-1],1):
            if flag.is_set():return {'run_id':run_id,'project_id':project_id,'status':'cancelled','artifacts':[],'parameter_steps':step_ids}
            prefix[name]=plan['params'][name]
            step_code,_=override_parameters(plan['original_code'],prefix)
            child=uuid.uuid4().hex;self.analysis_children[run_id]=child
            target=export/('parameter_step_'+str(index)+'.py');target.write_text(step_code,encoding='utf8')
            self._save_analysis_state(project_id,run_id,{'run_id':run_id,'project_id':project_id,'status':'running','artifacts':[],
                'parameter_stage':name,'completed_steps':index-1,'total_steps':len(plan['order'])})
            result=runner.run(launch,{**inputs,'analysis.py':target},project_id=project_id,run_id=child,timeout_seconds=timeout)
            self._save_analysis_state(project_id,child,result);step_ids.append({'parameter':name,'run_id':child,'status':result['status']})
            if result['status']!='succeeded':return {'run_id':run_id,'project_id':project_id,'status':'failed','artifacts':[],
                'error':'parameter_step_failed: '+name,'parameter_steps':step_ids,'cause':result.get('error'),'stderr':result.get('stderr')}
            steps.append(tables(result))
        if flag.is_set():return {'run_id':run_id,'project_id':project_id,'status':'cancelled','artifacts':[],'parameter_steps':step_ids}
        comparison=export/'parameter_comparison.json'
        comparison.write_text(dumps({'baseline':before,'steps':steps,'order':plan['order'],'parameters':plan['changes'],'baseline_id':plan['source_run_id'],'scenario_id':run_id}),encoding='utf8')
        self.analysis_children[run_id]=run_id
        return {**runner.run(launch,{**inputs,'parameter_comparison.json':comparison},project_id=project_id,run_id=run_id,timeout_seconds=timeout),
                'parameter_changes':plan['changes'],'parameter_steps':step_ids,'params_order':plan['order'],'input_snapshot_from':plan['source_run_id']}

    def get_analysis_status(self, project_id, run_id):
        saved=self._analysis_state(project_id,run_id)
        if saved.get("status") not in {"queued","running"}:return response(self._analysis_presentation(project_id,run_id,saved))
        try:
            observed=self._runner().status(run_id,project_id=project_id)
        except Exception:
            # A queued worker has not necessarily created its runner manifest yet.
            future=self.analysis_futures.get(run_id)
            if future is not None and not future.done():return response(saved)
            latest=self._analysis_state(project_id,run_id)
            if latest.get("status") not in {"queued","running"}:return response(self._analysis_presentation(project_id,run_id,latest))
            # Reconcile persisted jobs after service restart instead of hanging forever.
            failed=saved|{"status":"failed","error":"runner_state_unavailable_after_restart"}
            return response(self._save_analysis_state(project_id,run_id,failed))
        return response(self._analysis_presentation(project_id,run_id,self._save_analysis_state(project_id,run_id,observed)))

    def cancel_analysis(self, project_id, run_id):
        saved=self._analysis_state(project_id,run_id)
        if saved.get("status") not in {"queued","running"}:return response(saved)
        flag=self.analysis_flags.get(run_id)
        if flag:flag.set()
        future=self.analysis_futures.get(run_id)
        if future and future.cancel():
            return response(self._save_analysis_state(project_id,run_id,saved|{"status":"cancelled"}))
        try:
            observed=self._runner().cancel(self.analysis_children.get(run_id,run_id),project_id=project_id)
            return response(observed)
        except Exception:
            # Cancellation may precede manifest creation; retry until the worker exits or is cancellable.
            if future and not future.done():
                threading.Thread(target=self._cancel_analysis_when_available,args=(project_id,run_id,future),daemon=True).start()
            return response(saved|{"cancel_requested":True})

    def _cancel_analysis_when_available(self, project_id, run_id, future):
        while not future.done():
            try:
                self._runner().cancel(self.analysis_children.get(run_id,run_id),project_id=project_id)
                return
            except Exception:
                time.sleep(.1)

    def _analysis_presentation(self, project_id, run_id, state):
        if state.get('status') != 'succeeded': return state
        from .analysis_tables import collect_tables, table_view
        runner = self._runner()
        paths = {item['name']: runner.artifact_path(run_id, item['name'], project_id=project_id)
                 for item in state.get('artifacts', []) if Path(item['name']).suffix.lower() in ('.csv', '.json')}
        plot_path=paths.pop('plot_diagnostics.json',None)
        plot_diagnostics=json.loads(plot_path.read_text(encoding='utf8')) if plot_path else None
        tables, warnings = collect_tables(paths)
        scenario_context={}
        if 'scenario_bindings.json' in paths:
            context=json.loads(paths['scenario_bindings.json'].read_text(encoding='utf8'))
            tables={context['preferred_table']:tables[context['preferred_table']],**{k:t for k,t in tables.items() if k not in context['unqualified_names']}}
            scenario_context={'scenario_context':context}
        from .analysis_parameters import parameter_inventory
        script=self.store.root/'exports'/project_id/run_id/'analysis.py'
        if not script.is_file():script=runner.root/run_id/'input'/'analysis.py'
        available=parameter_inventory(script.read_text(encoding='utf8')) if script.is_file() else {}
        return {**state, **scenario_context, 'numeric_tables': {k: table_view(t) for k, t in tables.items()}, 'table_warnings': warnings,'available_params':available,
                **({'plot_diagnostics':plot_diagnostics} if plot_diagnostics else {})}

    def render_answer(self, project_id, body, tables, charts=None):
        self.store.project(project_id)
        from .analysis_report import bind_text
        return response({'body':bind_text(body,tables,charts)})

    def get_artifact(self, project_id, run_id, name, rows=None):
        self.store.project(project_id)
        if isolation_key.get() is not None:self._analysis_state(project_id,run_id)
        path=self._runner().artifact_path(run_id,name,project_id=project_id)
        from .analysis_tables import artifact_content
        return response({"name":name,"relative_path":str(path.relative_to(self.store.root)),"sha256":hashlib.sha256(path.read_bytes()).hexdigest(),"size":path.stat().st_size,"mime_type":mimetypes.guess_type(name)[0] or "application/octet-stream", **artifact_content(path, rows)})
