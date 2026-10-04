import unittest
from decimal import Decimal
from service.research_models import financial_quality, ValidationError

class AttributionTests(unittest.TestCase):
    def spec(self):
        spec = {'currency':'CNY','amount_scale':'1','period_basis':'FY','receivables_sales_basis':'revenue_proxy','payables_cost_basis':'cogs_proxy','volume_unit':'units','periods':[
            {'year':2024,'days':'365','revenue':'1000','volume':'100','unit_price':'10','cogs':'600','opex':'200','other_operating_income':'10','ebit':'210','net_income':'150','cfo':'120'},
            {'year':2025,'days':'365','revenue':'1330','volume':'120','unit_price':'11','cogs':'700','opex':'230','other_operating_income':'15','ebit':'400','net_income':'280','cfo':'300','nonrecurring_net_income':'30','receivables_begin':'10','receivables_end':'40','inventory_begin':'10','inventory_end':'20','payables_begin':'10','payables_end':'30'}]}
        spec['profit_bridge'] = {'anchor':'ebit','definition':'Synthetic EBIT after D&A, before interest and tax','opex_definition':'Synthetic operating expenses excluding finance','other_operating_income_definition':'Synthetic net operating gains','finance_expense_treatment':'excluded'}
        for row in spec['periods']:
            row['ebit_basis'] = {'basis':'assumption','rationale':'Synthetic test input; not a company disclosure'}
        return spec
    def test_exact_bridges_and_unexplained_residual(self):
        r=financial_quality(self.spec());b=r['tables']['attribution'][0]
        self.assertEqual(Decimal(b['volume_effect']),Decimal(210))
        self.assertEqual(Decimal(b['price_effect']),Decimal(110))
        self.assertEqual(Decimal(b['revenue_residual']),Decimal(10))
        self.assertEqual(Decimal(b['ebit_change']),Decimal(190))
        self.assertEqual(Decimal(b['ebit_residual']),Decimal(-15))
        row=r['tables']['quality'][1]
        self.assertEqual(Decimal(row['cash_profit_gap']),Decimal(20))
        self.assertEqual(Decimal(row['recurring_net_income']),Decimal(250))
        self.assertEqual(Decimal(row['working_capital_change']),Decimal(20))
    def test_missing_driver_not_zero_and_no_nonconsecutive_bridge(self):
        s=self.spec();del s['periods'][1]['opex'];r=financial_quality(s)
        self.assertIsNone(r['tables']['attribution'][0]['ebit_change'])
        self.assertIn('absent data is not zero',r['tables']['attribution'][0]['ebit_reason'])
        s['periods'][1]['year']=2026;self.assertEqual(financial_quality(s)['tables']['attribution'],[])
    def test_volume_unit_required_and_negative_oneoff_loss(self):
        s=self.spec();del s['volume_unit']
        with self.assertRaises(ValidationError):financial_quality(s)
        s=self.spec();s['periods'][1]['nonrecurring_net_income']='-30'
        self.assertEqual(Decimal(financial_quality(s)['tables']['quality'][1]['recurring_net_income']),Decimal(310))

    def operating_spec(self):
        s = self.spec()
        s['profit_bridge']['anchor'] = 'reported_operating_profit'
        s['profit_bridge']['definition'] = 'Synthetic reported operating profit including finance expense'
        s['profit_bridge']['finance_expense_treatment'] = 'separate'
        for row, finance, operating in zip(s['periods'], ('20','-15'), ('190','430')):
            del row['ebit']; del row['ebit_basis']
            row.update(finance_expense=finance, reported_operating_profit=operating)
        return s

    def test_reported_operating_profit_bridge_is_not_labeled_ebit(self):
        s=self.operating_spec()
        result=financial_quality(s); bridge=result['tables']['attribution'][0]
        # Independent arithmetic: 430-190 = (1330-1000)-(700-600)
        # -(230-200)+(15-10)-(-15-20) = 240.
        self.assertEqual(Decimal(bridge['reported_operating_profit_change']), Decimal(240))
        self.assertEqual(Decimal(bridge['finance_expense_effect']), Decimal(35))
        self.assertEqual(Decimal(bridge['reported_operating_profit_residual']), Decimal(0))
        self.assertNotIn('ebit_change',bridge)
        self.assertNotIn('ebit',result['tables']['quality'][0])
        self.assertEqual(result['model_version'],'research-models-1.1.0')
        self.assertEqual(s,self.operating_spec())  # input/history is not mutated

    def test_negative_finance_expense_does_not_imply_interest_income(self):
        s=self.operating_spec()
        row=financial_quality(s)['tables']['quality'][1]
        self.assertIsNone(row['net_interest_expense'])
        s['periods'][1].update(interest_expense='30',interest_income='10')
        row=financial_quality(s)['tables']['quality'][1]
        self.assertEqual(Decimal(row['finance_expense']),Decimal(-15))
        self.assertEqual(Decimal(row['net_interest_expense']),Decimal(20))
        self.assertEqual(Decimal(row['finance_expense_noninterest_residual']),Decimal(-35))

    def test_finance_already_in_opex_is_not_double_subtracted(self):
        s=self.operating_spec()
        s['profit_bridge']['finance_expense_treatment']='included_in_opex'
        s['periods'][0]['opex']='220';s['periods'][1]['opex']='215'
        b=financial_quality(s)['tables']['attribution'][0]
        self.assertEqual(Decimal(b['reported_operating_profit_residual']),Decimal(0))
        self.assertNotIn('finance_expense_effect',b)

    def test_explicit_ebit_adjustments_are_recomputed_and_exposed(self):
        s=self.operating_spec();s['profit_bridge']['anchor']='ebit'
        s['profit_bridge']['definition']='Synthetic operating subtotal before net interest; remaining finance components retained'
        for row, adjustment in zip(s['periods'], ('25','20')):
            row['ebit_adjustments']=[{'label':'net interest addback','amount':adjustment,'basis':'assumption','rationale':'Synthetic separately defined net interest, not total finance expense'}]
        result=financial_quality(s); b=result['tables']['attribution'][0]
        self.assertEqual([Decimal(row['ebit']) for row in result['tables']['quality']],[Decimal(215),Decimal(450)])
        self.assertEqual(Decimal(b['ebit_change']),Decimal(235))
        self.assertEqual(Decimal(b['ebit_adjustments_effect']),Decimal(-5))
        self.assertEqual(Decimal(b['ebit_residual']),Decimal(0))
        s['periods'][1]['ebit']='999'
        with self.assertRaisesRegex(ValidationError,'does not equal'):financial_quality(s)

    def test_direct_disclosed_ebit_requires_a_located_source(self):
        s=self.spec();s['periods'][0]['ebit_basis']['basis']='disclosed'
        with self.assertRaisesRegex(ValidationError,'located reference'):financial_quality(s)
        s['source_refs']={'periods.0.ebit_basis':[{'kind':'document','id':'synthetic-document','locator':'page:1'}]}
        self.assertEqual(financial_quality(s)['tables']['quality'][0]['ebit_basis'],'disclosed')

    def test_legacy_unqualified_ebit_is_not_silently_reinterpreted(self):
        s=self.spec();del s['profit_bridge']
        with self.assertRaisesRegex(ValidationError,'not automatically EBIT'):financial_quality(s)
        s=self.operating_spec();s['periods'][1]['ebit']='430'
        with self.assertRaisesRegex(ValidationError,'must not use EBIT'):financial_quality(s)

    def test_missing_finance_is_not_implicitly_zero(self):
        s=self.operating_spec();del s['periods'][1]['finance_expense']
        b=financial_quality(s)['tables']['attribution'][0]
        self.assertIsNone(b['reported_operating_profit_change'])
        self.assertIn('absent data is not zero',b['reported_operating_profit_reason'])

    def test_mixed_reconciliation_modes_are_not_blended(self):
        s=self.spec()
        del s['periods'][1]['ebit_basis']
        s['periods'][1].update(reported_operating_profit='390',ebit_adjustments=[{'label':'interest','amount':'10','basis':'assumption','rationale':'Synthetic addback'}])
        with self.assertRaisesRegex(ValidationError,'same disclosed/assumed or reconciled'):financial_quality(s)

if __name__=='__main__':unittest.main()
