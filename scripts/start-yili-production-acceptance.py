"""Start the explicitly authorized, one-shot standard HTTP ingestion on 3001."""
import datetime as dt
import json
from pathlib import Path
import sys

import requests

QUARTERLY = "--quarterly" in sys.argv
OUT = Path(__file__).resolve().parents[1] / ("tmp/yili-q3-production-20261008" if QUARTERLY else "tmp/yili-full-production-20261008")
PROJECT = "374beac2-a970-4972-b210-e91018bbd6e6"
SOURCE = Path(r"D:\AI\财报agent\samples\native-pdf\伊利股份2024年年度报告.pdf")
if QUARTERLY:
    SOURCE = OUT / "伊利股份2024年第三季度报告.pdf"
BASE = "http://127.0.0.1:3001"
OUT.mkdir(parents=True, exist_ok=True)
manifest_path = OUT / "start.json"
with manifest_path.open("x", encoding="utf-8") as f:
    json.dump({"status": "starting", "created_at": dt.datetime.now(dt.timezone.utc).isoformat()}, f)

s = requests.Session()
s.trust_env = False

def api(method, path, **kwargs):
    response = s.request(method, BASE + path, timeout=120, **kwargs)
    response.raise_for_status()
    return response.json()

def save(name, value):
    (OUT / name).write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")

health = api("GET", "/api/health")
settings = api("GET", "/api/settings")
assert health["ok"] and settings["llm"]["model"] == "gpt-6-luna"
before = api("GET", f"/api/projects/{PROJECT}/documents")
save("documents-before.json", before)
with SOURCE.open("rb") as f:
    uploaded = api("POST", f"/api/projects/{PROJECT}/uploads", files={"files": (SOURCE.name, f, "application/pdf")})
save("upload.json", uploaded)
document = uploaded["documents"][0]
conversation = api("POST", f"/api/projects/{PROJECT}/conversations", json={})
save("conversation-created.json", conversation)
content = "请处理这份伊利股份2024年第三季度报告，清洗全部财务主表和附注表，完整入库并更新项目看板。" if QUARTERLY else "请处理这份伊利股份2024年年度报告，清洗全部财务主表和附注表，完整入库并更新项目看板。"
run = api("POST", f"/api/conversations/{conversation['id']}/messages", json={"content": content, "documentIds": [document["id"]], "annotations": []})
manifest = {"status": "started", "project_id": PROJECT, "source": str(SOURCE), "document_id": document["id"], "conversation_id": conversation["id"], "run_id": run["runId"], "started_at": dt.datetime.now(dt.timezone.utc).isoformat(), "category": "formal_material_preparation", "model": settings["llm"]["model"], "provider": settings["llm"]["provider"], "runtime": settings["runtime"], "content": content, "manual_continuations": 0, "health": health}
save("start.json", manifest)
print(json.dumps(manifest, ensure_ascii=False))
