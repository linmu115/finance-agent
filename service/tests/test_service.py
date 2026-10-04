import json
import shutil
import tempfile
import time
import unittest
from decimal import Decimal
from pathlib import Path
from service.core import FinanceService
from service.normalization import decimal_value, unit_info
from service.parser import extract_facts

class FinanceServiceTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.root=Path(self.tmp.name)
        self.svc=FinanceService(self.root)
        self.svc.create_project("alpha","甲公司")
        self.svc.create_project("beta","乙公司")

    def tearDown(self):
        self.svc.pool.shutdown(wait=True,cancel_futures=True)
        self.svc.analysis_pool.shutdown(wait=True,cancel_futures=True)
        self.svc.embedding_pool.shutdown(wait=True,cancel_futures=True)
        self.tmp.cleanup()

    def ingest(self,name,text,project="alpha"):
        path=self.root/"uploads"/name
        path.write_text(text,encoding="utf-8")
        result=self.svc.ingest_document(project,str(path),name)
        job=result["data"]["job_id"]
        deadline=time.monotonic()+20
        while time.monotonic()<deadline:
            state=self.svc.get_ingestion_status(project,job)["data"]
            if state["state"] in {"ready","needs_review","failed"}:
                self.assertNotEqual(state["state"],"failed",state)
                return result["data"]
            time.sleep(.03)
        self.fail("ingestion timeout")

    def test_real_csv_decimal_units_and_coordinates(self):
        doc=self.ingest("sample.csv","指标,2024年,2023年,单位\n营业收入,12345.67,10000,万元\n总资产,20000,18000,万元\n")
        facts=self.svc.get_financial_metrics("alpha",["revenue","assets"])["data"]["items"]
        self.assertEqual(len(facts),4)
        revenue=next(f for f in facts if f["metric"]=="revenue" and f["year"]==2024)
        self.assertEqual(revenue["value"],"123456700.00")
        self.assertEqual(revenue["source_ref"]["cell"],"B2")
        self.assertEqual(revenue["source_ref"]["sheet"],"sample")
        self.assertEqual(next(f["period"] for f in facts if f["metric"]=="assets" and f["year"]==2024),"2024-12-31")
        missing=self.svc.get_financial_metrics("alpha",["revenue"],years=[2027])
        self.assertEqual(missing["status"],"insufficient_evidence")

    def test_project_isolation_all_document_paths(self):
        doc=self.ingest("private.csv","指标,2024年,2023年,单位\n营业收入,666,123,元\n")
        doc_id=doc["document_id"]
        with self.assertRaises(ValueError):self.svc.get_document("beta",doc_id)
        with self.assertRaises(ValueError):self.svc.get_source_page("beta",doc_id,1)
        with self.assertRaises(ValueError):self.svc.get_source_table("beta",doc_id)
        with self.assertRaises(ValueError):self.svc.get_ingestion_status("beta",doc["job_id"])
        with self.assertRaises(ValueError):self.svc.cancel_ingestion("beta",doc["job_id"])
        self.assertEqual(self.svc.search_evidence("beta","营业收入")["data"]["items"],[])
        self.assertEqual(self.svc.get_financial_metrics("beta",["revenue"])["data"]["items"],[])
        fact=self.svc.get_financial_metrics("alpha",["revenue"])["data"]["items"][0]
        with self.assertRaises(ValueError):self.svc.calculate_financial_metrics("beta","ratio",{"numerator":{"fact_id":fact["fact_id"]},"denominator":"1"})

    def test_idempotent_ingestion_and_file_boundary(self):
        original="指标,2024年,2023年,单位\n营业收入,2,1,元\n"
        first=self.ingest("first.csv",original)
        second=self.ingest("renamed.csv",original)
        self.assertEqual(first["document_id"],second["document_id"])
        self.assertEqual(len(self.svc.list_documents("alpha")["data"]["items"]),1)
        outside=self.root/"outside.csv"
        outside.write_text(original,encoding="utf-8")
        with self.assertRaises(ValueError):self.svc.ingest_document("alpha",str(outside),"outside.csv")
        with self.assertRaises(ValueError):self.svc.create_project("../alpha","escape")
        with self.assertRaises(ValueError):self.svc.get_financial_metrics("alpha",["revenue');DROP TABLE facts;--"])

    def test_unknown_unit_never_assumed_yuan(self):
        self.ingest("unknown.csv","指标,2024年,2023年\n营业收入,2,1\n")
        self.assertEqual(self.svc.get_financial_metrics("alpha",["revenue"])["status"],"insufficient_evidence")
        self.assertEqual(decimal_value("(1,234.50)"),Decimal("-1234.50"))
        self.assertIsNone(decimal_value("—"))
        self.assertIsNone(decimal_value("NaN"))
        self.assertEqual(unit_info("千元")[1],Decimal(1000))

    def test_decimal_computations_and_zero_denominator(self):
        result=self.svc.calculate_financial_metrics("alpha","yoy",{"current":"115.71","previous":"100"})
        self.assertEqual(result["data"]["value"],"15.7100")
        self.assertEqual(result["data"]["unit"],"%")
        ratio=self.svc.calculate_financial_metrics("alpha","ratio",{"numerator":"2","denominator":"3"})
        self.assertTrue(ratio["data"]["value"].startswith("0.666666666666"))
        self.assertEqual(self.svc.calculate_financial_metrics("alpha","yoy",{"current":"2","previous":"0"})["status"],"insufficient_evidence")

    def test_excel_formula_without_cache_is_not_zero(self):
        from openpyxl import Workbook
        book=Workbook();sheet=book.active;sheet.title="利润表"
        sheet.append(["指标","2024年","2023年","单位"])
        sheet.append(["营业收入","=1+2",2,"千元"])
        file=self.root/"uploads"/"formula.xlsx";book.save(file)
        result=self.svc.ingest_document("alpha",str(file),"formula.xlsx")
        for _ in range(100):
            state=self.svc.get_ingestion_status("alpha",result["data"]["job_id"])["data"]
            if state["state"] in {"ready","needs_review","failed"}:break
            time.sleep(.03)
        self.assertEqual(state["state"],"needs_review",state)
        records=self.svc.get_financial_metrics("alpha",["revenue"])["data"]["items"]
        self.assertEqual([(f["year"],f["value"]) for f in records],[(2023,"2000")])
        table=self.svc.get_source_table("alpha",result["data"]["document_id"])["data"]["items"][0]
        detail=self.svc.get_source_table("alpha",result["data"]["document_id"],table["table_id"])["data"]["items"][0]
        self.assertEqual(detail["cells"]["B2"]["formula"],"=1+2")

    def test_finqa_source_ids_survive_import(self):
        original_text=[{"id":"sample:text_0","text":"Revenue rose to 100 million."},{"id":"sample:text_2","text":"This is the second supplied segment, not index one."}]
        original_rows=[{"id":"sample:table_0","cells":["Metric","2024","2023"]},{"id":"sample:table_1","cells":["revenue","100","90"]}]
        original_rows += [{"id":f"sample:table_{i}","cells":[f"item {i}",str(i),str(i-1)]} for i in range(2,7)]
        text=json.dumps({"source_id":"sample","text":original_text,"table":original_rows})
        doc=self.ingest("financial.json",text)
        result=self.svc.search_evidence("alpha","revenue")
        ids={r.get("source_id") for r in result["source_refs"]}
        self.assertIn("sample:text_0",ids)
        self.assertIn("sample:table_1",ids)
        page=self.svc.get_source_page("alpha",doc["document_id"],1)
        expected_ids=[r["id"] for r in original_text+original_rows]
        self.assertEqual([r["source_id"] for r in page["data"]["segments"]],expected_ids)
        self.assertEqual(page["data"]["segments"][1]["text"],original_text[1]["text"])
        self.assertEqual([r["source_id"] for r in page["source_refs"] if r.get("source_id")],expected_ids)
        preview=self.svc.get_source_table("alpha",doc["document_id"])["data"]["items"][0]
        self.assertEqual(preview["row_count"],7)
        self.assertEqual(preview["source_rows"],[r["id"] for r in original_rows[:5]])
        self.assertEqual([r["row"] for r in preview["row_source_refs"]],list(range(1,6)))
        table=self.svc.get_source_table("alpha",doc["document_id"],preview["table_id"])
        full=table["data"]["items"][0]
        self.assertEqual(full["rows"],[r["cells"] for r in original_rows])
        self.assertEqual(full["source_rows"],[r["id"] for r in original_rows])
        self.assertEqual(full["row_source_refs"][-1]["source_id"],"sample:table_6")
        self.assertEqual(full["row_source_refs"][-1]["row"],7)
        self.assertEqual([r["source_id"] for r in table["source_refs"] if r.get("source_id")],full["source_rows"])
        with self.assertRaises(ValueError):self.svc.get_source_page("beta",doc["document_id"],1)
        with self.assertRaises(ValueError):self.svc.get_source_table("beta",doc["document_id"],preview["table_id"])

    def test_app_state_and_config_secrets(self):
        self.svc.put_app_state("alpha","conversations","one",{"messages":[{"role":"user","content":"hello"}]})
        self.assertEqual(self.svc.get_app_state("beta","conversations","one")["data"]["value"],None)
        self.assertEqual(len(self.svc.list_app_state("alpha","conversations")["data"]["items"]),1)
        with self.assertRaises(ValueError):self.svc.put_app_state("alpha","secrets","one",{})
        secret="sentinel-private-key-654321"
        result=self.svc.configure_processing("alpha",embedding={"enabled":True,"base_url":"https://example.com/v1","model":"unit-test","api_key":secret})
        self.assertNotIn(secret,json.dumps(result))
        self.assertNotIn(secret,(self.root/"finance.sqlite").read_bytes().decode("latin1"))
        with self.assertRaises(ValueError):self.svc.configure_processing("alpha",embedding={"base_url":"http://example.com/v1"})

    def test_cross_page_header_uses_physical_columns_not_column_count(self):
        parsed={"pages":[{"page":1,"text":"主要会计数据 单位：元"},{"page":2,"text":"总资产（元）"}],
                "tables":[{"page":1,"index":0,"rows":[["指标","2024年末","","2023年末"]],"column_centers":{0:30,1:150,2:190,3:250}},
                          {"page":2,"index":1,"rows":[["总资产（元）","100","90"]],"column_centers":{0:30,1:150,2:250}}]}
        facts=extract_facts(parsed,"doc")
        self.assertEqual([(f["year"],f["value"]) for f in facts],[(2024,"100"),(2023,"90")])
        parsed["tables"][1]["column_centers"]={0:30,1:200,2:300}
        self.assertEqual(extract_facts(parsed,"doc"),[])

    def test_embedding_http_contract_cache_and_project_namespace(self):
        from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
        import threading
        requests=[]
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*args): pass
            def do_POST(self):
                body=json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                requests.append(body)
                if body["model"]=="unavailable":
                    self.send_response(503);self.end_headers();return
                vectors=[{"index":i,"embedding":[1.0,float(len(text)%7),.5]} for i,text in enumerate(body["input"])]
                data=json.dumps({"data":vectors}).encode()
                self.send_response(200);self.send_header("Content-Type","application/json");self.end_headers();self.wfile.write(data)
        http=ThreadingHTTPServer(("127.0.0.1",0),Handler)
        thread=threading.Thread(target=http.serve_forever,daemon=True);thread.start()
        try:
            self.ingest("embed.csv","指标,2024年,2023年,单位\n营业收入,2,1,元\n")
            cfg={"enabled":True,"base_url":f"http://127.0.0.1:{http.server_port}/v1","model":"contract-fixture","dimensions":3,"api_key":"secret-contract-key"}
            self.svc.configure_processing("alpha",embedding=cfg)
            for future in list(self.svc.embedding_jobs.values()):future.result(timeout=10)
            self.assertGreater(self.svc.embedding_states["alpha"]["indexed"],0)
            count=len(requests)
            self.assertEqual(self.svc.index_embeddings("alpha")["data"]["indexed"],0)
            self.assertEqual(len(requests),count)
            self.assertEqual(self.svc.search_evidence("alpha","营业收入")["data"]["retrieval"],"hybrid_rrf")
            for future in list(self.svc.embedding_jobs.values()):future.result(timeout=10)
            self.svc.configure_processing("alpha",embedding=cfg|{"model":"changed-model"})
            for future in list(self.svc.embedding_jobs.values()):future.result(timeout=10)
            self.assertGreater(self.svc.embedding_states["alpha"]["indexed"],0)
            self.assertTrue(any(r["model"]=="changed-model" for r in requests))
            self.svc.configure_processing("alpha",embedding=cfg|{"model":"unavailable"})
            for future in list(self.svc.embedding_jobs.values()):future.result(timeout=10)
            fallback=self.svc.search_evidence("alpha","营业收入")
            self.assertEqual(fallback["data"]["retrieval"],"fts5")
            self.assertTrue(any("embedding_unavailable" in w for w in fallback["warnings"]))
            self.svc.configure_processing("beta",embedding=cfg)
            self.assertEqual(self.svc.search_evidence("beta","营业收入")["data"]["items"],[])
            with self.svc.store.connect() as db:
                self.assertEqual(db.execute("SELECT count(*) FROM embedding_cache WHERE project_id='beta'").fetchone()[0],1) # Query only; no alpha evidence.
            self.assertNotIn("secret-contract-key",self.svc.store.path.read_bytes().decode("latin1"))
        finally:
            http.shutdown();thread.join();http.server_close()

    def test_ocr_header_without_label_does_not_shift_year(self):
        from service.parser import ocr_tables
        def item(text,x,y):return {"text":text,"bbox":[[x-20,y-6],[x+20,y-6],[x+20,y+6],[x-20,y+6]],"confidence":.99}
        lines=[item("2024年",150,10),item("2023年",250,10),item("营业收入（千元）",50,40),item("200",160,40),item("100",260,40),item("100%",350,40)]
        tables=[dict(t,page=1,index=i,ocr=True) for i,t in enumerate(ocr_tables(lines))]
        facts=extract_facts({"pages":[{"page":1,"text":"主要会计数据"}],"tables":tables},"scan")
        self.assertEqual([(f["year"],f["value"]) for f in facts],[(2024,"200000"),(2023,"100000")])

    def test_analysis_queued_race_failure_persistence_and_timeout_contract(self):
        import threading
        release=threading.Event()
        entered=threading.Event()
        class FailingRunner:
            def availability(self):return {"available":True}
            def run(self,*args,**kwargs):
                entered.set();release.wait(5)
                raise RuntimeError("sentinel-secret-must-not-appear")
            def status(self,*args,**kwargs):raise FileNotFoundError("manifest not created")
        self.svc.sandbox=FailingRunner()
        for invalid in (0,121,600,True,1.5):
            with self.assertRaisesRegex(ValueError,"analysis_timeout_must_be_1_to_120"):
                self.svc.run_analysis("alpha","pass",timeout_seconds=invalid)
        run=self.svc.run_analysis("alpha","pass",timeout_seconds=120)["data"]["run_id"]
        self.assertTrue(entered.wait(2))
        self.assertEqual(self.svc.get_analysis_status("alpha",run)["data"]["status"],"queued")
        with self.assertRaises(ValueError):self.svc.get_analysis_status("beta",run)
        with self.assertRaises(ValueError):self.svc.cancel_analysis("beta",run)
        release.set();self.svc.analysis_futures[run].result(timeout=5)
        state=self.svc.get_analysis_status("alpha",run)["data"]
        self.assertEqual(state["status"],"failed")
        self.assertEqual(state["error"],"runner_exception:RuntimeError")
        self.assertNotIn("sentinel-secret",json.dumps(state))
        with self.svc.store.connect() as db:
            self.assertEqual(json.loads(db.execute("SELECT state_json FROM analysis_jobs WHERE run_id=?",(run,)).fetchone()[0])["status"],"failed")

if __name__=="__main__":
    unittest.main()
