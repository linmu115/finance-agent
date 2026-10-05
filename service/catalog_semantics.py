"""Pi-owned LangExtract review of the project's financial metric directory.

This changes metric identities, never raw cells, periods, scopes, or values.
The original model mapping remains in source.normalization.original_*.
"""
from __future__ import annotations
import hashlib
import json
import re

from .normalization import METRICS
from .store import dumps, utcnow
from .definition_semantics import confirmed_definition
from .review_cache import shared_result, result_hash

from .catalog_model import PROMPT_HASH, CACHE_HASH, INFERENCE_CONFIG, VERSION, _call_model

def _hash(value):return hashlib.sha256(dumps(value).encode()).hexdigest()


def _bounded_review(store,project_id,profiles,runtime,progress,cancelled):
    """Bounded directory review; completed batches survive an interrupted owner.

    Candidate IDs supplement each primary batch. Cross-batch merge chains are
    conservatively kept separate; numeric data and meaning are never guessed.
    """
    if len(profiles)<=80 and len(dumps(profiles))<=60000:
        return _call_model(profiles,runtime,progress,cancelled)
    groups=[];current=[]
    for profile in profiles:
        if current and (len(current)>=48 or len(dumps(current+[profile]))>40000):groups.append(current);current=[]
        current.append(profile)
    if current:groups.append(current)
    aliases={};extractions=[];requests=0;failed=[];metric_sources={}
    for index,primary in enumerate(groups):
        if cancelled():raise InterruptedError('cancelled')
        ids={p['metric'] for p in primary}
        words=set(re.findall(r'[a-z]{3,}|[\u4e00-\u9fff]{2}', ' '.join(p['metric']+' '+' '.join(p['labels']) for p in primary)))
        def rank(p):return -len(words & set(re.findall(r'[a-z]{3,}|[\u4e00-\u9fff]{2}',p['metric']+' '+' '.join(p['labels']))))
        candidates=sorted((p for p in profiles if p['metric'] not in ids),key=rank)[:24]
        batch=list(primary)
        for candidate in candidates:
            if len(dumps(batch+[candidate]))<=60000:batch.append(candidate)
        batch_hash=_hash({'partition':'bounded-1','primary':sorted(ids),'profiles':batch})
        def infer():
            review,raw,count=_call_model(batch,runtime,lambda message:progress(f'目录复核 {index+1}/{len(groups)} 批 · '+message),cancelled)
            return {'review':review,'extractions':raw,'_review_provenance':{'processing_id':runtime.get('processing_id'),'owner_run_id':runtime.get('owner_run_id')}},count
        try:
            saved,_,count=shared_result(store,'metric_directory_reviews',{'project_id':project_id,'catalog_hash':batch_hash,'prompt_hash':CACHE_HASH,'model':runtime['model']},infer,cancelled)
            requests+=count;extractions.extend(saved['extractions'])
            for metric in ids:metric_sources[metric]={'catalog_hash':batch_hash,'result_hash':result_hash(saved),'source_provenance':saved.get('_review_provenance')}
            aliases.update({m:decision for m,decision in saved['review']['aliases'].items() if m in ids})
        except InterruptedError:raise
        except Exception:failed.append(index)
    if failed:raise ValueError('catalog_batches_pending_retry')
    # A target that is itself proposed as an alias cannot be merged safely in
    # this pass. Preserve both IDs rather than invent a transitive equivalence.
    conflicted={m for m,d in aliases.items() if d['canonical_metric'] in aliases}
    for metric in conflicted:aliases.pop(metric)
    return {'keep':[p['metric'] for p in profiles if p['metric'] not in aliases],'aliases':aliases,'metric_sources':metric_sources},extractions,requests


def _ensure_tables(store):
    with store.connect(write=True) as db:
        db.executescript("""
        CREATE TABLE IF NOT EXISTS metric_directory_reviews(project_id TEXT NOT NULL,catalog_hash TEXT NOT NULL,
          prompt_hash TEXT NOT NULL,model TEXT NOT NULL,result_json TEXT NOT NULL,created_at TEXT NOT NULL,
          PRIMARY KEY(project_id,catalog_hash,prompt_hash,model));
        CREATE TABLE IF NOT EXISTS metric_aliases(project_id TEXT NOT NULL,source_metric TEXT NOT NULL,
          canonical_metric TEXT NOT NULL,canonical_label TEXT NOT NULL,review_hash TEXT NOT NULL,evidence_json TEXT NOT NULL,
          updated_at TEXT NOT NULL,PRIMARY KEY(project_id,source_metric));
        """)


