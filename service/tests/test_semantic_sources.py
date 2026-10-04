"""Literal source units and immutable inference-owner publication regressions."""
import json
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from service.parser import parse_document
from service.semantic import SCHEMA_HASH, materialize, normalize_document, table_batches


def mappings(table, row, metric="assets", columns=None):
    columns = columns or [{"column": 2, "period": "2024-12-31", "start": "", "end": "2024-12-31", "unit": "元", "currency": "CNY"}]
    return [{"class": "table_schema", "text": f"[[T{table}]]", "span": [1, 7], "attributes": {
        "company": "示例公司", "statement": "balance", "scope": "consolidated_CAS", "columns_json": json.dumps(columns)}},
        {"class": "financial_row", "text": f"[[T{table}:R{row}]]", "span": [8, 20], "attributes": {"metric": metric, "label": metric}}]


def sdk_result(extractions):
    return SimpleNamespace(extractions=[SimpleNamespace(extraction_class=ex["class"], extraction_text=ex["text"],
        attributes=ex["attributes"], char_interval=SimpleNamespace(start_pos=ex["span"][0], end_pos=ex["span"][1])) for ex in extractions])


class SemanticSourceTests(unittest.TestCase):
    def test_real_mixed_summary_assets_are_not_rejected_by_prior_roe_percent(self):
        path = Path(__file__).resolve().parents[2] / "benchmark/versions/v0.4.1-holdout/inputs/liugong_2024_holdout.pdf"
        if not path.exists():
            self.skipTest("development PDF unavailable")
        parsed = parse_document(path, path.name, lambda *_: None, lambda: False, {})
        table = next(table for table in parsed["tables"] if table["page"] == 2 and any("总资产（元）" in row for row in table["rows"]))
        row = next(index for index, values in enumerate(table["rows"], 1) if "总资产（元）" in values)
        self.assertTrue(any("%" in str(values[3]) for values in table["rows"][:6]))
        columns = [{"column": column, "period": f"{year}-12-31", "start": "", "end": f"{year}-12-31", "unit": "元", "currency": "CNY"}
                   for column, year in [(4, 2024), (7, 2023), (13, 2022)]]
        batch = [{"table": table, "rows": [row]}]
        facts, issues = materialize(mappings(table["index"], row, columns=columns), batch, "source-doc", "fixture")
        self.assertEqual(issues, [])
        self.assertEqual([fact["value"] for fact in facts], ["47907158015.10", "46578044988.89", "42257986544.26"])
        self.assertEqual([fact["source"]["cell"] for fact in facts], [f"D{row}", f"G{row}", f"M{row}"])
        self.assertTrue(all(fact["source"]["bbox"] == table["cells"][fact["source"]["cell"]]["bbox"] for fact in facts))

    def test_prior_percent_data_and_unknown_header_shape_do_not_override_model(self):
        rows = [["Item", "Amount"], ["Capacity use", "16.7%"], ["Temporary heading", ""], ["Cash", "8765.43"]]
        table = {"index": 0, "page": 1, "rows": rows}
        facts, issues = materialize(mappings(0, 4, "cash_equivalents"), [{"table": table, "rows": [4]}], "doc", "fixture")
        self.assertEqual(issues, [])
        self.assertEqual(facts[0]["value"], "8765.43")

    def test_only_exact_source_percent_sign_rejects_monetary_interpretation(self):
        table = {"index": 0, "page": 1, "rows": [["Margin", "8.13%"]]}
        facts, issues = materialize(mappings(0, 1, "dynamic_amount"), [{"table": table, "rows": [1]}], "doc", "fixture")
        self.assertEqual(facts, [])
        self.assertEqual(issues[0]["reason"], "source_cell_unit_mismatch")
        ex = mappings(0, 1, "margin", [{"column": 2, "period": "2024-FY", "unit": "%", "currency": "percent"}])
        facts, issues = materialize(ex, [{"table": table, "rows": [1]}], "doc", "fixture")
        self.assertEqual(issues, [])
        self.assertEqual(facts[0]["value"], "8.13")

    def parsed(self):
        return {"company": "示例公司", "report_year": 2024, "pages": [{"page": 1, "text": "2024年财报"}],
                "tables": [{"index": 0, "page": 1, "rows": [["Item", "Year end"], ["Assets", "137"]]}]}

    def invoke(self, cache_put, force=False, cache_get=None):
        details = []
        runtime = {"base_url": "http://127.0.0.1:1/pi-test/v1", "api_key": "temporary-test-token", "model": "fixture",
                   "processing_id": "current-owner", "max_tokens": 32768, "force": force}
        with patch("langextract.extract", return_value=sdk_result(mappings(0, 2))) as model:
            facts, report = normalize_document(self.parsed(), "doc", runtime, lambda *_: None, lambda: False,
                cache_get or (lambda key: None), cache_put, lambda batch, facts, issues, detail: details.append(detail))
        return facts, report, details, model

    def test_cache_race_winner_decision_and_owner_are_used_without_erasing_model_usage(self):
        winner = {"extractions": mappings(0, 2, "other_assets"), "extraction_processing_id": "concurrent-winner",
                  "schema_hash": SCHEMA_HASH, "model": "fixture"}
        published = Mock(return_value=winner)
        facts, report, details, model = self.invoke(published)
        self.assertEqual(facts[0]["metric"], "other_assets")
        self.assertEqual(details[0]["extraction_processing_id"], "concurrent-winner")
        self.assertEqual(details[0]["extractions"], winner["extractions"])
        self.assertTrue(details[0]["reused_extraction"])
        self.assertEqual(report["requests"], 1)
        self.assertEqual(model.call_count, 1)
        model_config = model.call_args.kwargs["config"]
        self.assertEqual(model_config.provider, "PiBridgeLanguageModel")
        self.assertEqual(model_config.provider_kwargs["reasoning_effort"], "high")
        self.assertEqual(model_config.provider_kwargs["max_output_tokens"], 32768)

    def test_old_none_cache_callback_retains_current_inference(self):
        facts, report, details, _ = self.invoke(lambda *_: None)
        self.assertEqual(facts[0]["metric"], "assets")
        self.assertEqual(details[0]["extraction_processing_id"], "current-owner")
        self.assertFalse(details[0]["reused_extraction"])
        self.assertEqual(report["requests"], 1)

    def test_invalid_cache_publication_does_not_commit_local_interpretation_under_foreign_owner(self):
        for payload in [{"extractions": mappings(0, 2)}, {"extractions": mappings(0, 2), "extraction_processing_id": "foreign", "schema_hash": "wrong"}]:
            with self.subTest(payload=payload):
                facts, report, details, _ = self.invoke(lambda *_: payload)
                self.assertEqual(facts, [])
                self.assertEqual(details, [])
                self.assertEqual(report["failures"][0]["error"], "semantic_cache_publication_invalid")
                self.assertEqual(report["requests"], 1)

    def test_force_bypasses_reads_and_keeps_returned_fresh_owner(self):
        fresh = {"extractions": mappings(0, 2), "extraction_processing_id": "current-owner", "schema_hash": SCHEMA_HASH, "model": "fixture"}
        read = Mock(side_effect=AssertionError("force must not read cache"))
        facts, report, details, _ = self.invoke(lambda *_: fresh, force=True, cache_get=read)
        read.assert_not_called()
        self.assertEqual(facts[0]["metric"], "assets")
        self.assertEqual(details[0]["extraction_processing_id"], "current-owner")
        self.assertEqual(report["requests"], 1)

    def test_initial_rows_are_context_not_claimed_headers(self):
        text = table_batches(self.parsed())[0][0]["text"]
        self.assertIn("本表起始行（仅上下文，不表示都是表头）", text)
        self.assertNotIn("本表表头：", text)


if __name__ == "__main__":
    unittest.main()
