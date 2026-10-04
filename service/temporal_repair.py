"""Read-only source selection and additional evidence for temporal continuation.

The existing temporal transaction pipeline remains the sole model/commit path.
This module selects unfinished or changed sources and attaches document context;
it does not assign dates, write facts or decide whether a nearby table continues.
"""
from __future__ import annotations

import copy
import json


VERSION = "temporal-repair-context-0.1.0"


def select_targets(sources, prior_report):
    """Retain prior unresolved/stale/pending work plus new source fingerprints."""
    fingerprints = prior_report.get("source_fingerprints", {})
    pending = set()
    for field in ("unresolved", "stale_sources", "pending_new_sources"):
        for item in prior_report.get(field, []):
            key = item.get("source_key") if isinstance(item, dict) else item
            if isinstance(key, str):
                pending.add(key)
    return [source for source in sources if source["source_key"] in pending
            or fingerprints.get(source["source_key"]) != source["source_fingerprint"]]


def enrich_sources(db, project_id, sources):
    """Attach complete previous 2/current/next 1 pages for selected sources only.

    Each context keeps original document/page/table identities. No heading,
    financial word or model value is used to choose the date or related table.
    """
    result = copy.deepcopy(sources)
    documents, windows, table_cache = set(), {}, {}
    for source in result:
        document_id, page = source["document_id"], source.get("page")
        if document_id not in documents:
            exists = db.execute("SELECT 1 FROM documents WHERE document_id=? AND project_id=?",
                                (document_id, project_id)).fetchone()
            if not exists:
                raise ValueError("temporal_context_document_outside_project")
            documents.add(document_id)
        source["context_pages"] = []
        source["context_enrichment_version"] = VERSION
        if not isinstance(page, int) or isinstance(page, bool) or page < 1:
            continue
        window_key = (document_id, page)
        if window_key not in windows:
            window = []
            for row in db.execute("SELECT page,text FROM pages WHERE document_id=? AND page BETWEEN ? AND ? ORDER BY page",
                                  (document_id, max(1, page - 2), page + 1)):
                number, text = row[0], row[1] or ""
                table_key = (document_id, number)
                if table_key not in table_cache:
                    tables = []
                    for table in db.execute("SELECT table_id,rows_json FROM source_tables WHERE document_id=? AND page=? ORDER BY table_id",
                                            (document_id, number)):
                        rows = json.loads(table[1])
                        tables.append({"table_id": table[0], "page": number, "table_headers": rows[:6], "row_count": len(rows)})
                    table_cache[table_key] = tables
                window.append({"document_id": document_id, "page": number, "relative_page": number - page,
                               "text": text, "tables": table_cache[table_key]})
            windows[window_key] = window
        source["context_pages"] = copy.deepcopy(windows[window_key])
        current_page = next((context for context in source["context_pages"] if context["page"] == page), None)
        if current_page is not None:
            source["page_context"] = current_page["text"]
    return result
