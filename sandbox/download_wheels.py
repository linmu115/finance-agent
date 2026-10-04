"""Download pinned Linux CPython 3.12 wheels from official PyPI and verify SHA256."""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import http.client
import json
from pathlib import Path
import time
import urllib.request

BASE=Path(__file__).resolve().parent
LOCK=BASE/"wheels.lock.json"
DEST=BASE/"wheelhouse"


def fetch(url):
    last=None
    for attempt in range(4):
        try:
            return urllib.request.urlopen(url,timeout=60)
        except OSError as exc:
            last=exc;time.sleep(attempt+1)
    raise last


def resolve():
    if LOCK.exists():
        return json.loads(LOCK.read_text())
    def one(requirement):
        name,version=requirement.split("==")
        for attempt in range(4):
            try:
                with fetch(f"https://pypi.org/pypi/{name}/{version}/json") as stream:
                    metadata=json.load(stream)
                break
            except (OSError,http.client.HTTPException):
                if attempt==3:raise
                time.sleep(attempt+1)
        binaries=[item for item in metadata["urls"] if item["filename"].endswith(".whl")
                  and "cp312-cp312" in item["filename"]
                  and "manylinux" in item["filename"] and "x86_64" in item["filename"]]
        pure=[item for item in metadata["urls"] if item["filename"].endswith("-none-any.whl")]
        selected=(binaries or pure)
        if not selected:raise RuntimeError("No compatible CPython 3.12 wheel: "+name)
        item=sorted(selected,key=lambda item:item["filename"])[0]
        print("Resolved",requirement,flush=True)
        return {"requirement":requirement,"filename":item["filename"],"url":item["url"],
                "sha256":item["digests"]["sha256"],"size":item["size"]}
    requirements=[line for line in (BASE/"requirements.lock").read_text().splitlines() if line.strip()]
    with ThreadPoolExecutor(max_workers=4) as pool:items=list(pool.map(one,requirements))
    LOCK.write_text(json.dumps(items,indent=2),encoding="utf-8")
    return items


def download(item):
    target=DEST/item["filename"]
    if target.exists():
        with target.open("rb") as stream:
            if hashlib.file_digest(stream,"sha256").hexdigest()==item["sha256"]:
                return
    print("Downloading",item["filename"],flush=True)
    for attempt in range(4):
        try:
            with fetch(item["url"]) as source,target.open("wb") as output:
                while chunk:=source.read(1024*1024):output.write(chunk)
            with target.open("rb") as stream:
                if hashlib.file_digest(stream,"sha256").hexdigest()!=item["sha256"]:
                    raise RuntimeError("SHA256 mismatch: "+item["filename"])
            return
        except (OSError,http.client.HTTPException,RuntimeError):
            if attempt==3:raise
            time.sleep(attempt+1)


if __name__=="__main__":
    DEST.mkdir(exist_ok=True)
    items=resolve()
    with ThreadPoolExecutor(max_workers=4) as pool:list(pool.map(download,items))
    print("Verified",len(items),"pinned wheels",sum(item["size"] for item in items),"bytes")
