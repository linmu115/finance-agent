"""Read-only observation of the single authorized production acceptance run."""
import argparse
import collections
import datetime as dt
import json
from pathlib import Path
import shutil
import sqlite3
import time
import sys

import requests

OUT = Path(__file__).resolve().parents[1] / ("tmp/yili-q3-production-20261008" if "--quarterly" in sys.argv else "tmp/yili-full-production-20261008")
DATA = Path(r"D:\AI\财报agent\data\active")
M = json.loads((OUT / "start.json").read_text("utf-8"))
session = requests.Session()
session.trust_env = False

def save(name, value):
    (OUT / name).write_text(json.dumps(value, ensure_ascii=False, indent=2), "utf-8")

def snapshot():
    response = session.get("http://127.0.0.1:3001/api/runs/" + M["run_id"], timeout=30)
    response.raise_for_status()
    run = response.json()
    save("run-latest.json", run)
    db = sqlite3.connect((DATA / "finance.sqlite").as_uri() + "?mode=ro", uri=True)
    db.row_factory = sqlite3.Row
    states = [json.loads(row[0]) for row in db.execute("SELECT state_json FROM processing_runs WHERE project_id=? AND owner_run_id=? ORDER BY created_at", (M["project_id"], M["run_id"]))]
    document = dict(db.execute("SELECT * FROM documents WHERE project_id=? AND document_id=?", (M["project_id"], M["document_id"])).fetchone())
    facts = db.execute("SELECT count(*) FROM facts WHERE project_id=? AND document_id=?", (M["project_id"], M["document_id"])).fetchone()[0]
    db.close()
    save("processing-latest.json", states)
    save("document-latest.json", document)
    audit_path = DATA / "audit" / (M["run_id"] + ".jsonl")
    lines = audit_path.read_text("utf-8").splitlines(keepends=True)
    audit = [json.loads(line) for line in lines if line.endswith("\n")]
    summary = {"observed_at": dt.datetime.now(dt.timezone.utc).isoformat(), "status": run["status"], "stage": run["stage"], "error": run.get("error"), "usage": run["usage"], "document_state": document["state"], "facts": facts, "processing": [{"processing_id": st["processing_id"], "state": st["state"], "coverage": st.get("coverage"), "errors": st.get("errors"), "documents": [{k:d.get(k) for k in ["document_id", "core_tables", "completed_tables", "rule_reuse", "validation_issues"]} for d in st.get("documents", [])]} for st in states], "audit_types": dict(collections.Counter(x["type"] for x in audit)), "last_audit_time": audit[-1].get("at", audit[-1].get("time")) if audit else None}
    save("snapshot-latest.json", summary)
    with (OUT / "observations.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps(summary, ensure_ascii=False) + "\n")
    for st in states:
        if st.get("documents") and all(d.get("coverage", {}).get("core_complete") for d in st["documents"]) and not (OUT / "first-core-complete.json").exists():
            save("first-core-complete.json", summary)
    print(json.dumps({k:v for k,v in summary.items() if k not in {"processing", "usage"}} | {"calls":run["usage"]["calls"], "input":run["usage"]["input"], "coverage":[st.get("coverage") for st in states]}, ensure_ascii=False), flush=True)
    ended = run["status"] not in {"running", "queued"}
    if ended:
        shutil.copyfile(audit_path, OUT / "audit.jsonl")
        response = session.get("http://127.0.0.1:3001/api/conversations/" + M["conversation_id"], timeout=30)
        response.raise_for_status()
        save("conversation-ended.json", response.json())
        save("ended.json", summary)
    return ended

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--watch", action="store_true")
    parser.add_argument("--quarterly", action="store_true")
    args = parser.parse_args()
    while True:
        if snapshot() or not args.watch:
            break
        time.sleep(30)
