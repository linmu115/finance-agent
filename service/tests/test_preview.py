import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from service.core import FinanceService


class IsolatedPdfPreviewTests(unittest.TestCase):
    def test_parallel_pdf_previews_publish_complete_images(self):
        import fitz
        from PIL import Image
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);svc=FinanceService(root);svc.create_project("p","PDF preview")
            try:
                upload=root/"uploads"/"pages.pdf"
                with fitz.open() as pdf:
                    for index in range(2):pdf.new_page().insert_text((72,72),f"Page {index+1}")
                    pdf.save(upload)
                document=svc.register_document("p",str(upload),upload.name)["data"]
                svc._persist_prepared("p",document["document_id"],{"company":"Test","report_year":2024,"pages":[{"page":i+1,"text":f"Page {i+1}"} for i in range(2)],"tables":[],"warnings":[]})
                with ThreadPoolExecutor(max_workers=3) as pool:
                    futures=[pool.submit(svc.get_source_page,"p",document["document_id"],page) for page in (1,2,1)]
                    results=[future.result(timeout=45)["data"] for future in futures]
                for result in results:
                    image_path=root/result["image_relative_path"]
                    with Image.open(image_path) as image:
                        image.verify()
                    self.assertGreater(image_path.stat().st_size,1000)
                self.assertEqual(results[0]["image_relative_path"],results[2]["image_relative_path"])
                self.assertEqual(list((root/"artifacts"/"p"/document["document_id"]).glob("page-*.*.png")),[])
            finally:
                for pool in (svc.processing_pool,svc.pool,svc.analysis_pool,svc.embedding_pool):pool.shutdown(wait=True,cancel_futures=True)


if __name__=="__main__":unittest.main()
