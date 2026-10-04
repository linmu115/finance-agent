"""Fixed SSH RPC endpoint on the trusted Linux VM, outside the analysis container."""
import base64
import json
from pathlib import Path
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sandbox.launcher import SandboxRunner, RunnerError, validate_name, MAX_INPUT

def main():
    payload = json.loads(sys.stdin.buffer.read(MAX_INPUT * 2 + 1024 * 1024))
    runner = SandboxRunner("/var/lib/finance/runs")
    method = payload["method"]
    if method == "availability":
        result = runner.availability()
    elif method in {"status", "cancel"}:
        result = getattr(runner, method)(payload["run_id"], project_id=payload["project_id"])
    elif method == "artifacts":
        state = runner.status(payload["run_id"], project_id=payload["project_id"])
        result = {}
        for artifact in state["artifacts"]:
            path = runner.artifact_path(payload["run_id"], artifact["name"], project_id=payload["project_id"])
            result[artifact["name"]] = base64.b64encode(path.read_bytes()).decode("ascii")
    elif method == "evidence":
        state = runner.status(payload["run_id"], project_id=payload["project_id"])
        directory = runner._directory(payload["run_id"])
        result = {}
        for name in ["audit.jsonl","container-config.json","stdout.log","stderr.log"]:
            path=directory/name
            if path.is_file() and path.stat().st_size<=2*1024*1024:
                result[name]=path.read_text(encoding="utf-8")
    elif method == "run":
        with tempfile.TemporaryDirectory(prefix="finance-input-") as tmp:
            files = {}
            total = 0
            for name, encoded in payload.get("inputs", {}).items():
                validate_name(name)
                data = base64.b64decode(encoded, validate=True)
                total += len(data)
                if total > MAX_INPUT:
                    raise RunnerError("Combined inputs exceed 100 MiB")
                target = Path(tmp) / name
                target.write_bytes(data)
                files[name] = target
            result = runner.run(payload["code"], files, project_id=payload["project_id"],
                                run_id=payload["run_id"], timeout_seconds=payload.get("timeout_seconds",120))
    else:
        raise RunnerError("Unknown host RPC method")
    print(json.dumps({"ok":True,"result":result},ensure_ascii=False))


if __name__=="__main__":
    try:
        main()
    except Exception as exc:
        print(json.dumps({"ok":False,"error":str(exc)},ensure_ascii=False))
        raise SystemExit(1)

