"""Accounting basis is source metadata, not a model's default scope suffix."""
import re

VERSION = 'accounting-basis-1'
PATTERNS = {
    'CAS': r'企业会计准则|企業會計準則|Accounting Standards for Business Enterprises',
    'HKFRS': r'HKFRS|Hong Kong Financial Reporting Standards|香港財務報告準則|香港财务报告准则',
    'IFRS': r'IFRS|International Financial Reporting Standards|国际财务报告准则|國際財務報告準則',
}


def identify(parsed):
    evidence = []
    for page in parsed['pages']:
        text = page['text']
        for basis, pattern in PATTERNS.items():
            match = re.search(pattern, text, re.I)
            if match:
                # The source quote is kept in this document's profile, never in
                # the shared cleaning rule library.
                start = max(text.rfind('\n', 0, match.start()), text.rfind('。', 0, match.start())) + 1
                end = text.find('。', match.end())
                if end < 0: end = text.find('\n', match.end())
                evidence.append({'basis': basis, 'page': page['page'], 'quote': text[start:end+1 if end >= 0 else len(text)].strip()})
    kinds = {e['basis'] for e in evidence}
    return {'basis': next(iter(kinds)) if len(kinds) == 1 else 'unknown',
            'status': 'identified' if len(kinds) == 1 else 'conflicting' if kinds else 'missing',
            'evidence': evidence, 'version': VERSION}


def resolve(parsed, supplied=None):
    result = identify(parsed)
    if not supplied or supplied.get('basis') == result['basis']: return result
    from .research_ingestion import grounded_quote
    basis = supplied.get('basis')
    if basis not in PATTERNS: raise ValueError('unsupported_accounting_basis')
    proof = grounded_quote(parsed, supplied.get('evidence'))
    if not re.search(PATTERNS[basis], proof['quote'], re.I):
        raise ValueError('accounting_basis_not_supported_by_quote')
    return {'basis': basis, 'status': 'source_override', 'evidence': [proof], 'version': VERSION}


def apply_basis(item, basis):
    """Preserve consolidation scope; replace only the accounting framework."""
    import json
    item = json.loads(json.dumps(item))
    framework = basis['basis']
    def fix(attrs):
        scope = attrs.get('scope')
        if scope and framework != 'unknown':
            attrs['scope'] = re.sub(r'_(?:IFRS|HKFRS|CAS|unknown)$', '', scope, flags=re.I) + '_' + framework
        elif scope and re.search(r'_(?:IFRS|HKFRS|CAS)$', scope, re.I):
            # A document with no basis evidence cannot acquire IFRS from an
            # example script. Keep the actual consolidation interpretation.
            attrs['scope'] = re.sub(r'_(?:IFRS|HKFRS|CAS)$', '_unknown', scope, flags=re.I)
        columns = attrs.get('columns_json')
        if columns:
            decoded = json.loads(columns) if isinstance(columns, str) else columns
            for col in decoded: fix(col)
            attrs['columns_json'] = json.dumps(decoded, ensure_ascii=False)
    fix(item.get('schema', {}))
    for row in item.get('rows', []): fix(row['attributes'])
    return item


def reapply_document_facts(service, project_id, document_id, parsed, basis, processing_id):
    """Version existing interpretations; original values and source cells stay intact."""
    import json
    import uuid
    from .store import dumps, utcnow
    from .table_identity import table_index
    from .source_dimensions import apply_source_dimensions
    from .cleaning_rules import context
    changed=[]
    with service.store.connect(write=True) as db:
        records=[dict(r) for r in db.execute('SELECT * FROM facts WHERE project_id=? AND document_id=?',(project_id,document_id))]
        facts=[r|{'source':json.loads(r['source_json'])} for r in records]
        for f in facts:f['source'].setdefault('normalization',{})
        for table in parsed['tables']:
            local=[f for f in facts if table_index(f['source'].get('table_id'),document_id)==table['index'] and
                   isinstance(f['source'].get('row'),int) and 1<=f['source']['row']<=len(table['rows'])]
            if local:apply_source_dimensions(table,local,context=context(parsed,table))
        for old,fact in zip(records,facts):
            meta=fact['source']['normalization']
            if basis['basis']!='unknown':
                fact['scope']=apply_basis({'schema':{'scope':fact['scope']}},basis)['schema']['scope']
                meta['accounting_basis']={k:basis[k] for k in ('basis','version','status')}
            if old['scope']==fact['scope'] and json.loads(old['source_json'])==fact['source']:continue
            db.execute('INSERT INTO fact_history VALUES(?,?,?,?,?,?)',(uuid.uuid4().hex,project_id,document_id,processing_id,dumps(old),utcnow()))
            meta['document_semantics_revision']={'processing_id':processing_id,'reason':'source_basis_and_dimensions','basis_evidence':basis['evidence']}
            db.execute('UPDATE facts SET scope=?,source_json=? WHERE fact_id=?',(fact['scope'],dumps(fact['source']),old['fact_id']))
            changed.append(old['fact_id'])
    return {'updated':len(changed),'history_preserved':len(changed)}
