"""Locate model quotations in their own source group, with reversible offsets.

Only whitespace can be normalized. No punctuation, words, numbers or qualifiers
are changed. A corrected locator must have exactly one candidate; financial
meaning remains the model's decision, not a rule in this module.
"""
from __future__ import annotations

VERSION = "definition-quote-location-1"


def _matches(text, quote, whitespace=False):
    if whitespace:
        offsets = [i for i, char in enumerate(text) if not char.isspace()]
        haystack = "".join(text[i] for i in offsets)
        needle = "".join(char for char in quote if not char.isspace())
    else:
        haystack, needle, offsets = text, quote, None
    if not needle:
        return []
    matches, start = [], 0
    while True:
        found = haystack.find(needle, start)
        if found < 0:
            return matches
        end = found + len(needle)
        matches.append((offsets[found], offsets[end - 1] + 1) if offsets is not None else (found, end))
        start = found + 1


def locate_quote(quote, evidence):
    """Return an exact grounded quote and optional explicit locator correction."""
    if (not isinstance(quote, dict) or set(quote) != {"evidence_id", "text"}
            or not isinstance(quote["evidence_id"], str)
            or not isinstance(quote["text"], str) or not quote["text"].strip()):
        return None, None, "definition_invalid_quote_shape"
    own = {item["evidence_id"]: item["text"] for item in evidence}
    original_id, original_text = quote["evidence_id"], quote["text"]
    if original_id in own and original_text in own[original_id]:
        return dict(quote), None, None

    # An existing ID still identifies its own block if only PDF whitespace
    # differs. Multiple occurrences within that block cannot be located safely.
    if original_id in own:
        matches = _matches(own[original_id], original_text, whitespace=True)
        if len(matches) > 1:
            return None, None, "definition_ambiguous_quote_location"
        candidates = [(original_id, *span) for span in matches]
    else:
        candidates = []
    method = "whitespace_within_evidence"
    if not candidates:
        for whitespace in (False, True):
            candidates = [(identity, *span) for identity, text in own.items()
                          for span in _matches(text, original_text, whitespace)]
            method = "unique_group_whitespace" if whitespace else "unique_group_exact"
            if candidates:
                break
    if len(candidates) != 1:
        reason = "definition_ambiguous_quote_location" if candidates else "definition_quote_not_in_group_evidence"
        return None, None, reason
    identity, start, end = candidates[0]
    grounded = {"evidence_id": identity, "text": own[identity][start:end]}
    audit = {"version": VERSION, "method": method, "original_quote": dict(quote),
             "grounded_quote": grounded, "span": [start, end], "offset_unit": "python_unicode_codepoint"}
    return grounded, audit, None
