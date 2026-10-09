"""Explicit delivered-cell observations against the already sealed development gold."""
import argparse
import hashlib
from decimal import Decimal
from pathlib import Path

from blind import ROOT, read, dump, output
from metrics import numeric, UNITS


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def observe(study, bindings_path, protocol_path):
    protocol = read(protocol_path)
    relative = 'benchmark/blind-eval/reference-development.json'
    gold_path = ROOT / relative
    frozen = protocol['protocolFiles'][relative]
    if sha(gold_path) != frozen:
        raise ValueError('Development gold differs from the sealed protocol')
    gold = read(gold_path)
    bindings = read(bindings_path)
    reports = []
    for group in bindings['runs']:
        label = group['label']
        folder = study / (label + '-artifacts')
        delivered = read(study / (label + '-deliverables.json'))
        available = {a['localFile']: a for a in delivered['artifacts'] if a.get('localFile')}
        checks, proof = [], []
        for b in group['bindings']:
            file = folder / b['file']
            if b['file'] not in available or sha(file) != b['sha256'] or available[b['file']]['sha256'] != b['sha256']:
                raise ValueError('Binding does not identify an unchanged delivered artifact')
            evidence_name = b.get('unit_evidence_file', b['file'])
            if evidence_name not in available:
                raise ValueError('Unit evidence is not a delivered artifact')
            evidence = folder / evidence_name
            if sha(evidence) != available[evidence_name]['sha256'] or b['unit_quote'] not in evidence.read_text('utf-8-sig'):
                raise ValueError('Unit annotation is absent or changed')
            expected = gold
            for key in b['gold_path']:
                expected = expected[key]
            expected = Decimal(str(expected)) * Decimal(str(b.get('gold_sign', 1)))
            # Same half-last-displayed-digit convention as the frozen development notes.
            tolerance = Decimal(5).scaleb(-b['display_decimals'] - 1) * Decimal(str(UNITS[b['unit']][1])) / Decimal(str(UNITS[b['gold_unit']][1]))
            spec = {key: b[key] for key in ['key', 'file', 'format', 'unit']}
            spec.update({key: b[key] for key in ['row', 'column', 'path'] if key in b})
            spec['expected'] = {'value': str(expected), 'unit': b['gold_unit'], 'absolute_tolerance': float(tolerance)}
            checks.append(spec)
            proof.append(b)
        result = numeric({'checks': checks}, folder)
        result.update(label=label, gold_sha256=frozen, binding_provenance=proof,
                      unbound=group.get('unbound', []), scope=bindings['scope'])
        dump(study / (label + '-gold-numeric.json'), result)
        reports.append({'label': label, 'checks': len(result['checks']),
                        'statuses': {s: sum(c['status'] == s for c in result['checks']) for s in sorted({c['status'] for c in result['checks']})}})
    return {'binding_sha256': sha(bindings_path), 'gold_sha256': frozen, 'reports': reports, 'scope': bindings['scope']}


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('study'); p.add_argument('bindings'); p.add_argument('protocol'); p.add_argument('destination')
    a = p.parse_args()
    result = observe(output(a.study), Path(a.bindings), Path(a.protocol))
    dump(output(a.destination), result)
    print({'runs': len(result['reports']), 'explicit_cells': sum(r['checks'] for r in result['reports'])})
