import json
from pathlib import Path
import tempfile
import unittest
from service.analysis_report import compile_report, render_report, save_table
from service.analysis_tables import collect_tables, artifact_content, table_view


class AnalysisTablesTest(unittest.TestCase):
    def test_typed_tables_keep_precision_units_rows_and_sources(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            report = compile_report({'tables': {'forecast': {'row_key': 'year', 'columns': {
                'year': {}, 'profit': {'unit': '亿元', 'currency': 'CNY'}}, 'rows': [
                    {'year': '2025E', 'profit': {'value': '1234.56789', 'unit': '百万元', 'currency': 'CNY'}}]}}})
            render_report(report, root)
            save_table('margin', {'v': {'unit': '%'}}, [{'v': {'value': '0.3364626459957', 'unit': 'ratio'}}], input_dir=root, output_dir=root)
            tables, warnings = collect_tables({p.name:p for p in root.iterdir()})
            self.assertEqual(warnings, [])
            self.assertEqual(tables['forecast']['row_keys'], ['2025E'])
            self.assertEqual(tables['forecast']['rows'][0]['profit'], '12.3456789')
            self.assertEqual(table_view(tables['margin'])['display_rows'][0]['v'], '33.65 %')
            self.assertEqual(artifact_content(root/'forecast.csv', {'start':0,'end':1})['rows']['total'],1)
            self.assertIn('forecast', artifact_content(root/'numeric_tables.json')['content']['tables'])
            self.assertEqual(artifact_content(root/'report.md', {'start':0,'end':1})['content'],'# 分析报告')

    def test_csv_never_guesses_currency_or_mixed_unit(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'mixed.csv'
            path.write_text('metric,period,unit,value,delta\nmargin,2024,%,41.378,\nmargin,2025,%,33.646,-7.732\nprofit,2025,人民币百万元,102.791,-61.293\n',encoding='utf8')
            tables,_=collect_tables({'mixed.csv':path});table=tables['mixed']
            self.assertEqual(table['row_keys'],['margin|2024','margin|2025','profit|2025'])
            self.assertNotIn('unit',table['columns']['value'])
            self.assertEqual(table['cell_units'][2]['value']['currency'],'CNY')
            self.assertIn('不能证明',table['unit_note'])


if __name__=='__main__': unittest.main()
