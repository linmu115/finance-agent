"""Lossless wire-codec check on saved real mappings; read-only, no model calls."""
import copy
import json
import sqlite3
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from service.semantic import materialize, table_batches
from service.semantic_compact import expand_mappings

root=Path(__file__).resolve().parents[1];doc='1f94f25a3cb74d528f10ddac0be06a0d'
parsed=json.loads((root/'data/indexes/b43ae45c-d96b-43b6-ab5b-04306c0eb142'/f'{doc}.json').read_text(encoding='utf-8'))['parsed']
batches={tuple((p['table']['index'],r) for p in batch for r in p['rows']):batch for batch in table_batches(parsed)}
with sqlite3.connect('file:'+str(root/'data/finance.sqlite')+'?mode=ro',uri=True) as db:
    saved=[json.loads(r[0]) for r in db.execute('SELECT result_json FROM normalization_batches WHERE document_id=?',(doc,))]
count=0;errors=[];before_chars=0;after_chars=0;legacy_rows=0;facts_checked=0
for detail in saved:
    key=tuple((int(t.split(':t')[-1]),r) for t,r in detail['coordinates']);batch=batches[key]
    original=detail['extractions'];wire=copy.deepcopy(original);schemas={}
    for ex in wire:
        attrs=ex['attributes']
        if ex['class']!='table_schema':continue
        cols=json.loads(attrs.get('columns_json') or '[]')
        if not cols:continue
        schemas[ex['text']]=copy.deepcopy(cols)
        common={k:v for k,v in cols[0].items() if k in {'unit','currency','version','dimensions'} and all(c.get(k)==v for c in cols)}
        attrs['column_defaults_json']=json.dumps(common,ensure_ascii=False,separators=(',',':'))
        attrs['columns_json']=json.dumps([{k:v for k,v in c.items() if k not in common} for c in cols],ensure_ascii=False,separators=(',',':'))
    for ex in wire:
        attrs=ex['attributes']
        if ex['class']!='financial_row' or not attrs.get('columns_json'):continue
        cols=json.loads(attrs['columns_json']);base=schemas.get(ex['text'].split(':')[0]+']]',[])
        if {c.get('column') for c in cols}!={c.get('column') for c in base} or len({c.get('column') for c in cols})!=len(cols):legacy_rows+=1;continue
        defaults={c['column']:c for c in base};patches=[]
        for c in cols:
            inherited=defaults[c['column']]
            delta={k:v for k,v in c.items() if k=='column' or inherited.get(k)!=v}
            delta.update({k:None for k in inherited if k not in c and k!='column'})
            if len(delta)>1:patches.append(delta)
        attrs.pop('columns_json');attrs['column_overrides_json']=json.dumps({'columns':patches},ensure_ascii=False,separators=(',',':'))
    try:
        before=materialize(original,batch,doc,detail['model']);after=materialize(expand_mappings(wire),batch,doc,detail['model'])
        if before!=after:errors.append({'batch':key[0],'error':'facts_or_issues_changed'})
        facts_checked+=len(before[0]);count+=1
    except Exception as error:errors.append({'batch':key[0],'error':type(error).__name__+':'+str(error)})
    before_chars+=len(json.dumps(original,ensure_ascii=False,separators=(',',':')))
    after_chars+=len(json.dumps(wire,ensure_ascii=False,separators=(',',':')))
result={'batches_checked':count,'facts_checked':facts_checked,'errors':errors,'legacy_rows_kept_complete':legacy_rows,
        'original_mapping_characters':before_chars,'compact_mapping_characters':after_chars,
        'note':'Deterministic codec round-trip, not model-generated compression or token savings. No database writes.'}
(root/'data/retests/yili-20261004/wire-roundtrip-verification.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(result));sys.exit(bool(errors))
