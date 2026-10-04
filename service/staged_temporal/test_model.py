"""Staged temporal model tests; all model responses are fixtures."""
import copy
import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import SimpleNamespace
from unittest.mock import patch

from .model import (
    VERSION, PROFILE_PROMPT_HASH, CORRECTION_PROMPT_HASH,
    _render, _validate_profiles, _validate_sources, review_profiles, correct_sources,
)


def source(key="asset_cell", **overrides):
    return {"source_key": key, "document_id": "doc", "page": 90, "table_id": "doc:t3", "row": 2, "column": 2,
            "original_extraction_hash": "original-model-mapping", "raw_value": "100.00", "metric": "assets",
            "period": "2024-FY", "start": "", "end": "2024-12-31", "report_year": 2024,
            "row_data": ["总资产", "100.00"], "table_headers": [["项目", "2024年12月31日"]],
            "page_context": "合并资产负债表\n2024年12月31日\n总资产100.00元", **overrides}


def profile(key="asset_group", **overrides):
    return {"group_id": key, "metric": "assets", "label": "总资产", "statement": "balance", "unit": "CNY",
            "scope": "consolidated_CAS", "period_shape": {"period": "<report_year+0>-FY", "start": "", "end": "<report_year+0>-12-31"},
            "member_count": 1, "examples": [source()], **overrides}


def extraction(items, phase, kind, marker, attrs):
    text = _render(items, phase); start = text.find(marker)
    return {"class": kind, "text": marker, "attributes": attrs,
            "span": [start, start + len(marker)] if start >= 0 else None}


def review_summary(profiles, flags=0, **extra):
    return extraction(profiles, "profiles", "temporal_review", "[[TEMPORAL_REVIEW]]",
                      {"reviewed_count": len(profiles), "flag_count": flags, "keep_count": len(profiles) - flags, **extra})


def candidate(profiles, key, reason="原表是年末余额，当前期间ID却是全年"):
    return extraction(profiles, "profiles", "temporal_candidate", f"[[GROUP:{key}]]", {"reason": reason})


def correction(sources, key, **overrides):
    return extraction(sources, "sources", "temporal_correction", f"[[SOURCE:{key}]]",
                      {"period": "2024-12-31", "start": "", "end": "2024-12-31", "reason": "原表明确年末时点余额",
                       "evidence": "2024年12月31日", **overrides})


def unresolved(sources, key, reason="缺少可确定期间的原表表头"):
    return extraction(sources, "sources", "temporal_unresolved", f"[[SOURCE:{key}]]", {"reason": reason})


def response(extractions):
    return SimpleNamespace(extractions=[SimpleNamespace(
        extraction_class=ex["class"], extraction_text=ex["text"], attributes=ex["attributes"],
        char_interval=SimpleNamespace(start_pos=ex["span"][0], end_pos=ex["span"][1]) if ex["span"] else None,
    ) for ex in extractions])


