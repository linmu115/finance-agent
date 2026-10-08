import copy
import json
from concurrent.futures import ThreadPoolExecutor
import unittest
from service.tests import test_script_cleaning as fixtures
from service.source_periods import column_period, report_month
from service.cleaning_rules import mapping_headers, draft
from service.cleaning_consistency import table_semantics
from service.cleaning_mapping import mapping_issues


class CheckpointTests(unittest.TestCase):
    setUp=fixtures.ScriptCleaningTests.setUp
    tearDown=fixtures.ScriptCleaningTests.tearDown
    job=fixtures.ScriptCleaningTests.job

    def test_repeated_and_concurrent_process_calls_reuse_unfinished_attempt(self):
        with ThreadPoolExecutor(2) as pool:
            results=list(pool.map(lambda owner:self.s.begin_script_cleaning('p',[self.did],owner,'fixture')['data'],['second','third']))
        self.assertEqual({r['processing_id'] for r in results},{self.pid})
        with self.s.store.connect() as db:self.assertEqual(db.execute('SELECT count(*) FROM processing_runs').fetchone()[0],1)
        self.assertEqual(results[0]['pending_tables'][self.did],[0])
        self.assertEqual(self.s.begin_script_cleaning('p',[self.did],'force-repeat','fixture',force=True)['data']['processing_id'],self.pid)

    def test_historical_checkpoint_uses_other_attempts_commits_and_keeps_jobs(self):
        old=self.s._clean_state('p',self.pid)
        duplicate=copy.deepcopy(old);duplicate['processing_id']='duplicate'
        self.s._save_processing(duplicate)
        rid=self.job();self.s.commit_cleaning_result('p',self.pid,rid)
        refreshed=self.s.get_cleaning_progress('p','duplicate')['data']
        self.assertEqual(refreshed['pending_tables'][self.did],[])
        self.assertEqual(refreshed['document_progress'][0]['fact_count'],4)
        resumed=self.s.begin_script_cleaning('p',[self.did],'resume','fixture')['data']
        self.assertEqual(resumed['processing_id'],'duplicate')
        self.assertIn(rid,self.s._clean_state('p','duplicate')['jobs'])
        with self.s.store.connect() as db:self.assertEqual(db.execute('SELECT count(*) FROM facts').fetchone()[0],4)


class SourceInterpretationTests(unittest.TestCase):
    def test_quarter_and_cumulative_headings_current_and_prior(self):
        expected={'本报告期':'2024-Q3','年初至报告期末':'2024-9M','上年同期':'2023-Q3',
                  '年初至上年报告期末':'2023-9M','2024年前三季度（1-9月）':'2024-9M',
                  '2023 年7—9月':'2023-Q3'}
        for header,period in expected.items():
            with self.subTest(header=header):self.assertEqual(column_period(header,'','income',9,2024)['period'],period)
        self.assertEqual(column_period('本报告期','','income',3,2024)['period'],'2024-Q1')
        self.assertEqual(column_period('本期金额','','income',6,2025)['period'],'2025-H1')
        self.assertEqual(column_period('2025年6月30日','','balance',6,2025)['period'],'2025-06-30')
        self.assertEqual(column_period('上年年末','','balance',9,2024)['period'],'2023-12-31')
        self.assertEqual(column_period('2025','','income',None,2025)['period'],'unknown')
        self.assertEqual(column_period('期末余额','','balance',None,2025)['period'],'unknown')
        self.assertEqual(column_period('上年同期','2024年1—9月','income',9,2024)['period'],'2023-9M')
        self.assertEqual(column_period('June 30, 2025','','notes',6,2025)['period'],'2025-06-30')
        self.assertEqual(column_period('December 31, 2024','','notes',6,2025)['period'],'2024-12-31')
        self.assertEqual(column_period('2024年金额','第一季度（1-3月份）\n十、非经常性损益','notes',12,2024)['period'],'2024-FY')

    def test_document_title_wins_over_mentions_of_other_reports(self):
        parsed={'pages':[{'text':'2024 年年度报告\n参见2024年第三季度报告'}]}
        self.assertEqual(report_month(parsed),12)
        self.assertEqual(report_month({'pages':[{'text':'2025年半年度报告'}]}),6)
        self.assertEqual(report_month({'pages':[{'text':'INTERIM REPORT 2025'}]}),6)

    def test_numeric_sentence_is_data_but_dates_and_years_are_headers(self):
        rows=[['债券名称','付息兑付情况的说明'],['高级无抵押定息债券','2024 年5 月17 日和2024 年11 月18 日各兑付利息4,062,500 美元。']]
        table={'index':87,'page':77,'rows':rows}
        self.assertEqual(mapping_headers(table),rows[:1])
        issues=table_semantics(table,{'skipped_rows_json':json.dumps([{'row':1},{'row':2}])},[])
        self.assertEqual(issues[0]['reason'],'numeric_table_without_records')
        self.assertEqual(issues[0]['numeric_samples'][0]['row'],2)
        self.assertEqual(mapping_issues(table,{'skipped_rows_json':json.dumps([{'row':2,'reason':'source header'}])},[])[0]['reason'],'numeric_data_marked_as_header')
        for rows in [[['项目','2024','2023']],[['项目','2024年9月30日','2023年12月31日']],
                     [['','Six months ended 30 June',''],['','2025','2024']]]:
            table={'index':1,'page':1,'rows':rows}
            self.assertEqual(mapping_headers(table),rows)
            self.assertEqual(table_semantics(table,{},[]),[])
        self.assertEqual(mapping_headers({'rows':[['项目','2024','2023'],['自定义项目','88','99']]}),[['项目','2024','2023']])
        self.assertEqual(mapping_headers({'rows':[['二、投资活动产生的现金流量：','',''],['收回投资收到的现金','100','90']]}),[])


if __name__=='__main__':unittest.main()
