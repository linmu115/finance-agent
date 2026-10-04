import json
import tempfile
import unittest
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

from service.core import FinanceService
from service.parser import parse_document
from service.semantic import VERSION,SCHEMA_HASH,materialize,table_batches
from service.definition_semantics import build_groups,review_project,overlay_saved_definitions,_mask_page_values,family_catalog,metric_families,definition_chunks


class DefinitionTransactionTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name);self.svc=FinanceService(self.root)
        self.svc.create_project("p","Definitions")
        path=self.root/"uploads"/"2024报表.csv"
        path.write_text("项目,2024年度,2023年度\n应收款项账面余额（未扣减准备）,123456.78,98765.43\n应收款项账面价值（已扣减准备）,111111.11,88888.88\n",encoding="utf-8")
        self.doc=self.svc.register_document("p",str(path),path.name)["data"]
        parsed=parse_document(self.root/self.doc["relative_path"],path.name,lambda *_:None,lambda:False,{})
        self.svc._persist_prepared("p",self.doc["document_id"],parsed);self.batch=table_batches(parsed)[0]
        cols=[{"column":2,"period":"2024-12-31","unit":"元","currency":"CNY"},{"column":3,"period":"2023-12-31","unit":"元","currency":"CNY"}]
        self.extractions=[{"class":"table_schema","text":"[[T0]]","span":[0,6],"attributes":{"company":"测试公司","statement":"notes","scope":"consolidated_CAS","columns_json":json.dumps(cols)}}]
        for row,label in [(2,"应收款项账面余额（未扣减准备）"),(3,"应收款项账面价值（已扣减准备）")]:
            self.extractions.append({"class":"financial_row","text":f"[[T0:R{row}]]","span":[row*10,row*10+9],"attributes":{"metric":"receivable_amount","label":label}})
        self.detail={"version":VERSION,"schema_hash":SCHEMA_HASH,"model":"deepseek-flash","extractions":self.extractions}
        facts,issues=materialize(self.extractions,self.batch,self.doc["document_id"],"deepseek-flash")
        self.svc._commit_semantic_batch("p",self.doc["document_id"],"table-owner",self.batch,facts,issues,self.detail)
        self.runtime={"base_url":"http://127.0.0.1:1/pi/v1","api_key":"ephemeral","model":"deepseek-flash","processing_id":"definition-owner","owner_run_id":"pi-owner"}

    def tearDown(self):
        for pool in (self.svc.processing_pool,self.svc.pool,self.svc.analysis_pool,self.svc.embedding_pool):pool.shutdown(wait=True,cancel_futures=True)
        self.temp.cleanup()

    def model(self,groups,*args):
        result=[]
        for group in groups:
            gross="未扣减" in group["original_label"];quote="未扣减准备" if gross else "已扣减准备"
            evidence=next(item for item in group["evidence"] if quote in item["text"])
            result.append({"group_id":group["group_id"],"metric":"receivable_gross_balance" if gross else "receivable_net_value","label":"应收款项账面余额" if gross else "应收款项账面价值",
                           "definition":"按原文口径计量应收款项","definition_scope":quote,"reason":"原文明确是否扣减准备","grounded_quotes":[{"evidence_id":evidence["evidence_id"],"text":quote}]})
        from service.definition_model import align_extractions
        extracts=[{"class":"definition_decision","text":f"[[DEFINITION:{item['group_id']}]]","span":None,
                   "attributes":{field:item[field] for field in ("metric","label","definition","definition_scope","reason")}
                   |{"grounded_quotes_json":json.dumps(item["grounded_quotes"],ensure_ascii=False)}} for item in result]
        return {"decisions":result,"unresolved":[],"extractions":align_extractions(extracts,groups,[]),"requests":1}

    def facts(self):return self.svc.query_financial_data("p")["data"]["items"]

    def test_grouping_masks_amounts_but_keeps_years_and_unit_denominators(self):
        with self.svc.store.connect() as db:groups,members,known,missing,selected=build_groups(db,"p",["receivable_amount"])
        self.assertEqual(len(groups),2);self.assertEqual([group["member_count"] for group in groups],[2,2])
        text=json.dumps(groups,ensure_ascii=False)
        for amount in ("123456.78","98765.43","111111.11","88888.88"):self.assertNotIn(amount,text)
        self.assertIn("2024",text);self.assertIn("未扣减准备",text);self.assertEqual(missing,[])
        sample=_mask_page_values("2024 年、1 年内、每 10 股。金额 123456.78",["2024","1","10","123456.78"])
        self.assertIn("2024 年",sample);self.assertIn("1 年内",sample);self.assertIn("10 股",sample);self.assertNotIn("123456.78",sample)

    def test_definition_context_excludes_unrelated_project_catalog_and_keeps_family(self):
        from service.definition_model import _render
        with self.svc.store.connect() as db:groups,_,known,_,_=build_groups(db,"p",["receivable_amount"])
        known+=[{"metric":f"unrelated_{i}","labels":["其他业务"],"definitions":["其他领域定义"],"definition_scope":"其他范围","public_id":False} for i in range(513)]
        selected=family_catalog(known,groups)
        self.assertEqual([item["metric"] for item in selected],["receivable_amount"])
        self.assertLess(len(_render(groups,selected)),len(_render(groups,known))/4)
        groups[1]["current_metric"]="renamed_receivable"
        self.assertEqual(len(metric_families(groups)),1)
        self.assertEqual({item["metric"] for item in family_catalog(known,groups)},{"receivable_amount","renamed_receivable"})

    def test_definition_batches_budget_complete_rendered_directory_and_deduped_sources(self):
        from service.definition_model import _render
        with self.svc.store.connect() as db:groups,_,known,_,_=build_groups(db,"p",["receivable_amount"])
        rows=[dict(groups[0],group_id=f"group_{i}") for i in range(15)]
        parts=list(definition_chunks(rows,max_groups=6,max_chars=14000,known_metrics=known))
        self.assertEqual([g["group_id"] for part in parts for g in part],[g["group_id"] for g in rows])
        self.assertTrue(all(len(part)<=6 and len(_render(part,known))<=14000 for part in parts))

    def test_complete_source_page_preserves_late_exclusion_and_masks_amounts(self):
        from service.definition_model import _render
        text="正文"*2400+"范围条款：正常经营业务补助除外，金额123456.78，每10股。"
        with self.svc.store.connect(write=True) as db:
            db.execute("UPDATE pages SET text=? WHERE document_id=?",(text,self.doc["document_id"]))
        with self.svc.store.connect() as db:groups,_,known,_,_=build_groups(db,"p",["receivable_amount"])
        rendered=_render(groups,known)
        self.assertIn("正常经营业务补助除外",rendered)
        self.assertIn("每10股",rendered);self.assertNotIn("123456.78",rendered)
        self.assertEqual(rendered.count("正文"*2400),1,"shared full page must appear once per request")

    def test_review_changes_only_definition_and_saved_overlay_survives_replay(self):
        before={fact["source_ref"]["cell"]:fact for fact in self.facts()}
        with patch("service.definition_model.review_definitions",side_effect=self.model):result=review_project(self.svc,"p",["receivable_amount"],self.runtime)
        self.assertEqual(result["status"],"reviewed");self.assertEqual(result["groups_reviewed"],2);self.assertEqual(result["facts_updated"],4)
        for fact in self.facts():
            prior=before[fact["source_ref"]["cell"]]
            for field in ("value","raw_value","raw_unit","currency","period","scope","year"):self.assertEqual(fact[field],prior[field])
            self.assertEqual(fact["source_ref"]["normalization"]["original_metric"],"receivable_amount")
            self.assertEqual(fact["source_ref"]["normalization"]["definition_review"]["extraction_processing_id"],"definition-owner")
        rebuilt,_=materialize(self.extractions,self.batch,self.doc["document_id"],"deepseek-flash")
        from service.temporal_semantics import stamp_source_provenance
        stamp_source_provenance(self.doc["sha256"],rebuilt,self.detail)
        with self.svc.store.connect() as db:count=overlay_saved_definitions(db,"p",rebuilt)
        self.assertEqual(count,4);self.assertEqual({fact["metric"] for fact in rebuilt},{"receivable_gross_balance","receivable_net_value"})
        rebuilt[0]["source"]["normalization"]["source_fingerprint"]="changed"
        with self.svc.store.connect() as db:self.assertEqual(overlay_saved_definitions(db,"p",rebuilt),3)

    def test_completed_definitions_are_reused_with_original_model_owner(self):
        with patch("service.definition_model.review_definitions",side_effect=self.model):review_project(self.svc,"p",["receivable_amount"],self.runtime)
        with patch("service.definition_model.review_definitions",side_effect=AssertionError("already-reviewed original sources must reuse")):
            report=review_project(self.svc,"p",["receivable_amount"],self.runtime|{"processing_id":"later-run","owner_run_id":"later-pi"})
        self.assertEqual(report["model_requests"],0);self.assertEqual(report["reused_verified_groups"],2)
        self.assertEqual({fact["source_ref"]["normalization"]["definition_review"]["owner_run_id"] for fact in self.facts()},{"pi-owner"})
        self.assertEqual(report["audits"][0]["kind"],"revalidated_cached_result")
        self.assertEqual(report["audits"][0]["provenance"],{"processing_id":"definition-owner","owner_run_id":"pi-owner"})
        self.assertEqual(len(report["audits"][0]["revalidated_source_keys"]),4)

    def test_revalidation_registers_missing_historical_report_without_fabricating_it(self):
        with patch("service.definition_model.review_definitions",side_effect=self.model):first=review_project(self.svc,"p",["receivable_amount"],self.runtime)
        before={fact["fact_id"]:fact["definition_review"] for fact in self.facts()}
        with self.svc.store.connect(write=True) as db:db.execute("DELETE FROM fact_definition_reviews WHERE review_id=?",(first["review_id"],))
        with patch("service.definition_model.review_definitions",side_effect=AssertionError("verified cache only")):
            receipt=review_project(self.svc,"p",["receivable_amount"],self.runtime|{"processing_id":"receipt-processing","owner_run_id":"receipt-owner"})
        audit=receipt["audits"][0]
        self.assertTrue(audit["original_registration_missing"])
        self.assertEqual(audit["historical_review_ids"],[first["review_id"]])
        self.assertEqual({fact["fact_id"]:fact["definition_review"] for fact in self.facts()},before)
        with self.svc.store.connect() as db:self.assertIsNone(db.execute("SELECT 1 FROM fact_definition_reviews WHERE review_id=?",(first["review_id"],)).fetchone())

    def test_corrupt_reuse_cache_is_not_registered_or_silently_reinferred(self):
        with patch("service.definition_model.review_definitions",side_effect=self.model):first=review_project(self.svc,"p",["receivable_amount"],self.runtime)
        with self.svc.store.connect(write=True) as db:db.execute("UPDATE fact_definition_cache SET result_json=json_set(result_json,'$._review_provenance.owner_run_id','forged')")
        with patch("service.definition_model.review_definitions",side_effect=AssertionError("no hidden retry")):
            with self.assertRaisesRegex(ValueError,"definition_reuse_cache_owner_or_hash_mismatch"):
                review_project(self.svc,"p",["receivable_amount"],self.runtime|{"processing_id":"new-run","owner_run_id":"new-owner"})
        with self.svc.store.connect() as db:self.assertEqual(db.execute("SELECT count(*) FROM fact_definition_reviews").fetchone()[0],1)

    def test_reuse_cannot_register_a_fact_that_no_longer_matches_accepted_decision(self):
        with patch("service.definition_model.review_definitions",side_effect=self.model):review_project(self.svc,"p",["receivable_amount"],self.runtime)
        with self.svc.store.connect(write=True) as db:db.execute("UPDATE facts SET metric='unreviewed_replacement'")
        with patch("service.definition_model.review_definitions",side_effect=AssertionError("no hidden inference")):
            with self.assertRaisesRegex(ValueError,"definition_reuse_active_fact_mismatch"):
                review_project(self.svc,"p",["receivable_amount"],self.runtime|{"processing_id":"new-run","owner_run_id":"new-owner"})

    def test_output_limit_bisects_without_repeating_parent_and_counts_all_requests(self):
        from service.definition_model import DefinitionOutputLimitError
        calls=[]
        def model(groups,*args):
            ids=[group["group_id"] for group in groups];calls.append(ids)
            if len(groups)>1:raise DefinitionOutputLimitError([{"outcome":"output_limit","group_ids":ids}],ids)
            return self.model(groups)
        with patch("service.definition_model.review_definitions",side_effect=model):report=review_project(self.svc,"p",["receivable_amount"],self.runtime)
        self.assertEqual([len(part) for part in calls],[2,1,1])
        self.assertEqual(set(calls[0]),set(calls[1]+calls[2]))
        self.assertEqual(report["status"],"reviewed");self.assertEqual(report["model_requests"],3)
        self.assertEqual(report["facts_updated"],4);self.assertEqual(report["failures"],[])
        self.assertEqual(report["split_attempts"][0]["children"],[calls[1],calls[2]])
        self.assertEqual(len(report["failed_attempts"]),1)

    def test_single_group_limit_is_terminal_and_keeps_successful_sibling(self):
        from service.definition_model import DefinitionOutputLimitError
        calls=[]
        def model(groups,*args):
            ids=[group["group_id"] for group in groups];calls.append(ids)
            if len(groups)>1 or len(calls)==3:raise DefinitionOutputLimitError([{"outcome":"output_limit","group_ids":ids}],ids)
            return self.model(groups)
        with patch("service.definition_model.review_definitions",side_effect=model):
            with self.assertRaisesRegex(ValueError,"definition_output_limit") as caught:review_project(self.svc,"p",["receivable_amount"],self.runtime)
        report=caught.exception.definition_report
        self.assertEqual([len(part) for part in calls],[2,1,1]);self.assertEqual(report["model_requests"],3)
        self.assertEqual(report["status"],"failed");self.assertEqual(report["facts_updated"],2)
        self.assertEqual(report["groups_pending"],1);self.assertEqual(len(report["split_attempts"]),1)

    def test_transport_failure_never_triggers_batch_splitting(self):
        with patch("service.definition_model.review_definitions",side_effect=RuntimeError("HTTP 402 fixture")) as model:
            with self.assertRaises(RuntimeError) as caught:review_project(self.svc,"p",["receivable_amount"],self.runtime)
        self.assertEqual(model.call_count,1)
        self.assertEqual(caught.exception.definition_report["split_attempts"],[])

    def test_limit_during_repair_commits_already_valid_groups_without_reasking_them(self):
        from service.definition_model import DefinitionOutputLimitError
        def model(groups,*args):
            ids=[group["group_id"] for group in groups]
            partial=self.model(groups[:1]);partial["partial_coverage"]={"original_group_ids":ids,"pending_group_ids":ids[1:]}
            partial["attempts"]=[{"group_ids":ids,"extractions":partial["extractions"]},{"outcome":"output_limit","group_ids":ids[1:]}]
            raise DefinitionOutputLimitError(partial["attempts"],ids[1:],partial)
        with patch("service.definition_model.review_definitions",side_effect=model) as infer:
            with self.assertRaisesRegex(ValueError,"definition_output_limit") as caught:review_project(self.svc,"p",["receivable_amount"],self.runtime)
        report=caught.exception.definition_report
        self.assertEqual(infer.call_count,1)
        self.assertEqual(report["groups_reviewed"],1);self.assertEqual(report["facts_updated"],2)
        self.assertEqual(report["model_requests"],2)
        self.assertEqual(report["groups_pending"],1)

    def test_legacy_strictly_accepted_quotes_are_reused_without_model_or_owner_change(self):
        from service.definition_model import LEGACY_CACHE_HASH
        with patch("service.definition_model.review_definitions",side_effect=self.model):review_project(self.svc,"p",["receivable_amount"],self.runtime)
        with self.svc.store.connect(write=True) as db:
            for row in db.execute("SELECT fact_id,source_json FROM facts").fetchall():
                ref=json.loads(row["source_json"]);ref["normalization"]["definition_review"]["cache_hash"]=LEGACY_CACHE_HASH
                db.execute("UPDATE facts SET source_json=? WHERE fact_id=?",(json.dumps(ref),row["fact_id"]))
        with patch("service.definition_model.review_definitions",side_effect=AssertionError("strict accepted results are compatible")):
            report=review_project(self.svc,"p",["receivable_amount"],self.runtime|{"owner_run_id":"next-owner","processing_id":"next-processing"})
        self.assertEqual(report["reused_verified_groups"],2)
        self.assertEqual({fact["definition_review"]["owner_run_id"] for fact in self.facts()},{"pi-owner"})

    def test_split_restores_original_id_without_losing_previous_request_members(self):
        with self.svc.store.connect(write=True) as db:
            for row in db.execute("SELECT fact_id,source_json FROM facts").fetchall():
                ref=json.loads(row["source_json"])
                ref["normalization"]["original_metric"]="original_before_wrong_alias"
                db.execute("UPDATE facts SET source_json=? WHERE fact_id=?",(json.dumps(ref),row["fact_id"]))
        with patch("service.definition_model.review_definitions",side_effect=self.model):first=review_project(self.svc,"p",["receivable_amount"],self.runtime)
        with patch("service.definition_model.review_definitions",side_effect=AssertionError("already reviewed original members")):
            resumed=review_project(self.svc,"p",["receivable_amount"],self.runtime|{"processing_id":"resumed","owner_run_id":"next-owner"})
        self.assertEqual(first["facts_total"],4);self.assertEqual(resumed["facts_total"],4)
        self.assertEqual(resumed["groups_reviewed"],first["groups_reviewed"])
        self.assertEqual(resumed["model_requests"],0)

    def test_later_failure_persists_partial_report_history_and_resumes_only_unfinished_group(self):
        from service.definition_model import DefinitionValidationError
        calls=[]
        def model(groups,*args):
            calls.append(groups[0]["group_id"])
            if len(calls)==2:
                with self.svc.store.connect() as db:
                    partial=json.loads(db.execute("SELECT report_json FROM fact_definition_reviews").fetchone()[0])
                    self.assertEqual((partial["status"],partial["groups_reviewed"],partial["facts_updated"]),("running",1,2))
                raise DefinitionValidationError([{"group_id":calls[-1],"reason":"fixture_invalid_quote"}],[{"extractions":[]},{"extractions":[]}])
            return self.model(groups)
        single=lambda rows,**kwargs:([row] for row in rows)
        with patch("service.definition_semantics.definition_chunks",side_effect=single),patch("service.definition_model.review_definitions",side_effect=model):
            with self.assertRaisesRegex(ValueError,"definition_invalid_after_repair") as caught:review_project(self.svc,"p",["receivable_amount"],self.runtime)
        report=caught.exception.definition_report
        self.assertEqual((report["status"],report["groups_reviewed"],report["facts_updated"],report["groups_pending"]),("failed",1,2,1))
        self.assertEqual(report["model_requests"],3)
        with self.svc.store.connect() as db:
            saved=json.loads(db.execute("SELECT report_json FROM fact_definition_reviews WHERE review_id=?",(report["review_id"],)).fetchone()[0])
            self.assertEqual(saved["audits"],report["audits"])
            key=saved["audits"][0]["cache_key"]
            accepted=json.loads(db.execute("SELECT result_json FROM fact_definition_cache WHERE cache_key=?",(key,)).fetchone()[0])
            self.assertEqual(accepted["_review_provenance"]["owner_run_id"],"pi-owner")
            self.assertEqual(db.execute("SELECT count(*) FROM fact_history WHERE processing_id='definition-owner'").fetchone()[0],2)
        pending=[]
        def resume(groups,*args):pending.extend(group["group_id"] for group in groups);return self.model(groups)
        with patch("service.definition_model.review_definitions",side_effect=resume):
            later=review_project(self.svc,"p",["receivable_amount"],self.runtime|{"processing_id":"resume-processing","owner_run_id":"resume-owner"})
        self.assertEqual(pending,[calls[-1]]);self.assertEqual(later["reused_verified_groups"],1)
        self.assertEqual(later["status"],"reviewed")
        self.assertEqual({fact["definition_review"]["owner_run_id"] for fact in self.facts()},{"pi-owner","resume-owner"})

    def test_failed_family_does_not_discard_other_inflight_success(self):
        # Independent synthetic concepts, no company/financial-word dispatch.
        for index,item in enumerate(self.extractions[1:]):item["attributes"]["metric"]=f"concept_{index}"
        facts,issues=materialize(self.extractions,self.batch,self.doc["document_id"],"deepseek-flash")
        self.svc._commit_semantic_batch("p",self.doc["document_id"],"new-fixture",self.batch,facts,issues,self.detail)
        started=threading.Event()
        def model(groups,*args):
            if groups[0]["original_metric"]=="concept_0":
                self.assertTrue(started.wait(2))
                raise ValueError("fixture_failed_family")
            started.set();time.sleep(0.1)
            return self.model(groups)
        with patch("service.definition_model.review_definitions",side_effect=model):
            with self.assertRaisesRegex(ValueError,"fixture_failed_family") as caught:review_project(self.svc,"p",["concept_0","concept_1"],self.runtime)
        report=caught.exception.definition_report
        self.assertEqual(report["status"],"failed");self.assertEqual(report["facts_updated"],2)
        self.assertEqual(len(report["audits"]),1)
        self.assertEqual(sum(bool(fact.get("definition_review")) for fact in self.facts()),2)

    def test_shared_batch_commit_preserves_saved_definition_and_later_catalog_cannot_merge_it(self):
        from service.catalog_semantics import canonicalize_project
        with patch("service.definition_model.review_definitions",side_effect=self.model):review_project(self.svc,"p",["receivable_amount"],self.runtime)
        before={fact["source_ref"]["cell"]:fact for fact in self.facts()}
        rebuilt,issues=materialize(self.extractions,self.batch,self.doc["document_id"],"deepseek-flash")
        self.svc._commit_semantic_batch("p",self.doc["document_id"],"replay-owner",self.batch,rebuilt,issues,self.detail)
        for fact in self.facts():
            self.assertEqual(fact["metric"],before[fact["source_ref"]["cell"]]["metric"])
            self.assertEqual(fact["definition_review"]["owner_run_id"],"pi-owner")
        def bad_alias(profiles,*args):
            self.assertTrue(all(profile.get("definition_locked") for profile in profiles))
            return {"keep":["receivable_net_value"],"aliases":{"receivable_gross_balance":{"canonical_metric":"receivable_net_value","canonical_label":"错误共名","reason":"错误尝试合并不同口径","span":[0,1],"extraction_text":"marker"}}},[],1
        with patch("service.catalog_semantics._call_model",side_effect=bad_alias):
            result=canonicalize_project(self.svc.store,"p",self.runtime|{"force":True})
        self.assertEqual(result["status"],"reviewed")
        self.assertEqual({fact["metric"] for fact in self.facts()},{"receivable_gross_balance","receivable_net_value"})
        with patch("service.catalog_semantics._call_model",side_effect=AssertionError("verified definitions reuse")):
            self.assertEqual(canonicalize_project(self.svc.store,"p",self.runtime)["requests"],0)

    def test_explicit_empty_query_filter_never_returns_all_facts(self):
        self.assertEqual(self.svc.query_financial_data("p")["data"]["total"],4)
        for key in ("periods","metrics","statements","version"):
            result=self.svc.query_financial_data("p",{key:[]})["data"]
            self.assertEqual(result["items"],[]);self.assertEqual(result["total"],0)

    def test_family_batches_receive_previously_committed_model_definitions(self):
        seen=[]
        def model(groups,known,*args):seen.append(known);return self.model(groups)
        with patch("service.definition_semantics.definition_chunks",side_effect=lambda rows,**kwargs:([row] for row in rows)),patch("service.definition_model.review_definitions",side_effect=model):
            report=review_project(self.svc,"p",["receivable_amount"],self.runtime)
        self.assertEqual(len(seen),2);self.assertEqual(report["groups_reviewed"],2)
        self.assertFalse(any(item["definitions"] for item in seen[0]));self.assertTrue(any(item["definitions"] for item in seen[1]))

    def test_missing_group_response_never_partially_commits(self):
        with patch("service.definition_model.review_definitions",return_value={"decisions":[],"unresolved":[],"requests":1}):
            with self.assertRaisesRegex(ValueError,"coverage_invalid"):review_project(self.svc,"p",["receivable_amount"],self.runtime)
        self.assertEqual({fact["metric"] for fact in self.facts()},{"receivable_amount"})

    def test_concurrent_new_extraction_is_not_overwritten_by_old_definition(self):
        def fresh(groups,*args):
            result=self.model(groups)
            self.extractions[1]["attributes"]["label"]="另一会话重新解释的定义"
            facts,issues=materialize(self.extractions,self.batch,self.doc["document_id"],"deepseek-flash")
            self.svc._commit_semantic_batch("p",self.doc["document_id"],"other-owner",self.batch,facts,issues,self.detail)
            return result
        with patch("service.definition_model.review_definitions",side_effect=fresh):report=review_project(self.svc,"p",["receivable_amount"],self.runtime)
        self.assertEqual(report["status"],"needs_review");self.assertEqual(len(report["stale_sources"]),2)
        changed=[fact for fact in self.facts() if fact["source_ref"]["row"]==2]
        self.assertEqual({fact["metric"] for fact in changed},{"receivable_amount"})

    def test_concurrent_date_review_is_preserved_when_definition_commits(self):
        def reviewed_dates(groups,*args):
            result=self.model(groups)
            with self.svc.store.connect(write=True) as db:
                for row in db.execute("SELECT fact_id,source_json FROM facts").fetchall():
                    ref=json.loads(row["source_json"]);ref["normalization"]["period_start"]="";ref["normalization"]["period_end"]="2024-01-01"
                    db.execute("UPDATE facts SET period='2024-01-01',year=2024,source_json=? WHERE fact_id=?",(json.dumps(ref,ensure_ascii=False),row["fact_id"]))
            return result
        with patch("service.definition_model.review_definitions",side_effect=reviewed_dates):report=review_project(self.svc,"p",["receivable_amount"],self.runtime)
        self.assertEqual(report["status"],"reviewed")
        self.assertEqual({fact["period"] for fact in self.facts()},{"2024-01-01"})
        self.assertEqual({fact["period_end"] for fact in self.facts()},{"2024-01-01"})

    def test_concurrent_definition_change_with_same_metric_and_label_is_not_overwritten(self):
        def concurrent_definition(groups,*args):
            result=self.model(groups)
            with self.svc.store.connect(write=True) as db:
                for row in db.execute("SELECT fact_id,metric,source_json FROM facts").fetchall():
                    ref=json.loads(row["source_json"]);meta=ref["normalization"]
                    meta["definition_review"]={"status":"reviewed","source_fingerprint":meta["source_fingerprint"],"owner_run_id":"other-pi",
                                               "after":{"metric":row["metric"],"label":meta["label"],"definition":"另一会话完成的定义","definition_scope":"另一明确口径"}}
                    db.execute("UPDATE facts SET source_json=? WHERE fact_id=?",(json.dumps(ref,ensure_ascii=False),row["fact_id"]))
            return result
        with patch("service.definition_model.review_definitions",side_effect=concurrent_definition):
            report=review_project(self.svc,"p",["receivable_amount"],self.runtime)
        self.assertEqual(report["facts_updated"],0);self.assertEqual(report["status"],"needs_review")
        self.assertEqual(len(report["stale_sources"]),4)
        self.assertEqual({fact["definition_scope"] for fact in self.facts()},{"另一明确口径"})
        self.assertEqual({fact["definition_review"]["owner_run_id"] for fact in self.facts()},{"other-pi"})

    def test_concurrent_same_input_uses_accepted_definitions_and_original_owner(self):
        def infer(groups,known,runtime,*args):
            result=self.model(groups)
            for item in result["decisions"]:item["definition"]=runtime["owner_run_id"]+" 定义措辞"
            time.sleep(0.15);return result
        with patch("service.definition_model.review_definitions",side_effect=infer):
            with ThreadPoolExecutor(max_workers=2) as pool:
                reports=list(pool.map(lambda owner:review_project(self.svc,"p",["receivable_amount"],self.runtime|{"owner_run_id":owner,"processing_id":owner}),["definition-A","definition-B"]))
        self.assertEqual({report["status"] for report in reports},{"reviewed"})
        self.assertEqual(sum(report["model_requests"] for report in reports),1)
        self.assertEqual(reports[0]["audits"],reports[1]["audits"])
        owner=reports[0]["audits"][0]["provenance"]["owner_run_id"]
        self.assertEqual({fact["definition_review"]["owner_run_id"] for fact in self.facts()},{owner})
        self.assertEqual({fact["definition"] for fact in self.facts()},{owner+" 定义措辞"})
