import copy
from decimal import Decimal as D,localcontext
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from service.analysis_report import compile_report,bind_text,display_table,ROUNDING_NOTE
from service.financial_workpapers import cell,financial_workpaper
from service.tests import test_workpaper_annual as annual_tests
from service.workpaper_analyst import AnalystData
from service.workpaper_variance import gross_profit_effects,price_volume_mix,find_explanations,structural_contributions,disclosed_income


def q(v):return cell(v,'元','CNY',sources=[{'document_id':'synthetic','page':1,'table_id':'t','row':1,'column':2}])


class VarianceMathTests(unittest.TestCase):
    def test_explicit_nil_is_distinct_from_absent_or_blank_and_uses_other_period_anchor(self):
        a=SimpleNamespace(ps=['2025-H1','2024-H1'],currency='CNY',pick=lambda *args:cell(None,reason='missing'))
        a.d=SimpleNamespace(pages={1:'Fair value gains on financial assets\nat FVTPL 8 63,015 –\nProfit before tax 40,931 (39,108)'})
        a.st=SimpleNamespace(pick=lambda *args:{'value':'63015000','source_ref':{'page':1,'table_id':'t','normalization':{'label':'Fair value gains on financial assets at FVTPL','scale':'1000'}}})
        a.source_text=lambda p,quote:{'document_id':'test','page':p,'quote':quote}
        self.assertEqual(disclosed_income(a,'fair_value_gains','2024-H1')['value'],'0')
        a.d.pages[1]=a.d.pages[1].replace('63,015 –','63,015')
        self.assertIsNone(disclosed_income(a,'fair_value_gains','2024-H1')['value'])
        a.d.pages[1]='Fair value gains on financial assets 8 63,014 –'
        self.assertIsNone(disclosed_income(a,'fair_value_gains','2024-H1')['value'])
    def test_margin_split_cross_term_and_positive_or_negative_effects(self):
        with localcontext() as ctx:
            ctx.prec=40
            volume,margin=gross_profit_effects(q(120),q(100),q(24),q(30))
            self.assertEqual(D(volume['value']),6);self.assertEqual(D(margin['value']),-12)
            self.assertEqual(D(volume['value'])+D(margin['value']),-6)
        self.assertIsNone(gross_profit_effects(q(20),q(0),q(10),q(0))[0]['value'])

    def test_price_volume_mix_sums_without_double_count_and_keeps_units(self):
        def item(r1,r0,q1,q0):return {'revenue_now':q(r1),'revenue_before':q(r0),'volume_now':cell(q1,'个'),'volume_before':cell(q0,'个')}
        result=price_volume_mix([item(36,20,12,10),item(72,80,18,20)])
        self.assertEqual(sum(D(r[k]['value']) for r in result for k in ('volume','mix','price')),8)
        self.assertEqual(sum(D(r['volume']['value']) for r in result),0)
        self.assertEqual(sum(D(r['mix']['value']) for r in result),-4)
        self.assertEqual(sum(D(r['price']['value']) for r in result),12)
        data=[item(36,20,12,10),item(72,80,18,20)];data[1]['volume_now']['unit']='天'
        self.assertIsNone(price_volume_mix(data)[0]['mix']['value'])

    def test_evidence_does_not_turn_accounting_policy_inventory_or_checkbox_into_revenue_cause(self):
        a=SimpleNamespace(st=SimpleNamespace(scope='consolidated'),d=SimpleNamespace(pages={1:'第三节 管理层讨论与分析\n液体乳库存量增加主要原因：春节备货所致。主营业务导致利润重大变化的说明\n□适用 √不适用',2:'会计政策\n由于税收政策，所得税按权责发生制确认。'}))
        a.source_text=lambda p,quote,**k:{'page':p,'quote':quote,**k}
        self.assertFalse(find_explanations(a,'contribution_0','液体乳'))
        self.assertFalse(find_explanations(a,'contribution_1','主营业务'))
        self.assertFalse(find_explanations(a,'tax','所得税'))
        a.d.pages[1]+='\n销售费用变动原因说明：主要是本期广告费用减少所致。'
        self.assertIn('广告费用',find_explanations(a,'selling','销售费用')[0]['quote'])

    def test_structure_uses_whole_views_and_exact_physical_volumes(self):
        facts=[]
        for label,numbers in [('甲',(36,20,12,10,12,10)),('乙',(72,80,18,20,48,50))]:
            for metric,pair,currency in [('revenue',numbers[:2],'CNY'),('sales_volume',numbers[2:4],'吨'),('cost_of_sales',numbers[4:],'CNY')]:
                for period,amount in zip(('2025-H1','2024-H1'),pair):
                    facts.append({'period':period,'metric':metric,'value':str(amount),'currency':currency,'dimensions':{'product':label},
                                  'source_ref':{'table_id':'detail','page':2,'row':1,'column':2},'document_id':'test','quality':'verified'})
        a=SimpleNamespace(ps=['2025-H1','2024-H1'],currency='CNY',records=facts,d=SimpleNamespace(pages={}),st=SimpleNamespace(scope='consolidated'))
        a.pick=lambda key,p,stmt:q({'revenue':{'2025-H1':108,'2024-H1':100},'cogs':{'2025-H1':60,'2024-H1':60}}[key][p])
        rows,alternatives=structural_contributions(a)
        components=[r for r in rows if r['role']=='component']
        self.assertEqual(len(components),2)
        for name,want in [('volume_effect',0),('mix_effect',-4),('price_effect',12)]:
            self.assertEqual(sum(D(r[name]['value']) for r in components),want)
        residual=next(r for r in rows if r['role']=='residual')
        self.assertEqual(D(residual['revenue_change']['value']),0)
        self.assertEqual(D(residual['gross_change']['value']),0)
        # Missing comparison and a rounded growth rate cannot manufacture a
        # prior revenue. Keep the unknown component and the actual residual.
        a.records=[r for r in facts if not (r['metric']=='revenue' and r['period']=='2024-H1' and r['dimensions']['product']=='乙')]
        rows,_=structural_contributions(a)
        b=next(r for r in rows if r.get('item')=='乙')
        self.assertIsNone(b['revenue_change']['value'])
        self.assertEqual(D(next(r for r in rows if r['role']=='residual')['revenue_change']['value']),-8)


