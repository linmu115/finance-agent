"""Offline evaluator: scalar values, units, periods, scopes and evidence locators.

Usage: python benchmark/evaluate.py predictions.jsonl --split acceptance --output report.json
This does NOT establish sandbox safety or full-system acceptance.
"""
import argparse
from collections import defaultdict
from decimal import Decimal, DecimalException
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parent
THRESHOLDS={"cn_extract":0.95,"cn_calculate":0.95,"cn_audit":0.90,"cn_abstain":1.0,"cn_ocr":0.90,"finqa_single":0.85,"finqa_multi":0.75}

def read_jsonl(path):
    return [json.loads(line) for line in Path(path).read_text(encoding="utf-8-sig").splitlines() if line.strip()]

def numeric_equal(value, target, abs_tolerance, rel_tolerance="0"):
    if isinstance(value,bool) or value is None: return False
    try:
        a,b=Decimal(str(value)),Decimal(str(target))
        return a.is_finite() and b.is_finite() and abs(a-b)<=max(Decimal(abs_tolerance),abs(b)*Decimal(rel_tolerance))
    except (DecimalException,ValueError,TypeError): return False

def citation_scores(pred,gold):
    failures=[];citations=pred.get("citations")
    if not isinstance(citations,list) or any(not isinstance(x,str) for x in citations) or len(citations)>8 or len(citations)!=len(set(citations)):
        citations=[];failures.append("invalid_citation_schema")
    found=set(citations)
    groups=gold.get("evidence_sets")
    if groups is not None:
        if not isinstance(groups,list) or not groups or any(
            not isinstance(group,list) or not group or len(group)>8 or
            any(not isinstance(locator,str) for locator in group) or
            len(group)!=len(set(group)) for group in groups
        ):
            raise ValueError("Invalid gold evidence_sets: "+str(gold.get("id")))
    else:
        groups=[gold.get("citations",[])]
    alternatives=[set(group) for group in groups]
    expected=set().union(*alternatives)
    allowed=expected|set(gold.get("valid_context_citations",[]))
    precision=len(found&allowed)/len(found) if found else 0.0
    recall=max((len(found&group)/len(group) if group else 1.0 for group in alternatives),default=0.0)
    if recall<1: failures.append("missing_expected_evidence")
    if precision<0.8: failures.append("irrelevant_or_invalid_evidence")
    return precision,recall,failures

def value_in_gold_unit(pred,gold):
    """Explicit dimensional conversion for v0.2 only; never guess from values."""
    value=pred.get("answer");actual=pred.get("unit");expected=gold.get("unit")
    if actual==expected:return value,True
    if gold.get("benchmark_revision")!="0.2":return value,False
    if not isinstance(actual,str) or not isinstance(expected,str):return value,False
    money={"USD":Decimal(1),"thousand_USD":Decimal(1000),
           "million_USD":Decimal(1000000),"billion_USD":Decimal(1000000000)}
    fraction={"ratio":Decimal(1),"percent":Decimal("0.01")}
    for dimensions in [money,fraction]:
        if actual in dimensions and expected in dimensions:
            if isinstance(value,bool) or value is None:return value,False
            try:
                number=Decimal(str(value))
                if not number.is_finite():return value,False
                return number*dimensions[actual]/dimensions[expected],True
            except (DecimalException,ValueError,TypeError):return value,False
    # Percentage-point differences are not relative percent changes. Currencies
    # and count units are never inferred or treated as interchangeable.
    return value,False

def _score_case_single(pred,gold):
    failures=[]
    if pred is None:
        return {"id":gold["id"],"track":gold["track"],"answer_ok":False,"grounded_ok":False,"citation_precision":0.0,"citation_recall":0.0,"errors":["missing_prediction"]}
    if pred.get("status")!=gold["status"]: failures.append("status")
    if gold["status"]=="insufficient_evidence":
        if "answer" not in pred or pred["answer"] is not None: failures.append("must_abstain")
        if pred.get("reason_code")!=gold["reason_code"]: failures.append("reason_code")
        if gold.get("evidence_sets"):
            answer_ok=not failures
            precision,recall,citation_errors=citation_scores(pred,gold)
            failures.extend(citation_errors)
            return {"id":gold["id"],"track":gold["track"],"answer_ok":answer_ok,"grounded_ok":not failures,"citation_precision":precision,"citation_recall":recall,"errors":failures}
        if pred.get("citations")!=[]: failures.append("abstention_citations_must_be_empty")
        ok=not failures
        return {"id":gold["id"],"track":gold["track"],"answer_ok":ok,"grounded_ok":ok,"citation_precision":None,"citation_recall":None,"errors":failures}
    if isinstance(gold["answer"],bool):
        if type(pred.get("answer")) is not bool or pred["answer"]!=gold["answer"]: failures.append("verdict")
        if not numeric_equal(pred.get("corrected_value"),gold["corrected_value"],gold["abs_tolerance"]): failures.append("corrected_value")
    else:
        value,unit_ok=value_in_gold_unit(pred,gold)
        if not numeric_equal(value,gold["answer"],gold["abs_tolerance"],gold.get("rel_tolerance","0")):
            failures.append("numeric_value")
        if "unit" in gold and not unit_ok:failures.append("unit")
    for field in (["unit"] if isinstance(gold["answer"],bool) else [])+["period","scope"]:
        if field in gold and pred.get(field)!=gold[field]: failures.append(field)
    answer_ok=not failures
    precision,recall,citation_errors=citation_scores(pred,gold)
    failures.extend(citation_errors)
    return {"id":gold["id"],"track":gold["track"],"answer_ok":answer_ok,"grounded_ok":not failures,"citation_precision":precision,"citation_recall":recall,"errors":failures}

