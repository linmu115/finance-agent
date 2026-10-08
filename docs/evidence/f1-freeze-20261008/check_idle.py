"""Read live task metadata only; no documents, facts, answers or state writes."""
import json
from pathlib import Path
import sqlite3
import sys
from datetime import datetime
from urllib.request import build_opener, ProxyHandler

root=Path(__file__).resolve().parents[3]
opener=build_opener(ProxyHandler({}))
def get(route):
    with opener.open('http://127.0.0.1:3001'+route,timeout=15) as response:return json.load(response)

active=[]
for project in get('/api/projects')['projects']:
    for chat in get('/api/projects/'+project['id']+'/conversations')['conversations']:
        if chat.get('activeRunId'):active.append({'project_id':project['id'],'conversation_id':chat['id'],'run_id':chat['activeRunId']})
db=sqlite3.connect((root/'data/active/finance.sqlite').as_uri()+'?mode=ro',uri=True)
db.row_factory=sqlite3.Row
with db:
    analysis=[dict(r) for r in db.execute("SELECT run_id,project_id,json_extract(state_json,'$.status') AS status FROM analysis_jobs WHERE coalesce(json_extract(state_json,'$.status'),json_extract(state_json,'$.state')) IN ('queued','running')")]
    parsing=[dict(r) for r in db.execute("SELECT job_id,project_id,state FROM jobs WHERE state IN ('queued','running','parsing')")]
    persisted=[dict(r) for r in db.execute("SELECT project_id,key AS run_id,json_extract(value_json,'$.status') AS status FROM app_state WHERE kind='runs' AND json_extract(value_json,'$.status') IN ('queued','running')")]
db.close()
result={'checked_at':datetime.now().astimezone().isoformat(),'active_runs':active,'persisted_active_runs':persisted,
        'active_analysis_jobs':analysis,'active_parse_jobs':parsing,'pending_approval_count':len(get('/api/approvals')['requests']),
        'health':get('/api/health'),'launcher':json.loads((root/'data/active/runtime/launcher-3001.json').read_text(encoding='utf-8-sig'))}
result['idle']=not any([active,persisted,analysis,parsing,result['pending_approval_count']])
out=Path(sys.argv[1]);out.parent.mkdir(parents=True,exist_ok=True)
out.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
print(json.dumps(result,ensure_ascii=False,indent=2))
sys.exit(0 if result['idle'] else 2)
