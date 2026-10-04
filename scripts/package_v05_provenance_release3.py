"""Explicit pre-first-run evidence contract release; preserves old ZIP and gold."""
import hashlib
import json
import os
import shutil
import zipfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SUITE = ROOT / 'benchmark/versions/v0.5-holdout'
sha = lambda raw: hashlib.sha256(raw).hexdigest()
now = datetime.now(timezone.utc).isoformat()
for arm in ('financial', 'generic'):
    if (ROOT / f'benchmark/results/holdout-v05-{arm}-first-run.lock.json').exists():
        raise RuntimeError('First run already locked; cannot revise pre-run verifier')
manifest_path = SUITE / 'manifest.json'
manifest_bytes = manifest_path.read_bytes()
manifest = json.loads(manifest_bytes)
gold_before = sha((SUITE / 'gold.json').read_bytes())
score_before = sha((ROOT / 'scripts/score_financial_tables_v05.mjs').read_bytes())
expected = json.loads((ROOT / 'benchmark/versions/v0.5-execution-release-2.json').read_text(encoding='utf8'))
assert gold_before == expected['gold_sha256']
assert score_before == expected['helper_sha256']['scripts/score_financial_tables_v05.mjs']
change_path = SUITE / 'SCORER_PRE_RUN_CHANGES.json'
changes = json.loads(change_path.read_text(encoding='utf8'))
if changes['version'] != 'v0.5-pre-run-clarifications-1':
    raise RuntimeError('Unexpected existing change version; do not run twice')
changes['version'] = 'v0.5-pre-run-clarifications-2'
changes['changes'].append('Before any formal prediction, definition provenance now verifies definition-quote-location-1: exact original model attributes, same-group unique source relocation or whitespace-only alignment, Python Unicode codepoint offsets, immutable original owner/result hash, archived values and own partial-batch report. Explicit recorded definition repair may combine same-owner calls; catalog/temporal caches still require one complete original response. This supersedes only the definition-cache clause of clarification 5. No financial gold, input, exact amount, concept, unit, date, source-cell, precision or recall scoring rule changed.')
changes['evidence_contract_revision'] = {
    'created_at': now, 'reason': 'New production quote_alignment and per-invalid-group repair contract would be falsely rejected by the older evidence checker.',
    'validation': ['tests/definition-evidence-v2.test.ts', 'tests/review-evidence-v05.test.ts',
                   'benchmark/results/known-definition-clean1-grounding-independent-v2.json',
                   'benchmark/results/known-definition-clean1-provenance-v2.json'],
    'official_model_calls': 0, 'historical_reports_modified': False,
    'financial_scorer_sha256': score_before, 'gold_sha256': gold_before,
}
helpers = ['scripts/verify_holdout_v05.mjs', 'scripts/score_financial_tables_v05.mjs',
           'scripts/score_holdout_v05_artifact.mjs', 'scripts/review_evidence_v05.mjs',
           'scripts/export_review_evidence_v05.py', 'scripts/definition_evidence_v2.mjs',
           'scripts/export_definition_evidence_v2.py', 'scripts/validation_utils.mjs',
           'scripts/score_normalization.mjs', 'scripts/validation_budget_v05.mjs']
helper_hashes = {name: sha((ROOT / name).read_bytes()) for name in helpers}
changes_bytes = (json.dumps(changes, ensure_ascii=False, indent=2) + '\n').encode('utf8')
manifest['evidence_verifier_pre_run_revision'] = {
    'version': 'definition-provenance-2', 'created_at': now,
    'previous_manifest_sha256': sha(manifest_bytes), 'helper_sha256': helper_hashes,
    'clarifications_sha256': sha(changes_bytes), 'financial_scorer_unchanged': True,
    'gold_unchanged': True, 'model_calls': 0,
}
new_manifest_bytes = (json.dumps(manifest, ensure_ascii=False, indent=2) + '\n').encode('utf8')
zip_path = ROOT / 'samples/financial-holdout-v0.5-evaluation.zip'
old_zip_bytes = zip_path.read_bytes()
assert sha(old_zip_bytes) == expected['sha256']
archive = ROOT / 'samples/archive/financial-holdout-v0.5-evaluation-execution-package-2.zip'
if archive.exists() or (ROOT / 'benchmark/versions/v0.5-execution-release-3.json').exists():
    raise RuntimeError('Release already exists')
archive.parent.mkdir(exist_ok=True)
shutil.copy2(zip_path, archive)
release = {'version': 'execution-package-3', 'created_at': now, 'status': 'prepared_not_run',
           'model_calls': 0, 'previous_zip': str(archive.relative_to(ROOT)).replace('\\', '/'),
           'previous_zip_sha256': sha(old_zip_bytes), 'gold_sha256': gold_before,
           'financial_scorer_sha256': score_before, 'helper_sha256': helper_hashes,
           'previous_manifest_sha256': sha(manifest_bytes), 'manifest_sha256': sha(new_manifest_bytes),
           'change': 'Definition provenance only: exact reversible quotation locations, original Pi ownership, recorded partial repair and batch registration; independent financial scoring and every original input/gold unchanged.'}
replace = {name: (ROOT / name).read_bytes() for name in helpers}
replace.update({'SCORER_PRE_RUN_CHANGES.json': changes_bytes, 'manifest.json': new_manifest_bytes,
                'EXECUTION-RELEASE.json': json.dumps(release, ensure_ascii=False, indent=2).encode('utf8')})
temporary = zip_path.with_suffix('.release3.tmp.zip')
unchanged = []
with zipfile.ZipFile(archive) as old, zipfile.ZipFile(temporary, 'x', zipfile.ZIP_DEFLATED, compresslevel=9) as new:
    names = set(old.namelist())
    for info in old.infolist():
        raw = replace.pop(info.filename, old.read(info.filename))
        new.writestr(info.filename, raw)
        if raw == old.read(info.filename): unchanged.append(info.filename)
    for name, raw in replace.items(): new.writestr(name, raw)
with zipfile.ZipFile(temporary) as new, zipfile.ZipFile(archive) as old:
    assert new.testzip() is None
    for name in unchanged: assert new.read(name) == old.read(name)
    assert sha(new.read('gold.json')) == gold_before
    assert sha(new.read('scripts/score_financial_tables_v05.mjs')) == score_before
    assert sha(new.read('scorer/score_financial_tables_v05.mjs')) == score_before
manifest_path.write_bytes(new_manifest_bytes)
change_path.write_bytes(changes_bytes)
os.replace(temporary, zip_path)
release.update(zip=str(zip_path.relative_to(ROOT)).replace('\\', '/'), sha256=sha(zip_path.read_bytes()),
               bytes=zip_path.stat().st_size, unchanged_original_entries=len(unchanged))
with (ROOT / 'benchmark/versions/v0.5-execution-release-3.json').open('x', encoding='utf8') as stream:
    json.dump(release, stream, ensure_ascii=False, indent=2)
print(json.dumps({key: release[key] for key in ['zip', 'sha256', 'bytes', 'unchanged_original_entries', 'gold_sha256', 'financial_scorer_sha256']}))
