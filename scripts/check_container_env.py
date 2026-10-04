"""Exercise the real runner under the MCP service's secret-filtered environment."""
import json
import os
from pathlib import Path
import subprocess
import sys


def main():
    root = Path(__file__).resolve().parents[1]
    allowed = {"PATH", "SYSTEMROOT", "WINDIR", "TEMP", "TMP", "USERPROFILE", "LOCALAPPDATA", "APPDATA"}
    env = {key: value for key, value in os.environ.items() if key.upper() in allowed}
    env.update(PYTHONPATH=str(root), PYTHONIOENCODING="utf-8", PYTHONUNBUFFERED="1")
    code = """import json
from sandbox import create_runner
r = create_runner('sandbox/evidence/env-probe')
availability = r.availability()
state = r.run("from pathlib import Path;Path('/output/smoke.txt').write_text('real Docker via filtered MCP environment')", {}, project_id='filtered-env-smoke') if availability['available'] else None
print(json.dumps({'availability': availability, 'run': state}))
"""
    proc = subprocess.run([sys.executable, "-c", code], cwd=root, env=env,
                          capture_output=True, encoding="utf-8", timeout=90)
    report = {"returncode": proc.returncode,
              "programdata_present_in_parent": any(key.upper() == "PROGRAMDATA" for key in env),
              "payload": json.loads(proc.stdout) if proc.stdout else None,
              "stderr": proc.stderr}
    target = root / "sandbox/evidence/service-env-smoke.json"
    target.parent.mkdir(exist_ok=True)
    target.write_text(json.dumps(report, indent=2), encoding="utf-8")
    state = (report.get("payload") or {}).get("run") or {}
    passed = proc.returncode == 0 and state.get("status") == "succeeded" and state.get("container_removed")
    print(json.dumps({"status": "PASS" if passed else "FAIL", "run_id": state.get("run_id")}))
    return 0 if passed else 2


if __name__ == "__main__":
    raise SystemExit(main())
