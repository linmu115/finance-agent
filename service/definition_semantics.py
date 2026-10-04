"""Explicit Pi-owned review of selected metric definitions.

Only identifiers, labels and definition metadata may change. Original numeric
cells, dates, accounting scopes and immutable extraction records stay intact.
"""
from __future__ import annotations
from collections import deque
from copy import deepcopy
from concurrent.futures import ThreadPoolExecutor, wait, FIRST_COMPLETED
import hashlib
import json
import re
import uuid

from .normalization import METRICS, decimal_value
from .store import dumps, utcnow
from .temporal_semantics import collect_sources
from .review_cache import shared_result, result_hash, accept_result

VERSION="definition-transactions-0.4.3"
SPLIT_POLICY_VERSION="output-limit-bisection-1"


def digest(value):return hashlib.sha256(dumps(value).encode()).hexdigest()


def _column_shape(value):
    text=re.sub(r"(?<!\d)(?:19|20|21)\d{2}(?!\d)","〈报告年〉",str(value or ""))
    return re.sub(r"本年度|上年度|本期|上期|本年|上年","〈报告期〉",text)


def _family_ids(db,project_id,metric_ids):
    if not isinstance(metric_ids,list) or not metric_ids or not all(isinstance(value,str) and re.fullmatch(r"[a-z][a-z0-9_]{0,255}",value) for value in metric_ids):
        raise ValueError("invalid_review_metrics")
    selected=set(metric_ids)
    exists=db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='metric_aliases'").fetchone()
    aliases=list(db.execute("SELECT source_metric,canonical_metric FROM metric_aliases WHERE project_id=?",(project_id,))) if exists else []
    while True:
        extended=selected|{value for pair in aliases if selected.intersection(pair) for value in pair}
        if extended==selected:return selected
        selected=extended


def _mask_page_values(text,values):
    """Remove actual numeric-cell tokens, retaining dates and unit qualifiers."""
    for value in sorted(set(values),key=len,reverse=True):
        token=str(value).strip()
        if not token or decimal_value(token) is None:continue
        pattern=re.compile(r"(?<![A-Za-z0-9_.])(?<!\d[,，])"+re.escape(token)+r"(?![A-Za-z0-9_.]|[,，]\d)")
        def replace(match):
            following=text[match.end():match.end()+12]
            preceding=text[max(0,match.start()-8):match.start()]
            if re.match(r"\s*(?:年|月|日|股|个月|天)",following):return match[0]
            if re.search(r"每\s*$",preceding):return match[0]
            return "〈原数值已省略〉"
        text=pattern.sub(replace,text)
    return text


def _row_text(row,header=False):
    return " | ".join(str(value) if decimal_value(value) is None or (header and re.fullmatch(r"(?:19|20|21)\d{2}",str(value).strip())) else "〈原数值已省略〉" for value in row)


