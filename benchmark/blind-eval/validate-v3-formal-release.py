"""Offline final release checks against sealed evidence; no new runs or scoring."""
import hashlib
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
BASE=ROOT/'data/evaluation/blind-eval-F21-formal-private-20261009'
PUBLIC=ROOT/'data/evaluation/blind-eval-F21-formal-20261009'

def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()

protocol=read(PUBLIC/'protocol-freeze.json')
assert all(sha(ROOT/p)==value for p,value in protocol['protocolFiles'].items())
state=read(BASE/'experiment.json');summary=read(PUBLIC/'formal-results.json')
assert len(state['runs'])==162 and Counter(r['status'] for r in state['runs'])=={'completed':161,'failed':1}
assert summary==read(BASE/'formal-results.json')
assert summary['deployed_commit']==state['deployedCommit']
assert Counter((r['split'],r['profile']) for r in state['runs'])==Counter({(s,p):18 for s in ['development','heldout','extension'] for p in ['original_pi','prepared','financial']})
seal=read(BASE/'all-reviews-sealed-before-unblinding.json')
assert seal['review_threads']==18 and len(seal['packets'])==9
for packet in seal['packets']:
    folder=BASE/'review-packets'/packet['packet']
    assert sha(folder/'score-seal.json')==packet['seal_sha256']
    s=read(folder/'score-seal.json')
    assert datetime.fromisoformat(s['at'])<=datetime.fromisoformat(seal['at'])
    for f in s['reviews']:
        assert sha(folder/f['path'])==sha(folder/f['sealed_copy'])==f['sha256']
for rd in ['round1','round2']:
    decoded=read(BASE/(rd+'-decoded.json'))
    assert len(decoded)==162 and len({x['label'] for x in decoded})==162
    for s in ['development','heldout','extension']:
        for p in ['original_pi','prepared','financial']:
            rows=[x for x in decoded if x['split']==s and x['profile']==p]
            g=summary['splits'][s]['groups'][rd][p]
            assert sum(bool(x['material_defects']) for x in rows)==g['material_defective_cases']
            assert sum(len(x['material_defects']) for x in rows)==g['reviewer_material_entries']
    exported=read(PUBLIC/'development-extension-reviews.json')[rd]
    assert len(exported)==108 and all(x['split']!='heldout' and not x['task'].startswith('BH') for x in exported)
assert all(x['split']!='heldout' for x in read(PUBLIC/'development-extension-disagreements-originals.json'))
for row in read(PUBLIC/'heldout-disagreement-indicators.json'):
    assert set(row)=={'split','label','profile','task','material_presence','delta'}
usage=read(BASE/'usage-bounds-final.json')
assert len(usage['rows'])==162 and sum(r['unknown_calls'] for r in usage['rows'])==8
assert sum(t['request_count'] for t in summary['usage_totals'])==1861
assert sum(t['input_lower'] for t in summary['usage_totals'])==89277686
assert sum(t['output_lower'] for t in summary['usage_totals'])==1397031
delivery=read(BASE/'delivery-supplement.json')
assert len(delivery['rows'])==162 and all(r['delivery_collected'] and r['a5_observed'] for r in delivery['rows'])
assert sum(r['download_failed'] for r in delivery['rows'])==0
assert sum(r['downloaded'] for r in delivery['rows'])==3072
assert sum(r['numeric_explicit_cells'] or 0 for r in delivery['rows'])==1972
assert len(read(BASE/'replay-results.json'))==202
assert Counter(r['status'] for r in read(BASE/'replay-results.json'))=={'succeeded':202}
assert Counter(r['status'] for r in read(BASE/'bundle-replay-results.json'))=={'failed':12}
report=ROOT/'benchmark/blind-eval/F21_FORMAL_REPORT.md'
assert report.read_bytes()==(PUBLIC/'TECHNICAL_REPORT.md').read_bytes()
result={'at':datetime.now(timezone.utc).isoformat(),'passed':True,'participants':162,'raw_review_seals':18,
    'protocol_files_unchanged':len(protocol['protocolFiles']),'unknown_requests':8,
    'public_heldout_review_prose_exported':False,'heldout_public_structure_checked':True,
    'all_original_review_hashes_unchanged':True,'no_scores_revised':True,
    'technical_report_sha256':sha(report),'results_sha256':sha(PUBLIC/'formal-results.json'),
    'scores_and_disagreements':'Both independent originals retained; no adjudication or averaging.',
    'coverage':'F1_X7 round2 still-delivered auxiliary narrative incompletely inspected; recorded without score alteration.',
    'live_runtime_or_database_access':False}
for p in [BASE/'final-release-validation.json',PUBLIC/'final-release-validation.json']:
    p.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps(result,ensure_ascii=False))
