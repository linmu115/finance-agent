"""Workpaper selection and read-through of disclosed standard statement cells.

No facts are written. Document profiles select issuers, not fuzzy name scores;
the ingestion mapper supplies exact labels, units, periods and coordinates.
"""
import json
import re
from collections import defaultdict

from .workpaper_period_selection import WorkpaperInputError, normalize_period_records


def metadata(record):
    return record.get('source_ref', {}).get('normalization', {})


def scope_matches(actual, requested):
    return actual == requested or actual.startswith(requested + '_')


def candidates(project, facts, documents, kind='statement_analysis'):
    groups = defaultdict(list)
    for r in facts:
        groups[(r['company'], r['document_id'], r['scope'])].append(r)
    for did, doc in documents.items():
        if not any(key[1] == did for key in groups):
            groups[(doc['company'], did, 'consolidated')] = []
    result = []
    for (company, did, scope), rows in sorted(groups.items()):
        periods = sorted({r['period'] for r in rows if re.fullmatch(r'\d{4}-(?:FY|H[12]|9M|Q[1-4])', r['period'])
                          and not metadata(r).get('period_error')})
        args = {'project_id': project, 'kind': kind, 'document_id': did, 'company': company, 'scope': scope}
        if periods: args['periods'] = periods
        result.append({'company': company, 'document_id': did, 'report': documents.get(did, {}).get('original_name'),
                       'scope': scope, 'fact_count': len(rows), 'available_periods': periods,
                       'currencies': sorted({r['currency'] for r in rows}),
                       'original_period_labels': sorted({metadata(r).get('record_period', r['period']) for r in rows}),
                       'retry': {'tool': 'financial_workpaper', 'arguments': args,
                                 'call': 'financial_workpaper(' + json.dumps(args, ensure_ascii=False) + ')'}})
    return result


def selection_error(reason, project, facts, documents, diagnostics=()):
    choices = candidates(project, facts, documents)
    raise WorkpaperInputError(reason, selection={'reason': reason, 'candidates': choices,
        'retry_calls': [c['retry'] for c in choices], 'source_gaps': list(diagnostics)})


