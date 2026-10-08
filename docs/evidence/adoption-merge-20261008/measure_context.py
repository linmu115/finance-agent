"""Compare isolated native Pi snapshots; no inference or live service access."""
import hashlib
import json
import math
from pathlib import Path
import re

HERE=Path(__file__).resolve().parent
before=json.loads((HERE.parent/'evaluation-isolation-20261008/context.json').read_text(encoding='utf8'))
after=json.loads((HERE/'context.json').read_text(encoding='utf8'))
compact=lambda v:json.dumps(v,ensure_ascii=False,separators=(',',':'))
sha=lambda s:hashlib.sha256(s.encode('utf8')).hexdigest()

def structural(value):
    if isinstance(value,dict):return {k:structural(v) for k,v in value.items() if k!='description'}
    if isinstance(value,list):return [structural(v) for v in value]
    return value

def descriptions(value):
    if isinstance(value,dict):
        if 'description' in value:yield value['description']
        for v in value.values():yield from descriptions(v)
    elif isinstance(value,list):
        for v in value:yield from descriptions(v)

def count(text):
    return {'chars':len(text),'rough_tokens':math.ceil(sum(.25 if ord(c)<128 else 1 for c in text))}

def measure(p):
    tool_text=''.join(t['description'] for t in p['tools'])
    schema_text=''.join(d for t in p['tools'] for d in descriptions(t['parameters']))
    system=re.sub(r'<cwd>\n.*?\n</cwd>','<cwd>\n<WORKSPACE>\n</cwd>',p['system'],flags=re.S)
    return {'system':count(p['system']),'tool_descriptions':count(tool_text),'schema_descriptions':count(schema_text),
            'instruction_text':count(p['system']+tool_text+schema_text),'full_context':count(p['system']+compact(p['tools'])),
            'system_normalized_sha256':sha(system),'tools_sha256':sha(compact(p['tools'])),
            'context_normalized_sha256':sha(system+compact(p['tools']))}

result={'method':'Native Pi snapshots without prompt; full context=system plus compact JSON tool definitions, Unicode code points. Rough tokens=ceil(ASCII/4 + non-ASCII), not tokenizer or billing. Hashes normalize only cwd to <WORKSPACE>. No transport envelope/history/dynamic tool results.',
        'base_commit':'e2c1f460b21e91cd152b20e516d2e9e3f3574f55','merged_target':'f945e76f5a6f2aacb6ff8a6137ef7766428dc7c5','profiles':{}}
for name,new in after['profiles'].items():
    old=before['profiles'][name]
    assert [t['name'] for t in old['tools']]==[t['name'] for t in new['tools']]
    assert structural(old['tools'])==structural(new['tools'])
    tools={t['name']:t for t in new['tools']}
    assert 'delivery.id' in tools['get_artifact']['description']
    for entry in ('{{表名.行键.列名}}','{{table:表名}}','source_run_id+params','edits','get_artifact'):
        assert entry in tools['run_analysis']['description']
    assert ('financial_workpaper' in tools)==(name=='financial')
    assert not any('isolation_key' in t['parameters'].get('properties',{}) for t in new['tools'])
    a,b=measure(old),measure(new)
    result['profiles'][name]={'tool_count':len(tools),'tool_schema_structure_unchanged':True,'shared_entrypoints_visible':True,
        'before':a,'after':b,'full_context_delta':{k:b['full_context'][k]-a['full_context'][k] for k in ('chars','rough_tokens')}}
(HERE/'context-measurements.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
print(json.dumps({k:{'tools':v['tool_count'],'before':v['before']['full_context'],'after':v['after']['full_context'],'delta':v['full_context_delta']} for k,v in result['profiles'].items()},ensure_ascii=False,indent=2))
