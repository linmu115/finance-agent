"""Read existing evidence and unresolved issues without changing their status."""
import json

REASON_LABELS = {
    'semantic_review_pending': '复杂内容 尚未可靠提取',
    'unresolved_period': '期间 待确认',
    'unresolved_currency': '币种 待确认',
    'unstandardized_unit': '原单位 尚未标准化',
    'unclassified_data_kind': '实际值 预测 身份待确认',
    'price_eps_pe_requires_reconciliation': '股价 每股收益 市盈率 对照核验',
    'cross_market_currency_requires_confirmation': '跨市场 币种 核对',
}


def document_review(db, document, profile=None, *, include_items=True):
    did, pid = document['document_id'], document['project_id']
    # Version metadata belongs to the profile row, not its user-authored JSON.
    current_profile = db.execute('SELECT revision_id FROM document_profiles WHERE document_id=? AND project_id=?', (did,pid)).fetchone()
    revision = current_profile['revision_id'] if current_profile else None
    tables = {r['table_id']: r['page'] for r in db.execute(
        'SELECT table_id,page FROM source_tables WHERE document_id=?', (did,))}
    items, seen_tables, seen_issues = [], set(), set()

    def add(kind, message, source, **values):
        items.append({'kind': kind, 'message': message, 'source': {'document_id': did, **source}, **values})

    # A later repair supersedes the previous outcome for that table. A profile
    # change invalidates old extraction decisions, including their review state.
    for row in db.execute("""SELECT batch_key,created_at,
        json_extract(result_json,'$.script_table') table_index,
        json_extract(result_json,'$.coordinates') coordinates,
        json_extract(result_json,'$.issues') issues,
        json_extract(result_json,'$.document_sha256') source_hash,
        json_extract(result_json,'$.profile_revision') profile_revision
        FROM normalization_batches WHERE document_id=? ORDER BY created_at DESC,rowid DESC""", (did,)):
        if row['source_hash'] and row['source_hash'] != document['sha256']:
            continue
        if row['profile_revision'] and row['profile_revision'] != revision:
            continue
        issues = json.loads(row['issues'] or '[]')
        coordinates = json.loads(row['coordinates'] or '[]')
        touched = {c[0] for c in coordinates if isinstance(c, list) and c and c[0] in tables}
        if isinstance(row['table_index'], int):
            touched.add(f"{did}:t{row['table_index']}")
        touched.update(f"{did}:t{i['table']}" for i in issues if isinstance(i, dict) and isinstance(i.get('table'), int))
        current = touched - seen_tables
        seen_tables.update(touched)
        for issue in issues:
            if not isinstance(issue, dict):
                continue
            table = f"{did}:t{issue['table']}" if isinstance(issue.get('table'), int) else next(iter(current), None)
            if table and table not in current:
                continue
            key = json.dumps([table, issue], sort_keys=True, ensure_ascii=False)
            if key in seen_issues:
                continue
            seen_issues.add(key)
            source = {key: issue[key] for key in ('row', 'column') if key in issue}
            if table in tables:
                source.update(table_id=table, page=tables[table])
            elif isinstance(issue.get('page'), int):
                source['page'] = issue['page']
            add('extraction', issue.get('detail') or issue.get('note') or issue.get('reason') or '提取信息待核验',
                source, reason=issue.get('reason'), batch_key=row['batch_key'])
    extraction_count = len(items)
    pages_total = db.execute('SELECT count(*) FROM pages WHERE document_id=?', (did,)).fetchone()[0]
    page_reviews = list(db.execute("""SELECT page,review_json FROM research_page_reviews
        WHERE document_id=? AND profile_revision=? AND source_hash=? ORDER BY page""", (did, revision, document['sha256'])))
    for row in page_reviews:
        review = json.loads(row['review_json'])
        if review.get('verdict') == 'needs_review':
            add('page', review.get('note') or '本页内容尚需核验', {'page': row['page']}, reason='page_review_pending')
    page_issue_count = len(items) - extraction_count
    fact_where = " FROM current_financial_facts WHERE project_id=? AND document_id=? AND quality IN ('needs_review','conflict')"
    record_where = """ FROM research_records r LEFT JOIN document_profiles p USING(document_id)
        WHERE r.project_id=? AND r.document_id=? AND r.is_current=1
        AND (r.profile_revision IS NULL OR r.profile_revision=p.revision_id)
        AND json_extract(r.record_json,'$.quality') IN ('needs_review','conflict')"""
    args = (pid, did)
    fact_count = db.execute('SELECT count(*)' + fact_where, args).fetchone()[0]
    record_count = db.execute('SELECT count(*)' + record_where, args).fetchone()[0]
    if include_items:
        for row in db.execute('SELECT fact_id,metric,value,raw_value,raw_unit,quality,source_json' + fact_where + ' ORDER BY fact_id', args):
            source = json.loads(row['source_json']); meta = source.get('normalization', {})
            warnings = meta.get('review_warnings') or []
            add('fact', '；'.join(map(str, warnings)) or meta.get('semantic_review_note') or '所用期间、单位或口径需核对原文',
                {key: source[key] for key in ('page', 'table_id', 'row', 'column', 'source_id') if key in source},
                fact_id=row['fact_id'], label=meta.get('label') or row['metric'], value=row['value'],
                raw_value=row['raw_value'], raw_unit=row['raw_unit'], quality=row['quality'])
        for row in db.execute('SELECT r.record_id,r.record_json,r.source_json' + record_where + ' ORDER BY r.record_id', args):
            record, source = json.loads(row['record_json']), json.loads(row['source_json'])
            warnings = source.get('normalization', {}).get('review_warnings') or []
            add('research_record', '；'.join(map(str, warnings)) or '记录原值保留，需按本次任务所需口径复核',
                {key: source[key] for key in ('page', 'table_id', 'row', 'column', 'quote') if key in source},
                record_id=row['record_id'], label=record.get('label') or record.get('text'),
                value=record.get('value'), raw_value=record.get('raw_value'), raw_unit=record.get('raw_unit'),
                data_kind=record.get('data_kind'), quality=record.get('quality'))
    summary = {'extraction_issues': extraction_count, 'page_issues': page_issue_count,
               'facts_needing_review': fact_count, 'records_needing_review': record_count,
               'pages_preserved': pages_total, 'tables_preserved': len(tables),
               'tables_with_decisions': len(seen_tables.intersection(tables)),
               'pages_with_decisions': len(page_reviews),
               'review_items': extraction_count + page_issue_count + fact_count + record_count}
    return {'summary': summary, 'items': items if include_items else []}


def review_details(store, project_id, document_id, query=None, offset=0, limit=20, table_id=None):
    document = store.document(project_id, document_id)
    with store.connect() as db:
        db.execute('BEGIN')
        row = db.execute('SELECT profile_json FROM document_profiles WHERE document_id=?', (document_id,)).fetchone()
        review = document_review(db, document, json.loads(row[0]) if row else None)
    items = review['items']
    if table_id:
        items = [item for item in items if item['source'].get('table_id') == table_id]
    terms = str(query or '').casefold().split()
    if terms:
        def matches(item):
            text = json.dumps(item, ensure_ascii=False).casefold()
            text += ' ' + ' '.join(label for code, label in REASON_LABELS.items() if code in text)
            return all(term in text for term in terms)
        items = [item for item in items if matches(item)]
    total = len(items)
    offset, limit = max(0, int(offset)), max(1, min(100, int(limit)))
    return {'document_id': document_id, 'document_name': document['original_name'], **review,
            'items': items[offset:offset+limit], 'total': total, 'offset': offset, 'limit': limit,
            'next_offset': offset+limit if offset+limit < total else None,
            'scope': 'stored evidence and current unresolved issues; not an accuracy score'}
