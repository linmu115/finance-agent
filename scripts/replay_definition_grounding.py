"""Read-only replay of audited definition responses; no model or database writes."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from service.definition_model import align_extractions, validate_review, CACHE_HASH


def payload(request):
    message="\n".join(str(item.get("content", "")) for item in request["messages"])
    text="[[KNOWN_METRICS]] "+message.rsplit("Q: [[KNOWN_METRICS]] ",1)[1]
    contexts,groups,known={},[],None
    for line in text.splitlines():
        if line.startswith("[[KNOWN_METRICS]] "):known=json.loads(line.split("]] ",1)[1])
        elif line.startswith("[[EVIDENCE_CONTEXT:"):
            marker,body=line.split("]] ",1);contexts[marker.split(":",1)[1]]=json.loads(body)["text"]
        elif line.startswith("[[DEFINITION:"):
            groups.append(json.loads(line.split("]] ",1)[1]))
    for group in groups:
        for evidence in group["evidence"]:evidence["text"]=contexts[evidence.pop("text_ref")]
    return groups,known


def replay(audit):
    events=[json.loads(line) for line in audit.read_text(encoding="utf-8").splitlines() if line.strip()]
    requests={item["data"]["requestId"]:item["data"] for item in events if item["type"]=="extraction_request"}
    results=[]
    for event in events:
        if event["type"]!="extraction_result":continue
        data=event["data"];request=requests[data["requestId"]]
        if "[[DEFINITION:" not in json.dumps(request,ensure_ascii=False):continue
        groups,known=payload(request)
        raw=data["content"]
        if isinstance(raw,list):raw="".join(item.get("text","") for item in raw if item.get("type")=="text")
        value=json.loads(re.sub(r"^```(?:json)?\s*|\s*```$","",raw.strip()))
        extractions=[]
        for item in value["extractions"]:
            kind=next(key for key in item if not key.endswith("_attributes"))
            extractions.append({"class":kind,"text":item[kind],"attributes":item[kind+"_attributes"],"span":None})
        original=json.dumps(extractions,ensure_ascii=False,sort_keys=True)
        aligned=align_extractions(extractions,groups,known)
        reviewed,errors=validate_review(aligned,groups,known)
        assert original==json.dumps(extractions,ensure_ascii=False,sort_keys=True)
        results.append({"request_id":data["requestId"],"stop_reason":data["stopReason"],"group_count":len(groups),
                        "raw_response_sha256":hashlib.sha256(raw.encode()).hexdigest(),"errors":errors,
                        "quote_alignments":[{"group_id":decision["group_id"],"alignments":decision["quote_alignments"]}
                                            for decision in reviewed["decisions"] if decision["quote_alignments"]]})
    return {"mode":"read_only_original_response_replay","model_calls":0,"database_writes":0,
            "cache_hash":CACHE_HASH,"audit_sha256":hashlib.sha256(audit.read_bytes()).hexdigest(),
            "all_responses_valid":all(not result["errors"] for result in results),"responses":results,
            "limitation":"Tests source locator validation of historical model decisions, not a new financial score or live acceptance."}


if __name__=="__main__":
    parser=argparse.ArgumentParser();parser.add_argument("--audit",required=True);parser.add_argument("--output",required=True)
    args=parser.parse_args();result=replay(Path(args.audit))
    with Path(args.output).open("x",encoding="utf-8") as stream:json.dump(result,stream,ensure_ascii=False,indent=2)
    print(json.dumps({"responses":len(result["responses"]),"all_valid":result["all_responses_valid"],
                      "aligned_groups":sum(len(item["quote_alignments"]) for item in result["responses"])}))
