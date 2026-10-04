"""Specify only four known rejected cells from original source/extraction, never final facts."""
import hashlib
import json
from pathlib import Path
import sqlite3

root = Path(__file__).resolve().parents[1]
before = json.loads((root / "benchmark/results/pi-full-report-v03-before-temporal-facts.json").read_text(encoding="utf-8"))
document = "39de9b118212463bbee6c2ab3c571432"
table = document + ":t155"
with sqlite3.connect((root / "data/finance.sqlite").as_uri() + "?mode=ro", uri=True) as connection:
    page, raw_rows = connection.execute("SELECT page,rows_json FROM source_tables WHERE table_id=?", (table,)).fetchone()
    batch_key, owner, raw_batch = connection.execute("SELECT batch_key,processing_id,result_json FROM normalization_batches WHERE document_id=? AND result_json LIKE '%[[T155:R6]]%'", (document,)).fetchone()
rows, batch = json.loads(raw_rows), json.loads(raw_batch)
assert page == 97
schema = next(e for e in batch["extractions"] if e["text"] == "[[T155]]")["attributes"]
assert schema["currency"] == "CNY" and schema["unit"] == "元"
facts, evidence = [], []
for row, raw_value in [(6, "4,665,316.93"), (16, "462,005.27")]:
    extraction = next(e for e in batch["extractions"] if e["text"] == f"[[T155:R{row}]]")
    attrs = extraction["attributes"]
    assert 96 < len(attrs["metric"]) <= 256
    columns = json.loads(attrs["columns_json"])
    for col, letter in [(2, "B"), (5, "E")]:
        assert rows[row - 1][col - 1] == raw_value
        assert not any(f["source_ref"]["table_id"] == table and f["source_ref"]["row"] == row and f["source_ref"]["column"] == col for f in before["facts"])
        column = next(c for c in columns if c["column"] == col)
        assert column["currency"] == "CNY" and column["unit"] == "元"
        facts.append({"company": schema["company"], "metric": attrs["metric"], "original_metric": attrs["metric"],
                      "scope": schema["scope"], "currency": "CNY", "value": raw_value.replace(",", ""),
                      "raw_value": raw_value, "raw_unit": "元", "normalized_unit": "CNY", "restatement": "original",
                      "period": column["period"], "period_start": column["start"], "period_end": column["end"], "year": 2024,
                      "dimensions": column["dimensions"], "source_ref": {"document_id": document, "table_id": table,
                      "page": page, "row": row, "column": col, "cell": letter + str(row), "text": " | ".join(rows[row - 1])}})
    evidence.append({"source_row": row, "row_cells": rows[row - 1], "original_extraction": extraction})
result = {"project_id": before["project_id"], "before_facts_sha256": before["facts_sha256"],
          "scope": "Exactly four source cells rejected by the former 96-character metric-ID limit. No other new fact is allowed; all original 3294 facts must retain their source and amount.",
          "evidence_source": "host_sqlite_readonly_original_source_tables_and_normalization_batches_not_after_facts",
          "source_table_sha256": hashlib.sha256(raw_rows.encode()).hexdigest(), "batch_key": batch_key,
          "batch_sha256": hashlib.sha256(raw_batch.encode()).hexdigest(), "original_extraction_processing_id": batch.get("extraction_processing_id", owner),
          "source_page": page, "source_header": rows[0], "original_extraction_evidence": evidence, "facts": facts}
output = root / "benchmark/results/pi-full-report-v03-four-recovered-facts-allowlist.json"
with output.open("x", encoding="utf-8") as handle:
    json.dump(result, handle, ensure_ascii=False, indent=2)
print(json.dumps({"output": str(output), "expected_additions": len(facts), "cells": [f["source_ref"]["cell"] for f in facts]}, ensure_ascii=False))