def read_standard_tables(service, project, doc, company, existing):
    """Reuse the deterministic ingestion mapper; read only core statements.

    Presence of structured notes does not substitute for a missing statement
    row. Existing statement facts win per semantic identity, including version.
    """
    from . import cleaning_rules
    from .accounting_basis import identify
    from .semantic import materialize
    from .source_semantics import apply_source_semantics
    from .source_dimensions import apply_source_dimensions
    from .standard_metrics import workpaper_concepts, canonical_rows
    did = doc['document_id']
    with service.store.connect() as db:
        pages = [dict(r) for r in db.execute('SELECT page,text FROM pages WHERE document_id=? ORDER BY page', (did,))]
        tables = [dict(r) for r in db.execute('SELECT * FROM source_tables WHERE document_id=? ORDER BY page,table_id', (did,))]
        prepared = db.execute('SELECT prepared_json FROM prepared_documents WHERE document_id=?', (did,)).fetchone()
    if prepared:
        geometry = {p['page']: p.get('words', []) for p in json.loads(prepared[0])['pages']}
        pages = [p | {'words': geometry.get(p['page'], [])} for p in pages]
    if not tables: return [], [{'reason': '没有可直读的标准报表原表', 'document_id': did}], None
    parsed = {'pages': pages, 'report_year': doc.get('report_year'), 'tables': [
        {'index': int(t['table_id'].rsplit(':t', 1)[1]), 'page': t['page'], 'rows': json.loads(t['rows_json']),
         'bbox': json.loads(t['bbox_json']) if t['bbox_json'] else None,
         'cells': json.loads(t['cells_json']) if t['cells_json'] else {}} for t in tables]}
    parsed['tables'].sort(key=lambda t: t['index'])
    basis = identify(parsed)
    added, gaps = [], []
    def identity(r):
        n = metadata(r)
        return (tuple(workpaper_concepts(r['metric'])) or (r['metric'],), r['period'], r['scope'], r['currency'],
                n.get('statement'), n.get('restatement', 'original'), json.dumps(n.get('dimensions', {}), sort_keys=True))
    known = {identity(r) for r in existing}
    def cell_key(ref):
        span = ref.get('normalization', {}).get('numeric_span', {})
        return (ref.get('table_id'), ref.get('row'), ref.get('column'), span.get('start'), span.get('end'))
    known_cells = {cell_key(r['source_ref'])
                   for r in existing if metadata(r).get('statement') in ('income', 'cashflow', 'balance') and not metadata(r).get('period_error')}
    known_positions = {key[:3] for key in known_cells}
    for t in parsed['tables']:
        ctx = cleaning_rules.context(parsed, t)
        if ctx['statement'] not in ('income', 'cashflow', 'balance') or ctx['scope'] == 'unspecified': continue
        item = cleaning_rules.draft(parsed, t, company, basis)
        locator = {'document_id': did, 'page': t['page'], 'table_id': f"{did}:t{t['index']}", 'scope': ctx['scope']}
        if not item or item.get('mapping_error'):
            gaps.append(locator | {'reason': '原表单位或期间列无法确定', 'detail': (item or {}).get('mapping_error')}); continue
        schema = item['schema']
        headers = cleaning_rules.mapping_headers(t)
        columns = json.loads(schema['columns_json'])
        previous = None
        for c in columns:
            header = ' '.join(row[c['column'] - 1] for row in headers if len(row) >= c['column'])
            if c['period'] == 'unknown' and previous and c['column'] == previous['column'] + 1:
                if re.search(r'调整后|重述后', header) and re.search(r'调整前|重述前', previous['label']):
                    c.update({k: previous[k] for k in ('period', 'start', 'end') if k in previous})
            if re.search(r'调整后|重述|restated|adjusted', header, re.I) and not re.search(r'调整前|unadjusted|before', header, re.I):
                c['version'] = 'restated'
            c['label'] = header
            previous = c
        schema['columns_json'] = json.dumps(columns, ensure_ascii=False)
        if any('\n' in str(row[0]) for row in t['rows']):
            from .workpaper_table_geometry import geometry_rows
            mapped_cells = {(r['row'], c['column'], c.get('numeric_span', {}).get('start')) for r in item['rows']
                            for c in json.loads(r['attributes'].get('columns_json', schema['columns_json']))}
            for row in geometry_rows(parsed, t, schema):
                cs = [c for c in json.loads(row['attributes']['columns_json'])
                      if (row['row'], c['column'], c.get('numeric_span', {}).get('start')) not in mapped_cells]
                if cs:
                    row['attributes']['columns_json'] = json.dumps(cs, ensure_ascii=False)
                    item['rows'].append(row)
        ext = [{'class': 'table_schema', 'text': f"[[T{t['index']}]]", 'span': [0, 1], 'attributes': schema}]
        for r in canonical_rows(t, item['rows'], 1, ctx['statement'], schema, ctx['topic']):
            ext.append({'class': 'financial_row', 'text': f"[[T{t['index']}:R{r['row']}]]", 'span': [0, 1], 'attributes': r['attributes']})
        raw, issues = materialize(ext, [{'table': t, 'rows': list(range(1, len(t['rows']) + 1))}], did, 'deterministic-table-read')
        geometry_sources = {(r['row'], c['column'], c.get('numeric_span', {}).get('start')): c['source_geometry']
                            for r in item['rows'] for c in json.loads(r['attributes'].get('columns_json', '[]')) if c.get('source_geometry')}
        apply_source_dimensions(t, raw, context=ctx)
        apply_source_semantics(parsed, t, raw, ctx)
        for issue in issues:
            if (locator['table_id'], issue.get('row'), issue.get('column')) in known_positions: continue
            if not issue.get('column') and any(tid == locator['table_id'] and row == issue.get('row') for tid, row, _ in known_positions): continue
            gaps.append(locator | issue | ({'source_row': t['rows'][issue['row'] - 1]} if issue.get('row') else {}))
        for f in raw:
            ref = f.pop('source'); n = ref['normalization']
            geometry_source = geometry_sources.get((ref['row'], ref['column'], n.get('numeric_span', {}).get('start')))
            if geometry_source: ref['label_alignment'] = geometry_source
            key = cell_key(ref)
            if key in known_cells or key[:3] + (None, None) in known_cells: continue
            f.update(document_id=did, project_id=project, source_ref=ref, quality='source_table_read',
                     # This is a transient source-cell ID, not an inserted DB fact.
                     fact_id=f"table-read:{did}:{t['index']}:{ref['row']}:{ref['column']}",
                     dimensions=n.get('dimensions', {}), data_kind='disclosed_actual')
            ref['source_method'] = '原表直读'
            n['engine'] = 'workpaper-table-read-v1'
            if f['period'] == 'unknown':
                gaps.append(locator | {'row': ref['row'], 'column': ref['column'], 'reason': '原表期间未识别'}); continue
            f = normalize_period_records([f])[0]
            if identity(f) not in known: added.append(f)
    return added, gaps, basis