def build_groups(db,project_id,metric_ids):
    selected=_family_ids(db,project_id,metric_ids)
    all_sources,unreviewable=collect_sources(db,project_id)
    records={row["fact_id"]:dict(row) for row in db.execute("SELECT * FROM facts WHERE project_id=?",(project_id,))}
    metas={key:json.loads(value["source_json"]).get("normalization",{}) for key,value in records.items()}
    # A completed split may remove a formerly wrong global alias. Its original
    # request membership must remain visible on resume, without re-merging its
    # meaning or silently dropping already reviewed sources from coverage.
    chosen={key for key,record in records.items() if {record["metric"],metas[key].get("original_metric"),
            metas[key].get("definition_review",{}).get("before",{}).get("metric"),
            metas[key].get("definition_review",{}).get("after",{}).get("metric")}&selected}
    sources=[source for source in all_sources if source["fact_id"] in chosen]
    unavailable=[issue for issue in unreviewable if issue["fact_id"] in chosen]
    first_rows={};page_values={}
    for source in all_sources:
        first_rows[source["table_id"]]=min(first_rows.get(source["table_id"],source["row"]),source["row"])
        page_values.setdefault((source["document_id"],source["page"]),set()).add(source["raw_value"])
    for row in db.execute("SELECT document_id,page,rows_json FROM source_tables WHERE document_id IN (SELECT document_id FROM documents WHERE project_id=?)",(project_id,)):
        for cells in json.loads(row["rows_json"]):
            for value in cells:
                if decimal_value(value) is not None:page_values.setdefault((row["document_id"],row["page"]),set()).add(str(value))
    tables={};groups={};members={};catalog={};page_texts={}
    for fact_id,record in records.items():
        meta=metas[fact_id];definition=meta.get("definition_review",{}).get("after",{})
        item=catalog.setdefault(record["metric"],{"metric":record["metric"],"labels":set(),"definitions":set(),"definition_scopes":set(),"public_id":record["metric"] in METRICS})
        item["labels"].add(meta.get("label") or record["metric"])
        if definition.get("definition"):item["definitions"].add(definition["definition"])
        if definition.get("definition_scope"):item["definition_scopes"].add(definition["definition_scope"])
    for source in sources:
        meta=metas[source["fact_id"]];record=records[source["fact_id"]]
        if source["table_id"] not in tables:
            row=db.execute("SELECT rows_json FROM source_tables WHERE table_id=?",(source["table_id"],)).fetchone();tables[source["table_id"]]=json.loads(row[0])
        rows=tables[source["table_id"]];header_count=max(0,first_rows[source["table_id"]]-1)
        headers=rows[:header_count];column=source["column"]-1
        column_definition=[str(row[column]).strip() for row in headers if len(row)>column and str(row[column]).strip()]
        # Only calendar years vary within an otherwise identical source column.
        # No global grouping by financial label, numeric equality or metric ID.
        column_shape=[_column_shape(value) for value in column_definition]
        identity={"document_id":source["document_id"],"table_id":source["table_id"],"row":source["row"],"column_definition":column_shape,
                  "column_metric":meta.get("column_metric"),"column_label":_column_shape(meta.get("column_label")),"row_metric":meta.get("row_metric"),
                  "original_metric":meta.get("original_metric") or record["metric"],"unit":record["currency"],"accounting_scope":record["scope"],"dimensions":meta.get("dimensions",{}),"restatement":meta.get("restatement","original")}
        group_id=digest(identity)
        if group_id not in groups:
            page_key=(source["document_id"],source["page"])
            if page_key not in page_texts:
                page=db.execute("SELECT text FROM pages WHERE document_id=? AND page=?",page_key).fetchone()
                page_texts[page_key]=page[0] if page else ""
            numeric_tokens=page_values.get(page_key,set())|page_values.get((source["document_id"],(source["page"] or 1)-1),set())
            blocks=[("page_context",_mask_page_values(page_texts[page_key],numeric_tokens)),
                    ("table_headers","\n".join(_row_text(row,header=True) for row in headers)),
                    ("row_context","\n".join(_row_text(row,header=i<header_count) for i,row in enumerate(rows))),
                    ("definition","原始行名："+str(meta.get("row_label") or "")+"\n原始列名："+str(meta.get("column_label") or "")+"\n本列完整表头："+" | ".join(column_definition))]
            evidence=[]
            for kind,text in blocks:
                evidence.append({"evidence_id":digest({"document_id":source["document_id"],"page":source["page"],"table_id":source["table_id"],"kind":kind,"text":text}),"kind":kind,"document_id":source["document_id"],"page":source["page"],"table_id":source["table_id"],"text":text})
            previous_key=(source["document_id"],(source["page"] or 1)-1)
            if previous_key[1]>0:
                if previous_key not in page_texts:
                    previous=db.execute("SELECT text FROM pages WHERE document_id=? AND page=?",previous_key).fetchone()
                    page_texts[previous_key]=previous[0] if previous else ""
                if page_texts[previous_key]:
                    previous_text=_mask_page_values(page_texts[previous_key],page_values.get(previous_key,set()))
                    evidence.append({"evidence_id":digest({"document_id":source["document_id"],"page":previous_key[1],"kind":"page_context","text":previous_text}),
                                     "kind":"page_context","document_id":source["document_id"],"page":previous_key[1],"table_id":"","text":previous_text})
            groups[group_id]={"group_id":group_id,"current_metric":record["metric"],"original_metric":identity["original_metric"],"current_label":meta.get("label"),
                              "original_label":meta.get("original_label") or meta.get("label"),"statement":meta.get("statement","notes"),"accounting_scope":record["scope"],
                              "normalized_unit":record["currency"],"dimensions":meta.get("dimensions",{}),"member_count":0,"evidence":evidence}
            members[group_id]=[]
        groups[group_id]["member_count"]+=1
        members[group_id].append(source|{"original_metric":identity["original_metric"],"current_label":meta.get("label"),"current_definition":meta.get("definition_review")})
    known=[]
    for metric,item in sorted(catalog.items()):
        record={key:sorted(value) if isinstance(value,set) else value for key,value in item.items() if key!="definition_scopes"}
        record["definition_scope"]="；".join(sorted(item["definition_scopes"]))
        known.append(record)
    return [groups[key] for key in sorted(groups)],members,known,unavailable,sorted(selected)


