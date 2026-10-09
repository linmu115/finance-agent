"""Decode only after all 18 original reviews have been sealed; never revise scores."""
import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT/'data/evaluation/blind-eval-F21-formal-private-20261009'
DIMS = dict(zip(['reading','substantive','explanation','adjustments','anomalies','common'], ['R1','R2','R3','R4','R5','C']))


def read(p):
    return json.loads(p.read_text(encoding='utf-8-sig'))


def digest(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def decode():
    state = read(BASE/'experiment.json')
    assert len(state['runs']) == 162
    assert all(r['status'] in {'completed','failed','cancelled','blocked_dependency'} for r in state['runs'])
    runs = {r['label']:r for r in state['runs']}
    packets = list(dict.fromkeys(r['reviewPacket'] for r in state['runs']))
    assert len(packets) == 9
    # Establish the all-review seal before parsing any review, mapping or score.
    receipts = []
    for packet in packets:
        folder = BASE/'review-packets'/packet
        seal = read(folder/'score-seal.json')
        assert len(seal['reviews']) == 2 and seal['scores_read'] is False
        for file in seal['reviews']:
            assert digest(folder/file['path']) == file['sha256'] == digest(folder/file['sealed_copy'])
        receipts.append({'packet':packet,'seal_sha256':digest(folder/'score-seal.json')})
    with (BASE/'all-reviews-sealed-before-unblinding.json').open('x',encoding='utf-8') as h:
        json.dump({'at':datetime.now(timezone.utc).isoformat(),'review_threads':18,'packets':receipts},h,indent=2)
    output = {'round1':[],'round2':[]}
    for packet in packets:
        folder = BASE/'review-packets'/packet
        identities = {x['case_id']:x for x in read(folder/'private-map.json')['cases']}
        reference = read(folder/'reference/reference.json')
        for rd in output:
            mapping = read(folder/f'private-{rd}-map.json')
            raw = read(folder/f'sealed-{rd}-review.json')
            meta = raw['metadata']
            assert meta['model'] == 'gpt-6-astra' and meta['reasoning_effort'] == 'high'
            assert meta['rubric_version'] == 'analyst-requirements-v2-20261008'
            assert len(raw['reviews']) == 18 and {r['case_id'] for r in raw['reviews']} == set(mapping)
            for review in raw['reviews']:
                identity = identities[mapping[review['case_id']]]
                run = runs[identity['label']]
                assert set(review['scores']) == set(DIMS)
                for dim, req in DIMS.items():
                    value = review['scores'][dim]
                    coverage = reference['task_requirements'][identity['task']][req]['coverage']
                    assert value is None if coverage == 'not_tested' else type(value) is int and 0 <= value <= 4
                assert not review['material_defects'] or review['scores']['substantive'] <= 1
                assert all(k in review for k in ['reasons','material_defects','minor_defects','unreviewed','identity_clues','inspection','common_checks'])
                output[rd].append({**review,'label':run['label'],'task':run['taskId'],
                    'profile':run['profile'],'repeat':run['repeat'],'split':run['split'],
                    'packet':packet,'critical_unreviewed':None})
    assert all(len(rows) == 162 and len({r['label'] for r in rows}) == 162 for rows in output.values())
    for rd, rows in output.items():
        with (BASE/f'{rd}-decoded.json').open('x',encoding='utf-8') as h:
            json.dump(rows,h,ensure_ascii=False,indent=2)
    # Interpretation of actual inspection omissions happens after sealing, and is
    # separate from the original scores. No omitted file is automatically accepted.
    pending = [{'round':rd,'label':r['label'],'unreviewed':r['unreviewed'],
                'critical_unreviewed':None,'reason':None} for rd,rows in output.items() for r in rows]
    with (BASE/'critical-unreviewed-assessment.pending.json').open('x',encoding='utf-8') as h:
        json.dump(pending,h,ensure_ascii=False,indent=2)
    print(json.dumps({'decoded_rounds':2,'cases_per_round':162,'private_only':True,
                      'critical_delivery_inspection_assessment':'pending'}))


if __name__ == '__main__':
    p=argparse.ArgumentParser();p.parse_args();decode()