def score_case(pred,gold):
    primary=_score_case_single(pred,gold)
    if primary["grounded_ok"] or gold.get("benchmark_revision")!="0.2" or gold.get("status")!="ok":
        return primary
    for index,variant in enumerate(gold.get("supported_rounding_variants",[])):
        alternative={**gold,"answer":variant["canonical_answer"],"unit":variant["answer_unit"],
            "abs_tolerance":variant["abs_tolerance"],"rel_tolerance":"0",
            "evidence_sets":variant["evidence_sets"],"citations":variant["evidence_sets"][0],
            "valid_context_citations":variant.get("valid_context_citations",[])}
        result=_score_case_single(pred,alternative)
        # Rounded source arithmetic is admissible only with its own complete
        # evidence. Do not award numerical credit for a coincidental scalar.
        if result["grounded_ok"]:
            return {**result,"matched_answer_variant":"rounded_source_"+str(index+1)}
    return primary

def evaluate(predictions,gold,split="acceptance"):
    target=[r for r in gold if split=="all" or r["split"]==split]
    expected_ids={r["id"] for r in target}; indexed={};protocol_errors=[]
    for row in predictions:
        if not isinstance(row,dict) or not isinstance(row.get("id"),str):
            protocol_errors.append("prediction_missing_string_id");continue
        rid=row["id"]
        if rid not in expected_ids: protocol_errors.append("unknown_or_wrong_split_id:"+rid)
        if rid in indexed: protocol_errors.append("duplicate_id:"+rid)
        indexed[rid]=row
    results=[score_case(indexed.get(r["id"]),r) for r in target]
    grouped=defaultdict(list)
    for row in results: grouped[row["track"]].append(row)
    metrics={}
    for track,rows in grouped.items():
        accuracy=sum(r["answer_ok"] for r in rows)/len(rows)
        grounded=sum(r["grounded_ok"] for r in rows)/len(rows)
        metrics[track]={"n":len(rows),"answer_accuracy":accuracy,"grounded_accuracy":grounded,"target_answer_accuracy":THRESHOLDS[track],"pass":accuracy>=THRESHOLDS[track]}
    cited=[r for r in results if r["citation_recall"] is not None]
    evidence_recall=sum(r["citation_recall"] for r in cited)/len(cited) if cited else 0
    evidence_precision=sum(r["citation_precision"] for r in cited)/len(cited) if cited else 0
    grounded_overall=sum(r["grounded_ok"] for r in results)/len(results) if results else 0
    passed=bool(results) and not protocol_errors and all(v["pass"] for v in metrics.values()) and evidence_recall>=0.95 and evidence_precision>=0.95 and grounded_overall>=0.85
    version="0.2.0" if any(r.get("benchmark_revision")=="0.2" for r in target) else "0.1.0"
    return {"benchmark":"finance-agent-bench-"+version,"split":split,"evaluated_cases":len(results),"received_predictions":len(predictions),"dataset_gate_pass":passed,"full_system_acceptance":False,"runtime_gate":"NOT_RUN: require separate trusted sandbox, chart, isolation and reproducibility checks", "metrics":metrics,"citation_recall":evidence_recall,"citation_precision":evidence_precision,"grounded_accuracy":grounded_overall,"protocol_errors":protocol_errors,"cases":results}

def main():
    parser=argparse.ArgumentParser();parser.add_argument("predictions",type=Path);parser.add_argument("--split",choices=["dev","acceptance","all"],default="acceptance");parser.add_argument("--output",type=Path,default=ROOT/"results/latest.json");parser.add_argument("--version",choices=["0.1","0.2"],default="0.1");args=parser.parse_args()
    gold_path=ROOT/"evaluator/gold.jsonl" if args.version=="0.1" else ROOT/"versions/v0.2/gold.jsonl"
    result=evaluate(read_jsonl(args.predictions),read_jsonl(gold_path),args.split)
    args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps({k:v for k,v in result.items() if k!="cases"},ensure_ascii=False,indent=2))
    raise SystemExit(0 if result["dataset_gate_pass"] else 1)

if __name__=="__main__": main()
