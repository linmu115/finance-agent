"""N2 pipeline adapter. Projects existing evidence; no retrieval/model calls."""
import json


PREFIXES = {'statement_analysis': 'statement', 'variance_attribution': 'variance',
            'anomaly_signals': 'signals', 'comparison': 'comparison', 'expectations': 'expectations'}
STATES = {'quantitative': 'quantified', 'qualitative': 'qualitative_disclosed', 'not_stated': 'no_statement_found'}


def enrich_workpaper_context(service, project_id, *, selection, reports, context):
    """Accept raw or compiled reports; all depth fields are JSON, not quantities.

    Repeated quoted evidence is emitted once, with all linked numeric cells.
    No-statement-found is distinct from a report that was never searched.
    """
    management = []; followups = []; constraints = []; entries = {}; links = {}
    inventory = context.get('full_tables', {}).get('tables', {})

    def table_name(kind, name):
        prefixed = PREFIXES[kind] + '_' + name
        return name if name in inventory and prefixed not in inventory else prefixed

    def cell_ref(kind, q):
        return f'{table_name(kind,q["table"])}.{q["row_key"]}.{q["column"]}'

    for kind, report in reports.items():
        for row in report.get('drivers_evidence', []):
            identifiers = []
            # A candidate quote may support several movements. Keep its original
            # business scope, and expose each association without repeating text.
            for quote in row['evidence'] or [None]:
                state = quote.get('disclosure_status', row['disclosure_status']) if quote else row['disclosure_status']
                signature = json.dumps([row['period'], state,
                                        [quote.get('document_id'),quote['page'],quote['quote']] if quote else row['driver']], ensure_ascii=False)
                if signature not in entries:
                    entry = {'id': f'management_{len(entries)+1}', 'metric': row['driver'], 'metrics': [],
                             'period': row['period'], 'linked_refs': [], 'status': STATES[state],
                             'quotes': [{k: quote[k] for k in ('document_id','page','quote','section') if k in quote}] if quote else [],
                             'quantitative_gap': {'quantitative':'仅局部原因量化，不等于完整因果桥',
                                                  'qualitative':'未拆出该原因的独立贡献金额',
                                                  'not_stated':'已解析原文未检出适用期间原因，非所有材料均未披露'}[state]}
                    if not quote:
                        entry['search_limit'] = row['search']['note']
                        if row['search']['missing_pages']: entry['missing_pages'] = row['search']['missing_pages']
                    entries[signature] = entry; management.append(entry)
                entry = entries[signature]
                if row['driver'] not in entry['metrics']: entry['metrics'].append(row['driver'])
                if quote and quote.get('relation') == 'related_driver':
                    entry['alignment_note'] = '关联驱动的原文，不直接证明该信号或阈值的成因'
                if row.get('quantity_ref'):
                    ref = cell_ref(kind, row['quantity_ref'])
                    if ref not in entry['linked_refs']: entry['linked_refs'].append(ref)
                identifiers.append(entry['id'])
            links[kind, row['key']] = identifiers
        for row in report.get('signal_followups', []):
            p = row['persistence']
            followups.append({'signal_key': row['key'],
                'signal_ref': f'{table_name(kind,row["signal_ref"]["table"])}.{row["signal_ref"]["row_key"]}',
                'management_evidence_ids': links.get((kind,row['key']), []),
                'alternatives': [{'text': r['hypothesis'], 'status': 'hypothesis', 'test': r['test']} for r in row['alternative_explanations']],
                'persistence': {'periods': p['sample_periods'], 'sample_count': p['known_sample_count'],
                                'triggered_periods': p['triggered_periods'], 'missing_periods': p['missing_periods'],
                                'allow_continuous_claim': p['allow_continuous_claim'], 'assessment': p['summary']},
                'tracking_metrics': row['tracking_metrics']})
        for row in report.get('answer_constraints', []):
            subject = row['subject']
            refs = [f'{table_name(kind,subject["table"])}.{r}.{c}' for r in subject.get('row_keys', [subject['row_key']]) for c in subject['columns']]
            constraints.append({'id': kind + ':' + row['id'], 'kind': row['code'], 'affected_refs': refs,
                'status': 'unaligned' if any(x['status']=='different' for x in row['issues']) else 'unknown',
                'reason': '；'.join(dict.fromkeys(x['detail'] for x in row['issues'])),
                'issues': row['issues'], 'record_ids': subject['record_ids'],
                'forbidden_claims': row['prohibited_uses'], 'required_qualification': row['message'], 'evidence': row['evidence']})
    searched = all('drivers_evidence' in reports.get(k, {}) for k in ('variance_attribution', 'anomaly_signals'))
    extensions = {'management_evidence': 'ready' if searched else 'partial' if management else 'pending',
                  'signal_followups': 'ready' if 'signal_followups' in reports.get('anomaly_signals', {}) else 'pending',
                  'comparability_constraints': 'ready' if any('answer_constraints' in r for r in reports.values()) else 'not_provided'}
    return {'management_evidence': management, 'signal_followups': followups,
            'comparability_constraints': constraints, 'extensions': extensions}
