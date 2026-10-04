"""Publish a separately versioned, source-reviewed benchmark; preserve all legacy data."""
from pathlib import Path
from decimal import Decimal
from datetime import datetime,timezone
import json,hashlib,re
ROOT=Path(__file__).resolve().parents[1]
def rows(p):return [json.loads(x) for x in p.read_text("utf8").splitlines() if x.strip()]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()

def public_contract(unit):
    if not isinstance(unit,str) or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*",unit):
        raise ValueError("Invalid reviewed answer unit")
    return (
        "Return unit="+unit+" and keep full calculation precision. "
        "percent=10 means 10%; ratio=0.1 means the same fraction. "
        "percentage_points=2 means the absolute difference between 12% and 10%, "
        "not the relative percentage change. Change from A to B means B-A; "
        "percentage change means (B-A)/A*100. An undirected difference or explicit "
        "decline magnitude is nonnegative; explain its direction. "
        "Monetary units are literal: million_USD means millions of US dollars. "
        "If the original question and source cannot uniquely determine a value, "
        "return insufficient_evidence, answer=null, reason_code=ambiguous_question_or_source "
        "and cite the material demonstrating the ambiguity. Never choose an unstated "
        "period, aggregation, or accounting interpretation merely to produce a scalar."
    )

def validate_review(case,review,source_path,legacy):
    """Fail before publication if review provenance or evidence is incomplete."""
    if review.get("split",case["split"])!=case["split"]:
        raise ValueError("Review split mismatch: "+case["id"])
    expected=review.get("material_sha256") or review.get("source_sha256")
    if not expected or expected!=sha(source_path):
        raise ValueError("Missing or changed reviewed source hash: "+case["id"])
    if not isinstance(review.get("rationale"),str) or not review["rationale"].strip():
        raise ValueError("Missing source-based review rationale: "+case["id"])
    if "legacy_answer" not in review or Decimal(str(review["legacy_answer"]))!=Decimal(str(legacy["answer"])):
        raise ValueError("Legacy answer changed since review: "+case["id"])
    material=json.loads(source_path.read_text("utf8"))
    locators={x["id"] for x in material["table"]+material["text"]}
    evidence=review.get("evidence_sets")
    if not isinstance(evidence,list) or not evidence or any(
        not isinstance(group,list) or not group or len(group)>8 or
        any(not isinstance(x,str) for x in group) or len(group)!=len(set(group)) or
        not set(group)<=locators for group in evidence
    ):raise ValueError("Invalid evidence sets: "+case["id"])
    context=review.get("valid_context_citations",[])
    if not isinstance(context,list) or any(not isinstance(x,str) for x in context) or len(context)!=len(set(context)) or not set(context)<=locators:
        raise ValueError("Invalid context citation: "+case["id"])
    status=review.get("label_status")
    if status not in {"verified","corrected","ambiguous"}:raise ValueError("Unreviewed label: "+case["id"])
    public_contract(review.get("answer_unit"))
    if status=="ambiguous":
        if "canonical_answer" not in review or review["canonical_answer"] is not None:
            raise ValueError("Ambiguous review must retain null canonical answer: "+case["id"])
    else:
        answer=review.get("canonical_answer")
        if isinstance(answer,bool) or answer is None or not Decimal(str(answer)).is_finite():
            raise ValueError("Nonfinite or absent canonical answer: "+case["id"])
    tolerance=Decimal(str(review.get("abs_tolerance","0.000006")))
    if not tolerance.is_finite() or tolerance<0:
        raise ValueError("Invalid absolute tolerance: "+case["id"])
    if Decimal(str(review.get("rel_tolerance","0")))!=0:
        raise ValueError("Reviewed benchmark requires zero relative tolerance: "+case["id"])
    variants=review.get("supported_rounding_variants",[])
    if not isinstance(variants,list) or (status=="ambiguous" and variants):
        raise ValueError("Ambiguity cannot be bypassed by rounding variants: "+case["id"])
    for variant in variants:
        # A variant is a separately sourced answer, not a wider tolerance for
        # the primary value. Reuse all provenance/evidence/number validation.
        if not isinstance(variant,dict) or not all(key in variant for key in
            ["canonical_answer","answer_unit","abs_tolerance","evidence_sets","rationale"]):
            raise ValueError("Incomplete source rounding variant: "+case["id"])
        candidate={**review,**variant,"label_status":"verified","supported_rounding_variants":[]}
        candidate["valid_context_citations"]=variant.get("valid_context_citations",[])
        validate_review(case,candidate,source_path,legacy)
    return evidence,context,status

