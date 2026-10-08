"""Raw document access for a general Pi comparison, without financial cleaning.

Uses exactly the production deterministic parser and source persistence. It does
not invoke model normalization, legacy extract_facts, metric mapping or review.
"""
from __future__ import annotations
import hashlib
import uuid
from pathlib import Path

from .parser import PARSER_VERSION, parse_document
from .evaluation_isolation import analysis_only


def prepare_document_sources(service, project_id, document_ids, progress=lambda value,message:None, cancelled=lambda:False):
    service.store.project(project_id)
    if not isinstance(document_ids,list) or not 1<=len(document_ids)<=20 or not all(isinstance(v,str) for v in document_ids):
        raise ValueError('invalid_document_ids')
    ids=list(dict.fromkeys(document_ids))
    # Same lock as normalization: no two writers may mutate this source index.
    claim='rematerialize_baseline_'+uuid.uuid4().hex
    with service.processing_lock:
        documents=[service.store.document(project_id,i) for i in ids]
        if any(service.processing_documents.get((project_id,i)) for i in ids):raise ValueError('document_processing_active')
        for i in ids:service.processing_documents[(project_id,i)]=claim
    results=[]
    try:
        for ordinal,document in enumerate(documents):
            if cancelled():raise InterruptedError('cancelled')
            document_id=document['document_id']
            original=service.store.root/document['relative_path']
            if hashlib.sha256(original.read_bytes()).hexdigest()!=document['sha256']:raise ValueError('document_source_hash_changed')
            parsed=service._read_prepared(project_id,document);reused=parsed is not None
            if parsed is None:
                if analysis_only.get():raise ValueError('analysis_sources_not_prepared')
                with service.store.connect() as db:
                    if db.execute('SELECT 1 FROM facts WHERE document_id=? LIMIT 1',(document_id,)).fetchone() or db.execute('SELECT 1 FROM normalization_batches WHERE document_id=? LIMIT 1',(document_id,)).fetchone():
                        raise ValueError('baseline_sources_missing_for_prepared_document')
                options=service.configs.get(project_id,{})
                notify=lambda value,message:progress((ordinal+value/100)/len(documents)*100,message)
                if original.suffix.lower()=='.pdf':parsed=service._parse_native_pdf(original,document['original_name'],notify,cancelled,options)
                else:parsed=parse_document(Path(original),document['original_name'],notify,cancelled,options)
                if cancelled():raise InterruptedError('cancelled')
                service._persist_prepared(project_id,document_id,parsed)
            if not reused:
                with service.store.connect(write=True) as db:
                    db.execute("UPDATE documents SET state='sources_ready' WHERE document_id=?",(document_id,))
            results.append({'document_id':document_id,'sha256':document['sha256'],'parser_version':PARSER_VERSION,'pages':len(parsed['pages']),'tables':len(parsed['tables']),'reused_sources':reused,'facts_written':0,'state':document['state'] if reused else 'sources_ready','warnings':parsed.get('warnings',[])})
        if any(not item['reused_sources'] for item in results):service._write_navigation(project_id)
        return {'status':'ok','data':{'documents':results,'facts_written':0,'mode':'deterministic_sources_only'},'source_refs':[],'warnings':[],'trace_id':uuid.uuid4().hex}
    finally:
        with service.processing_lock:
            for document_id in ids:
                if service.processing_documents.get((project_id,document_id))==claim:service.processing_documents.pop((project_id,document_id),None)
