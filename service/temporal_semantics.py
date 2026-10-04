"""Pi-owned temporal review; original extraction batches stay immutable.

Integration points after acceptance:
  * process_documents tail: review_project(service, project_id, runtime, ...)
  * batch commit and zero-inference maintenance: overlay_saved_corrections(...)
No worker, MCP task, model-provider configuration or background service is added.
"""
from __future__ import annotations
import hashlib
import json
import re
import uuid
from datetime import date
from concurrent.futures import ThreadPoolExecutor, as_completed

from service.store import dumps, utcnow
from service.normalization import decimal_value
from .review_cache import accept_result, shared_result, result_hash

VERSION="temporal-transactions-0.4.0"


def digest(value):
    return hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(",", ":")).encode()).hexdigest()


def _extraction_hash(detail, table_index, row):
    markers={f"[[T{table_index}]]",f"[[T{table_index}:R{row}]]"}
    extractions=[e for e in detail.get("extractions",[]) if e.get("text") in markers]
    if not any(e.get("class")=="financial_row" for e in extractions):return None
    return digest({"model":detail.get("model"),"schema_hash":detail.get("schema_hash"),"extractions":extractions})


def _identity(document_sha, ref, meta, original_hash, raw_value):
    original_metric=meta.get("original_metric") or meta.get("column_metric") or meta.get("row_metric") or ""
    key=digest({"document_id":ref["document_id"],"table_id":ref.get("table_id"),"row":ref.get("row"),"column":ref.get("column"),"original_metric":original_metric})
    fingerprint=digest({"document_sha":document_sha,"source_key":key,"original_extraction_hash":original_hash,"raw_value":raw_value})
    return key,fingerprint


def _relative_years(text, report_year, reference="report_year"):
    """Structural grouping only; this function never assigns financial dates."""
    if not isinstance(report_year,int):return str(text)
    return re.sub(r"(?<!\d)(?:19|20|21)\d{2}(?!\d)",lambda m:f"<{reference}{int(m[0])-report_year:+d}>",str(text))


def _period_shape(before, report_year):
    basis=int(before["period"][:4]) if re.match(r"^(?:19|20|21)\d{2}",before["period"]) else report_year
    return {k:_relative_years(before[k],basis,"period_year") for k in ("period","start","end")}


def collect_sources(db,project_id):
    documents={r["document_id"]:dict(r) for r in db.execute("SELECT document_id,sha256,report_year,original_name FROM documents WHERE project_id=?",(project_id,))}
    tables={};pages={};headings={};batch_rows={}
    for row in db.execute("SELECT document_id,result_json,processing_id FROM normalization_batches WHERE document_id IN (SELECT document_id FROM documents WHERE project_id=?)",(project_id,)):
        detail=json.loads(row["result_json"])
        for table_id,index in detail.get("coordinates",[]):batch_rows[(table_id,index)]=(detail,row["processing_id"])
    records=db.execute("SELECT * FROM facts WHERE project_id=? ORDER BY document_id,rowid",(project_id,)).fetchall()
    sources=[];unreviewable=[]
    for record in records:
        ref=json.loads(record["source_json"]);meta=ref.get("normalization",{});doc=documents[record["document_id"]]
        table_id=ref.get("table_id");row=ref.get("row");column=ref.get("column")
        saved=batch_rows.get((table_id,row))
        try:index=int(table_id.rsplit(":t",1)[1])
        except (AttributeError,ValueError,IndexError):index=None
        original_hash=_extraction_hash(saved[0],index,row) if saved and index is not None else None
        if not original_hash or not isinstance(row,int) or not isinstance(column,int):
            unreviewable.append({"fact_id":record["fact_id"],"reason":"original_model_mapping_unavailable"});continue
        if table_id not in tables:
            raw=db.execute("SELECT rows_json,page FROM source_tables WHERE table_id=?",(table_id,)).fetchone()
            tables[table_id]=(json.loads(raw[0]),raw[1]) if raw else ([],None)
        rows,page=tables[table_id]
        if not 1<=row<=len(rows) or not 1<=column<=len(rows[row-1]):
            unreviewable.append({"fact_id":record["fact_id"],"reason":"source_cell_unavailable"});continue
        key,fingerprint=_identity(doc["sha256"],ref,meta,original_hash,record["raw_value"])
        current={"period":record["period"],"start":meta.get("period_start",""),"end":meta.get("period_end","")}
        previous=meta.get("temporal_correction",{})
        before=previous["before"] if previous.get("source_fingerprint")==fingerprint else current
        page_key=(record["document_id"],page)
        if page_key not in pages:
            text=db.execute("SELECT text FROM pages WHERE document_id=? AND page=?",page_key).fetchone()
            preceding=db.execute("SELECT text FROM pages WHERE document_id=? AND page=?",(record["document_id"],(page or 1)-1)).fetchone()
            pages[page_key]=(preceding[0][-1800:] if preceding else "")+"\n"+(text[0][:4000] if text else "")
            headings[page_key]=" / ".join((text[0] if text else "").splitlines()[:4])[:200]
        headers=rows[:min(row-1,6)]
        source={"source_key":key,"source_fingerprint":fingerprint,"fact_id":record["fact_id"],"document_id":record["document_id"],
                "page":page,"table_id":table_id,"row":row,"column":column,"original_extraction_hash":original_hash,
                "extraction_processing_id":saved[0].get("extraction_processing_id") or saved[1],"raw_value":record["raw_value"],
                "metric":record["metric"],"label":meta.get("label",record["metric"]),"statement":meta.get("statement","notes"),
                "unit":record["currency"],"scope":record["scope"],"report_year":doc["report_year"],"document_title":doc["original_name"],
                "row_label":meta.get("row_label") or rows[row-1][0],"column_label":meta.get("column_label") or "",
                "row_data":rows[row-1],"nearby_rows":rows[max(0,row-3):row+2],"table_headers":headers,"table_rows":rows,
                "page_context":pages[page_key],"page_heading":headings[page_key],"before":before,"current":current,**before}
        sources.append(source)
    return sorted(sources,key=lambda s:s["source_key"]),unreviewable


