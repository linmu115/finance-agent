"""Trusted host Docker launcher. Analysis never falls back to a host subprocess.

The service owns instances of this class; tools provide Python text and exported
project-scoped input copies, never Docker arguments, host paths or credentials.
"""
from __future__ import annotations

import hashlib
import json
import os
import platform
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import subprocess
import sys
import threading
import time
import uuid
from typing import Any

MAX_OUTPUT = 50 * 1024 * 1024
MAX_INPUT = 100 * 1024 * 1024
MAX_FILES = 256
TERMINAL = {"succeeded", "failed", "timed_out", "cancelled", "output_rejected", "runner_unavailable"}
SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,99}$")
SAFE_NAME = re.compile(r"^[^\\/:*?\"<>|\x00-\x1f]{1,180}$")


class RunnerError(RuntimeError):
    pass


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def is_link(path: Path) -> bool:
    return path.is_symlink() or (hasattr(path, "is_junction") and path.is_junction())


def validate_id(value: str) -> str:
    if not isinstance(value, str) or not SAFE_ID.fullmatch(value):
        raise RunnerError("Invalid run_id or project_id")
    return value


def process_token(pid: int) -> str | None:
    """PID plus kernel creation identity prevents adopting a recycled PID."""
    if not isinstance(pid,int) or pid<=0:
        return None
    if sys.platform.startswith("linux"):
        try:
            return Path(f"/proc/{pid}/stat").read_text().rsplit(")",1)[1].split()[19]
        except (OSError,IndexError):
            return None
    if os.name=="nt":
        import ctypes
        kernel=ctypes.WinDLL("kernel32",use_last_error=True)
        kernel.OpenProcess.restype=ctypes.c_void_p
        handle=kernel.OpenProcess(0x1000,False,pid)
        if not handle:return None
        try:
            times=[ctypes.c_ulonglong() for _ in range(4)]
            kernel.GetProcessTimes.argtypes=[ctypes.c_void_p,*([ctypes.c_void_p]*4)]
            if kernel.GetProcessTimes(handle,*[ctypes.byref(value) for value in times]):
                return str(times[0].value)
        finally:
            kernel.CloseHandle.argtypes=[ctypes.c_void_p]
            kernel.CloseHandle(handle)
    return None


def validate_name(value: str) -> str:
    if not isinstance(value, str) or not SAFE_NAME.fullmatch(value) or value in {".", ".."}:
        raise RunnerError("Input names must be plain file names without path components")
    if value.endswith((" ", ".")) or value.split(".")[0].upper() in {
        "CON", "PRN", "AUX", "NUL", *[f"COM{i}" for i in range(10)], *[f"LPT{i}" for i in range(10)]
    }:
        raise RunnerError("Unsafe platform file name")
    return value


def scan_outputs(root: Path) -> list[dict[str, Any]]:
    """Refuse links, special files, excessive count/size; never follow a link."""
    root = root.absolute()
    if is_link(root):
        raise RunnerError("Output directory cannot be a link")
    files: list[dict[str, Any]] = []
    total = 0
    for directory, subdirs, names in os.walk(root, followlinks=False):
        for name in subdirs + names:
            path = Path(directory) / name
            relative = path.relative_to(root).as_posix()
            if len(relative) > 240 or len(PurePosixPath(relative).parts) > 8:
                raise RunnerError("Output path is too deep or too long")
            if is_link(path):
                raise RunnerError("Symbolic links and reparse points are forbidden in outputs")
            mode = path.lstat().st_mode
            if not stat.S_ISDIR(mode) and not stat.S_ISREG(mode):
                raise RunnerError("Only ordinary output files are allowed")
            if stat.S_ISREG(mode):
                size = path.stat().st_size
                total += size
                if total > MAX_OUTPUT:
                    raise RunnerError("Combined output exceeds 50 MiB")
                files.append({"name": relative, "size": size})
                if len(files) > MAX_FILES:
                    raise RunnerError("Output file count exceeds 256")
    return sorted(files, key=lambda item: item["name"])


