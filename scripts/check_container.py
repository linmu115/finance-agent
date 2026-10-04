"""Real Docker runtime acceptance probes. Missing engine is NOT a pass.

Run: python scripts/check_container.py --output sandbox/evidence/runtime.json
S10 additionally requires --chart-input <service-export.json> and --reference
<evaluator/reference.sqlite>. The evaluator stays on the host, never in /input.
"""
from __future__ import annotations
import argparse
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
import time
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sandbox import create_runner
from sandbox.launcher import RunnerError

LIBRARIES = r'''
import json,warnings,importlib
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
from matplotlib import pyplot as plt,font_manager,ft2font
names=["numpy","pandas","scipy","matplotlib","seaborn","statsmodels","sklearn","openpyxl"]
versions={name:importlib.import_module(name).__version__ for name in names}
font=font_manager.findfont(font_manager.FontProperties(family="Noto Sans CJK JP"),fallback_to_default=False)
charmap=ft2font.FT2Font(font).get_charmap()
text="营业收入年度比较亿元"
assert all(ord(c) in charmap for c in text)
plt.rcParams["font.family"]="Noto Sans CJK JP"
plt.rcParams["axes.unicode_minus"]=False
with warnings.catch_warnings(record=True) as caught:
 plt.bar(["2023","2024"],[1,2],color=["#bbbbbb","#333333"])
 plt.title("营业收入年度比较");plt.ylabel("亿元")
 plt.savefig("/output/chinese.png",dpi=120)
 assert not [w for w in caught if "Glyph" in str(w.message)]
Path("/output/versions.json").write_text(json.dumps({"versions":versions,"font":font,"glyphs_verified":True}))
'''
READ_ONLY = r'''
from pathlib import Path
import json
denied=False
try: Path("/input/data.json").write_text("CHANGED")
except OSError: denied=True
assert denied
Path("/output/probe.json").write_text(json.dumps({"write_denied":denied}))
'''
NETWORK = r'''
import socket,json
from pathlib import Path
results={}
try: socket.getaddrinfo("example.com",443);results["dns"]=True
except OSError: results["dns"]=False
for name,host,port in [("external","1.1.1.1",443),("host_service","10.0.2.2",8000),("local_app","127.0.0.1",8000)]:
 try:
  socket.create_connection((host,port),timeout=1).close();results[name]=True
 except OSError: results[name]=False
assert not any(results.values()),results
Path("/output/probe.json").write_text(json.dumps(results))
'''
ISOLATION = r'''
import os,json
from pathlib import Path
bad=[key for key in os.environ if any(s in key.upper() for s in ["API_KEY","SECRET","TOKEN","DATABASE_URL","PASSWORD"])]
paths=["/var/run/docker.sock","/run/docker.sock","/root/.ssh","/benchmark/evaluator","/host","/Users","/mnt/c"]
found=[];denied=[]
for path in paths:
 try:
  if Path(path).exists():found.append(path)
 except PermissionError:denied.append(path)
assert not bad and not found and os.getuid()==10001
Path("/output/probe.json").write_text(json.dumps({"secret_variable_names":bad,"forbidden_paths":found,"permission_denied":denied,"uid":os.getuid()}))
'''
PIDS = r'''
import subprocess,json
from pathlib import Path
children=[];limited=False
try:
 for i in range(100):
  try: children.append(subprocess.Popen(["sleep","30"]))
  except OSError: limited=True;break
finally:
 for child in children: child.terminate()
 for child in children: child.wait()
assert limited and len(children)<64
Path("/output/pids.json").write_text(json.dumps({"limited":limited,"children":len(children)}))
'''
OVERSIZE = r'''
from pathlib import Path
for n in range(40):
 Path(f"/output/block{n}.bin").write_bytes(b"x"*(2*1024*1024))
'''
LINK = r'''
from pathlib import Path
Path("/output/leak").symlink_to("/etc/passwd")
'''
TRAVERSAL = r'''
from pathlib import Path
import json
denied=False
try: Path("/output/../escape.txt").write_text("escape")
except OSError: denied=True
assert denied
Path("/output/probe.json").write_text(json.dumps({"escape_denied":denied}))
'''
CHART = r'''
import json
from pathlib import Path
from decimal import Decimal
from matplotlib import pyplot as plt
data=json.loads(Path("/input/chart_input.json").read_text())
plt.rcParams["font.family"]="Noto Sans CJK JP"
plt.rcParams["axes.unicode_minus"]=False
for company in data:
 rows=sorted(company["values"],key=lambda x:x["year"])
 assert [r["year"] for r in rows]==[2023,2024]
 values=[float(Decimal(str(r["value_cny"]))/Decimal('1e8')) for r in rows]
 fig,ax=plt.subplots(figsize=(6,4))
 ax.bar([str(r["year"]) for r in rows],values,color=["#b8b8b8","#333333"])
 ax.set_title(company["company"]+"营业收入");ax.set_ylabel("亿元");ax.set_ylim(bottom=0)
 for i,value in enumerate(values):ax.text(i,value,f"{value:.2f}",ha="center",va="bottom")
 fig.tight_layout();fig.savefig("/output/"+company["id"]+".png",dpi=160);plt.close(fig)
Path("/output/chart_data.json").write_text(json.dumps(data,ensure_ascii=False),encoding="utf-8")
'''


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="sandbox/evidence/runtime.json")
    parser.add_argument("--state-root", default="sandbox/evidence/runs")
    parser.add_argument("--image", default="finance-analysis:0.1")
    parser.add_argument("--chart-input")
    parser.add_argument("--reference")
    parser.add_argument("--quick", action="store_true", help="Use 3s timeout probe; full S05 stays incomplete")
    args = parser.parse_args()
    runner = create_runner(Path(args.state_root))
    availability = runner.availability()
    report = {"created_at": time.time(), "runner": availability, "cases": [],
              "full_gate": False, "method": "trusted host invokes actual Docker; no mock execution"}
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    def save():
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    ids = ["S01","S02","S03","S04","S05","S06","S07","S10"]
    if not availability["available"]:
        report["cases"] = [{"id": value, "status": "NOT_EXECUTED", "reason": availability["reason"]} for value in ids]
        save()
        print(json.dumps({"status": "NOT_EXECUTED", "reason": availability["reason"], "report": str(output)}))
        return 2
    project = "runtime-acceptance"
    def run(code, files=None, **kwargs):
        return runner.run(code, files or {}, project_id=project, **kwargs)
    def record(case_id, passed, runs, **details):
        report["cases"].append({"id": case_id, "status": "PASS" if passed else "FAIL",
                                "runs": runs, **details})
        save()
        print(case_id, "PASS" if passed else "FAIL", flush=True)
    def read(run_state, name):
        return json.loads(runner.artifact_path(run_state["run_id"],name,project_id=project).read_text(encoding="utf-8"))
    with tempfile.TemporaryDirectory() as temp:
        source=Path(temp)/"data.json";source.write_text('{"revenue":42}',encoding="utf-8")
        state=run(LIBRARIES)
        record("S01",state["status"]=="succeeded" and read(state,"versions.json")["glyphs_verified"],[state],
               visual_check="pending human inspection of chinese.png")
        state=run(READ_ONLY,{"data.json":source})
        record("S02",state["status"]=="succeeded" and source.read_text()=='{"revenue":42}',[state])
        state=run(NETWORK)
        record("S03",state["status"]=="succeeded",[state])
        os.environ["FINANCE_FAKE_HOST_API_KEY"]="not-a-secret-acceptance-canary"
        try: state=run(ISOLATION)
        finally: os.environ.pop("FINANCE_FAKE_HOST_API_KEY",None)
        record("S04",state["status"]=="succeeded",[state])
        timeout=3 if args.quick else 120
        timed=run("while True: pass",timeout_seconds=timeout)
        cancel_id=uuid.uuid4().hex
        with ThreadPoolExecutor(max_workers=1) as pool:
            pending=pool.submit(run,"import time\nwhile True: time.sleep(0.2)",run_id=cancel_id)
            deadline=time.monotonic()+40
            while time.monotonic()<deadline:
                try:
                    if runner.status(cancel_id,project_id=project)["status"]=="running": break
                except RunnerError: pass
                time.sleep(.1)
            requested=runner.cancel(cancel_id,project_id=project)
            cancelled=pending.result(timeout=20)
        passed=timed["status"]=="timed_out" and timed.get("execution_seconds",99999)<=timeout+5 and cancelled["status"]=="cancelled" and timed.get("container_removed") and cancelled.get("container_removed")
        record("S05",passed and not args.quick,[timed,cancelled],
               reason="quick mode does not prove the required 120-second boundary" if args.quick else None)
        memory=run("blocks=[]\nwhile True: blocks.append(bytearray(64*1024*1024))")
        pids=run(PIDS)
        after=runner.availability()
        record("S06",memory.get("oom_killed") is True and pids["status"]=="succeeded" and after["available"],[memory,pids])
        oversize=run(OVERSIZE);link=run(LINK);traversal=run(TRAVERSAL)
        record("S07",oversize["status"]=="output_rejected" and link["status"]=="output_rejected" and traversal["status"]=="succeeded",
               [oversize,link,traversal])
        if args.chart_input and args.reference:
            state=run(CHART,{"chart_input.json":Path(args.chart_input)})
            generated=read(state,"chart_data.json") if state["status"]=="succeeded" else []
            con=sqlite3.connect(f"file:{Path(args.reference).absolute().as_posix()}?mode=ro",uri=True)
            from decimal import Decimal
            reference={(row[0],int(row[1][:4])):Decimal(row[2]) for row in con.execute("SELECT company,period,value_cny FROM facts WHERE metric='revenue'")}
            actual={(company['company'],row['year']):Decimal(str(row['value_cny'])) for company in generated for row in company['values']}
            matches=set(actual)==set(reference) and all(abs(actual[key]-reference[key])<=Decimal('0.01') for key in reference)
            record("S10",state['status']=='succeeded' and matches,[state],
                   reference_match=matches,visual_check="pending human inspection of all three PNGs",generated_data=generated)
            con.close()
        else:
            report["cases"].append({"id":"S10","status":"NOT_EXECUTED","reason":"Provide service-exported chart inputs and evaluator reference"})
        save()
    # S08/S09/S11/S12 belong to full application acceptance; never declare a full-system pass here.
    return 0 if all(item["status"]=="PASS" for item in report["cases"]) else 2


if __name__=="__main__":
    raise SystemExit(main())
