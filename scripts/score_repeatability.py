"""Numerical repeatability, independent of display rounding or citation ordering."""
import argparse,hashlib,json
from decimal import Decimal,DecimalException
from itertools import combinations
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/"benchmark"))
from evaluate import read_jsonl,numeric_equal,value_in_gold_unit

def valid_prediction(prediction,definition):
    """Check the output contract, independently of answer correctness."""
    if not isinstance(prediction,dict) or "answer" not in prediction:return False
    citations=prediction.get("citations")
    if not isinstance(citations,list) or len(citations)>8 or any(not isinstance(x,str) or not x.strip() for x in citations) or len(citations)!=len(set(citations)):
        return False
    status=prediction.get("status")
    if status=="insufficient_evidence":
        reason=prediction.get("reason_code")
        if prediction["answer"] is not None or reason not in {"period_not_in_source","ambiguous_question_or_source"}:return False
        return not citations if reason=="period_not_in_source" else bool(citations)
    if status!="ok" or not citations:return False
    if not isinstance(prediction.get("unit"),str) or not prediction["unit"].strip():return False
    for field in ("unit","period","scope"):
        if field in definition and (not isinstance(prediction.get(field),str) or not prediction[field].strip()):return False
    is_audit=isinstance(definition.get("answer"),bool)
    if is_audit:
        if type(prediction["answer"]) is not bool or "corrected_value" not in prediction:return False
        value=prediction["corrected_value"]
    else:value=prediction["answer"]
    if isinstance(value,bool) or value is None:return False
    try:return Decimal(str(value)).is_finite()
    except (DecimalException,ValueError,TypeError):return False

def same_value(a,b,definition):
    if not valid_prediction(a,definition) or not valid_prediction(b,definition):return False
    if a.get("status")!=b.get("status"):return False
    if a.get("status")=="insufficient_evidence":
        return a.get("answer") is None and b.get("answer") is None and a.get("reason_code")==b.get("reason_code")
    if a.get("status")!="ok":return False
    for field in ("period","scope"):
        if field in definition and a.get(field)!=b.get(field):return False
    if isinstance(definition.get("answer"),bool):
        if "unit" in definition and a.get("unit")!=b.get("unit"):return False
        return type(a.get("answer")) is bool and type(b.get("answer")) is bool and a["answer"]==b["answer"] and numeric_equal(a.get("corrected_value"),b.get("corrected_value"),definition["abs_tolerance"],definition.get("rel_tolerance","0"))
    if "abs_tolerance" not in definition:
        # An abstention gold has no numeric tolerance. Still measure identical
        # valid numerical conclusions independently of whether they are right.
        comparison={"unit":a["unit"],"benchmark_revision":definition.get("benchmark_revision")}
        bv,bu=value_in_gold_unit(b,comparison)
        return bu and numeric_equal(a["answer"],bv,"0","0")
    av,au=value_in_gold_unit(a,definition);bv,bu=value_in_gold_unit(b,definition)
    return au and bu and numeric_equal(av,bv,definition["abs_tolerance"],definition.get("rel_tolerance","0"))

def evaluate(directory):
    manifest=json.loads((directory/"manifest.json").read_text("utf8"))
    expected=set(manifest["caseIds"]);protocol_errors=[];rounds=[];prediction_files=[]
    if len(expected)!=len(manifest["caseIds"]):protocol_errors.append("duplicate_manifest_case_id")
    for index in range(1,manifest["repeat"]+1):
        file=directory/f"round-{index}"/"predictions.jsonl";indexed={}
        for prediction in read_jsonl(file):
            if not isinstance(prediction,dict) or not isinstance(prediction.get("id"),str):
                protocol_errors.append(f"round-{index}:prediction_missing_string_id");continue
            case_id=prediction["id"]
            if case_id not in expected:protocol_errors.append(f"round-{index}:unknown_id:{case_id}")
            if case_id in indexed:protocol_errors.append(f"round-{index}:duplicate_id:{case_id}")
            indexed[case_id]=prediction
        for case_id in sorted(expected-set(indexed)):protocol_errors.append(f"round-{index}:missing_id:{case_id}")
        rounds.append(indexed)
        prediction_files.append({"round":index,"path":str(file),"sha256":hashlib.sha256(file.read_bytes()).hexdigest()})
    gold_path="benchmark/versions/v0.2/gold.jsonl" if manifest.get("benchmarkVersion")=="0.2" else "benchmark/evaluator/gold.jsonl"
    gold={r["id"]:r for r in read_jsonl(ROOT/gold_path)}
    rows=[]
    for id in manifest["caseIds"]:
        predictions=[r.get(id,{}) for r in rounds]
        valid=[valid_prediction(p,gold[id]) for p in predictions]
        eligible=len(rounds)>=2 and not protocol_errors and all(valid)
        numeric=eligible and all(same_value(a,b,gold[id]) for a,b in combinations(predictions,2))
        citations=eligible and all(sorted(predictions[0]["citations"])==sorted(p["citations"]) for p in predictions)
        rows.append({"id":id,"numeric_consistent":numeric,"citation_set_consistent":citations,
                     "round_evidence":[{"round":index,"valid_shape":ok,"status":p.get("status"),"prediction_file":prediction_files[index-1]["path"]} for index,(p,ok) in enumerate(zip(predictions,valid),1)]})
    return {"definition":"Across every pair of runs, compare valid numeric conclusions at the frozen benchmark tolerance; when gold expects abstention and has no numeric tolerance, require exact Decimal equality after explicit unit conversion. Consistency is independent of correctness. Failures never count as consistent. Citation-set consistency is reported separately.",
      "rounds":len(rounds),"cases":len(rows),"numericConclusionConsistency":sum(r["numeric_consistent"] for r in rows)/len(rows) if rows else 0,"citationSetConsistency":sum(r["citation_set_consistent"] for r in rows)/len(rows) if rows else 0,"protocol_errors":protocol_errors,"prediction_files":prediction_files,"rows":rows}
if __name__=="__main__":
    parser=argparse.ArgumentParser();parser.add_argument("directory",type=Path);args=parser.parse_args()
    result=evaluate(args.directory);(args.directory/"repeatability.json").write_text(json.dumps(result,indent=2),"utf8")
    print(json.dumps({k:v for k,v in result.items() if k!="rows"}))
