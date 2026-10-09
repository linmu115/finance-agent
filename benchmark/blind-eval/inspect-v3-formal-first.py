"""Inspect the authorized replacement's real sandbox execution and delivery.

No model call, database write, service restart, or score interpretation.
"""
import json
import subprocess
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
STUDY = ROOT / 'data/evaluation/blind-eval-F21-formal-private-20261009'
PUBLIC = ROOT / 'data/evaluation/blind-eval-F21-formal-20261009'


def read(p):
    return json.loads(p.read_text(encoding='utf-8-sig'))


def criteria(run, deliveries, health):
    scripts = deliveries.get('evaluatorScripts', [])
    artifacts = deliveries.get('artifacts', [])
    return {
        'host_completed': run.get('status') == 'completed',
        'sandbox_executed': any(s.get('status') == 'succeeded' for s in scripts),
        'attachments_generated_and_downloaded': any(a.get('httpStatus') == 200 and a.get('localFile') and a.get('bytes', 0) > 0 for a in artifacts),
        'service_connected': health.get('ok') is True and health.get('service') == 'connected',
    }


def main():
    state = read(STUDY / 'experiment.json')
    first = state['runs'][0]
    assert len([r for r in state['runs'] if r.get('runId')]) == 1
    assert first['status'] in {'completed', 'failed', 'cancelled'}
    assert first.get('attempt') == 2 and first.get('replacementForEnvironmentCheck')
    subprocess.run(['node', 'benchmark/blind-eval/runner-v3-formal.mjs', 'verify'], cwd=ROOT, check=True)
    subprocess.run(['node', 'benchmark/blind-eval/runner-v3-formal.mjs', 'collect'], cwd=ROOT, check=True, stdout=subprocess.DEVNULL)
    manifest = read(STUDY / (first['label'] + '-deliverables.json'))
    with urllib.request.urlopen('http://127.0.0.1:3001/api/health', timeout=10) as response:
        health = json.loads(response.read())
    checks = criteria(first, manifest, health)
    text = (ROOT / 'server/dist/main.js').read_text(encoding='utf-8')
    start = text.index("app.get('/api/projects/:projectId/artifacts/:runId/:name'")
    checks['frozen_metadata_route'] = "service.call('get_artifact_metadata'" in text[start:start+1800]
    result = {
        'at': datetime.now(timezone.utc).isoformat(), 'passed': all(checks.values()),
        'label': first['label'], 'runId': first['runId'], 'attempt': first['attempt'],
        'checks': checks, 'sandbox_runs': manifest.get('evaluatorScripts', []),
        'artifact_count': len(manifest['artifacts']),
        'downloaded': sum(a.get('httpStatus') == 200 for a in manifest['artifacts']),
        'health': health, 'paid_inspection_calls': 0,
        'note': 'Actual standard sandbox state and generated artifact HTTP downloads; financial correctness remains for independent review. No inference from host completed alone.',
    }
    state['firstTurnInspection'] = result
    if not result['passed']:
        state['stopReason'] = 'replacement_first_environment_check_not_passed'
    (STUDY / 'first-turn-inspection.json').write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    (STUDY / 'experiment.json').write_text(json.dumps(state, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    public = {k: result[k] for k in ['at', 'passed', 'label', 'attempt', 'checks', 'artifact_count', 'downloaded', 'health', 'paid_inspection_calls']}
    (PUBLIC / 'replacement-first-inspection.json').write_text(json.dumps(public, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(public, ensure_ascii=False))
    if not result['passed']:
        sys.exit(2)


if __name__ == '__main__':
    main()