def build_profiles(sources):
    groups={}
    for source in sources:
        column_headers=[str(r[source["column"]-1]).replace("\n"," ") for r in source["table_headers"] if len(r)>=source["column"] and str(r[source["column"]-1]).strip() and decimal_value(r[source["column"]-1]) is None]
        semantics={k:source[k] for k in ("metric","label","statement","unit","scope","row_label","column_label")}
        basis=int(source["period"][:4]) if re.match(r"^(?:19|20|21)\d{2}",source["period"]) else source["report_year"]
        semantics["column_headers"]=list(dict.fromkeys(_relative_years(v,basis,"period_year") for v in column_headers))
        semantics["period_shape"]=_period_shape(source["before"],source["report_year"])
        group_id=digest(semantics)
        group=groups.setdefault(group_id,{"group_id":group_id,**semantics,"member_count":0,"source_keys":[],"examples":[]})
        group["member_count"]+=1;group["source_keys"].append(source["source_key"])
        if not group["examples"]:
            example={k:source[k] for k in ("period","start","end","report_year")}
            example["header_hint"]=" | ".join(dict.fromkeys(str(c).replace("\n"," ") for r in source["table_headers"][:2] for c in r if c))[:120]
            example["heading"]=source["page_heading"][:80]
            group["examples"].append(example)
    return [groups[key] for key in sorted(groups)]


def chunks(items,max_items,max_chars=60000):
    current=[];size=0
    for item in items:
        length=len(dumps(item))
        if current and (len(current)>=max_items or size+length>max_chars):yield current;current=[];size=0
        current.append(item);size+=length
    if current:yield current



def source_chunks(sources,max_items=20,max_chars=60000):
    from .temporal_model import _render
    current=[]
    ordered=sorted(sources,key=lambda s:(s["document_id"],s["page"],s["table_id"],s["row"],s["column"],s["source_key"]))
    for source in ordered:
        candidate=current+[source]
        if current and (len(candidate)>max_items or len(_render(candidate,"corrections"))>max_chars):
            yield current;current=[]
        current.append(source)
    if current:yield current

def _ensure_tables(store):
    with store.connect(write=True) as db:
        db.executescript("""
        CREATE TABLE IF NOT EXISTS temporal_review_cache(cache_key TEXT PRIMARY KEY,result_json TEXT NOT NULL,created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS temporal_project_reviews(review_id TEXT PRIMARY KEY,project_id TEXT NOT NULL,report_json TEXT NOT NULL,created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS temporal_corrections(project_id TEXT NOT NULL,source_key TEXT NOT NULL,source_fingerprint TEXT NOT NULL,
          correction_json TEXT NOT NULL,created_at TEXT NOT NULL,PRIMARY KEY(project_id,source_key));
        """)


