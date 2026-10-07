"""Count and compare actual before/after native Pi snapshots, not a proposal."""
import json,math
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];folder=ROOT/'docs/evidence/a3-a5-b4-20261007'
before=json.loads((folder/'before-context.json').read_text(encoding='utf8'))
after=json.loads((folder/'after-context.json').read_text(encoding='utf8'))
def strip_descriptions(value):
    if isinstance(value,dict):return {k:strip_descriptions(v) for k,v in value.items() if k!='description'}
    if isinstance(value,list):return [strip_descriptions(v) for v in value]
    return value
def descriptions(value,path=''):
    if isinstance(value,dict):
        if 'description' in value:yield path,value['description']
        for key,v in value.items():yield from descriptions(v,path+'/'+key)
    elif isinstance(value,list):
        for i,v in enumerate(value):yield from descriptions(v,path+'/'+str(i))
def count(s):return {'chars':len(s),'rough_tokens':math.ceil(sum(.25 if ord(c)<128 else 1 for c in s))}
def measure(profile):
    tool_text=''.join(t['description'] for t in profile['tools'])
    schema_text=''.join(d for t in profile['tools'] for _,d in descriptions(t['parameters']))
    return {'system':count(profile['system']),'tool_descriptions':count(tool_text),'schema_descriptions':count(schema_text),
            'instruction_text':count(profile['system']+tool_text+schema_text),
            'full_context':count(profile['system']+json.dumps(profile['tools'],ensure_ascii=False,separators=(',',':'))),
            'tools':{t['name']:{'description':count(t['description']),'schema_full':count(json.dumps(t['parameters'],ensure_ascii=False,separators=(',',':'))),
                              'schema_descriptions':[{'path':p,'text':d,**count(d)} for p,d in descriptions(t['parameters'])]} for t in profile['tools']}}
result={'method':'Actual native Pi session snapshots before and after implementation. Unicode code points; rough tokens=ceil(ASCII/4 + non-ASCII). No tokenizer/billing claim; no model inference. Full context includes compact JSON schemas; transport envelope, history and dynamic tool results excluded.','profiles':{}}
for name,old in before['profiles'].items():
    new=after['profiles'][name]
    assert [t['name'] for t in old['tools']]==[t['name'] for t in new['tools']]
    assert [strip_descriptions(t['parameters']) for t in old['tools']]==[strip_descriptions(t['parameters']) for t in new['tools']]
    tools={t['name']:t for t in new['tools']}
    shared=tools['run_analysis']['description']
    for entry in ('{{表名.行键.列名}}','{{table:表名}}','source_run_id+params','edits','get_artifact'):assert entry in shared,(name,entry)
    assert 'rows' in tools['get_artifact']['parameters']['properties']
    assert not any('consistency' in t for t in tools)
    if name=='prepared':
        assert 'financial_workpaper' not in tools
        assert 'model_refs' not in tools['run_analysis']['parameters']['properties']
        assert 'Finance:' not in shared
    else:
        assert 'statement_analysis' in new['system'] and 'dcf_fcf' in new['system']
        assert '不罗列检查过程和状态字段' in new['system']
        assert '自绘图仍须检查' not in new['system']
        assert '柱形以零为基准，缺失留空' in new['system']
    a,b=measure(old),measure(new)
    result['profiles'][name]={'tools_count':len(tools),'tool_and_schema_structure_unchanged':True,'shared_entrypoints_visible':True,'before':a,'after':b,
        'reductions':{key:{metric:round(1-b[key][metric]/a[key][metric],6) for metric in ('chars','rough_tokens')} for key in ('instruction_text','full_context')}}
(folder/'b4-measurements.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
print(json.dumps({k:{'tools':v['tools_count'],'before':v['before']['full_context'],'after':v['after']['full_context'],'reductions':v['reductions']} for k,v in result['profiles'].items()},ensure_ascii=False,indent=2))