class VarianceContractTests(unittest.TestCase):
    def setUp(self):
        annual_tests.AnnualWorkpapersTests.setUp(self)
        # K1's fixture omits total operating revenue. Add its financial-service
        # interest component so the full CAS bridge must include this step.
        for p,interest in [('2024-FY','386243672.61'),('2023-FY','421289673.85')]:
            r=copy.deepcopy(next(x for x in self.facts if x['period']==p and x['metric']=='revenue'))
            r['metric']='total_operating_revenue';r['fact_id']+='-total';r['value']=str(D(r['value'])+D(interest));self.facts.append(r)
    save_tables=annual_tests.AnnualWorkpapersTests.save_tables

    def report(self):
        with patch('service.financial_workpapers.load_facts',return_value=self.facts):return financial_workpaper(self.s,'p','variance_attribution',document_id=self.doc)

    def test_annual_cas_all_four_residuals_zero_and_no_associate_double_count(self):
        data=self.report();tabs=data['report']['tables'];rows={r['key']:r for r in tabs['profit_bridge']['rows']}
        self.assertEqual([D(r['contribution']) for r in rows.values() if r['role']=='residual'],[0]*4)
        self.assertNotIn('associates',rows)
        self.assertGreater(D(rows['finance_costs']['contribution']),0)
        self.assertEqual(D(rows['parent_profit_change']['contribution']),D('-1975.68046476'))
        self.assertEqual(data['numeric_tables'],tabs)
        self.assertIn('-1,975.6805',bind_text('{{profit_bridge.parent_profit_change.contribution}}',tabs))

    def test_actual_error_changes_residual_and_missing_is_not_zero(self):
        for r in self.facts:
            if r['period']=='2024-FY' and r['metric']=='net_profit_parent':r['value']=str(D(r['value'])+100)
        rows={r['key']:r for r in self.report()['report']['tables']['profit_bridge']['rows']}
        self.assertEqual(D(rows['parent_profit_residual']['contribution']),D('.0001'))
        self.facts=[r for r in self.facts if not (r['period']=='2024-FY' and r['metric']=='asset_impairment_losses')]
        rows={r['key']:r for r in self.report()['report']['tables']['profit_bridge']['rows']}
        self.assertIsNone(rows['asset_impairment']['contribution'])
        self.assertNotEqual(D(rows['operating_profit_residual']['contribution']),0)

    def test_final_attribution_display_adds_up_without_changing_exact_values(self):
        tabs=self.report()['numeric_tables'];original=copy.deepcopy(tabs)
        self.assertEqual(tabs['profit_bridge']['title'],'利润桥')
        checked=0
        for name in ('profit_bridge','contributions'):
            t=tabs[name];display=display_table(t);rows={r['key']:r for r in display['rows']}
            for relation in t['sum_relations']:
                refs=[*relation['parts'],relation['total']]
                if any(rows[r['row']][r['column']] is None for r in refs):continue
                parts=sum(D(rows[r['row']][r['column']]) for r in relation['parts'])
                total=relation['total'];self.assertEqual(parts,D(rows[total['row']][total['column']]))
                checked+=1
            if name=='profit_bridge':self.assertIn(ROUNDING_NOTE,display['notes'])
        self.assertGreater(checked,0);self.assertEqual(tabs,original)

    def test_structure_display_sums_only_within_each_declared_view(self):
        rows=[]
        for view in ('product','region'):
            for key,role,revenue,gross in [('a','component',1000040,400040),('b','component',1000040,400040),('r','residual',0,0),('t','total',2000080,800080)]:
                rows.append({'key':view+key,'item':key,'axis':view,'view':view,'role':role,
                             'revenue_change':q(revenue),'gross_change':q(gross)})
        with patch('service.workpaper_variance.structural_contributions',return_value=(rows,[])):
            t=self.report()['numeric_tables']['contributions']
        exact=copy.deepcopy(t['rows']);display=display_table(t)
        self.assertEqual(len(t['sum_relations']),4)
        shown={r['key']:r for r in display['rows']}
        for relation in t['sum_relations']:
            total=relation['total']
            self.assertEqual(sum(D(shown[r['row']][r['column']]) for r in relation['parts']),D(shown[total['row']][total['column']]))
        self.assertEqual(t['rows'],exact);self.assertIn(ROUNDING_NOTE,display['notes'])


if __name__=='__main__':unittest.main()
