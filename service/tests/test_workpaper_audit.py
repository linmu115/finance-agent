import copy
import json
import unittest
from decimal import Decimal, localcontext
from pathlib import Path

from service.analysis_report import compile_report
from service.workpaper_audit import audit_records, bounds


def record(metric,value,currency='CNY',year='2025-FY',page=1,**kwargs):
    return {'record_id':metric+'_'+str(page),'document_id':'doc','metric':metric,'period':year,'value':value,
            'currency':currency,'entity_id':'entity','scope':'consolidated','scenario':'base','dimensions':{},'data_kind':'analyst_forecast','raw_value':value,
            'source_ref':{'document_id':'doc','page':page,'table_id':'t'+str(page),'normalization':{'scale':'1','statement':'income'}},**kwargs}


class AuditTests(unittest.TestCase):
    def report(self,records,pages=None):
        with localcontext() as ctx:
            ctx.prec=40
            return compile_report(audit_records(records,pages or {},{'title':'test'}),records)

    def checks(self,report):
        return [r for k,t in report['tables'].items() if k!='observations' for r in t['rows']]

    def fixture(self,name):
        data=json.loads((Path(__file__).parent/'fixtures'/'workpapers'/(name+'.json')).read_text(encoding='utf-8'))
        with localcontext() as ctx:
            ctx.prec=40
            return compile_report(audit_records(data['records'],{int(k):v for k,v in data['pages'].items()},data['profile']),data['records'])

    def test_eps_weighted_share_calculation_and_difference(self):
        records=[record('eps','2.01','CNY/share'),record('net_profit_parent','200.00'),record('weighted_average_shares','100.00','股')]
        row=self.checks(self.report(records))[0]
        self.assertEqual(row['recomputed'],'2');self.assertEqual(row['difference'],'-0.01')
        self.assertEqual(row['status'],'超出披露精度')

    def test_total_shares_difference_does_not_prove_eps_wrong(self):
        row=self.checks(self.report([record('eps','2.01','CNY/share'),record('net_profit_parent','200.00'),record('total_shares','100.00','股')]))[0]
        self.assertEqual(row['status'],'股数口径待核实')
        self.assertEqual(row['recomputed'],'2')

    def test_unknown_historic_weighted_shares_stays_missing(self):
        row=self.checks(self.report([record('eps','2.00','CNY/share',year='2023-FY'),record('net_profit_parent','200.00',year='2023-FY'),record('issued_shares','100.00','股',year='unknown')]))[0]
        self.assertEqual(row['status'],'无法复算');self.assertIsNone(row['recomputed'])

    def test_pe_growth_and_gross_margin(self):
        records=[record('p_e','5.00','倍'),record('eps','2.00','CNY/share'),record('market_price','10.00','CNY/share'),
                 record('revenue_growth','20.0','percent'),record('revenue','120.00'),record('revenue','100.00',year='2024-FY'),
                 record('gross_margin','40.0','percent'),record('cost_of_goods_sold','-72.00')]
        rows=self.checks(self.report(records))
        for prefix,expected in [('P/E','5'),('相邻','20'),('毛利率','40')]:
            r=next(r for r in rows if r['check'].startswith(prefix))
            self.assertEqual(Decimal(r['recomputed']),Decimal(expected));self.assertEqual(r['status'],'舍入范围内')

    def test_rounding_uses_original_precision(self):
        a=record('eps','1.230','CNY/share')
        self.assertEqual(bounds(a),(Decimal('1.2295'),Decimal('1.2305')))
        a['raw_value']='1.23';self.assertEqual(bounds(a),(Decimal('1.225'),Decimal('1.235')))

    def test_different_currency_does_not_implicitly_convert(self):
        rows=self.checks(self.report([record('p_e','5','倍'),record('eps','2','CNY/share'),record('market_price','10','HKD/share')]))
        self.assertEqual(next(r for r in rows if r['check'].startswith('P/E'))['status'],'无法复算')

    def test_cross_page_conflict_reports_ids_pages_and_interval(self):
        a=record('revenue','120.0',page=1);b=record('revenue','130.0',page=2)
        row=self.checks(self.report([a,b]))[0]
        self.assertEqual(row['status'],'超出披露精度');self.assertEqual(row['pages'],'1, 2')
        self.assertEqual(row['difference'],'10.0')

    def test_segments_and_scenarios_are_not_mixed(self):
        records=[record('revenue','100',page=1,dimensions={'source_label':'Mainland China'}),record('revenue','200',page=2,dimensions={'source_label':'Overseas'}),
                 record('revenue','300',page=3,scenario='optimistic'),record('revenue','200',page=4,scenario='pessimistic')]
        self.assertFalse(self.checks(self.report(records)))

    def test_cmbi_requested_findings_and_precision_boundary(self):
        report=self.fixture('cmbi');rows=self.checks(report)
        labels=[r for r in rows if r['check']=='DCF标题预测年份']
        self.assertEqual(len(labels),1);self.assertIn('2023–2027',labels[0]['detail']);self.assertIn('2024–2028',labels[0]['detail'])
        self.assertTrue(any(r['check']=='币种标注' for r in rows))
        target=next(r for r in rows if r['check'].startswith('目标价=EPS'))
        self.assertEqual(Decimal(target['recomputed']),Decimal('8.881'))
        self.assertEqual(Decimal(target['difference']),Decimal('-0.089'))
        self.assertEqual(target['rounding_low'],'8.786250');self.assertEqual(target['rounding_high'],'8.976250')
        self.assertEqual(target['status'],'舍入范围内')
        self.assertFalse(any(r['check'].startswith('跨页同指标 branded_revenue_share') for r in rows))

    def test_guosen_actual_data_has_useful_checks_and_preserved_basis_gaps(self):
        rows=self.checks(self.fixture('guosen'))
        self.assertTrue(any(r['status']=='舍入范围内' for r in rows))
        eps=next(r for r in rows if r['check'].startswith('EPS') and r['period']=='2023-FY' and r['recomputed'])
        self.assertAlmostEqual(Decimal(eps['recomputed']),Decimal('1.629785904047507423'),places=17)
        self.assertEqual(eps['status'],'股数口径待核实')
        self.assertTrue(any(r['status']=='无法复算' for r in rows))
        low=next(r for r in rows if r['check'].startswith('目标价区间下限'))
        high=next(r for r in rows if r['check'].startswith('目标价区间上限'))
        self.assertEqual(Decimal(low['recomputed']),Decimal('33.82'));self.assertEqual(Decimal(high['recomputed']),Decimal('35.60'))
        self.assertEqual(low['status'],'舍入范围内')
        self.assertTrue(any(r['check']=='DCF敏感性单元复算' and r['status']=='无法复算' for r in rows))

    def test_audit_does_not_mutate_ingested_records(self):
        records=[record('eps','1.23','CNY/share')];before=copy.deepcopy(records)
        self.report(records);self.assertEqual(records,before)


if __name__=='__main__':unittest.main()