def prepare_statement(service, project, facts, scope, document_id=None, company=None):
    facts = normalize_period_records(facts)
    doc_ids = {r['document_id'] for r in facts} | ({document_id} if document_id else set())
    documents, profiles = {}, {}
    with service.store.connect() as db:
        if not doc_ids:
            query = 'SELECT document_id FROM documents WHERE project_id=?'
            args = [project]
            if company: query += ' AND company LIKE ?'; args.append('%' + company + '%')
            doc_ids = {r[0] for r in db.execute(query, args)}
        for did in doc_ids:
            row = db.execute('SELECT * FROM documents WHERE project_id=? AND document_id=?', (project, did)).fetchone()
            if row: documents[did] = dict(row)
            profile = db.execute('SELECT profile_json FROM document_profiles WHERE project_id=? AND document_id=?', (project, did)).fetchone()
            if profile: profiles[did] = json.loads(profile[0])
    basis = []
    # A document's issuer applies only within that document. A+H frameworks
    # remain separate scopes; a parent company's report is not a group alias.
    selected = []
    for did in doc_ids:
        rows = [r for r in facts if r['document_id'] == did]
        profile = profiles.get(did, {})
        issuer = profile.get('publisher') if profile.get('kind') == 'financial_report' else None
        names = {issuer} if issuer else set()
        for entity in profile.get('entities', []):
            if issuer in [entity['name'], *entity.get('aliases', [])]: names.update([entity['name'], *entity.get('aliases', [])])
        grounded = {r['company'] for r in rows if r['company'] in names}
        if len(grounded) == 1:
            chosen = next(iter(grounded)); rows = [r for r in rows if r['company'] == chosen]
            basis.append({'rule': 'document_profile_issuer', 'document_id': did, 'company': chosen,
                          'evidence': [e for e in profile.get('evidence', []) if e.get('field') == 'publisher']})
        elif len({r['company'] for r in rows}) > 1 and documents.get(did, {}).get('company') in {r['company'] for r in rows}:
            chosen = documents[did]['company']; rows = [r for r in rows if r['company'] == chosen]
            basis.append({'rule': 'document_report_subject', 'document_id': did, 'company': chosen})
        selected.extend(rows)
    scoped = [r for r in selected if scope_matches(r['scope'], scope)]
    companies = {r['company'] for r in scoped}
    if len(companies) > 1: selection_error('主体定位不唯一；请选择候选主体/报告', project, facts, documents)
    docs = {r['document_id'] for r in scoped} or doc_ids
    if len(docs) > 1:
        ends = {did: max((metadata(r).get('period_end', '') for r in scoped if r['document_id'] == did), default='') for did in docs}
        newest = max(ends.values())
        docs = {did for did in docs if newest and ends[did] == newest}
        if len(docs) != 1: selection_error('同一最新期有多份资料；请选择报告及会计口径', project, facts, documents)
        basis.append({'rule': 'latest_report_with_own_comparatives', 'document_id': next(iter(docs))})
    if len(docs) != 1: selection_error('未找到主体资料；请指定报告', project, facts, documents)
    did = next(iter(docs)); scoped = [r for r in scoped if r['document_id'] == did]
    issuer = next(iter(companies)) if companies else documents.get(did, {}).get('company')
    gaps, extra = [], []
    if did in documents and issuer:
        extra, gaps, framework = read_standard_tables(service, project, documents[did], issuer, scoped)
        if extra and framework and framework['status'] == 'identified':
            # This is one physical report: its stated framework outranks stale
            # fact annotations. Reconcile metadata in this read-only view only.
            changed = []
            for i, r in enumerate(scoped):
                resolved = re.sub(r'_(?:CAS|IFRS|HKFRS|unknown)$', '_' + framework['basis'], r['scope'])
                if resolved != r['scope']:
                    changed.append(r['scope'])
                    scoped[i] = r | {'scope': resolved, 'source_ref': r['source_ref'] | {'normalization': metadata(r) | {'record_scope': r['scope'], 'scope_resolution': 'report_framework'}}}
            if changed: basis.append({'rule': 'report_framework_over_record_annotation', 'previous_scopes': sorted(set(changed)),
                                      'framework': framework['basis'], 'evidence': framework['evidence'], 'database_changed': False})
            if changed and not all(scope_matches(r['scope'], scope) for r in scoped):
                selection_error('请求会计口径与报告原文不一致；请选择报告披露的口径', project, scoped + extra, documents, gaps)
        scoped.extend(r for r in extra if scope_matches(r['scope'], scope))
        gaps = [g for g in gaps if not g.get('scope') or scope_matches(scope, g['scope'])]
    gaps.extend({'document_id': r['document_id'], 'table_id': r['source_ref'].get('table_id'),
                 'row': r['source_ref'].get('row'), 'column': r['source_ref'].get('column'),
                 'original_period': r['period'], 'reason': metadata(r)['period_error']}
                for r in scoped if metadata(r).get('period_error'))
    if not scoped: selection_error('当前口径无可计算来源；请选择已有口径或补齐原表', project, facts + extra, documents, gaps)
    direct = [r for r in scoped if r.get('quality') == 'source_table_read']
    if direct: basis.append({'rule': 'source_table_read', 'label': '来源：原表直读', 'cells': len(direct),
                             'pages': sorted({r['source_ref']['page'] for r in direct})})
    if any(metadata(r).get('restatement') in ('restated', 'adjusted') for r in scoped):
        basis.append({'rule': 'explicit_restated_comparative_preferred',
                      'reason': '同一报告同期间优先显式调整后列；原报数保留，逐格来源记录原列和重述状态'})
    basis.append({'rule': 'requested_scope', 'scope': scope, 'reason': '默认合并口径优先；不混入母公司报表'})
    return scoped, {'company': issuer, 'document_id': did, 'scope': scope, 'basis': basis}, gaps, documents

