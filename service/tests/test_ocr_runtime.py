"""Bounded local OCR execution and failure persistence, without network/model downloads."""
import io
import json
from pathlib import Path
import tempfile
import threading
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

from PIL import Image
import cv2
import fitz
import numpy as np
from rapidocr_onnxruntime.ch_ppocr_det.utils import DetPreProcess, ResizeImgError
from service import parser
from service.core import FinanceService


class OCRRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.previous_engine = getattr(parser, "_OCR_ENGINE", None)
        if hasattr(parser, "_OCR_ENGINE"):
            del parser._OCR_ENGINE
        self.previous_threads = cv2.getNumThreads()
        buf = io.BytesIO()
        Image.new("RGB", (64, 64), "white").save(buf, format="PNG")
        self.png = buf.getvalue()

    def tearDown(self):
        if self.previous_engine is None:
            if hasattr(parser, "_OCR_ENGINE"):
                del parser._OCR_ENGINE
        else:
            parser._OCR_ENGINE = self.previous_engine
        cv2.setNumThreads(self.previous_threads)

    def test_shared_engine_is_serialized_and_all_native_pools_are_bounded(self):
        active = 0
        peak = 0
        guard = threading.Lock()
        def engine(image):
            nonlocal active, peak
            with guard:
                active += 1
                peak = max(peak, active)
            time.sleep(.02)
            with guard:
                active -= 1
            return None, None
        with patch("rapidocr_onnxruntime.RapidOCR", return_value=engine) as factory:
            with ThreadPoolExecutor(max_workers=4) as pool:
                results = list(pool.map(lambda _: parser.ocr_image(self.png, {}), range(4)))
        self.assertEqual(results, [("", [], [])] * 4)
        self.assertEqual(peak, 1)
        self.assertEqual(cv2.getNumThreads(), 1)
        factory.assert_called_once_with(det_use_cuda=False, cls_use_cuda=False, rec_use_cuda=False,
                                        intra_op_num_threads=1, inter_op_num_threads=1)

    def test_pdf_error_keeps_real_resize_cause_page_and_failed_job(self):
        # Exercise the installed OpenCV error and installed RapidOCR wrapper.
        # Only engine inference is substituted; this is explicitly a fault-injection test.
        def broken_engine(image):
            with patch("cv2.resize", side_effect=lambda *a, **kw: real_resize(np.empty((0, 0, 3), dtype=np.uint8), (32, 32))):
                DetPreProcess().resize(image)
        real_resize = cv2.resize
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            service = FinanceService(root)
            try:
                service.create_project("ocr", "OCR failure regression")
                source = root / "uploads" / "blank.pdf"
                with fitz.open() as pdf:
                    pdf.new_page(width=64, height=64)
                    pdf.save(source)
                service.configs["ocr"] = {"ocr": {"mode": "local", "api_key": "never-record-this-test-secret"}}
                with patch("rapidocr_onnxruntime.RapidOCR", return_value=broken_engine):
                    incoming = service.ingest_document("ocr", str(source), source.name)["data"]
                    service.pool.shutdown(wait=True)
                state = service.get_ingestion_status("ocr", incoming["job_id"])["data"]
                self.assertEqual(state["state"], "failed")
                self.assertEqual(state["error"], "ResizeImgError")
                document = service.get_document("ocr", incoming["document_id"])["data"]
                self.assertEqual(document["state"], "failed")
                self.assertEqual(document["page_count"], 0)
                self.assertEqual(document["table_count"], 0)
                diagnostic_path = root / "diagnostics" / ("ingestion-" + incoming["job_id"] + ".json")
                raw = diagnostic_path.read_text(encoding="utf-8")
                self.assertNotIn("never-record-this-test-secret", raw)
                diagnostic = json.loads(raw)
                self.assertEqual(diagnostic["page"], 1)
                self.assertEqual(diagnostic["image_shape"], [128, 128, 3])
                self.assertIn("ResizeImgError", diagnostic["causes"][0]["type"])
                self.assertEqual(diagnostic["causes"][1]["opencv"]["code"], -215)
                self.assertIn("cv2.error", diagnostic["traceback"])
                self.assertIn("direct cause", diagnostic["traceback"])
            finally:
                service.pool.shutdown(wait=True)
                service.analysis_pool.shutdown(wait=True)
                service.embedding_pool.shutdown(wait=True)


if __name__ == "__main__":
    unittest.main()