class SandboxRunner:
    def __init__(self, state_root: Path | str, docker_bin: str | None = None,
                 image: str = "finance-analysis:0.1"):
        self.root = Path(state_root).absolute()
        self.root.mkdir(parents=True, exist_ok=True)
        if is_link(self.root):
            raise RunnerError("State directory must not be a link")
        self.docker = docker_bin or shutil.which("docker") or ""
        if not self.docker and os.name == "nt":
            candidate = Path(r"C:\Program Files\Docker\Docker\resources\bin\docker.exe")
            if candidate.is_file():
                self.docker = str(candidate)
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._/@:+-]{0,250}", image):
            raise RunnerError("Invalid image reference")
        self.image = image
        self._lock = threading.RLock()

    def _exec(self, arguments: list[str], timeout: float = 15) -> subprocess.CompletedProcess[str]:
        if not self.docker:
            raise RunnerError("Docker CLI is unavailable; analysis code was not executed")
        # No shell, no arbitrary Docker arguments, no inheritance into the container.
        creationflags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        try:
            return subprocess.run([self.docker, *arguments], capture_output=True, text=True,
                                  encoding="utf-8", errors="replace", timeout=timeout,
                                  creationflags=creationflags, stdin=subprocess.DEVNULL, check=False)
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise RunnerError(f"Docker operation failed: {type(exc).__name__}") from exc

    def availability(self) -> dict[str, Any]:
        try:
            version = self._exec(["version", "--format", "{{json .Server}}"], timeout=8)
            if version.returncode:
                return {"available": False, "reason": "Docker daemon unavailable", "version": None}
            server = json.loads(version.stdout)
            if not server or server.get("Os", "linux") != "linux":
                return {"available": False, "reason": "A Linux Docker engine is required", "version": None}
            image = self._exec(["image", "inspect", self.image])
            if image.returncode:
                return {"available": False, "reason": f"Build the analysis image {self.image} first",
                        "version": server.get("Version")}
            details = json.loads(image.stdout)[0]
            image_id = details["Id"]
            if not re.fullmatch(r"sha256:[a-f0-9]{64}", image_id):
                raise RunnerError("Docker image ID is not content-addressed")
            self.recover_orphans()
            return {"available": True, "reason": None, "version": server.get("Version"),
                    "image_id": image_id, "repo_digests": details.get("RepoDigests", [])}
        except (RunnerError, ValueError, KeyError, IndexError) as exc:
            return {"available": False, "reason": str(exc), "version": None}

    def _directory(self, run_id: str) -> Path:
        directory = self.root / validate_id(run_id)
        if is_link(directory):
            raise RunnerError("Run directory cannot be a link")
        return directory

    def _write(self, directory: Path, data: dict[str, Any]) -> None:
        with self._lock:
            temp = directory / ("state-" + uuid.uuid4().hex + ".tmp")
            temp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            os.replace(temp, directory / "state.json")

    def _audit(self, directory: Path, event: str, **details: Any) -> None:
        with self._lock, (directory / "audit.jsonl").open("a", encoding="utf-8") as stream:
            stream.write(json.dumps({"at": time.time(), "event": event, **details},
                                    ensure_ascii=False) + "\n")

    def status(self, run_id: str, *, project_id: str) -> dict[str, Any]:
        validate_id(project_id)
        state_path = self._directory(run_id) / "state.json"
        if not state_path.is_file() or is_link(state_path):
            raise RunnerError("Run not found")
        result = json.loads(state_path.read_text(encoding="utf-8"))
        if result["project_id"] != project_id:
            self._audit(state_path.parent,"access_denied",run_id=run_id,
                        requested_project_id=project_id,owner_project_id=result["project_id"])
            raise RunnerError("Run not found in this project")
        result=self._recover_if_abandoned(state_path.parent,result)
        return result

    def _recover_if_abandoned(self,directory: Path,state: dict[str,Any]) -> dict[str,Any]:
        if state.get("host_platform")!=sys.platform or state.get("host_name")!=platform.node():
            return state
        if state.get("status") not in {"queued","running"} and not state.get("cleanup_pending"):
            return state
        if state.get("owner_token") and process_token(state.get("owner_pid"))==state["owner_token"]:
            return state
        name="finance-"+validate_id(state["run_id"])
        removed=False
        try:
            inspected=self._exec(["inspect",name],timeout=5)
            if inspected.returncode==0:
                info=json.loads(inspected.stdout)[0]
                labels=info.get("Config",{}).get("Labels",{})
                if labels.get("finance.run_id")!=state["run_id"] or labels.get("finance.runner")!="1":
                    raise RunnerError("Refusing to remove a container without matching runner labels")
                if info["State"]["Running"]:self._exec(["kill",name],timeout=5)
                removed=self._exec(["rm","-f",name],timeout=5).returncode==0
            elif "no such" in inspected.stderr.lower():
                removed=True
        except (RunnerError,ValueError,KeyError,IndexError):
            pass
        state.update(status="failed",artifacts=[],error="Host runner interrupted; unfinished artifacts withheld",
                     container_removed=removed,cleanup_pending=not removed,recovered_at=time.time())
        self._write(directory,state)
        self._audit(directory,"orphan_recovered",run_id=state["run_id"],container_removed=removed)
        return state

    def recover_orphans(self) -> list[str]:
        recovered=[]
        for path in self.root.glob("*/state.json"):
            if is_link(path) or is_link(path.parent):continue
            try:
                state=json.loads(path.read_text(encoding="utf-8"))
                before=state.get("status")
                after=self._recover_if_abandoned(path.parent,state)
                if before in {"queued","running"} and after.get("status")=="failed":
                    recovered.append(after["run_id"])
            except (OSError,ValueError,RunnerError):
                continue
        return recovered

    def cancel(self, run_id: str, *, project_id: str) -> dict[str, Any]:
        result = self.status(run_id, project_id=project_id)
        if result["status"] in TERMINAL:
            return result
        directory = self._directory(run_id)
        (directory / "cancel.request").write_text("requested", encoding="ascii")
        self._audit(directory, "cancel_requested")
        # A trusted container name comes from our validated run ID, not the model.
        try:
            self._exec(["kill", "finance-" + run_id], timeout=5)
        except RunnerError:
            pass
        return {**result, "cancel_requested": True}

    def command(self, *, run_id: str, input_dir: Path, output_dir: Path, image_id: str) -> list[str]:
        validate_id(run_id)
        for path in (input_dir, output_dir):
            if "," in str(path) or "\n" in str(path):
                raise RunnerError("Docker bind paths must not contain commas or newlines")
        return [
            "create", "--name", "finance-" + run_id, "--pull", "never",
            "--label", "finance.runner=1", "--label", "finance.run_id=" + run_id,
            "--network", "none", "--read-only", "--user", "10001:10001",
            "--cap-drop", "ALL", "--security-opt", "no-new-privileges=true",
            "--cpus", "2", "--memory", "2g", "--memory-swap", "2g",
            "--pids-limit", "64", "--ulimit", "nofile=128:128", "--ulimit", "core=0:0",
            "--stop-timeout", "1", "--log-driver", "local",
            "--log-opt", "max-size=1m", "--log-opt", "max-file=1",
            "--log-opt", "compress=false",
            "--tmpfs", "/tmp:rw,nosuid,nodev,noexec,size=268435456,mode=1777",
            "--mount", f"type=bind,src={input_dir.absolute()},dst=/input,readonly",
            "--mount", f"type=bind,src={output_dir.absolute()},dst=/output",
            "--workdir", "/output",
            "--env", "HOME=/tmp", "--env", "MPLCONFIGDIR=/tmp/matplotlib",
            "--env", "MPLBACKEND=Agg", "--env", "OPENBLAS_NUM_THREADS=1",
            "--env", "OMP_NUM_THREADS=1", "--env", "MKL_NUM_THREADS=1",
            "--env", "NUMEXPR_NUM_THREADS=1",
            image_id,
        ]

    def run(self, code: str, inputs: dict[str, Path | str], *, project_id: str,
            run_id: str | None = None, timeout_seconds: int = 120) -> dict[str, Any]:
        run_id = validate_id(run_id or uuid.uuid4().hex)
        project_id = validate_id(project_id)
        if not isinstance(code, str) or not code.strip() or len(code.encode("utf-8")) > 512 * 1024:
            raise RunnerError("Analysis code must be 1 to 524288 bytes")
        if isinstance(timeout_seconds, bool) or not isinstance(timeout_seconds, int) or not 1 <= timeout_seconds <= 120:
            raise RunnerError("Timeout must be an integer from 1 to 120 seconds")
        if not isinstance(inputs, dict) or len(inputs) > MAX_FILES:
            raise RunnerError("Too many input files")
        validated: list[tuple[str, Path]] = []
        total = 0
        for name, source in inputs.items():
            validate_name(name)
            if name.casefold() == "__analysis__.py":
                raise RunnerError("Reserved input name")
            path = Path(source).absolute()
            # Refuse any link in the source path, including parent junctions.
            if any(is_link(part) for part in [path, *path.parents]) or not path.is_file():
                raise RunnerError("Inputs must be ordinary files without links")
            total += path.stat().st_size
            if total > MAX_INPUT:
                raise RunnerError("Combined inputs exceed 100 MiB")
            validated.append((name, path))
        directory = self._directory(run_id)
        try:
            directory.mkdir(exist_ok=False)
        except FileExistsError as exc:
            raise RunnerError("run_id already exists; use status instead of rerunning") from exc
        began = time.monotonic()
        state: dict[str, Any] = {
            "run_id": run_id, "project_id": project_id, "status": "queued",
            "exit_code": None, "artifacts": [], "error": None, "image_id": None,
            "created_at": time.time(), "elapsed_seconds": 0, "input_sha256": {},
            "timeout_seconds": timeout_seconds,
            "owner_pid":os.getpid(),"owner_token":process_token(os.getpid()),
            "host_platform":sys.platform,"host_name":platform.node(),
        }
        self._write(directory, state)
        self._audit(directory, "queued", project_id=project_id)
        name = "finance-" + run_id
        container_created = False
        running_at = None
        input_dir, output_dir = directory / "input", directory / "output"
        try:
            available = self.availability()
            if not available["available"]:
                state.update(status="runner_unavailable", error=available["reason"])
                return state
            state["image_id"] = available["image_id"]
            state["repo_digests"] = available.get("repo_digests", [])
            input_dir.mkdir()
            output_dir.mkdir()
            # Linux bind-mounted output must be writable by container UID 10001.
            # Parent task directory remains host-only; output holds untrusted artifacts.
            output_dir.chmod(0o777)
            input_dir.chmod(0o755)
            for filename, source in validated:
                target = input_dir / filename
                shutil.copyfile(source, target)
                target.chmod(0o444)
                state["input_sha256"][filename] = digest(target)
            code_path = input_dir / "__analysis__.py"
            code_path.write_text(code, encoding="utf-8")
            code_path.chmod(0o444)
            state["code_sha256"] = digest(code_path)
            command = self.command(run_id=run_id, input_dir=input_dir, output_dir=output_dir,
                                   image_id=state["image_id"])
            created = self._exec(command)
            if created.returncode:
                raise RunnerError("Container create failed: " + created.stderr[-2000:])
            container_created = True
            config = self._exec(["inspect", name])
            if config.returncode:
                raise RunnerError("Cannot verify container configuration")
            inspected = json.loads(config.stdout)[0]
            self._verify_config(inspected)
            (directory / "container-config.json").write_text(
                json.dumps(inspected, ensure_ascii=False, indent=2), encoding="utf-8")
            self._audit(directory, "container_created", image_id=state["image_id"])
            if (directory / "cancel.request").exists():
                state["status"] = "cancelled"
                return state
            started = self._exec(["start", name])
            if started.returncode:
                raise RunnerError("Container start failed: " + started.stderr[-2000:])
            running_at = time.monotonic()
            state.update(status="running", started_at=time.time())
            self._write(directory, state)
            self._audit(directory, "running")
            while True:
                if (directory / "cancel.request").exists():
                    state["status"] = "cancelled"
                    break
                if time.monotonic() - running_at >= timeout_seconds:
                    state["status"] = "timed_out"
                    break
                try:
                    scan_outputs(output_dir)
                except (RunnerError, OSError) as exc:
                    state.update(status="output_rejected", error=str(exc))
                    break
                inspection = self._exec(["inspect", "--format", "{{json .State}}", name], timeout=5)
                if inspection.returncode:
                    raise RunnerError("Container disappeared during execution")
                live = json.loads(inspection.stdout)
                if not live["Running"]:
                    state["execution_seconds"] = round(time.monotonic() - running_at, 3)
                    state["exit_code"] = live["ExitCode"]
                    state["oom_killed"] = live.get("OOMKilled", False)
                    state["status"] = "succeeded" if live["ExitCode"] == 0 else "failed"
                    state["error"] = "Memory limit exceeded" if live.get("OOMKilled") else (
                        None if live["ExitCode"] == 0 else "Analysis process exited with an error")
                    break
                time.sleep(0.15)
            if state["status"] in {"timed_out", "cancelled", "output_rejected"}:
                self._exec(["kill", name], timeout=5)
                state["execution_seconds"] = round(time.monotonic() - running_at, 3)
            # Kill/inspect occurs before any artifact export to prevent TOCTOU by live code.
            self._exec(["stop", "--time", "0", name], timeout=5)
            final_inspect = self._exec(["inspect", "--format", "{{json .State}}", name], timeout=5)
            if final_inspect.returncode == 0:
                final = json.loads(final_inspect.stdout)
                if final.get("Running"):
                    raise RunnerError("Container remains live; artifacts withheld")
                state["exit_code"] = final.get("ExitCode")
                state["oom_killed"] = final.get("OOMKilled", False)
            log = self._exec(["logs", "--tail", "1000", name], timeout=5)
            # Docker logging driver bounds disk usage; also bound application audit log.
            state["stdout"] = log.stdout[-1024*1024:]
            state["stderr"] = log.stderr[-1024*1024:]
            (directory / "stdout.log").write_text(state["stdout"], encoding="utf-8")
            (directory / "stderr.log").write_text(state["stderr"], encoding="utf-8")
            for filename, expected in state["input_sha256"].items():
                if digest(input_dir / filename) != expected:
                    raise RunnerError("Input integrity verification failed")
            if state["status"] == "succeeded":
                try:
                    artifacts = scan_outputs(output_dir)
                    for artifact in artifacts:
                        artifact["sha256"] = digest(output_dir / artifact["name"])
                    state["artifacts"] = artifacts
                except (RunnerError, OSError) as exc:
                    state.update(status="output_rejected", error=str(exc), artifacts=[])
        except (RunnerError, ValueError, KeyError, OSError) as exc:
            state.update(status="failed", error=str(exc), artifacts=[])
        finally:
            if container_created:
                try:
                    removed = self._exec(["rm", "-f", name], timeout=5)
                    state["container_removed"] = removed.returncode == 0
                except RunnerError:
                    state["container_removed"] = False
                if not state["container_removed"]:
                    state.update(status="failed", error="Container cleanup failed; manual inspection required",
                                 artifacts=[])
            if running_at is not None and "execution_seconds" not in state:
                state["execution_seconds"] = round(time.monotonic() - running_at, 3)
            state["elapsed_seconds"] = round(time.monotonic() - began, 3)
            state["finished_at"] = time.time()
            self._write(directory, state)
            self._audit(directory, "finished", status=state["status"], elapsed_seconds=state["elapsed_seconds"])
        return state

    @staticmethod
    def _verify_config(info: dict[str, Any]) -> None:
        host = info.get("HostConfig", {})
        config = info.get("Config", {})
        expected = {
            "NetworkMode": "none", "ReadonlyRootfs": True, "Memory": 2147483648,
            "MemorySwap": 2147483648, "NanoCpus": 2000000000, "PidsLimit": 64,
            "Privileged": False,
        }
        for key, value in expected.items():
            if host.get(key) != value:
                raise RunnerError(f"Docker did not apply required policy: {key}")
        if config.get("User") != "10001:10001":
            raise RunnerError("Container must use non-root UID 10001")
        if "ALL" not in [value.upper() for value in host.get("CapDrop", [])]:
            raise RunnerError("Container capabilities were not dropped")
        if not any(value in {"no-new-privileges", "no-new-privileges=true"} for value in host.get("SecurityOpt", [])):
            raise RunnerError("Container no-new-privileges is missing")
        mounts = info.get("Mounts", [])
        binds = [item for item in mounts if item.get("Type") == "bind"]
        if len(binds) != 2 or {item.get("Destination") for item in binds} != {"/input", "/output"}:
            raise RunnerError("Unexpected host filesystem mounts")
        if any(item.get("RW") for item in binds if item.get("Destination") == "/input"):
            raise RunnerError("Container inputs are not read-only")
        if host.get("Binds") or host.get("VolumesFrom") or host.get("Devices"):
            raise RunnerError("Unexpected inherited mount or device")

    def artifact_path(self, run_id: str, name: str, *, project_id: str) -> Path:
        state = self.status(run_id, project_id=project_id)
        if state["status"] != "succeeded":
            raise RunnerError("Artifacts are unavailable for this run")
        if not isinstance(name, str) or "\\" in name or ":" in name or name.startswith("/"):
            raise RunnerError("Invalid artifact path")
        parts = PurePosixPath(name).parts
        if not parts or any(part in {".", ".."} for part in parts) or str(PurePosixPath(name)) != name:
            raise RunnerError("Invalid artifact path")
        manifest = next((item for item in state["artifacts"] if item["name"] == name), None)
        if manifest is None:
            raise RunnerError("Artifact not found")
        root = self._directory(run_id) / "output"
        path = root.joinpath(*parts)
        if any(is_link(root.joinpath(*parts[:i])) for i in range(len(parts) + 1)):
            raise RunnerError("Artifact path contains a link")
        if not path.is_file() or not path.resolve().is_relative_to(root.resolve()):
            raise RunnerError("Artifact is not a regular task output")
        if path.stat().st_size != manifest["size"] or digest(path) != manifest["sha256"]:
            raise RunnerError("Artifact integrity verification failed")
        return path
