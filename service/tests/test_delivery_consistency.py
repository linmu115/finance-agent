import json
import subprocess
import sys
import unittest
from service.delivery_consistency import scan_delivery, source_quantities


def forecast():
    return {'forecast':{'artifact':'forecast.csv','columns':{'year':{},'revenue':{'unit':'百万元','currency':'CNY'},'EPS':{'unit':'元/股','currency':'CNY'}},
                        'rows':[{'year':'2030E','revenue':'1250','EPS':'.72'},{'year':'2031E','revenue':'1700','EPS':'.94'}]}}


class DeliveryConsistencyTests(unittest.TestCase):
    def test_exact_conversion_and_decimal_rounding(self):
        result=scan_delivery('|年度|收入（人民币亿元）|EPS（元/股）|\n|---|---|---|\n|2030E|12.50|0.72|',forecast())
        self.assertEqual(result['counts'],{'exact':2});self.assertEqual(result['issue_count'],0)

    def test_order_of_magnitude_and_period_do_not_match_other_year(self):
        result=scan_delivery('|年度|收入（人民币亿元）|EPS（元/股）|\n|---|---|---|\n|2030E|125|0.94|',forecast())
        self.assertEqual([c['classification'] for c in result['checks']],['order_of_magnitude','wrong_cell'])
        self.assertEqual(result['checks'][0]['expected'][0]['power'],1)

    def test_source_can_expose_wrong_value_repeated_in_registry_and_csv(self):
        tables=forecast();tables['forecast']['rows'][0]['EPS']='.94'
        source=[{'metric':'EPS','value':'.72','currency':'CNY/share','period':'2030E'}]
        result=scan_delivery('|年度|EPS（元/股）|\n|---|---|\n|2030E|0.94|',tables,source)
        self.assertTrue(result['checks'][0]['issue']);self.assertEqual(result['checks'][0]['expected'][0]['value'],'.72')

    def test_csv_header_with_qualifiers_and_self_reference_exclusion(self):
        tables=forecast()
        artifact={'name':'download-forecast.csv','artifact':'forecast.csv','format':'csv','text':'FY,收入（人民币亿元，机构预测）\n2030E,1250\n'}
        source=[{'metric':'revenue','value':'1250000000','currency':'CNY','period':'2030E'}]
        result=scan_delivery(tables=tables,source_records=source,attachments=[artifact])
        self.assertEqual(result['checks'][0]['expected'][0]['power'],2)

    def test_markdown_grid_matches_coordinates_even_when_transposed(self):
        table={'grid':{'columns':{'永续增长率':{},'WACC 9%（港元/股）':{'unit':'元/股','currency':'HKD'},'WACC 10%（港元/股）':{'unit':'元/股','currency':'HKD'}},
                       'rows':[{'永续增长率':'.01','WACC 9%（港元/股）':'8.12','WACC 10%（港元/股）':'7.19'},
                               {'永续增长率':'.02','WACC 9%（港元/股）':'9.21','WACC 10%（港元/股）':'8.05'}]}}
        result=scan_delivery('敏感性（港元/股）\n| WACC / g | 1% | 2% |\n|---|---|---|\n|9%|8.12|9.21|\n|10%|9.21|8.05|',table)
        issues=[c for c in result['checks'] if c['issue']]
        self.assertEqual(len(issues),1);self.assertEqual(issues[0]['classification'],'wrong_cell')
        self.assertEqual(issues[0]['expected'][0]['value'],'7.19')

    def test_unrounded_margin_difference(self):
        table={'margin':{'columns':{'year':{},'毛利率':{'unit':'%'}},'rows':[{'year':'2030','毛利率':'40.376'},{'year':'2031','毛利率':'31.143'}]}}
        result=scan_delivery('|指标|变化|\n|---|---|\n|毛利率|-9.24个百分点|',table)
        self.assertTrue(result['checks'][0]['issue']);self.assertEqual(result['checks'][0]['expected'][0]['value'],'-9.23300')

    def test_source_merged_cells_preserve_money_after_yoy_header(self):
        sources=[{'rows':[['Valuation in RMB mn'],['Unleveraged FCF 20 30 40\nYoY%\nEV (End-29E) 900\nFully diluted equity value (End-29E) 950']]}]
        refs=source_quantities(sources);ev=next(q for q in refs if q['metric']=='ev')
        self.assertEqual(ev['unit'],['money','CNY','1000000'])

    def test_valuation_gap_is_derived_and_rounded_not_found_anywhere(self):
        table={'valuation':{'columns':{'metric':{},'value':{'unit':'百万元','currency':'CNY'}},'rows':[{'metric':'EV','value':'892.734'}]}}
        source=[{'rows':[['Valuation in RMB mn'],['EV (End-29E) 900']]}]
        result=scan_delivery('DCF差异为人民币1.2百万元。\nDCF差异为人民币7.3百万元。',table,source)
        self.assertTrue(result['checks'][0]['issue']);self.assertEqual(result['checks'][1]['classification'],'rounding_consistent')

    def test_unknown_and_zero_are_distinct_and_no_feedback(self):
        result=scan_delivery('收入人民币0百万元。')
        self.assertEqual(result['counts'],{'unmatched':1});self.assertFalse(result['checks'][0]['issue'])
        self.assertFalse(result['feedback_enabled']);self.assertEqual(result['mode'],'observation_only')

    def test_metadata_page_and_operations_substring_are_not_quantities(self):
        from service.delivery_quantities import unit
        self.assertIsNone(unit('Net cash generated from operations'))
        result=scan_delivery(attachments=[{'name':'input.csv','format':'csv','text':'metric,value,unit,physical_page\nrevenue,250,RMB mn,2\n'}])
        self.assertEqual(len(result['checks']),1);self.assertEqual(result['checks'][0]['claim']['value'],'250')

    def test_both_standard_tie_rounding_modes(self):
        table={'x':{'columns':{'revenue':{'unit':'百万元','currency':'CNY'}},'rows':[{'revenue':'14.125'}]}}
        result=scan_delivery('收入人民币14.12百万元；收入人民币14.13百万元。',table)
        self.assertEqual(result['counts'],{'rounding_consistent':2})

    def test_declared_display_unit_precedes_source_original_unit(self):
        table={'x':{'columns':{'revenue':{'unit':'百万元','currency':'CNY'}},'rows':[{'revenue':'15'}]}}
        result=scan_delivery('单位：人民币百万元，金额由原报表人民币千元换算。\n|指标|金额|\n|---|---|\n|收入|15|',table)
        self.assertEqual(result['counts'],{'exact':1})

    def test_cli_reads_payload_and_emits_adapter_ready_json(self):
        payload={'answer':'收入人民币0元。'}
        result=subprocess.run([sys.executable,'scripts/scan-delivery-consistency.py'],input=json.dumps(payload),text=True,capture_output=True,check=True)
        self.assertEqual(json.loads(result.stdout)['mode'],'observation_only')


if __name__=='__main__':unittest.main()
