"""Local acceptance evidence from one production run; never changes source data."""
import argparse
from collections import Counter, defaultdict
from datetime import datetime
from decimal import Decimal, InvalidOperation
import json
from pathlib import Path
import re
import sqlite3

ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser()
parser.add_argument("--quarterly", action="store_true")
args = parser.parse_args()
OUT = ROOT / ("tmp/yili-q3-production-20261008" if args.quarterly else "tmp/yili-full-production-20261008")

def read(name): return json.loads((OUT / name).read_text("utf-8"))
def save(name, value): (OUT / name).write_text(json.dumps(value, ensure_ascii=False, indent=2), "utf-8")
def index(table_id): return int(table_id.rsplit(":t", 1)[1])
def coord(f):
    s = f["source"]
    return (index(s["table_id"]), s["row"], s["column"])

m = read("start.json")
run = read("run-latest.json")
states = read("processing-latest.json")
db = sqlite3.connect(Path(r"D:\AI\财报agent\data\active\finance.sqlite").as_uri() + "?mode=ro", uri=True)
db.row_factory = sqlite3.Row
for name, query, params in [
    ("facts.json", "SELECT * FROM facts WHERE project_id=? AND document_id=?", (m["project_id"], m["document_id"])),
    ("source-tables.json", "SELECT * FROM source_tables WHERE document_id=?", (m["document_id"],)),
    ("normalization-batches.json", "SELECT * FROM normalization_batches WHERE document_id=?", (m["document_id"],)),
    ("document-profile.json", "SELECT * FROM document_profiles WHERE document_id=?", (m["document_id"],)),
]:
    save(name, [dict(r) for r in db.execute(query, params)])
db.close()
facts = [f | {"source": json.loads(f["source_json"])} for f in read("facts.json")]
tables = {index(t["table_id"]): t | {"rows": json.loads(t["rows_json"])} for t in read("source-tables.json")}
batches = [json.loads(b["result_json"]) | {"saved_at": b["created_at"]} for b in read("normalization-batches.json")]
documents = [d for st in states for d in st["documents"] if d["document_id"] == m["document_id"]]
candidates = set(documents[0]["tables"]) if documents else set()
done = {b["script_table"] for b in batches if b["status"] in {"completed", "needs_review"}}
core = set(documents[0].get("core_tables", [])) if documents else set()
pages = defaultdict(set)
for t in candidates: pages[tables[t]["page"]].add(t)
replay = []
for f in facts:
    t, r, c = coord(f)
    raw = tables[t]["rows"][r-1][c-1]
    meta = f["source"].get("normalization", {})
    span = meta.get("numeric_span")
    item = {"fact_id": f["fact_id"], "table": t, "row": r, "column": c,
            "raw_match": raw == f["raw_value"], "span_match": not span or raw[span["start"]:span["end"]] == span["text"]}
    numeric = span["text"] if span else raw
    numeric = re.sub(r"[,，\s%％]", "", numeric).replace("−", "-").replace("﹣", "-").replace("（", "(").replace("）", ")")
    if numeric.startswith("(") and numeric.endswith(")"): numeric = "-" + numeric[1:-1]
    try:
        value = Decimal(numeric)
        if span and span.get("polarity") == "negative": value = -abs(value)
        item["arithmetic_match"] = value * Decimal(meta["scale"]) == Decimal(f["value"])
    except (InvalidOperation, KeyError):
        item["arithmetic_match"] = None
    replay.append(item)
save("raw-cell-replay.json", replay)
audit = [json.loads(line) for line in (OUT / "audit.jsonl").read_text("utf-8").splitlines()]
reopening_jobs = []
unique_conflicts = {}
for st in states:
    for rid, job in st.get("jobs", {}).items():
        issues = job.get("semantic_reopenings", [])
        if not issues: continue
        reopening_jobs.append({"processing_id": st["processing_id"], "job_id": rid, "rule_job": bool(job.get("rule_payload")), "issues": issues})
        for issue in issues:
            key = json.dumps({k:v for k,v in issue.items() if k not in {"table", "instruction"}}, sort_keys=True, ensure_ascii=False)
            unique_conflicts[key] = issue