def main():
    originals=rows(ROOT/"agent_input/cases.jsonl")
    legacy_rows=rows(ROOT/"evaluator/gold.jsonl")
    oldgold={g["id"]:g for g in legacy_rows}
    if len({c["id"] for c in originals})!=len(originals) or len(oldgold)!=len(legacy_rows) or set(oldgold)!={c["id"] for c in originals}:
        raise ValueError("Legacy case/gold inventory is not one-to-one")
    review_files=[ROOT/"review"/name for name in ["curation-dev.json","curation-acceptance-a.json","curation-acceptance-b.json"]]
    reviews={}
    for file in review_files:
        data=json.loads(file.read_text("utf8"))
        items=data if isinstance(data,list) else data.get("cases",data.get("items"))
        if not isinstance(items,list):raise ValueError("Missing review case list: "+str(file))
        for item in items:
            if item["id"] in reviews:raise ValueError("duplicate reviewed ID")
            reviews[item["id"]]=item
    finqa={c["id"] for c in originals if c["track"].startswith("finqa")}
    if set(reviews)!=finqa:raise ValueError("Review IDs differ: "+str(set(reviews)^finqa))
    cases=[];gold=[];changes=[]
    for original in originals:
        case=dict(original);g=dict(oldgold[case["id"]]);g["benchmark_revision"]="0.2"
        if case["id"] in reviews:
            review=reviews[case["id"]]
            evidence,context,status=validate_review(case,review,ROOT/"agent_input"/case["allowed_assets"][0],oldgold[case["id"]])
            unit=review["answer_unit"]
            # Same public output convention for every item; no ambiguity labels,
            # operands, programs, review rationale or expected answers go to Pi.
            case["answer_unit"]=unit
            case["response_contract"]="financial-source-grounded-v2"
            case["answer_convention"]=public_contract(unit)
            g={k:v for k,v in g.items() if k not in {"program","recomputed","answer","unit","citations","abs_tolerance","rel_tolerance","period","scope"}}
            g.update(evidence_sets=evidence,valid_context_citations=context,citations=evidence[0],label_status=status)
            if review.get("supported_rounding_variants"):
                g["supported_rounding_variants"]=review["supported_rounding_variants"]
            if status=="ambiguous":
                g.update(status="insufficient_evidence",answer=None,reason_code="ambiguous_question_or_source")
            else:
                answer=str(review["canonical_answer"])
                if not Decimal(answer).is_finite():raise ValueError("Nonfinite answer")
                g.update(status="ok",answer=answer,unit=unit,abs_tolerance=str(review.get("abs_tolerance","0.000006")),rel_tolerance="0")
            changes.append({"id":case["id"],"label_status":status,"legacy_answer":oldgold[case["id"]]["answer"],"canonical_answer":g["answer"],"answer_unit":unit,"rationale":review["rationale"],"source_sha256":sha(ROOT/"agent_input"/case["allowed_assets"][0])})
        cases.append(case);gold.append(g)
    target=ROOT/"versions/v0.2";target.mkdir(parents=True,exist_ok=True)
    for name,values in [("cases.jsonl",cases),("gold.jsonl",gold)]:
        (target/name).write_text("".join(json.dumps(x,ensure_ascii=False)+"\n" for x in values),"utf8")
    (target/"label-review.json").write_text(json.dumps(changes,ensure_ascii=False,indent=2),"utf8")
    files={f.relative_to(ROOT).as_posix():sha(f) for f in review_files+[target/"cases.jsonl",target/"gold.jsonl",target/"label-review.json"]}
    manifest={"version":"0.2","created_at":datetime.now(timezone.utc).isoformat(),"cases":len(cases),"dev":sum(c["split"]=="dev" for c in cases),"acceptance":sum(c["split"]=="acceptance" for c in cases),"source_materials_unchanged":True,"legacy_version_preserved":True,"review":"Independent agent review of sources and arithmetic before comparison with legacy labels; not human double annotation.","label_status_counts":{s:sum(r["label_status"]==s for r in reviews.values()) for s in ["verified","corrected","ambiguous"]},"files":files,"rationale":"Correct source/question/units contradictions and accept independently sufficient evidence alternatives. No model prediction is used as a gold answer."}
    (target/"manifest.json").write_text(json.dumps(manifest,ensure_ascii=False,indent=2),"utf8")
    print(json.dumps(manifest,ensure_ascii=False,indent=2))
if __name__=="__main__":main()
