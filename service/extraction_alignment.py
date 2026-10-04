"""Locate unique literal source markers without imposing extraction order."""
from __future__ import annotations

import re

ALIGNMENT_VERSION = "unique-exact-marker-1"


def align_unique_markers(extractions, text, marker_pattern):
    """Return copies with original SDK spans and independently verified spans.

    Model classes, marker text and attributes are unchanged. An absent,
    ambiguous or malformed marker is explicitly ungrounded for the caller's
    existing validation to reject.
    """
    pattern = re.compile(marker_pattern)
    aligned = []
    for extraction in extractions:
        if not isinstance(extraction, dict):
            aligned.append(extraction)
            continue
        item = dict(extraction)
        item["sdk_span"] = extraction.get("sdk_span", extraction.get("span"))
        marker = item.get("text")
        occurrences = text.count(marker) if isinstance(marker, str) and pattern.fullmatch(marker) else 0
        if occurrences == 1:
            start = text.index(marker)
            item["span"] = [start, start + len(marker)]
        else:
            item["span"] = None
        item["alignment"] = {"method": ALIGNMENT_VERSION, "literal_occurrences": occurrences}
        aligned.append(item)
    return aligned
