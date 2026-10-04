"""Verify historical source evidence without parser migration or rematerialization."""
import hashlib
import json

from .definition_semantics import build_groups
from .temporal_semantics import collect_sources


def validate_existing_review(service, project_id, document_ids, metric_ids):
    # Definitions operate on every source in the selected project metric family.
    # Verify all contributing documents, including those outside the attachment list.
    with service.store.connect() as db:
        groups,members,_,unavailable,_=build_groups(db,project_id,metric_ids)
        if unavailable:raise ValueError("existing_review_original_extractions_missing")
        if not groups:raise ValueError("existing_review_metrics_have_no_sources")
        required=set(document_ids)|{source["document_id"] for values in members.values() for source in values}
        sources,unreviewable=collect_sources(db,project_id)
        records={row["fact_id"]:dict(row) for row in db.execute("SELECT * FROM facts WHERE project_id=?",(project_id,))}
        if any(records.get(item["fact_id"],{}).get("document_id") in required for item in unreviewable):
            raise ValueError("existing_review_original_extractions_missing")
        verified={}
        for document_id in sorted(required):
            doc=service.store.document(project_id,document_id)
            if doc["state"] in {"queued","parsing","validating","normalizing"}:
                raise ValueError("existing_review_source_processing_active")
            original=service.store.root/doc["relative_path"]
            if not original.is_file():raise ValueError("existing_review_original_file_missing")
            with original.open("rb") as stream:
                if hashlib.file_digest(stream,"sha256").hexdigest()!=doc["sha256"]:
                    raise ValueError("existing_review_original_file_changed")
            prepared=db.execute("SELECT sha256,parser_version,prepared_json FROM prepared_documents WHERE document_id=?",(document_id,)).fetchone()
            if prepared:
                payload={"sha256":prepared["sha256"],"parser_version":prepared["parser_version"],"parsed":json.loads(prepared["prepared_json"])}
            else:
                path=service._prepared_path(project_id,document_id)
                if not path.is_file():raise ValueError("existing_review_source_snapshot_missing")
                payload=json.loads(path.read_text(encoding="utf-8"))
            if payload.get("sha256")!=doc["sha256"]:raise ValueError("existing_review_source_snapshot_changed")
            from .processing import _source_index
            pages=[dict(row) for row in db.execute("SELECT * FROM pages WHERE document_id=? ORDER BY page",(document_id,))]
            tables=[dict(row) for row in db.execute("SELECT * FROM source_tables WHERE document_id=?",(document_id,))]
            stored={"pages":pages,"tables":[{"index":int(row["table_id"].rsplit(":t",1)[1]),"page":row["page"],"sheet":row["sheet"],
                       "bbox":json.loads(row["bbox_json"]),"rows":json.loads(row["rows_json"]),"cells":json.loads(row["cells_json"])} for row in tables]}
            if not tables or not pages or _source_index(stored)!=_source_index(payload["parsed"]):
                raise ValueError("existing_review_source_snapshot_changed")
            own=[source for source in sources if source["document_id"]==document_id]
            if not own:raise ValueError("existing_review_facts_missing")
            for source in own:
                record=records[source["fact_id"]];meta=json.loads(record["source_json"]).get("normalization",{})
                if any(meta.get(field)!=source[field] for field in ("source_key","source_fingerprint","original_extraction_hash")):
                    raise ValueError("existing_review_original_provenance_changed")
                if str(source["row_data"][source["column"]-1]).strip()!=str(record["raw_value"]).strip():
                    raise ValueError("existing_review_raw_source_cell_changed")
            verified[document_id]={"fact_count":len(own),"source_parser_version":payload["parser_version"],"source_sha256":doc["sha256"],
                                   "source_state":doc["state"],"source_tables":len(tables),"source_pages":len(pages)}
    return verified
