"""Public document availability from submitted tables, separate from run failure."""


def describe_availability(document, processing_states, batches):
    did = document['document_id']
    candidates = [(state, d) for state in processing_states if state.get('mode') == 'script_cleaning'
                  for d in state.get('documents', []) if d['document_id'] == did]
    if not candidates:
        return document
    # Match the cleaner: oldest unfinished attempt, otherwise oldest attempt.
    # Receipts are independent, so stale checkpoint counts cannot erase commits.
    unfinished = [(s, d) for s, d in candidates if s.get('state') not in {'completed', 'needs_review'}
                  or any(set(x['tables']) - set(x['completed_tables']) for x in s['documents'])]
    state, part = (unfinished or candidates)[0]
    tables = set(part['tables'])
    core = set(part.get('core_tables', []))
    statuses = {}
    for batch in batches:
        index = batch.get('script_table')
        if (index in tables and not batch.get('superseded_by')
                and batch.get('document_sha256') == document['sha256']
                and batch.get('profile_revision') == part.get('profile_revision')):
            statuses[index] = batch['status']
    completed = {i for i, status in statuses.items() if status in {'completed', 'needs_review'}}
    deferred = {int(i) for i in (part.get('deferred_tables') or {})} & tables - completed
    pending = tables - completed - deferred
    core_complete = bool(core) and core <= completed
    core_text = '核心表已完成' if core_complete else f'核心表 {len(core & completed)}/{len(core)} 已完成' if core else '核心集合尚未判定'
    label = f'{core_text} / {len(pending)} 张待处理 / {len(deferred)} 张搁置'
    text = part.get('text_coverage') or {}
    pages, reviewed = text.get('pages_total', 0), text.get('pages_reviewed', 0)
    if pages:
        label += f' / 正文 {reviewed}/{pages} 页'
    available = bool(completed or document.get('fact_count') or document.get('research_record_count'))
    complete = bool(tables or pages) and tables <= completed and reviewed == pages
    needs_review = any(status == 'needs_review' for status in statuses.values()) or bool(text.get('review_issues'))
    raw_state = document['state']
    public_state = ('needs_review' if needs_review else 'ready') if complete else raw_state if raw_state in {'normalizing', 'parsing', 'validating'} else 'partial' if available else raw_state
    return {**document, 'state': public_state, 'processing_state': raw_state, 'status_label': label,
            'ingestion': {'availability': 'complete' if complete else 'partial' if available else 'sources_only',
                          'analysis_available': available, 'tables_total': len(tables),
                          'tables_completed': len(completed), 'tables_pending': len(pending),
                          'tables_deferred': len(deferred), 'core_complete': core_complete,
                          'processing_id': state['processing_id'],
                          'detail_tool': 'get_processing_checkpoint',
                          'note': '已提交资料可用于分析；未入库或搁置部分不能当作已披露数据。'}}
