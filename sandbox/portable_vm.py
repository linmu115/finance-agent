"""Project-local QEMU/Docker bootstrap. No installer or Windows feature changes.

python -m pip install -r sandbox/portable-requirements.txt
python sandbox/portable_vm.py prepare
python sandbox/portable_vm.py start
python sandbox/portable_vm.py connect
python sandbox/portable_vm.py sync
python sandbox/portable_vm.py build
"""
from __future__ import annotations
import argparse
import base64
import ctypes
import hashlib
import io
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import subprocess
import tarfile
import time
import urllib.parse
import urllib.request

ROOT = Path(__file__).resolve().parent / "runtime"
PROJECT = ROOT.parents[1]
PORT = 22222
DOWNLOADS = {
    "qemu.exe": ("https://qemu.weilnetz.de/w64/2025/qemu-w64-setup-20251224.exe",
                 "1285e85026910c7350fdf49c92323bb813f9feb0889f7aa7f2c6e3409c901ed5"),
    "alpine.qcow2": ("https://dl-cdn.alpinelinux.org/alpine/v3.22/releases/cloud/nocloud_alpine-3.22.4-x86_64-bios-cloudinit-r0.qcow2",
                     "b9d7685e3b0589308d0803de5a766d5a857adb2002e123fd4823fbdcb8466ca4"),
    "7zip.msi": ("https://www.7-zip.org/a/7z2301-x64.msi",
                "0ba639b6dacdf573d847c911bd147c6384381a54dac082b1e8c77bc73d58958b"),
}


def sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def ssh_args():
    return [
        "ssh", "-T", "-o", "BatchMode=yes", "-o", "IdentitiesOnly=yes",
        "-o", "ConnectTimeout=5", "-o", "StrictHostKeyChecking=yes",
        "-o", "UserKnownHostsFile=" + str(ROOT / "known_hosts"),
        "-i", str(ROOT / "vm_ed25519"), "-p", str(PORT), "root@127.0.0.1",
    ]


def ssh(command, data=None, timeout=30):
    return subprocess.run(ssh_args() + [command], input=data, capture_output=True, timeout=timeout,
                          creationflags=subprocess.CREATE_NO_WINDOW if os.name=="nt" else 0)


def active_pid():
    path=ROOT/"vm-process.json"
    if not path.exists():return None
    pid=json.loads(path.read_text(encoding="utf-8"))["pid"]
    if os.name!="nt":return None
    kernel=ctypes.WinDLL("kernel32",use_last_error=True)
    kernel.OpenProcess.restype=ctypes.c_void_p
    handle=kernel.OpenProcess(0x1000,False,pid)
    if not handle:return None
    try:
        buffer=ctypes.create_unicode_buffer(32768)
        size=ctypes.c_ulong(len(buffer))
        kernel.QueryFullProcessImageNameW.argtypes=[ctypes.c_void_p,ctypes.c_ulong,ctypes.c_wchar_p,ctypes.POINTER(ctypes.c_ulong)]
        ok=kernel.QueryFullProcessImageNameW(handle,0,buffer,ctypes.byref(size))
        expected=ROOT/"qemu/qemu-system-x86_64.exe"
        return pid if ok and Path(buffer.value).resolve()==expected.resolve() else None
    finally:
        kernel.CloseHandle.argtypes=[ctypes.c_void_p]
        kernel.CloseHandle(handle)


