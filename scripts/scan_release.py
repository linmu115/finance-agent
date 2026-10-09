"""Scan a runnable release without printing matched secret values.

Inspect all ZIP members, nested ZIP/whl/tgz data, and extracted PDF text.
This is pattern detection, not proof that arbitrary secrets cannot exist.
"""
from __future__ import annotations
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path
import re
import tarfile
import zipfile

KEY_PATTERNS = [
    (b"sk-", re.compile(rb"\bsk-[A-Za-z0-9_-]{24,}\b")),
    (b"PRIVATE KEY", re.compile(rb"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----")),
    (b"gh", re.compile(rb"\b(?:ghp|github_pat)-?[A-Za-z0-9_]{28,}\b")),
    (b"xox", re.compile(rb"\bxox[bpa]-?[A-Za-z0-9_]{28,}\b")),
    (b"AKIA", re.compile(rb"\bAKIA[0-9A-Z]{16}\b")),
    (b"tvly-", re.compile(rb"\btvly-[A-Za-z0-9_-]{20,}\b")),
]
BEARER = re.compile(rb"(?i)\bBearer\s+[A-Za-z0-9_\-\.]{28,}")
ASSIGN = re.compile(rb'''(?i)["']?(?:api[_-]?key|access[_-]?token|secret[_-]?key|client[_-]?secret)["']?\s*[:=]\s*["']([A-Za-z0-9_+/=.-]{24,})["']''')

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("package", type=Path)
    ap.add_argument("--term", action="append", default=[])
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--reviewed", type=Path, help="Exact path/hash/category exceptions independently reviewed by a human or agent")
    args = ap.parse_args()
    terms = [(term, encoding, term.encode(encoding)) for term in args.term for encoding in ("utf-8", "utf-16-le")]
    terms += [(term, "json-escaped", json.dumps(term, ensure_ascii=True)[1:-1].encode()) for term in args.term if not term.isascii()]

    def inspect(name, raw):
        findings = []
        numeric = 0
        patterns = [rx for marker, rx in KEY_PATTERNS if marker in raw]
        low = raw.lower()
        if b"bearer" in low: patterns.append(BEARER)
        if any(x in low for x in (b"api", b"access", b"secret", b"client")): patterns.append(ASSIGN)
        count = sum(len(rx.findall(raw)) for rx in patterns)
        if count: findings.append({"path":name,"category":"key-pattern","count":count,"file_sha256":hashlib.sha256(raw).hexdigest()})
        for term, enc, needle in terms:
            start = 0
            while (pos := raw.find(needle, start)) >= 0:
                start = pos + len(needle)
                # Bare numeric usernames can also be substrings of scientific
                # constants. Retain a separate count instead of hiding them.
                if term.isdecimal() and enc == "utf-8" and (raw[max(0,pos-1):pos].isdigit() or raw[start:start+1].isdigit()):
                    numeric += 1
                else:
                    findings.append({"path":name,"category":"blocked-term","term":term,"encoding":enc,"offset":pos,"file_sha256":hashlib.sha256(raw).hexdigest()})
        nested_count = 0
        suffix = Path(name).suffix.lower()
        if suffix in {".zip", ".whl", ".xlsx", ".docx"} or raw[:4] == b"PK\x03\x04":
            with zipfile.ZipFile(io.BytesIO(raw)) as archive:
                for entry in archive.infolist():
                    if not entry.is_dir():
                        f, n, c = inspect(name+"!"+entry.filename, archive.read(entry)); findings.extend(f); numeric += n; nested_count += c+1
        elif suffix == ".tgz":
            with tarfile.open(fileobj=io.BytesIO(raw), mode="r:gz") as archive:
                for entry in archive:
                    if entry.isfile():
                        f, n, c = inspect(name+"!"+entry.name, archive.extractfile(entry).read()); findings.extend(f); numeric += n; nested_count += c+1
        elif suffix == ".pdf":
            import fitz
            with fitz.open(stream=raw, filetype="pdf") as pdf:
                text = "\n".join(page.get_text() for page in pdf).encode()
            f, n, c = inspect(name+"!extracted-text", text); findings.extend(f); numeric += n; nested_count += c+1
        return findings, numeric, nested_count

    if args.package.is_dir():
        files = [(p.relative_to(args.package).as_posix(), p) for p in args.package.rglob("*") if p.is_file()]
        def scan(row):
            name, path = row
            return inspect(name, path.read_bytes())
        with ThreadPoolExecutor(max_workers=8) as pool: results = list(pool.map(scan, files))
        names = [name for name, _ in files]
        checksum = None
    else:
        with args.package.open("rb") as f: checksum = hashlib.file_digest(f,"sha256").hexdigest()
        with zipfile.ZipFile(args.package) as archive:
            names = [n for n in archive.namelist() if not n.endswith("/")]
            results = [inspect(name.split("/",1)[1], archive.read(name)) for name in names]
    report = {"created_at":datetime.now(timezone.utc).isoformat(),"package":args.package.name,"sha256":checksum,"files":len(names),"nested_members_or_pdf_texts":sum(r[2] for r in results),"numeric_substring_hits":sum(r[1] for r in results),"findings":[f for r in results for f in r[0]],"forbidden_paths":[],"limitations":"Known key formats and supplied terms; numeric substrings retained separately. Images are not OCR-scanned; screenshot privacy is visually reviewed."}
    for name in names:
        normalized = name.lower().replace("\\", "/")
        parts = normalized.split("/")
        if "__pycache__" in parts or normalized.endswith((".pyc", ".sqlite", ".sqlite3", ".db")) or "/data/evaluation/" in "/"+normalized or parts[-1] in {".env", "settings.json", "pyvenv.cfg"}:
            report["forbidden_paths"].append(name)
    reviewed = json.loads(args.reviewed.read_text(encoding="utf-8")) if args.reviewed else []
    report["reviewed_matches"] = []
    unresolved = []
    for finding in report["findings"]:
        rule = next((r for r in reviewed if all(finding.get(k) == r.get(k) for k in ("path","category","file_sha256","count","term","encoding","offset"))), None)
        if rule:
            report["reviewed_matches"].append({**finding,"reason":rule["reason"]})
        else: unresolved.append(finding)
    report["raw_finding_count"] = len(report["findings"])
    report["findings"] = unresolved
    report["status"] = "findings_require_review" if report["findings"] or report["forbidden_paths"] else "passed"
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps({k:report[k] for k in ("status","files","nested_members_or_pdf_texts","numeric_substring_hits")}))
    print("findings",len(report["findings"]),"forbidden_paths",len(report["forbidden_paths"]))
    return 0 if report["status"] == "passed" else 1

if __name__ == "__main__": raise SystemExit(main())
