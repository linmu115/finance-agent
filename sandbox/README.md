# Scientific analysis container

Analysis code is executed only inside a Linux Docker container. A missing engine returns runner_unavailable. There is no Python/subprocess fallback on the service host.

## Service contract

    from pathlib import Path
    from sandbox import create_runner

    runner = create_runner(Path("service/data/analysis"))
    info = runner.availability()
    result = runner.run(
        "import pandas as pd\npd.read_csv('/input/table.csv').describe().to_csv('/output/summary.csv')",
        {"table.csv": Path("service/exported/project-A-table.csv")},
        project_id="project-A",
        run_id="generated_uuid_hex",
        timeout_seconds=120,
    )
    runner.status(result["run_id"], project_id="project-A")
    runner.cancel(result["run_id"], project_id="project-A")
    path = runner.artifact_path(result["run_id"], "summary.csv", project_id="project-A")

Call run in a service background thread. The service must resolve document IDs with a project-scoped database query and export a fresh copy. Never accept arbitrary host paths, Docker arguments, image references, SSH configuration or container names from model tool arguments.

run() returns run_id, project_id, status, exit_code, artifacts, error, image_id, input_sha256 and elapsed timing. Artifacts contain name, size and sha256; download paths are resolved and hashed again by artifact_path(). States: queued, running, succeeded, failed, timed_out, cancelled, output_rejected, runner_unavailable. Reusing a run ID is rejected; inspect its status instead. cancel() is safe across runner instances.

## Build and isolation

    python sandbox/download_wheels.py
    docker build --pull=false -t finance-analysis:0.1 sandbox
    python scripts/check_container.py --chart-input sandbox/evidence/chart_input.json --reference benchmark/evaluator/reference.sqlite
    python -m unittest sandbox.test_launcher -v

The Python base image is pinned by official registry manifest digest. Python dependencies are pinned in requirements.lock, and official PyPI wheel URLs/SHA256 are frozen in wheels.lock.json. download_wheels.py verifies every wheel before an offline package-install build step; wheels are mounted only at build time and are not duplicated into the image. Debian packages come from a fixed snapshot. The host resolves the finished image to its content-addressed image ID before each run and records that ID plus the inspected configuration. The runtime never pulls a changed tag implicitly.

Required settings: non-root UID 10001; read-only root filesystem and /input; writable task-only /output; 256 MiB temporary /tmp; no network; all capabilities dropped; no-new-privileges; 2 CPUs; 2 GiB memory and equal memory-swap (no extra swap); 64 PIDs; 120-second maximum execution; container cleanup on completion/cancellation/error.

Output collection allows only ordinary files under the task directory, at most 256 files and 50 MiB combined. Symlinks, Windows junctions, special files, deep paths, traversal and changed hashes are rejected. Host monitoring terminates oversized output and validation runs again after the container stops. The 50 MiB total is an export/rejection limit with polling, not a bind-mount filesystem quota: transient writes can exceed it before termination. A per-file kernel limit supplements the host check. Inputs are SHA256-checked after execution. Docker logs are capped by its local logging driver and copied to bounded host logs.

## Local Windows without Docker Desktop

The optional project-local runtime lives under ignored sandbox/runtime/. QEMU provides a Linux VM using existing WHPX acceleration on this machine, with TCG as a portable fallback; Docker remains the actual analysis boundary inside that VM. This does not enable Windows features, install global services or require a host reboot.

The VM uses two emulated CPUs and 4 GiB RAM. SSH is bound to 127.0.0.1:22222 and public-key authenticated. The project-local identity is used only by the trusted service and never mounted into an analysis container. The SSH host key must match the VM console before being saved. Do not distribute runtime/, its private key, seed ISO or disk as a public deliverable.

For a new Windows machine:

    python -m pip install -r sandbox/portable-requirements.txt
    python sandbox/portable_vm.py prepare
    python sandbox/portable_vm.py start
    python sandbox/portable_vm.py connect
    python sandbox/download_wheels.py
    python sandbox/portable_vm.py sync
    python sandbox/portable_vm.py build

Wait until the first boot finishes before connect; inspect sandbox/runtime/serial.log for progress. Subsequent sessions only need start. If Windows Hypervisor Platform already exists, start --accel whpx uses hardware acceleration with the validated qemu64/q35 configuration; it does not enable or install a Windows feature. TCG remains the portable fallback. status verifies the actual QEMU process path; stop requests graceful guest shutdown. Downloads are SHA256-pinned. The 7-Zip MSI is parsed as data and its cabinet extracted without running an installer. On a host with a local default HTTP proxy, build configures the guest Docker and build client to use the QEMU host gateway; those settings are never passed to analysis containers.

create_runner() selects this runtime when sandbox/runtime/remote.json exists. The remote trusted Python launcher receives only code and exported input copies over SSH, creates a real restricted Docker container, and transfers only manifest-listed, hashed artifacts back to Windows. Credentials and evaluator answers never enter the analysis container. remote_worker.py accepts fixed RPC methods; the model cannot run arbitrary VM shell commands.

The MCP service uses a filtered subprocess environment. Win32 OpenSSH additionally requires PROGRAMDATA; the adapter resolves only that non-secret OS folder from the Windows registry for its SSH child. It does not restore model API credentials or relax the service environment filter. Run `python scripts/check_container_env.py` to verify availability and a real container task under the same filtered environment.

Upstream references: [Docker resource constraints](https://docs.docker.com/engine/containers/resource_constraints/), [Docker run options](https://docs.docker.com/engine/containers/run/), [Docker network none](https://docs.docker.com/engine/network/drivers/none/), [QEMU official downloads](https://www.qemu.org/download/), [Alpine cloud images](https://alpinelinux.org/cloud/).

## Evidence

evidence/runtime.json contains actual S01-S07/S10 results, including the previous S04 probe attempt and its corrected re-run. Evidence from failed attempts is retained. evidence/recovery.json proves actual S08 project isolation and S11 recovery after SIGKILL of the trusted Linux runner process. Incomplete artifacts are withheld and the orphan container is removed. Launcher owner PID plus kernel creation token prevents confusion from PID reuse. Orphan cleanup runs on availability checks and status recovery.

All eight assigned runtime cases and both recovery cases passed in the current environment. The three company charts in evidence/charts were visually inspected; generated chart_data matches six service-extracted revenue facts and the separate evaluator reference. The actual 120-second timeout was observed at 120.221 seconds and cancellation at 0.559 seconds. Full application acceptance additionally requires S08/S09/S11/S12 application-level evidence; this module does not claim that the overall application gate passed. Host unit tests are not proof of kernel isolation.
