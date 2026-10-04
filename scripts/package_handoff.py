"""Build a source-only v0.8 candidate handoff; default is a scanned dry run.

Extends the historical delivery allowlist without changing package_delivery.py.
No application runtime data is exported. Archive scanning reads bytes only and
never prints credential matches. Dependencies and containers must be rebuilt.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import sys
from datetime import datetime, timezone
import zipfile


spec = importlib.util.spec_from_file_location("historical_package_delivery", Path(__file__).with_name("package_delivery.py"))
legacy = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(legacy)
ROOT = Path(__file__).resolve().parents[1]
EXTRA_ROOT = {"HANDOFF.md", "HANDOFF.html", "goal_requirements.json"}
REQUIRED = EXTRA_ROOT | {"README.txt", "WORK_STATUS.md", "package.json", "package-lock.json", "requirements.lock.txt", "service/tool-schema.json", "benchmark/design.html", "benchmark/results/upgrade-progress-v06.html", "sandbox/Dockerfile", "sandbox/requirements.lock", "sandbox/wheels.lock.json", legacy.VENDOR}
EXTRA_BLOCKED = {"tmp", "dist", "build", "coverage", ".pytest_cache", ".mypy_cache", ".ruff_cache", "deliverables"}
BLOCKED_PARTS = legacy.BLOCKED_PARTS | EXTRA_BLOCKED
SOURCE_EXT = legacy.SOURCE_EXT | {".yaml", ".yml", ".toml", ".sql", ".sh", ".svg"}
BENCHMARK_EXT = legacy.DATA_EXT | SOURCE_EXT | {".xlsx", ".xls", ".zip", ".log"}
EVIDENCE_EXT = legacy.EVIDENCE_EXT | {".html", ".pdf", ".svg"}
ARCHIVE_EXT = {".zip", ".docx", ".xlsx", ".xlsm"}
TAVILY = re.compile(rb"\btvly-(?:dev-|prod-)?[A-Za-z0-9_-]{16,}\b")
MAX_ARCHIVE_DEPTH = 8
MAX_MEMBER_BYTES = 128 * 1024 * 1024
MAX_EXPANDED_BYTES = 2 * 1024 * 1024 * 1024
REVIEWED_HANDOFF_FIXTURES = {
    "scripts/verify_utf8_roundtrip.mjs": {
        "file_sha256": "9581abe32108f353c48859df586db4327b6851cfb6cd0acf06f69fc088b08c0f",
        "value_sha256": "c3652a068e6a4508abee8cfd6ae8cb76520cda1eca17e3d83aa43041b59099d2",
        "pattern_index": 5,
        "reason": "Reviewed deterministic UTF-8 persistence fixture: an isolated temporary DATA host calls only its own HTTP provider bound to 127.0.0.1. This fixed synthetic authorization value is not an official provider key. Exact path, file hash and value hash are required.",
    },
}


class HandoffError(ValueError):
    """Messages contain a path and a public reason, never payload content."""


def checked_relative(name: str) -> str:
    normalized = name.replace("\\", "/")
    parts = PurePosixPath(normalized).parts
    if not parts or normalized.startswith("/") or re.match(r"^[A-Za-z]:", normalized) or any(p in {"..", "."} for p in normalized.split("/")):
        raise HandoffError("unsafe_archive_path: " + name)
    return normalized.rstrip("/")


def blocked(name: str) -> bool:
    parts = PurePosixPath(name).parts
    if not parts:
        return True
    lower = tuple(p.lower() for p in parts)
    # Templates may be nested in a packaged benchmark; content still gets scanned.
    credential_name = lower[-1] in legacy.BLOCKED_NAMES or (lower[-1].startswith(".env") and lower[-1] != ".env.example")
    return any(p in BLOCKED_PARTS for p in lower) or credential_name or PurePosixPath(lower[-1]).suffix in legacy.BLOCKED_EXT or lower[-1].endswith(".pub")


def application_downloads(root: Path) -> set[str]:
    source = (root / "server/workspace-api.ts").read_text(encoding="utf-8-sig")
    start = source.find("const downloads:")
    end = source.find("app.get('/api/benchmark/catalog'", start)
    if start < 0 or end < 0:
        raise HandoffError("download_route_not_found: server/workspace-api.ts")
    downloads = set(re.findall(r"\bfile\s*:\s*['\"](samples/[^'\"]+\.zip)['\"]", source[start:end]))
    if not downloads:
        raise HandoffError("download_route_empty: server/workspace-api.ts")
    for name in downloads:
        checked_relative(name)
        if blocked(name):
            raise HandoffError("forbidden_download_path: " + name)
    return downloads


def allow_rule(name: str, runs: set[str], downloads: set[str]) -> str | None:
    checked_relative(name)
    if blocked(name):
        return None
    parts = PurePosixPath(name).parts
    suffix = PurePosixPath(name).suffix.lower()
    if name in EXTRA_ROOT:
        return "handoff-contract-and-requirements"
    if name in downloads:
        return "application-advertised-sample-download"
    if len(parts) >= 3 and parts[:2] == ("samples", "native-pdf") and suffix in legacy.DATA_EXT | {".log"}:
        return "native-text-pdf-samples-and-inspection"
    if parts[0] in {"server", "service"} and len(parts) >= 2 and (len(parts) == 2 or parts[1] != "runs") and suffix in SOURCE_EXT:
        return "application-source-recursive"
    if parts[0] == "scripts" and len(parts) >= 2 and suffix in SOURCE_EXT:
        return "reproduction-scripts-and-tests-recursive"
    if parts[0] == "benchmark":
        if len(parts) == 2 and suffix in BENCHMARK_EXT:
            return "benchmark-definition-and-design"
        if len(parts) >= 3 and parts[1] == "versions" and suffix in BENCHMARK_EXT:
            return "frozen-benchmark-versions"
        if len(parts) >= 3 and parts[1] == "results" and suffix in EVIDENCE_EXT:
            if parts[-1].startswith("agent-") and "qwen" in parts[-1].lower():
                return None
            return "benchmark-result-and-linked-evidence"
    return legacy.allow_rule(name, runs)


def linked(path: Path) -> bool:
    return path.is_symlink() or (hasattr(path, "is_junction") and path.is_junction())


def collect_inputs(root: Path, runs: set[str], downloads: set[str]):
    selected = []
    for directory, dirs, files in os.walk(root, followlinks=False):
        parent = Path(directory)
        dirs[:] = sorted(d for d in dirs if d.lower() not in BLOCKED_PARTS and not linked(parent / d))
        for name in sorted(files):
            file = parent / name
            relative = file.relative_to(root).as_posix()
            rule = allow_rule(relative, runs, downloads)
            if rule is None:
                continue
            if linked(file) or root.resolve() not in file.resolve().parents:
                raise HandoffError("linked_input_refused: " + relative)
            selected.append((relative, file, rule))
    return sorted(selected)


def secret_count(raw: bytes) -> int:
    return legacy.match_count(raw) + len(TAVILY.findall(raw))


def reviewed_fixture_count(relative: str, raw: bytes) -> int:
    count = legacy.reviewed_fixture_count(relative, raw)
    fixture = REVIEWED_HANDOFF_FIXTURES.get(relative)
    if not fixture or hashlib.sha256(raw).hexdigest() != fixture["file_sha256"]:
        return count
    matches = list(legacy.SECRET_PATTERNS[fixture["pattern_index"]].finditer(raw))
    if len(matches) == 1 and hashlib.sha256(matches[0].group(1)).hexdigest() == fixture["value_sha256"]:
        count += 1
    return count


def scan_contents(relative: str, raw: bytes, *, depth=0, budget=None):
    """Recursively inspect ZIP/Office members and credential paths without extraction."""
    budget = budget if budget is not None else {"expanded_bytes": 0, "members": 0}
    if depth > MAX_ARCHIVE_DEPTH:
        raise HandoffError("archive_nesting_limit: " + relative)
    count = secret_count(raw) - (reviewed_fixture_count(relative, raw) if depth == 0 else 0)
    findings = [{"path": relative, "match_count": count}] if count else []
    violations = []
    is_archive = PurePosixPath(relative).suffix.lower() in ARCHIVE_EXT or raw[:4] in {b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08"}
    if is_archive:
        try:
            with zipfile.ZipFile(io.BytesIO(raw)) as archive:
                seen = set()
                for member in archive.infolist():
                    display = relative + "!" + member.filename
                    name = checked_relative(member.filename)
                    if name in seen:
                        raise HandoffError("duplicate_archive_member: " + display)
                    seen.add(name)
                    mode = member.external_attr >> 16
                    if stat.S_ISLNK(mode):
                        raise HandoffError("linked_archive_member: " + display)
                    if blocked(name):
                        violations.append({"path": display, "match_count": 1})
                    if member.is_dir():
                        continue
                    if member.flag_bits & 1:
                        raise HandoffError("encrypted_archive_member: " + display)
                    if member.file_size > MAX_MEMBER_BYTES:
                        raise HandoffError("oversized_archive_member: " + display)
                    budget["expanded_bytes"] += member.file_size
                    budget["members"] += 1
                    if budget["expanded_bytes"] > MAX_EXPANDED_BYTES:
                        raise HandoffError("archive_expansion_limit: " + relative)
                    child = scan_contents(display, archive.read(member), depth=depth + 1, budget=budget)
                    findings.extend(child["findings"])
                    violations.extend(child["forbidden_members"])
        except (zipfile.BadZipFile, RuntimeError, NotImplementedError, EOFError):
            raise HandoffError("unreadable_archive: " + relative) from None
    elif relative == legacy.VENDOR and depth == 0:
        # Preserve the exact reviewed dependency SHA512 and tar member checks.
        legacy_count, members = legacy.scan_contents(relative, raw)
        budget["members"] += members
        extra = legacy_count - legacy.match_count(raw)
        if extra:
            findings.append({"path": relative + "!reviewed_dependency_members", "match_count": extra})
        # Tavily matching is also required in the compressed dependency payload.
        import tarfile
        with tarfile.open(fileobj=io.BytesIO(raw), mode="r:gz") as archive:
            for member in archive:
                if member.isfile():
                    stream = archive.extractfile(member)
                    assert stream is not None
                    hits = len(TAVILY.findall(stream.read()))
                    if hits:
                        findings.append({"path": relative + "!" + member.name, "match_count": hits})
    return {"findings": findings, "forbidden_members": violations, "members_scanned": budget["members"], "expanded_bytes": budget["expanded_bytes"]}


def verify_archive(path: Path, rows: list[dict], manifest_bytes: bytes) -> dict:
    expected = {row["path"]: (row["size"], row["sha256"]) for row in rows}
    expected["DELIVERY_MANIFEST.json"] = (len(manifest_bytes), hashlib.sha256(manifest_bytes).hexdigest())
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        if len(names) != len(set(names)) or set(names) != set(expected):
            raise HandoffError("archive_member_set_mismatch: " + path.name)
        bad = archive.testzip()
        if bad:
            raise HandoffError("archive_crc_mismatch: " + bad)
        for info in archive.infolist():
            size, digest = expected[info.filename]
            if info.file_size != size:
                raise HandoffError("archive_size_mismatch: " + info.filename)
            with archive.open(info) as stream:
                actual = hashlib.file_digest(stream, "sha256").hexdigest()
            if actual != digest:
                raise HandoffError("archive_sha256_mismatch: " + info.filename)
    return {"crc": "passed", "exact_member_set": "passed", "sha256": "passed", "verified_members": len(expected), "source_files": len(rows)}


def output_path(root: Path, value: str) -> Path:
    path = (root / value).resolve()
    delivery = (root / "deliverables").resolve()
    if delivery not in path.parents or root.resolve() not in delivery.parents:
        raise HandoffError("output_must_be_under_deliverables: " + value)
    if path.exists():
        raise HandoffError("existing_output_refused: " + path.relative_to(root).as_posix())
    return path


def build_archive(output: Path, selected, rows, manifest: dict) -> dict:
    if output.exists():
        raise HandoffError("existing_output_refused: " + output.name)
    partial = output.with_name(output.name + ".partial")
    if partial.exists():
        raise HandoffError("existing_partial_refused: " + partial.name)
    embedded = copy.deepcopy(manifest)
    embedded["kind"] = "source_handoff_input_manifest"
    embedded["archive_created"] = True
    embedded["archive_verification_policy"] = "Before publication: CRC, exact entry set and SHA256 of every source file and this manifest. Final archive hash and verification result are in the external manifest."
    manifest_bytes = json.dumps(embedded, ensure_ascii=False, indent=2).encode("utf8")
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(partial, "x", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for row, (relative, file, _) in zip(rows, selected, strict=True):
            raw = file.read_bytes()
            if relative != row["path"] or len(raw) != row["size"] or hashlib.sha256(raw).hexdigest() != row["sha256"]:
                raise HandoffError("source_changed_after_scan: " + relative)
            archive.writestr(relative, raw)
        archive.writestr("DELIVERY_MANIFEST.json", manifest_bytes)
    verified = verify_archive(partial, rows, manifest_bytes)
    # Windows rename refuses an existing target; the explicit check also covers POSIX.
    if output.exists():
        raise HandoffError("existing_output_refused: " + output.name)
    partial.rename(output)
    return verified


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--build", action="store_true")
    parser.add_argument("--output", default="deliverables/finance-agent-handoff-v0.8-candidate.zip")
    parser.add_argument("--manifest", default="deliverables/handoff-v0.8-candidate-plan.json")
    args = parser.parse_args(argv)
    output = output_path(ROOT, args.output)
    manifest_path = output_path(ROOT, args.manifest)
    if output == manifest_path:
        raise HandoffError("output_and_manifest_must_differ: " + args.output)
    downloads = application_downloads(ROOT)
    selected = collect_inputs(ROOT, legacy.deepseek_runs(), downloads)
    present = {name for name, _, _ in selected}
    missing = sorted((REQUIRED | downloads) - present)
    rows, findings, forbidden_members, exemptions = [], [], [], []
    budget = {"expanded_bytes": 0, "members": 0}
    for relative, file, rule in selected:
        raw = file.read_bytes()
        scanned = scan_contents(relative, raw, budget=budget)
        findings.extend(scanned["findings"])
        forbidden_members.extend(scanned["forbidden_members"])
        if reviewed_fixture_count(relative, raw):
            policy = REVIEWED_HANDOFF_FIXTURES.get(relative) or legacy.REVIEWED_TEST_FIXTURES[relative]
            exemptions.append({"path": relative, "match_count": reviewed_fixture_count(relative, raw), **policy})
        rows.append({"path": relative, "size": len(raw), "sha256": hashlib.sha256(raw).hexdigest(), "allow_rule": rule})
    unsafe = bool(findings or forbidden_members)
    manifest = {"schema": "finance-source-handoff-0.8", "kind": "source_handoff_scan", "created_at": datetime.now(timezone.utc).isoformat(),
                "mode": "build" if args.build else "dry-run", "archive_created": False,
                "status": "privacy_scan_failed" if unsafe else "missing_required_inputs" if missing else "scan_passed",
                "purpose": "Private candidate source, benchmark and evidence handoff. No compiled production bundle, credentials, live project database, runtime session, VM or dependency cache. Reinstall dependencies and build before starting.",
                "missing_required_inputs": missing, "application_downloads": sorted(downloads),
                "file_count": len(rows), "uncompressed_bytes": sum(row["size"] for row in rows),
                "excluded_directory_names": sorted(BLOCKED_PARTS),
                "privacy_scan": {"findings": findings, "match_count": sum(item["match_count"] for item in findings),
                                 "forbidden_archive_members": forbidden_members, "compressed_members_scanned": budget["members"], "expanded_bytes_scanned": budget["expanded_bytes"],
                                 "reviewed_synthetic_fixtures": exemptions,
                                 "limitations": "Pattern scanning detects known key formats including Tavily and recursively inspects ZIP/Office members. It does not prove absence of arbitrary secrets or secrets embedded in images. No matched values are emitted."},
                "reproduction_boundary": "Historical report JSON is reviewable, but original live data/audit/research state is intentionally absent. Frozen benchmark input and scorer packages are included; historical runtime replay scripts may require original local inputs.",
                "files": rows}
    if args.build and not unsafe and not missing:
        manifest["archive_verification"] = build_archive(output, selected, rows, manifest)
        manifest["archive_created"] = True
        manifest["status"] = "built_and_verified_source_candidate"
        manifest["archive"] = {"path": output.relative_to(ROOT).as_posix(), "size": output.stat().st_size,
                               "sha256": hashlib.sha256(output.read_bytes()).hexdigest()}
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    with manifest_path.open("x", encoding="utf8") as stream:
        json.dump(manifest, stream, ensure_ascii=False, indent=2)
    # The console report contains paths/counts only; payloads and key values never appear.
    print(json.dumps({"manifest": manifest_path.relative_to(ROOT).as_posix(),
                      "archive": output.relative_to(ROOT).as_posix() if manifest["archive_created"] else None,
                      "file_count": len(rows), "secret_findings": findings, "forbidden_archive_members": forbidden_members,
                      "missing_required_inputs": [{"path": name, "match_count": 1} for name in missing]}, ensure_ascii=True))
    return 2 if unsafe or (args.build and missing) else 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, zipfile.BadZipFile) as exc:
        # Library errors can contain arbitrary payload fragments; only our path-only
        # diagnostics are safe to expose directly.
        message = str(exc) if isinstance(exc, HandoffError) else type(exc).__name__
        print(message, file=sys.stderr)
        raise SystemExit(1)
