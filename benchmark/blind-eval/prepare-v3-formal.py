"""Seal the approved formal protocol and plan, without network or model calls.

Runtime/data readiness is deliberately separate: this file does not authorize a
POST or turn an offline snapshot into an active API data freeze.
"""
import hashlib
import json
import shutil
import uuid
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / 'benchmark/blind-eval'
PUBLIC = ROOT / 'data/evaluation/blind-eval-F21-formal-20261009'
PRIVATE = ROOT / 'data/evaluation/blind-eval-F21-formal-private-20261009'
HELD = ROOT / 'data/evaluation/blind-eval-v3-heldout-private-20261008'


def read(p):
    return json.loads(p.read_text(encoding='utf-8-sig'))


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def save(p, value):
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open('x', encoding='utf-8', newline='\n') as stream:
        stream.write(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


def packet(task, repeat):
    if task.startswith('BH'):
        return 'heldout-' + task
    if task == 'D1':
        return 'development-D1'
    if task in ('D2', 'D3'):
        return 'development-D2-D3-r' + ('1-3' if repeat <= 3 else '4-6')
    return {'X1': 'extension-X1-X3', 'X3': 'extension-X1-X3',
            'X4': 'extension-X4-X5', 'X5': 'extension-X4-X5',
            'X6': 'extension-X6-X7', 'X7': 'extension-X6-X7'}[task]


def main():
    if (PUBLIC / 'protocol-freeze.json').exists():
        raise RuntimeError('Formal protocol already sealed; do not overwrite or generate a second batch')
    now = datetime.now(timezone.utc).isoformat()
    batch = 'F21_formal_' + uuid.uuid4().hex
    schedule = read(BASE / 'v3-formal-schedule.json')
    assert len(schedule) == 162
    tasks = {}
    for name in ['f1-config.json', 'f14-stage-b-config.json', 'f14-x7-config.json']:
        tasks.update({task['id']: task for task in read(BASE / name)['tasks']})
    source_manifest = read(HELD / 'frozen/manifest.json')
    for name, expected in source_manifest['files'].items():
        assert sha(HELD / 'frozen' / name) == expected, name
    held_data = read(HELD / 'completed-F21-20261009/manifest.json')
    for task in read(HELD / 'frozen/tasks.json'):
        tasks[task['id']] = {**task, 'projectId': held_data['project_id']}
    ids = {row['task'] for row in schedule}
    tasks = {key: tasks[key] for key in sorted(ids)}
    rows = []
    for row in schedule:
        task = tasks[row['task']]
        key = f"{batch}_{task['split']}_{row['chain']}_{row['arm']}_r{row['repeat']}"
        rows.append({
            'ordinal': row['ordinal'], 'label': {'original_pi': 'G', 'prepared': 'P', 'financial': 'F'}[row['arm']] + str(row['repeat']) + '_' + row['task'],
            'taskId': row['task'], 'profile': row['arm'], 'repeat': row['repeat'],
            'chainTask': row['chain'], 'parentTask': row['same_session_as'],
            'chainId': key, 'isolationKey': key, 'projectId': task['projectId'],
            'split': task['split'], 'reviewPacket': packet(row['task'], row['repeat']),
            'status': 'planned', 'attempt': 1, 'usage': None,
        })
    counts = Counter((r['taskId'], r['profile']) for r in rows)
    assert all(n == (3 if task.startswith('X') else 6) for (task, _), n in counts.items())
    assert len({r['chainId'] for r in rows}) == 144
    packets = Counter(r['reviewPacket'] for r in rows)
    assert len(packets) == 9 and set(packets.values()) == {18}
    for index, row in enumerate(rows):
        if row['parentTask']:
            previous = rows[index-1]
            assert previous['taskId'] == row['parentTask'] and previous['chainId'] == row['chainId']

    source_names = [
        'V3_PROTOCOL_REVISION_20261009.md', 'V3_THREE_ARM_PLAN_20261008.md',
        'v3-formal-schedule.json', 'v3-gate-plan.json', 'review-protocol.md', 'rubric.md',
        'reference-development.json', 'reference-phase1.json', 'reference-stage-b-additions.json',
        'reference-stage-c-X7.json', 'selectors-phase1.json', 'selectors-stage-b-additions.json',
        'selectors-stage-c-X7.json', 'f1-config.json', 'f14-stage-b-config.json', 'f14-x7-config.json',
    ]
    sealed = {}
    for name in source_names:
        target = PRIVATE / 'frozen-public-inputs' / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(BASE / name, target)
        sealed['benchmark/blind-eval/' + name] = sha(target)
    shutil.copytree(HELD / 'frozen', PRIVATE / 'frozen-heldout-inputs')
    judge_seals = {}
    for name in ['judge-round1-prompt.txt', 'judge-round2-prompt.txt']:
        source = ROOT / 'data/evaluation/blind-eval-F21-gate-20261009' / name
        target = PRIVATE / 'frozen-judge-instructions' / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        judge_seals[name] = sha(target)
    save(PRIVATE / 'tasks.json', list(tasks.values()))
    save(PRIVATE / 'planned-runs.json', rows)
    save(PRIVATE / 'heldout-freeze-inheritance.json', {
        'source_manifest': str((HELD / 'completed-F21-20261009/manifest.json').relative_to(ROOT)),
        'source_manifest_sha256': sha(HELD / 'completed-F21-20261009/manifest.json'),
        'source_reference_hashes': source_manifest['files'],
        'review_issues_total': 14, 'required_table_overlap': 1,
        'reference_required_input_overlap': 0, 'answerability_affected': False,
        'database_modified_for_evaluation': False,
        'current_api_freeze_reverification': 'pending_3001_restoration',
    })
    save(PRIVATE / 'execution-state.json', {
        'schema': 'blind-eval-v3-formal-preflight-1', 'batchId': batch,
        'version': 'F2.1', 'deployedCommit': '7e702ff3f53eba8686254895ad98300445eac759',
        'paid_participant_authorized': True, 'runs': rows, 'runtimeFreeze': None,
        'projectFreezes': {}, 'stopReason': 'service_unavailable_before_first_submission',
        'requiresFirstTurnInspection': True, 'firstTurnInspection': None,
        'unknown_usage': 'observed per-request maxima within this batch, arm and task; no maximum means unknown',
    })
    manifest = {
        'schema': 'blind-eval-v3-formal-protocol-seal-1', 'sealedAt': now, 'batchId': batch,
        'status': 'protocol_sealed_runtime_preflight_blocked',
        'authority': '2026-10-09 coordinator confirms user authorization for 162 formal turns and protocol revision',
        'version': 'F2.1', 'deployedCommit': '7e702ff3f53eba8686254895ad98300445eac759',
        'p3': 'deferred', 'protocolFiles': sealed, 'judgeInstructionFiles': judge_seals,
        'participantTurns': 162, 'chains': 144, 'reviewPackets': dict(packets), 'reviewThreads': 18,
        'seeds': {'core_and_heldout': 20261008, 'extension': 20261009},
        'schedule_sha256': sha(BASE / 'v3-formal-schedule.json'),
        'ready_material_task_ids': ['BH1', 'BH2', 'BH3', 'D1', 'D2', 'D3'],
        'ready_material_turns': 108, 'pending_full_ingestion_and_freeze': ['X1', 'X3', 'X4', 'X5', 'X6', 'X7'],
        'dispatch': 'stable filter of approved schedule by frozen material block; unchanged order inside each block',
        'concurrency': {'maximum_chains': 2, 'different_active_arms': True, 'dependent_turns_same_session': True},
        'request': {'analysis_only': True, 'documentIds': [], 'fresh_isolation_key_per_chain': True},
        'stability': {'per_split_min_material_presence_agreement': 0.8, 'mean_absolute_score_delta_max': 0.5,
                      'maximum_delta': 'report_only', 'kappa': 'report_only', 'independent_E4_each_pass': True,
                      'adjudication': False, 'averaging_pass_scores': False},
        'heldout_review_issues': {'total': 14, 'required_table_overlap': 1, 'required_reference_overlap': 0, 'answerability_affected': False},
        'privacy': 'Public outputs contain IDs and aggregate metrics only. All held-out content, raw reviews and disagreement quotations stay N1-private.',
        'model_connectivity': 'not_tested: 3001 has no listener; not evidence of authentication or quota failure',
        'participant_requests_submitted': 0, 'paid_probe_requests_submitted': 0,
        'runtime_freeze': 'pending_service_restoration_and_current_live_verification',
        'code_or_database_changed': False,
    }
    save(PUBLIC / 'protocol-freeze.json', manifest)
    save(PUBLIC / 'offline-plan-validation.json', {
        'at': now, 'passed': True, 'planned_turns': len(rows), 'chains': 144,
        'review_packets': 9, 'repeat_counts_correct': True, 'D2_D3_dependencies_preserved': True,
        'approved_schedule_bytes_unchanged': True, 'heldout_frozen_inputs_hashes_match': True,
        'network_calls': 0, 'model_calls': 0, 'runtime_verified': False,
    })
    print(json.dumps({'batchId': batch, 'turns': len(rows), 'chains': 144, 'packets': dict(packets), 'participant_posts': 0}))


if __name__ == '__main__':
    main()
