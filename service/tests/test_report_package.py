import json
from pathlib import Path
import tempfile
import unittest
from types import SimpleNamespace
from openpyxl import load_workbook
import fitz
from service.analysis_report import compile_report
from service.report_package import prepare, finish, section_for

class ReportPackageTests(unittest.TestCase):
    def test_exact_cells_unknowns_and_provenance_survive_workbook_and_zip(self):
        with tempfile.TemporaryDirectory() as tmp:
            report=compile_report({'tables':{'income':{'columns':{'key':{},'value':{'unit':'百万元','currency':'CNY'}},'rows':[
                {'key':'revenue','value':{'value':'12.1234567890123456789','unit':'百万元','currency':'CNY','source':{'document_id':'d','page':7}}},
                {'key':'=1+1','value':{'value':None,'unit':'百万元','currency':'CNY','source':{'missing_reason':'未披露'}}}]}}})
            snapshot={'project_id':'p','conversation_id':'c','title':'测试报告','turns':[{'id':'m','created_at':'2026-10-08','body':'【观点】关注现金转换。','sources':[],'tables':report['tables']}]}
            svc=SimpleNamespace(store=SimpleNamespace(root=Path(tmp),project=lambda p:None))
            prepared=prepare(svc,'p',snapshot);folder=Path(tmp)/'report_packages/p'/prepared['package_id']
            book=load_workbook(folder/'workpapers.xlsx');sheet=book['指标']
            row=next(row for row in sheet if row[0].value=='revenue');self.assertEqual(row[1].value,'12.1234567890123456789')
            self.assertIn('"page": 7',row[1].comment.text)
            blank=next(row for row in sheet if row[0].value=='=1+1');self.assertEqual(blank[0].data_type,'s');self.assertIsNone(blank[1].value)
            self.assertIn('未披露',blank[1].comment.text)
            mixed=compile_report({'tables':{'mixed':{'columns':{'key':{},'value':{}},'rows':[
                {'key':'cash','value':{'value':'12','unit':'元','currency':'CNY'}},
                {'key':'shares','value':{'value':'100','unit':'股'}}]}}})
            from service.report_package import workbook
            workbook({**snapshot,'turns':[{**snapshot['turns'][0],'tables':mixed['tables']}]},folder/'mixed.xlsx')
            mixed_sheet=load_workbook(folder/'mixed.xlsx')['指标']
            self.assertEqual(mixed_sheet['C6'].value,'CNY 元');self.assertEqual(mixed_sheet['C7'].value,'股')
            self.assertEqual(json.loads((folder/'snapshot.json').read_text('utf8')),snapshot)
            exported=finish(svc,'p',prepared['package_id'],'<h1>财报分析报告</h1><p>收入 12.12 CNY 百万元</p>')
            self.assertTrue((Path(tmp)/exported['relative_path']).is_file())
            with fitz.open(folder/'report.pdf') as pdf:self.assertIn('12.12',pdf[0].get_text())
            self.assertEqual(section_for('new_kind',{'report_section':'anomaly_signals'}),4)
            with self.assertRaisesRegex(ValueError,'项目'):prepare(svc,'other',snapshot)
            with self.assertRaisesRegex(ValueError,'标识'):finish(svc,'p','../outside','')

if __name__=='__main__':unittest.main()