def prepare():
    if os.name!="nt":raise SystemExit("Use native Docker on Linux. Portable bootstrap targets Windows.")
    import olefile
    import pycdlib
    downloads=ROOT/"downloads";downloads.mkdir(parents=True,exist_ok=True)
    for name,(url,expected) in DOWNLOADS.items():
        path=downloads/name
        if not path.exists() or sha(path)!=expected:
            print("Downloading",name,flush=True)
            urllib.request.urlretrieve(url,path)
        if sha(path)!=expected:raise SystemExit("Download checksum mismatch: "+name)
    unzip=ROOT/"7zip";unzip.mkdir(exist_ok=True)
    if not (unzip/"_7z.exe").exists():
        ole=olefile.OleFileIO(downloads/"7zip.msi")
        for name in ole.listdir():
            content=ole.openstream(name).read()
            if content.startswith(b"MSCF"):
                (downloads/"7zip.cab").write_bytes(content)
                break
        else:raise SystemExit("7-Zip MSI cabinet was not found")
        # Administrative extraction through MSI is intentionally not used.
        subprocess.run(["tar","-xf",str(downloads/"7zip.cab"),"-C",str(unzip)],check=True)
    shutil.copyfile(unzip/"_7z.dll",unzip/"7z.dll")
    if not (ROOT/"qemu/qemu-system-x86_64.exe").exists():
        subprocess.run([str(unzip/"_7z.exe"),"x",str(downloads/"qemu.exe"),"-o"+str(ROOT/"qemu"),"-y"],check=True)
    key=ROOT/"vm_ed25519"
    if not key.exists():
        subprocess.run(["ssh-keygen","-q","-t","ed25519","-N","","-C","finance-local-vm","-f",str(key)],check=True)
    if not (ROOT/"seed.iso").exists():
        public=key.with_suffix(".pub").read_text().strip()
        password=secrets.token_urlsafe(48)
        user=(
            "#cloud-config\nhostname: finance-vm\nssh_pwauth: false\ndisable_root: false\n"
            "users:\n  - name: root\n    lock_passwd: false\n    ssh_authorized_keys:\n      - "+public+
            "\nchpasswd:\n  expire: false\n  users:\n    - name: root\n      type: text\n      password: "+password+
            "\npackage_update: true\npackages: [docker, python3]\nruncmd:\n"
            "  - [rc-update, add, cgroups, boot]\n  - [rc-service, cgroups, start]\n"
            "  - [rc-update, add, docker, default]\n  - [rc-service, docker, start]\n"
            "  - [sh, -c, 'mkdir -p /opt/finance /var/lib/finance; touch /var/lib/finance/bootstrap-complete']\n"
        )
        meta="instance-id: finance-local-v2\nlocal-hostname: finance-vm\n"
        iso=pycdlib.PyCdlib()
        iso.new(interchange_level=3,vol_ident="cidata",joliet=3,rock_ridge="1.09")
        for text,name,iso_name in [(user,"user-data","USER_DAT.;1"),(meta,"meta-data","META_DAT.;1")]:
            data=text.encode()
            iso.add_fp(io.BytesIO(data),len(data),iso_path="/"+iso_name,rr_name=name,joliet_path="/"+name)
        iso.write(str(ROOT/"seed.iso"));iso.close()
    if not (ROOT/"finance-vm.qcow2").exists():
        subprocess.run([str(ROOT/"qemu/qemu-img.exe"),"create","-f","qcow2","-F","qcow2","-b",
                        "downloads/alpine.qcow2","finance-vm.qcow2","20G"],cwd=ROOT,check=True)
    print("Prepared project-local VM; downloads SHA256 verified.")


def start():
    pid=active_pid()
    if pid:print("VM already running",pid);return
    executable=ROOT/"qemu/qemu-system-x86_64.exe"
    if not executable.exists():raise SystemExit("Run prepare first")
    # Relative paths and explicit firmware dir avoid QEMU Windows Unicode-path bugs.
    selected=OPTIONS.accel
    if selected=="auto":
        config=ROOT/"accelerator.json"
        selected=json.loads(config.read_text())["accel"] if config.exists() else "tcg"
    accelerator="whpx,kernel-irqchip=off" if selected=="whpx" else "tcg,thread=multi"
    cpu="qemu64" if selected=="whpx" else "max"
    cmd=[str(executable),"-L","qemu/share","-accel",accelerator,"-cpu",cpu,
         "-smp","2","-m","4096","-drive","file=finance-vm.qcow2,if=virtio,format=qcow2",
         "-drive","file=seed.iso,media=cdrom,readonly=on",
         "-netdev",f"user,id=n1,hostfwd=tcp:127.0.0.1:{PORT}-:22",
         "-device","virtio-net-pci,netdev=n1","-display","none","-serial","file:serial.log",
         "-monitor","none","-no-reboot"]
    if selected=="whpx":cmd.extend(["-machine","q35"])
    log=(ROOT/"qemu.log").open("wb")
    process=subprocess.Popen(cmd,cwd=ROOT,stdin=subprocess.DEVNULL,stdout=log,stderr=log,
                             creationflags=subprocess.CREATE_NO_WINDOW)
    (ROOT/"vm-process.json").write_text(json.dumps({"pid":process.pid,"ssh_port":PORT,"command":cmd},
                                                   ensure_ascii=False,indent=2),encoding="utf-8")
    print("VM started",process.pid,"accelerator",selected)


