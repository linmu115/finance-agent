"""OCR smoke: only scan images are inputs, no original PDF or answer file is opened."""
import json
from pathlib import Path
from service.parser import parse_document,extract_facts
root=Path("service/runs/ocr-smoke");root.mkdir(parents=True,exist_ok=True)
for path in Path("benchmark/agent_input/scans").glob("*.png"):
    print("OCR",path.name,flush=True)
    parsed=parse_document(path,path.name,lambda *args:None,lambda:False,{})
    facts=extract_facts(parsed,path.stem)
    (root/(path.stem+".json")).write_text(json.dumps({"parsed":parsed,"facts":facts},ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps({"name":path.name,"fact_count":len(facts),"facts":facts},ensure_ascii=False),flush=True)

