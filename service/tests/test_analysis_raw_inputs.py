import json
import tempfile
import unittest
from pathlib import Path

from service.core import FinanceService
from service.semantic import SCHEMA_HASH, VERSION, materialize, table_batches
from service.tests.test_semantic_sources import mappings


class AnalysisRawInputTests(unittest.TestCase):
    def test_generic_container_gets_raw_pages_and_tables_but_no_standardized_facts(self):
        with tempfile.TemporaryDirectory() as temporary:
            service=FinanceService(Path(temporary));captured=[]
            class Runner:
                def availability(self):return {"available":True}
                def run(self,code,inputs,**kwargs):
                    captured.append({key:json.loads(path.read_text(encoding="utf-8")) if path.suffix==".json" else path.read_bytes() if path.suffix=='.zip' else path.read_text(encoding="utf-8") for key,path in inputs.items()})
                    return {"status":"completed","run_id":kwargs["run_id"],"artifacts":[]}
            service.sandbox=Runner()
            try:
                service.create_project("p","Input fixture")
                path=service.store.root/"uploads"/"2024.csv";path.write_text("指标,本期\n资产,137",encoding="utf-8")
                doc=service.register_document("p",str(path),path.name)["data"]
                parsed={"company":"公司","report_year":2024,"warnings":[],"pages":[{"page":1,"text":"资产137","words":[{"text":"137","bbox":[1,2,3,4]}]}],
                        "tables":[{"index":0,"page":1,"rows":[["指标","本期"],["资产","137"]],"cells":{}}]}
                service._persist_prepared("p",doc["document_id"],parsed)
                batch=table_batches(parsed)[0];ex=mappings(0,2);facts,issues=materialize(ex,batch,doc["document_id"],"fixture")
                service._commit_semantic_batch("p",doc["document_id"],"owner",batch,facts,issues,{"version":VERSION,"schema_hash":SCHEMA_HASH,"model":"fixture","extractions":ex})
                for raw_only in (True,False):
                    run=service.run_analysis("p","pass",raw_only=raw_only)["data"]["run_id"]
                    service.analysis_futures[run].result(timeout=3)
                run=service.run_analysis('p','pass',raw_only=False,financial_tools=False)['data']['run_id']
                service.analysis_futures[run].result(timeout=3)
                patched=service.run_analysis('p',source_run_id=run,edits=[{'before':'pass','after':"print('patched')"}],financial_tools=False)['data']['run_id']
                service.analysis_futures[patched].result(timeout=3)
                self.assertEqual(captured[3]['analysis.py'],"print('patched')")
                self.assertEqual(captured[2]['analysis.py'],'pass')
                with self.assertRaisesRegex(ValueError,'edit_must_match_once'):
                    service.run_analysis('p',source_run_id=run,edits=[{'before':'missing','after':'x'}],financial_tools=False)
                repeated=service.run_analysis('p','print(1)\nprint(1)',financial_tools=False)['data']['run_id']
                service.analysis_futures[repeated].result(timeout=3)
                with self.assertRaisesRegex(ValueError,'edit_must_match_once') as caught:
                    service.run_analysis('p',source_run_id=repeated,edits=[{'before':'print(1)','after':'print(2)'}],financial_tools=False)
                self.assertEqual(caught.exception.details['matches'],2)
                updated=service.run_analysis('p',source_run_id=repeated,edits=[{'before':'print(1)','after':'print(2)','replace_all':True}],financial_tools=False)['data']['run_id']
                service.analysis_futures[updated].result(timeout=3)
                self.assertEqual(captured[-1]['analysis.py'],'print(2)\nprint(2)')
                with self.assertRaisesRegex(ValueError,'edit_makes_no_change'):
                    service.run_analysis('p',source_run_id=run,edits=[{'before':'pass','after':'pass'}],financial_tools=False)
                self.assertEqual(set(captured[0]),{"pages.json","tables.json","facts.json","research_records.json","analysis.py","plot_runtime.py","analysis_report.py","model_units.py","analysis_report.md","delivery_text.py"})
                self.assertEqual(captured[0]['analysis.py'],'pass')
                self.assertEqual(captured[0]['plot_runtime.py'],captured[1]['plot_runtime.py'])
                self.assertEqual(captured[0]['analysis_report.py'],captured[2]['analysis_report.py'])
                report={'tables':{'x':{'columns':{'v':{'unit':'元','currency':'CNY'}},'rows':[{'v':'10'}]}}}
                report_run=service.run_analysis('p',report=report,financial_tools=False)['data']['run_id']
                service.analysis_futures[report_run].result(timeout=3)
                self.assertEqual(captured[-1]['analysis.py'],'pass')
                self.assertEqual(captured[-1]['analysis_report.json'],report)
                rerun=service.run_analysis('p',source_run_id=report_run,financial_tools=False)['data']['run_id']
                service.analysis_futures[rerun].result(timeout=3)
                self.assertEqual(captured[-1]['analysis_report.json'],report)
                self.assertEqual(captured[1]['models.json'],{})
                self.assertEqual(captured[0]["facts.json"],[])
                self.assertEqual(captured[0]["research_records.json"],[])
                self.assertEqual(len(captured[1]["facts.json"]),1)
                self.assertEqual(captured[1]['facts.json'],captured[2]['facts.json'])
                self.assertEqual(captured[1]['research_records.json'],captured[2]['research_records.json'])
                self.assertNotIn('finance_charts.py',captured[2])
                self.assertNotIn('models.json',captured[2])
                for name in ("finance_charts.py", "finance_charts.md"):
                    expected=(Path(__file__).resolve().parents[1]/name).read_text(encoding="utf-8")
                    self.assertEqual(captured[1][name],expected)
                self.assertEqual(captured[0]["pages.json"][0]["words"],[{"text":"137","bbox":[1,2,3,4]}])
                self.assertEqual(captured[0]["tables.json"],captured[1]["tables.json"])
            finally:
                for pool in (service.processing_pool,service.pool,service.analysis_pool,service.embedding_pool):pool.shutdown(wait=True,cancel_futures=True)


if __name__=="__main__":unittest.main()
