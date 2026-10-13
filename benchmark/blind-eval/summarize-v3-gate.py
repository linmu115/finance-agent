"""Offline F202 gate report, after both original review files have been sealed."""
import argparse
import hashlib
import statistics
from collections import Counter
from pathlib import Path
from blind import read, dump, output
from metrics import DIMS, stability, summarize


def main(study, packet):
    study, packet = output(study), output(packet)
    state = read(study / 'experiment.json')
    assert len(state['runs']) == 18
    assert all(r['status'] in {'completed', 'failed', 'cancelled'} for r in state['runs'])
    seal = read(packet / 'score-seal.json')
    for item in seal['reviews']:
        assert hashlib.sha256((packet / item['path']).read_bytes()).hexdigest() == item['sha256']
    stable = stability(packet)
    stable['purpose'] = 'approved_18_turn_engineering_gate'
    dump(study / 'review-stability.json', stable)
    identities = {r['case_id']: r for r in read(packet / 'private-map.json')['cases']}
    usage = summarize(study)
    dump(study / 'usage.json', usage)
    # Reviewed grouping of indices only; never rewrites either judge's scores/defects.
    # Separate versions of the same underlying defect count once within a case.
    dedup = read(study / 'defect-deduplication.json')
    passes = []
    for rd in ['round1', 'round2']:
        mapping = read(packet / f'private-{rd}-map.json')
        reviews = read(packet / rd / 'review.json')['reviews']
        rows = []
        for r in reviews:
            ident = identities[mapping[r['case_id']]]
            groups = dedup[rd][ident['label']]['groups']
            assert sorted(i for g in groups for i in g) == list(range(len(r['material_defects'])))
            assert all(groups)
            rows.append({**r, **{k:ident[k] for k in ['label','profile','task']},
                         'deduplicated_material_entries':len(groups)})
        dump(study / f'{rd}-decoded.json', {'rows':rows})
        stats = {}
        for profile in state['config']['arms']:
            group = [r for r in rows if r['profile'] == profile]
            stats[profile] = {
                'cases':len(group),
                'material_defective_cases':sum(bool(r['material_defects']) for r in group),
                'raw_material_entries':sum(len(r['material_defects']) for r in group),
                'deduplicated_material_entries':sum(r['deduplicated_material_entries'] for r in group),
                'scores':{k:statistics.mean(v) if (v := [r['scores'][k] for r in group if r['scores'][k] is not None]) else None for k in DIMS},
                'R3_mean':statistics.mean(r['scores']['explanation'] for r in group),
                'R5_primary_mean':statistics.mean(r['scores']['anomalies'] for r in group if r['task'] in ['D1','X3']),
                'R5_auxiliary_X7_mean':statistics.mean(r['scores']['anomalies'] for r in group if r['task']=='X7'),
                'unreviewed':[{ 'label':r['label'],'items':r['unreviewed']} for r in group if r.get('unreviewed')],
            }
        p, f = stats['prepared'], stats['financial']
        checks = {
            'material_cases':None if p['material_defective_cases'] <= 1 else
                f['material_defective_cases'] <= p['material_defective_cases']-2 and f['material_defective_cases'] <= .5*p['material_defective_cases'],
            'deduplicated_entries':f['deduplicated_material_entries'] <= p['deduplicated_material_entries'],
            'R3':f['R3_mean'] >= p['R3_mean'],
            'R5_primary':f['R5_primary_mean'] >= p['R5_primary_mean'],
            'complete_review':not any(g['unreviewed'] for g in stats.values()),
        }
        passes.append({'round':rd,'groups':stats,'checks':checks,
                       'floor_effect':p['material_defective_cases']<=1})
    costs = {}
    for profile in state['config']['arms']:
        rows = [r for r in usage['rows'] if r['profile']==profile]
        costs[profile] = {'attempts':len(rows),'completed':sum(r['status']=='completed' for r in rows),
            'failure_classes':dict(Counter(r['failureClass'] for r in state['runs'] if r['profile']==profile and r.get('failureClass'))),
            'elapsed_seconds_median':statistics.median(r['elapsed_seconds'] for r in rows),
            'input_median':statistics.median(r['usage']['input'] for r in rows) if all(r.get('usage') and r['usage'].get('input') is not None for r in rows) else None,
            'provider_billed_cost':None}
        for k in ['calls','input','output','uncachedInput','cacheRead','cacheWrite','reasoning','unknownCalls']:
            vals = [r['usage'].get(k) if r.get('usage') else None for r in rows]
            costs[profile][k] = {'known_sum':sum(v for v in vals if v is not None) if any(v is not None for v in vals) else None,
                                 'missing_attempts':sum(v is None for v in vals)}
    p, f = costs['prepared'], costs['financial']
    pairs_complete = all(g['completed']==6 and not g['unknownCalls']['missing_attempts'] and g['unknownCalls']['known_sum']==0 and not g['input']['missing_attempts'] for g in [p,f])
    shared = {
        'completion':f['completed']>=p['completed'],
        'input_total':f['input']['known_sum']<=p['input']['known_sum'] if pairs_complete else None,
        'input_paired_median':f['input_median']<=p['input_median'] if pairs_complete else None,
        'zero_product_failures_all_arms':not any(r.get('failureClass')=='product' for r in state['runs']),
        'failure_classification_complete':not any(r.get('failureClass') in ['unclassified','cancelled','resource_limit'] for r in state['runs']),
        'review_stability':stable['stable_by_preregistered_threshold'],
    }
    all_checks = [*shared.values(),*[v for p in passes for v in p['checks'].values()]]
    conclusion = 'failed' if False in all_checks else 'inconclusive' if None in all_checks else 'passed'
    result = {'version':state['freeze']['version'],'commit':state['freeze']['commit'],
        'conclusion':conclusion,'shared_checks':shared,'passes':passes,'usage_by_arm':costs,
        'cost_pairs_complete':pairs_complete,'latency_is_isolated':False,
        'limits':['18-turn engineering gate; no formal held-out superiority claim',
                  'Known input is a lower bound if unknown calls exist; no shortened-failure cost advantage',
                  'Preparation and judging excluded from participant analysis; actual CPA bills unknown',
                  'Reasoning is an output subclass, not added twice; concurrency and independent ingestion affect elapsed time']}
    dump(study/'gate-result.json',result)
    print(conclusion)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('study');parser.add_argument('packet')
    args=parser.parse_args();main(args.study,args.packet)
