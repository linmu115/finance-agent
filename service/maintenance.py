"""Host-only replay of persisted LangExtract mappings; never performs inference."""
from __future__ import annotations
import hashlib
import json
import uuid

from .semantic import VERSION, SCHEMA_HASH, materialize, table_batches
from .store import dumps, utcnow


def rematerialize_documents(service, project_id, document_ids):
    service.store.project(project_id)
    if not isinstance(document_ids,list) or not document_ids:raise ValueError("invalid_document_ids")
    maintenance_id="rematerialize_"+uuid.uuid4().hex
    report={"maintenance_id":maintenance_id,"created_at":utcnow(),"version":VERSION,"model_requests":0,
            "catalog_review":"not_run","documents":[],"batches_replayed":0,"facts_rebuilt":0}
    claimed=[]
    document_ids=list(dict.fromkeys(document_ids))
    for document_id in document_ids:service.store.document(project_id,document_id)
    with service.processing_lock:
        if any((project_id,d) in service.processing_documents for d in document_ids):raise ValueError("document_processing_active")
        for document_id in document_ids:
            service.processing_documents[(project_id,document_id)]=maintenance_id;claimed.append(document_id)
    try:
        for document_id in claimed:
            doc=service.store.document(project_id,document_id)
            parsed=service._read_prepared(project_id,doc)
            if parsed is None:raise ValueError("prepared_document_required_for_replay")
            with service.store.connect() as db:
                saved={r["batch_key"]:(json.loads(r["result_json"]),r["processing_id"]) for r in db.execute("SELECT batch_key,result_json,processing_id FROM normalization_batches WHERE document_id=?",(document_id,))}
            item={"document_id":document_id,"previous_state":doc["state"],"replayed":0,"missing_batches":0,"facts":0,"issues":[],"source_owners":[]}
            owners=set()
            for batch in table_batches(parsed):
                coordinates=[(f"{document_id}:t{p['table']['index']}",r) for p in batch for r in p["rows"]]
                key=hashlib.sha256(dumps(coordinates).encode()).hexdigest()
                cached=saved.get(key)
                if not cached:item["missing_batches"]+=1;continue
                detail,origin=cached
                if detail.get("schema_hash")!=SCHEMA_HASH or not isinstance(detail.get("extractions"),list) or detail.get("source_input_fingerprint")!=service._batch_input_fingerprint(batch):
                    item["issues"].append({"batch_key":key,"reason":"incompatible_saved_extraction"});continue
                owner=detail.get("extraction_processing_id") or origin
                facts,issues=materialize(detail["extractions"],batch,document_id,detail.get("model","unknown"))
                replay_detail={**detail,"version":VERSION,"reused_extraction":True,"extraction_processing_id":owner,"rematerialized_at":utcnow(),"maintenance_id":maintenance_id}
                service._commit_semantic_batch(project_id,document_id,maintenance_id,batch,facts,issues,replay_detail)
                item["replayed"]+=1;item["facts"]+=len(facts);item["issues"].extend(issues);owners.add(owner)
            item["source_owners"]=sorted(owners)
            report["documents"].append(item);report["batches_replayed"]+=item["replayed"];report["facts_rebuilt"]+=item["facts"]
        service._write_navigation(project_id)
        report["completed_at"]=utcnow()
        path=service.store.root/"exports"/(maintenance_id+".json")
        path.write_text(dumps(report),encoding="utf-8");report["audit_path"]=str(path)
        return report
    finally:
        with service.processing_lock:
            for document_id in claimed:
                if service.processing_documents.get((project_id,document_id))==maintenance_id:
                    service.processing_documents.pop((project_id,document_id),None)
