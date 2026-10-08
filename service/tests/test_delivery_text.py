import copy
import json
from pathlib import Path
import tempfile
import unittest

from service.analysis_report import bind_text, fmt_change
from service.delivery_text import direction_issues
from service.core import FinanceService
from service.tests.test_evaluation_isolation import scoped

FIXTURES = Path(__file__).resolve().parents[2] / 'tests/fixtures/v3-delivery'


class DeliveryTextTests(unittest.TestCase):
    def test_original_f1_x3_and_failed_repair_keep_valid_tables_and_chart(self):
        tables = json.loads((FIXTURES/'F1_X3-tables.json').read_text(encoding='utf8'))
        original = copy.deepcopy(tables)
        charts = {'ocf_contribution.png':'/registered/chart.png'}
        issues, rewrites = [], []
        body = bind_text((FIXTURES/'F1_X3-1.md').read_text(encoding='utf8'),tables,charts,
                         degrade=True,issues=issues,rewrites=rewrites)
        # The original also used tool-shaped placeholders for MD/Python attachments;
        # those are not tables or images and must remain explicit repair items.
        self.assertEqual(len(issues),2)
        self.assertTrue(all('report.md' in i['text'] or 'recalculate.py' in i['text'] for i in issues))
        self.assertTrue(rewrites)
        self.assertIn('{{get_artifact(4e660ebf66824ad4b5fcb09caf0c11df, cashflow_reconciliation.csv)}}', [r['original'] for r in rewrites])
        self.assertIn('| 合并净利润 |',body)
        self.assertNotIn('{{get_artifact(4e660ebf66824ad4b5fcb09caf0c11df, cashflow_reconciliation.csv)}}',body)
        issues = []
        repaired = bind_text((FIXTURES/'F1_X3-2.md').read_text(encoding='utf8'),tables,charts,degrade=True,issues=issues)
        self.assertEqual(len(issues),1)
        self.assertIn('[引用无效：{{get_artifact(...)}}]',repaired)
        self.assertIn('| 合并净利润 |',repaired)
        self.assertIn('![ocf_contribution.png](/registered/chart.png)',repaired)
        self.assertEqual(tables,original)

    def test_tool_shape_is_unique_inventory_lookup_never_execution(self):
        table={'columns':{'v':{'unit':'元'}},'rows':[{'v':'1234.56'}]}
        for token in ["get_artifact('r', 't.csv')", 'get_artifact(run_id="r", name="t.csv")', 'get_artifact(r, t)']:
            rewrites=[]
            self.assertIn('1,234.56',bind_text('{{'+token+'}}',{'t':table},rewrites=rewrites))
            self.assertEqual(rewrites[0]['replacement'],'{{table:t}}')
        self.assertEqual(bind_text('{{get_artifact(r, image.png)}}',{}, {'image.png':'/safe'}),'![image.png](/safe)')
        for tables,charts,token in [({'t':table,'T':table},{},'get_artifact(r, t.csv)'),
                                    ({'t':table},{'t.csv':'/conflict'},'get_artifact(r,t.csv)'),
                                    ({'t':table},{},'get_artifact(foreign, secret.csv)'),
                                    ({'t':table},{},"get_artifact(r, __import__('os').system('bad'))")]:
            with self.subTest(token=token),self.assertRaises(ValueError):bind_text('{{'+token+'}}',tables,charts)

    def test_f2_d1_unparseable_cells_degrade_locally_including_sum_relations(self):
        for bad in ['41.38%','-7.73个百分点','—','', '约12','NaN']:
            tables={'good':{'columns':{'v':{'unit':'元'}},'rows':[{'v':'12'}]},
                    'bad':{'columns':{'v':{'unit':'百万元'}},'rows':[{'v':bad}]}}
            issues=[]
            result=bind_text('{{good.0.v}} {{bad.0.v}} {{table:bad}}',tables,degrade=True,issues=issues)
            self.assertTrue(result.startswith('12.00 元'))
            self.assertEqual(len(issues),2)
            self.assertIn('非有限数值' if bad=='NaN' else bad,issues[0]['message'])
            tables['bad']['sum_relations']=[{'total':{'row':'0','column':'v'},'parts':[{'row':'0','column':'v'}]}]
            self.assertIn('[引用无效',bind_text('{{table:bad}}',tables,degrade=True))

    def test_formatter_preserves_magnitude_percent_contract_and_unknowns(self):
        for args,expected in [((-3.2,'亿元',-5),'减少 3.2亿元（5%）'),((12,'元'),'增加 12元'),
                              ((0,'元',0),'持平'),(('-0','个百分点'),'持平'),
                              (('-1,234.567','百万元'),'减少 1234.567百万元')]:
            self.assertEqual(fmt_change(*args),expected)
            self.assertFalse(direction_issues(expected))
        for args in [(None,'元'),('NaN','元'),(-3,'元',5),(0,'元',1)]:
            with self.assertRaises(ValueError):fmt_change(*args)

    def test_explicit_direction_signs_chinese_english_points_and_accounting_negatives(self):
        for text in ['同比增长 -3%','减少 -1,234.56百万元','下降 −2.5 个百分点','增加 **-3**亿元',
                     '上升（3.2）个百分点','下降（3.2%）','减少 (-3.2)','下降 - 3.2%','Revenue increased by -3 million',
                     'Margins fell by (3.2) percentage points','成本下降 +3亿元']:
            with self.subTest(text=text):self.assertEqual(len(direction_issues(text)),1)
        for text in ['同比增长率为 -3%','变化 -3亿元','净增加额 -3','从 -5 上升至 -3','下降至 -3%',
                     '上升为 -3','The loss increased from -5 to -3','增加 3亿元','减少 3亿元',
                     '减少 -0.0元','`增加 -3` 是错误例子','```python\nx="减少 -3"\n```']:
            with self.subTest(text=text):self.assertEqual(direction_issues(text),[])
        issues=direction_issues('项目,同比增加(亿元),说明\n收入,-3,"减少 -2亿元"\n成本,2,正常','test.csv',True)
        self.assertEqual(len(issues),2)
        self.assertTrue(all(i['source']=='test.csv' and i['line']==2 for i in issues))

    def test_artifacts_are_scoped_and_scanned_without_mutation(self):
        with tempfile.TemporaryDirectory() as tmp:
            service=FinanceService(Path(tmp));service.create_project('p','Test')
            class Runner:
                def artifact_path(self,rid,name,project_id):return Path(tmp)/rid/name
            service.sandbox=Runner()
            try:
                for rid,key in [('own','a'),('other','b')]:
                    with scoped(key):service._save_analysis_state('p',rid,{'status':'succeeded'})
                    folder=Path(tmp)/rid;folder.mkdir()
                    (folder/'report.md').write_text('收入增加 -3亿元。',encoding='utf8')
                    (folder/'data.csv').write_text('项目,说明\n收入,减少 (3)亿元',encoding='utf8')
                with scoped('a'):
                    result=service.render_answer('p','回答无方向问题',{},degrade=True,files=[{'run_id':'own','name':n} for n in ['report.md','data.csv']])['data']
                    self.assertEqual({i['source'] for i in result['issues']},{'report.md','data.csv'})
                    self.assertEqual((Path(tmp)/'own/report.md').read_text(encoding='utf8'),'收入增加 -3亿元。')
                    foreign=service.render_answer('p','',{},degrade=True,files=[{'run_id':'other','name':'report.md'}])['data']
                    absent=service.render_answer('p','',{},degrade=True,files=[{'run_id':'absent','name':'report.md'}])['data']
                    self.assertEqual(foreign,absent)
                    self.assertNotIn('增加',json.dumps(foreign,ensure_ascii=False))
            finally:
                for name in ('pool','analysis_pool','embedding_pool','processing_pool'):getattr(service,name).shutdown(wait=True)
