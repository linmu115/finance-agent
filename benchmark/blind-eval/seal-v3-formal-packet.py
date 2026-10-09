"""Offline inventory and sealing; does not inspect scores or start reviewers."""
import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT/'data/evaluation/blind-eval-F21-formal-private-20261009'


def read(p):
    return json.loads(p.read_text(encoding='utf-8-sig'))


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def save(p, value):
    with p.open('x', encoding='utf-8') as h:
        json.dump(value, h, ensure_ascii=False, indent=2)
        h.write('\n')


def inventory(folder):
    grouped = {}
    for p in sorted((folder/'packet').rglob('*')):
        if p.is_file() and p.suffix.lower() in {'.png', '.jpg', '.jpeg'}:
            grouped.setdefault(sha(p), []).append(p.relative_to(folder).as_posix())
    return [{'sha256':key, 'paths':paths} for key, paths in grouped.items()]


def seal_inputs(folder):
    verification = read(folder/'attachment-verification.json')
    assert verification['all_passed']
    decisions = read(folder/'identity-release.json')
    visuals = inventory(folder)
    assert {x['sha256'] for x in visuals} == set(decisions['visually_opened_sha256'])
    assert decisions['explicit_group_or_model_identity_found'] is False
    flags = read(folder/'anonymization-audit.json')['explicit_marker_findings']
    assert len(decisions['finding_decisions']) == len(flags)
    for flag, decision in zip(flags, decisions['finding_decisions']):
        assert flag == decision['finding'] and decision['release'] is True
        assert decision['reason']
    mappings = [read(folder/f'private-{rd}-map.json') for rd in ['round1','round2']]
    assert list(mappings[0].values()) == list(reversed(list(mappings[1].values())))
    rounds = {}
    for rd, mapping in zip(['round1','round2'], mappings):
        target = folder/rd
        assert len(mapping) == 18 and read(target/'cases.json') == list(mapping)
        assert not (target/'review.json').exists()
        # All copied question/answer/attachment bytes must match the verified packet.
        # The dependency index is round-specific and was added by the packet assembler.
        for alias, source_id in mapping.items():
            source = folder/'packet'/source_id
            for p in source.rglob('*'):
                if p.is_file() and p.name != 'files.json':
                    assert sha(p) == sha(target/alias/p.relative_to(source))
            expected = read(source/'files.json')
            visible = read(target/alias/'files.json')
            extra = [x for x in visible if x.get('role') == 'previous_turn_context']
            assert [x for x in visible if x.get('role') != 'previous_turn_context'] == expected
            assert len(extra) <= 1
        source_prompt = BASE/'frozen-judge-instructions'/f'judge-{rd}-prompt.txt'
        original = source_prompt.read_bytes()
        old_path = f'D:/AI/财报agent/data/evaluation/blind-eval-F21-gate-review-20261009/{rd}'.encode('utf-8')
        assert original.count(old_path) == 1
        prompt = original.replace(old_path, target.as_posix().encode('utf-8'))
        prompt_path = folder/f'judge-{rd}-prompt.txt'
        with prompt_path.open('xb') as h:
            h.write(prompt)
        files = [{'path':p.relative_to(target).as_posix(), 'bytes':p.stat().st_size, 'sha256':sha(p)}
                 for p in sorted(target.rglob('*')) if p.is_file()]
        rounds[rd] = {'files':files, 'prompt_sha256':sha(prompt_path),
                      'template_sha256':sha(source_prompt), 'only_prompt_change':'permitted materials directory'}
    save(folder/'input-seal.json', {'at':datetime.now(timezone.utc).isoformat(),
         'packet':folder.name, 'model':'gpt-6-astra', 'reasoning_effort':'high',
         'attachment_verification_sha256':sha(folder/'attachment-verification.json'),
         'identity_release_sha256':sha(folder/'identity-release.json'), 'rounds':rounds})
    return {'packet':folder.name, 'input_sealed':True, 'cases_per_round':18}


def seal_scores(folder):
    seal = read(folder/'input-seal.json')
    for rd, record in seal['rounds'].items():
        assert all(sha(folder/rd/x['path']) == x['sha256'] for x in record['files'])
        assert sha(folder/f'judge-{rd}-prompt.txt') == record['prompt_sha256']
    # Read bytes only. No scores, rankings, identity mapping or review JSON parsing.
    files = []
    for rd in ['round1','round2']:
        p = folder/rd/'review.json'
        assert p.stat().st_size > 0
        raw = p.read_bytes()
        archive = folder/f'sealed-{rd}-review.json'
        with archive.open('xb') as h:
            h.write(raw)
        files.append({'path':p.relative_to(folder).as_posix(), 'sealed_copy':archive.name,
                      'bytes':len(raw), 'sha256':hashlib.sha256(raw).hexdigest()})
    save(folder/'score-seal.json', {'at':datetime.now(timezone.utc).isoformat(),
         'model':'gpt-6-astra','reasoning_effort':'high','reviews':files,
         'scores_read':False, 'rule':'All 18 review threads sealed before decoding any formal result.'})
    return {'packet':folder.name, 'two_reviews_sealed':True, 'scores_read':False}


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('command', choices=['inventory','inputs','scores'])
    p.add_argument('packet')
    a = p.parse_args()
    folder = BASE/'review-packets'/a.packet
    if a.command == 'inventory':
        result = {'visuals':inventory(folder), 'flags':read(folder/'anonymization-audit.json')['explicit_marker_findings']}
        save(folder/'visual-inventory.json', result)
        print(json.dumps({'unique_visuals':len(result['visuals']), 'flags':len(result['flags'])}))
    else:
        print(json.dumps(seal_inputs(folder) if a.command == 'inputs' else seal_scores(folder)))
