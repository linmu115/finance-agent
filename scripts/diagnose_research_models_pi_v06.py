"""Read-only v06 verification against independent, pre-existing Fraction references.

The 161 rational reference values were computed from frozen synthetic assumptions
by diagnose_research_models_pi_v05.py before this v06 run. This script imports no
production calculation code and makes no network/model/database calls.
"""
from pathlib import Path
from fractions import Fraction
from decimal import Decimal, localcontext
import hashlib
import json


ROOT = Path(__file__).resolve().parents[1]
FOLDER = ROOT / 'benchmark/results'


def read(name):
    return json.loads((FOLDER / name).read_text(encoding='utf-8-sig'))


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    original_path = FOLDER / 'research-models-pi-workflow-v06.json'
    original_hash = digest(original_path)
    report = read(original_path.name)
    prior = read('research-models-pi-workflow-v05.diagnosis.json')
    before = read('research-models-pi-workflow-v06.before.json')
    prior_before = read('research-models-pi-workflow-v05.before.json')
    assert before['assumptions'] == prior_before['assumptions']
    assert report['status'] in ('passed', 'failed')
    artifacts = {a['kind']: a for a in report['artifacts_before']}
    scenario, dcf = artifacts['manufacturing_scenario'], artifacts['dcf']
    roots = {'scenario': scenario['result'], 'original': scenario['result'],
             'dcf': dcf['result'], 'edited': report['host_edit']['result']}
    calculations = []
    with localcontext() as context:
        context.prec = 65
        for old in prior['independent_arithmetic']['checks']:
            parts = old['path'].split('.')
            current = roots[parts[0]]
            for part in parts[1:]:
                current = current[int(part)] if isinstance(current, list) else current[part]
            value = Fraction(old['reference_fraction'])
            reference = Decimal(value.numerator) / Decimal(value.denominator)
            error = abs(Decimal(str(current)) - reference)
            calculations.append({'path': old['path'], 'actual': str(current),
                                 'reference_fraction': str(value), 'reference_decimal': str(reference),
                                 'absolute_error': str(error), 'passed': error <= Decimal('1e-40')})
    inherited = scenario['result']['results']['scenario_dcf_spec']
    spec_hash = hashlib.sha256(json.dumps(dcf['spec'], ensure_ascii=False, separators=(',', ':')).encode('utf-8')).hexdigest()
    pinned = dcf.get('source_model', {})
    actual_requests = []
    for e in read('research-models-pi-workflow-v06.run-1.audit.json'):
        if e['type'] == 'tool_request' and e['data']['name'] == 'run_financial_model' and e['data']['args'].get('kind') == 'dcf':
            actual_requests.append(e['data']['args'])
    metadata = {
        'complete_spec_equal': dcf['spec'] == inherited,
        'input_basis_equal': dcf['spec'].get('input_basis') == inherited.get('input_basis'),
        'source_refs_equal': dcf['spec'].get('source_refs') == inherited.get('source_refs'),
        'scenario_assumptions_equal': dcf['spec'].get('scenario_assumptions') == inherited.get('scenario_assumptions'),
        'source_model_correct_artifact_and_revision': pinned.get('artifact_id') == scenario['id'] and pinned.get('revision_id') == scenario['revision_id'] and pinned.get('variant') == 'scenario',
        'import_hash_matches_saved_spec': pinned.get('spec_sha256') == spec_hash,
        'dependency_exactly_pins_scenario': any(d['kind'] == 'artifact' and d['id'] == scenario['id'] and d['version'] == scenario['revision_id'] for d in dcf['dependencies']),
        'real_pi_used_source_model_without_handwritten_spec': any(a.get('source_model', {}).get('revision_id') == scenario['revision_id'] and 'spec' not in a for a in actual_requests),
        'inherited_audit_points_to_selected_scenario': dcf['source_validation']['inherited_from']['revision_id'] == scenario['revision_id'],
        'no_parameter_semantic_verification_claim': dcf['source_validation']['semantic_accuracy_verified'] is False,
    }
    final_budget = report['runs'][-1]['evaluation']
    old_files_unchanged = all(digest(ROOT / p) == sha for p, sha in prior['protected_file_hashes'].items())
    output = {
        'kind': 'independent_synthetic_workflow_verification', 'accuracy_holdout': False,
        'original_report': str(original_path.relative_to(ROOT)), 'original_status': report['status'],
        'original_report_sha256': original_hash, 'task_sha256': report['task_sha256'],
        'reference_provenance': {'source': 'research-models-pi-workflow-v05.diagnosis.json',
                                 'sha256': digest(FOLDER / 'research-models-pi-workflow-v05.diagnosis.json'),
                                 'method': 'Exact Fraction arithmetic on the same frozen synthetic assumptions, computed before the v06 run; no production model implementation import',
                                 'economic_inputs_identical': True},
        'project_id': report['project_id'], 'runs': [{'id': r['id'], 'status': r['status'], 'usage': r['usage']} for r in report['runs']],
        'final_shared_budget': final_budget,
        'arithmetic': {'absolute_tolerance': '1e-40', 'passed': sum(x['passed'] for x in calculations), 'total': len(calculations), 'checks': calculations},
        'metadata_checks': metadata, 'source_model': pinned, 'source_validation': dcf.get('source_validation'),
        'actual_dcf_tool_requests': actual_requests, 'actual_failures': report['failures'],
        'implementation_changed': report['implementation_changed'],
        'old_v05_results_unchanged': old_files_unchanged,
        'limitations': [
            'The original v06 10/10 workflow score uses its disclosed contract; v05 retains 8/10 under its earlier contract.',
            'This confirms synthetic calculations, metadata transfer and dependency behavior, not real-company financial accuracy.',
            'Other independent development runs were active; elapsed time is not an unloaded performance measurement.',
            'Two failed report citations were corrected in the same first Pi session. No host-driven retry was made.',
            'The host-edit fixture changed only the WACC value, preserving an old rationale that says WACC=0.1. The second Pi session correctly reported this metadata inconsistency. The test fixture does not exercise the UI edit helper that reclassifies modified inputs.',
            'Reference-location and literal-quote checks do not prove semantic correctness of model-proposed disclosed/derived/assumption classifications.',
        ],
        'host_edit_rationale_observation': {
            'new_wacc': report['host_edit']['spec']['dcf']['discount']['wacc'],
            'basis': report['host_edit']['spec'].get('input_basis', {}).get('dcf.discount.wacc'),
            'scope': 'Frozen host-edit fixture metadata; not changed after the run',
        },
    }
    assert digest(original_path) == original_hash
    output['status'] = 'verified_with_recorded_workflow_limitations' if all(metadata.values()) and all(c['passed'] for c in calculations) and not report['implementation_changed'] and old_files_unchanged else 'failed'
    target = FOLDER / 'research-models-pi-workflow-v06.independent.json'
    with target.open('x', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
        f.write('\n')
    print(json.dumps({'path': str(target), 'status': output['status'],
                      'arithmetic': [output['arithmetic']['passed'], len(calculations)],
                      'metadata': [sum(metadata.values()), len(metadata)],
                      'original_report_unchanged': True, 'old_v05_results_unchanged': old_files_unchanged}, ensure_ascii=True))


if __name__ == '__main__':
    main()
