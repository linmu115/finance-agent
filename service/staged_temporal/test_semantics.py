import json
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from service.core import FinanceService
from service.parser import parse_document
from service.semantic import materialize,table_batches,SCHEMA_HASH
from service.store import dumps
from service.staged_temporal.semantics import review_project,collect_sources,build_profiles,chunks,overlay_saved_corrections,temporal_review_status


class TemporalTransactionTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);self.svc=FinanceService(self.root)
        self.svc.create_project("p","期间审校测试")
        self.runtime={"base_url":"http://127.0.0.1:1/pi/v1","api_key":"ephemeral-test","model":"deepseek-flash","processing_id":"review-owner","owner_run_id":"pi-owner"}

    def tearDown(self):
        for pool in (self.svc.processing_pool,self.svc.pool,self.svc.analysis_pool,self.svc.embedding_pool):pool.shutdown(wait=True,cancel_futures=True)
        self.tmp.cleanup()

    def seed(self,metric="assets",label="资产总计",name="2024财报.csv",start="",end="2024-12-31",statement="balance",heading="2024年12月31日"):
        upload=self.root/"uploads"/name;upload.write_text("项目,"+heading+"\n"+label+",100\n",encoding="utf-8")
        doc=self.svc.register_document("p",str(upload),name)["data"]
        parsed=parse_document(self.root/doc["relative_path"],name,lambda *_:None,lambda:False,{})
        self.svc._persist_prepared("p",doc["document_id"],parsed)
        batch=table_batches(parsed)[0]
        extracts=[{"class":"table_schema","text":"[[T0]]","span":[0,6],"attributes":{"company":"测试公司","statement":statement,"scope":"consolidated_CAS","columns_json":json.dumps([{"column":2,"period":"2024-FY","start":start,"end":end,"unit":"元","currency":"CNY"}])}},
                  {"class":"financial_row","text":"[[T0:R2]]","span":[7,17],"attributes":{"metric":metric,"label":label}}]
        facts,issues=materialize(extracts,batch,doc["document_id"],"deepseek-flash")
        self.assertFalse(issues)
        detail={"model":"deepseek-flash","schema_hash":SCHEMA_HASH,"extractions":extracts,"extraction_processing_id":"table-owner"}
        self.svc._commit_semantic_batch("p",doc["document_id"],"table-owner",batch,facts,issues,detail)
        return doc,batch,detail

    def all_candidates(self,profiles,*args):
        return {"candidates":[{"group_id":p["group_id"],"reason":"复核原表时点"} for p in profiles],"reviewed_count":len(profiles),"requests":1,"extractions":[]}

    def to_instant(self,sources,*args):
        return {"corrections":[{"source_key":s["source_key"],"period":"2024-12-31","start":"","end":"2024-12-31","reason":"原表明确2024年12月31日余额","evidence":"2024年12月31日","span":[0,10]} for s in sources],"unresolved":[],"requests":1,"extractions":[]}

    def run_review(self,profiles=None,correct=None,runtime=None):
        with patch("service.staged_temporal.model.review_profiles",side_effect=profiles or self.all_candidates),patch("service.staged_temporal.model.correct_sources",side_effect=correct or self.to_instant):
            return review_project(self.svc,"p",runtime or self.runtime)

    def test_consistently_wrong_asset_period_is_in_full_profile_review(self):
        self.seed();seen=[]
        def audit(profiles,*args):seen.extend(profiles);return self.all_candidates(profiles)
        result=self.run_review(profiles=audit)
        self.assertEqual(result["profiles_total"],1);self.assertEqual(result["profiles_reviewed"],1)
        self.assertEqual(len(seen),1);self.assertEqual(seen[0]["examples"][0]["period"],"2024-FY")
        self.assertEqual(result["facts_updated"],1)
        summary=temporal_review_status(self.svc.store,"p")
        self.assertEqual(summary["profiles_reviewed"],1);self.assertEqual(summary["owner_run_id"],"pi-owner")
        fact=self.svc.query_financial_data("p")["data"]["items"][0]
        self.assertEqual(fact["period"],"2024-12-31");self.assertEqual(fact["value"],"100")
        correction=fact["source_ref"]["normalization"]["temporal_correction"]
        self.assertEqual(correction["before"],{"period":"2024-FY","start":"","end":"2024-12-31"})
        self.assertEqual(correction["extraction_processing_id"],"review-owner")

    def test_cached_review_keeps_original_model_owner_and_has_zero_calls(self):
        self.seed();self.run_review()
        with patch("service.staged_temporal.model.review_profiles",side_effect=AssertionError("cache required")),patch("service.staged_temporal.model.correct_sources",side_effect=AssertionError("cache required")):
            result=review_project(self.svc,"p",self.runtime|{"processing_id":"new-execution","owner_run_id":"new-pi","api_key":"new-token","base_url":"http://127.0.0.1:2/other/v1"})
        self.assertEqual(result["model_requests"],0);self.assertEqual(result["cache_hits"],2);self.assertEqual(result["facts_updated"],0)
        fact=self.svc.query_financial_data("p")["data"]["items"][0]
        self.assertEqual(fact["source_ref"]["normalization"]["temporal_correction"]["extraction_processing_id"],"review-owner")

    def test_original_extraction_is_immutable_and_saved_correction_overlays_replay(self):
        doc,batch,detail=self.seed();before=json.dumps(detail,sort_keys=True)
        self.run_review()
        facts,_=materialize(detail["extractions"],batch,doc["document_id"],"deepseek-flash")
        with self.svc.store.connect() as db:applied=overlay_saved_corrections(db,"p",doc["document_id"],facts,detail)
        self.assertEqual(applied,1);self.assertEqual(facts[0]["period"],"2024-12-31");self.assertEqual(json.dumps(detail,sort_keys=True),before)
        detail["extractions"][1]["attributes"]["label"]="另一轮模型解释"
        facts,_=materialize(detail["extractions"],batch,doc["document_id"],"deepseek-flash")
        with self.svc.store.connect() as db:applied=overlay_saved_corrections(db,"p",doc["document_id"],facts,detail)
        self.assertEqual(applied,0);self.assertEqual(facts[0]["period"],"2024-FY")

    def test_concurrent_new_extraction_prevents_old_correction_overwrite(self):
        doc,batch,detail=self.seed()
        def concurrent_change(sources,*args):
            result=self.to_instant(sources)
            detail["extractions"][1]["attributes"]["label"]="并发更新后的资产总计"
            facts,issues=materialize(detail["extractions"],batch,doc["document_id"],"deepseek-flash")
            self.svc._commit_semantic_batch("p",doc["document_id"],"other-owner",batch,facts,issues,detail)
            return result
        result=self.run_review(correct=concurrent_change)
        self.assertEqual(result["facts_updated"],0);self.assertEqual(len(result["stale_sources"]),1)
        self.assertEqual(result["status"],"needs_review")
        self.assertEqual(self.svc.query_financial_data("p")["data"]["items"][0]["period"],"2024-FY")

    def test_missing_profile_coverage_is_rejected_without_mutation(self):
        self.seed()
        def incomplete(profiles,*args):return {"candidates":[],"reviewed_count":0,"requests":1}
        with self.assertRaisesRegex(ValueError,"profile_coverage_invalid"):self.run_review(profiles=incomplete)
        self.assertEqual(self.svc.query_financial_data("p")["data"]["items"][0]["period"],"2024-FY")
        with self.svc.store.connect() as db:self.assertEqual(db.execute("SELECT count(*) FROM temporal_review_cache").fetchone()[0],0)

    def test_unresolved_source_is_kept_as_an_explicit_issue(self):
        self.seed(metric="planned_investment",label="计划投资总额")
        def unresolved(sources,*args):return {"corrections":[],"unresolved":[{"source_key":s["source_key"],"reason":"原文没有计划归属日期，不能赋年"} for s in sources],"requests":1}
        result=self.run_review(correct=unresolved)
        self.assertEqual(result["status"],"needs_review");self.assertEqual(result["facts_updated"],0)
        self.assertEqual(len(result["unresolved"]),1)

    def test_overview_covers_valid_flow_too_and_does_not_change_its_interval(self):
        self.seed()
        self.seed(metric="operating_cash_flow",label="经营现金流净额",name="2024现金流.csv",start="2024-01-01",statement="cashflow",heading="2024年度")
        seen=[]
        def review(profiles,*args):
            seen.extend(profiles)
            return {"candidates":[{"group_id":p["group_id"],"reason":"资产存量需时点"} for p in profiles if p["metric"]=="assets"],"reviewed_count":len(profiles),"requests":1}
        result=self.run_review(profiles=review)
        self.assertEqual({p["metric"] for p in seen},{"assets","operating_cash_flow"})
        self.assertEqual(result["facts_total"],2);self.assertEqual(result["facts_updated"],1)
        flow=self.svc.query_financial_data("p",{"metric":"operating_cash_flow"})["data"]["items"][0]
        self.assertEqual(flow["period"],"2024-FY");self.assertEqual(flow["period_start"],"2024-01-01")
        self.assertEqual((flow["value"],flow["currency"],flow["raw_unit"],flow["scope"]),("100","CNY","元","consolidated_CAS"))

    def test_cancellation_after_model_response_does_not_commit_dates(self):
        self.seed();flag=threading.Event()
        def correct(sources,*args):
            result=self.to_instant(sources);flag.set();return result
        with patch("service.staged_temporal.model.review_profiles",side_effect=self.all_candidates),patch("service.staged_temporal.model.correct_sources",side_effect=correct):
            with self.assertRaises(InterruptedError):review_project(self.svc,"p",self.runtime,cancelled=flag.is_set)
        self.assertEqual(self.svc.query_financial_data("p")["data"]["items"][0]["period"],"2024-FY")

    def test_chunking_covers_every_profile_even_when_payload_is_large(self):
        rows=[{"group_id":str(i),"text":"x"*100} for i in range(113)]
        parts=list(chunks(rows,50,max_chars=3000))
        self.assertEqual([r["group_id"] for part in parts for r in part],[r["group_id"] for r in rows])
        self.assertTrue(all(len(part)<=50 for part in parts))


if __name__=="__main__":unittest.main()
