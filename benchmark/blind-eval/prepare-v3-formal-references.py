"""Assemble judge references from the already sealed inputs; no answer access."""
import hashlib
import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PRIVATE = ROOT / 'data/evaluation/blind-eval-F21-formal-private-20261009'
SEALED = PRIVATE / 'frozen-public-inputs'
HELD = PRIVATE / 'frozen-heldout-inputs'
OLD_HELD = ROOT / 'data/evaluation/blind-eval-v3-heldout-private-20261008'


def read(p):
    return json.loads(p.read_text(encoding='utf-8-sig'))


def write(p, value):
    p.write_text(json.dumps(value, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')


def main():
    planned = read(PRIVATE / 'planned-runs.json')
    dev = read(SEALED / 'reference-development.json')
    tasks = {t['id']: t for t in read(HELD / 'tasks.json')}
    original_dev = ROOT / 'data/evaluation/blind-eval-F1-20261008/stage-A-reference'
    destinations = []
    for packet in dict.fromkeys(r['reviewPacket'] for r in planned):
        if packet.startswith('extension'):
            continue
        dest = PRIVATE / 'reference-packets' / packet
        dest.mkdir(parents=True, exist_ok=False)
        selected = sorted({r['taskId'] for r in planned if r['reviewPacket'] == packet})
        gold = {'rubric_version': 'analyst-requirements-v2-20261008', 'task_requirements': {}, 'references': {}}
        if packet.startswith('development'):
            gold['references']['development_original'] = dev
            gold['task_requirements'] = {task: dev['task_requirements'][task[1:]] for task in selected}
            shutil.copyfile(original_dev / 'reference-notes.md', dest / 'reference-notes.md')
            prefix = 'interim' if selected == ['D1'] else 'research'
            for p in original_dev.glob(prefix+'-p*.*'):
                shutil.copyfile(p, dest / p.name)
        else:
            gold['references']['frozen_reference'] = read(HELD / 'reference.json')
            selectors = read(HELD / 'selectors.json')['selectors']
            gold['references']['frozen_selectors'] = {task: selectors[task] for task in selected}
            for task in selected:
                gold['task_requirements'][task] = {
                    k: {'coverage': {'primary': 'direct', 'auxiliary': 'supporting', 'not_tested': 'not_tested'}[v],
                        'must_mention': [] if v == 'not_tested' else ['参见冻结 reference-notes.md 中对应题目的五项要求、必提要点及原页参考。'],
                        'scope': '冻结题面的适用范围；不增加题外评分要求。'}
                    for k, v in tasks[task]['requirements'].items()
                }
            # Only the approved answer/requirements sections, byte-preserved.
            # Preparation budgets, workflow history and source-selection notes are not judge inputs.
            notes = (HELD / 'source-review-reference.md').read_text(encoding='utf-8')
            notes = notes[notes.index('## 五项要求与必提要点'):notes.index('## 入库门槛与材料规模')]
            (dest / 'reference-notes.md').write_text(notes, encoding='utf-8')
            for p in (OLD_HELD / 'source-review').iterdir():
                if p.is_file() and p.suffix in {'.png', '.txt'}:
                    shutil.copyfile(p, dest / ('source-' + p.name))
            complete = dest / 'complete-originals'
            complete.mkdir()
            source = read(OLD_HELD / 'source-manifest.json')
            pdf = ROOT / source['path']
            assert hashlib.sha256(pdf.read_bytes()).hexdigest() == source['sha256']
            shutil.copyfile(pdf, complete / 'source-annual-report.pdf')
        write(dest / 'gold.json', gold)
        shutil.copyfile(SEALED / 'rubric.md', dest / 'rubric.md')
        files = [{'file': p.relative_to(dest).as_posix(), 'sha256': hashlib.sha256(p.read_bytes()).hexdigest()}
                 for p in sorted(dest.rglob('*')) if p.is_file()]
        destinations.append({'packet': packet, 'tasks': selected, 'files': files})
    write(PRIVATE / 'reference-packets-provenance.json', {
        'sources': 'Previously frozen reference and source pages only; no participant answers read',
        'scoring_content_changed': False, 'packets': destinations,
    })
    print(json.dumps({'reference_packets': len(destinations), 'answers_read': 0, 'model_calls': 0}))


if __name__ == '__main__':
    main()
