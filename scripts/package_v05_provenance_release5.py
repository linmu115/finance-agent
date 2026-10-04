"""Final pre-first-run historical-limit evidence contract; old packs retained."""
import hashlib
import json
import os
import shutil
import zipfile
from datetime import datetime, timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1];SUITE=ROOT/'benchmark/versions/v0.5-holdout';sha=lambda b:hashlib.sha256(b).hexdigest();now=datetime.now(timezone.utc).isoformat()
if any((ROOT/f'benchmark/results/holdout-v05-{arm}-first-run.lock.json').exists() for arm in ('financial','generic')):raise RuntimeError('Formal first run already locked')
previous=json.loads((ROOT/'benchmark/versions/v0.5-execution-release-4.json').read_text(encoding='utf8'))
archive=ROOT/'samples/archive/financial-holdout-v0.5-evaluation-execution-package-4.zip';destination=ROOT/'samples/financial-holdout-v0.5-evaluation.zip';release_file=ROOT/'benchmark/versions/v0.5-execution-release-5.json'
if archive.exists() or release_file.exists():raise RuntimeError('Release already exists')
assert sha(destination.read_bytes())==previous['sha256']
gold=sha((SUITE/'gold.json').read_bytes());scorer=sha((ROOT/'scripts/score_financial_tables_v05.mjs').read_bytes())
assert gold==previous['gold_sha256'] and scorer==previous['financial_scorer_sha256']
changes=json.loads((SUITE/'SCORER_PRE_RUN_CHANGES.json').read_text(encoding='utf8'));assert changes['version']=='v0.5-pre-run-clarifications-3'
changes['version']='v0.5-pre-run-clarifications-4'
changes['changes'].append('Before first formal prediction, a separately recorded verified_historical_output_limit can justify a zero-new-call split only when the original audit bytes, unique request/result, original Pi owner/processing/project, complete message hash, input group hash, inference settings, original length stop/usage and current source fingerprints match. split_attempts must link the receipt and partition the parent groups exactly. Historical failures and usage retain original ownership and are not counted as newly accepted outputs or new model calls. Independent receipt validation does not claim to have executed the current split or re-generated the full current LangExtract template.')
changes['historical_limit_pre_run_revision']={'created_at':now,'model_calls':0,'validation':['tests/definition-evidence-v2.test.ts:9 positive/negative tests','tests/review-evidence-v05.test.ts:3 retained regression tests','benchmark/results/known-definition-clean2-historical-limit-independent-v2.json'],'financial_scorer_unchanged':True,'gold_unchanged':True}
change_bytes=(json.dumps(changes,ensure_ascii=False,indent=2)+'\n').encode('utf8')
manifest_before=(SUITE/'manifest.json').read_bytes();manifest=json.loads(manifest_before);helpers={name:sha((ROOT/name).read_bytes()) for name in previous['helper_sha256']}
manifest['evidence_verifier_pre_run_revision'].update(version='definition-provenance-2-historical-limits',created_at=now,previous_manifest_sha256=sha(manifest_before),helper_sha256=helpers,clarifications_sha256=sha(change_bytes))
manifest_bytes=(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n').encode('utf8')
release={'version':'execution-package-5','created_at':now,'status':'prepared_not_run','model_calls':0,'previous_zip':str(archive.relative_to(ROOT)).replace('\\','/'),'previous_zip_sha256':previous['sha256'],'gold_sha256':gold,'financial_scorer_sha256':scorer,'helper_sha256':helpers,'previous_manifest_sha256':sha(manifest_before),'manifest_sha256':sha(manifest_bytes),'change':'Source proof only: auditable original length receipt and zero-new-call exact split linkage; all former caches/financial gold/scoring unchanged.'}
replace={name:(ROOT/name).read_bytes() for name in helpers};replace.update({'SCORER_PRE_RUN_CHANGES.json':change_bytes,'manifest.json':manifest_bytes,'EXECUTION-RELEASE.json':json.dumps(release,ensure_ascii=False,indent=2).encode('utf8')})
shutil.copy2(destination,archive);temporary=destination.with_suffix('.release5.tmp.zip');unchanged=[]
with zipfile.ZipFile(archive) as old,zipfile.ZipFile(temporary,'x',zipfile.ZIP_DEFLATED,compresslevel=9) as new:
    for item in old.infolist():
        former=old.read(item.filename);raw=replace.pop(item.filename,former);new.writestr(item.filename,raw)
        if raw==former:unchanged.append(item.filename)
    for name,raw in replace.items():new.writestr(name,raw)
with zipfile.ZipFile(temporary) as new,zipfile.ZipFile(archive) as old:
    assert new.testzip() is None
    for name in unchanged:assert new.read(name)==old.read(name)
    assert sha(new.read('gold.json'))==gold and sha(new.read('scripts/score_financial_tables_v05.mjs'))==scorer
(SUITE/'SCORER_PRE_RUN_CHANGES.json').write_bytes(change_bytes);(SUITE/'manifest.json').write_bytes(manifest_bytes);os.replace(temporary,destination)
release.update(zip=str(destination.relative_to(ROOT)).replace('\\','/'),sha256=sha(destination.read_bytes()),bytes=destination.stat().st_size,unchanged_original_entries=len(unchanged))
with release_file.open('x',encoding='utf8') as f:json.dump(release,f,ensure_ascii=False,indent=2)
print(json.dumps({k:release[k] for k in ['zip','sha256','bytes','unchanged_original_entries','gold_sha256','financial_scorer_sha256']}))