def snapshot(db, project_id):
    groups={};table_cache={}
    rows=db.execute("SELECT fact_id,metric,currency,raw_unit,source_json FROM facts WHERE project_id=? ORDER BY document_id,rowid",(project_id,)).fetchall()
    for row in rows:
        ref=json.loads(row["source_json"]);meta=ref.get("normalization",{})
        definition=confirmed_definition(meta)
        metric=definition["metric"] if definition else meta.get("original_metric") or row["metric"]
        label=definition["label"] if definition else meta.get("original_label") or meta.get("label") or METRICS.get(metric,[metric])[0]
        profile=groups.setdefault(metric,{"metric":metric,"labels":set(),"statements":set(),"units":set(),"dimension_keys":set(),"examples":[]})
        profile["labels"].add(label);profile["statements"].add(meta.get("statement","notes"));profile["units"].add(row["currency"])
        profile["dimension_keys"].update(meta.get("dimensions",{}))
        if definition:
            profile["definition_locked"]=True
            profile.setdefault("definitions",set()).add(definition["definition"])
            profile.setdefault("definition_scopes",set()).add(definition["definition_scope"])
        if len(profile["examples"])<2 and not any(e["table_id"]==ref.get("table_id") for e in profile["examples"]):
            table_id=ref.get("table_id")
            if table_id not in table_cache:
                source=db.execute("SELECT rows_json FROM source_tables WHERE table_id=?",(table_id,)).fetchone()
                table_cache[table_id]=json.loads(source[0]) if source else []
            source_rows=table_cache[table_id];index=max(0,int(ref.get("row",1))-1)
            neighborhood=source_rows[max(0,index-3):index+3]
            # Row labels supply statement hierarchy; values are irrelevant to identity.
            context=[" | ".join(str(c) for c in r[:2])[:220] for r in neighborhood]
            profile["examples"].append({"table_id":table_id,"page":ref.get("page"),"row_label":ref.get("text","").split(" | ")[0][:200],"context":context})
    result=[]
    for metric,profile in sorted(groups.items()):
        for field in ("labels","statements","units","dimension_keys"):profile[field]=sorted(profile[field])
        for field in ("definitions","definition_scopes"):
            if field in profile:profile[field]=sorted(profile[field])
        # Model sees source context; directory hash ignores file IDs and numeric changes.
        signature={k:profile[k] for k in ("metric","labels","statements","units","dimension_keys")}
        signature["contexts"]=[[re.sub(r"[\d,.]+","#",s) for s in e["context"]] for e in profile["examples"]]
        if profile.get("definition_locked"):signature.update(definition_locked=True,definitions=profile["definitions"],definition_scopes=profile["definition_scopes"])
        profile["signature"]=_hash(signature)
        result.append(profile)
    return result,_hash([(p["metric"],p["signature"]) for p in result])


