import json,re,sqlite3
from pathlib import Path
from collections import Counter
BASE=Path(__file__).parent;ROOT=BASE.parents[1];OUT=ROOT/'docs/evidence/n4-adoption-preflight-20261008'
rows=json.loads((BASE/'summary.json').read_text(encoding='utf-8'));manifest=json.loads((BASE/'manifest.json').read_text(encoding='utf-8'))
assert len(rows)==12
requests=Counter();tools=Counter()
for r in rows:
    assert r['status']=='completed'
    d=BASE/'runs'/(r['case']+'-'+r['profile'])
    start=json.loads((d/'start.json').read_text(encoding='utf-8'))
    assert start['code']==manifest['code_commit']
    case=next(c for c in manifest['cases'] if c['id']==r['case'])
    assert start['question']==case['prompt']+'\n'+manifest['common_suffix']
    p=[json.loads(line)['payload'] for line in (d/'payloads.jsonl').read_text(encoding='utf-8').splitlines()]
    assert len(p)==len(r['requests'])==r['usage']['calls'],d
    assert sum(x['reasoning']['effort']=='low' for x in p)==1
    for x in p:
        assert x['model']=='gpt-6-luna'
        if x['reasoning']['effort']=='high':assert len(x['tools'])==(40 if r['profile']=='financial' else 13)
    assert r['usage']['input']==r['usage']['uncachedInput']+r['usage']['cacheRead']+r['usage']['cacheWrite']
    requests[r['profile']]+=len(p);tools[r['profile']]+=len(r['calls'])
for name in ['adoption-one-page.md','findings.md','method.md','cases.md']:
    for dest in re.findall(r'\[[^\]]+\]\(([^)]+)\)',(OUT/name).read_text(encoding='utf-8')):
        if '://' not in dest and not dest.startswith('#'):assert (OUT/dest.split('#')[0]).exists(),(name,dest)
db=sqlite3.connect((BASE/'seed/finance.sqlite').resolve().as_uri()+'?mode=ro',uri=True)
pages={'d84573bf6b584e7e874faa4c6adf454a':[7,8,19,95,96], 'ab25c52089fd4db89fba046c9c811c46':[28,32,33,46,47], '3d9d0befd8374eed9a7488dbd8dd00d2':[9,11,12,13,23]}
sources=[]
for doc,ns in pages.items():
    for page in ns:
        text=db.execute('SELECT text FROM pages WHERE document_id=? AND page=?',(doc,page)).fetchone()[0]
        sources.append({'document_id':doc,'pdf_page':page,'text':text})
(OUT/'reviewed-source-pages.json').write_text(json.dumps(sources,ensure_ascii=False,indent=2),encoding='utf-8')
record={'sessions_completed':12,'frozen_commit':manifest['code_commit'],'model_requests':dict(requests),'tool_calls':dict(tools),'all_prompts_match_manifest':True,'all_request_reasoning_matches_protocol':True,'all_main_tool_counts_match_profiles':True,'unknown_usage_requests':sum(r['usage']['unknownCalls'] for r in rows),'evidence_links_resolve':True,'note':'Offline evidence consistency only; financial review remains the manual observations in cases.md.'}
(OUT/'validation.json').write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(record,ensure_ascii=False,indent=2))
