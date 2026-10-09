"""Collect one completed 18-case block and create two anonymous review copies.

Does not start reviewers, inspect scores, or release unverified attachments.
"""
import argparse
import hashlib
import json
import os
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / 'data/evaluation/blind-eval-F21-formal-private-20261009'


def read(p):
    return json.loads(p.read_text(encoding='utf-8-sig'))


def write(p, value):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(value, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')


def main(packet):
    state = read(BASE / 'experiment.json')
    rows = [r for r in state['runs'] if r['reviewPacket'] == packet]
    assert len(rows) == 18 and all(r['status'] in {'completed','failed','cancelled','blocked_dependency'} for r in rows)
    dest = BASE / 'review-packets' / packet
    source = BASE / 'review-sources' / packet
    assert not dest.exists() and not source.exists()
    subprocess.run(['node','benchmark/blind-eval/runner-v3-formal.mjs','collect'],cwd=ROOT,check=True,stdout=subprocess.DEVNULL)
    source.mkdir(parents=True)
    tasks = [t for t in state['config']['tasks'] if t['id'] in {r['taskId'] for r in rows}]
    for r in rows:
        label = r['label']
        if r['status'] == 'blocked_dependency':
            (source / (label+'-answer.md')).write_text('',encoding='utf-8')
            write(source / (label+'-deliverables.json'),{'label':label,'artifacts':[],'evaluatorScripts':[]})
            r['original_status'] = r['status'];r['status'] = 'failed'
        else:
            for suffix in ['-run.json','-conversation.json','-audit.jsonl','-answer.md','-deliverables.json']:
                shutil.copyfile(BASE / (label+suffix),source / (label+suffix))
            shutil.copytree(BASE / (label+'-artifacts'),source / (label+'-artifacts'))
    write(source/'experiment.json',{'schema':'blind-eval-f1-v1','runs':rows,'config':{'tasks':tasks},'source_batch':state['batchId'],'view':'completed review block; blocked_dependency retained as an empty delivered answer'})
    sealed = [{'path':p.relative_to(source).as_posix(),'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in sorted(source.rglob('*')) if p.is_file()]
    write(source/'raw-seal.json',{'at':datetime.now(timezone.utc).isoformat(),'files':sealed})
    reference = BASE / 'reference-packets' / packet
    assert reference.exists()
    # Same anonymization seed/mechanics as the valid gate. Formal source positions are already frozen.
    result = subprocess.run(['python','-B','benchmark/blind-eval/blind.py',str(source),str(dest),'--reference-dir',str(reference),'--seed','2026100903'],cwd=ROOT,capture_output=True,text=True,encoding='utf-8')
    (source/'anonymization.log').write_text(result.stdout+result.stderr,encoding='utf-8')
    if not (dest/'private-map.json').exists():
        raise RuntimeError('Anonymization failed before a complete packet; inspect private log')
    mapping = read(dest/'private-map.json')['cases']
    assert len(mapping) == 18
    identities = {x['label']: x for x in mapping}
    # Link dependent answers by their anonymous IDs in each pass. No tool history,
    # group identifiers, cost, failure explanations or evaluator opinions are added.
    for rd in ['round1','round2']:
        inverse = {v:k for k,v in read(dest/('private-'+rd+'-map.json')).items()}
        for r in rows:
            if not r.get('parentLabel'):
                continue
            child = inverse[identities[r['label']]['case_id']]
            parent = inverse[identities[r['parentLabel']]['case_id']]
            folder = dest/rd/child
            (folder/'conversation-context.md').write_text('本案是同一会话的后续问题。前一答卷：'+parent+'；前一答卷的回答与附件保留在该目录。\n',encoding='utf-8')
            files=read(folder/'files.json');files.append({'file':'conversation-context.md','role':'previous_turn_context'})
            write(folder/'files.json',files)
        if (reference/'complete-originals').exists():
            shutil.copytree(reference/'complete-originals',dest/rd/'reference/complete-originals')
    if (reference/'complete-originals').exists():
        shutil.copytree(reference/'complete-originals',dest/'reference/complete-originals')
    verify = subprocess.run(['python','-B','benchmark/blind-eval/verify-anonymous-attachments.py',str(source),str(dest)],cwd=ROOT,capture_output=True,text=True,encoding='utf-8')
    (source/'attachment-verification.log').write_text(verify.stdout+verify.stderr,encoding='utf-8')
    write(dest/'pre-release-status.json',{'packet':packet,'cases':18,'anonymizer_exit':result.returncode,'attachment_verification_exit':verify.returncode,'visual_identity_review':'required before release','reviewers_started':False,'scores_read':False})
    print(json.dumps({'packet':packet,'cases':18,'anonymizer_exit':result.returncode,'attachment_verification_exit':verify.returncode,'released':False}))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('packet');main(p.parse_args().packet)
