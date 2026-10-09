"""Descriptive delivery/replay/numeric coverage, without reading any judge score."""
import argparse
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from blind import read, dump, output


def summarize(study):
    state = read(study/'experiment.json')
    delivery = {r['label']: r for r in read(study/'delivery-observations.json')['rows']}
    replay = read(study/'replay-results.json')
    bundles = read(study/'bundle-replay-results.json')
    rows = []
    for run in state['runs']:
        label = run['label']
        d = delivery.get(label)
        analysis = [r for r in replay if r['label'] == label]
        model = [r for r in bundles if r['label'] == label]
        path = study/(label+'-gold-numeric.json')
        n = read(path) if path.exists() else None
        rows.append({'label':label, 'task':run['taskId'], 'split':run['split'],
            'profile':run['profile'], 'status':run['status'],
            'delivery_collected':bool(d and d['delivery_observation']=='collected'),
            'downloaded':d.get('downloaded') if d else None,
            'download_failed':d.get('download_failed') if d else None,
            'a5_observed':bool(d and d.get('a5')),
            'a5_raw_issue_count':d['a5']['issue_count'] if d and d.get('a5') else None,
            'analysis_versions_replayed':len(analysis),
            'analysis_replay_statuses':dict(Counter(r['status'] for r in analysis)),
            'analysis_byte_mismatches':sum(not c['matches'] for r in analysis for c in r['checks']),
            'model_bundles_replayed':len(model),
            'model_bundle_statuses':dict(Counter(r['status'] for r in model)),
            'numeric_binding_record':n is not None,
            'numeric_explicit_cells':len(n['checks']) if n else None,
            'numeric_bound_unique_keys':len({c['key'] for c in n['checks']}) if n else None,
            'numeric_statuses':dict(Counter(c['status'] for c in n['checks'])) if n else None,
            'numeric_scope':n.get('scope') if n else 'No binding observation recorded yet; unknown.'})
    groups = []
    for split in ['development','heldout','extension']:
        for profile in ['original_pi','prepared','financial']:
            group = [r for r in rows if r['split']==split and r['profile']==profile]
            status = Counter(); numeric = Counter(); bundle_status = Counter()
            for r in group:
                status.update(r['analysis_replay_statuses'])
                numeric.update(r['numeric_statuses'] or {})
                bundle_status.update(r['model_bundle_statuses'])
            groups.append({'split':split,'profile':profile,'planned_positions':len(group),
                'terminal_positions':sum(r['status'] in {'completed','failed','cancelled','blocked_dependency'} for r in group),
                'collected_positions':sum(r['delivery_collected'] for r in group),
                'downloaded_artifact_links':sum(r['downloaded'] or 0 for r in group),
                'failed_artifact_links':sum(r['download_failed'] or 0 for r in group),
                'a5_observed_positions':sum(r['a5_observed'] for r in group),
                'a5_observed_raw_issues':sum(r['a5_raw_issue_count'] or 0 for r in group),
                'analysis_versions_replayed':sum(r['analysis_versions_replayed'] for r in group),
                'analysis_replay_statuses':dict(status),
                'model_bundles_replayed':sum(r['model_bundles_replayed'] for r in group),
                'model_bundle_statuses':dict(bundle_status),
                'numeric_positions_with_bindings':sum(bool(r['numeric_explicit_cells']) for r in group),
                'numeric_positions_without_bindings':sum(not r['numeric_explicit_cells'] for r in group),
                'numeric_explicit_cells':sum(r['numeric_explicit_cells'] or 0 for r in group),
                'numeric_observation_statuses':dict(numeric)})
    return {'at':datetime.now(timezone.utc).isoformat(),'rows':rows,'groups':groups,
        'scope':'Descriptive only; does not enter E4, reviewer defect counts or reliability.',
        'limitations':['Zero observed events in an unobserved position is not a successful check; coverage denominators are provided.',
            'Repeated delivered versions are retained; raw tool flags and cell counts are not deduplicated defect counts.',
            'Numerical bindings cover only explicit evaluator-inspected locations and units; no keyword or matching-value scanner.',
            'Unknown/unbound values are not passes. Independent reviews assess semantics, explanations, all still-delivered versions and unreviewed material.',
            'Successful sandbox execution or matching bytes does not establish financial correctness.',
            'ZIP member equivalence and XLSX metadata differences are explained separately in the private replay-equivalence.json.',
            'First correct/usable financial delivery time was not observed; elapsed time is non-isolated.']}


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('study');args=parser.parse_args()
    study=output(args.study);result=summarize(study)
    dump(study/'delivery-supplement.json',result)
    print({'positions':len(result['rows']),'groups':len(result['groups']),'judge_scores_read':False})
