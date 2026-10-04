"""Actual container ownership and killed-runner recovery probes (S08/S11)."""
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import subprocess
import sys
import time
import uuid

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from sandbox import create_runner, RunnerError
from sandbox.remote import RemoteSandboxRunner


def main():
    runner=create_runner(Path("sandbox/evidence/recovery-runs"))
    available=runner.availability()
    report={"runner":available,"cases":[],"created_at":time.time()}
    target=Path("sandbox/evidence/recovery.json")
    target.parent.mkdir(parents=True,exist_ok=True)
    def save():
        target.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
    if not available["available"]:
        report["cases"]=[{"id":key,"status":"NOT_EXECUTED","reason":available["reason"]} for key in ["S08","S11"]]
        save();return 2
    first=runner.run("from pathlib import Path\nPath('/output/report.txt').write_text('project A output')",
                     {},project_id="isolation-A")
    if first["status"]!="succeeded":
        report["cases"].append({"id":"S08","status":"FAIL","run":first});save();return 2
    denials=[]
    for method in ["status","artifact","cancel"]:
        try:
            if method=="status":runner.status(first["run_id"],project_id="isolation-B")
            elif method=="artifact":runner.artifact_path(first["run_id"],"report.txt",project_id="isolation-B")
            else:runner.cancel(first["run_id"],project_id="isolation-B")
            denials.append({"method":method,"denied":False})
        except RunnerError as exc:
            denials.append({"method":method,"denied":True,"reason":str(exc)})
    if isinstance(runner,RemoteSandboxRunner):
        audit=runner._rpc("evidence",run_id=first["run_id"],project_id="isolation-A").get("audit.jsonl","")
    else:
        audit=(runner.root/first["run_id"]/"audit.jsonl").read_text()
    events=[json.loads(line) for line in audit.splitlines() if line]
    rejected=[event for event in events if event["event"]=="access_denied"]
    report["cases"].append({"id":"S08","status":"PASS" if all(d["denied"] for d in denials) and len(rejected)>=3 else "FAIL",
                            "scope":"actual sandbox run/status/artifact/cancel project boundary",
                            "run_id":first["run_id"],"owner_project":"isolation-A","attempted_project":"isolation-B",
                            "denials":denials,"audit_events":rejected})
    save()
    if not isinstance(runner,RemoteSandboxRunner):
        report["cases"].append({"id":"S11","status":"NOT_EXECUTED","reason":"This destructive probe targets the project-local VM SSH runner"})
        save();return 2
    run_id=uuid.uuid4().hex
    code="from pathlib import Path\nimport time\nPath('/output/partial.txt').write_text('unfinished')\nwhile True: time.sleep(0.2)"
    with ThreadPoolExecutor(max_workers=1) as pool:
        future=pool.submit(runner.run,code,{},project_id="recovery-A",run_id=run_id)
        deadline=time.monotonic()+40
        state=None
        while time.monotonic()<deadline:
            try:
                state=runner.status(run_id,project_id="recovery-A")
                if state["status"]=="running":break
            except RunnerError:pass
            time.sleep(.2)
        if not state or state["status"]!="running":
            report["cases"].append({"id":"S11","status":"FAIL","reason":"Task never reached running"})
            save();return 2
        pid=state["owner_pid"]
        assert isinstance(pid,int) and pid>1
        # Verify exact trusted worker identity before killing this task's owner.
        script=("import os,signal;from pathlib import Path;"
                f"p={pid};cmd=Path('/proc/'+str(p)+'/cmdline').read_bytes();"
                "assert b'/opt/finance/sandbox/remote_worker.py' in cmd;"
                "os.kill(p,signal.SIGKILL);print('KILLED_CONFIRMED_WORKER')")
        command="python3 -c "+__import__("shlex").quote(script)
        killed=subprocess.run(runner.ssh_args[:-2]+[command],capture_output=True,timeout=15)
        interrupted=future.result(timeout=25)
    recovered=runner.status(run_id,project_id="recovery-A")
    try:
        runner.artifact_path(run_id,"partial.txt",project_id="recovery-A")
        withheld=False
    except RunnerError:
        withheld=True
    inspected=subprocess.run(runner.ssh_args[:-2]+["docker inspect finance-"+run_id],
                             capture_output=True,timeout=10)
    absent=inspected.returncode!=0 and b"no such" in inspected.stderr.lower()
    audit=runner._rpc("evidence",run_id=run_id,project_id="recovery-A").get("audit.jsonl","")
    events=[json.loads(line) for line in audit.splitlines() if line]
    passed=killed.returncode==0 and b"KILLED_CONFIRMED_WORKER" in killed.stdout and recovered["status"]=="failed" and recovered.get("container_removed") and withheld and absent
    report["cases"].append({"id":"S11","status":"PASS" if passed else "FAIL",
                            "scope":"actual Linux host runner SIGKILL and orphan-container recovery",
                            "run_id":run_id,"killed_owner_pid":pid,"kill_exit_code":killed.returncode,
                            "interrupted_transport_state":interrupted,"recovered_state":recovered,
                            "unfinished_artifact_withheld":withheld,"container_absent":absent,"audit_events":events})
    save()
    print(json.dumps([{"id":item["id"],"status":item["status"]} for item in report["cases"]]))
    return 0 if all(item["status"]=="PASS" for item in report["cases"]) else 2


if __name__=="__main__":
    raise SystemExit(main())