affected = {i["table"] for j in reopening_jobs for i in j["issues"] if "table" in i}
save("consistency-interceptions.json", {"jobs": reopening_jobs, "unique_conflicts": list(unique_conflicts.values()), "affected_tables": sorted(affected), "completed_afterwards": sorted(affected & done), "still_pending": sorted(affected - done)})
summary = {
    "project_id": m["project_id"], "document_id": m["document_id"], "run_id": m["run_id"],
    "category": "formal_material_preparation", "status": run["status"], "error": run.get("error"),
    "created_at": run["createdAt"], "finished_at": run.get("finishedAt"),
    "duration_seconds": (datetime.fromisoformat(run["finishedAt"].replace("Z", "+00:00"))-datetime.fromisoformat(run["createdAt"].replace("Z", "+00:00"))).total_seconds() if run.get("finishedAt") else None,
    "usage": run["usage"], "model_requests_in_audit": sum(a["type"] == "model_request" for a in audit),
    "manual_continuations": 0, "automatic_continuations": sum(a["type"] == "ingestion_continuation" for a in audit),
    "tables": {"archived":len(tables), "candidates": len(candidates), "completed":len(done), "pending":sorted(candidates-done)},
    "pages": {"parsed":read("document-latest.json")["page_count"], "with_candidates":len(pages), "with_all_candidates_completed":sum(ts <= done for ts in pages.values()), "with_any_completed_candidate":sum(bool(ts & done) for ts in pages.values())},
    "facts": len(facts), "generic_metric_facts":sum(f["metric"] in {"amount","value","number","data","financial_metric"} for f in facts),
    "core": {"total":len(core), "completed":len(core & done), "pending":sorted(core-done), "first_complete_at":None},
    "consistency": {"jobs_with_interceptions":len(reopening_jobs), "unique_conflicts":len(unique_conflicts), "affected_tables":sorted(affected), "resolved_tables":sorted(affected & done), "pending_tables":sorted(affected-done)},
    "raw_replay": {"total":len(replay), "passed":sum(r["raw_match"] and r["span_match"] for r in replay), "arithmetic_passed":sum(r["arithmetic_match"] is True for r in replay), "arithmetic_unknown":sum(r["arithmetic_match"] is None for r in replay)},
    "zero_fact_completed_tables": [b["script_table"] for b in batches if b["fact_count"] == 0],
    "tool_errors": [a for a in audit if a["type"] == "tool_error"],
}
if not args.quarterly:
    previous = [f | {"source":json.loads(f["source_json"])} for f in read("legacy-facts.json")]
    old_tables = {index(t["table_id"]):json.loads(t["rows_json"]) for t in read("legacy-tables.json")}
    current = defaultdict(list)
    for f in facts: current[coord(f)].append(f)
    coverage = []
    for f in previous:
        matches = current[coord(f)]
        t = coord(f)[0]
        equal = [v for v in matches if Decimal(v["value"]) == Decimal(f["value"])]
        compatible = [v for v in equal if all(v[k] == f[k] for k in ["period", "scope", "currency", "company"])]
        state = "same_cell_value_period_scope_currency_company" if compatible else "same_cell_value_changed_semantics" if equal else "same_cell_changed_value" if matches else "pending_table" if t in candidates-done else "completed_table_missing_cell" if t in done else "not_candidate_table"
        coverage.append({"legacy_fact_id":f["fact_id"], "coordinate":coord(f), "status":state, "legacy_metric":f["metric"], "legacy_period":f["period"], "legacy_value":f["value"], "current":[{k:v[k] for k in ["fact_id","metric","period","scope","currency","value"]} for v in matches]})
    save("legacy-coverage-details.json", coverage)
    summary["legacy_coverage"] = {"legacy_facts":len(previous), "current_facts":len(facts), "identical_source_tables":sum(t in old_tables and v["rows"] == old_tables[t] for t,v in tables.items()), "categories":dict(Counter(c["status"] for c in coverage)), "new_source_cells":sum(coord(f) not in {coord(p) for p in previous} for f in facts)}
    reviews=[]
    metric_choices={"货币资金":{"cash"},"存货":{"inventory"},"资产总计":{"assets"},"营业收入":{"revenue"},"营业成本":{"cost_of_revenue"},"资产减值损失":{"asset_impairment_loss"},"经营活动产生的现金流量净额":{"operating_cash_flow"},"购建固定资产、无形资产和其他长期资产支付的现金":{"capex"},"应收账款":{"accounts_receivable"},"固定资产":{"fixed_assets","property_plant_equipment"},"营业利润":{"operating_profit"},"投资收益":{"investment_income"},"财务费用":{"finance_expense","finance_expenses","financial_expenses"},"销售商品、提供劳务收到的现金":{"cash_received_from_sales"},"收取利息、手续费及佣金的现金":{"cash_received_interest_commission","cash_interest_fees_received"}}
    import fitz
    pdf=fitz.open(m["source"])
    for g in read("source-review-reference.json"):
        available=[f for f in facts if f["source"].get("page")==g["page"] and Decimal(f["value"])==Decimal(g["value"])]
        correct=[f for f in available if all(f[k]==g[k] for k in ["period","scope","currency","company"]) and (g["label"] not in metric_choices or f["metric"] in metric_choices[g["label"]]) and (not g.get("dimension") or g["dimension"] in json.dumps(f["source"]["normalization"].get("dimensions",{}),ensure_ascii=False))]
        literal=g["value"] in pdf[g["page"]-1].get_text().replace(",","").replace("−","-")
        reviews.append(g | {"pdf_literal_verified":literal,"status":"passed" if correct and literal else "missing" if not available else "semantic_mismatch", "candidates":[{k:f[k] for k in ["fact_id","metric","period","scope","currency","value"]} | {"source":f["source"]} for f in available]})
    save("source-review-results.json",reviews)
    summary["source_review"]={"total":len(reviews),"statuses":dict(Counter(r["status"] for r in reviews)),"by_category":{k:dict(Counter(r["status"] for r in reviews if r["category"]==k)) for k in dict.fromkeys(r["category"] for r in reviews)}}
save("acceptance-summary.json", summary)
print(json.dumps({k:v for k,v in summary.items() if k not in {"error","tool_errors","tables","core"}}, ensure_ascii=False, indent=2))
