"""Boundary tests for the delivery allowlist; never read application secrets."""
import importlib.util
import io
from pathlib import Path
import unittest
import zipfile

spec = importlib.util.spec_from_file_location("package_delivery", Path(__file__).with_name("package_delivery.py"))
package = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(package)


class DeliveryBoundaries(unittest.TestCase):
    def setUp(self):
        self.runs = {"agent-official"}

    def test_all_credential_and_runtime_paths_are_excluded(self):
        paths = [
            "data/settings.json", "local-model/manifest.json", "local-model/start.ps1",
            "node_modules/package.json", ".venv/pyvenv.cfg", ".env", ".env.production",
            "sandbox/runtime/manifest.json", "sandbox/downloads/source.json",
            "sandbox/wheelhouse/pandas.whl", "paper/runtime/manifest.json",
            "sandbox/evidence/private/server.pem", "sandbox/evidence/id_ed25519",
            "scripts/.dependency-verification/clean/package-lock.json",
            "benchmark/runs/agent-official/round-1/case/data/result.json",
            "benchmark/runs/agent-official/round-1/case/data/settings.json",
            "benchmark/runs/agent-official/round-1/case/data/audit.jsonl",
            "benchmark/versions/v0.2/settings.json",
            "service/runs/parser-concurrency-fixed-2/data/finance.sqlite",
            "benchmark/results/demo-latest-artifacts/settings.json",
            "benchmark/results/demo-latest-artifacts/data/result.json",
            "benchmark/results/demo-latest-artifacts/nested/result.json",
            "benchmark/results/demo-latest-artifacts/worker.log",
            "benchmark/results/demo-latest-artifacts/raw.pdf",
            "benchmark/results/unreviewed-report.html",
        ]
        for path in paths:
            with self.subTest(path=path):
                self.assertIsNone(package.allow_rule(path, self.runs))

    def test_model_artifacts_have_exact_depth_and_name_limits(self):
        for path in [
            "benchmark/runs/agent-official/manifest.json",
            "benchmark/runs/agent-official/known-code-change.json",
            "benchmark/runs/agent-official/repeatability.json",
            "benchmark/runs/agent-official/round-1/traces.json",
            "benchmark/runs/agent-official/round-3/case_12/result.json",
            "benchmark/runs/agent-official/round-3/case_12/audit.jsonl",
        ]:
            self.assertEqual(package.allow_rule(path, self.runs), "official-deepseek-run-evidence")
        for path in [
            "benchmark/runs/qwen/manifest.json",
            "benchmark/runs/agent-official/round-1/result.json",
            "benchmark/runs/agent-official/round-1/audit.jsonl",
            "benchmark/runs/agent-official/audit.jsonl",
            "benchmark/runs/agent-official/round-1/case/input/case.json",
            "benchmark/runs/agent-official/round-1/case/output/result.json",
            "benchmark/runs/agent-official/round-1/case/output/audit.jsonl",
            "benchmark/runs/agent-official/round-1/case/worker.log",
            "benchmark/results/agent-qwen-summary.json",
        ]:
            self.assertIsNone(package.allow_rule(path, self.runs))

    def test_required_deliverables_remain_allowed(self):
        for path in ["package-lock.json", ".env.example", package.VENDOR,
                     "web/dist/assets/index.js", "benchmark/review/curation-acceptance-b.json",
                     "benchmark/results/demo.json", "benchmark/results/demo-artifacts/chart_data.json",
                     "benchmark/results/demo-artifacts/revenue_2023_2024.png", "benchmark/results/demo-artifacts/verification.json",
                     "benchmark/results/demo-latest.json", "benchmark/results/demo-latest-artifacts/chart_data.json",
                     "benchmark/results/demo-latest-artifacts/chart.png", "benchmark/results/demo-artifacts/font_check.json",
                     "benchmark/results/acceptance-report.html", "benchmark/results/reviewed-scorer-tests.txt",
                     "benchmark/results/report-preview/qa.json", "benchmark/results/report-preview/desktop-model.png",
                     "sandbox/.dockerignore", "sandbox/.gitignore",
                     "service/runs/parser-concurrency-fixed-2/summary.json", "service/runs/parser-concurrency-fixed-2/worker-3.json",
                     "service/runs/parser-concurrency-fixed-2/resource-sample.json", "service/runs/parser-concurrency-content.json",
                     "service/runs/parser-regression-tests.txt",
                     "benchmark/versions/v0.2/gold.jsonl", "sandbox/evidence/runtime.json",
                     "paper/financial_analysis_paper_v0.2.docx"]:
            self.assertIsNotNone(package.allow_rule(path, self.runs))

    def test_secret_detector_does_not_emit_values_and_scans_office_contents(self):
        synthetic = ("sk-" + "Z" * 32).encode()
        self.assertGreater(package.match_count(synthetic), 0)
        memory = io.BytesIO()
        with zipfile.ZipFile(memory, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("word/document.xml", synthetic)
        count, members = package.scan_contents("paper/test.docx", memory.getvalue())
        self.assertGreater(count, 0)
        self.assertEqual(members, 1)

    def test_reviewed_synthetic_fixture_requires_exact_path_file_and_value(self):
        relative = "service/tests/test_ocr_runtime.py"
        raw = (package.ROOT / relative).read_bytes()
        self.assertEqual(package.match_count(raw), 1)
        self.assertEqual(package.reviewed_fixture_count(relative, raw), 1)
        self.assertEqual(package.scan_contents(relative, raw)[0], 0)
        self.assertEqual(package.reviewed_fixture_count("service/tests/other.py", raw), 0)
        self.assertEqual(package.scan_contents(relative, raw + b"\n")[0], 1)
        self.assertEqual(package.scan_contents(relative, raw + ("\nsk-" + "X" * 32).encode())[0], 2)


if __name__ == "__main__":
    unittest.main()
