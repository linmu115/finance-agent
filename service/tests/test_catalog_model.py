"""Catalog decisions use fixture model responses, never a live provider."""
import copy
import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import SimpleNamespace
from unittest.mock import patch

from service.catalog_model import (
    PROMPT_HASH, PROMPT_VERSION, _call_model, _catalog_text,
    catalog_fingerprint, review_catalog, validate_review,
    align_extractions,
)


def profile(metric, label="应收账款", units=None, **extra):
    return {"metric": metric, "labels": [label], "statements": ["balance"],
            "units": units or ["CNY"], "dimension_keys": [],
            "examples": [{"row_label": label, "context": ["资产负债表", label]}], **extra}


def aligned(profiles, kind, marker, attrs):
    content = _catalog_text(profiles)
    start = content.find(marker)
    return {"class": kind, "text": marker, "attributes": attrs,
            "span": [start, start + len(marker)] if start >= 0 else [0, len(marker)]}


def summary(profiles, merge_count=0, **overrides):
    attrs = {"reviewed_count": len(profiles), "merge_count": merge_count,
             "keep_count": len(profiles) - merge_count, "keep_summary": "保留不同财务概念"}
    attrs.update(overrides)
    return aligned(profiles, "catalog_review", "[[CATALOG]]", attrs)


def alias(profiles, source, target, label="应收账款", reason="原表均为销售产生的应收账款余额"):
    return aligned(profiles, "metric_alias", f"[[METRIC:{source}]]",
                   {"canonical_metric": target, "canonical_label": label, "reason": reason})


def model_result(extractions):
    return SimpleNamespace(extractions=[SimpleNamespace(
        extraction_class=ex["class"], extraction_text=ex["text"], attributes=ex["attributes"],
        char_interval=SimpleNamespace(start_pos=ex["span"][0], end_pos=ex["span"][1]) if ex["span"] else None,
    ) for ex in extractions])


