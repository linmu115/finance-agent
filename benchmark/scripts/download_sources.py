"""Download public benchmark sources only; never reads user credentials."""
import concurrent.futures
import hashlib
import json
from pathlib import Path
import urllib.parse
import urllib.request
import time

ROOT = Path(__file__).resolve().parents[1]
SOURCES = [
    ("moutai_2024", "reports/moutai_2024.pdf", "https://static.cninfo.com.cn/finalpage/2025-04-03/1222993920.PDF", "贵州茅台2024年年度报告", "public-disclosure; original copyright retained"),
    ("midea_2024", "reports/midea_2024.pdf", "https://www.midea.com.cn/content/dam/mideacn-aem/投资者关系/投资者关系文件总览/2024文件/美的集团-2024年年度报告.PDF.coredownload.inline.pdf", "美的集团2024年年度报告", "public-disclosure; original copyright retained"),
    ("yili_2024", "reports/yili_2024.pdf", "https://static.cninfo.com.cn/finalpage/2025-04-30/1223421123.PDF", "伊利股份2024年年度报告", "public-disclosure; original copyright retained"),
]

def get(url):
    url = urllib.parse.quote(url, safe=":/?=&%#")
    req = urllib.request.Request(url, headers={"User-Agent": "FinancialResearchBenchmark/0.1 (public research data download)"})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=90) as response:
                chunks = []
                while True:
                    chunk = response.read(256 * 1024)
                    if not chunk:
                        break
                    chunks.append(chunk)
                result = b"".join(chunks)
                expected = response.headers.get("Content-Length")
                if expected and len(result) != int(expected):
                    raise ValueError("Incomplete HTTP body")
                return result
        except Exception:
            if attempt == 2:
                raise
            time.sleep(1)

def main():
    (ROOT / "sources").mkdir(parents=True, exist_ok=True)
    commit_file = ROOT / "sources" / "finqa_commit.txt"
    if commit_file.exists():
        commit = commit_file.read_text(encoding="utf-8").strip()
    else:
        api = json.loads(get("https://api.github.com/repos/czyssrs/FinQA/commits/main"))
        commit = api["sha"]
        commit_file.write_text(commit, encoding="utf-8")
    sources = SOURCES + [
        ("finqa_" + name, "finqa/" + name, "https://raw.githubusercontent.com/czyssrs/FinQA/" + commit + "/" + ("dataset/" if name.endswith(".json") else "") + name,
         "FinQA " + name, "repository MIT; preserve attribution; underlying financial-report rights retained")
        for name in ["dev.json", "test.json", "LICENSE", "README.md"]
    ]
    def download(entry):
        source_id, relative, url, title, license_note = entry
        path = ROOT / "sources" / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        content = path.read_bytes() if path.exists() else get(url)
        if path.suffix.lower() == ".pdf" and not content.startswith(b"%PDF"):
            raise ValueError("Not a PDF: " + source_id)
        if path.suffix == ".json":
            json.loads(content)
        path.write_bytes(content)
        row = {"id": source_id, "title": title, "url": url, "path": path.relative_to(ROOT).as_posix(), "bytes": len(content),
               "sha256": hashlib.sha256(content).hexdigest(), "retrieved_date": "2026-10-03", "rights": license_note}
        if source_id.startswith("finqa"):
            row["upstream_commit"] = commit
        print(json.dumps({"downloaded": source_id, "bytes": len(content)}, ensure_ascii=False), flush=True)
        return row
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        manifest = list(pool.map(download, sources))
    (ROOT / "sources" / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print("Saved source manifest with SHA-256 hashes.", flush=True)

if __name__ == "__main__":
    main()