def _ensure_tables(store):
    with store.connect(write=True) as db:
        db.executescript("""
        CREATE TABLE IF NOT EXISTS fact_definition_cache(cache_key TEXT PRIMARY KEY,result_json TEXT NOT NULL,created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS fact_definition_corrections(project_id TEXT NOT NULL,source_key TEXT NOT NULL,source_fingerprint TEXT NOT NULL,correction_json TEXT NOT NULL,created_at TEXT NOT NULL,PRIMARY KEY(project_id,source_key));
        CREATE TABLE IF NOT EXISTS fact_definition_reviews(review_id TEXT PRIMARY KEY,project_id TEXT NOT NULL,report_json TEXT NOT NULL,created_at TEXT NOT NULL);
        """)


def apply_definition(fact,evidence):
    meta=fact["source"].setdefault("normalization",{})
    meta.setdefault("original_metric",fact["metric"]);meta.setdefault("original_label",meta.get("label",fact["metric"]))
    fact["metric"]=evidence["after"]["metric"];meta["label"]=evidence["after"]["label"]
    meta["definition_review"]=evidence
    if meta.get("canonical_alias"):meta["directory_alias_superseded_by_definition"]=evidence["review_id"]


def confirmed_definition(meta):
    """Shared directory/commit hook: respect an existing model definition."""
    review=meta.get("definition_review") or {}
    if review.get("status")=="reviewed" and review.get("source_fingerprint")==meta.get("source_fingerprint"):
        return review.get("after")
    return None


def overlay_saved_definitions(db,project_id,facts):
    if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='fact_definition_corrections'").fetchone():return 0
    applied=0
    for fact in facts:
        meta=fact["source"].get("normalization",{});key=meta.get("source_key")
        if not key:continue
        saved=db.execute("SELECT source_fingerprint,correction_json FROM fact_definition_corrections WHERE project_id=? AND source_key=?",(project_id,key)).fetchone()
        if saved and saved[0]==meta.get("source_fingerprint"):
            apply_definition(fact,json.loads(saved[1]));applied+=1
    return applied


def definition_chunks(groups,max_groups=6,max_chars=28000,known_metrics=None):
    from .definition_model import _render
    current=[]
    for group in groups:
        candidate=current+[group]
        if current and (len(current)>=max_groups or len(_render(candidate,known_metrics or []))>max_chars):yield current;current=[]
        current.append(group)
    if current:yield current