def _cache_get(store,key):
    with store.connect() as db:row=db.execute("SELECT result_json FROM temporal_review_cache WHERE cache_key=?",(key,)).fetchone()
    return json.loads(row[0]) if row else None


def _cache_put(store,key,payload):
    with store.connect(write=True) as db:return accept_result(db,"temporal_review_cache",{"cache_key":key},payload)


def _audits_intact(store,report):
    """A historical report cannot inherit another run's overwritten cache entry."""
    for audit in report.get("profile_audits",[])+report.get("correction_audits",[]):
        saved=_cache_get(store,audit["cache_key"])
        if saved is None or saved.get("_review_provenance")!=audit.get("source_provenance"):return False
        if audit.get("result_hash") and result_hash(saved)!=audit["result_hash"]:return False
    return True


def validate_after(correction):
    from .temporal_model import _validate_dates
    after={k:str(correction.get(k) or "") for k in ("period","start","end")}
    error=_validate_dates(after)
    if error:raise ValueError(error)
    return after


def _apply_to_reference(ref,evidence):
    meta=ref.setdefault("normalization",{})
    meta.update(period_start=evidence["after"]["start"],period_end=evidence["after"]["end"],temporal_correction=evidence)



def stamp_source_provenance(document_sha,facts,detail):
    """Stable source identity, independent of fact UUID or executing session."""
    for fact in facts:
        ref=fact["source"];meta=ref.setdefault("normalization",{})
        original_hash=_extraction_hash(detail,int(ref["table_id"].rsplit(":t",1)[1]),ref["row"])
        if not original_hash:continue
        key,fingerprint=_identity(document_sha,ref,meta,original_hash,fact["raw_value"])
        meta.update(original_extraction_hash=original_hash,source_key=key,source_fingerprint=fingerprint)

def overlay_saved_corrections(db,project_id,document_id,facts,detail):
    """Pure replay hook for current commit/maintenance; zero model calls."""
    if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='temporal_corrections'").fetchone():return 0
    doc=db.execute("SELECT sha256 FROM documents WHERE project_id=? AND document_id=?",(project_id,document_id)).fetchone()
    if not doc:return 0
    applied=0
    for fact in facts:
        ref=fact["source"];meta=ref.get("normalization",{});index=int(ref["table_id"].rsplit(":t",1)[1])
        original_hash=_extraction_hash(detail,index,ref["row"])
        key,fingerprint=_identity(doc[0],ref,meta,original_hash,fact["raw_value"])
        stored=db.execute("SELECT source_fingerprint,correction_json FROM temporal_corrections WHERE project_id=? AND source_key=?",(project_id,key)).fetchone()
        if not stored or stored[0]!=fingerprint:continue
        evidence=json.loads(stored[1]);after=validate_after(evidence["after"])
        fact.update(period=after["period"],year=int(after["period"][:4]));_apply_to_reference(ref,evidence);applied+=1
    return applied


