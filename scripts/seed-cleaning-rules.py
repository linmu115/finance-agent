"""Initialize an isolated experiment with rule rows, never source data."""
import json
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from service.store import Store

rules=json.loads(Path(sys.argv[1]).read_text(encoding='utf-8'))
store=Store(sys.argv[2])
with store.connect(write=True) as db:
    for r in rules:
        db.execute('INSERT OR IGNORE INTO cleaning_rules VALUES(?,?,?,?,?)',tuple(r[k] for k in ('signature','version','rule_id','mapping_json','created_at')))
print(json.dumps({'seeded_rules':len(rules)}))
