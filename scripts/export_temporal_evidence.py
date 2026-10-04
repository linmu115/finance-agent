"""Read-only export of accepted period-review evidence, never imports Store."""
import argparse
import json
from pathlib import Path
import sqlite3

parser = argparse.ArgumentParser()
parser.add_argument("--project", required=True)
parser.add_argument("--review", required=True)
args = parser.parse_args()
database = Path(__file__).resolve().parents[1] / "data/finance.sqlite"
with sqlite3.connect(database.as_uri()+"?mode=ro", uri=True) as connection:
    row=connection.execute("SELECT report_json FROM temporal_project_reviews WHERE project_id=? AND review_id=?",(args.project,args.review)).fetchone()
    if not row:
        raise RuntimeError("accepted_temporal_review_not_found")
    review=json.loads(row[0]); chunks=[]
    for phase,field in (("profiles","profile_audits"),("corrections","correction_audits")):
        for audit in review.get(field,[]):
            row=connection.execute("SELECT result_json FROM temporal_review_cache WHERE cache_key=?",(audit["cache_key"],)).fetchone()
            chunks.append({"phase":phase,"audit":audit,"cached":json.loads(row[0]) if row else None})
print(json.dumps({"source":"host_sqlite_readonly","review":review,"chunks":chunks},ensure_ascii=False))
