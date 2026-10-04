import copy
import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from service.completed_document import completed_document
from service.core import FinanceService
from service.parser import PARSER_VERSION
from service.semantic import SCHEMA_HASH, VERSION, materialize, normalize_document, table_batches
from service.tests.test_semantic_sources import mappings


class PreparedSourceMigrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        self.svc=FinanceService(self.root);self.svc.create_project("p","Migration")
        path=self.root/"uploads"/"source2024.csv";path.write_text("项目,本期\n资产,137\n",encoding="utf-8")
        self.doc=self.svc.register_document("p",str(path),path.name)["data"];self.did=self.doc["document_id"]
        self.parsed={"company":"公司","report_year":2024,"warnings":[],"kind":".csv",
                     "pages":[{"page":1,"text":"company report 2024","ocr":False}],
                     "tables":[{"index":0,"page":1,"rows":[["项目","本期"],["资产","137"]],"cells":{"B2":{"bbox":[30,40,50,60]}}}]}
        self.svc._persist_prepared("p",self.did,self.parsed)
        self.batch=table_batches(self.parsed)[0];self.ex=mappings(0,2)
        facts,issues=materialize(self.ex,self.batch,self.did,"fixture")
        self.detail={"version":VERSION,"schema_hash":SCHEMA_HASH,"model":"fixture","extractions":self.ex}
        self.svc._commit_semantic_batch("p",self.did,"original-owner",self.batch,facts,issues,self.detail)

    def tearDown(self):
        for pool in (self.svc.processing_pool,self.svc.pool,self.svc.analysis_pool,self.svc.embedding_pool):pool.shutdown(wait=True,cancel_futures=True)
        self.tmp.cleanup()

    def rows(self, table):
        with self.svc.store.connect() as db:return [dict(row) for row in db.execute("SELECT * FROM "+table)]

    def test_table_index_reorder_archives_old_fact_source_and_mapping_together(self):
        before=self.rows("facts")[0];old_file=self.svc._prepared_path("p",self.did).read_text(encoding="utf-8")
        changed=copy.deepcopy(self.parsed)
        changed["tables"]=[{"index":0,"page":1,"rows":[["新增源表","本期"],["费用","91"]],"cells":{}},
                           dict(changed["tables"][0],index=1)]
        self.svc._persist_prepared("p",self.did,changed)
        self.assertEqual(self.rows("facts"),[]);self.assertEqual(self.rows("normalization_batches"),[])
        history=self.rows("fact_history");self.assertEqual(json.loads(history[0]["fact_json"]),before)
        snapshot=self.rows("source_parse_history")[0]
        self.assertEqual(history[0]["processing_id"],snapshot["snapshot_id"])
        saved=json.loads(snapshot["source_json"])
        self.assertEqual(saved["prepared_file"],old_file)
        self.assertEqual(saved["prepared"],self.parsed)
        self.assertEqual(json.loads(saved["source_tables"][0]["rows_json"]),self.parsed["tables"][0]["rows"])
        self.assertEqual(len(saved["normalization_batches"]),1)
        self.assertEqual(self.svc._read_prepared("p",self.doc),changed)
        self.assertEqual((self.root/self.doc["relative_path"]).read_text(encoding="utf-8"),"项目,本期\n资产,137\n")

    def test_source_index_write_failure_rolls_back_every_live_and_history_table(self):
        tables=["facts","source_tables","pages","normalization_batches","prepared_documents","fact_history","source_parse_history"]
        before={table:self.rows(table) for table in tables}
        old_file=self.svc._prepared_path("p",self.did).read_bytes()
        changed=copy.deepcopy(self.parsed);changed["tables"][0]["rows"][1][1]="999"
        with patch.object(self.svc,"_insert_chunk",side_effect=RuntimeError("fixture publication failure")):
            with self.assertRaises(RuntimeError):self.svc._persist_prepared("p",self.did,changed)
        self.assertEqual({table:self.rows(table) for table in tables},before)
        self.assertEqual(self.svc._prepared_path("p",self.did).read_bytes(),old_file)

    def test_invalid_parse_before_transaction_leaves_old_data_untouched(self):
        before=self.rows("facts");sources=self.rows("source_tables")
        with self.assertRaises((KeyError,TypeError)):self.svc._persist_prepared("p",self.did,{"tables":None})
        self.assertEqual(self.rows("facts"),before);self.assertEqual(self.rows("source_tables"),sources)

    def test_parser_exception_keeps_old_sources_and_active_facts(self):
        before={table:self.rows(table) for table in ("facts","source_tables","pages","normalization_batches","prepared_documents")}
        runtime={"base_url":"http://127.0.0.1:1/fixture/v1","api_key":"fixture","model":"fixture"}
        with patch("service.processing.PARSER_VERSION","next-parser"),patch("service.processing.parse_document",side_effect=ValueError("fixture_parser_failed")):
            run=self.svc.start_document_processing("p",[self.did],"failed-parse",runtime)["data"]["processing_id"]
            deadline=time.monotonic()+5
            while time.monotonic()<deadline:
                state=self.svc.get_processing_status("p",run)["data"]
                if state["state"]=="failed":break
                time.sleep(.01)
            self.assertEqual(state["state"],"failed")
            self.assertEqual(state["errors"][0]["code"],"fixture_parser_failed")
        self.assertEqual({table:self.rows(table) for table in before},before)

    def test_active_parse_version_does_not_rewrite_registration_unique_identity(self):
        with self.svc.store.connect(write=True) as db:
            db.execute("UPDATE documents SET parser_version='legacy-parser' WHERE document_id=?",(self.did,))
            row=dict(db.execute("SELECT * FROM documents WHERE document_id=?",(self.did,)).fetchone())
            row.update(document_id="later-upload",parser_version=PARSER_VERSION)
            db.execute("INSERT INTO documents ("+",".join(row)+") VALUES("+",".join("?" for _ in row)+")",list(row.values()))
        self.svc._persist_prepared("p",self.did,copy.deepcopy(self.parsed))
        self.assertEqual(self.svc.store.document("p",self.did)["parser_version"],"legacy-parser")
        self.assertEqual(self.rows("prepared_documents")[0]["parser_version"],PARSER_VERSION)
        self.assertEqual(len(self.rows("facts")),1)

    def test_same_structure_keeps_facts_and_verified_batch_reusable(self):
        before=self.rows("facts");batch=self.rows("normalization_batches")
        self.svc._persist_prepared("p",self.did,copy.deepcopy(self.parsed))
        self.assertEqual(self.rows("facts"),before);self.assertEqual(self.rows("normalization_batches"),batch)
        self.assertEqual(self.rows("source_parse_history"),[])
        detail=json.loads(batch[0]["result_json"])
        self.assertEqual(detail["source_input_fingerprint"],self.svc._batch_input_fingerprint(self.batch))
        with patch("langextract.extract",side_effect=AssertionError("must reuse exact batch")):
            facts,report=normalize_document(self.parsed,self.did,{"model":"fixture","base_url":"http://127.0.0.1:1/v1","api_key":"fixture"},
                lambda *_:None,lambda:False,lambda *_:None,lambda *_:None,resume_get=lambda batch:detail)
        self.assertEqual(report["requests"],0);self.assertEqual(report["resumed_batches"],1)
        self.assertEqual(facts[0]["value"],"137")
        self.assertIsNotNone(completed_document(self.svc,"p",self.doc,{"model":"fixture"}))

    def test_source_fingerprint_tracks_parser_version_page_cells_rows_and_selected_rows(self):
        original=self.svc._batch_input_fingerprint(self.batch)
        for mutation in ("page","value","bbox","selected_rows"):
            changed=copy.deepcopy(self.batch)
            if mutation=="page":changed[0]["table"]["page"]=2
            elif mutation=="value":changed[0]["table"]["rows"][1][1]="999"
            elif mutation=="bbox":changed[0]["table"]["cells"]["B2"]["bbox"][0]=31
            else:changed[0]["rows"]=[2]
            self.assertNotEqual(original,self.svc._batch_input_fingerprint(changed),mutation)
        with patch("service.processing.PARSER_VERSION","older-parser"):
            self.assertNotEqual(original,self.svc._batch_input_fingerprint(self.batch))

    def test_old_or_wrong_source_fingerprint_cannot_use_completed_or_maintenance_shortcuts(self):
        for missing in (True,False):
            with self.subTest(missing=missing),self.svc.store.connect(write=True) as db:
                detail=json.loads(db.execute("SELECT result_json FROM normalization_batches").fetchone()[0])
                if missing:detail.pop("source_input_fingerprint",None)
                else:detail["source_input_fingerprint"]="stale"
                db.execute("UPDATE normalization_batches SET result_json=?",(json.dumps(detail),))
            before=self.rows("facts")
            self.assertIsNone(completed_document(self.svc,"p",self.doc,{"model":"fixture"}))
            report=self.svc.rematerialize_documents("p",[self.did])["data"]
            self.assertEqual(report["batches_replayed"],0);self.assertEqual(self.rows("facts"),before)

    def test_stale_worker_cannot_commit_to_replaced_table_identity(self):
        changed=copy.deepcopy(self.parsed);changed["tables"][0]["rows"][1][1]="999"
        self.svc._persist_prepared("p",self.did,changed)
        facts,issues=materialize(self.ex,self.batch,self.did,"fixture")
        with self.assertRaisesRegex(ValueError,"semantic_source_input_changed"):
            self.svc._commit_semantic_batch("p",self.did,"stale-worker",self.batch,facts,issues,self.detail)
        self.assertEqual(self.rows("facts"),[])

    def test_current_db_parse_is_authoritative_when_json_copy_is_stale(self):
        self.svc._prepared_path("p",self.did).write_text('{"parser_version":"old"}',encoding="utf-8")
        self.assertEqual(self.svc._read_prepared("p",self.doc),self.parsed)
        self.assertEqual(self.rows("prepared_documents")[0]["parser_version"],PARSER_VERSION)


if __name__=="__main__":unittest.main()
