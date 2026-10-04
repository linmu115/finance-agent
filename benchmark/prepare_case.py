"""Export ONLY one case and its allowlisted source materials to a fresh directory."""
import argparse
import json
from pathlib import Path
import shutil

ROOT=Path(__file__).resolve().parent

def prepare(case_id,destination,version="0.1"):
    if version not in {"0.1","0.2"}: raise ValueError("Unknown benchmark version")
    source=(ROOT/"agent_input").resolve();destination=Path(destination).resolve()
    if destination.exists(): raise ValueError("Use a NEW per-case destination; do not reuse input directories.")
    cases_path=source/"cases.jsonl" if version=="0.1" else ROOT/"versions/v0.2/cases.jsonl"
    cases=[json.loads(s) for s in cases_path.read_text(encoding="utf-8").splitlines() if s.strip()]
    case=next((r for r in cases if r["id"]==case_id),None)
    if case is None: raise ValueError("Unknown case")
    paths=[]
    for relative in case["allowed_assets"]:
        path=(source/relative).resolve()
        if not path.is_relative_to(source) or not path.is_file(): raise ValueError("Invalid source asset")
        paths.append((relative,path))
    destination.mkdir(parents=True)
    for relative,path in paths:
        target=destination/relative;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(path,target)
    (destination/"case.json").write_text(json.dumps(case,ensure_ascii=False,indent=2),encoding="utf-8")
    return case

if __name__=="__main__":
    parser=argparse.ArgumentParser();parser.add_argument("case_id");parser.add_argument("destination",type=Path);parser.add_argument("--version",choices=["0.1","0.2"],default="0.1");a=parser.parse_args()
    c=prepare(a.case_id,a.destination,a.version);print(json.dumps({"prepared":c["id"],"assets":c["allowed_assets"],"version":a.version},ensure_ascii=False))
