import json
import time
import unittest
from unittest.mock import patch

from service.existing_review import validate_existing_review


class ExistingSourceReviewTests(unittest.TestCase):
    def setUp(self):
        from service.tests.test_definition_semantics import DefinitionTransactionTests
        DefinitionTransactionTests.setUp(self)
        self.fixture=DefinitionTransactionTests
    def tearDown(self):self.fixture.tearDown(self)
    def wait(self,pid):
        until=time.monotonic()+10
        while time.monotonic()<until:
            state=self.svc.get_processing_status("p",pid)["data"]
            if state["state"] in {"completed","needs_review","failed","cancelled"}:return state
            time.sleep(.01)
        self.fail("review did not complete")
    def test_historical_parser_and_mapping_are_retained_definition_only(self):
        with self.svc.store.connect(write=True) as db:
            db.execute("UPDATE prepared_documents SET parser_version='historical-parser'")
            db.execute("UPDATE normalization_batches SET result_json=json_set(result_json,'$.version','historical-model')")
            db.execute("UPDATE facts SET source_json=json_set(source_json,'$.normalization.version','historical-model')")
            batches=[tuple(row) for row in db.execute("SELECT * FROM normalization_batches")]
            source_index=[tuple(row) for row in db.execute("SELECT * FROM source_tables")]
            before={row["fact_id"]:{k:row[k] for k in ("value","raw_value","raw_unit","currency","period","scope","year")} for row in db.execute("SELECT * FROM facts")}
        model=lambda groups,*args:self.fixture.model(self,groups)
        with patch("service.processing.parse_document",side_effect=AssertionError("no parser")),patch("service.processing.normalize_document",side_effect=AssertionError("no normalization")),patch("service.processing.canonicalize_project",side_effect=AssertionError("no catalog")),patch("service.processing.review_temporal_project",side_effect=AssertionError("no temporal")),patch("service.definition_model.review_definitions",side_effect=model):
            state=self.svc.start_document_processing("p",[self.doc["document_id"]],"review-only",self.runtime|{"review_metrics":["receivable_amount"],"review_existing_only":True})["data"]
            result=self.wait(state["processing_id"])
        self.assertEqual(result["state"],"completed",result)
        self.assertEqual(result["mode"],"existing_source_definition_review")
        self.assertEqual(result["documents"][0]["source_parser_version"],"historical-parser")
        self.assertEqual(result["documents"][0]["normalization"]["requests"],0)
        with self.svc.store.connect() as db:
            self.assertEqual([tuple(row) for row in db.execute("SELECT * FROM normalization_batches")],batches)
            self.assertEqual([tuple(row) for row in db.execute("SELECT * FROM source_tables")],source_index)
            self.assertEqual({row["fact_id"]:{k:row[k] for k in before[row["fact_id"]]} for row in db.execute("SELECT * FROM facts")},before)
        self.assertEqual(result["definition_review"]["facts_updated"],4)
    def test_changed_original_file_fails_without_implicit_reparse(self):
        (self.root/self.doc["relative_path"]).write_text("changed",encoding="utf-8")
        with patch("service.processing.parse_document",side_effect=AssertionError("no parser")),patch("service.processing.review_definition_project",side_effect=AssertionError("no model")):
            state=self.svc.start_document_processing("p",[self.doc["document_id"]],"review-only",self.runtime|{"review_metrics":["receivable_amount"],"review_existing_only":True})["data"]
            result=self.wait(state["processing_id"])
        self.assertEqual(result["state"],"failed")
        self.assertEqual(result["errors"][0]["error"],"existing_review_original_file_changed")
    def test_failed_existing_review_exposes_durable_partial_progress(self):
        from service.definition_model import DefinitionValidationError
        calls=[]
        def model(groups,*args):
            calls.append(groups[0]["group_id"])
            if len(calls)==2:raise DefinitionValidationError([{"group_id":calls[-1],"reason":"fixture_error"}],[{"extractions":[]},{"extractions":[]}])
            return self.fixture.model(self,groups)
        with patch("service.definition_semantics.definition_chunks",side_effect=lambda rows,**kw:([row] for row in rows)),patch("service.definition_model.review_definitions",side_effect=model):
            state=self.svc.start_document_processing("p",[self.doc["document_id"]],"review-only",self.runtime|{"review_metrics":["receivable_amount"],"review_existing_only":True})["data"]
            result=self.wait(state["processing_id"])
        self.assertEqual(result["state"],"failed")
        self.assertEqual(result["errors"][0]["error"],"definition_invalid_after_repair")
        review=result["definition_review"]
        self.assertEqual((review["groups_reviewed"],review["facts_updated"],review["groups_pending"]),(1,2,1))
        self.assertEqual(review["model_requests"],3)
        self.assertNotIn("failed_attempts",review)
        with self.svc.store.connect() as db:
            saved=json.loads(db.execute("SELECT report_json FROM fact_definition_reviews WHERE review_id=?",(review["review_id"],)).fetchone()[0])
        self.assertEqual(saved["status"],"failed");self.assertEqual(len(saved["audits"]),1)
        self.assertEqual(len(saved["failed_attempts"][0]["attempts"]),2)
    def test_missing_original_model_mapping_is_not_silently_recreated(self):
        with self.svc.store.connect(write=True) as db:db.execute("DELETE FROM normalization_batches")
        with self.assertRaisesRegex(ValueError,"existing_review_original_extractions_missing"):
            validate_existing_review(self.svc,"p",[self.doc["document_id"]],["receivable_amount"])
    def test_changed_source_index_is_rejected(self):
        with self.svc.store.connect(write=True) as db:db.execute("UPDATE source_tables SET bbox_json='[0,0,10,10]'")
        with self.assertRaisesRegex(ValueError,"existing_review_source_snapshot_changed"):
            validate_existing_review(self.svc,"p",[self.doc["document_id"]],["receivable_amount"])
    def test_mode_requires_selected_metrics_and_rejects_force(self):
        for config in ({"review_existing_only":True},{"review_existing_only":True,"review_metrics":["receivable_amount"],"force":True}):
            with self.assertRaisesRegex(ValueError,"existing_review_requires_metrics_without_force"):
                self.svc.start_document_processing("p",[self.doc["document_id"]],"review-only",self.runtime|config)


if __name__=="__main__":unittest.main()
