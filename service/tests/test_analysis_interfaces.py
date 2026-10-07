import unittest
from service.analysis_edits import apply_edits, AnalysisEditError
from service.analysis_report import compile_report, bind_text, render_table

class InterfaceTests(unittest.TestCase):
    def test_mixed_metric_cells_keep_their_actual_units(self):
        report={'tables':{'metrics':{'columns':{'metric':{},'value':{'unit':'人民币百万元或比率'}},'rows':[
            {'metric':'收入','value':{'value':'125.78901','unit':'人民币百万元'}},
            {'metric':'毛利率','value':{'value':'0.312','unit':'ratio'}},
            {'metric':'毛利率变动','value':{'value':'-1.3','unit':'percentage points'}}]}}}
        table=compile_report(report)['tables']['metrics']
        self.assertEqual(table['rows'][0]['value'],'125.78901')
        self.assertEqual(table['cell_units'][2]['value']['unit'],'个百分点')
        self.assertEqual(bind_text('{{metrics.收入.value}} / {{metrics.毛利率变动.value}}',{'metrics':table}),'125.79 CNY 百万元 / -1.30 个百分点')
        self.assertIn('0.31 ratio',render_table(table))

    def test_keys_labels_and_errors_do_not_guess_amounts(self):
        report={'tables':{'forecast':{'columns':{'year':{},'Revenue':{'label':'收入','unit':'人民币亿元'}},'rows':[{'year':'2025E',' revenue ':{'value':'1234','unit':'人民币百万元'}}]}},'body':'{{forecast.2025E.收入}}'}
        self.assertEqual(compile_report(report)['body'],'12.34 CNY 亿元')
        with self.assertRaisesRegex(ValueError,'可用引用.*2025E'):
            bind_text('{{forecast.wrong.Revenue}}',compile_report(report)['tables'])
        report['tables']['forecast']['columns']['Revenue']['unit']='百万'
        with self.assertRaisesRegex(ValueError,'未知单位'):compile_report(report)
        self.assertEqual(compile_report({'body':'Only prose'})['body'],'Only prose')
        self.assertEqual(compile_report({'tables':{'t':{'columns':{'rate':{'unit':'%'}},'rows':[{'rate':'12.2%'}]}}})['tables']['t']['rows'][0]['rate'],'12.2')

    def test_edits_accept_equivalent_python_tokens_and_return_exact_candidates(self):
        self.assertEqual(apply_edits("x={'unit': '百分点'}",[{'before':'"unit":"百分点"','after':"'unit':'个百分点'"}]),"x={'unit':'个百分点'}")
        with self.assertRaises(AnalysisEditError) as error:
            apply_edits('print(1)\nprint(1)',[{'before':'print(1)','after':'print(2)'}])
        self.assertEqual([c['line'] for c in error.exception.details['candidates']],[1,2])
        with self.assertRaises(AnalysisEditError) as error:
            apply_edits('WACC = 0.122',[{'before':'WACC = 0.123','after':'WACC = 0.127'}])
        self.assertEqual(error.exception.details['candidates'][0]['text'],'WACC = 0.122')

    def test_three_binding_forms_use_the_report_formatter(self):
        report=compile_report({'tables':{'forecast':{'row_key':'year','columns':{'year':{},'revenue':{'unit':'人民币亿元','decimals':2}},'rows':[{'year':'2025E','revenue':{'value':'3242','unit':'人民币百万元'}}]}}})
        text=bind_text('{{forecast.2025E.revenue}}\n\n{{table:forecast}}\n\n{{chart:chart.png}}',report['tables'],{'chart.png':'/verified/chart.png'})
        self.assertIn('32.42 CNY 亿元',text)
        self.assertIn(render_table(report['tables']['forecast']),text)
        self.assertIn('![chart.png](/verified/chart.png)',text)
        with self.assertRaisesRegex(ValueError,'可用图片.*chart.png'):
            bind_text('{{chart:missing.png}}',report['tables'],{'chart.png':'/verified/chart.png'})

if __name__=='__main__':unittest.main()
