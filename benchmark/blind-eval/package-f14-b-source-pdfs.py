"""Supply complete, already-frozen original reports to both independent reviewers."""
import hashlib
import json
import shutil
from pathlib import Path
from datetime import datetime, timezone
from blind import ROOT, read, dump

study = ROOT / 'data/evaluation/blind-eval-F14-B-20261008'
material = next(iter(read(study / 'materials-F14-P1.json').values()))
names = {
    'd84573bf6b584e7e874faa4c6adf454a': 'annual-original.pdf',
    '4c3e9228d37e49fca132e0e79377b04d': 'q3-original.pdf',
    '585db15e768043b7b465d1af7c690e90': 'guosen-original.pdf',
    '5a64cb3df8a54728a8562add6840881c': 'may-original.pdf',
    '952ecfa574aa4ea8b849bea4b1c6020c': 'huatai-original.pdf',
    '47d2d1bad23d4318bdfa197bcad17349': 'nov-original.pdf',
}
folder = study / 'judge-reference' / 'complete-originals'
folder.mkdir(exist_ok=False)
copied = []
for row in material['source_files']:
    if row['document_id'] not in names:
        continue
    src = ROOT / row['path']
    sha = hashlib.sha256(src.read_bytes()).hexdigest()
    assert sha == row['sha256']
    name = names[row['document_id']]
    shutil.copyfile(src, folder / name)
    copied.append({'file': name, 'sha256': sha, 'bytes': row['bytes']})
assert len(copied) == len(names)
(folder / 'README.md').write_text(
    '这些是本批冻结资料中的完整原始报告，供核验参考摘页以外的引用。'
    '文件名只是来源简称；不包含任何参评组、运行轨迹或评分信息。'
    '金标及其数值未改。PDF页码为从1起的物理页。\n', encoding='utf8')
dump(study / 'complete-source-packaging-receipt.json', {
    'at': datetime.now(timezone.utc).isoformat(),
    'purpose': 'Complete original evidence, exactly matched to pre-run material hashes; no gold edits',
    'files': copied,
    'copy_into_both_round_reference_directories_after_anonymization': True,
    'gold_changed': False,
    'model_calls': 0,
})
print(json.dumps({'source_documents': len(copied), 'gold_changed': False}))
