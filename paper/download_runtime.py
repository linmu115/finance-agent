"""Download official mirrored MSI using verified byte ranges, no installation."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import hashlib,json,urllib.request
BASE=Path(__file__).resolve().parent/"runtime"
BASE.mkdir(exist_ok=True)
URL="https://mirrors.ibiblio.org/libreoffice/stable/26.2.6/win/x86_64/LibreOffice_26.2.6_Win_x86-64.msi"
SIZE=373252096
CHUNK=8*1024*1024
def fetch(index):
    first=index*CHUNK;last=min(SIZE,first+CHUNK)-1
    target=BASE/f"lo.part{index:03}"
    if target.exists() and target.stat().st_size==last-first+1:return target
    req=urllib.request.Request(URL,headers={"Range":f"bytes={first}-{last}"})
    with urllib.request.urlopen(req,timeout=90) as response:
        if response.status!=206:raise RuntimeError("range_request_not_honored")
        if response.headers.get("Content-Range")!=f"bytes {first}-{last}/{SIZE}":raise RuntimeError("range_mismatch")
        data=response.read()
    if len(data)!=last-first+1:raise RuntimeError("range_size_mismatch")
    target.write_bytes(data)
    print("part",index,"complete",flush=True)
    return target
with ThreadPoolExecutor(max_workers=12) as pool:
    paths=list(pool.map(fetch,range((SIZE+CHUNK-1)//CHUNK)))
target=BASE/"LibreOffice-official.msi"
with target.open("wb") as output:
    for path in paths:output.write(path.read_bytes())
sha=hashlib.sha256(target.read_bytes()).hexdigest()
(BASE/"libreoffice-download.json").write_text(json.dumps({"url":URL,"size":SIZE,"sha256":sha,"version":"26.2.6","install_performed":False},indent=2),encoding="utf-8")
print("downloaded",target,"sha256",sha,flush=True)

