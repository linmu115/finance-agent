"""Package the already-frozen X7 gold and verified source pages, without live data."""
import hashlib
import json
import shutil
from pathlib import Path
from blind import ROOT, read, dump, output

source = ROOT / 'data/evaluation/blind-eval-haier-reference-20261008'
receipt = read(source / 'freeze-receipt.json')
gold_path = ROOT / receipt['reference']
selectors_path = ROOT / receipt['selectors']
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
assert sha(gold_path) == receipt['reference_sha256']
assert sha(selectors_path) == receipt['selectors_sha256']
frozen = read(gold_path)
dest = output(ROOT / 'data/evaluation/blind-eval-F14-X7-preparation-20261008/judge-reference')
dest.mkdir(parents=True, exist_ok=False)
dump(dest / 'gold.json', {
    'rubric_version': frozen['rubric_version'],
    'task_requirements': {'X7': frozen['tasks']['X7']['task_requirements']},
    'references': {'X7': frozen['tasks']['X7']},
})
files = []
for page in frozen['sources']['annual']['evidence']:
    for kind in ['txt', 'png']:
        src = source / page[kind]
        assert sha(src) == page[kind + '_sha256']
        shutil.copyfile(src, dest / src.name)
        files.append({'path': src.name, 'sha256': sha(src)})
(dest / 'reference-notes.md').write_text(
    '冻结参考来自独立原页核对。原报告物理页码与印刷页码相同。'
    '按题目要求和六维 rubric 评审；任何实质错误使实质取数计算最高1分。'
    '资料中未披露的拆分保持未知；不把列报调整、同一控制合并和经营变化混为一谈。'
    '只读取本轮匿名包，代码只读不执行。\n', encoding='utf8')
dump(dest.parent / 'reference-packaging-receipt.json', {
    'purpose': 'Copy already-frozen X7 reference; no live project snapshot or participant request',
    'original_freeze': receipt,
    'source_pages': files,
    'gold_changed': False,
    'database_writes': 0,
    'paid_requests': 0,
})
print(json.dumps({'destination': str(dest), 'source_files': len(files), 'paid_requests': 0}))
