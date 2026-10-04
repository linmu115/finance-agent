import json
import tempfile
import unittest
import uuid
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

from service.catalog_semantics import canonicalize_project, directory_status
from service.core import FinanceService
from service.store import dumps


class CatalogTransactionTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.svc=FinanceService(Path(self.tmp.name))
        self.svc.create_project("p","目录事务测试")
        source=Path(self.tmp.name)/"uploads"/"sample.csv";source.write_text("指标,数值\n应收账款,10",encoding="utf-8")
        self.doc=self.svc.register_document("p",str(source),source.name)["data"]["document_id"]
        self.runtime={"model":"deepseek-flash","base_url":"http://127.0.0.1:1/pi/v1","api_key":"test-ephemeral"}

    def tearDown(self):
        for pool in (self.svc.processing_pool,self.svc.pool,self.svc.analysis_pool,self.svc.embedding_pool):pool.shutdown(wait=True,cancel_futures=True)
        self.tmp.cleanup()

    def fact(self,metric,label="应收账款",currency="CNY",dimensions=None):
        source={"document_id":self.doc,"page":1,"table_id":self.doc+":t0","row":2,"column":2,"text":label+" | 10",
                "normalization":{"engine":"LangExtract","label":label,"statement":"balance","dimensions":dimensions or {}}}
        with self.svc.store.connect(write=True) as db:
            db.execute("INSERT INTO facts VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",(uuid.uuid4().hex,self.doc,"p","测试公司",metric,2024,"2024-12-31","consolidated_CAS",currency,"10","元","10",dumps(source),120,"llm_normalized"))

    def review(self,profiles,*args):
        ids={p["metric"] for p in profiles}
        aliases={"trade_receivables":{"canonical_metric":"accounts_receivable","canonical_label":"应收账款","reason":"同为销售形成的应收账款余额","span":[20,48],"extraction_text":"[[METRIC:trade_receivables]]"}} if "trade_receivables" in ids else {}
        return {"keep":sorted(ids-set(aliases)),"aliases":aliases},[{"class":"catalog_review","text":"[[CATALOG]]"}],1

    def test_model_alias_updates_facts_preserves_sources_and_reuses_directory_cache(self):
        self.fact("accounts_receivable");self.fact("trade_receivables",dimensions={"segment":"华东"})
        self.assertEqual(directory_status(self.svc.store,"p")["status"],"not_run")
        with patch("service.catalog_semantics._call_model",side_effect=self.review) as call:
            first=canonicalize_project(self.svc.store,"p",self.runtime)
            second=canonicalize_project(self.svc.store,"p",self.runtime|{"api_key":"another-token","base_url":"http://127.0.0.1:2/other/v1"})
        self.assertEqual(call.call_count,1);self.assertEqual(first["alias_count"],1);self.assertEqual(second["cache_hits"],1)
        self.assertEqual(second["facts_updated"],0)
        facts=self.svc.query_financial_data("p",{"metric":"trade_receivables"})["data"]["items"]
        self.assertEqual(len(facts),2);self.assertTrue(all(f["metric"]=="accounts_receivable" for f in facts))
        aliased=next(f for f in facts if f["original_metric"]=="trade_receivables")
        self.assertEqual(aliased["dimensions"],{"segment":"华东"});self.assertEqual(aliased["value"],"10")
        self.assertEqual(aliased["canonical_alias"]["reason"],"同为销售形成的应收账款余额")
        self.assertEqual(directory_status(self.svc.store,"p")["status"],"reviewed")
        aliases=self.svc.get_data_catalog("p")["data"]["metric_aliases"]
        self.assertEqual(aliases[0]["source_metric"],"trade_receivables")
        self.assertEqual(aliases[0]["canonical_metric"],"accounts_receivable")

    def test_concurrent_new_metric_is_not_lost_or_falsely_reviewed(self):
        self.fact("accounts_receivable");self.fact("trade_receivables")
        def review_with_concurrent_commit(profiles,*args):
            self.fact("deferred_tax_assets","递延所得税资产")
            return self.review(profiles)
        with patch("service.catalog_semantics._call_model",side_effect=review_with_concurrent_commit):
            result=canonicalize_project(self.svc.store,"p",self.runtime,max_rounds=1)
        self.assertEqual(result["status"],"pending");self.assertEqual(result["pending_metric_ids"],["deferred_tax_assets"])
        facts=self.svc.query_financial_data("p",{"metric":"deferred_tax_assets"})["data"]["items"]
        self.assertEqual(len(facts),1);self.assertIsNone(facts[0]["canonical_alias"])
        self.assertEqual(directory_status(self.svc.store,"p")["status"],"partial")

    def test_failed_review_leaves_original_metrics_and_unreviewed_status(self):
        self.fact("accounts_receivable");self.fact("trade_receivables")
        with patch("service.catalog_semantics._call_model",side_effect=ValueError("catalog_review_invalid_after_repair")):
            with self.assertRaisesRegex(ValueError,"catalog_review_invalid"):
                canonicalize_project(self.svc.store,"p",self.runtime)
        facts=self.svc.query_financial_data("p")["data"]["items"]
        self.assertEqual({f["metric"] for f in facts},{"accounts_receivable","trade_receivables"})
        self.assertEqual(directory_status(self.svc.store,"p")["status"],"not_run")

    def test_parallel_catalog_review_commits_accepted_result_and_original_owner(self):
        self.fact("accounts_receivable");self.fact("trade_receivables")
        def disagree(profiles,runtime,*args):
            result=self.review(profiles)
            if runtime["owner_run_id"]=="review-B":result=({"keep":[p["metric"] for p in profiles],"aliases":{}},[{"class":"other_result"}],1)
            time.sleep(0.15);return result
        with patch("service.catalog_semantics._call_model",side_effect=disagree):
            with ThreadPoolExecutor(max_workers=2) as pool:
                reports=list(pool.map(lambda owner:canonicalize_project(self.svc.store,"p",self.runtime|{"owner_run_id":owner,"processing_id":owner}),["review-A","review-B"]))
        self.assertEqual(sum(r["requests"] for r in reports),1)
        with self.svc.store.connect() as db:
            rows=db.execute("SELECT result_json FROM metric_directory_reviews").fetchall();self.assertEqual(len(rows),1)
            accepted=json.loads(rows[0][0])
        owner=accepted["_review_provenance"]["owner_run_id"]
        facts=self.svc.query_financial_data("p")["data"]["items"]
        self.assertEqual({fact["canonical_alias"]["source_provenance"]["owner_run_id"] for fact in facts},{owner})
        expected={"accounts_receivable"} if owner=="review-A" else {"accounts_receivable","trade_receivables"}
        self.assertEqual({fact["metric"] for fact in facts},expected)


if __name__=="__main__":unittest.main()
