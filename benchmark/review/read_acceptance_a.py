"""Blind source review helper: reads only agent_input, never evaluator or predictions."""
import json
from pathlib import Path
import sys
root=Path(__file__).resolve().parents[1]/'agent_input'
cases=sorted([json.loads(s) for s in (root/'cases.jsonl').read_text(encoding='utf-8').splitlines() if s.strip()],key=lambda x:x['id'])
cases=[c for c in cases if c['split']=='acceptance' and c['id'].startswith('finqa_')][:40]
start=int(sys.argv[1]);stop=int(sys.argv[2])
for index,case in enumerate(cases[start:stop],start):
    data=json.loads((root/case['allowed_assets'][0]).read_text(encoding='utf-8'))
    print('\nCASE',index,case['id'],'QUESTION',case['question'])
    print('\n'.join(r['id'].split(':')[-1]+' '+repr(r['cells']) for r in data['table']))
    print('\n'.join(t['id'].split(':')[-1]+' '+t['text'] for t in data['text']))