def metric_families(groups):
    """Connected original/current IDs, independent of financial vocabulary."""
    parents={}
    def root(value):
        parents.setdefault(value,value)
        while parents[value]!=value:
            parents[value]=parents[parents[value]];value=parents[value]
        return value
    for group in groups:
        left,right=root(group["original_metric"]),root(group["current_metric"])
        if left!=right:parents[max(left,right)]=min(left,right)
    result={}
    for group in groups:result.setdefault(root(group["original_metric"]),[]).append(group)
    return result


def family_catalog(known,groups):
    """Only concepts directly represented by this selected source family."""
    selected={group[field] for group in groups for field in ("original_metric","current_metric")}
    result={item["metric"]:item for item in known if item["metric"] in selected}
    for group in groups:
        for field,label in (("original_metric","original_label"),("current_metric","current_label")):
            metric=group[field]
            if metric not in result:result[metric]={"metric":metric,"labels":[group.get(label) or metric],"definitions":[],"definition_scope":"","public_id":metric in METRICS}
    return [result[key] for key in sorted(result)]


def definition_status(store,project_id):
    with store.connect() as db:
        if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='fact_definition_reviews'").fetchone():return {"status":"not_run","reviewed_fact_count":0,"definitions":[]}
        definitions={};count=0
        for row in db.execute("SELECT metric,source_json FROM facts WHERE project_id=?",(project_id,)):
            meta=json.loads(row["source_json"]).get("normalization",{});definition=confirmed_definition(meta)
            if not definition:continue
            count+=1;key=(row["metric"],definition["definition"],definition["definition_scope"])
            item=definitions.setdefault(key,definition|{"fact_count":0});item["fact_count"]+=1
        records=[json.loads(row[0]) for row in db.execute("SELECT report_json FROM fact_definition_reviews WHERE project_id=? ORDER BY created_at DESC LIMIT 10",(project_id,))]
    reports=[{key:value for key,value in record.items() if key not in {"source_fingerprints","audits","failed_attempts"}} for record in records]
    return {"status":reports[0]["status"] if reports else "not_run","reviewed_fact_count":count,"definitions":list(definitions.values()),"reviews":reports}


def revalidate_saved_groups(db,groups,members):
    """Verify immutable accepted payloads before registering present-day reuse.

    This receipt never rewrites a fact's original owner/review ID or creates a
    historical review that was not persisted at the time.
    """
    from .definition_model import align_extractions,validate_review
    payloads,audits={},{}
    fields=("metric","label","definition","definition_scope","reason","grounded_quotes")
    for group in groups:
        for source in members[group["group_id"]]:
            saved=source["current_definition"];key=saved.get("cache_key")
            if key not in payloads:
                row=db.execute("SELECT result_json FROM fact_definition_cache WHERE cache_key=?",(key,)).fetchone()
                if not row:raise ValueError("definition_reuse_cache_missing")
                payloads[key]=json.loads(row[0])
            cache=payloads[key];provenance=cache.get("_review_provenance",{})
            if (result_hash(cache)!=saved.get("result_hash") or provenance!={"processing_id":saved.get("extraction_processing_id"),"owner_run_id":saved.get("owner_run_id")}):
                raise ValueError("definition_reuse_cache_owner_or_hash_mismatch")
            if any(saved.get(field)!=source.get(field) for field in ("source_key","source_fingerprint","original_extraction_hash")):
                raise ValueError("definition_reuse_source_mismatch")
            if (saved.get("group_id")!=group["group_id"]
                    or (saved.get("after",{}).get("metric"),saved.get("after",{}).get("label"))!=(source["metric"],source["current_label"])):
                raise ValueError("definition_reuse_active_fact_mismatch")
            choices=[item for item in cache.get("decisions",[]) if item.get("group_id")==group["group_id"]]
            raw=[item for item in cache.get("extractions",[]) if item.get("text")==f"[[DEFINITION:{group['group_id']}]]"]
            checked,errors=validate_review(align_extractions(raw,[group],[]),[group],[])
            if errors or len(choices)!=1 or len(checked["decisions"])!=1:
                raise ValueError("definition_reuse_extraction_or_quote_invalid")
            decision=choices[0];verified=checked["decisions"][0]
            if (any(decision.get(field)!=verified.get(field) for field in fields)
                    or decision.get("quote_alignments",[])!=verified.get("quote_alignments",[])
                    or saved.get("after")!={field:decision[field] for field in ("metric","label","definition","definition_scope")}
                    or saved.get("reason")!=decision["reason"] or saved.get("grounded_quotes")!=decision["grounded_quotes"]
                    or saved.get("quote_alignments",[])!=decision.get("quote_alignments",[])):
                raise ValueError("definition_reuse_decision_mismatch")
            item=audits.setdefault(key,{"cache_key":key,"result_hash":result_hash(cache),
                "group_count":len(cache.get("decisions",[]))+len(cache.get("unresolved",[])),"provenance":provenance,
                "kind":"revalidated_cached_result","revalidated_source_keys":[],"historical_review_ids":[],
                "original_registration_missing":False})
            item["revalidated_source_keys"].append(source["source_key"])
            if saved["review_id"] not in item["historical_review_ids"]:item["historical_review_ids"].append(saved["review_id"])
            original=db.execute("SELECT report_json FROM fact_definition_reviews WHERE review_id=?",(saved["review_id"],)).fetchone()
            original_audits=json.loads(original[0]).get("audits",[]) if original else []
            registered=any(a.get("cache_key")==key and a.get("result_hash")==item["result_hash"] and a.get("provenance")==provenance for a in original_audits)
            item["original_registration_missing"]|=not registered
    return list(audits.values())