def review_project(service,project_id,runtime,progress=lambda message:None,cancelled=lambda:False):
    from .temporal_model import VERSION as MODEL_VERSION, PROFILE_PROMPT_HASH, CORRECTION_PROMPT_HASH, PROFILE_CACHE_HASH, CORRECTION_CACHE_HASH, PROFILE_INFERENCE_CONFIG, CORRECTION_INFERENCE_CONFIG, review_profiles, correct_sources
    from .temporal_repair import select_targets, enrich_sources
    service.store.project(project_id);_ensure_tables(service.store)
    if not runtime.get("processing_id") or not runtime.get("owner_run_id"):raise ValueError("temporal_owner_required")
    with service.store.connect() as db:
        sources,unreviewable=collect_sources(db,project_id)
        reviews=[json.loads(row[0]) for row in db.execute("SELECT report_json FROM temporal_project_reviews WHERE project_id=? ORDER BY created_at DESC",(project_id,))]
    initial={s["source_key"]:s["source_fingerprint"] for s in sources}
    compatible=[r for r in reviews if r.get("model")==runtime["model"] and r.get("profiles_reviewed")==r.get("profiles_total")
                and r.get("source_fingerprints") and all(a.get("prompt_hash")==PROFILE_PROMPT_HASH for a in r.get("profile_audits",[]))
                and (not r.get("profile_cache_hash") or r["profile_cache_hash"]==PROFILE_CACHE_HASH)]
    compatible.sort(key=lambda r:sum(initial.get(k)==v for k,v in r["source_fingerprints"].items()),reverse=True)
    prior=next((r for r in compatible if _audits_intact(service.store,r)),None) if not runtime.get("force") else None
    previous=prior.get("source_fingerprints",{}) if prior else {}
    new_sources=[s for s in sources if previous.get(s["source_key"])!=s["source_fingerprint"]]
    profiles=build_profiles(new_sources);by_key={s["source_key"]:s for s in sources}
    report={"version":VERSION,"model_version":MODEL_VERSION,"model":runtime["model"],"facts_total":len(sources)+len(unreviewable),
            "facts_reviewable":len(sources),"unreviewable":unreviewable,"profiles_total":len(profiles),"profiles_reviewed":0,
            "candidate_groups":0,"sources_targeted":0,"facts_updated":0,"model_requests":0,"cache_hits":0,"unresolved":[],"stale_sources":[],"profile_audits":[],"correction_audits":[]}
    targets=[];previous_targets=set()
    if prior:
        # Metric-definition corrections do not invalidate original source identity.
        # Carry original audit owners, and review only unfinished or changed cells.
        report.update(prior_review_id=prior["review_id"],reused_profile_review=True,
                      profiles_total=prior["profiles_total"]+len(profiles),profiles_reviewed=prior["profiles_reviewed"],
                      candidate_groups=prior.get("candidate_groups",0),
                      profile_audits=list(prior.get("profile_audits",[])),correction_audits=list(prior.get("correction_audits",[])))
        unfinished=select_targets(sources,prior)
        targets=[s for s in unfinished if previous.get(s["source_key"])==s["source_fingerprint"]]
        previous_targets=set(prior.get("target_source_keys",[]))
        if not previous_targets:
            for audit in prior.get("correction_audits",[]):
                saved=_cache_get(service.store,audit["cache_key"]) or {}
                previous_targets.update(item["source_key"] for field in ("corrections","unresolved") for item in saved.get(field,[]))
        report["cache_hits"]=len(report["profile_audits"])+len(report["correction_audits"])
    candidate_ids=set()
    model_profiles=[{k:v for k,v in profile.items() if k!="source_keys"} for profile in profiles]
    report["profile_input_characters"]=sum(len(dumps(p)) for p in model_profiles)
    def audit_chunk(part):
        if cancelled():raise InterruptedError("cancelled")
        key=digest({"phase":"profiles","configuration":PROFILE_CACHE_HASH,"model":runtime["model"],"input":part})
        def compute():
            result=review_profiles(part,runtime,progress,cancelled)
            result["_review_provenance"]={"processing_id":runtime.get("processing_id"),"owner_run_id":runtime.get("owner_run_id")}
            return result,result.get("requests",0)
        def validate(result):
            ids={p["group_id"] for p in part};flagged=[c["group_id"] for c in result["candidates"]]
            if result["reviewed_count"]!=len(part) or len(set(flagged))!=len(flagged) or not set(flagged)<=ids:raise ValueError("temporal_profile_coverage_invalid")
        result,cached,requests=shared_result(service.store,"temporal_review_cache",{"cache_key":key},compute,cancelled,validate)
        flagged=[c["group_id"] for c in result["candidates"]]
        return len(part),flagged,requests,int(cached),{"cache_key":key,"result_hash":result_hash(result),"reviewed_count":len(part),"source_provenance":result.get("_review_provenance"),"prompt_hash":PROFILE_PROMPT_HASH,"inference_config":PROFILE_INFERENCE_CONFIG}
    profile_chunks=list(chunks(model_profiles,100));report["profile_chunks"]=len(profile_chunks);report["profile_groups_this_run"]=len(profiles)
    with ThreadPoolExecutor(max_workers=3,thread_name_prefix="pi-temporal-review") as pool:
        for reviewed,flagged,requests,cached,audit in pool.map(audit_chunk,profile_chunks):
            report["profiles_reviewed"]+=reviewed;candidate_ids.update(flagged)
            report["model_requests"]+=requests;report["cache_hits"]+=cached;report["profile_audits"].append(audit)
    for profile in profiles:
        if profile["group_id"] in candidate_ids:targets.extend(by_key[k] for k in profile["source_keys"])
    target_keys=previous_targets|{s["source_key"] for s in targets}
    report.update(candidate_groups=report["candidate_groups"]+len(candidate_ids),sources_targeted=len(target_keys),
                  sources_targeted_this_run=len(targets),target_source_keys=sorted(target_keys),profile_cache_hash=PROFILE_CACHE_HASH)
    if prior and targets:
        with service.store.connect() as db:targets=enrich_sources(db,project_id,targets)
    correction_chunks=list(source_chunks(targets));report["correction_chunks"]=len(correction_chunks)
    def infer_correction(part):
        if cancelled():raise InterruptedError("cancelled")
        key=digest({"phase":"corrections","configuration":CORRECTION_CACHE_HASH,"model":runtime["model"],"input":[{k:v for k,v in s.items() if k not in {"fact_id","current","extraction_processing_id"}} for s in part]})
        def compute():
            result=correct_sources(part,runtime,progress,cancelled)
            result["_review_provenance"]={"processing_id":runtime.get("processing_id"),"owner_run_id":runtime.get("owner_run_id")}
            return result,result.get("requests",0)
        def validate(result):
            ids={s["source_key"] for s in part};answered=[c["source_key"] for c in result["corrections"]]+[c["source_key"] for c in result["unresolved"]]
            if len(answered)!=len(set(answered)) or set(answered)!=ids:raise ValueError("temporal_correction_coverage_invalid")
            for correction in result["corrections"]:validate_after(correction)
        result,cached,requests=shared_result(service.store,"temporal_review_cache",{"cache_key":key},compute,cancelled,validate)
        return part,key,result,cached,requests
    def completed_corrections():
        with ThreadPoolExecutor(max_workers=3,thread_name_prefix="pi-temporal-correction") as pool:
            futures=[pool.submit(infer_correction,part) for part in correction_chunks]
            try:
                for future in as_completed(futures):yield future.result()
            finally:
                for future in futures:future.cancel()
    for part,key,result,cached,requests in completed_corrections():
        if cancelled():raise InterruptedError("cancelled")
        report["model_requests"]+=requests
        ids={s["source_key"] for s in part};answered=[c["source_key"] for c in result["corrections"]]+[c["source_key"] for c in result["unresolved"]]
        if len(answered)!=len(set(answered)) or set(answered)!=ids:raise ValueError("temporal_correction_coverage_invalid")
        for correction in result["corrections"]:validate_after(correction)
        report["cache_hits"]+=int(cached)
        report["correction_audits"].append({"cache_key":key,"result_hash":result_hash(result),"source_count":len(part),"source_keys":sorted(ids),"source_provenance":result.get("_review_provenance"),"prompt_hash":CORRECTION_PROMPT_HASH,"inference_config":CORRECTION_INFERENCE_CONFIG})
        report["unresolved"].extend(result["unresolved"])
        with service.store.connect(write=True) as db:
            current,_=collect_sources(db,project_id);now={s["source_key"]:s for s in current}
            for correction in result["corrections"]:
                source=by_key[correction["source_key"]];latest=now.get(source["source_key"])
                if not latest or latest["source_fingerprint"]!=source["source_fingerprint"]:
                    report["stale_sources"].append(source["source_key"]);continue
                after=validate_after(correction)
                if latest["current"]!=source["current"] and latest["current"]!=after:
                    report["stale_sources"].append(source["source_key"]);continue
                evidence={"status":"reviewed","engine":"LangExtract","version":MODEL_VERSION,"model":runtime["model"],"prompt_hash":CORRECTION_PROMPT_HASH,"inference_config":CORRECTION_INFERENCE_CONFIG,
                          "cache_key":key,"result_hash":result_hash(result),
                          "extraction_processing_id":result.get("_review_provenance",{}).get("processing_id"),"owner_run_id":result.get("_review_provenance",{}).get("owner_run_id"),"source_key":source["source_key"],
                          "source_fingerprint":source["source_fingerprint"],"original_extraction_hash":source["original_extraction_hash"],
                          "before":source["before"],"after":after,"reason":correction["reason"],"evidence":correction.get("evidence"),"span":correction.get("span")}
                enriched=next(item for item in part if item["source_key"]==source["source_key"])
                if enriched.get("context_enrichment_version"):
                    evidence.update(context_enrichment_version=enriched["context_enrichment_version"],context_pages=[{"document_id":p["document_id"],"page":p["page"]} for p in enriched.get("context_pages",[])])
                stored=db.execute("SELECT * FROM facts WHERE fact_id=?",(latest["fact_id"],)).fetchone()
                ref=json.loads(stored["source_json"]);_apply_to_reference(ref,evidence)
                if latest["current"]!=after or ref!=json.loads(stored["source_json"]):
                    db.execute("INSERT INTO fact_history VALUES(?,?,?,?,?,?)",(uuid.uuid4().hex,project_id,stored["document_id"],runtime.get("processing_id") or "temporal_review",dumps(dict(stored)),utcnow()))
                    db.execute("UPDATE facts SET period=?,year=?,source_json=? WHERE fact_id=?",(after["period"],int(after["period"][:4]),dumps(ref),stored["fact_id"]));report["facts_updated"]+=1
                db.execute("INSERT OR REPLACE INTO temporal_corrections VALUES(?,?,?,?,?)",(project_id,source["source_key"],source["source_fingerprint"],dumps(evidence),utcnow()))
    with service.store.connect() as db:final_sources,final_unreviewable=collect_sources(db,project_id)
    report["pending_new_sources"]=[s["source_key"] for s in final_sources if initial.get(s["source_key"])!=s["source_fingerprint"]]
    report["status"]="needs_review" if report["unresolved"] or report["stale_sources"] or unreviewable or report["pending_new_sources"] or final_unreviewable else "reviewed"
    report.update(review_id=uuid.uuid4().hex,completed_at=utcnow(),processing_id=runtime.get("processing_id"),owner_run_id=runtime.get("owner_run_id"),source_snapshot_hash=digest(initial),source_fingerprints=initial)
    with service.store.connect(write=True) as db:db.execute("INSERT INTO temporal_project_reviews VALUES(?,?,?,?)",(report["review_id"],project_id,dumps(report),report["completed_at"]))
    service._write_navigation(project_id)
    return report


