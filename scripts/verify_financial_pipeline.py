"""Fresh, source-only financial parsing/query acceptance driver (NOT an LLM benchmark).

This driver and service do not open evaluator/gold/reference/curated facts.
It emits actual predictions for a separate host-side scorer.
Run: .venv/Scripts/python.exe scripts/verify_financial_pipeline.py --runs 3
"""
from __future__ import annotations
import argparse
import hashlib
import json
import shutil
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from service.core import FinanceService
from service.parser import PARSER_VERSION

METRICS=["revenue","net_profit_parent","operating_cash_flow","assets","equity_parent"]
YEARS=[2023,2024]

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def run_one(index):
    run_id=datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")+"-"+uuid.uuid4().hex[:8]
    data=ROOT/"benchmark"/"runs"/"financial-pipeline"/run_id
    svc=FinanceService(data)
    started=time.monotonic()
    documents=[];predictions=[]
    try:
        for source in sorted((ROOT/"benchmark"/"agent_input"/"reports").glob("*.pdf")):
            project_id=source.stem+"-"+str(index)
            svc.create_project(project_id,source.stem)
            uploaded=data/"uploads"/source.name
            shutil.copyfile(source,uploaded)
            intake=svc.ingest_document(project_id,str(uploaded),source.name)
            document_id=intake["data"]["document_id"]
            job_id=intake["data"]["job_id"]
            deadline=time.monotonic()+900
            while True:
                job=svc.get_ingestion_status(project_id,job_id)["data"]
                if job["state"] in {"ready","needs_review","failed","cancelled"}:break
                if time.monotonic()>deadline:
                    svc.cancel_ingestion(project_id,job_id)
                    raise TimeoutError("report_parse_timeout")
                time.sleep(.2)
            if job["state"] not in {"ready","needs_review"}:
                raise RuntimeError(json.dumps(job,ensure_ascii=False))
            doc=svc.get_document(project_id,document_id)["data"]
            actual=svc.get_financial_metrics(project_id,METRICS,years=YEARS,document_id=document_id,scope="consolidated_CAS")
            facts={(f["metric"],f["year"]):f for f in actual["data"]["items"]}
            with svc.store.connect() as db:
                observed_pages=db.execute("SELECT count(*) FROM pages WHERE document_id=?",(document_id,)).fetchone()[0]
            documents.append({"source_id":source.stem,"sha256":digest(source),"document_id":document_id,"project_id":project_id,
                              "page_count":doc["page_count"],"persisted_page_count":observed_pages,"table_count":doc["table_count"],
                              "fact_candidate_count":doc["fact_count"],"state":doc["state"],"warnings":doc["warnings"]})
            for metric in METRICS:
                for year in YEARS:
                    fact=facts.get((metric,year))
                    record={"id":f"{source.stem}_extract_{metric}_{year}","status":"ok" if fact else "insufficient_evidence",
                            "answer":fact["value"] if fact else None,"unit":"CNY","period":fact["period"] if fact else None,
                            "scope":fact["scope"] if fact else "consolidated_CAS",
                            "citations":[f"{source.stem}:p{fact['source_ref']['page']}"] if fact else [],
                            "source_ref":fact["source_ref"] if fact else None,"quality":fact["quality"] if fact else "missing"}
                    predictions.append(record)
            print(f"run={index} source={source.stem} physical_pages={observed_pages} extracted={sum((m,y) in facts for m in METRICS for y in YEARS)}/10",flush=True)
        return {"run_id":run_id,"data_dir":str(data.relative_to(ROOT)),"elapsed_seconds":round(time.monotonic()-started,3),
                "documents":documents,"physical_pages_processed":sum(d["persisted_page_count"] for d in documents),"predictions":predictions}
    finally:
        svc.pool.shutdown(wait=True,cancel_futures=True)
        svc.analysis_pool.shutdown(wait=True,cancel_futures=True)

def main():
    args=argparse.ArgumentParser()
    args.add_argument("--runs",type=int,default=1)
    parsed=args.parse_args()
    if not 1<=parsed.runs<=3:raise ValueError("runs must be between 1 and 3")
    results=[run_one(i+1) for i in range(parsed.runs)]
    signatures=[[(r["id"],r["status"],r["answer"],r["period"],r["scope"],r["citations"]) for r in run["predictions"]] for run in results]
    report={"test_layer":"deterministic_document_parsing_and_financial_query","is_llm_agent_result":False,
            "gold_accessed_by_driver":False,"fresh_database_each_run":True,"parser_version":PARSER_VERSION,
            "created_at":datetime.now(timezone.utc).isoformat(),"runs":results,"repeat_values_and_citations_identical":all(s==signatures[0] for s in signatures),
            "total_elapsed_seconds":round(sum(r["elapsed_seconds"] for r in results),3),
            "implementation_sha256":{str(p.relative_to(ROOT)):digest(p) for p in [ROOT/"service"/name for name in ("parser.py","normalization.py","core.py","store.py")]}}
    output=ROOT/"benchmark"/"results"
    output.mkdir(parents=True,exist_ok=True)
    (output/"financial_pipeline_predictions.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
    with (output/"financial_pipeline_predictions.jsonl").open("w",encoding="utf-8") as stream:
        for row in results[0]["predictions"]:stream.write(json.dumps(row,ensure_ascii=False)+"\n")
    print(json.dumps({"output":"benchmark/results/financial_pipeline_predictions.json","runs":len(results),"pages_per_run":[r["physical_pages_processed"] for r in results],
                      "prediction_counts":[len(r["predictions"]) for r in results],"total_elapsed_seconds":report["total_elapsed_seconds"]},ensure_ascii=False))

if __name__=="__main__":main()

