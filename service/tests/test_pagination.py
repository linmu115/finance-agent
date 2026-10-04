import json
import tempfile
import unittest
from pathlib import Path

from service.core import FinanceService


class BoundedFinancialPagesTests(unittest.TestCase):
    def test_large_requested_pages_can_traverse_every_fact_and_mapping(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);service=FinanceService(root)
            try:
                service.create_project("p","Pagination")
                upload=root/"uploads"/"sample.csv";upload.write_text("项目,金额\n资产,1\n",encoding="utf-8")
                document=service.register_document("p",str(upload),upload.name)["data"]
                document_id=document["document_id"]
                with service.store.connect(write=True) as db:
                    for index in range(405):
                        source=json.dumps({"document_id":document_id,"page":1,"row":index+1,"column":2,"text":"完整原始证据"*200,"normalization":{"label":"资产总计","statement":"balance"}},ensure_ascii=False)
                        db.execute("INSERT INTO facts VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",(f"fact-{index}",document_id,"p","公司","assets",2024,"2024-12-31","consolidated_CAS","CNY","1","元","1",source,1,"verified"))
                    for index in range(25):
                        db.execute("INSERT INTO normalization_batches VALUES(?,?,?,?,?)",(document_id,f"batch-{index}","original-owner",json.dumps({"fact_count":1,"issues":[],"extractions":[]}),f"2026-10-03T00:00:{index:02d}Z"))
                seen=[];offset=0;page_sizes=[]
                while True:
                    response=service.query_financial_data("p",limit=10000,offset=offset)
                    page=response["data"]
                    self.assertEqual(page["limit"],200);self.assertEqual(page["offset"],offset);self.assertEqual(page["total"],405)
                    self.assertLess(len(json.dumps(response,ensure_ascii=False).encode("utf-8")),10*1024*1024)
                    page_sizes.append(len(page["items"]));seen.extend(item["fact_id"] for item in page["items"])
                    offset+=len(page["items"])
                    if offset>=page["total"]:break
                self.assertEqual(page_sizes,[200,200,5]);self.assertEqual(len(set(seen)),405)
                dashboard=service.get_dashboard("p")["data"]
                self.assertEqual((dashboard["limit"],len(dashboard["facts"]),dashboard["total"]),(200,200,405));self.assertTrue(dashboard["truncated"])
                first=service.get_normalization_details("p",document_id,limit=10000)["data"]
                second=service.get_normalization_details("p",document_id,limit=10000,offset=len(first["batches"]))["data"]
                self.assertEqual((first["limit"],first["total"],len(first["batches"])),(20,25,20))
                self.assertEqual((second["limit"],second["offset"],len(second["batches"])),(20,20,5))
                self.assertEqual(len({batch["batch_key"] for batch in first["batches"]+second["batches"]}),25)
            finally:
                for pool in (service.processing_pool,service.pool,service.analysis_pool,service.embedding_pool):pool.shutdown(wait=True,cancel_futures=True)


if __name__=="__main__":unittest.main()
