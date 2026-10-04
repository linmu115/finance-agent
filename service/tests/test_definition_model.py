"""Definition review tests with fixtures only, including a local HTTP bridge."""
import copy
import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import SimpleNamespace
from unittest.mock import patch

from service.definition_model import (
    VERSION, PROMPT_HASH, CACHE_HASH, INFERENCE_CONFIG,
    _render, _examples, align_extractions, validate_review, review_definitions,
    DefinitionOutputLimitError, output_limit_evidence,
)


def group(identity="gross", **overrides):
    return {"group_id": identity, "current_metric": "receivable_amount", "original_metric": "receivable_amount",
            "current_label": "应收款项", "original_label": "账面余额", "statement": "notes",
            "accounting_scope": "consolidated_CAS", "normalized_unit": "CNY", "dimensions": {}, "member_count": 2,
            "evidence": [{"evidence_id": identity + "_definition", "kind": "definition", "document_id": "fixture_document",
                          "page": 8, "table_id": "fixture_table", "text": "应收款项账面余额，未扣减损失准备。"}], **overrides}


def known():
    return [{"metric": "receivable_gross_balance", "labels": ["应收款项账面余额"],
             "definitions": ["未扣减损失准备的应收款项余额"], "definition_scope": "未扣减损失准备", "public_id": False}]


def extraction(groups, identity, kind="definition_decision", **overrides):
    marker = f"[[DEFINITION:{identity}]]"
    text = _render(groups, known()); offset = text.find(marker)
    attrs = {"metric": "receivable_gross_balance", "label": "应收款项账面余额", "definition": "未扣减损失准备的应收款项余额",
             "definition_scope": "未扣减损失准备", "reason": "原表明确未扣减准备，可使用同定义指标",
             "grounded_quotes_json": json.dumps([{"evidence_id": identity + "_definition", "text": "未扣减损失准备"}], ensure_ascii=False)}
    if kind == "definition_unresolved":
        attrs = {"reason": "缺少可确定计量定义的原表列标题"}
    return {"class": kind, "text": marker, "attributes": attrs | overrides,
            "span": [offset, offset + len(marker)] if offset >= 0 else None}


def response(extractions):
    return SimpleNamespace(extractions=[SimpleNamespace(
        extraction_class=item["class"], extraction_text=item["text"], attributes=item["attributes"],
        char_interval=SimpleNamespace(start_pos=item["span"][0], end_pos=item["span"][1]) if item["span"] else None,
    ) for item in extractions])


def bridge_error(status=422, **overrides):
    import httpx
    from openai import APIStatusError
    from langextract.core.exceptions import InferenceRuntimeError
    body={"error":{"message":"structured_output_incomplete","code":"model_output_limit","stop_reason":"length","request_id":"fixture-request",**overrides}}
    response=httpx.Response(status,request=httpx.Request("POST","http://127.0.0.1/fixture/v1"))
    original=APIStatusError("fixture",response=response,body=body)
    return InferenceRuntimeError("wrapped fixture",original=original)


