"""Create a reviewed, allowlisted research handoff. Default: dry run only.

No credentials, local models, runtime VMs, downloaded wheels or case databases
are delivery inputs. The manifest records exact hashes; secret checks never
print matched content. This is a local research handoff, not a public mirror.
"""
from __future__ import annotations

import argparse
import fnmatch
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import sys
import tarfile
from datetime import datetime, timezone
from urllib.parse import urlparse
import zipfile

ROOT = Path(__file__).resolve().parents[1]
ROOT_FILES = {
    "README.txt", "WORK_STATUS.md", "package.json", "package-lock.json",
    "requirements.lock.txt", "tsconfig.tools.json", ".gitignore", ".env.example", "start-finance.cmd",
}
SOURCE_EXT = {".py", ".ts", ".tsx", ".js", ".cjs", ".mjs", ".json", ".css", ".html", ".txt", ".md", ".ps1"}
DATA_EXT = {".json", ".jsonl", ".pdf", ".png", ".csv", ".tsv", ".sqlite", ".sha256", ".md", ".txt", ".py"}
EVIDENCE_EXT = {".json", ".jsonl", ".png", ".csv", ".txt", ".md", ".log", ".py"}
BLOCKED_PARTS = {
    "data", "local-model", "node_modules", ".venv", "__pycache__", ".git",
    "runtime", ".runtime", "downloads", "wheelhouse", ".dependency-verification",
    "private", "private_keys", "private-keys", ".ssh", "secrets", "credentials",
}
BLOCKED_NAMES = {"settings.json", "settings.enc", "credentials.json", "id_rsa", "id_ed25519"}
BLOCKED_EXT = {".pem", ".key", ".p12", ".pfx", ".jks", ".qcow2", ".vhd", ".vhdx", ".iso", ".whl", ".pyc"}
VENDOR = "vendor/brace-expansion-5.0.12.tgz"
VENDOR_SHA512 = "628bd0debce168b308ac38cd0cc90d4b4d6d79af77aa11211b9c72f1febe47497e770dca8bee6c0a822823de368ae2d94c75a881692d830543854d3d88d12299"