def canonicalize_project(store, project_id, runtime, progress=lambda message:None, cancelled=lambda:False, max_rounds=3):
    store.project(project_id);_ensure_tables(store)
    aggregate={"engine":"LangExtract","version":VERSION,"model":runtime.get("model"),"requests":0,"cache_hits":0,"facts_updated":0,"alias_count":0,"pending_metric_ids":[]}
    if not runtime.get("force"):
        with store.connect() as db:
            existing=db.execute("SELECT metric,source_json FROM facts WHERE project_id=?",(project_id,)).fetchall()
            verified=0
            for row in existing:
                meta=json.loads(row["source_json"]).get("normalization",{});definition=confirmed_definition(meta);previous=meta.get("canonical_alias",{})
                if definition and definition["metric"]==row["metric"]:verified+=1
                elif previous.get("status")=="reviewed" and previous.get("version")==VERSION and previous.get("model")==runtime.get("model") and previous.get("prompt_hash")==PROMPT_HASH and previous.get("canonical_metric")==row["metric"] and previous.get("canonical_label")==meta.get("label"):verified+=1
            if existing and verified==len(existing):
                count=db.execute("SELECT count(*) FROM metric_aliases WHERE project_id=?",(project_id,)).fetchone()[0]
                return aggregate|{"status":"reviewed","cache_hits":1,"reused_verified_facts":verified,"metric_count":len({row["metric"] for row in existing}),"alias_count":count}
    for round_number in range(max_rounds):
        with store.connect() as db:
            profiles,catalog_hash=snapshot(db,project_id)
        if not profiles:return aggregate|{"status":"empty","metric_count":0}
        def infer():
            review,extractions,requests=_bounded_review(store,project_id,profiles,runtime,progress,cancelled)
            return {"review":review,"extractions":extractions,"catalog_hash":catalog_hash,"prompt_hash":PROMPT_HASH,"cache_hash":CACHE_HASH,"inference_config":INFERENCE_CONFIG,"model":runtime["model"],"created_at":utcnow(),
                    "_review_provenance":{"processing_id":runtime.get("processing_id"),"owner_run_id":runtime.get("owner_run_id")}},requests
        saved,cached,requests=shared_result(store,"metric_directory_reviews",{"project_id":project_id,"catalog_hash":catalog_hash,"prompt_hash":CACHE_HASH,"model":runtime["model"]},infer,cancelled)
        aggregate["requests"]+=requests;aggregate["cache_hits"]+=int(cached)
        review=saved["review"];extractions=saved["extractions"]
        if cancelled():raise InterruptedError("cancelled")
        before={p["metric"]:p for p in profiles}
        with store.connect(write=True) as db:
            current,current_hash=snapshot(db,project_id);now={p["metric"]:p for p in current}
            compatible={m for m in before if m in now and before[m]["signature"]==now[m]["signature"]}
            protected={m for m in compatible if now[m].get("definition_locked")}
            # Source and target must both still refer to the reviewed concepts.
            aliases={m:d for m,d in review["aliases"].items() if m in compatible and m not in protected and d["canonical_metric"] in compatible}
            covered=(set(review["keep"])&compatible)|set(aliases)|protected
            pending=set(now)-covered
            for source in set(review["keep"]) & compatible:
                db.execute("DELETE FROM metric_aliases WHERE project_id=? AND source_metric=?",(project_id,source))
            target_labels={d["canonical_metric"]:d["canonical_label"] for d in aliases.values()}
            for source,decision in aliases.items():
                db.execute("INSERT OR REPLACE INTO metric_aliases VALUES(?,?,?,?,?,?,?)",(project_id,source,decision["canonical_metric"],decision["canonical_label"],catalog_hash,dumps(decision),utcnow()))
            records=db.execute("SELECT fact_id,metric,source_json FROM facts WHERE project_id=?",(project_id,)).fetchall()
            for record in records:
                ref=json.loads(record["source_json"]);meta=ref.setdefault("normalization",{})
                if confirmed_definition(meta):continue
                source=meta.get("original_metric") or record["metric"]
                if source not in covered:continue
                original_label=meta.get("original_label") or meta.get("label") or source
                decision=aliases.get(source)
                target=decision["canonical_metric"] if decision else source
                canonical_label=decision["canonical_label"] if decision else target_labels.get(source,original_label)
                evidence={"status":"reviewed","engine":"LangExtract","version":VERSION,"model":runtime["model"],"catalog_hash":catalog_hash,"prompt_hash":PROMPT_HASH,
                          "source_metric":source,"canonical_metric":target,"canonical_label":canonical_label,"decision":"alias" if decision else "keep",
                          "result_hash":result_hash(saved),"source_provenance":saved.get("_review_provenance")}
                batch_source=review.get('metric_sources',{}).get(source)
                if batch_source:evidence.update(batch_catalog_hash=batch_source['catalog_hash'],batch_result_hash=batch_source['result_hash'],source_provenance=batch_source['source_provenance'])
                if decision:evidence.update(reason=decision["reason"],char_interval=decision["span"],extraction_text=decision["extraction_text"])
                meta.update(original_metric=source,original_label=original_label,label=canonical_label,canonical_alias=evidence)
                changed=record["metric"]!=target or ref!=json.loads(record["source_json"])
                if changed:
                    db.execute("UPDATE facts SET metric=?,source_json=? WHERE fact_id=?",(target,dumps(ref),record["fact_id"]));aggregate["facts_updated"]+=1
            aggregate.update(alias_count=len(aliases),metric_count=len(current),catalog_hash=catalog_hash,pending_metric_ids=sorted(pending))
        if not pending:return aggregate|{"status":"reviewed"}
        progress(f"目录新增或变动 {len(pending)} 个指标，读取最新目录继续审校")
    return aggregate|{"status":"pending","reason":"directory_changed_during_review"}


def directory_status(store,project_id):
    with store.connect() as db:
        rows=db.execute("SELECT source_json FROM facts WHERE project_id=?",(project_id,)).fetchall()
        reviewed=0
        for row in rows:
            meta=json.loads(row[0]).get("normalization",{})
            if confirmed_definition(meta) or meta.get("canonical_alias",{}).get("status")=="reviewed":reviewed+=1
        return {"status":"not_run" if not reviewed else "reviewed" if reviewed==len(rows) else "partial",
                "reviewed_fact_count":reviewed,"pending_fact_count":len(rows)-reviewed,"engine":"LangExtract","version":VERSION}
