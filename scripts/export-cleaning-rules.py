"""Revalidate one explicitly named scratch trial and export mappings only.

Used when the rule format changes during development; no original trial writes.
The next trial imports only the value-free rule rows, not documents or facts.
"""
import json
import re
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from service.cleaning_rules import compile_rule, shape, digest, VERSION
from service.semantic import materialize
from service.cleaning_mapping import mapping_issues
from service.store import utcnow

root=Path(sys.argv[1]).resolve();output=Path(sys.argv[2]).resolve()
run=json.loads((root/'run.json').read_text(encoding='utf-8'))
db=sqlite3.connect((root/'app-data/finance.sqlite').as_uri()+'?mode=ro',uri=True)
parsed=json.loads(db.execute('SELECT prepared_json FROM prepared_documents WHERE document_id=?',(run['documentId'],)).fetchone()[0])
tables={t['index']:t for t in parsed['tables']};rules=[]
for raw, in db.execute('SELECT result_json FROM normalization_batches WHERE document_id=?',(run['documentId'],)):
    saved=json.loads(raw);index=saved.get('script_table')
    if index not in tables:continue
    ext=saved.get('extractions',[]);schemas=[e['attributes'] for e in ext if e['class']=='table_schema']
    if not schemas:continue
    schema=schemas[0];table=tables[index]
    rows=[{'row':int(re.search(r':R(\d+)',e['text'])[1]),'attributes':e['attributes']} for e in ext if e['class']=='financial_row']
    facts,issues=materialize(ext,[{'table':table,'rows':list(range(1,len(table['rows'])+1))}],run['documentId'],'offline-rule-export')
    issues+=mapping_issues(table,schema,rows,page_text=next(p['text'] for p in parsed['pages'] if p['page']==table['page']),facts=facts)
    item={'schema':schema,'mapping':rows,'issues':issues,'exclusion_reason':schema.get('statement')=='nonfinancial'}
    rule=compile_rule(parsed,table,item)
    if rule:
        signature=shape(parsed,table);rule_id=digest([VERSION,signature,rule])
        rules.append({'signature':signature,'version':VERSION,'rule_id':rule_id,'mapping_json':json.dumps(rule,ensure_ascii=False),'created_at':utcnow()})
output.write_text(json.dumps(rules,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'rules':len(rules),'version':VERSION,'source_trial':root.name,'output':str(output)}))
