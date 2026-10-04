"""Private-data exclusion and exact archive-integrity tests; synthetic bytes only."""
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import stat
import struct
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch
import zipfile

spec = importlib.util.spec_from_file_location("package_handoff", Path(__file__).with_name("package_handoff.py"))
package = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(package)


def archive_bytes(items):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, value in items:
            archive.writestr(name, value)
    return buffer.getvalue()


class HandoffBoundaries(unittest.TestCase):
    def test_required_sources_samples_and_evidence_allowed_without_compiled_or_runtime_data(self):
        downloads = {"samples/evaluation.zip"}
        for name in ["HANDOFF.md", "HANDOFF.html", "goal_requirements.json", "service/staged_temporal/model.py",
                     "scripts/tests/test_repeatability.py", "benchmark/design.html", "benchmark/results/progress.html",
                     "benchmark/results/tests.log", "benchmark/results/sub/check.json", "benchmark/versions/v0.5-holdout/gold.json",
                     "benchmark/versions/v0.5-holdout/inputs/report.pdf", "samples/native-pdf/report.pdf",
                     "samples/native-pdf/inspection/report.txt", "samples/evaluation.zip", package.legacy.VENDOR]:
            with self.subTest(name=name):self.assertIsNotNone(package.allow_rule(name, set(), downloads))
        for name in ["data/finance.sqlite", "data/audit/run.jsonl", "server/dist/main.js", "web/dist/index.html",
                     "samples/archive/old.zip", "samples/unadvertised.zip", "tmp/output.json", ".env", ".env.production",
                     "service/nested/settings.json", "scripts/tests/private_keys/token.txt", "sandbox/runtime/remote.json",
                     "sandbox/wheelhouse/library.whl", "scripts/.dependency-verification/cache.json", "node_modules/a/index.js",
                     ".venv/pyvenv.cfg", "web/src/credentials/settings.enc"]:
            with self.subTest(name=name):self.assertIsNone(package.allow_rule(name, set(), downloads))

    def test_current_download_map_is_read_without_adding_unadvertised_archives(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp);(root / "server").mkdir()
            (root / "server/workspace-api.ts").write_text("const downloads:Record<string,any>={a:{file:'samples/a.zip'},b:{file:\"samples/中文.zip\"}}; app.get('/api/benchmark/catalog',route); const ignored='samples/unadvertised.zip';", encoding="utf8")
            self.assertEqual(package.application_downloads(root), {"samples/a.zip", "samples/中文.zip"})

    def test_nested_zip_office_and_disguised_zip_tavily_detection_never_outputs_value(self):
        value = ("tvly-" + "dev-" + "X" * 32).encode()
        deep = archive_bytes([("word/document.xml", value)])
        hidden = archive_bytes([("payload.bin", deep)])
        outer = archive_bytes([("nested.zip", hidden)])
        result = package.scan_contents("samples/example.zip", outer)
        self.assertEqual(result["members_scanned"], 3)
        self.assertEqual(sum(x["match_count"] for x in result["findings"]), 1)
        self.assertEqual(result["findings"][0]["path"], "samples/example.zip!nested.zip!payload.bin!word/document.xml")
        self.assertNotIn(value.decode(), json.dumps(result))
        self.assertGreater(package.scan_contents("notes.txt", ("sk-" + "Y" * 32).encode())["findings"][0]["match_count"], 0)

    def test_forbidden_member_paths_are_rejected_even_if_no_secret_text_matches(self):
        inner = archive_bytes([("data/settings.json", b"{}"), ("runtime/key.txt", b"empty"), (".env", b"empty")])
        result = package.scan_contents("samples/example.zip", archive_bytes([("nested.zip", inner)]))
        self.assertFalse(result["findings"])
        self.assertEqual(len(result["forbidden_members"]), 3)
        self.assertTrue(all(x["match_count"] == 1 for x in result["forbidden_members"]))

    def test_traversal_duplicates_links_and_expansion_limit_are_rejected(self):
        for name in ["../secret.txt", "/absolute.txt", "C:/private.txt", "a/../b.txt"]:
            with self.subTest(name=name),self.assertRaises(package.HandoffError):
                package.scan_contents("sample.zip", archive_bytes([(name, b"text")]))
        with self.assertWarns(UserWarning):duplicate = archive_bytes([("same.txt", b"a"), ("same.txt", b"b")])
        with self.assertRaisesRegex(package.HandoffError, "duplicate_archive_member"):
            package.scan_contents("sample.zip", duplicate)
        info = zipfile.ZipInfo("linked.txt");info.create_system = 3;info.external_attr = (stat.S_IFLNK | 0o777) << 16
        with self.assertRaisesRegex(package.HandoffError, "linked_archive_member"):
            package.scan_contents("sample.zip", archive_bytes([(info, b"target")]))
        with patch.object(package, "MAX_MEMBER_BYTES", 8),self.assertRaisesRegex(package.HandoffError, "oversized_archive_member"):
            package.scan_contents("sample.zip", archive_bytes([("large.txt", b"012345678")]))

    def test_archive_depth_limit_and_reviewed_legacy_fixture_stay_bounded(self):
        data = archive_bytes([("notes.txt", b"text")])
        for _ in range(10):data = archive_bytes([("nested.zip", data)])
        with self.assertRaisesRegex(package.HandoffError, "archive_nesting_limit"):
            package.scan_contents("sample.zip", data)
        name = "service/tests/test_ocr_runtime.py";raw = (package.ROOT / name).read_bytes()
        self.assertFalse(package.scan_contents(name, raw)["findings"])
        self.assertTrue(package.scan_contents(name, raw + b"\n")["findings"])

    def test_local_utf8_fixture_exception_is_exact_and_does_not_change_legacy_scan(self):
        name = "scripts/verify_utf8_roundtrip.mjs";raw = (package.ROOT / name).read_bytes()
        self.assertEqual(package.legacy.scan_contents(name, raw)[0], 1)
        self.assertEqual(package.reviewed_fixture_count(name, raw), 1)
        self.assertFalse(package.scan_contents(name, raw)["findings"])
        for relative, data in [("scripts/other.mjs", raw), (name, raw + b"\n"), (name, raw + ("sk-" + "Z" * 32).encode())]:
            with self.subTest(relative=relative):self.assertTrue(package.scan_contents(relative, data)["findings"])

    def test_source_handoff_is_crc_and_sha256_verified_and_never_overwritten(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp);source = root / "example.py";source.write_bytes(b"print('synthetic')\n")
            raw = source.read_bytes();rows = [{"path":"service/example.py","size":len(raw),"sha256":hashlib.sha256(raw).hexdigest()}]
            selected = [("service/example.py", source, "application-source")]
            output = root / "handoff.zip"
            result = package.build_archive(output, selected, rows, {"files":rows,"archive_created":False})
            self.assertEqual(result, {"crc":"passed","exact_member_set":"passed","sha256":"passed","verified_members":2,"source_files":1})
            original = output.read_bytes()
            with self.assertRaisesRegex(package.HandoffError, "existing_output_refused"):
                package.build_archive(output, selected, rows, {})
            self.assertEqual(original, output.read_bytes())
            with zipfile.ZipFile(output) as archive:manifest = archive.read("DELIVERY_MANIFEST.json")
            changed = root / "changed.zip"
            changed.write_bytes(archive_bytes([("service/example.py", b"x" * len(raw)), ("DELIVERY_MANIFEST.json", manifest)]))
            with self.assertRaisesRegex(package.HandoffError, "archive_sha256_mismatch"):
                package.verify_archive(changed, rows, manifest)
            changed.write_bytes(archive_bytes([("service/example.py", raw), ("DELIVERY_MANIFEST.json", manifest), ("extra.txt", b"x")]))
            with self.assertRaisesRegex(package.HandoffError, "archive_member_set_mismatch"):
                package.verify_archive(changed, rows, manifest)

    def test_changed_source_and_output_escape_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp);source = root / "example.py";source.write_bytes(b"changed")
            rows = [{"path":"service/example.py","size":3,"sha256":hashlib.sha256(b"old").hexdigest()}]
            with self.assertRaisesRegex(package.HandoffError, "source_changed_after_scan"):
                package.build_archive(root / "handoff.zip", [("service/example.py", source, "source")], rows, {})
            with self.assertRaisesRegex(package.HandoffError, "output_must_be_under_deliverables"):
                package.output_path(root, "../outside.zip")
            (root / "deliverables").mkdir();existing = root / "deliverables/manifest.json";existing.write_text("{}")
            with self.assertRaisesRegex(package.HandoffError, "existing_output_refused"):
                package.output_path(root, "deliverables/manifest.json")

    def test_crc_corruption_is_rejected_before_a_successful_integrity_claim(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "corrupted.zip";payload = b"exact-content";manifest = b"{}"
            with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_STORED) as archive:
                archive.writestr("file.txt", payload);archive.writestr("DELIVERY_MANIFEST.json", manifest)
            with zipfile.ZipFile(target) as archive:header = archive.getinfo("file.txt").header_offset
            raw = bytearray(target.read_bytes());name_length, extra_length = struct.unpack_from("<HH", raw, header + 26)
            raw[header + 30 + name_length + extra_length] ^= 1;target.write_bytes(raw)
            rows = [{"path":"file.txt","size":len(payload),"sha256":hashlib.sha256(payload).hexdigest()}]
            with self.assertRaisesRegex(package.HandoffError, "archive_crc_mismatch"):
                package.verify_archive(target, rows, manifest)

    def test_dry_run_creates_only_new_manifest_and_missing_docs_block_build(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp);(root / "server").mkdir();(root / "samples").mkdir()
            (root / "server/workspace-api.ts").write_text("const downloads:Record<string,any>={a:{file:'samples/a.zip'}}; app.get('/api/benchmark/catalog',route);", encoding="utf8")
            (root / "samples/a.zip").write_bytes(archive_bytes([("input.txt", b"public synthetic input")]))
            with patch.object(package, "ROOT", root),patch.object(package, "REQUIRED", {"HANDOFF.md","HANDOFF.html"}),patch.object(package.legacy, "deepseek_runs", return_value=set()),redirect_stdout(io.StringIO()):
                self.assertEqual(package.main(["--manifest","deliverables/dry.json"]), 0)
                self.assertFalse(list((root / "deliverables").glob("*.zip")))
                dry = json.loads((root / "deliverables/dry.json").read_text())
                self.assertEqual(dry["missing_required_inputs"], ["HANDOFF.html","HANDOFF.md"])
                self.assertFalse(dry["archive_created"])
                self.assertEqual(package.main(["--build","--manifest","deliverables/build.json"]), 2)
                self.assertFalse(list((root / "deliverables").glob("*.zip")))
                with self.assertRaisesRegex(package.HandoffError, "existing_output_refused"):
                    package.main(["--manifest","deliverables/dry.json"])


if __name__ == "__main__":
    unittest.main()
