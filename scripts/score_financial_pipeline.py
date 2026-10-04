"""Trusted host scorer; never imported by the application or the tested agent."""
import json, sys
from pathlib import Path
from datetime import datetime, timezone
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"benchmark"))
from evaluate import score_case
source=json.loads((ROOT/"benchmark/results/financial_pipeline_predictions.json").read_text(encoding="utf-8"))
gold={r["id"]:r for line in (ROOT/"benchmark/evaluator/gold.jsonl").read_text(encoding="utf-8").splitlines() if (r:=json.loads(line))["track"]=="cn_extract"}
runs=[]
for run in source["runs"]:
    indexed={p["id"]:p for p in run["predictions"]}
    rows=[]
    for rid,truth in gold.items():
        pred=indexed.get(rid)
        scored=score_case(pred,truth)
        rows.append({**scored,"actual":pred.get("answer") if pred else None,"expected":truth["answer"],
                     "actual_citations":pred.get("citations") if pred else [],"expected_citations":truth["citations"],
                     "period":pred.get("period") if pred else None,"scope":pred.get("scope") if pred else None})
    passed=sum(r["grounded_ok"] for r in rows)
    runs.append({"run_id":run["run_id"],"elapsed_seconds":run["elapsed_seconds"],"physical_pages_processed":run["physical_pages_processed"],
                 "total":len(rows),"passed":passed,"accuracy":sum(r["answer_ok"] for r in rows)/len(rows),
                 "evidence_accuracy":passed/len(rows),"documents":run["documents"],"cases":rows})
result={"name":"三轮真实财报解析与数据库查询","status":"passed" if all(r["passed"]==r["total"] for r in runs) else "failed",
        "mode":"deterministic_pipeline","is_llm_agent_result":False,"is_full_system_acceptance":False,
        "createdAt":datetime.now(timezone.utc).isoformat(),"total":sum(r["total"] for r in runs),"passed":sum(r["passed"] for r in runs),
        "runs":runs,"repeat_values_and_citations_identical":source["repeat_values_and_citations_identical"],
        "implementation_sha256":source["implementation_sha256"],"parser_version":source["parser_version"],
        "limitations":"Only cn_extract parsing/query layer. This result does not prove LLM reasoning, retrieval, OCR, sandbox or full-system gates."}
(ROOT/"benchmark/results/financial_pipeline.json").write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8")
print(json.dumps({k:v for k,v in result.items() if k not in {"runs","implementation_sha256"}},ensure_ascii=True))
sys.exit(0 if result["status"]=="passed" else 1)