def review_project(service,project_id,metric_ids,runtime,progress=lambda message:None,cancelled=lambda:False):
    from .definition_model import review_definitions, VERSION as MODEL_VERSION, CACHE_HASH, PROMPT_HASH, COMPATIBLE_CACHE_HASHES, DefinitionOutputLimitError
    if not runtime.get("processing_id") or not runtime.get("owner_run_id"):raise ValueError("definition_review_owner_required")
    service.store.project(project_id);_ensure_tables(service.store)
    with service.store.connect() as db:groups,members,known,unavailable,selected=build_groups(db,project_id,metric_ids)
    report={"review_id":uuid.uuid4().hex,"version":VERSION,"model_version":MODEL_VERSION,"model":runtime["model"],"metric_ids":metric_ids,"expanded_metric_ids":selected,
            "groups_total":len(groups),"groups_reviewed":0,"facts_total":sum(len(rows) for rows in members.values())+len(unavailable),"facts_updated":0,
            "model_requests":0,"cache_hits":0,"unreviewable":unavailable,"unresolved":[],"stale_sources":[],"audits":[],"processing_id":runtime["processing_id"],"owner_run_id":runtime["owner_run_id"],
            "status":"running","started_at":utcnow(),"failures":[],"failed_attempts":[],"split_policy":SPLIT_POLICY_VERSION,"split_attempts":[],"historical_output_limits":[]}
    if not groups and not unavailable:raise ValueError("review_metrics_not_found")
    reused=[]
    if not runtime.get("force"):
        for group in groups:
            previous=[source.get("current_definition") or {} for source in members[group["group_id"]]]
            if all(saved.get("status")=="reviewed" and saved.get("version")==MODEL_VERSION and saved.get("prompt_hash")==PROMPT_HASH and saved.get("cache_hash") in COMPATIBLE_CACHE_HASHES and saved.get("model")==runtime["model"] and saved.get("source_fingerprint")==source["source_fingerprint"] for saved,source in zip(previous,members[group["group_id"]])):
                reused.append(group["group_id"])
    report["groups_reviewed"]=len(reused);report["reused_verified_groups"]=len(reused)
    with service.store.connect() as db:
        report["audits"]=revalidate_saved_groups(db,[group for group in groups if group["group_id"] in set(reused)],members)
    pending_groups=[group for group in groups if group["group_id"] not in set(reused)]
    snapshot={source["source_key"]:source["source_fingerprint"] for values in members.values() for source in values}
    report.update(source_snapshot_hash=digest(snapshot),source_fingerprints=snapshot)
    def save_report(db):
        report["updated_at"]=utcnow()
        db.execute("INSERT INTO fact_definition_reviews VALUES(?,?,?,?) ON CONFLICT(review_id) DO UPDATE SET report_json=excluded.report_json",
                   (report["review_id"],project_id,dumps(report),report["started_at"]))
    with service.store.connect(write=True) as db:save_report(db)
    def infer(part,current_known,split_depth=0,parent_cache_key=None):
        if cancelled():raise InterruptedError("cancelled")
        key=digest({"config":CACHE_HASH,"model":runtime["model"],"groups":part,"known_metrics":current_known})
        attempted=0
        def compute():
            nonlocal attempted
            from .definition_history import historical_output_limit
            fingerprints={source["source_key"]:source["source_fingerprint"] for group in part for source in members[group["group_id"]]}
            historical=historical_output_limit(service.store,project_id,key,part,current_known,runtime,fingerprints)
            if historical:
                error=DefinitionOutputLimitError([],historical["group_ids"])
                error.historical_limit=historical
                raise error
            result=review_definitions(part,current_known,runtime,progress,cancelled)
            attempted=result.get("requests",0)
            result["_review_provenance"]={"processing_id":runtime["processing_id"],"owner_run_id":runtime["owner_run_id"]}
            return result,result.get("requests",0)
        def validate(result):
            expected={group["group_id"] for group in part};answered=[item["group_id"] for item in result["decisions"]+result["unresolved"]]
            if set(answered)!=expected or len(answered)!=len(set(answered)):raise ValueError("definition_review_coverage_invalid")
        try:
            result,cached,calls=shared_result(service.store,"fact_definition_cache",{"cache_key":key},compute,cancelled,validate)
        except Exception as exc:
            exc.definition_batch={"cache_key":key,"group_ids":[group["group_id"] for group in part],"split_depth":split_depth,"parent_cache_key":parent_cache_key}
            exc.definition_input_groups=part
            if not hasattr(exc,"definition_requests"):exc.definition_requests=attempted
            raise
        return part,key,result,cached,calls
    def commit(completed):
        part,key,result,cached,requests=completed
        if cancelled():raise InterruptedError("cancelled")
        expected={group["group_id"] for group in part};answered=[item["group_id"] for item in result["decisions"]+result["unresolved"]]
        if set(answered)!=expected or len(answered)!=len(set(answered)):raise ValueError("definition_review_coverage_invalid")
        report["groups_reviewed"]+=len(part);report["model_requests"]+=requests;report["cache_hits"]+=int(cached)
        report["unresolved"].extend(result["unresolved"]);report["audits"].append({"cache_key":key,"result_hash":result_hash(result),"group_count":len(part),"provenance":result["_review_provenance"]})
        with service.store.connect(write=True) as db:
            current,_=collect_sources(db,project_id);now={source["source_key"]:source for source in current}
            for decision in result["decisions"]:
                for source in members[decision["group_id"]]:
                    latest=now.get(source["source_key"])
                    if not latest or latest["source_fingerprint"]!=source["source_fingerprint"]:
                        report["stale_sources"].append(source["source_key"]);continue
                    record=db.execute("SELECT * FROM facts WHERE fact_id=?",(latest["fact_id"],)).fetchone();ref=json.loads(record["source_json"]);meta=ref.get("normalization",{})
                    if meta.get("definition_review")!=source.get("current_definition"):
                        accepted=meta.get("definition_review") or {}
                        if accepted.get("cache_key")==key and accepted.get("source_fingerprint")==source["source_fingerprint"] and accepted.get("after")=={field:decision[field] for field in ("metric","label","definition","definition_scope")}:
                            continue
                        report["stale_sources"].append(source["source_key"]);continue
                    if (record["metric"],meta.get("label"))!=(source["metric"],source["current_label"]) and (record["metric"],meta.get("label"))!=(decision["metric"],decision["label"]):
                        report["stale_sources"].append(source["source_key"]);continue
                    after={field:decision[field] for field in ("metric","label","definition","definition_scope")}
                    evidence={"review_id":report["review_id"],"status":"reviewed","engine":"LangExtract","version":MODEL_VERSION,"model":runtime["model"],"prompt_hash":PROMPT_HASH,"cache_hash":CACHE_HASH,
                              "result_hash":result_hash(result),
                              "group_id":decision["group_id"],
                              "source_key":source["source_key"],"source_fingerprint":source["source_fingerprint"],"original_extraction_hash":source["original_extraction_hash"],
                              "extraction_processing_id":result["_review_provenance"]["processing_id"],"owner_run_id":result["_review_provenance"]["owner_run_id"],
                              "before":{"metric":source["metric"],"label":source["current_label"]},"after":after,"reason":decision["reason"],"grounded_quotes":decision["grounded_quotes"],"quote_alignments":decision.get("quote_alignments",[]),"cache_key":key}
                    fact={"metric":record["metric"],"source":ref};apply_definition(fact,evidence)
                    if record["metric"]!=fact["metric"] or dumps(ref)!=record["source_json"]:
                        db.execute("INSERT INTO fact_history VALUES(?,?,?,?,?,?)",(uuid.uuid4().hex,project_id,record["document_id"],runtime["processing_id"],dumps(dict(record)),utcnow()))
                        db.execute("UPDATE facts SET metric=?,source_json=? WHERE fact_id=?",(fact["metric"],dumps(ref),record["fact_id"]));report["facts_updated"]+=1
                    db.execute("INSERT OR REPLACE INTO fact_definition_corrections VALUES(?,?,?,?,?)",(project_id,source["source_key"],source["source_fingerprint"],dumps(evidence),utcnow()))
                    # A global old-ID alias cannot express a per-source
                    # definition split; remove it rather than routing an
                    # explicit old-ID query back into the mixed target.
                    if db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='metric_aliases'").fetchone():
                        db.execute("DELETE FROM metric_aliases WHERE project_id=? AND source_metric=?",(project_id,source["original_metric"]))
            save_report(db)
    errors=[]
    with ThreadPoolExecutor(max_workers=3,thread_name_prefix="pi-definition-review") as pool:
        # Observe every already-started batch even when another family fails.
        # Only new scheduling stops; independently valid in-flight results still
        # receive their own atomic facts/history/report commit.
        all_families=metric_families(groups)
        family_ids={family:{item[field] for item in items for field in ("original_metric","current_metric")} for family,items in all_families.items()}
        families={family:deque(item for item in items if item in pending_groups) for family,items in all_families.items()}
        split_queues={family:deque() for family in families}
        def submit(family,current_groups,current_known):
            related=[item for item in current_groups if item["original_metric"] in family_ids[family] or item["current_metric"] in family_ids[family]]
            directory=family_catalog(current_known,related)
            if split_queues[family]:
                ids,depth,parent=split_queues[family].popleft()
                latest={item["group_id"]:item for item in current_groups}
                part=[latest[identity] for identity in ids]
            else:
                part=next(definition_chunks(list(families[family]),known_metrics=directory))
                for _ in part:families[family].popleft()
                depth,parent=0,None
            return pool.submit(infer,part,directory,depth,parent)
        futures={submit(family,groups,known):family for family,parts in families.items() if parts}
        while futures:
            completed,_=wait(futures,return_when=FIRST_COMPLETED)
            next_families=[]
            for future in completed:
                family=futures.pop(future)
                before_report=deepcopy(report)
                try:
                    commit(future.result())
                    next_families.append(family)
                except Exception as exc:
                    # A failed write rolls back facts and its report together.
                    report.clear();report.update(before_report)
                    failure={"error":str(exc) if isinstance(exc,(ValueError,InterruptedError)) else type(exc).__name__,
                             **getattr(exc,"definition_batch",{}),"model_requests":getattr(exc,"definition_requests",0),
                             "validation_errors":getattr(exc,"validation_errors",[])}
                    report["model_requests"]+=failure["model_requests"]
                    historical=getattr(exc,"historical_limit",None)
                    if historical:
                        report["historical_output_limits"].append(historical)
                        failure["historical_index"]=len(report["historical_output_limits"])-1
                    pending_ids=getattr(exc,"pending_group_ids",None) or failure.get("group_ids",[])
                    partial=getattr(exc,"partial_result",None)
                    if partial:
                        proposed=deepcopy(partial)
                        proposed["_review_provenance"]={"processing_id":runtime["processing_id"],"owner_run_id":runtime["owner_run_id"]}
                        accepted_ids={item["group_id"] for item in proposed["decisions"]+proposed["unresolved"]}
                        accepted_part=[item for item in exc.definition_input_groups if item["group_id"] in accepted_ids]
                        partial_key=digest({"config":CACHE_HASH,"partial_of":failure["cache_key"],"accepted_groups":sorted(accepted_ids)})
                        with service.store.connect(write=True) as db:
                            accepted,inserted=accept_result(db,"fact_definition_cache",{"cache_key":partial_key},proposed)
                        # The failed parent owns/counts these requests once.
                        commit((accepted_part,partial_key,accepted,not inserted,0))
                    if isinstance(exc,DefinitionOutputLimitError) and len(pending_ids)>1 and not cancelled():
                        middle=len(pending_ids)//2;children=[pending_ids[:middle],pending_ids[middle:]]
                        depth=failure.get("split_depth",0)+1
                        for ids in reversed(children):split_queues[family].appendleft((ids,depth,failure["cache_key"]))
                        report["split_attempts"].append(failure|{"children":children,"policy":SPLIT_POLICY_VERSION})
                        if not historical:report["failed_attempts"].append({"split_index":len(report["split_attempts"])-1,"attempts":getattr(exc,"model_attempts",[])})
                        next_families.append(family)
                    else:
                        errors.append(exc)
                        report["failures"].append(failure)
                        if not historical:report["failed_attempts"].append({"failure_index":len(report["failures"])-1,"attempts":getattr(exc,"model_attempts",[])})
                    with service.store.connect(write=True) as db:save_report(db)
            if not errors and not cancelled():
                for family in next_families:
                    if families[family] or split_queues[family]:
                        with service.store.connect() as db:latest_groups,_,latest_known,_,_=build_groups(db,project_id,selected)
                        futures[submit(family,latest_groups,latest_known)]=family
        if cancelled() and not errors:errors.append(InterruptedError("cancelled"))
    if errors:
        report.update(status="cancelled" if cancelled() or isinstance(errors[0],InterruptedError) else "failed",completed_at=utcnow(),
                      groups_pending=report["groups_total"]-report["groups_reviewed"])
        with service.store.connect(write=True) as db:save_report(db)
        errors[0].definition_report=report
        raise errors[0]
    with service.store.connect() as db:_,final_members,_,final_unavailable,_=build_groups(db,project_id,selected)
    reviewed={source["source_key"]:source["source_fingerprint"] for values in members.values() for source in values}
    report["pending_new_sources"]=[source["source_key"] for values in final_members.values() for source in values if reviewed.get(source["source_key"])!=source["source_fingerprint"]]
    report["status"]="needs_review" if report["unresolved"] or unavailable or final_unavailable or report["stale_sources"] or report["pending_new_sources"] else "reviewed"
    report.update(completed_at=utcnow(),source_snapshot_hash=digest(reviewed),source_fingerprints=reviewed)
    with service.store.connect(write=True) as db:save_report(db)
    return report