def connect():
    """Trust only a key obtained from this VM's project-local serial console."""
    if not active_pid():raise SystemExit("VM is not running")
    log=(ROOT/"serial.log").read_text(encoding="utf-8",errors="replace")
    keys=re.findall(r"(ssh-ed25519 [A-Za-z0-9+/=]+) root@finance-vm",log)
    if not keys and not (ROOT/"known_hosts").exists():
        raise SystemExit("VM has not published its console host key yet; inspect serial.log and retry")
    if keys:
        key=keys[-1]
        (ROOT/"known_hosts").write_text(f"[127.0.0.1]:{PORT} "+key+"\n")
    result=ssh("test -f /var/lib/finance/bootstrap-complete && docker version --format '{{json .Server}}'")
    if result.returncode:raise SystemExit("SSH/bootstrap not ready: "+result.stderr.decode(errors="replace")[-400:])
    # Windows RTC / accelerator changes can leave guest wall time offset; only the
    # owned VM clock is adjusted. Runtime deadlines use monotonic clocks.
    synced=ssh("date -u -s @"+str(int(time.time()))+" >/dev/null")
    if synced.returncode:raise SystemExit("Guest audit-clock synchronization failed")
    config={"host":"127.0.0.1","port":PORT,"identity_file":str(ROOT/"vm_ed25519"),
            "known_hosts":str(ROOT/"known_hosts")}
    (ROOT/"remote.json").write_text(json.dumps(config,ensure_ascii=False,indent=2),encoding="utf-8")
    print("Verified SSH and real Docker Engine",json.loads(result.stdout)["Version"])


def sync():
    buffer=io.BytesIO()
    with tarfile.open(fileobj=buffer,mode="w") as archive:
        for name in ["__init__.py","launcher.py","remote_worker.py","Dockerfile","requirements.lock",
                     "entrypoint.py",".dockerignore","test_launcher.py"]:
            archive.add(PROJECT/"sandbox"/name,arcname="sandbox/"+name)
        wheel_lock=PROJECT/"sandbox/wheels.lock.json"
        if wheel_lock.exists():
            for item in json.loads(wheel_lock.read_text()):
                path=PROJECT/"sandbox/wheelhouse"/item["filename"]
                if not path.is_file() or sha(path)!=item["sha256"]:
                    raise SystemExit("Run python sandbox/download_wheels.py to restore verified wheels")
                archive.add(path,arcname="sandbox/wheelhouse/"+item["filename"])
    result=ssh("mkdir -p /opt/finance && tar -xf - -C /opt/finance",buffer.getvalue(),timeout=120)
    if result.returncode:raise SystemExit(result.stderr.decode(errors="replace"))
    print("Trusted launcher and image recipe synced")


def build():
    proxy=urllib.request.getproxies().get("https")
    extra=""
    prefix=""
    if proxy:
        parsed=urllib.parse.urlparse(proxy)
        if parsed.hostname in {"localhost","127.0.0.1"} and parsed.port and not parsed.username:
            vmproxy=f"http://10.0.2.2:{parsed.port}"
            config=json.dumps({"proxies":{"http-proxy":vmproxy,"https-proxy":vmproxy,"no-proxy":"localhost,127.0.0.1"}})
            result=ssh("mkdir -p /etc/docker && cat > /tmp/finance-docker-proxy.json && if ! cmp -s /tmp/finance-docker-proxy.json /etc/docker/daemon.json; then cp /tmp/finance-docker-proxy.json /etc/docker/daemon.json && rc-service docker restart; fi",config.encode())
            if result.returncode:raise SystemExit("Guest Docker proxy configuration failed")
            extra=f" --build-arg HTTP_PROXY={vmproxy} --build-arg HTTPS_PROXY={vmproxy} --build-arg http_proxy={vmproxy} --build-arg https_proxy={vmproxy}"
            prefix=f"HTTP_PROXY={vmproxy} HTTPS_PROXY={vmproxy} "
    command="cd /opt/finance && "+prefix+"docker build --pull=false"+extra+" -t finance-analysis:0.1 sandbox"
    raise SystemExit(subprocess.call(ssh_args()+[command]))


def stop():
    if not active_pid():print("VM is stopped");return
    result=ssh("poweroff",timeout=10)
    if result.returncode not in {0,255}:raise SystemExit("Guest shutdown failed; inspect VM state")
    print("Graceful VM poweroff requested")


def status():
    print(json.dumps({"running":bool(active_pid()),"pid":active_pid(),"ssh_port":PORT,
                      "remote_configured":(ROOT/"remote.json").exists()},indent=2))


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action",choices=["prepare","start","connect","sync","build","stop","status"])
    parser.add_argument("--accel",choices=["auto","tcg","whpx"],default="auto")
    OPTIONS=parser.parse_args()
    globals()[OPTIONS.action]()
