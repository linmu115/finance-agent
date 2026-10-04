"""Read-only snapshot of persisted source evidence; never constructs FinanceService."""
import argparse
import hashlib
import json
import sqlite3
from pathlib import Path

parser=argparse.ArgumentParser()
parser.add_argument("--project",required=True)
parser.add_argument("--output",required=True)
args=parser.parse_args()
root=Path(__file__).resolve().parents[1]
db=sqlite3.connect((root/"data/finance.sqlite").as_uri()+"?mode=ro",uri=True)
db.row_factory=sqlite3.Row
tables={}
for table in ("documents","pages","source_tables","normalization_batches","prepared_documents"):
    query=(f"SELECT * FROM {table} WHERE project_id=?" if table=="documents" else
           f"SELECT * FROM {table} WHERE document_id IN (SELECT document_id FROM documents WHERE project_id=?)")
    rows=[dict(row) for row in db.execute(query,(args.project,))]
    tables[table]=sorted(rows,key=lambda row:json.dumps(row,sort_keys=True,ensure_ascii=False))
payload={"project_id":args.project,"source":"SQLite mode=ro; no service initialization","tables":tables}
payload["tables_sha256"]=hashlib.sha256(json.dumps(tables,sort_keys=True,ensure_ascii=False,separators=(",",":")).encode()).hexdigest()
Path(args.output).parent.mkdir(parents=True,exist_ok=True)
with Path(args.output).open("x",encoding="utf-8") as stream:json.dump(payload,stream,ensure_ascii=False,indent=2)
print(json.dumps({"output":args.output,"tables_sha256":payload["tables_sha256"],"counts":{key:len(rows) for key,rows in tables.items()}}))
