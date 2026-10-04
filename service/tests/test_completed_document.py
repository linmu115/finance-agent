import json
import tempfile
import unittest
from pathlib import Path

from service.completed_document import completed_document
from service.core import FinanceService
from service.parser import parse_document
from service.semantic import VERSION, SCHEMA_HASH, materialize, table_batches
from service.store import dumps


class CompletedDocumentVerificationTests(unittest.TestCase):
    def test_only_fully_matching_current_materialization_skips_commits(self):
        for mutation in ("none","old_version","missing_fact","missing_batch","changed_file","changed_table","changed_value","force"):
            with self.subTest(mutation=mutation),tempfile.TemporaryDirectory() as temporary:
                root=Path(temporary);svc=FinanceService(root)
                try:
                    svc.create_project("p","Reuse")
                    path=root/"uploads"/"公司2024.csv";path.write_text("项目,2024年度\n营业收入,123\n",encoding="utf-8")
                    doc=svc.register_document("p",str(path),path.name)["data"]
                    parsed=parse_document(root/doc["relative_path"],path.name,lambda *_:None,lambda:False,{})
                    svc._persist_prepared("p",doc["document_id"],parsed);batch=table_batches(parsed)[0]
                    extracted=[{"class":"table_schema","text":"[[T0]]","span":[0,6],"attributes":{"company":"公司","statement":"income","columns_json":json.dumps([{"column":2,"period":"2024-FY","unit":"元","currency":"CNY"}])}},
                               {"class":"financial_row","text":"[[T0:R2]]","span":[7,17],"attributes":{"metric":"revenue","label":"营业收入"}}]
                    facts,issues=materialize(extracted,batch,doc["document_id"],"deepseek-flash")
                    detail={"version":VERSION,"schema_hash":SCHEMA_HASH,"model":"deepseek-flash","extractions":extracted,"fact_count":999,"issues":[{"reason":"old_summary"}]}
                    svc._commit_semantic_batch("p",doc["document_id"],"original-owner",batch,facts,issues,detail)
                    with svc.store.connect(write=True) as db:
                        db.execute("UPDATE documents SET state='failed' WHERE document_id=?",(doc["document_id"],))
                        if mutation=="old_version":db.execute("UPDATE normalization_batches SET result_json=json_set(result_json,'$.version','older-version')")
                        elif mutation=="missing_fact":db.execute("DELETE FROM facts")
                        elif mutation=="missing_batch":db.execute("DELETE FROM normalization_batches")
                        elif mutation=="changed_table":db.execute("UPDATE source_tables SET rows_json=?",(dumps([["项目","2024年度"],["营业收入","999"]]),))
                        elif mutation=="changed_value":db.execute("UPDATE facts SET value='999'")
                        if mutation=="none":
                            saved=json.loads(db.execute("SELECT result_json FROM normalization_batches").fetchone()[0])
                            self.assertEqual(saved["fact_count"],1);self.assertEqual(saved["issues"],[])
                    if mutation=="changed_file":(root/doc["relative_path"]).write_text("changed upload",encoding="utf-8")
                    result=completed_document(svc,"p",doc,{"model":"deepseek-flash","force":mutation=="force"})
                    if mutation=="none":
                        self.assertEqual(result["normalization"]["reused_committed_batches"],1);self.assertTrue(result["normalization"]["skipped_materialization"])
                        self.assertEqual(result["coverage"]["batches_completed"],1)
                    else:self.assertIsNone(result)
                finally:
                    for pool in (svc.processing_pool,svc.pool,svc.analysis_pool,svc.embedding_pool):pool.shutdown(wait=True,cancel_futures=True)


if __name__=="__main__":unittest.main()