class StagedTemporalModelTests(unittest.TestCase):
    def setUp(self):
        self.runtime = {"base_url": "http://127.0.0.1:30099/owner/v1", "api_key": "temporary-test-token",
                        "model": "deepseek-flash", "max_tokens": 16000}

    def test_single_consistently_wrong_profile_can_be_flagged(self):
        profiles = [profile()]
        result, errors = _validate_profiles([review_summary(profiles, 1), candidate(profiles, "asset_group")], profiles)
        self.assertEqual(errors, [])
        self.assertEqual(result["candidates"][0]["group_id"], "asset_group")
        self.assertEqual(result["reviewed_count"], 1)
        self.assertEqual(result["reviewed_group_ids"], ["asset_group"])

    def test_profile_semantics_are_decided_by_model_not_metric_rules(self):
        profiles = [profile()]
        with patch("langextract.extract", return_value=response([review_summary(profiles)])) as extract:
            result = review_profiles(profiles, self.runtime)
        self.assertEqual(result["candidates"], [])
        self.assertEqual(extract.call_count, 1)
        self.assertIn("单", extract.call_args.kwargs["prompt_description"])

    def test_summary_counts_catch_missing_candidates_or_profiles(self):
        profiles = [profile(), profile("flow_group", metric="operating_cash_flow")]
        for extracts in ([], [review_summary(profiles, 1)], [review_summary(profiles, reviewed_count=1)],
                         [review_summary(profiles, keep_count=True)], [review_summary(profiles), review_summary(profiles)]):
            with self.subTest(extracts=extracts):
                self.assertTrue(_validate_profiles(extracts, profiles)[1])

    def test_profile_duplicate_candidates_and_unknown_ids_fail(self):
        profiles = [profile()]
        repeated = candidate(profiles, "asset_group")
        self.assertTrue(_validate_profiles([review_summary(profiles, 1), repeated, repeated], profiles)[1])
        self.assertTrue(_validate_profiles([review_summary(profiles, 1), candidate(profiles, "not_in_input")], profiles)[1])

    def test_ungrounded_source_and_profile_markers_fail(self):
        profiles, sources = [profile()], [source()]
        for phase, items, validator, ex in (("profiles", profiles, _validate_profiles, review_summary(profiles)),
                                            ("sources", sources, _validate_sources, correction(sources, "asset_cell"))):
            for span in (None, [-1, 3], [0, 1], [True, 10], [0, 99999]):
                with self.subTest(phase=phase, span=span):
                    bad = copy.deepcopy(ex); bad["span"] = span
                    self.assertTrue(validator([bad], items)[1])

    def test_point_correction_changes_only_temporal_fields(self):
        sources = [source()]; before = copy.deepcopy(sources)
        result, errors = _validate_sources([correction(sources, "asset_cell")], sources)
        self.assertEqual(errors, [])
        self.assertEqual(sources, before)
        self.assertEqual(result["corrections"][0]["period"], "2024-12-31")
        self.assertEqual(result["corrections"][0]["start"], "")
        self.assertNotIn("metric", result["corrections"][0])
        self.assertNotIn("raw_value", result["corrections"][0])

    def test_parent_cashflow_can_be_corrected_from_point_to_full_period(self):
        sources = [source("flow_cell", metric="operating_cash_flow", scope="parent_CAS", period="2024-12-31",
                          page_context="母公司现金流量表\n2024年1月1日至12月31日\n经营活动产生的现金流量净额", table_headers=[["项目", "2024年度"]])]
        result, errors = _validate_sources([correction(sources, "flow_cell", period="2024-FY", start="2024-01-01",
                                                      evidence="2024年1月1日至12月31日")], sources)
        self.assertEqual(errors, [])
        self.assertEqual(result["corrections"][0]["period"], "2024-FY")

    def test_already_correct_source_may_return_same_dates(self):
        sources = [source(period="2024-12-31")]
        result, errors = _validate_sources([correction(sources, "asset_cell", reason="原期间和原表时点一致，保留")], sources)
        self.assertEqual(errors, [])
        self.assertEqual(result["corrections"][0]["period"], sources[0]["period"])

    def test_every_source_requires_correction_or_explicit_unresolved(self):
        sources = [source(), source("missing_header", row_data=["收入", "7"], table_headers=[], page_context="续表")]
        good = [correction(sources, "asset_cell"), unresolved(sources, "missing_header")]
        result, errors = _validate_sources(good, sources)
        self.assertEqual(errors, [])
        self.assertEqual(len(result["unresolved"]), 1)
        self.assertTrue(_validate_sources(good[:1], sources)[1])
        self.assertTrue(_validate_sources(good + [unresolved(sources, "asset_cell")], sources)[1])

    def test_unknown_source_is_not_accepted(self):
        sources = [source()]
        self.assertTrue(_validate_sources([correction(sources, "invented_cell")], sources)[1])

    def test_non_temporal_updates_are_rejected(self):
        sources = [source()]
        for field, value in (("metric", "revenue"), ("raw_value", "9999"), ("value", "9999"),
                             ("scope", "parent_CAS"), ("source_key", "other"), ("currency", "USD")):
            with self.subTest(field=field):
                self.assertTrue(_validate_sources([correction(sources, "asset_cell", **{field: value})], sources)[1])

    def test_invalid_date_shapes_and_inconsistent_boundaries_fail(self):
        sources = [source()]
        bad = [dict(period="2024-02-30", end="2024-02-30"), dict(start="2024-01-01"), dict(end="2023-12-31"),
               dict(period="2024-FY", start="", end="2024-12-31"),
               dict(period="2024-FY", start="2024-12-31", end="2024-01-01"),
               dict(period="2024-Q5", start="2024-01-01"), dict(period="2024-FY", start="20240101"),
               dict(period="2024-FY", start=None)]
        for attrs in bad:
            with self.subTest(attrs=attrs):
                self.assertTrue(_validate_sources([correction(sources, "asset_cell", **attrs)], sources)[1])

    def test_evidence_must_be_verbatim_from_same_sources_raw_context(self):
        sources = [source(), source("other_cell", page_context="只在别处出现的2025年6月30日")]
        for evidence in ("虚构日期原文", "2024年12月31日及不存在文字", "2024-FY", "只在别处出现的2025年6月30日", ""):
            with self.subTest(evidence=evidence):
                ex = [correction(sources, "asset_cell", evidence=evidence), unresolved(sources, "other_cell")]
                self.assertTrue(_validate_sources(ex, sources)[1])

    def test_evidence_can_come_from_original_header_or_row(self):
        for field, raw in (("table_headers", [["项目", "2024年12月31日"]]),
                           ("row_data", ["2024年12月31日余额", "100.00"])):
            with self.subTest(field=field):
                sources = [source()]
                sources[0].update(table_headers=[], row_data=[], page_context="")
                sources[0][field] = raw
                self.assertEqual(_validate_sources([correction(sources, "asset_cell")], sources)[1], [])

    def test_source_prompt_shares_page_and_table_context_without_losing_source_rows(self):
        sources = [source(), source("second_cell", row=3, raw_value="200.00", row_data=["负债合计", "200.00"])]
        text = _render(sources, "sources")
        self.assertEqual(text.count('"page_context":'), 1)
        self.assertEqual(text.count('"table_headers":'), 1)
        self.assertEqual(text.count('"page_context_ref":"P1"'), 2)
        self.assertIn('[[SOURCE:asset_cell]]', text)
        self.assertIn('[[SOURCE:second_cell]]', text)
        self.assertIn('"row_data":["负债合计","200.00"]', text)
        ex = [correction(sources, "asset_cell"), correction(sources, "second_cell")]
        self.assertEqual(_validate_sources(ex, sources)[1], [])

    def test_profile_prompt_accepts_compact_context_without_losing_members(self):
        profiles = [profile(examples=[{"source_key": "cell", "header_hint": "2024年12月31日", "heading": "合并资产负债表"}],
                            source_keys=["cell", "another_cell"], member_count=2)]
        text = _render(profiles, "profiles")
        self.assertNotIn('"source_keys"', text)
        self.assertIn('"member_count":2', text)
        self.assertIn('"header_hint":"2024年12月31日"', text)

    def test_empty_batches_and_invalid_runtime_do_not_call_model(self):
        with patch("langextract.extract") as extract:
            self.assertEqual(review_profiles([], {})["requests"], 0)
            self.assertEqual(correct_sources([], {})["requests"], 0)
            with self.assertRaisesRegex(ValueError, "pi_runtime_bridge_required"):
                correct_sources([source()], self.runtime | {"base_url": "https://api.deepseek.com"})
            extract.assert_not_called()

    def test_one_explicit_repair_then_fail_or_return_complete_result(self):
        profiles = [profile()]
        with patch("langextract.extract", side_effect=[response([]), response([review_summary(profiles)])]) as extract:
            result = review_profiles(profiles, self.runtime)
        self.assertEqual(result["requests"], 2)
        self.assertIn("one_temporal_summary_required", extract.call_args_list[1].kwargs["prompt_description"])
        sources = [source()]
        with patch("langextract.extract", return_value=response([])) as extract:
            with self.assertRaisesRegex(ValueError, "temporal_sources_invalid_after_repair"):
                correct_sources(sources, self.runtime)
            self.assertEqual(extract.call_count, 2)

    def test_cancel_before_or_after_model_call_does_not_return_success(self):
        sources = [source()]
        with patch("langextract.extract") as extract:
            with self.assertRaises(InterruptedError):
                correct_sources(sources, self.runtime, cancelled=lambda: True)
            extract.assert_not_called()
        sequence = iter((False, True))
        with patch("langextract.extract", return_value=response([correction(sources, "asset_cell")])):
            with self.assertRaises(InterruptedError):
                correct_sources(sources, self.runtime, cancelled=lambda: next(sequence))

    def test_provider_errors_propagate_and_results_never_contain_bridge_secrets(self):
        profiles = [profile()]
        with patch("langextract.extract", side_effect=RuntimeError("model_unavailable")):
            with self.assertRaisesRegex(RuntimeError, "model_unavailable"):
                review_profiles(profiles, self.runtime)
        with patch("langextract.extract", return_value=response([review_summary(profiles)])):
            result = review_profiles(profiles, self.runtime)
        self.assertNotIn(self.runtime["api_key"], json.dumps(result))
        self.assertNotIn(self.runtime["base_url"], json.dumps(result))
        self.assertNotEqual(PROFILE_PROMPT_HASH, CORRECTION_PROMPT_HASH)
        self.assertTrue(VERSION.endswith("staged"))

    def test_duplicate_input_identity_is_invalid(self):
        with self.assertRaisesRegex(ValueError, "temporal_duplicate_input_id"):
            review_profiles([profile(), profile()], self.runtime)
        with self.assertRaisesRegex(ValueError, "temporal_duplicate_input_id"):
            correct_sources([source(), source()], self.runtime)

    def test_real_langextract_both_stages_use_only_local_pi_fixture_bridge(self):
        profiles, sources, requests = [profile()], [source()], []
        replies = [[review_summary(profiles, 1), candidate(profiles, "asset_group")], [correction(sources, "asset_cell")]]
        class Bridge(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_POST(self):
                payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                index = len(requests)
                requests.append({"path": self.path, "model": payload["model"], "format": payload.get("response_format")})
                extracts = [{ex["class"]: ex["text"], ex["class"] + "_attributes": ex["attributes"]} for ex in replies[index]]
                body = json.dumps({"id": "fixture", "object": "chat.completion", "created": 1, "model": payload["model"],
                    "choices": [{"index": 0, "message": {"role": "assistant", "content": json.dumps({"extractions": extracts}, ensure_ascii=False)}, "finish_reason": "stop"}],
                    "usage": {"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30}}, ensure_ascii=False).encode("utf-8")
                self.send_response(200); self.send_header("Content-Type", "application/json"); self.send_header("Content-Length", str(len(body)))
                self.end_headers(); self.wfile.write(body)
        server = ThreadingHTTPServer(("127.0.0.1", 0), Bridge)
        thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
        try:
            runtime = self.runtime | {"base_url": f"http://127.0.0.1:{server.server_port}/owning-run/v1"}
            reviewed = review_profiles(profiles, runtime)
            corrected = correct_sources(sources, runtime)
        finally:
            server.shutdown(); server.server_close(); thread.join(timeout=3)
        self.assertEqual(reviewed["reviewed_count"], 1)
        self.assertEqual(reviewed["candidates"][0]["group_id"], "asset_group")
        self.assertEqual(corrected["corrections"][0]["period"], "2024-12-31")
        self.assertEqual(len(requests), 2)
        self.assertTrue(all(req["path"] == "/owning-run/v1/chat/completions" for req in requests))
        self.assertTrue(all(req["model"] == "deepseek-flash" and req["format"] == {"type": "json_object"} for req in requests))


if __name__ == "__main__":
    unittest.main()