def temporal_review_status(store,project_id):
    """Use the completed review matching current sources, never finish order."""
    with store.connect() as db:
        if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='temporal_project_reviews'").fetchone():return {"status":"not_run"}
        records=db.execute("SELECT source_json FROM facts WHERE project_id=?",(project_id,)).fetchall()
        current={};missing=False
        for row in records:
            meta=json.loads(row[0]).get("normalization",{})
            if meta.get("source_key") and meta.get("source_fingerprint"):current[meta["source_key"]]=meta["source_fingerprint"]
            else:missing=True
        if missing:
            sources,_=collect_sources(db,project_id);current={s["source_key"]:s["source_fingerprint"] for s in sources}
        snapshot_hash=digest(current)
        row=db.execute("SELECT report_json FROM temporal_project_reviews WHERE project_id=? AND json_extract(report_json,'$.source_snapshot_hash')=? AND json_extract(report_json,'$.facts_total')=? ORDER BY created_at DESC LIMIT 1",(project_id,snapshot_hash,len(records))).fetchone()
        exact=bool(row)
        if not row:row=db.execute("SELECT report_json FROM temporal_project_reviews WHERE project_id=? ORDER BY created_at DESC LIMIT 1",(project_id,)).fetchone()
    if not row:return {"status":"not_run"}
    report=json.loads(row[0])
    summary={k:report[k] for k in ("status","review_id","completed_at","processing_id","owner_run_id","facts_total","facts_reviewable","profiles_total","profiles_reviewed","candidate_groups","sources_targeted","facts_updated","unresolved","unreviewable","stale_sources","pending_new_sources","source_snapshot_hash")}
    summary.update(coverage_snapshot_valid=exact,current_fact_count=len(records))
    for field in ("prior_review_id","reused_profile_review","profile_groups_this_run","sources_targeted_this_run","model_requests"):
        if field in report:summary[field]=report[field]
    if not exact:
        previous=report.get("source_fingerprints",{})
        summary.update(status="pending",last_review_status=report["status"],pending_new_sources=[k for k,v in current.items() if previous.get(k)!=v])
    return summary
