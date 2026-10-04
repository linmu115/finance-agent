"""Read-only verification that current-version table facts are already committed."""
from __future__ import annotations
import hashlib
import json

from .semantic import VERSION, SCHEMA_HASH, materialize, table_batches
from .store import dumps
from .temporal_semantics import stamp_source_provenance


def completed_document(service, project_id, document, runtime):
    if runtime.get("force"):return None
    parsed=service._read_prepared(project_id,document)
    if parsed is None:return None
    original=service.store.root/document["relative_path"]
    if not original.is_file():return None
    with original.open("rb") as handle:
        if hashlib.file_digest(handle,"sha256").hexdigest()!=document["sha256"]:return None
    batches=table_batches(parsed)
    if not batches:return None
    with service.store.connect() as db:
        saved={r["batch_key"]:json.loads(r["result_json"]) for r in db.execute("SELECT batch_key,result_json FROM normalization_batches WHERE document_id=?",(document["document_id"],))}
        tables={r["table_id"]:json.loads(r["rows_json"]) for r in db.execute("SELECT table_id,rows_json FROM source_tables WHERE document_id=?",(document["document_id"],))}
        records=[dict(r) for r in db.execute("SELECT * FROM facts WHERE document_id=?",(document["document_id"],))]
    # Both immutable upload and persisted original table index must still match.
    if any(tables.get(f"{document['document_id']}:t{table['index']}")!=table["rows"] for table in parsed["tables"]):return None
    actual={};retained=set()
    for record in records:
        ref=json.loads(record["source_json"]);meta=ref.get("normalization",{})
        key=meta.get("source_key")
        if record["quality"]=="previous_version_unresolved" and ref.get("retained_after_processing"):
            retained.add(key);continue
        if not key or key in actual or meta.get("version")!=VERSION or meta.get("model")!=runtime["model"]:return None
        actual[key]=(record,meta)
    expected_keys=set();issues=[];candidate_tables=set()
    for batch in batches:
        coordinates=[(f"{document['document_id']}:t{part['table']['index']}",row) for part in batch for row in part["rows"]]
        key=hashlib.sha256(dumps(coordinates).encode()).hexdigest();detail=saved.get(key)
        if not detail or detail.get("version")!=VERSION or detail.get("schema_hash")!=SCHEMA_HASH or detail.get("model")!=runtime["model"] or detail.get("repair_error") or not isinstance(detail.get("extractions"),list):return None
        if detail.get("source_input_fingerprint")!=service._batch_input_fingerprint(batch):return None
        if detail.get("coordinates")!=[list(value) for value in coordinates]:return None
        expected,warnings=materialize(detail["extractions"],batch,document["document_id"],runtime["model"])
        stamp_source_provenance(document["sha256"],expected,detail)
        for fact in expected:
            meta=fact["source"]["normalization"];source_key=meta.get("source_key")
            match=actual.get(source_key)
            if not match or match[1].get("source_fingerprint")!=meta.get("source_fingerprint"):return None
            if any(match[0][field]!=fact[field] for field in ("company","scope","currency","raw_value","raw_unit","value")):return None
            expected_keys.add(source_key)
        issues.extend(warnings);candidate_tables.update(part["table"]["index"] for part in batch)
    if set(actual)!=expected_keys:return None
    coverage={"tables_total":len(candidate_tables),"tables_completed":len(candidate_tables),"batches_total":len(batches),"batches_completed":len(batches)}
    return {"state":"needs_review" if issues or parsed.get("warnings") else "ready","progress":1,"fact_count":len(records),"reused":True,
            "coverage":coverage,"normalization":{"engine":"LangExtract","version":VERSION,"model":runtime["model"],"batches":len(batches),"completed":len(batches),"requests":0,"resumed_batches":0,"reused_committed_batches":len(batches),"skipped_materialization":True,"issues":issues}}