class DefinitionModelTests(unittest.TestCase):
    def setUp(self):
        self.runtime = {"base_url": "http://127.0.0.1:30099/owner/v1", "api_key": "temporary-fixture-token",
                        "model": "deepseek-flash", "max_tokens": 32768}

    def test_existing_definition_is_model_selected_and_source_grounded(self):
        groups = [group()]; before = copy.deepcopy(groups)
        decision = extraction(groups, "gross")
        result, errors = validate_review([decision], groups, known())
        self.assertEqual(errors, [])
        self.assertEqual(result["decisions"][0]["metric"], "receivable_gross_balance")
        self.assertEqual(result["decisions"][0]["grounded_quotes"], [{"evidence_id": "gross_definition", "text": "未扣减损失准备"}])
        self.assertEqual(groups, before)

    def test_same_current_id_can_split_to_new_model_defined_metric(self):
        groups = [group(), group("net", original_label="账面价值", evidence=[{
            "evidence_id": "net_definition", "kind": "definition", "document_id": "fixture_document", "page": 8,
            "table_id": "fixture_table", "text": "应收款项账面价值，已扣减损失准备。"}])]
        decisions = [extraction(groups, "gross"), extraction(groups, "net", metric="receivable_net_carrying_amount",
            label="应收款项账面价值", definition="扣减损失准备后的应收款项价值", definition_scope="已扣减损失准备",
            grounded_quotes_json=json.dumps([{"evidence_id": "net_definition", "text": "已扣减损失准备"}]))]
        with patch("langextract.extract", return_value=response(decisions)):
            result = review_definitions(groups, known(), self.runtime)
        self.assertEqual([item["metric"] for item in result["decisions"]], ["receivable_gross_balance", "receivable_net_carrying_amount"])
        self.assertEqual(groups[0]["current_metric"], groups[1]["current_metric"])

    def test_keep_is_allowed_without_program_financial_word_rules(self):
        groups = [group()]
        chosen = extraction(groups, "gross", metric="receivable_amount")
        self.assertEqual(validate_review([chosen], groups, known())[1], [])

    def test_later_batch_cannot_silently_redefine_an_accepted_concept(self):
        groups=[group()]
        changed=extraction(groups,"gross",definition="扣减准备后的余额",definition_scope="已扣减损失准备")
        self.assertIn("definition_existing_concept_changed",{error["reason"] for error in validate_review([changed],groups,known())[1]})
        # A different meaning remains expressible as a different model-chosen ID.
        changed["attributes"]["metric"]="another_receivable_definition"
        self.assertEqual(validate_review([changed],groups,known())[1],[])

    def test_one_batch_cannot_assign_two_definitions_to_same_new_id(self):
        groups=[group(),group("other")]
        first=extraction(groups,"gross",metric="new_receivable_definition")
        second=extraction(groups,"other",metric="new_receivable_definition",definition_scope="不同范围")
        errors=validate_review([first,second],groups,known())[1]
        self.assertIn("definition_conflicting_same_id",{error["reason"] for error in errors})

    def test_explicit_unresolved_is_covered_without_guessing(self):
        groups = [group(evidence=[])]
        result, errors = validate_review([extraction(groups, "gross", "definition_unresolved")], groups, known())
        self.assertEqual(errors, [])
        self.assertEqual(result["decisions"], [])
        self.assertEqual(result["unresolved"][0]["group_id"], "gross")

    def test_complete_coverage_rejects_missing_duplicate_and_unknown(self):
        groups = [group(), group("another")]
        first = extraction(groups, "gross")
        for decisions in ([], [first], [first, first], [first, extraction(groups, "outside")],
                          [first, extraction(groups, "another"), extraction(groups, "gross", "definition_unresolved")]):
            with self.subTest(decisions=decisions):
                self.assertTrue(validate_review(decisions, groups, known())[1])

    def test_malformed_first_decision_cannot_be_silently_replaced(self):
        groups = [group()]
        bad = extraction(groups, "gross", value="100")
        errors = validate_review([bad, extraction(groups, "gross")], groups, known())[1]
        self.assertIn("definition_duplicate_group_decision", {error["reason"] for error in errors})

    def test_quotes_must_be_exactly_in_own_group_evidence(self):
        groups = [group(), group("other", evidence=[{"evidence_id": "other_definition", "kind": "definition", "text": "仅在另一组出现"}])]
        other = extraction(groups, "other", "definition_unresolved")
        for quotes in ([{"evidence_id": "gross_definition", "text": "未扣减损失准备及虚构字句"}],
                       [{"evidence_id": "other_definition", "text": "仅在另一组出现"}],
                       [{"evidence_id": "gross_definition", "text": "未扣损失准备"}],
                       [{"evidence_id": "gross_definition", "text": ""}],
                       [{"evidence_id": "gross_definition", "text": "未扣减损失准备", "forged_source": True}]):
            with self.subTest(quotes=quotes):
                invalid = extraction(groups, "gross", grounded_quotes_json=json.dumps(quotes))
                self.assertTrue(validate_review([invalid, other], groups, known())[1])

    def test_multiple_grounded_quotes_can_preserve_all_qualifiers(self):
        groups = [group()]
        groups[0]["evidence"].append({"evidence_id": "note", "kind": "definition", "text": "不包括转出的款项。"})
        quotes = [{"evidence_id": "gross_definition", "text": "未扣减损失准备"}, {"evidence_id": "note", "text": "不包括转出的款项"}]
        result, errors = validate_review([extraction(groups, "gross", grounded_quotes_json=json.dumps(quotes))], groups, known())
        self.assertEqual(errors, [])
        self.assertEqual(result["decisions"][0]["grounded_quotes"], quotes)

    def test_wrong_evidence_id_is_uniquely_relocated_without_editing_model_decision(self):
        groups=[group()]
        groups[0]["evidence"].append({"evidence_id":"wrong_block","kind":"definition","text":"原文另一个说明。"})
        raw=extraction(groups,"gross",grounded_quotes_json=json.dumps([{"evidence_id":"wrong_block","text":"未扣减损失准备"}]))
        before=copy.deepcopy(raw)
        result,errors=validate_review([raw],groups,known())
        self.assertEqual(errors,[]);self.assertEqual(raw,before)
        decision=result["decisions"][0];alignment=decision["quote_alignments"][0]
        self.assertEqual(decision["grounded_quotes"][0]["evidence_id"],"gross_definition")
        self.assertEqual(alignment["original_quote"]["evidence_id"],"wrong_block")
        self.assertEqual(alignment["method"],"unique_group_exact")
        start,end=alignment["span"]
        self.assertEqual(groups[0]["evidence"][0]["text"][start:end],"未扣减损失准备")

    def test_pdf_whitespace_alignment_preserves_original_chars_and_non_bmp_offsets(self):
        groups=[group(evidence=[{"evidence_id":"gross_definition","kind":"definition","text":"表😀：未扣减\n 损失准备；范围不变。"}])]
        raw=extraction(groups,"gross")
        result,errors=validate_review([raw],groups,known())
        self.assertEqual(errors,[])
        decision=result["decisions"][0]
        self.assertEqual(decision["grounded_quotes"][0]["text"],"未扣减\n 损失准备")
        self.assertEqual(decision["quote_alignments"][0]["span"],[3,12])
        self.assertEqual(decision["quote_alignments"][0]["original_quote"]["text"],"未扣减损失准备")

    def test_quote_relocation_never_guesses_multiple_blocks_or_occurrences(self):
        for evidence in ([{"evidence_id":"a","kind":"definition","text":"未扣减损失准备"},
                          {"evidence_id":"b","kind":"definition","text":"未扣减损失准备"}],
                         [{"evidence_id":"a","kind":"definition","text":"未扣减损失准备；未扣减损失准备"}],
                         [{"evidence_id":"gross_definition","kind":"definition","text":"未扣减 损失准备；未扣减\n损失准备"}]):
            groups=[group(evidence=evidence)]
            result,errors=validate_review([extraction(groups,"gross")],groups,known())
            self.assertEqual(result["decisions"],[])
            self.assertEqual(errors[0]["quote_errors"][0]["reason"],"definition_ambiguous_quote_location")

    def test_quote_alignment_cannot_remove_punctuation_or_change_qualifiers(self):
        for text in ("未扣减、损失准备", "已扣减损失准备", "未扣减部分损失准备"):
            groups=[group(evidence=[{"evidence_id":"gross_definition","kind":"definition","text":text}])]
            self.assertTrue(validate_review([extraction(groups,"gross")],groups,known())[1])

    def test_empty_invalid_or_object_quotes_fail(self):
        groups = [group()]
        for quotes in ("[]", "{}", "null", "not JSON", "[null]", "[5]", '[{"text":"未扣减损失准备"}]'):
            with self.subTest(quotes=quotes):
                self.assertTrue(validate_review([extraction(groups, "gross", grounded_quotes_json=quotes)], groups, known())[1])

    def test_only_definition_attributes_are_allowed(self):
        groups = [group()]
        for field, value in (("value", "1"), ("period", "2024-FY"), ("unit", "USD"), ("accounting_scope", "parent_CAS"),
                             ("dimensions", {}), ("source_keys", []), ("scope", "unrequested")):
            with self.subTest(field=field):
                self.assertTrue(validate_review([extraction(groups, "gross", **{field: value})], groups, known())[1])
        for field in ("label", "definition", "definition_scope", "reason"):
            self.assertTrue(validate_review([extraction(groups, "gross", **{field: " "})], groups, known())[1])

    def test_long_ids_are_valid_but_invalid_syntax_or_257_chars_fail(self):
        groups = [group()]
        self.assertEqual(validate_review([extraction(groups, "gross", metric="a" * 256)], groups, known())[1], [])
        for metric in ("a" * 257, "Revenue", "has-hyphen", "1amount", "金额", "a b", "a\n"):
            with self.subTest(metric=metric):
                self.assertTrue(validate_review([extraction(groups, "gross", metric=metric)], groups, known())[1])

    def test_render_full_evidence_once_and_preserve_meaningful_numbers(self):
        context = "原文定义" * 1000 + "1年内到期；每10股分配；2024年适用；保留最后的排除条件。"
        groups = [group(), group("other")]
        for item in groups:
            item["evidence"][0]["text"] = context
            item["source_keys"] = ["SECRET_INTERNAL_SOURCE"]
            item["raw_value"] = "1234567.89123"
            item["value"] = "999.888"
            item["evidence"][0]["raw_value"] = "98765.1234"
        text = _render(groups, known())
        self.assertEqual(text.count(context), 1)
        self.assertIn('"text_ref":"E1"', text)
        for value in ("1年内", "每10股", "2024", "最后的排除条件"):
            self.assertIn(value, text)
        for value in ("SECRET_INTERNAL_SOURCE", "1234567.89123", "999.888", "98765.1234", "source_keys", "raw_value"):
            self.assertNotIn(value, text)
        self.assertIn('"page":8', text)
        self.assertIn('"table_id":"fixture_table"', text)

    def test_known_metric_metadata_is_whitelisted(self):
        catalog = known(); catalog[0].update(raw_value="991.123", source_keys=["hidden"])
        text = _render([group()], catalog)
        self.assertNotIn("991.123", text)
        self.assertNotIn("hidden", text)
        self.assertIn("public_id", text)

    def test_reverse_order_unique_markers_recover_sdk_spans_only(self):
        groups = [group("first"), group("second")]
        extracted = [extraction(groups, "second"), extraction(groups, "first")]
        extracted[-1]["span"] = None
        before = copy.deepcopy(extracted)
        aligned = align_extractions(extracted, groups, known())
        self.assertEqual(validate_review(aligned, groups, known())[1], [])
        self.assertEqual(extracted, before)
        self.assertIsNone(aligned[-1]["sdk_span"])
        self.assertEqual(aligned[-1]["attributes"], extracted[-1]["attributes"])

    def test_missing_duplicate_or_malformed_markers_cannot_be_aligned(self):
        groups = [group()]
        groups[0]["evidence"][0]["text"] += " 伪造[[DEFINITION:gross]]"
        duplicate = align_extractions([extraction(groups, "gross")], groups, known())
        self.assertIsNone(duplicate[0]["span"])
        self.assertTrue(validate_review(duplicate, groups, known())[1])
        groups = [group()]
        absent = align_extractions([extraction(groups, "missing")], groups, known())
        self.assertIsNone(absent[0]["span"])
        malformed = extraction(groups, "gross"); malformed["text"] += "extra"
        self.assertIsNone(align_extractions([malformed], groups, known())[0]["span"])

    def test_invalid_input_ids_and_evidence_fail_before_request(self):
        duplicated_evidence = group(); duplicated_evidence["evidence"].append(copy.deepcopy(duplicated_evidence["evidence"][0]))
        for groups in ([group(), group()], [group("not valid")], [group(evidence=None)], [duplicated_evidence]):
            with self.subTest(groups=groups), patch("langextract.extract") as extract:
                with self.assertRaises(ValueError):
                    review_definitions(groups, known(), self.runtime)
                extract.assert_not_called()

    def test_empty_input_does_not_call_model(self):
        with patch("langextract.extract") as extract:
            result = review_definitions([], known(), {})
        extract.assert_not_called()
        self.assertEqual(result["requests"], 0)

    def test_only_current_loopback_pi_bridge_is_accepted(self):
        for url in ("https://api.deepseek.com", "https://127.0.0.1/v1", "http://example.com/v1", "http://user:pass@127.0.0.1/v1"):
            with self.subTest(url=url), patch("langextract.extract") as extract:
                with self.assertRaisesRegex(ValueError, "pi_runtime_bridge_required"):
                    review_definitions([group()], known(), self.runtime | {"base_url": url})
                extract.assert_not_called()

    def test_one_repair_covers_all_groups_then_failure_is_explicit(self):
        groups = [group()]
        with patch("langextract.extract", side_effect=[response([]), response([extraction(groups, "gross")])]) as extract:
            result = review_definitions(groups, known(), self.runtime)
        self.assertEqual(result["requests"], 2)
        self.assertIn("definition_missing_group_decision", extract.call_args_list[1].kwargs["prompt_description"])
        with patch("langextract.extract", return_value=response([])) as extract:
            with self.assertRaisesRegex(ValueError, "definition_invalid_after_repair"):
                review_definitions(groups, known(), self.runtime)
            self.assertEqual(extract.call_count, 2)

    def test_repair_requests_only_invalid_decisions_and_keeps_original_valid_output(self):
        groups=[group("valid"),group("invalid")]
        valid=extraction(groups,"valid")
        bad=extraction(groups,"invalid",grounded_quotes_json='[{"evidence_id":"invalid_definition","text":"虚构"}]')
        fixed=extraction([groups[1]],"invalid")
        with patch("langextract.extract",side_effect=[response([valid,bad]),response([fixed])]) as extract:
            result=review_definitions(groups,known(),self.runtime)
        second=extract.call_args_list[1].kwargs["text_or_documents"]
        self.assertNotIn("[[DEFINITION:valid]]",second)
        self.assertIn("[[DEFINITION:invalid]]",second)
        self.assertEqual(result["requests"],2)
        self.assertEqual(result["extractions"][0]["attributes"],valid["attributes"])
        self.assertEqual(result["attempts"][1]["group_ids"],["invalid"])
        self.assertEqual(result["attempts"][0]["extractions"][1]["attributes"],bad["attributes"])

    def test_failed_repair_exposes_real_requests_and_both_raw_attempts(self):
        groups=[group()]
        with patch("langextract.extract",return_value=response([])):
            with self.assertRaises(ValueError) as caught:review_definitions(groups,known(),self.runtime)
        self.assertEqual(caught.exception.definition_requests,2)
        self.assertEqual(len(caught.exception.model_attempts),2)
        self.assertEqual(caught.exception.validation_errors[0]["group_id"],"gross")

    def test_unknown_marker_is_not_carried_into_repaired_response(self):
        groups=[group()]
        with patch("langextract.extract",side_effect=[response([extraction(groups,"outside")]),response([extraction(groups,"gross")])]):
            result=review_definitions(groups,known(),self.runtime)
        self.assertEqual(result["requests"],2)
        self.assertEqual([item["text"] for item in result["extractions"]],["[[DEFINITION:gross]]"])

    def test_cancel_before_and_after_request_never_returns_success(self):
        groups = [group()]
        with patch("langextract.extract") as extract:
            with self.assertRaises(InterruptedError):
                review_definitions(groups, known(), self.runtime, cancelled=lambda: True)
            extract.assert_not_called()
        sequence = iter((False, True))
        with patch("langextract.extract", return_value=response([extraction(groups, "gross")])):
            with self.assertRaises(InterruptedError):
                review_definitions(groups, known(), self.runtime, cancelled=lambda: next(sequence))

    def test_provider_failure_is_not_reported_as_success_or_silently_retried(self):
        with patch("langextract.extract", side_effect=RuntimeError("fixture_unavailable")) as extract:
            with self.assertRaisesRegex(RuntimeError, "fixture_unavailable"):
                review_definitions([group()], known(), self.runtime)
        self.assertEqual(extract.call_count, 1)

    def test_only_typed_audited_output_limit_is_splittable(self):
        self.assertEqual(output_limit_evidence(bridge_error())["request_id"],"fixture-request")
        for error in (bridge_error(401),bridge_error(402),bridge_error(502),bridge_error(code="other"),
                      bridge_error(stop_reason="error"),bridge_error(request_id=""),RuntimeError("422 model_output_limit length")):
            self.assertIsNone(output_limit_evidence(error))
            with patch("langextract.extract",side_effect=error) as extract:
                with self.assertRaises(Exception) as caught:review_definitions([group()],known(),self.runtime)
            self.assertNotIsInstance(caught.exception,DefinitionOutputLimitError)
            self.assertEqual(extract.call_count,1)

    def test_output_limit_keeps_original_request_evidence_without_same_batch_retry(self):
        groups=[group(),group("other")]
        with patch("langextract.extract",side_effect=bridge_error()) as extract:
            with self.assertRaises(DefinitionOutputLimitError) as caught:review_definitions(groups,known(),self.runtime)
        error=caught.exception
        self.assertEqual(extract.call_count,1);self.assertEqual(error.definition_requests,1)
        self.assertEqual(error.pending_group_ids,["gross","other"])
        self.assertEqual(error.model_attempts[0]["outcome"],"output_limit")
        self.assertEqual(error.model_attempts[0]["bridge_error"]["request_id"],"fixture-request")

    def test_limit_during_targeted_repair_retains_valid_original_decisions(self):
        groups=[group("accepted"),group("pending")]
        valid=extraction(groups,"accepted")
        with patch("langextract.extract",side_effect=[response([valid]),bridge_error()]) as extract:
            with self.assertRaises(DefinitionOutputLimitError) as caught:review_definitions(groups,known(),self.runtime)
        error=caught.exception
        self.assertEqual(error.definition_requests,2)
        self.assertEqual(error.pending_group_ids,["pending"])
        self.assertEqual(error.partial_result["partial_coverage"],{"original_group_ids":["accepted","pending"],"pending_group_ids":["pending"]})
        self.assertEqual([item["group_id"] for item in error.partial_result["decisions"]],["accepted"])
        self.assertEqual(error.partial_result["extractions"][0]["attributes"],valid["attributes"])
        self.assertEqual(error.partial_result["extractions"][0]["span"],valid["span"])
        self.assertNotIn("[[DEFINITION:accepted]]",extract.call_args_list[1].kwargs["text_or_documents"])

    def test_examples_obey_our_own_schema(self):
        examples = _examples()
        self.assertEqual(len(examples), 1)
        self.assertEqual({ex.extraction_class for ex in examples[0].extractions}, {"definition_decision", "definition_unresolved"})
        for ex in examples[0].extractions:
            self.assertEqual(examples[0].text.count(ex.extraction_text), 1)
            if ex.extraction_class == "definition_decision":
                self.assertTrue(json.loads(ex.attributes["grounded_quotes_json"]))

    def test_high_reasoning_cache_identity_and_no_credentials_in_results(self):
        groups = [group()]
        with patch("langextract.extract", return_value=response([extraction(groups, "gross")])) as extract:
            result = review_definitions(groups, known(), self.runtime)
        kwargs = extract.call_args.kwargs
        provider = kwargs["config"].provider_kwargs
        self.assertEqual(provider["reasoning_effort"], "high")
        self.assertEqual(provider["max_output_tokens"], 32768)
        self.assertGreater(kwargs["max_char_buffer"], len(kwargs["text_or_documents"]))
        self.assertNotIn(self.runtime["api_key"], json.dumps(result))
        self.assertNotIn(self.runtime["base_url"], json.dumps(result))
        self.assertEqual(INFERENCE_CONFIG["reasoning_effort"], "high")
        self.assertTrue(VERSION.startswith("definition-langextract-"))
        self.assertEqual(len(PROMPT_HASH), 64)
        self.assertEqual(len(CACHE_HASH), 64)
        self.assertNotEqual(CACHE_HASH, PROMPT_HASH)

    def test_real_langextract_sdk_uses_high_local_bridge_and_handles_reverse_order(self):
        groups, requests = [group("first"), group("second")], []
        replies = [extraction(groups, "second"), extraction(groups, "first")]
        class Bridge(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_POST(self):
                payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                requests.append({"path": self.path, "model": payload["model"], "reasoning_effort": payload.get("reasoning_effort"),
                                 "max_tokens": payload.get("max_tokens"), "messages": payload["messages"]})
                extracts = [{item["class"]: item["text"], item["class"] + "_attributes": item["attributes"]} for item in replies]
                body = json.dumps({"id": "fixture", "object": "chat.completion", "created": 1, "model": payload["model"],
                    "choices": [{"index": 0, "message": {"role": "assistant", "content": json.dumps({"extractions": extracts}, ensure_ascii=False)},
                                 "finish_reason": "stop"}], "usage": {"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30}}, ensure_ascii=False).encode("utf-8")
                self.send_response(200); self.send_header("Content-Type", "application/json"); self.send_header("Content-Length", str(len(body)))
                self.end_headers(); self.wfile.write(body)
        server = ThreadingHTTPServer(("127.0.0.1", 0), Bridge)
        thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
        try:
            runtime = self.runtime | {"base_url": f"http://127.0.0.1:{server.server_port}/owning-run/v1"}
            result = review_definitions(groups, known(), runtime)
        finally:
            server.shutdown(); server.server_close(); thread.join(timeout=3)
        self.assertEqual([item["group_id"] for item in result["decisions"]], ["second", "first"])
        self.assertEqual(result["requests"], 1)
        self.assertEqual(len(requests), 1)
        self.assertEqual(requests[0]["path"], "/owning-run/v1/chat/completions")
        self.assertEqual(requests[0]["model"], "deepseek-flash")
        self.assertEqual(requests[0]["reasoning_effort"], "high")
        self.assertEqual(requests[0]["max_tokens"], 32768)

    def test_real_sdk_preserves_typed_length_but_does_not_retry_balance_error(self):
        seen=[];status=[422]
        class Bridge(BaseHTTPRequestHandler):
            def log_message(self,*args):pass
            def do_POST(self):
                seen.append(json.loads(self.rfile.read(int(self.headers['Content-Length']))))
                detail={"message":"structured_output_incomplete","type":"runtime_error"}
                if status[0]==422:detail.update(code="model_output_limit",stop_reason="length",request_id="fixture-real-sdk")
                body=json.dumps({"error":detail}).encode()
                self.send_response(status[0]);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
        server=ThreadingHTTPServer(('127.0.0.1',0),Bridge)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        runtime=self.runtime|{"base_url":f"http://127.0.0.1:{server.server_port}/fixture/v1"}
        try:
            with self.assertRaises(DefinitionOutputLimitError) as caught:review_definitions([group()],known(),runtime)
            self.assertEqual(caught.exception.model_attempts[0]["bridge_error"]["request_id"],"fixture-real-sdk")
            status[0]=402
            with self.assertRaises(Exception) as caught:review_definitions([group()],known(),runtime)
            self.assertNotIsInstance(caught.exception,DefinitionOutputLimitError)
        finally:server.shutdown();server.server_close();thread.join(3)
        self.assertEqual(len(seen),2)
        self.assertEqual({request['reasoning_effort'] for request in seen},{'high'})


if __name__ == "__main__":
    unittest.main()
