import json
import re
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

from service.core import FinanceService
from service.normalization import unit_info
from service.semantic import materialize, table_batches, pack_slices, render_group, SCHEMA_HASH


class PiDocumentProcessingTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        self.svc=FinanceService(self.root);self.svc.create_project("alpha","测试项目");self.svc.create_project("beta","独立项目")

    def tearDown(self):
        for pool in (self.svc.processing_pool,self.svc.pool,self.svc.analysis_pool,self.svc.embedding_pool):pool.shutdown(wait=True,cancel_futures=True)
        self.tmp.cleanup()

    def register(self, name="财报2024.csv"):
        path=self.root/"uploads"/name
        path.write_text("示例公司2024年合并利润表,本期,上期\n销售费用,12.5,10\n研发费用,2.25,2\n",encoding="utf-8")
        return self.svc.register_document("alpha",str(path),name)["data"]

    def wait(self, processing):
        deadline=time.monotonic()+30
        while time.monotonic()<deadline:
            state=self.svc.get_processing_status("alpha",processing)["data"]
            if state["state"] in {"completed","ready","needs_review","partial","failed","cancelled"}:return state
            time.sleep(.02)
        self.fail("processing timeout")

    def test_registration_has_no_implicit_ingestion_and_catalog_has_real_paths(self):
        with patch("service.processing.parse_document",side_effect=AssertionError("must not parse on upload")):
            doc=self.register()
        self.assertEqual(doc["state"],"registered");self.assertEqual(doc["fact_count"],0)
        catalog=self.svc.get_data_catalog("alpha")["data"]
        self.assertTrue(Path(catalog["index_path"]).is_file());self.assertTrue(Path(catalog["database_path"]).is_file())
        self.assertEqual(catalog["counts"]["facts"],0);self.assertFalse(catalog["embedding_enabled"])
        self.assertEqual(self.svc.get_data_catalog("beta")["data"]["counts"]["documents"],0)

    def test_real_langextract_uses_pi_bridge_and_commits_dynamic_facts(self):
        requests=[]
        class Bridge(BaseHTTPRequestHandler):
            def log_message(self,*args):pass
            def do_POST(self):
                payload=json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                requests.append({"path":self.path,"model":payload["model"],"format":payload.get("response_format")})
                text=payload["messages"][-1]["content"]
                if "[[TEMPORAL_REVIEW]]" in text:
                    count=len(set(re.findall(r"\[\[GROUP:([a-f0-9]{64})\]\]",text)))
                    extracts=[{"temporal_review":"[[TEMPORAL_REVIEW]]","temporal_review_attributes":{"reviewed_count":count,"flag_count":0,"keep_count":count}}]
                    body=json.dumps({"id":"temporal","object":"chat.completion","created":1,"model":payload["model"],"choices":[{"index":0,"message":{"role":"assistant","content":json.dumps({"extractions":extracts},ensure_ascii=False)},"finish_reason":"stop"}],"usage":{"prompt_tokens":10,"completion_tokens":20,"total_tokens":30}},ensure_ascii=False).encode()
                    self.send_response(200);self.send_header("Content-Type","application/json");self.send_header("Content-Length",str(len(body)));self.end_headers();self.wfile.write(body)
                    return
                if "[[CATALOG]]" in text:
                    extracts=[{"catalog_review":"[[CATALOG]]","catalog_review_attributes":{"reviewed_count":2,"merge_count":0,"keep_count":2,"keep_summary":"销售费用与研发费用含义不同，分别保留"}}]
                    body=json.dumps({"id":"catalog","object":"chat.completion","created":1,"model":payload["model"],"choices":[{"index":0,"message":{"role":"assistant","content":json.dumps({"extractions":extracts},ensure_ascii=False)},"finish_reason":"stop"}],"usage":{"prompt_tokens":10,"completion_tokens":20,"total_tokens":30}},ensure_ascii=False).encode()
                    self.send_response(200);self.send_header("Content-Type","application/json");self.send_header("Content-Length",str(len(body)));self.end_headers();self.wfile.write(body)
                    return
                table=re.findall(r"目标区\s*\[\[T(\d+)\]\]",text)[-1]
                cols=[{"column":2,"period":"2024-FY","start":"2024-01-01","end":"2024-12-31","unit":"百万元","currency":"CNY","version":"original","dimensions":{}},
                      {"column":3,"period":"2023-FY","start":"2023-01-01","end":"2023-12-31","unit":"百万元","currency":"CNY","version":"restated","dimensions":{}}]
                extracts=[{"table_schema":f"[[T{table}]]","table_schema_attributes":{"company":"示例公司","statement":"income","scope":"consolidated_CAS","currency":"CNY","unit":"百万元","columns_json":json.dumps(cols),"skipped_rows_json":"[]"}}]
                for row,metric,label in [(2,"selling_expenses","销售费用"),(3,"research_expenses","研发费用")]:
                    extracts.append({"financial_row":f"[[T{table}:R{row}]]","financial_row_attributes":{"metric":metric,"label":label,"unit":"","dimensions_json":"{}","columns_json":""}})
                body=json.dumps({"id":"test","object":"chat.completion","created":1,"model":payload["model"],"choices":[{"index":0,"message":{"role":"assistant","content":json.dumps({"extractions":extracts},ensure_ascii=False)},"finish_reason":"stop"}],"usage":{"prompt_tokens":10,"completion_tokens":20,"total_tokens":30}},ensure_ascii=False).encode()
                self.send_response(200);self.send_header("Content-Type","application/json");self.send_header("Content-Length",str(len(body)));self.end_headers();self.wfile.write(body)
        server=ThreadingHTTPServer(("127.0.0.1",0),Bridge)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            doc=self.register()
            runtime={"base_url":f"http://127.0.0.1:{server.server_port}/session-test/v1","api_key":"test-bridge-token","model":"deepseek-flash","max_tokens":16000}
            state=self.wait(self.svc.start_document_processing("alpha",[doc["document_id"]],"session-test",runtime)["data"]["processing_id"])
            self.assertEqual(state["state"],"completed",state)
            self.assertEqual(state["fact_count"],4)
            facts=self.svc.query_financial_data("alpha",{"metric":"selling_expenses"})["data"]["items"]
            self.assertEqual(len(facts),2)
            fact=next(f for f in facts if f["year"]==2024)
            self.assertEqual(fact["value"],"12500000.0");self.assertEqual(fact["normalized_unit"],"CNY")
            self.assertEqual(fact["source_ref"]["cell"],"B2");self.assertEqual(fact["normalization_engine"],"LangExtract")
            self.assertEqual(facts[0]["label"],"销售费用")
            self.assertEqual(len(self.svc.get_financial_metrics("alpha",["研发费用"])["data"]["items"]),2)
            self.assertTrue(all(r["path"]=="/session-test/v1/chat/completions" for r in requests))
            self.assertTrue(all(r["format"]=={"type":"json_object"} for r in requests))
            details=self.svc.get_normalization_details("alpha",doc["document_id"])["data"]
            self.assertEqual(details["batches"][0]["result"]["issues"],[])
            self.assertEqual(details["batches"][0]["result"]["extraction_processing_id"],state["processing_id"])
            # Reprocessing writes a new history version and never stores bridge credentials.
            runtime["force"]=True
            second=self.wait(self.svc.start_document_processing("alpha",[doc["document_id"]],"session-test-2",runtime)["data"]["processing_id"])
            self.assertEqual(second["state"],"completed",second)
            self.assertEqual(self.svc.get_normalization_details("alpha",doc["document_id"])["data"]["archived_fact_count"],4)
            with self.svc.store.connect() as db:
                saved="".join(r[0] for r in db.execute("SELECT state_json FROM processing_runs"))
            self.assertNotIn("test-bridge-token",saved)
        finally:server.shutdown();server.server_close();thread.join(timeout=3)

    def test_same_document_shared_processing_cancel_does_not_cancel_owner(self):
        doc=self.register();entered=threading.Event();release=threading.Event()
        def normalize(parsed,document_id,config,progress,cancelled,cache_get,cache_put,on_batch,resume_get=None,on_failure=None):
            entered.set();release.wait(5)
            self.assertFalse(cancelled())
            return [],{"issues":[],"completed":0}
        runtime={"base_url":"http://127.0.0.1:1/run/v1","api_key":"test-token","model":"deepseek-flash"}
        with patch("service.processing.normalize_document",normalize):
            first=self.svc.start_document_processing("alpha",[doc["document_id"]],"first",runtime)["data"]
            self.assertTrue(entered.wait(5))
            second=self.svc.start_document_processing("alpha",[doc["document_id"]],"second",runtime)["data"]
            self.assertEqual(second["documents"][0]["shared_processing_id"],first["processing_id"])
            self.svc.cancel_processing("alpha",second["processing_id"])
            self.assertEqual(self.wait(second["processing_id"])["state"],"cancelled")
            release.set();self.assertEqual(self.wait(first["processing_id"])["state"],"completed")

    def test_dependent_session_resumes_when_original_owner_is_cancelled(self):
        doc=self.register();entered=threading.Event();calls=[]
        def normalize(parsed,document_id,config,progress,cancelled,cache_get,cache_put,on_batch,resume_get=None,on_failure=None):
            calls.append(config["base_url"])
            if "first" in config["base_url"]:
                entered.set()
                deadline=time.monotonic()+5
                while not cancelled() and time.monotonic()<deadline:time.sleep(.01)
                raise InterruptedError("cancelled")
            return [],{"issues":[],"completed":0}
        base={"api_key":"test-token","model":"deepseek-flash"}
        with patch("service.processing.normalize_document",normalize):
            first=self.svc.start_document_processing("alpha",[doc["document_id"]],"first",base|{"base_url":"http://127.0.0.1:1/first/v1"})["data"]
            self.assertTrue(entered.wait(5))
            second=self.svc.start_document_processing("alpha",[doc["document_id"]],"second",base|{"base_url":"http://127.0.0.1:1/second/v1"})["data"]
            self.svc.cancel_processing("alpha",first["processing_id"])
            self.assertEqual(self.wait(first["processing_id"])["state"],"cancelled")
            self.assertEqual(self.wait(second["processing_id"])["state"],"completed")
            self.assertEqual(calls,["http://127.0.0.1:1/first/v1","http://127.0.0.1:1/second/v1"])

    def test_table_slices_keep_all_original_rows_and_units(self):
        parsed={"company":"示例公司","report_year":2024,"pages":[{"page":1,"text":"2024年"}],"tables":[{"index":1,"page":1,"rows":[["指标",str(i)] for i in range(70)]}]}
        batches=table_batches(parsed)
        self.assertEqual([r for batch in batches for item in batch for r in item["rows"]],list(range(1,71)))
        self.assertTrue(all(len(batch)==1 for batch in batches))
        for unit,factor,currency in [("百万元",1000000,"CNY"),("百万美元",1000000,"USD"),("千港元",1000,"HKD"),("万股",10000,"股"),("美元/股",1,"USD/share")]:
            self.assertEqual(unit_info(unit)[1:],(factor,currency))

    def test_empty_semantic_columns_are_reported_for_corrective_pass(self):
        batch=[{"table":{"index":0,"page":1,"rows":[["销售费用","12.5"]]},"rows":[1]}]
        extractions=[{"class":"table_schema","text":"[[T0]]","span":[1,7],"attributes":{"statement":"income","columns_json":"[]"}},
                     {"class":"financial_row","text":"[[T0:R1]]","span":[8,19],"attributes":{"metric":"selling_expenses","label":"销售费用"}}]
        facts,issues=materialize(extractions,batch,"doc","deepseek-flash")
        self.assertEqual(facts,[]);self.assertIn("missing_numeric_columns",[i["reason"] for i in issues])

    def test_merged_header_metadata_is_preserved_for_model(self):
        from openpyxl import Workbook
        from service.parser import parse_document
        path=self.root/"uploads"/"merged2024.xlsx"
        book=Workbook();sheet=book.active;sheet.merge_cells("B1:C1");sheet["B1"]="2024年";sheet.append(["项目","调整前","调整后"]);sheet.append(["净利润",1,2]);book.save(path);book.close()
        parsed=parse_document(path,path.name,lambda *_:None,lambda:False,{"ocr":{"mode":"disabled"}})
        self.assertEqual(parsed["tables"][0]["cells"]["B1"]["merged_range"],"B1:C1")
        self.assertIn("B1:C1",table_batches(parsed)[0][0]["text"])

    def test_horizontal_metrics_keep_different_column_units_and_row_dimensions(self):
        batch=[{"table":{"index":0,"page":1,"rows":[["华东","125","30"]]},"rows":[1]}]
        cols=[{"column":2,"metric":"revenue","label":"营业收入","period":"2025-FY","unit":"百万元","currency":"CNY","dimensions":{}},
              {"column":3,"metric":"gross_margin","label":"毛利率","period":"2025-FY","unit":"%","currency":"CNY","dimensions":{}}]
        extractions=[{"class":"table_schema","text":"[[T0]]","span":[0,6],"attributes":{"company":"测试公司","statement":"segment","scope":"consolidated_CAS","columns_json":json.dumps(cols)}},
                     {"class":"financial_row","text":"[[T0:R1]]","span":[7,17],"attributes":{"metric":"segment_data","label":"分部指标","unit":"百万元","dimensions_json":'{"region":"华东"}'}}]
        facts,issues=materialize(extractions,batch,"doc","deepseek-flash")
        self.assertEqual(issues,[]);self.assertEqual([f["metric"] for f in facts],["revenue","gross_margin"])
        self.assertEqual([f["value"] for f in facts],["125000000","30"])
        self.assertEqual([f["currency"] for f in facts],["CNY","percent"])
        self.assertEqual(facts[1]["source"]["normalization"]["dimensions"],{"region":"华东","financial_item":"segment_data"})
        self.assertEqual(facts[1]["source"]["normalization"]["dimension_labels"],{"financial_item":"分部指标"})

    def test_parallel_native_pdf_workers_preserve_identical_sources(self):
        from concurrent.futures import ThreadPoolExecutor
        source=Path(__file__).resolve().parents[2]/"benchmark/versions/v0.3-normalization/inputs/10_moutai_2024_pages5-6.pdf"
        if not source.exists():self.skipTest("native-PDF benchmark source not installed")
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures=[pool.submit(self.svc._parse_native_pdf,source,source.name,lambda *_:None,lambda:False,{"ocr":{"mode":"disabled"}}) for _ in range(2)]
            first,second=[f.result(timeout=30) for f in futures]
        self.assertEqual(first,second);self.assertEqual(len(first["pages"]),2)
        self.assertEqual(len(first["tables"]),5)
        self.assertTrue(first["tables"][1]["cells"]["B2"]["bbox"])

    def test_growth_percentage_cannot_be_materialized_as_revenue_amount(self):
        batch=[{"table":{"index":0,"page":1,"rows":[["指标","本期收入","本期比上年增减(%)"],["营业收入","100","15.71"]]},"rows":[1,2]}]
        cols=[{"column":2,"period":"2024-FY","unit":"元","currency":"CNY"},{"column":3,"period":"2024-FY","unit":"%","currency":"percent"}]
        extracts=[{"class":"table_schema","text":"[[T0]]","span":[0,6],"attributes":{"company":"测试公司","statement":"income","columns_json":json.dumps(cols)}},
                  {"class":"financial_row","text":"[[T0:R2]]","span":[7,17],"attributes":{"metric":"revenue","label":"营业收入"}}]
        facts,issues=materialize(extracts,batch,"doc","deepseek-flash")
        self.assertEqual([f["value"] for f in facts],["100"])
        self.assertIn("metric_unit_mismatch",[i["reason"] for i in issues])
        cols[1].update(metric="revenue_yoy",label="营业收入同比增减率")
        extracts[0]["attributes"]["columns_json"]=json.dumps(cols)
        facts,issues=materialize(extracts,batch,"doc","deepseek-flash")
        self.assertEqual(issues,[]);self.assertEqual(facts[1]["metric"],"revenue_yoy")

    def test_period_column_label_does_not_override_financial_metric_label(self):
        batch=[{"table":{"index":0,"page":1,"rows":[["存货","125"]]},"rows":[1]}]
        cols=[{"column":2,"label":"本期期末数","period":"2024-12-31","unit":"元","currency":"CNY"}]
        extracts=[{"class":"table_schema","text":"[[T0]]","span":[0,6],"attributes":{"company":"测试公司","statement":"balance","columns_json":json.dumps(cols)}},
                  {"class":"financial_row","text":"[[T0:R1]]","span":[7,17],"attributes":{"metric":"inventory","label":"存货"}}]
        facts,issues=materialize(extracts,batch,"doc","deepseek-flash")
        self.assertEqual(issues,[]);self.assertEqual(facts[0]["source"]["normalization"]["label"],"存货")

    def test_inference_packing_keeps_original_slices_and_deduplicates_context(self):
        parsed={"company":"示例公司","report_year":2024,"pages":[{"page":1,"text":"同一页背景。"*500}],"tables":[{"index":i,"page":1,"rows":[["指标","2024年度"],["金额","100"]]} for i in range(3)]}
        original=table_batches(parsed);groups=pack_slices(original)
        self.assertEqual(len(groups),1)
        self.assertEqual(sorted(p["table"]["index"] for group in groups for p in group),[0,1,2])
        self.assertLess(len(render_group(groups[0])),sum(len(batch[0]["text"]) for batch in original))
        duplicate=pack_slices([original[0],original[0]])
        self.assertEqual(len(duplicate),2)

    def test_resume_re_materializes_saved_extraction_without_model_requests(self):
        from service.parser import parse_document
        doc=self.register();document_id=doc["document_id"]
        parsed=parse_document(self.root/doc["relative_path"],doc["original_name"],lambda *_:None,lambda:False,{})
        self.svc._persist_prepared("alpha",document_id,parsed)
        batch=table_batches(parsed)[0]
        cols=[{"column":2,"label":"本期","period":"2024-FY","unit":"百万元","currency":"CNY"},{"column":3,"label":"上期","period":"2023-FY","unit":"百万元","currency":"CNY"}]
        extracts=[{"class":"table_schema","text":"[[T0]]","span":[0,6],"attributes":{"company":"示例公司","statement":"income","columns_json":json.dumps(cols)}}]
        for r,metric,label in [(2,"selling_expenses","销售费用"),(3,"research_expenses","研发费用")]:
            extracts.append({"class":"financial_row","text":f"[[T0:R{r}]]","span":[10*r,10*r+9],"attributes":{"metric":metric,"label":label}})
        facts,issues=materialize(extracts,batch,document_id,"deepseek-flash")
        for f in facts:f["source"]["normalization"]["label"]="本期或上期（模拟旧版错误）"
        self.svc._commit_semantic_batch("alpha",document_id,"previous-run",batch,facts,issues,{"engine":"LangExtract","version":"langextract-finance-0.3.1","schema_hash":SCHEMA_HASH,"model":"deepseek-flash","extractions":extracts})
        with self.svc.store.connect(write=True) as db:db.execute("UPDATE documents SET state='cancelled' WHERE document_id=?",(document_id,))
        runtime={"base_url":"http://127.0.0.1:1/resume/v1","api_key":"test-token","model":"deepseek-flash"}
        with patch("service.processing.review_temporal_project",return_value={"status":"reviewed","model_requests":0}) as temporal, patch("service.processing.canonicalize_project",return_value={"status":"reviewed","requests":0}) as catalog, patch("langextract.extract",side_effect=AssertionError("resume must not invoke model")) as invoke:
            result=self.wait(self.svc.start_document_processing("alpha",[document_id],"resume",runtime)["data"]["processing_id"])
        catalog.assert_called_once();temporal.assert_called_once()
        self.assertEqual(temporal.call_args.args[2]["owner_run_id"],"resume")
        self.assertTrue(temporal.call_args.args[2]["processing_id"])
        self.assertEqual(result["state"],"completed",result);invoke.assert_not_called()
        report=result["documents"][0]["normalization"]
        self.assertEqual(report["resumed_batches"],1);self.assertEqual(report["requests"],0)
        self.assertEqual({f["label"] for f in self.svc.query_financial_data("alpha")["data"]["items"]},{"销售费用","研发费用"})
        details=self.svc.get_normalization_details("alpha",document_id,table_id=document_id+":t0",limit=1)["data"]
        self.assertEqual(details["total"],1);self.assertEqual(details["batches"][0]["result"]["extraction_processing_id"],"previous-run")
        self.assertEqual(self.svc.get_normalization_details("alpha",document_id,offset=1)["data"]["batches"],[])
        # Fully verified current facts skip redundant commits but still review
        # the whole project, regardless of the previous review state.
        with patch("service.processing.review_temporal_project",return_value={"status":"reviewed","model_requests":0}) as temporal, patch("service.processing.canonicalize_project",return_value={"status":"reviewed","requests":0}) as catalog, patch("service.processing.normalize_document",side_effect=AssertionError("ready document must reuse current result")):
            ready=self.wait(self.svc.start_document_processing("alpha",[document_id],"ready-reuse",runtime)["data"]["processing_id"])
        self.assertEqual(ready["state"],"completed",ready);catalog.assert_called_once();temporal.assert_called_once()
        deadline=time.monotonic()+3
        while ready["processing_id"] in self.svc.processing_flags and time.monotonic()<deadline:time.sleep(.01)
        with self.svc.store.connect(write=True) as db:db.execute("UPDATE documents SET state='needs_review' WHERE document_id=?",(document_id,))
        with patch("service.processing.review_temporal_project",return_value={"status":"reviewed","model_requests":0}) as temporal, patch("service.processing.canonicalize_project",return_value={"status":"reviewed","requests":0}) as catalog, patch("langextract.extract",side_effect=AssertionError("saved table extraction must resume")):
            resumed=self.wait(self.svc.start_document_processing("alpha",[document_id],"review-reuse",runtime)["data"]["processing_id"])
        self.assertEqual(resumed["state"],"completed",resumed);catalog.assert_called_once();temporal.assert_called_once()
        self.assertEqual(resumed["documents"][0]["normalization"]["reused_committed_batches"],1)
        self.assertTrue(resumed["documents"][0]["normalization"]["skipped_materialization"])
        deadline=time.monotonic()+3
        while resumed["processing_id"] in self.svc.processing_flags and time.monotonic()<deadline:time.sleep(.01)
        with patch("service.processing.review_definition_project",return_value={"status":"reviewed","model_requests":1}) as definitions, patch("service.processing.review_temporal_project",return_value={"status":"needs_review","model_requests":0}) as temporal, patch("service.processing.canonicalize_project",return_value={"status":"reviewed","requests":0}), patch("service.processing.normalize_document",side_effect=AssertionError("definition-only review must reuse table output")):
            checked=self.wait(self.svc.start_document_processing("alpha",[document_id],"definition-run",runtime|{"review_metrics":["selling_expenses"]})["data"]["processing_id"])
        self.assertEqual(checked["state"],"needs_review");definitions.assert_called_once();temporal.assert_called_once()
        self.assertEqual(definitions.call_args.args[2],["selling_expenses"])
        self.assertEqual(definitions.call_args.args[3]["owner_run_id"],"definition-run")
        self.assertEqual(definitions.call_args.args[3]["processing_id"],checked["processing_id"])
        self.assertEqual(checked["definition_review"]["status"],"reviewed")

    def test_failed_directory_defers_dependent_review_and_resume_keeps_saved_facts(self):
        from service.parser import parse_document
        from service.semantic import VERSION
        from service.tests.test_semantic_sources import mappings
        doc=self.register();did=doc['document_id']
        parsed=parse_document(self.root/doc['relative_path'],doc['original_name'],lambda *_:None,lambda:False,{})
        self.svc._persist_prepared('alpha',did,parsed);batch=table_batches(parsed)[0]
        cols=[{'column':2,'period':'2024-FY','unit':'元','currency':'CNY'},{'column':3,'period':'2023-FY','unit':'元','currency':'CNY'}]
        ex=mappings(0,2,'selling_expenses',cols)+mappings(0,3,'research_expenses',cols)[1:]
        facts,issues=materialize(ex,batch,did,'deepseek-flash')
        self.svc._commit_semantic_batch('alpha',did,'saved-owner',batch,facts,issues,{'version':VERSION,'schema_hash':SCHEMA_HASH,'model':'deepseek-flash','extractions':ex})
        runtime={'base_url':'http://127.0.0.1:1/test/v1','api_key':'test-token','model':'deepseek-flash','review_metrics':['selling_expenses']}
        with patch('service.processing.normalize_document',side_effect=AssertionError('saved tables must remain reusable')),patch('service.processing.canonicalize_project',side_effect=ValueError('catalog_batches_pending_retry')),patch('service.processing.review_definition_project') as definitions,patch('service.processing.review_temporal_project') as temporal:
            failed=self.wait(self.svc.start_document_processing('alpha',[did],'failed-review',runtime)['data']['processing_id'])
        self.assertEqual(failed['state'],'partial');definitions.assert_not_called();temporal.assert_not_called()
        self.assertEqual(failed['temporal_review']['status'],'pending')
        self.assertEqual(self.svc.query_financial_data('alpha')['data']['total'],4)
        with patch('service.processing.normalize_document',side_effect=AssertionError('resume must not reclean')),patch('service.processing.canonicalize_project',return_value={'status':'reviewed'}),patch('service.processing.review_definition_project',return_value={'status':'reviewed'}) as definitions,patch('service.processing.review_temporal_project',return_value={'status':'reviewed'}) as temporal:
            resumed=self.wait(self.svc.start_document_processing('alpha',[did],'resume-review',runtime)['data']['processing_id'])
        self.assertEqual(resumed['state'],'completed');definitions.assert_called_once();temporal.assert_called_once()
        self.assertEqual(self.svc.query_financial_data('alpha')['data']['total'],4)

    def test_per_ten_share_amount_preserves_denominator_and_exposes_conversion(self):
        batch=[{"table":{"index":0,"page":34,"rows":[["每10股派息数（元）（含税）","276.24"]]},"rows":[1]}]
        cols=[{"column":2,"period":"2024-FY","unit":"元/10股","currency":"CNY"}]
        extracts=[{"class":"table_schema","text":"[[T0]]","span":[0,6],"attributes":{"company":"示例公司","statement":"notes","columns_json":json.dumps(cols)}},
                  {"class":"financial_row","text":"[[T0:R1]]","span":[7,17],"attributes":{"metric":"dividend_per_10_shares_pretax","label":"每10股派息数（含税）"}}]
        facts,issues=materialize(extracts,batch,"doc","deepseek-flash")
        self.assertEqual(issues,[]);self.assertEqual(facts[0]["value"],"276.24");self.assertEqual(facts[0]["currency"],"CNY/10shares")
        conversion=facts[0]["source"]["normalization"]["unit_conversion"]
        self.assertEqual(conversion["value"],"27.624");self.assertEqual(conversion["to_unit"],"CNY/share")
        extracts[1]["attributes"]["metric"]="revenue"
        facts,issues=materialize(extracts,batch,"doc","deepseek-flash")
        self.assertEqual(facts,[]);self.assertEqual(issues[0]["reason"],"metric_unit_mismatch")

    def test_host_replay_uses_original_owner_and_never_calls_model(self):
        from service.parser import parse_document
        doc=self.register();document_id=doc["document_id"]
        parsed=parse_document(self.root/doc["relative_path"],doc["original_name"],lambda *_:None,lambda:False,{})
        self.svc._persist_prepared("alpha",document_id,parsed)
        batch=table_batches(parsed)[0]
        cols=[{"column":2,"period":"2024-FY","unit":"万元","currency":"CNY"}]
        extracts=[{"class":"table_schema","text":"[[T0]]","span":[0,6],"attributes":{"company":"示例公司","statement":"income","columns_json":json.dumps(cols)}}]
        for row,metric in [(2,"selling_expenses"),(3,"research_expenses")]:
            extracts.append({"class":"financial_row","text":f"[[T0:R{row}]]","span":[row*10,row*10+9],"attributes":{"metric":metric,"label":metric}})
        self.svc._commit_semantic_batch("alpha",document_id,"original-pi-run",batch,[],[],{"schema_hash":SCHEMA_HASH,"model":"deepseek-flash","extractions":extracts})
        with patch("langextract.extract",side_effect=AssertionError("maintenance cannot call models")) as invoke:
            result=self.svc.rematerialize_documents("alpha",[document_id])["data"]
        invoke.assert_not_called();self.assertEqual(result["model_requests"],0);self.assertEqual(result["batches_replayed"],1)
        self.assertEqual(result["facts_rebuilt"],2);self.assertEqual(result["documents"][0]["source_owners"],["original-pi-run"])
        details=self.svc.get_normalization_details("alpha",document_id)["data"]["batches"][0]["result"]
        self.assertEqual(details["extraction_processing_id"],"original-pi-run")
        self.assertEqual(self.svc.get_data_catalog("alpha")["data"]["catalog_review"]["status"],"not_run")
        self.assertTrue(Path(result["audit_path"]).is_file())

    def test_invalid_maintenance_document_does_not_leave_claim(self):
        doc=self.register()
        with self.assertRaises(ValueError):self.svc.rematerialize_documents("alpha",[doc["document_id"],"not-a-document"])
        self.assertEqual(self.svc.processing_documents,{})

    def test_ownerless_old_cache_is_not_reused_as_proven_model_output(self):
        from service.semantic import normalize_document
        parsed={"company":"示例公司","report_year":2024,"pages":[{"page":1,"text":"2024年财报"}],"tables":[{"index":0,"page":1,"rows":[["指标","本期"],["金额","100"]]}]}
        runtime={"base_url":"http://127.0.0.1:1/cache/v1","api_key":"ephemeral","model":"deepseek-flash","processing_id":"current-owner"}
        with patch("langextract.extract",side_effect=RuntimeError("model required for untraceable cache")) as model:
            facts,report=normalize_document(parsed,"doc",runtime,lambda *_:None,lambda:False,lambda key:[],lambda *_:None)
        self.assertGreater(model.call_count,0);self.assertEqual(report["cache_hits"],0);self.assertEqual(report["resumed_batches"],0)
        self.assertEqual(facts,[]);self.assertEqual(report["failures"][0]["reason"],"model_request_failed")

    def test_model_request_failure_is_persisted_as_failure_not_success(self):
        doc=self.register()
        runtime={"base_url":"http://127.0.0.1:1/failure/v1","api_key":"test-token","model":"deepseek-flash"}
        with patch("langextract.extract",side_effect=RuntimeError("controlled inference failure")):
            state=self.wait(self.svc.start_document_processing("alpha",[doc["document_id"]],"failure",runtime)["data"]["processing_id"])
        self.assertEqual(state["state"],"failed",state)
        self.assertEqual(state["errors"][0]["code"],"model_batches_failed")
        report=state["documents"][0]["normalization"]
        self.assertEqual(report["completed"],0);self.assertEqual(report["failures"][0]["reason"],"model_request_failed")
        self.assertEqual(self.svc.get_document("alpha",doc["document_id"])["data"]["state"],"failed")


if __name__=="__main__":unittest.main()
