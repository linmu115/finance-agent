"""Read-only replay of the real missed queries; no document or record updates."""
import importlib.util
import json
import sqlite3
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from service.research_ingestion import ResearchIngestionMixin
trial=ROOT/'data/evaluation/pi-analysis-20261006'
candidate=trial/'followup-candidate/service/research_ingestion.py'
spec=importlib.util.spec_from_file_location('service.research_query_candidate',candidate)
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)


class ReadOnlyStore:
    def connect(self):
        db=sqlite3.connect((ROOT/'data/active/finance.sqlite').as_uri()+'?mode=ro',uri=True)
        db.row_factory=sqlite3.Row
        return db
    def project(self,project_id):
        with self.connect() as db:
            if not db.execute('SELECT 1 FROM projects WHERE project_id=?',(project_id,)).fetchone():raise ValueError('missing project')


service=SimpleNamespace(store=ReadOnlyStore());results=[]
for query in ('FCFF','折旧 摊销 资本开支 营运资金'):
    filters={'document_id':'585db15e768043b7b465d1af7c690e90','query':query,'latest_per_series':False}
    row={'query':query}
    for name,method in [('before',ResearchIngestionMixin.query_research_records),('candidate',module.ResearchIngestionMixin.query_research_records)]:
        result=method(service,'374beac2-a970-4972-b210-e91018bbd6e6',filters,limit=200)['data']
        row[name]={'total':result['total'],'metrics':sorted({r['metric'] for r in result['items'] if r.get('metric')}),'pages':sorted({r['source_ref']['page'] for r in result['items']})}
    results.append(row)
(trial/'query-recall-check.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(results,ensure_ascii=False))
