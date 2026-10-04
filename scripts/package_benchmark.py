"""Package explicit public benchmark assets. Never reads data/settings or app DB."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import zipfile

ROOT=Path(__file__).resolve().parents[1]
SAMPLES=ROOT/"samples"

def pack(output, files, instructions=None):
    SAMPLES.mkdir(exist_ok=True)
    records=[]
    if output.exists():
        # Published ZIP bytes and hashes stay immutable. A changed suite needs
        # a distinct revision filename, not a silent repack of the old one.
        with zipfile.ZipFile(output) as archive:
            if archive.testzip():raise RuntimeError("existing zip integrity failure")
            for source,name in files:
                if archive.read(name)!=source.read_bytes():raise RuntimeError("existing published package differs; create a new revision: "+name)
            if instructions and archive.read("使用说明.txt").decode("utf-8")!=instructions:raise RuntimeError("existing package instructions changed")
            count=len(json.loads(archive.read("package-manifest.json"))["files"])
        return {"path":str(output.relative_to(ROOT)),"files":count,"bytes":output.stat().st_size,"sha256":hashlib.sha256(output.read_bytes()).hexdigest()}
    with zipfile.ZipFile(output,"w",compression=zipfile.ZIP_DEFLATED,compresslevel=6) as archive:
        for source,name in files:
            content=source.read_bytes(); archive.writestr(name,content)
            records.append({"path":name,"bytes":len(content),"sha256":hashlib.sha256(content).hexdigest()})
        if instructions: archive.writestr("使用说明.txt",instructions)
        archive.writestr("package-manifest.json",json.dumps({"files":records},ensure_ascii=False,indent=2))
    with zipfile.ZipFile(output) as archive:
        if archive.testzip(): raise RuntimeError("zip integrity failure")
        for record in records:
            if hashlib.sha256(archive.read(record["path"])).hexdigest()!=record["sha256"]:raise RuntimeError("hash mismatch")
    return {"path":str(output.relative_to(ROOT)),"files":len(records),"bytes":output.stat().st_size,"sha256":hashlib.sha256(output.read_bytes()).hexdigest()}

def main():
    results=[]
    for number in ("v0.3.1","v0.3"):
        version=ROOT/("benchmark/versions/"+number+"-normalization")
        files=[(p,str(p.relative_to(version)).replace("\\","/")) for p in sorted(version.rglob("*")) if p.is_file() and p.suffix in {".json",".jsonl",".txt",".csv",".xlsx",".pdf"}]
        if not files:raise RuntimeError("missing benchmark revision: "+number)
        results.append(pack(SAMPLES/("normalization-benchmark-"+number+".zip"),files))
    old=ROOT/"benchmark/versions/v0.2"
    files=[(p,str(p.relative_to(ROOT)).replace("\\","/")) for folder in [old,ROOT/"benchmark/agent_input"] for p in sorted(folder.rglob("*")) if p.is_file() and p.suffix in {".json",".jsonl",".pdf",".png"}]
    instructions="历史问答测试集 v0.2\n186 题：开发 62 题、正式验收 124 题。包含公开年报原件、FinQA 问题材料、题目和独立评测标准。\n此包保留历史标签，不能把 gold.jsonl 发给 Agent。正式评测在项目中运行 npm run benchmark，相关参数见项目 README。\n它评估财报问答与来源支持；v0.3-normalization 另测新架构的清洗、单位、期间、版本和并行会话。\n"
    results.append(pack(SAMPLES/"financial-benchmark-v0.2.zip",files,instructions))
    output=ROOT/"benchmark/results/benchmark-packages.json";output.parent.mkdir(exist_ok=True)
    output.write_text(json.dumps({"packages":results},ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps(results,ensure_ascii=False))

if __name__=="__main__":main()
