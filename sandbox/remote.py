"""SSH transport to the trusted host of a real Docker engine.

Only exported task copies cross the boundary. User code runs in Docker inside the
Linux VM. SSH keys and Docker access remain in the trusted service/VM host.
"""
from __future__ import annotations
import base64
import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import threading
import time
import uuid

from .launcher import SandboxRunner, RunnerError, validate_id, validate_name, is_link, MAX_INPUT, MAX_OUTPUT, MAX_FILES, digest


class RemoteSandboxRunner(SandboxRunner):
    def __init__(self, state_root, config_path):
        super().__init__(state_root)
        self.remote = json.loads(Path(config_path).read_text(encoding="utf-8"))
        host = self.remote["host"]
        if host not in {"127.0.0.1", "localhost", "::1"}:
            raise RunnerError("Portable VM transport is restricted to localhost")
        port = self.remote["port"]
        if not isinstance(port, int) or not 1024 <= port <= 65535:
            raise RunnerError("Invalid VM SSH port")
        self.ssh_args = [
            "ssh", "-T", "-o", "BatchMode=yes", "-o", "IdentitiesOnly=yes",
            "-o", "ConnectTimeout=5", "-o", "StrictHostKeyChecking=yes",
            "-o", "UserKnownHostsFile=" + str(Path(self.remote["known_hosts"]).absolute()),
            "-i", str(Path(self.remote["identity_file"]).absolute()), "-p", str(port),
            "root@" + host, "python3", "/opt/finance/sandbox/remote_worker.py",
        ]

    def _rpc(self, method, *, timeout=20, **arguments):
        try:
            child_env = os.environ.copy()
            if os.name == "nt" and not child_env.get("PROGRAMDATA"):
                # Win32 OpenSSH exits 255 without diagnostics when its OS data
                # directory is absent from the MCP service's filtered environment.
                # Restore only this non-secret Windows folder for the SSH child.
                import winreg
                with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                        r"SOFTWARE\Microsoft\Windows\CurrentVersion\Explorer\Shell Folders") as key:
                    child_env["PROGRAMDATA"] = winreg.QueryValueEx(key, "Common AppData")[0]
            proc = subprocess.run(
                self.ssh_args, input=json.dumps({"method": method, **arguments}, ensure_ascii=False),
                capture_output=True, encoding="utf-8", errors="replace", timeout=timeout,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name=="nt" else 0,
                env=child_env,
            )
        except (subprocess.TimeoutExpired, OSError) as exc:
            raise RunnerError("Portable VM SSH unavailable: " + type(exc).__name__) from exc
        try:
            payload=json.loads(proc.stdout)
        except ValueError as exc:
            raise RunnerError("Portable VM returned no valid host response") from exc
        if proc.returncode or not payload.get("ok"):
            raise RunnerError(payload.get("error","Portable VM host operation failed"))
        return payload["result"]

    def availability(self):
        try:
            result=self._rpc("availability")
            return {**result,"transport":"ssh-local-vm","isolation":"Docker in Linux VM"}
        except RunnerError as exc:
            return {"available":False,"reason":str(exc),"version":None,"transport":"ssh-local-vm"}

    def run(self, code, inputs, *, project_id, run_id=None, timeout_seconds=120):
        run_id=validate_id(run_id or uuid.uuid4().hex)
        project_id=validate_id(project_id)
        directory=self._directory(run_id)
        if directory.exists():
            raise RunnerError("run_id already exists; use status instead of rerunning")
        if not isinstance(code,str) or not code.strip() or len(code.encode())>512*1024:
            raise RunnerError("Invalid analysis code size")
        if isinstance(timeout_seconds,bool) or not isinstance(timeout_seconds,int) or not 1<=timeout_seconds<=120:
            raise RunnerError("Timeout must be 1 to 120 seconds")
        encoded={};total=0
        if not isinstance(inputs,dict) or len(inputs)>MAX_FILES:
            raise RunnerError("Too many input files")
        for name,source in inputs.items():
            validate_name(name)
            path=Path(source).absolute()
            if any(is_link(part) for part in [path,*path.parents]) or not path.is_file():
                raise RunnerError("Inputs must be ordinary files")
            total+=path.stat().st_size
            if total>MAX_INPUT:raise RunnerError("Combined inputs exceed 100 MiB")
            data=path.read_bytes()
            encoded[name]=base64.b64encode(data).decode("ascii")
        directory.mkdir()
        initial={"run_id":run_id,"project_id":project_id,"status":"queued","artifacts":[],"error":None}
        self._write(directory,initial)
        began=time.monotonic()
        stopped=threading.Event()
        def relay_cancel():
            while not stopped.wait(0.2):
                if (directory/"cancel.request").exists():
                    try:
                        self._rpc("cancel",run_id=run_id,project_id=project_id,timeout=10)
                        return
                    except RunnerError:
                        pass
        cancel_thread=threading.Thread(target=relay_cancel,daemon=True)
        cancel_thread.start()
        try:
            if (directory/"cancel.request").exists():
                state={**initial,"status":"cancelled","container_removed":True,"elapsed_seconds":0}
                self._write(directory,state)
                return state
            state=self._rpc("run",code=code,inputs=encoded,run_id=run_id,project_id=project_id,
                            timeout_seconds=timeout_seconds,timeout=timeout_seconds+90)
            if state["status"]=="succeeded":
                outputs=self._rpc("artifacts",run_id=run_id,project_id=project_id,timeout=60)
                output=directory/"output";output.mkdir()
                total=0
                manifests={item["name"]:item for item in state["artifacts"]}
                if set(outputs)!=set(manifests):raise RunnerError("Remote artifact manifest mismatch")
                for name,encoded_data in outputs.items():
                    parts=PurePosixPath(name).parts
                    if not parts or any(part in {".",".."} for part in parts) or "\\" in name or ":" in name or name.startswith("/"):
                        raise RunnerError("Unsafe remote artifact path")
                    data=base64.b64decode(encoded_data,validate=True);total+=len(data)
                    if total>MAX_OUTPUT:raise RunnerError("Remote output exceeds 50 MiB")
                    path=output.joinpath(*parts);path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(data)
                    if path.stat().st_size!=manifests[name]["size"] or digest(path)!=manifests[name]["sha256"]:
                        raise RunnerError("Remote output integrity mismatch")
            evidence=self._rpc("evidence",run_id=run_id,project_id=project_id)
            for name,content in evidence.items():
                if name in {"audit.jsonl","container-config.json","stdout.log","stderr.log"}:
                    (directory/name).write_text(content,encoding="utf-8")
            self._write(directory,state)
            return state
        except (RunnerError,OSError,ValueError) as exc:
            state={**initial,"status":"failed","error":str(exc),"elapsed_seconds":round(time.monotonic()-began,3)}
            self._write(directory,state)
            return state
        finally:
            stopped.set()

    def status(self,run_id,*,project_id):
        validate_id(run_id);validate_id(project_id)
        try:
            remote=self._rpc("status",run_id=run_id,project_id=project_id)
            local=super().status(run_id,project_id=project_id)
            if remote["status"]=="succeeded" and local["status"]=="queued":
                return {**remote,"status":"running","phase":"exporting_artifacts"}
            if remote.get("recovered_at") and local.get("recovered_at")!=remote["recovered_at"]:
                directory=self._directory(run_id)
                self._write(directory,remote)
                evidence=self._rpc("evidence",run_id=run_id,project_id=project_id)
                for name,content in evidence.items():
                    if name in {"audit.jsonl","container-config.json","stdout.log","stderr.log"}:
                        (directory/name).write_text(content,encoding="utf-8")
            return remote
        except RunnerError:
            return super().status(run_id,project_id=project_id)

    def cancel(self,run_id,*,project_id):
        validate_id(run_id);validate_id(project_id)
        local=self.status(run_id,project_id=project_id)
        if local["status"] in {"succeeded","timed_out","cancelled","output_rejected","runner_unavailable"}:
            return local
        (self._directory(run_id)/"cancel.request").write_text("requested",encoding="ascii")
        try:
            return self._rpc("cancel",run_id=run_id,project_id=project_id)
        except RunnerError:
            return {**local,"cancel_requested":True}

    def artifact_path(self,run_id,name,*,project_id):
        # The host copy and its digest are checked again at download time.
        return SandboxRunner.artifact_path(self,run_id,name,project_id=project_id)
