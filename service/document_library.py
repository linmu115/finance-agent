"""Explicit UI deletion of a document and its ingested data, within one project."""
import json
import shutil
from pathlib import Path
from .store import dumps, utcnow


DOCUMENT_TABLES = ('pages', 'source_tables', 'facts', 'fact_history', 'chunks', 'jobs',
    'normalization_batches', 'prepared_documents', 'source_parse_history',
    'research_records', 'research_page_reviews', 'research_document_entities',
    'document_profiles', 'document_profile_history', 'attachment_flows')


def remove_document(service, project_id, document_id):
    store = service.store
    doc = store.document(project_id, document_id)
    removed = {}
    run_ids = set()
    with service.ingest_lock, service.processing_lock, store.connect(write=True) as db:
        db.execute('BEGIN IMMEDIATE')
        if service.processing_documents.get((project_id, document_id)):
            raise ValueError('资料正在入库，请完成或停止任务后删除')
        source_keys = set()
        for row in db.execute('SELECT source_json FROM facts WHERE document_id=?', (document_id,)):
            meta = json.loads(row[0]).get('normalization', {})
            for value in meta.values():
                if isinstance(value, dict) and value.get('source_key'): source_keys.add(value['source_key'])
            if meta.get('source_key'): source_keys.add(meta['source_key'])
        if db.execute("SELECT 1 FROM jobs WHERE document_id=? AND state IN ('queued','parsing','running')", (document_id,)).fetchone():
            raise ValueError('资料正在解析，请完成或停止任务后删除')
        # Remove this document from multi-document progress without erasing its peers.
        for row in db.execute('SELECT * FROM processing_runs WHERE project_id=?', (project_id,)).fetchall():
            state = json.loads(row['state_json'])
            documents = state.get('documents', [])
            if not any(d.get('document_id') == document_id for d in documents):
                continue
            jobs = state.get('jobs', {})
            related = {key for key, job in jobs.items() if job.get('document_id') == document_id}
            run_ids.update(related)
            state['jobs'] = {key: job for key, job in jobs.items() if key not in related}
            state['documents'] = [d for d in documents if d.get('document_id') != document_id]
            if state['documents']:
                state['fact_count'] = sum(d.get('fact_count', 0) for d in state['documents'])
                state['research_record_count'] = sum(d.get('research_record_count', 0) for d in state['documents'])
                state['coverage'] = {key: sum(d.get('coverage', {}).get(key, 0) for d in state['documents'])
                                     for key in ('tables_total','tables_completed','batches_total','batches_completed')}
                state['progress'] = sum(d.get('progress', 0) for d in state['documents']) / len(state['documents'])
                for key in ('catalog_review', 'definition_review', 'temporal_review'):
                    state.pop(key, None)
                db.execute('UPDATE processing_runs SET state_json=?,updated_at=? WHERE processing_id=?', (dumps(state), utcnow(), row['processing_id']))
            else:
                db.execute('DELETE FROM processing_runs WHERE processing_id=?', (row['processing_id'],))
        for row in db.execute('SELECT run_id FROM analysis_jobs WHERE project_id=?', (project_id,)).fetchall():
            metadata = store.root / 'exports' / project_id / row['run_id'] / 'analysis_inputs.json'
            if metadata.is_file() and document_id in json.loads(metadata.read_text('utf-8')).get('document_ids', []):
                run_ids.add(row['run_id'])
        if any(run_id in service.analysis_futures and not service.analysis_futures[run_id].done() for run_id in run_ids):
            raise ValueError('资料仍被计算任务使用，请完成或停止任务后删除')
        for run_id in run_ids:
            db.execute('DELETE FROM analysis_jobs WHERE project_id=? AND run_id=?', (project_id, run_id))
        db.execute('DELETE FROM chunks_fts WHERE chunk_id IN (SELECT chunk_id FROM chunks WHERE document_id=?)', (document_id,))
        tables = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        for table in DOCUMENT_TABLES:
            if table in tables:
                removed[table] = db.execute(f'DELETE FROM {table} WHERE document_id=?', (document_id,)).rowcount
        # Legacy review caches hold source keys without a document foreign key.
        for table, column in [('fact_definition_corrections','source_key'), ('temporal_corrections','source_key'),
                              ('fact_definition_reviews','report_json'), ('temporal_project_reviews','report_json'),
                              ('normalization_cache','result_json'), ('fact_definition_cache','result_json'),
                              ('temporal_review_cache','result_json')]:
            if table in tables:
                db.execute(f'DELETE FROM {table} WHERE instr({column},?)>0', (document_id,))
                for source_key in source_keys:
                    db.execute(f'DELETE FROM {table} WHERE instr({column},?)>0', (source_key,))
        # Cache is shared by text; invalidating it removes vectors of old revisions too.
        db.execute('DELETE FROM embedding_cache WHERE project_id=?', (project_id,))
        db.execute('DELETE FROM research_entities WHERE project_id=? AND entity_id NOT IN (SELECT entity_id FROM research_records) AND entity_id NOT IN (SELECT entity_id FROM research_document_entities)', (project_id,))
        db.execute('DELETE FROM documents WHERE project_id=? AND document_id=?', (project_id, document_id))
    # Only app-owned paths are removed. Backups and historical chat text are not ingested assets.
    paths = [store.root / doc['relative_path'], service._prepared_path(project_id, document_id),
             store.root / 'artifacts' / project_id / document_id]
    for run_id in run_ids:
        paths.extend([store.root/'exports'/project_id/run_id, store.root/'artifacts'/project_id/run_id,
                      store.root/'analysis'/run_id])
    for candidate in paths:
        target = candidate.resolve()
        if not target.is_relative_to(store.root.resolve()) or target == store.root.resolve():
            raise ValueError('document_cleanup_path_outside_data')
        if target.is_dir(): shutil.rmtree(target)
        elif target.is_file(): target.unlink()
    service._write_navigation(project_id)
    return {'document_id': document_id, 'name': doc['original_name'], 'removed': removed,
            'removed_analysis_runs': sorted(run_ids)}
