"""Independent parser smoke run on real public reports; never reads evaluator or gold data."""
import json
import shutil
import time
from pathlib import Path
from service.core import FinanceService

root=Path("service/runs/parser-smoke")
svc=FinanceService(root)
svc.create_project("reports","真实财报解析")
jobs=[]
for source in Path("benchmark/agent_input/reports").glob("*.pdf"):
    target=root/"uploads"/source.name
    shutil.copyfile(source,target)
    result=svc.ingest_document("reports",str(target),source.name)
    jobs.append(result["data"]["job_id"])
last={}
while jobs:
    for job in jobs[:]:
        state=svc.get_ingestion_status("reports",job)["data"]
        key=(state["state"],round(state["progress"],1))
        if last.get(job)!=key:
            print(json.dumps(state,ensure_ascii=False),flush=True)
            last[job]=key
        if state["state"] in {"ready","needs_review","failed","cancelled"}:
            jobs.remove(job)
    time.sleep(1)
result=svc.get_financial_metrics("reports",["revenue","net_profit_parent","operating_cash_flow","assets","equity_parent"],years=[2023,2024])
(root/"results.json").write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8")
print(json.dumps(result,ensure_ascii=False),flush=True)