# Patterns identify likely credential values; regex source itself is not a key.
SECRET_PATTERNS = [
    re.compile(rb"\bsk-[A-Za-z0-9_-]{24,}\b"),
    re.compile(rb"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----"),
    re.compile(rb"\b(?:ghp|github_pat|xoxb|xoxp|xoxa)-?[A-Za-z0-9_]{28,}\b"),
    re.compile(rb"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(rb"(?i)\bBearer\s+[A-Za-z0-9_\-\.]{28,}"),
    re.compile(rb'''(?i)["']?(?:api[_-]?key|access[_-]?token|secret[_-]?key|client[_-]?secret)["']?\s*[:=]\s*["']([A-Za-z0-9_+/=.-]{24,})["']'''),
]

# One independently reviewed local fault-injection fixture. A file edit or any
# different token invalidates the exception. No real API request uses this value.
REVIEWED_TEST_FIXTURES = {
    "service/tests/test_ocr_runtime.py": {
        "file_sha256": "384531518b3fff099a653d37efbe45ef783f478fb2d92279dc04933bdcf7f50d",
        "value_sha256": "23e5a4ebbf69ad142e047b6831c4183933312a5060f71a5264cc57a91c50373b",
        "pattern_index": 5,
        "reason": "Agent-reviewed synthetic credential in temporary local OCR fault-injection and diagnostic-redaction test; no external API call.",
    },
}


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def forbidden(relative: str) -> bool:
    parts = PurePosixPath(relative).parts
    lowered = tuple(p.lower() for p in parts)
    name = lowered[-1]
    return (
        any(p in BLOCKED_PARTS for p in lowered)
        or name in BLOCKED_NAMES
        or (name.startswith(".env") and relative != ".env.example")
        or PurePosixPath(name).suffix in BLOCKED_EXT
        or name.endswith(".pub")
    )


def deepseek_runs() -> set[str]:
    selected = set()
    base = ROOT / "benchmark/runs"
    if base.exists():
        for manifest in sorted(base.glob("*/manifest.json")):
            if manifest.is_symlink() or manifest.parent.is_symlink():
                continue
            try:
                data = read_json(manifest)
                provider = urlparse(data.get("settings", {}).get("llm", {}).get("baseUrl", ""))
                traceable = all(re.fullmatch(r"[a-fA-F0-9]{64}", str(data.get(k, ""))) for k in ("configHash", "promptHash"))
                if data.get("model") == "deepseek-flash" and provider.scheme == "https" and provider.hostname == "api.deepseek.com" and traceable:
                    selected.add(manifest.parent.name)
            except (OSError, ValueError):
                pass
    return selected


def run_evidence_allowed(parts: tuple[str, ...]) -> bool:
    # benchmark/runs/RUN/{manifest,known-code-change}.json
    if len(parts) == 4:
        return parts[3] in {"manifest.json", "known-code-change.json", "summary.json", "repeatability.json"}
    # No input/, data/, settings, worker logs or arbitrary result.json recursion.
    if len(parts) >= 5 and re.fullmatch(r"round-\d+", parts[3]):
        if len(parts) == 5:
            return parts[4] in {"predictions.jsonl", "score.json", "traces.json"}
        if len(parts) == 6:
            return bool(re.fullmatch(r"[A-Za-z0-9_.-]+", parts[4])) and parts[5] in {"result.json", "audit.jsonl"}
    return False


def allow_rule(relative: str, runs: set[str]) -> str | None:
    if forbidden(relative):
        return None
    parts = PurePosixPath(relative).parts
    suffix = PurePosixPath(relative).suffix.lower()
    if relative in ROOT_FILES:
        return "root-files"
    if relative == VENDOR:
        return "verified-official-dependency-tarball"
    if parts[0] in {"server", "service"}:
        if len(parts) == 2 and suffix in SOURCE_EXT:
            return "application-source"
        if len(parts) >= 3 and parts[1] == "tests" and suffix in SOURCE_EXT:
            return "service-tests"
        if parts[0] == "service" and len(parts) == 3 and parts[1] == "runs" and parts[2] in {"parser-concurrency-content.json", "parser-regression-tests.txt"}:
            return "parser-concurrency-regression-evidence"
        if parts[0] == "service" and len(parts) == 4 and parts[1] == "runs" and re.fullmatch(r"parser-concurrency[A-Za-z0-9_-]*", parts[2]):
            if parts[3] == "summary.json" or re.fullmatch(r"worker-\d+\.json", parts[3]) or (parts[2] == "parser-concurrency-fixed-2" and parts[3] == "resource-sample.json"):
                return "parser-concurrency-worker-evidence"
    if parts[0] == "tests" and suffix in SOURCE_EXT:
        return "integration-tests"
    if parts[0] == "web":
        if len(parts) == 2 and suffix in SOURCE_EXT:
            return "web-config"
        if len(parts) >= 3 and parts[1] in {"src", "tests"} and suffix in SOURCE_EXT:
            return "web-source-and-tests"
        if len(parts) >= 3 and parts[1] == "dist" and suffix in {".html", ".js", ".css", ".svg", ".png", ".woff2"}:
            return "built-web-application"
        if len(parts) == 3 and parts[1] == "test-fixtures" and suffix in {".xlsx", ".pdf", ".csv", ".tsv"}:
            return "synthetic-browser-fixtures"
        if len(parts) == 3 and parts[1] == "test-results" and suffix in {".json", ".png"} and "qwen" not in parts[-1].lower():
            return "browser-test-evidence"
    if parts[0] == "design" and suffix in {".html", ".css", ".js", ".cjs", ".json", ".png", ".md"}:
        return "architecture-and-marked-prototype"
    if parts[0] == "scripts":
        if len(parts) == 2 and suffix in SOURCE_EXT:
            return "reproduction-scripts"
        if len(parts) == 3 and parts[1] == "dependency-evidence" and suffix in {".json", ".txt"}:
            return "dependency-security-evidence"
    if parts[0] == "sandbox":
        if len(parts) == 2 and (suffix in SOURCE_EXT or parts[1] in {"Dockerfile", "requirements.lock", ".dockerignore", ".gitignore"}):
            return "sandbox-source-and-locks"
        if len(parts) >= 3 and parts[1] == "evidence" and suffix in EVIDENCE_EXT:
            return "container-security-evidence"
    if parts[0] == "paper":
        if len(parts) == 2 and suffix in SOURCE_EXT | {".docx", ".pdf", ".png"}:
            return "paper-and-reproduction-source"
        if len(parts) == 3 and parts[1] == "render" and suffix in {".json", ".png", ".pdf"}:
            return "paper-render-evidence"
    if parts[0] == "benchmark":
        if len(parts) == 4 and parts[1:3] == ("results", "report-preview") and parts[3] in {"qa.json", "desktop-overview.png", "desktop-model.png", "desktop-runtime.png", "mobile-overview.png", "mobile-model.png"}:
            return "final-acceptance-report-browser-evidence"
        if len(parts) == 4 and parts[1] == "results" and parts[2] in {"demo-artifacts", "demo-latest-artifacts"} and suffix in {".json", ".png"}:
            return "three-report-real-agent-demo-artifacts"
        if len(parts) == 3 and parts[1] == "results" and parts[2] in {"reviewed-scorer-tests.txt", "acceptance-report.html"}:
            return "reviewed-scorer-and-acceptance-report"
        if len(parts) == 2 and suffix in DATA_EXT:
            return "benchmark-definition"
        if len(parts) >= 3 and parts[1] in {"agent_input", "evaluator", "review", "sources", "tests", "scripts"}:
            if suffix in DATA_EXT or parts[-1] == "LICENSE":
                return "benchmark-" + parts[1]
        if len(parts) >= 4 and parts[1:3] == ("versions", "v0.2") and suffix in DATA_EXT:
            return "reviewed-benchmark-v0.2"
        if len(parts) == 3 and parts[1] == "results" and suffix in {".json", ".jsonl"}:
            name = parts[2]
            if name.startswith("agent-") and not any(name.startswith(run + "-") for run in runs):
                return None
            return "benchmark-result-evidence"
        if len(parts) >= 4 and parts[1] == "runs" and parts[2] in runs and run_evidence_allowed(parts):
            return "official-deepseek-run-evidence"
    return None


def candidates(runs: set[str]):
    selected = []
    rejected_links = []
    # Never descend into credentials, application data or large runtime trees.
    for directory, dirs, files in os.walk(ROOT, followlinks=False):
        parent = Path(directory)
        dirs[:] = sorted(d for d in dirs if d.lower() not in BLOCKED_PARTS and d != "deliverables" and not (parent / d).is_symlink())
        for name in sorted(files):
            file = parent / name
            relative = file.relative_to(ROOT).as_posix()
            rule = allow_rule(relative, runs)
            if rule is None:
                continue
            if file.is_symlink() or ROOT not in file.resolve().parents:
                rejected_links.append(relative)
                continue
            selected.append((relative, file, rule))
    if rejected_links:
        raise ValueError("Refusing linked input paths: " + ", ".join(rejected_links))
    return sorted(selected)


def match_count(data: bytes) -> int:
    return sum(sum(1 for _ in pattern.finditer(data)) for pattern in SECRET_PATTERNS)


def reviewed_fixture_count(relative: str, raw: bytes) -> int:
    fixture = REVIEWED_TEST_FIXTURES.get(relative)
    if not fixture or hashlib.sha256(raw).hexdigest() != fixture["file_sha256"]:
        return 0
    matches = list(SECRET_PATTERNS[fixture["pattern_index"]].finditer(raw))
    if len(matches) != 1 or hashlib.sha256(matches[0].group(1)).hexdigest() != fixture["value_sha256"]:
        return 0
    return 1


def scan_contents(relative: str, raw: bytes) -> tuple[int, int]:
    count = match_count(raw) - reviewed_fixture_count(relative, raw)
    members_scanned = 0
    # Office documents are ZIPs; inspect their compressed XML/media as well.
    if PurePosixPath(relative).suffix.lower() in {".docx", ".xlsx"}:
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            for entry in archive.infolist():
                if entry.is_dir():
                    continue
                if entry.file_size > 64 * 1024 * 1024:
                    raise ValueError("Oversized Office archive member: " + relative)
                count += match_count(archive.read(entry))
                members_scanned += 1
    if relative == VENDOR:
        if hashlib.sha512(raw).hexdigest() != VENDOR_SHA512:
            raise ValueError("Official dependency archive SHA512 mismatch: " + relative)
        with tarfile.open(fileobj=io.BytesIO(raw), mode="r:gz") as archive:
            for member in archive:
                if member.isfile():
                    if member.size > 1024 * 1024:
                        raise ValueError("Oversized dependency archive member: " + relative)
                    contents = archive.extractfile(member)
                    assert contents is not None
                    count += match_count(contents.read())
                    members_scanned += 1
    return count, members_scanned


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="Write the scanned manifest only (default).")
    mode.add_argument("--build", action="store_true", help="Create ZIP after all allowlist, integrity and secret checks pass.")
    parser.add_argument("--output", default="deliverables/finance-agent-implementation-v0.2.zip")
    parser.add_argument("--manifest", default="deliverables/delivery-plan.json")
    args = parser.parse_args()
    runs = deepseek_runs()
    selected = candidates(runs)
    manifest_path = (ROOT / args.manifest).resolve()
    output = (ROOT / args.output).resolve()
    delivery_root = (ROOT / "deliverables").resolve()
    if delivery_root not in manifest_path.parents or delivery_root not in output.parents:
        raise ValueError("Manifest and ZIP outputs must remain under deliverables/.")
    if args.build and output.exists():
        raise ValueError("Refusing to overwrite an existing delivery ZIP.")
    partial_output = output.with_name(output.name + ".partial")
    if args.build and partial_output.exists():
        raise ValueError("A prior partial archive exists; review it before another build.")
    rows, findings, archive_members, reviewed_fixtures = [], [], 0, []
    for relative, file, rule in selected:
        raw = file.read_bytes()
        count, members = scan_contents(relative, raw)
        reviewed = reviewed_fixture_count(relative, raw)
        if reviewed:
            reviewed_fixtures.append({"path": relative, "match_count": reviewed, **REVIEWED_TEST_FIXTURES[relative]})
        archive_members += members
        if count:
            findings.append({"path": relative, "match_count": count})
        rows.append({"path": relative, "size": len(raw), "sha256": hashlib.sha256(raw).hexdigest(), "allow_rule": rule})
    manifest = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "mode": "build" if args.build else "dry-run", "archive_created": False,
        "purpose": "Private local research handoff; public redistribution of report PDFs requires separate review.",
        "file_count": len(rows), "uncompressed_bytes": sum(r["size"] for r in rows),
        "eligible_official_model_runs": sorted(runs),
        "excluded_directory_names": sorted(BLOCKED_PARTS | {"deliverables"}),
        "secret_scan": {"files_scanned": len(rows), "compressed_members_scanned": archive_members, "findings": findings, "match_count": sum(f["match_count"] for f in findings), "reviewed_synthetic_fixtures": reviewed_fixtures, "reviewed_fixture_match_count": sum(item["match_count"] for item in reviewed_fixtures), "limitations": "Pattern detection is not proof against arbitrary secrets or secrets embedded in raster images. No matched values are logged. The sole reviewed synthetic test-fixture exception is bound to its exact path, whole-file hash, and value hash; any change invalidates it."},
        "files": rows,
    }
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if findings:
        print(json.dumps({"secret_scan_failed": findings}, ensure_ascii=True))
        return 2
    if args.build:
        # Verify that concurrent work did not change an input between scan and write.
        with zipfile.ZipFile(partial_output, "x", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
            for row, (_, file, _) in zip(rows, selected):
                raw = file.read_bytes()
                if hashlib.sha256(raw).hexdigest() != row["sha256"]:
                    raise ValueError("Input changed after scan: " + row["path"])
                archive.writestr(row["path"], raw)
            archive.writestr("DELIVERY_MANIFEST.json", json.dumps(manifest, ensure_ascii=False, indent=2))
        partial_output.rename(output)
        manifest["archive_created"] = True
        manifest["archive"] = {"path": output.relative_to(ROOT).as_posix(), "size": output.stat().st_size, "sha256": hashlib.sha256(output.read_bytes()).hexdigest()}
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"mode": manifest["mode"], "file_count": len(rows), "uncompressed_bytes": manifest["uncompressed_bytes"], "secret_match_count": 0, "reviewed_fixture_match_count": manifest["secret_scan"]["reviewed_fixture_match_count"], "manifest": manifest_path.relative_to(ROOT).as_posix(), "archive_created": manifest["archive_created"]}, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, zipfile.BadZipFile, tarfile.TarError) as exc:
        print(type(exc).__name__ + ": " + str(exc), file=sys.stderr)
        raise SystemExit(1)
