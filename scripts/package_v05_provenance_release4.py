"""Freeze pre-first-run partial-cache proof protocol; preserve all former bytes."""
import hashlib
import json
import os
import shutil
import zipfile
from datetime import datetime, timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1];SUITE=ROOT/'benchmark/versions/v0.5-holdout';sha=lambda b:hashlib.sha256(b).hexdigest();now=datetime.now(timezone.utc).isoformat()
for arm in ('financial','generic'):
    if (ROOT/f'benchmark/results/holdout-v05-{arm}-first-run.lock.json').exists():raise RuntimeError('Formal first run already locked')
previous=json.loads((ROOT/'benchmark/versions/v0.5-execution-release-3.json').read_text(encoding='utf8'))
archive=ROOT/'samples/archive/financial-holdout-v0.5-evaluation-execution-package-3.zip';destination=ROOT/'samples/financial-holdout-v0.5-evaluation.zip';release_file=ROOT/'benchmark/versions/v0.5-execution-release-4.json'
if archive.exists() or release_file.exists():raise RuntimeError('Release already exists')
assert sha(destination.read_bytes())==previous['sha256']
gold=sha((SUITE/'gold.json').read_bytes());scorer=sha((ROOT/'scripts/score_financial_tables_v05.mjs').read_bytes())
assert gold==previous['gold_sha256'] and scorer==previous['financial_scorer_sha256']
changes=json.loads((SUITE/'SCORER_PRE_RUN_CHANGES.json').read_text(encoding='utf8'));assert changes['version']=='v0.5-pre-run-clarifications-2'
changes['version']='v0.5-pre-run-clarifications-3'
changes['changes'].append('Before first formal prediction, provenance accepts explicit partial_coverage only when accepted and pending groups uniquely partition the original group list; accepted spans must match the original full input and each output_limit attempt must match a real same-owner length response, request ID, input hash and pending group list. Later revalidated_cached_result receipts must bind immutable cache hash/owner and explicitly name source keys and historical review IDs. Historical absent registrations remain marked missing. No pending decision, invented output or cross-owner substitution is accepted.')
changes['partial_cache_pre_run_revision']={'created_at':now,'model_calls':0,'validation':'tests/definition-evidence-v2.test.ts:8 positive/negative tests','financial_scorer_unchanged':True,'gold_unchanged':True}
change_bytes=(json.dumps(changes,ensure_ascii=False,indent=2)+'\n').encode('utf8')
manifest_before=(SUITE/'manifest.json').read_bytes();manifest=json.loads(manifest_before)
helpers={name:sha((ROOT/name).read_bytes()) for name in previous['helper_sha256']}
manifest['evidence_verifier_pre_run_revision'].update(version='definition-provenance-2-partial-receipts',created_at=now,previous_manifest_sha256=sha(manifest_before),helper_sha256=helpers,clarifications_sha256=sha(change_bytes))
manifest_bytes=(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n').encode('utf8')
release={'version':'execution-package-4','created_at':now,'status':'prepared_not_run','model_calls':0,'previous_zip':str(archive.relative_to(ROOT)).replace('\\','/'),'previous_zip_sha256':previous['sha256'],'gold_sha256':gold,'financial_scorer_sha256':scorer,'helper_sha256':helpers,'previous_manifest_sha256':sha(manifest_before),'manifest_sha256':sha(manifest_bytes),'change':'Source proof only: explicit original/pending group partition, actual typed-length attempts and original-owner revalidation receipts. Financial gold and scoring remain unchanged.'}
replace={name:(ROOT/name).read_bytes() for name in helpers};replace.update({'SCORER_PRE_RUN_CHANGES.json':change_bytes,'manifest.json':manifest_bytes,'EXECUTION-RELEASE.json':json.dumps(release,ensure_ascii=False,indent=2).encode('utf8')})
shutil.copy2(destination,archive);temporary=destination.with_suffix('.release4.tmp.zip');unchanged=[]
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
