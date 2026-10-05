import json
import tempfile
import threading
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

from service.core import FinanceService
from service.parser import parse_document
from service.semantic import materialize,table_batches,SCHEMA_HASH
from service.store import dumps
from service.temporal_semantics import review_project,collect_sources,build_profiles,chunks,overlay_saved_corrections,temporal_review_status


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
        with patch("service.temporal_model.review_profiles",side_effect=profiles or self.all_candidates),patch("service.temporal_model.correct_sources",side_effect=correct or self.to_instant):
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
        with patch("service.temporal_model.review_profiles",side_effect=AssertionError("cache required")),patch("service.temporal_model.correct_sources",side_effect=AssertionError("cache required")):
            result=review_project(self.svc,"p",self.runtime|{"processing_id":"new-execution","owner_run_id":"new-pi","api_key":"new-token","base_url":"http://127.0.0.1:2/other/v1"})
        self.assertEqual(result["model_requests"],0);self.assertEqual(result["cache_hits"],2);self.assertEqual(result["facts_updated"],0)
        fact=self.svc.query_financial_data("p")["data"]["items"][0]
        self.assertEqual(fact["source_ref"]["normalization"]["temporal_correction"]["extraction_processing_id"],"review-owner")

    def test_output_limit_splits_profile_and_source_batches_with_leaf_provenance(self):
        from service.tests.test_review_budget import LimitError
        self.seed();self.seed(metric='liabilities',label='负债总计',name='2024负债.csv')
        def profiles(part,*args):
            if len(part)>1:raise LimitError()
            return self.all_candidates(part)
        def corrections(part,*args):
            if len(part)>1:raise LimitError()
            return self.to_instant(part)
        report=self.run_review(profiles,corrections)
        self.assertEqual(report['status'],'reviewed');self.assertEqual(report['model_requests'],6)
        facts=self.svc.query_financial_data('p')['data']['items'];self.assertEqual(len(facts),2)
        with self.svc.store.connect() as db:
            for fact in facts:
                evidence=fact['source_ref']['normalization']['temporal_correction']
                saved=json.loads(db.execute('select result_json from temporal_review_cache where cache_key=?',(evidence['cache_key'],)).fetchone()[0])
                self.assertEqual(len(saved['corrections']),1)
                self.assertEqual(saved['corrections'][0]['source_key'],evidence['source_key'])
                self.assertEqual(evidence['owner_run_id'],'pi-owner')
        with patch('service.temporal_model.review_profiles',side_effect=AssertionError('no paid replay')),patch('service.temporal_model.correct_sources',side_effect=AssertionError('no paid replay')):
            again=review_project(self.svc,'p',self.runtime)
        self.assertEqual(again['model_requests'],0)

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

    def test_invalid_source_response_does_not_stop_later_batch_or_change_failed_fact(self):
        import re
        from service.tests.test_temporal_model import response,correction
        self.seed();self.seed(metric='liabilities',label='负债总计',name='2024负债.csv')
        with self.svc.store.connect() as db:sources,_=collect_sources(db,'p')
        lookup={s['source_key']:s for s in sources};bad=next(s['source_key'] for s in sources if s['metric']=='assets')
        def answer(**kwargs):
            key=re.search(r'\[\[SOURCE:([^]]+)\]\]',kwargs['text_or_documents'])[1]
            return response([] if key==bad else [correction([lookup[key]],key)])
        with patch('service.temporal_model.review_profiles',side_effect=self.all_candidates),\
             patch('service.temporal_semantics.source_chunks',side_effect=lambda targets:[[s] for s in targets]),\
             patch('langextract.extract',side_effect=answer) as model:
            report=review_project(self.svc,'p',self.runtime)
        self.assertEqual(model.call_count,3);self.assertEqual(report['status'],'needs_review')
        self.assertEqual([s['source_key'] for s in report['unresolved']],[bad])
        self.assertEqual(report['facts_updated'],1);self.assertEqual(len(report['correction_audits']),2)
        periods={f['metric']:f['period'] for f in self.svc.query_financial_data('p')['data']['items']}
        self.assertEqual(periods,{'assets':'2024-FY','liabilities':'2024-12-31'})

    def test_continuation_reviews_only_unresolved_sources_after_metric_definition_change(self):
        self.seed();self.seed(metric="liabilities",label="负债合计",name="2024负债表.csv")
        def partial(sources,*args):
            kept=[source for source in sources if source["metric"]=="assets"]
            result=self.to_instant(kept)
            result["unresolved"]=[{"source_key":source["source_key"],"reason":"缺续页表头"} for source in sources if source["metric"]=="liabilities"]
            return result
        first=self.run_review(correct=partial)
        self.assertEqual(first["status"],"needs_review")
        with self.svc.store.connect(write=True) as db:
            # Definition review changes display identity, never original mapping.
            db.execute("UPDATE facts SET metric='liabilities_defined' WHERE metric='liabilities'")
        seen=[]
        def repair(sources,*args):
            seen.extend(sources);self.assertEqual(len(sources),1)
            self.assertIn("context_pages",sources[0]);return self.to_instant(sources)
        result=self.run_review(profiles=lambda *args: self.fail("completed overview must not repeat"),correct=repair,
                               runtime=self.runtime|{"processing_id":"repair-owner","owner_run_id":"repair-pi"})
        self.assertEqual(result["status"],"reviewed");self.assertEqual(result["profile_groups_this_run"],0)
        self.assertEqual(result["profiles_reviewed"],2);self.assertEqual(result["sources_targeted_this_run"],1)
        self.assertEqual(result["sources_targeted"],2);self.assertEqual(result["model_requests"],1)
        self.assertEqual(result["profile_audits"],first["profile_audits"])
        facts=self.svc.query_financial_data("p")["data"]["items"]
        asset=next(fact for fact in facts if fact["metric"]=="assets")
        repaired=next(fact for fact in facts if fact["metric"]=="liabilities_defined")
        self.assertEqual(asset["source_ref"]["normalization"]["temporal_correction"]["owner_run_id"],"pi-owner")
        self.assertEqual(repaired["source_ref"]["normalization"]["temporal_correction"]["owner_run_id"],"repair-pi")
        self.assertTrue(repaired["source_ref"]["normalization"]["temporal_correction"]["context_pages"])
        self.assertEqual({fact["value"] for fact in facts},{"100"})

    def test_new_sources_get_overview_without_repeating_completed_source_groups(self):
        self.seed();self.run_review()
        self.seed(metric="liabilities",label="负债合计",name="2024负债表.csv")
        seen=[]
        def overview(profiles,*args):seen.extend(profiles);return self.all_candidates(profiles)
        result=self.run_review(profiles=overview)
        self.assertEqual([item["metric"] for item in seen],["liabilities"])
        self.assertEqual(result["facts_total"],2);self.assertEqual(result["profiles_reviewed"],2)
        self.assertEqual(result["sources_targeted_this_run"],1)

    def test_cross_year_correction_uses_matching_explicit_range_and_replays(self):
        from service.temporal_semantics import validate_after
        doc,batch,detail=self.seed(metric="cumulative_amount",label="三年累计金额")
        def range_result(sources,*args):
            result=self.to_instant(sources)
            for item in result["corrections"]:item.update(period="2022-01-01/2024-12-31",start="2022-01-01",end="2024-12-31")
            return result
        self.run_review(correct=range_result)
        rebuilt,_=materialize(detail["extractions"],batch,doc["document_id"],"deepseek-flash")
        with self.svc.store.connect() as db:self.assertEqual(overlay_saved_corrections(db,"p",doc["document_id"],rebuilt,detail),1)
        self.assertEqual(rebuilt[0]["period"],"2022-01-01/2024-12-31")
        self.assertEqual(rebuilt[0]["value"],"100")
        with self.assertRaises(ValueError):validate_after({"period":"2022-01-01/2024-12-31","start":"2023-01-01","end":"2024-12-31"})

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
        with patch("service.temporal_model.review_profiles",side_effect=self.all_candidates),patch("service.temporal_model.correct_sources",side_effect=correct):
            with self.assertRaises(InterruptedError):review_project(self.svc,"p",self.runtime,cancelled=flag.is_set)
        self.assertEqual(self.svc.query_financial_data("p")["data"]["items"][0]["period"],"2024-FY")

    def test_old_partial_review_finishing_last_does_not_replace_full_snapshot_status(self):
        self.seed();first=self.run_review()
        self.seed(metric="liabilities",label="负债合计",name="2024另一报表.csv")
        complete=self.run_review(runtime=self.runtime|{"processing_id":"newer-full-owner"})
        old=dict(first);old.update(review_id="late-old-review",status="needs_review",pending_new_sources=["new-data"],completed_at="2999-01-01T00:00:00+00:00")
        with self.svc.store.connect(write=True) as db:
            db.execute("INSERT INTO temporal_project_reviews VALUES(?,?,?,?)",(old["review_id"],"p",dumps(old),old["completed_at"]))
        summary=temporal_review_status(self.svc.store,"p")
        self.assertEqual(summary["review_id"],complete["review_id"])
        self.assertEqual(summary["status"],"reviewed");self.assertTrue(summary["coverage_snapshot_valid"])
        self.assertEqual(summary["facts_total"],2)

    def test_new_source_during_review_remains_pending(self):
        self.seed()
        def concurrent_source(sources,*args):
            self.seed(metric="liabilities",label="负债合计",name="2024新增负债表.csv")
            return self.to_instant(sources)
        result=self.run_review(correct=concurrent_source)
        self.assertEqual(result["status"],"needs_review");self.assertEqual(len(result["pending_new_sources"]),1)
        summary=temporal_review_status(self.svc.store,"p")
        self.assertEqual(summary["status"],"pending");self.assertFalse(summary["coverage_snapshot_valid"])
        self.assertEqual(summary["current_fact_count"],2)

    def test_chunking_covers_every_profile_even_when_payload_is_large(self):
        rows=[{"group_id":str(i),"text":"x"*100} for i in range(113)]
        parts=list(chunks(rows,50,max_chars=3000))
        self.assertEqual([r["group_id"] for part in parts for r in part],[r["group_id"] for r in rows])
        self.assertTrue(all(len(part)<=50 for part in parts))

    def test_correction_batches_infer_concurrently_and_commit_every_source(self):
        for i in range(3):self.seed(metric=f"asset_{i}",label=f"资产项目{i}",name=f"2024表{i}.csv")
        barrier=threading.Barrier(3);thread_ids=set()
        def concurrent_correction(sources,*args):
            thread_ids.add(threading.get_ident());barrier.wait(timeout=5)
            return self.to_instant(sources)
        with patch("service.temporal_semantics.source_chunks",side_effect=lambda rows:([row] for row in rows)):
            result=self.run_review(correct=concurrent_correction)
        self.assertEqual(len(thread_ids),3);self.assertEqual(result["correction_chunks"],3)
        self.assertEqual(result["facts_updated"],3);self.assertEqual(result["status"],"reviewed")
        self.assertEqual({f["period"] for f in self.svc.query_financial_data("p")["data"]["items"]},{"2024-12-31"})

    def test_parallel_reviews_use_the_same_immutable_cache_output_and_owner(self):
        self.seed()
        def overview(profiles,runtime,*args):
            result=self.all_candidates(profiles)
            for item in result["candidates"]:item["reason"]=runtime["owner_run_id"]
            time.sleep(0.15);return result
        def corrections(sources,runtime,*args):
            result=self.to_instant(sources)
            for item in result["corrections"]:item["reason"]=runtime["owner_run_id"]
            time.sleep(0.15);return result
        with patch("service.temporal_model.review_profiles",side_effect=overview),patch("service.temporal_model.correct_sources",side_effect=corrections):
            with ThreadPoolExecutor(max_workers=2) as pool:
                reports=list(pool.map(lambda owner:review_project(self.svc,"p",self.runtime|{"owner_run_id":owner,"processing_id":owner}),["parallel-A","parallel-B"]))
        self.assertEqual(sum(report["model_requests"] for report in reports),2)
        for kind in ("profile_audits","correction_audits"):
            left,right=reports[0][kind][0],reports[1][kind][0]
            self.assertEqual(left,right)
            with self.svc.store.connect() as db:stored=json.loads(db.execute("SELECT result_json FROM temporal_review_cache WHERE cache_key=?",(left["cache_key"],)).fetchone()[0])
            self.assertEqual(left["source_provenance"],stored["_review_provenance"])
        correction=self.svc.query_financial_data("p")["data"]["items"][0]["temporal_correction"]
        self.assertEqual(correction["owner_run_id"],reports[0]["correction_audits"][0]["source_provenance"]["owner_run_id"])

    def test_old_report_with_overwritten_owner_is_not_inherited(self):
        self.seed();first=self.run_review();audit=first["profile_audits"][0]
        with self.svc.store.connect(write=True) as db:
            payload=json.loads(db.execute("SELECT result_json FROM temporal_review_cache WHERE cache_key=?",(audit["cache_key"],)).fetchone()[0])
            payload["_review_provenance"]={"owner_run_id":"historical-overwriter","processing_id":"other"}
            db.execute("UPDATE temporal_review_cache SET result_json=? WHERE cache_key=?",(dumps(payload),audit["cache_key"]))
        with patch("service.temporal_model.review_profiles",side_effect=AssertionError("accepted cache already exists")),patch("service.temporal_model.correct_sources",side_effect=AssertionError("accepted cache already exists")):
            second=review_project(self.svc,"p",self.runtime)
        self.assertFalse(second.get("reused_profile_review",False));self.assertEqual(second["profile_groups_this_run"],1)
        self.assertEqual(second["profile_audits"][0]["source_provenance"]["owner_run_id"],"historical-overwriter")
        with self.svc.store.connect() as db:unchanged=json.loads(db.execute("SELECT report_json FROM temporal_project_reviews WHERE review_id=?",(first["review_id"],)).fetchone()[0])
        self.assertEqual(unchanged,first)


if __name__=="__main__":unittest.main()
