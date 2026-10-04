"""Real four-process full-PDF regression; no LLM, labels, or cached parse results."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import traceback

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


def worker(source, output, start_at, threaded, service_mode):
    from service import parser
    import cv2
    record = {"pid": os.getpid(), "source": str(source), "sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
              "parser_version": parser.PARSER_VERSION, "opencv_threads_before": cv2.getNumThreads(), "ocr_calls": [], "threaded": threaded,
              "service_mode": service_mode}
    started = time.monotonic()
    last_page = 0
    original_ocr = parser.ocr_image
    original_resize = cv2.resize
    def observed_resize(image, size, *args, **kwargs):
        try:
            return original_resize(image, size, *args, **kwargs)
        except Exception:
            record["resize_failure"] = {"input_shape": list(image.shape), "dtype": str(image.dtype), "output_size": list(size),
                                        "opencv_threads": cv2.getNumThreads(), "traceback": traceback.format_exc()}
            raise
    cv2.resize = observed_resize
    def observed_ocr(image_bytes, config):
        from PIL import Image
        import io
        with Image.open(io.BytesIO(image_bytes)) as image:
            record["ocr_calls"].append({"page": last_page + 1, "size": list(image.size), "mode": image.mode})
        return original_ocr(image_bytes, config)
    parser.ocr_image = observed_ocr
    def progress(fraction, message):
        nonlocal last_page
        last_page += 1
        if last_page % 25 == 0:
            print(json.dumps({"pid": os.getpid(), "page": last_page}), flush=True)
    while time.time() < start_at:
        time.sleep(.05)
    try:
        if service_mode:
            import shutil
            from service import core
            os.environ["FINANCE_DATA_DIR"] = str(output.parent / output.stem / "data")
            from service.server import service
            captured = {}
            def observed_parse(path, name, original_progress, cancelled, config):
                def both_progress(fraction, message):
                    progress(fraction, message)
                    original_progress(fraction, message)
                try:
                    result = parser.parse_document(path, name, both_progress, cancelled, config)
                    captured["parsed"] = result
                    return result
                except Exception:
                    captured["traceback"] = traceback.format_exc()
                    raise
            core.parse_document = observed_parse
            service.create_project("regression", "Concurrent complete source regression")
            target = service.store.root / "uploads" / source.name
            shutil.copyfile(source, target)
            job = service.ingest_document("regression", str(target), source.name)["data"]
            deadline = time.monotonic() + 300
            while time.monotonic() < deadline:
                state = service.get_ingestion_status("regression", job["job_id"])["data"]
                if state["state"] in {"ready", "needs_review", "failed", "cancelled"}:
                    break
                time.sleep(.1)
            service.pool.shutdown(wait=True)
            service.analysis_pool.shutdown(wait=True)
            service.embedding_pool.shutdown(wait=True)
            record["ingestion_state"] = state
            record["document"] = service.get_document("regression", job["document_id"])["data"]
            if "traceback" in captured:
                record["service_traceback"] = captured["traceback"]
            if state["state"] not in {"ready", "needs_review"}:
                raise RuntimeError("real_service_ingestion_failed")
            parsed = captured["parsed"]
        elif threaded:
            from concurrent.futures import ThreadPoolExecutor
            with ThreadPoolExecutor(max_workers=1, thread_name_prefix="document-parser") as pool:
                parsed = pool.submit(parser.parse_document, source, source.name, progress, lambda: False, {}).result()
        else:
            parsed = parser.parse_document(source, source.name, progress, lambda: False, {})
        facts = parser.extract_facts(parsed, "regression-document")
        record.update(status="passed", page_count=len(parsed["pages"]),
                      page_numbers=[p["page"] for p in parsed["pages"]], table_count=len(parsed["tables"]),
                      text_sha256=hashlib.sha256(json.dumps(parsed["pages"], sort_keys=True, ensure_ascii=False).encode()).hexdigest(),
                      page_text_sha256=hashlib.sha256(json.dumps([[p["page"],p["text"]] for p in parsed["pages"]], ensure_ascii=False).encode()).hexdigest(),
                      tables_sha256=hashlib.sha256(json.dumps(parsed["tables"], sort_keys=True, ensure_ascii=False).encode()).hexdigest(),
                      facts_sha256=hashlib.sha256(json.dumps(facts, sort_keys=True, ensure_ascii=False).encode()).hexdigest(),
                      fact_count=len(facts), warnings=parsed["warnings"])
    except Exception:
        record.update(status="failed", last_completed_page=last_page, traceback=traceback.format_exc())
    finally:
        record["elapsed_seconds"] = round(time.monotonic() - started, 3)
        record["opencv_threads_after"] = cv2.getNumThreads()
        engine = getattr(parser, "_OCR_ENGINE", None)
        if engine:
            record["onnx_threads"] = {}
            for component in ("text_det", "text_cls", "text_rec"):
                part = getattr(engine, component, None)
                session = getattr(part, "infer", None) or getattr(part, "session", None)
                if session and hasattr(session, "session"):
                    options = session.session.get_session_options()
                    record["onnx_threads"][component] = {"intra": options.intra_op_num_threads, "inter": options.inter_op_num_threads}
        output.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0 if record["status"] == "passed" else 1


def main():
    args = argparse.ArgumentParser()
    args.add_argument("--source", type=Path, default=ROOT / "benchmark/agent_input/reports/midea_2024.pdf")
    args.add_argument("--output", type=Path, required=True)
    args.add_argument("--workers", type=int, default=4)
    args.add_argument("--worker", action="store_true")
    args.add_argument("--threaded", action="store_true")
    args.add_argument("--minimal-env", action="store_true")
    args.add_argument("--service-mode", action="store_true")
    args.add_argument("--start-at", type=float, default=0)
    options = args.parse_args()
    if options.worker:
        return worker(options.source, options.output, options.start_at, options.threaded, options.service_mode)
    options.output.mkdir(parents=True, exist_ok=False)
    processes = []
    start_at = time.time() + 8
    child_env = dict(os.environ)
    if options.minimal_env:
        essentials = {"PATH", "SYSTEMROOT", "WINDIR", "TEMP", "TMP", "USERPROFILE", "LOCALAPPDATA", "APPDATA"}
        child_env = {k: v for k, v in os.environ.items() if k.upper() in essentials}
        child_env.update(PYTHONPATH=str(ROOT), PYTHONIOENCODING="utf-8", PYTHONUNBUFFERED="1")
    for index in range(options.workers):
        logfile = (options.output / f"worker-{index}.log").open("w", encoding="utf-8")
        process = subprocess.Popen([sys.executable, str(Path(__file__).resolve()), "--worker", "--source", str(options.source),
                                    "--output", str(options.output / f"worker-{index}.json"), "--start-at", str(start_at)]
                                   + (["--threaded"] if options.threaded else []) + (["--service-mode"] if options.service_mode else []),
                                   cwd=ROOT, env=child_env, stdout=logfile, stderr=subprocess.STDOUT)
        processes.append((process, logfile))
    exits = []
    for process, logfile in processes:
        exits.append(process.wait())
        logfile.close()
    records = [json.loads((options.output / f"worker-{i}.json").read_text(encoding="utf-8")) for i in range(options.workers)]
    summary = {"workers": options.workers, "exit_codes": exits, "all_passed": all(r["status"] == "passed" for r in records),
               "records": records}
    (options.output / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"workers": options.workers, "exit_codes": exits, "all_passed": summary["all_passed"]}))
    return 0 if summary["all_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
