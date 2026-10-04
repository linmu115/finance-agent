"""Verify a previous Pi output limit before reusing only its scheduling fact.

This module never infers financial meaning, publishes model results, edits an
old report, or charges a historical request to a new run. Missing or changed
evidence makes a past failure ineligible; exception messages are not evidence.
"""
from __future__ import annotations

import hashlib
import json
import re

from .review_cache import result_hash

VERSION = "verified-historical-output-limit-1"
_ID = re.compile(r"[A-Za-z0-9_-]{1,128}")


def expected_messages(groups, known):
    """Pure SDK prompt formatting, including instructions and examples."""
    from langextract.prompting import PromptTemplateStructured, QAPromptGenerator
    from langextract.core.format_handler import FormatHandler
    from langextract.core.data import FormatType
    from .definition_model import PROMPT, _examples, _render
    text = _render(groups, known)
    prompt = QAPromptGenerator(PromptTemplateStructured(PROMPT, _examples()),
        FormatHandler(format_type=FormatType.JSON, use_wrapper=True, use_fences=False)).render(text)
    messages = [{"role": "system", "content": "You are a helpful assistant that responds in JSON format."},
                {"role": "user", "content": prompt}]
    return text, messages


def historical_output_limit(store, project_id, cache_key, groups, known, runtime, source_fingerprints):
    """Return verified historical limit evidence, or None; strictly read-only."""
    from .definition_model import INFERENCE_CONFIG
    if runtime.get("force") or not source_fingerprints:
        return None
    ids = [group["group_id"] for group in groups]
    with store.connect() as db:
        # An accepted result always takes precedence over any previous failure.
        if db.execute("SELECT 1 FROM fact_definition_cache WHERE cache_key=?", (cache_key,)).fetchone():
            return None
        reports = [json.loads(row[0]) for row in db.execute(
            "SELECT report_json FROM fact_definition_reviews WHERE project_id=? ORDER BY created_at DESC", (project_id,))]
    candidates = [report for report in reports if report.get("completed_at") and report.get("model") == runtime["model"]
                  and any(item.get("cache_key") == cache_key and item.get("group_ids") == ids
                          for item in report.get("failures", []) + report.get("split_attempts", []))
                  and all(report.get("source_fingerprints", {}).get(key) == value for key, value in source_fingerprints.items())]
    if not candidates:
        return None
    text, messages = expected_messages(groups, known)
    max_tokens = int(runtime.get("max_tokens") or 32768)
    for report in candidates:
        owner, processing = report.get("owner_run_id"), report.get("processing_id")
        if not isinstance(owner, str) or not _ID.fullmatch(owner) or not isinstance(processing, str):
            continue
        audit = store.root / "audit" / (owner + ".jsonl")
        try:
            raw = audit.read_bytes()
            events = [json.loads(line) for line in raw.decode("utf-8").splitlines() if line.strip()]
        except (OSError, UnicodeError, json.JSONDecodeError):
            continue
        own = [event for event in events if isinstance(event, dict) and event.get("runId") == owner
               and event.get("projectId") == project_id and isinstance(event.get("data"), dict)]
        if not any(event.get("type") == "processing_started" and event["data"].get("ownerRunId") == owner
                   and event["data"].get("processingId") == processing for event in own):
            continue
        for position, event in enumerate(own):
            request = event["data"]
            if (event.get("type") != "extraction_request" or request.get("ownerRunId") != owner
                    or request.get("model") != runtime["model"] or request.get("reasoningEffort") != INFERENCE_CONFIG["reasoning_effort"]
                    or request.get("maxTokens") != max_tokens or request.get("messages") != messages):
                continue
            request_id = request.get("requestId")
            if not isinstance(request_id, str) or not _ID.fullmatch(request_id):
                continue
            starts = [item["data"] for item in own[:position] if item.get("type") == "processing_started"]
            if not starts or starts[-1].get("processingId") != processing or starts[-1].get("ownerRunId") != owner:
                continue
            if sum(item.get("type") == "extraction_request" and item["data"].get("requestId") == request_id for item in own) != 1:
                continue
            results = [item for item in own if item.get("type") == "extraction_result"
                       and item["data"].get("requestId") == request_id]
            if len(results) != 1:
                continue
            result = results[0]["data"]
            if (result.get("ownerRunId") != owner or result.get("model") != runtime["model"]
                    or result.get("stopReason") != "length"):
                continue
            return {"kind": "verified_historical_output_limit", "policy_version": VERSION,
                    "cache_key": cache_key, "group_ids": ids, "original_review_id": report["review_id"],
                    "original_owner_run_id": owner, "original_processing_id": processing,
                    "original_request_id": request_id, "audit_sha256": hashlib.sha256(raw).hexdigest(),
                    "input_hash": hashlib.sha256(text.encode("utf-8")).hexdigest(), "messages_hash": result_hash(messages),
                    "source_fingerprints": dict(source_fingerprints), "model": runtime["model"],
                    "reasoning_effort": INFERENCE_CONFIG["reasoning_effort"], "max_tokens": max_tokens,
                    "stop_reason": "length", "historical_usage": result.get("usage"), "current_model_requests": 0}
    return None
