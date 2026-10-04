"""Compare complete persisted page/table content to the aborted run's successful parse."""
import argparse
import hashlib
import json
from pathlib import Path
import sqlite3


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()


def read_database(path):
    with sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True) as db:
        db.row_factory = sqlite3.Row
        documents = [dict(r) for r in db.execute("SELECT document_id,original_name,sha256,state,page_count,parser_version FROM documents")]
        jobs = [dict(r) for r in db.execute("SELECT job_id,document_id,state,error FROM jobs")]
        pages = [dict(r) for r in db.execute("SELECT page,text,printed_page,width,height,ocr FROM pages ORDER BY page")]
        tables = []
        for r in db.execute("SELECT table_id,page,sheet,bbox_json,rows_json,cells_json FROM source_tables"):
            tables.append({"index": int(r["table_id"].rsplit(":t", 1)[1]), "page": r["page"], "sheet": r["sheet"],
                           **{key: json.loads(r[key + "_json"]) for key in ("bbox", "rows", "cells")}})
        tables.sort(key=lambda item: item["index"])
    return {"path": str(path), "documents": documents, "jobs": jobs, "pages": len(pages), "tables": len(tables),
            "page_numbers": [p["page"] for p in pages], "pages_sha256": digest(pages), "tables_sha256": digest(tables)}


def main():
    options = argparse.ArgumentParser()
    options.add_argument("--original-run", type=Path, required=True)
    options.add_argument("--regression", type=Path, nargs="+", required=True)
    options.add_argument("--output", type=Path, required=True)
    args = options.parse_args()
    old = [read_database(path) for path in args.original_run.glob("round-1/midea*/data/finance.sqlite")]
    successful = [item for item in old if item["pages"] == 295 and all(d["state"] in {"ready", "needs_review"} for d in item["documents"])]
    if not successful:
        raise SystemExit("No successful original full source to compare")
    reference = successful[0]
    # OCR-image cases share the source-id prefix but are separate one-page assets.
    old = [item for item in old if all(d["sha256"] == reference["documents"][0]["sha256"] for d in item["documents"])]
    new = [read_database(path) for folder in args.regression for path in folder.glob("worker-*/data/finance.sqlite")]
    for item in successful + new:
        item["matches_reference"] = (item["pages_sha256"] == reference["pages_sha256"] and item["tables_sha256"] == reference["tables_sha256"]
                                      and item["page_numbers"] == list(range(1, 296))
                                      and all(d["sha256"] == reference["documents"][0]["sha256"] for d in item["documents"]))
    report = {"original_failures": [item for item in old if item["pages"] != 295], "original_successes": successful,
              "new_regressions": new, "compared_fields": ["every page: number,text,printed_page,width,height,ocr", "every table: index,page,sheet,bbox,rows,cells"],
              "all_content_equal": bool(new) and all(item["matches_reference"] for item in successful + new),
              "root_cause": "Original intermittent ResizeImgError not reproduced; original service retained only class name, so its underlying cause is unavailable.",
              "changes": ["OpenCV threads=1; each OCR ONNX session intra/inter threads=1", "Shared OCR engine lock", "Release Pixmap before PIL/NumPy copies", "Persist local OCR cause chain, traceback and page on failure; no swallowed errors or skipped pages"],
              "not_a_model_benchmark": True}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"original_failures": len(report["original_failures"]), "original_successes": len(successful), "regressions": len(new), "all_content_equal": report["all_content_equal"]}))
    return 0 if report["all_content_equal"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