class CatalogModelTests(unittest.TestCase):
    def setUp(self):
        self.profiles = [profile("accounts_receivable"), profile("trade_receivables"),
                         profile("other_receivables", "其他应收款")]
        self.runtime = {"base_url": "http://127.0.0.1:34567/pi-run/v1", "api_key": "ephemeral-test-token",
                        "model": "deepseek-flash", "max_tokens": 16000}

    def errors(self, extracted, profiles=None):
        _, errors = validate_review(extracted, profiles or self.profiles)
        return {item["reason"] for item in errors}

    def test_model_alias_and_implicit_keeps_preserve_evidence(self):
        ex = [summary(self.profiles, 1), alias(self.profiles, "trade_receivables", "accounts_receivable")]
        review, errors = validate_review(ex, self.profiles)
        self.assertEqual(errors, [])
        self.assertEqual(review["keep"], ["accounts_receivable", "other_receivables"])
        decision = review["aliases"]["trade_receivables"]
        self.assertEqual(decision["canonical_metric"], "accounts_receivable")
        self.assertEqual(_catalog_text(self.profiles)[slice(*decision["span"])], decision["extraction_text"])
        self.assertIn("原表", decision["reason"])

    def test_same_label_does_not_trigger_programmatic_merge(self):
        profiles = [profile("interest_income", "利息收入"),
                    profile("finance_cost_interest_income", "利息收入")]
        review, errors = validate_review([summary(profiles)], profiles)
        self.assertEqual(errors, [])
        self.assertEqual(review["aliases"], {})
        self.assertEqual(set(review["keep"]), {p["metric"] for p in profiles})

    def test_known_revenue_and_profit_boundaries_are_bidirectional(self):
        for left, right in (("revenue", "total_revenue"), ("revenue", "segment_revenue"),
                            ("net_profit", "parent_net_profit"),
                            ("net_profit", "net_profit_parent"),
                            ("net_profit_parent", "net_profit_excluding_nonrecurring"),
                            ("parent_net_profit", "net_profit_excluding_nonrecurring")):
            for source, target in ((left, right), (right, left)):
                with self.subTest(source=source, target=target):
                    profiles = [profile(source), profile(target)]
                    reasons = self.errors([summary(profiles, 1), alias(profiles, source, target)], profiles)
                    self.assertTrue({"protected_concept_boundary", "public_metric_id_must_be_kept"} & reasons)

    def test_public_metric_id_cannot_be_an_alias_source(self):
        profiles = [profile("assets", "总资产"), profile("total_assets", "总资产")]
        self.assertIn("public_metric_id_must_be_kept", self.errors(
            [summary(profiles, 1), alias(profiles, "assets", "total_assets", label="总资产")], profiles))

    def test_dynamic_metric_can_map_to_existing_public_id_by_model_decision(self):
        profiles = [profile("assets", "总资产"), profile("total_assets", "总资产")]
        review, errors = validate_review(
            [summary(profiles, 1), alias(profiles, "total_assets", "assets", label="总资产", reason="两者原表均为资产负债表的资产总计")], profiles)
        self.assertEqual(errors, [])
        self.assertEqual(review["aliases"]["total_assets"]["canonical_metric"], "assets")
        self.assertEqual(review["keep"], ["assets"])

    def test_quantity_unit_families_cannot_merge(self):
        for source_unit, target_unit in (("CNY", "percent"), ("CNY", "CNY/share"), ("%", "USD/share")):
            with self.subTest(source=source_unit, target=target_unit):
                profiles = [profile("a", units=[source_unit]), profile("b", units=[target_unit])]
                self.assertIn("incompatible_quantity_units", self.errors([summary(profiles, 1), alias(profiles, "a", "b")], profiles))

    def test_currencies_do_not_prevent_same_concept_reconciliation(self):
        profiles = [profile("a", units=["CNY"]), profile("b", units=["USD"])]
        _, errors = validate_review([summary(profiles, 1), alias(profiles, "a", "b")], profiles)
        self.assertEqual(errors, [])

    def test_per_share_denominator_is_preserved_during_reconciliation(self):
        profiles = [profile("per_ten_share_dividend", units=["CNY/10shares"]),
                    profile("dividend_per_share", units=["CNY/share"])]
        for source, target in (("per_ten_share_dividend", "dividend_per_share"),
                               ("dividend_per_share", "per_ten_share_dividend")):
            with self.subTest(source=source):
                self.assertIn("incompatible_quantity_units", self.errors(
                    [summary(profiles, 1), alias(profiles, source, target)], profiles))

    def test_same_share_denominator_allows_different_currencies(self):
        for source_unit, target_unit in (("CNY/share", "USD/1shares"), ("CNY/10shares", "USD/10.0shares")):
            with self.subTest(units=(source_unit, target_unit)):
                profiles = [profile("a", units=[source_unit]), profile("b", units=[target_unit])]
                _, errors = validate_review([summary(profiles, 1), alias(profiles, "a", "b")], profiles)
                self.assertEqual(errors, [])

    def test_missing_or_truncated_summary_never_passes(self):
        self.assertIn("one_catalog_summary_required", self.errors([]))
        self.assertIn("catalog_count_mismatch", self.errors([summary(self.profiles, 1)]))
        self.assertIn("catalog_count_mismatch", self.errors([summary(self.profiles, reviewed_count=2)]))
        self.assertIn("catalog_count_mismatch", self.errors([summary(self.profiles, keep_count=True)]))
        self.assertIn("one_catalog_summary_required", self.errors([summary(self.profiles), summary(self.profiles)]))

    def test_unaligned_and_wrong_span_extractions_are_rejected(self):
        for span in (None, [0, 1], [-1, 9], [0, 99999], [True, 11]):
            with self.subTest(span=span):
                ex = summary(self.profiles)
                ex["span"] = span
                self.assertIn("ungrounded_extraction", self.errors([ex]))

    def test_unique_markers_realign_unordered_sdk_spans_without_changing_model_decisions(self):
        profiles = [profile("a_receivable"), profile("b_receivable"), profile("c_receivable")]
        extracted = [summary(profiles, 2), alias(profiles, "c_receivable", "a_receivable"),
                     alias(profiles, "b_receivable", "a_receivable")]
        extracted[-1]["span"] = None
        before = copy.deepcopy(extracted)
        corrected = align_extractions(extracted, profiles)
        review, errors = validate_review(corrected, profiles)
        self.assertEqual(errors, [])
        self.assertEqual(set(review["aliases"]), {"b_receivable", "c_receivable"})
        self.assertEqual(extracted, before)
        self.assertIsNone(corrected[-1]["sdk_span"])
        for prior, after in zip(extracted, corrected):
            self.assertEqual((prior["class"], prior["text"], prior["attributes"]),
                             (after["class"], after["text"], after["attributes"]))

    def test_absent_or_ambiguous_literal_marker_cannot_be_realigned(self):
        profiles = copy.deepcopy(self.profiles)
        profiles[0]["examples"].append({"context": "原文重复标记 [[METRIC:trade_receivables]]"})
        extracted = [summary(profiles, 1), alias(profiles, "trade_receivables", "accounts_receivable")]
        corrected = align_extractions(extracted, profiles)
        self.assertIsNone(corrected[1]["span"])
        self.assertEqual(corrected[1]["alignment"]["literal_occurrences"], 2)
        self.assertTrue(validate_review(corrected, profiles)[1])
        unknown = {"class": "metric_alias", "text": "[[METRIC:absent]]", "attributes": {}, "span": [0, 5]}
        self.assertIsNone(align_extractions([unknown], profiles)[0]["span"])

    def test_unknown_target_cannot_create_metric(self):
        ex = [summary(self.profiles, 1), alias(self.profiles, "trade_receivables", "invented_metric")]
        self.assertIn("unknown_metric_id", self.errors(ex))

    def test_chains_cycles_duplicate_and_self_alias_are_rejected(self):
        a, b, c = (p["metric"] for p in self.profiles)
        for mappings, reason in (([(a, b), (b, c)], "target_must_be_kept"),
                                 ([(a, b), (b, a)], "target_must_be_kept"),
                                 ([(a, c), (a, c)], "duplicate_mapping"),
                                 ([(a, a)], "self_alias_use_keep")):
            with self.subTest(mappings=mappings):
                ex = [summary(self.profiles, len(mappings))] + [alias(self.profiles, x, y) for x, y in mappings]
                self.assertIn(reason, self.errors(ex))

    def test_aliases_targeting_same_id_need_consistent_label(self):
        profiles = self.profiles + [profile("receivables_trade")]
        ex = [summary(profiles, 2), alias(profiles, "trade_receivables", "accounts_receivable"),
              alias(profiles, "receivables_trade", "accounts_receivable", label="其他名称")]
        self.assertIn("conflicting_canonical_labels", self.errors(ex, profiles))

    def test_missing_reason_cannot_be_stored_as_semantic_evidence(self):
        ex = [summary(self.profiles, 1), alias(self.profiles, "trade_receivables", "accounts_receivable", reason=" ")]
        self.assertIn("missing_semantic_evidence", self.errors(ex))

    def test_legacy_explicit_keep_format_requires_full_coverage(self):
        ex = aligned(self.profiles, "catalog_review", "[[CATALOG]]",
                     {"keep_ids_json": json.dumps([p["metric"] for p in self.profiles])})
        self.assertEqual(self.errors([ex]), set())
        ex["attributes"]["keep_ids_json"] = '["accounts_receivable"]'
        self.assertIn("incomplete_explicit_coverage", self.errors([ex]))

    def test_directory_input_rejects_ambiguous_identity(self):
        for profiles in ([profile("a"), profile("a")], [profile("invalid-ID")]):
            with self.subTest(profiles=profiles), self.assertRaises(ValueError):
                validate_review([], profiles)

    def test_long_metric_ids_up_to_256_characters_remain_grounded(self):
        for size in (102, 128, 256):
            with self.subTest(size=size):
                long_id = "a" * size
                profiles = [profile(long_id), profile("trade_receivables")]
                review, errors = validate_review([summary(profiles, 1), alias(profiles, long_id, "trade_receivables")], profiles)
                self.assertEqual(errors, [])
                self.assertEqual(review["aliases"][long_id]["canonical_metric"], "trade_receivables")
        with self.assertRaisesRegex(ValueError, "catalog_invalid_metric_id"):
            validate_review([], [profile("a" * 257)])

    def test_cache_fingerprint_tracks_semantics_model_and_prompt_without_credentials(self):
        first = catalog_fingerprint(self.profiles, "deepseek-flash")
        self.assertEqual(first, catalog_fingerprint(list(reversed(self.profiles)), "deepseek-flash"))
        changed = copy.deepcopy(self.profiles)
        changed[0]["examples"][0]["context"] = ["财务费用下的利息收入"]
        self.assertNotEqual(first, catalog_fingerprint(changed, "deepseek-flash"))
        self.assertNotEqual(first, catalog_fingerprint(self.profiles, "another-model"))
        with patch("service.catalog_model.PROMPT_VERSION", "future-prompt"):
            self.assertNotEqual(first, catalog_fingerprint(self.profiles, "deepseek-flash"))
        with patch("service.catalog_model.INFERENCE_CONFIG_HASH", "future-reasoning-profile"):
            self.assertNotEqual(first, catalog_fingerprint(self.profiles, "deepseek-flash"))

    def test_no_provider_call_for_empty_catalog_and_invalid_bridge(self):
        with patch("langextract.extract") as extract:
            self.assertEqual(_call_model([], {}), ({"keep": [], "aliases": {}}, [], 0))
            for base in ("https://api.deepseek.com", "http://example.com/v1", "http://user:pass@127.0.0.1/v1"):
                with self.subTest(base=base), self.assertRaisesRegex(ValueError, "pi_runtime_bridge_required"):
                    _call_model(self.profiles, self.runtime | {"base_url": base})
            extract.assert_not_called()

    def test_invalid_model_output_gets_one_specific_repair(self):
        responses = [model_result([summary(self.profiles, 1)]), model_result([summary(self.profiles)])]
        with patch("langextract.extract", side_effect=responses) as extract:
            review, _, requests = _call_model(self.profiles, self.runtime)
        self.assertEqual(requests, 2)
        self.assertEqual(len(review["keep"]), 3)
        self.assertIn("catalog_count_mismatch", extract.call_args_list[1].kwargs["prompt_description"])
        self.assertEqual(extract.call_args_list[0].kwargs["config"].provider, "PiBridgeLanguageModel")
        self.assertEqual(extract.call_args_list[0].kwargs["config"].provider_kwargs["base_url"], self.runtime["base_url"])

    def test_twice_invalid_or_provider_failure_is_not_success(self):
        with patch("langextract.extract", return_value=model_result([])) as extract:
            with self.assertRaisesRegex(ValueError, "catalog_review_invalid_after_repair"):
                review_catalog(self.profiles, self.runtime)
            self.assertEqual(extract.call_count, 2)
        with patch("langextract.extract", side_effect=RuntimeError("provider_failed")):
            with self.assertRaisesRegex(RuntimeError, "provider_failed"):
                review_catalog(self.profiles, self.runtime)

    def test_cancel_before_and_after_model_call_never_returns_reviewed(self):
        with patch("langextract.extract") as extract:
            with self.assertRaises(InterruptedError):
                _call_model(self.profiles, self.runtime, cancelled=lambda: True)
            extract.assert_not_called()
        cancelled = iter((False, True))
        with patch("langextract.extract", return_value=model_result([summary(self.profiles)])):
            with self.assertRaises(InterruptedError):
                _call_model(self.profiles, self.runtime, cancelled=lambda: next(cancelled))

    def test_public_result_contains_only_model_review_and_fingerprints(self):
        with patch("langextract.extract", return_value=model_result([summary(self.profiles)])):
            result = review_catalog(self.profiles, self.runtime)
        self.assertEqual(result["status"], "reviewed")
        self.assertEqual(result["prompt_hash"], PROMPT_HASH)
        self.assertEqual(result["prompt_version"], PROMPT_VERSION)
        self.assertNotIn(self.runtime["api_key"], json.dumps(result))
        self.assertNotIn(self.runtime["base_url"], json.dumps(result))

    def test_real_langextract_uses_local_fixture_bridge_and_source_alignment(self):
        # The SDK and its OpenAI adapter run normally; this HTTP fixture is the
        # only model endpoint. It does not contact DeepSeek or spend API credit.
        requests = []
        self.profiles = [profile("accounts_receivable"), profile("trade_receivables"), profile("receivables_from_customers")]
        class Bridge(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_POST(self):
                payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                requests.append({"path": self.path, "payload": payload,
                                 "authorization": self.headers.get("Authorization")})
                extracts = [
                    {"catalog_review": "[[CATALOG]]", "catalog_review_attributes": {
                        "reviewed_count": 3, "merge_count": 2, "keep_count": 1, "keep_summary": "保留应收账款规范ID"}},
                    {"metric_alias": "[[METRIC:trade_receivables]]", "metric_alias_attributes": {
                        "canonical_metric": "accounts_receivable", "canonical_label": "应收账款",
                        "reason": "相邻科目和原表语境均说明是销售形成的应收账款余额"}},
                    {"metric_alias": "[[METRIC:receivables_from_customers]]", "metric_alias_attributes": {
                        "canonical_metric": "accounts_receivable", "canonical_label": "应收账款",
                        "reason": "原表说明同为销售形成的应收账款余额"}},
                ]
                body = json.dumps({"id": "fixture", "object": "chat.completion", "created": 1,
                    "model": payload["model"], "choices": [{"index": 0, "message": {
                        "role": "assistant", "content": json.dumps({"extractions": extracts}, ensure_ascii=False)},
                        "finish_reason": "stop"}], "usage": {"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30}},
                    ensure_ascii=False).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
        server = ThreadingHTTPServer(("127.0.0.1", 0), Bridge)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            result = review_catalog(self.profiles, self.runtime | {"base_url": f"http://127.0.0.1:{server.server_port}/pi-owner/v1"})
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=3)
        self.assertEqual(result["status"], "reviewed")
        self.assertEqual(result["requests"], 1)
        self.assertEqual(list(result["review"]["aliases"]), ["trade_receivables", "receivables_from_customers"])
        self.assertEqual(result["extractions"][-1]["alignment"]["literal_occurrences"], 1)
        self.assertEqual(requests[0]["path"], "/pi-owner/v1/chat/completions")
        self.assertEqual(requests[0]["payload"]["model"], "deepseek-flash")
        self.assertEqual(requests[0]["payload"]["response_format"], {"type": "json_object"})
        self.assertEqual(requests[0]["payload"]["reasoning_effort"], "low")
        self.assertEqual(requests[0]["authorization"], "Bearer ephemeral-test-token")


if __name__ == "__main__":
    unittest.main()
