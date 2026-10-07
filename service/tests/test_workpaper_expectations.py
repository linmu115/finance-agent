import copy
import unittest
from decimal import Decimal as D

from service.analysis_report import compile_report
from service.financial_workpapers import WorkpaperInputError
from service.workpaper_expectations import expectations_report


def forecast(rid, value, publisher='A', published='2024-09-01', metric='net_profit_parent', unit='百万元', **extra):
    return dict(record_id=rid,entity_id='e1',company='甲',metric=metric,period='2024',scope='consolidated',
                scenario='base',publisher=publisher,published_at=published,data_kind='analyst_forecast',
                value=str(value) if value is not None else None,unit=unit,currency='CNY',source={'record_id':rid,'page':2},**extra)


def actual(value, metric='net_profit_parent', unit='百万元'):
    r=forecast('actual',value,metric=metric,unit=unit,published='2025-04-30')
    r.update(data_kind='reported_actual',fact_id='fact1',publisher=None,scenario='unspecified',source={'fact_id':'fact1','page':50})
    return r


def rows(report, name='actual_vs_expected_CNY_money'):
    return report['tables'][name]['rows']


class ExpectationsCoreTests(unittest.TestCase):
    def report(self, forecasts, actuals=(), cutoff='2024-12-31'):
        return compile_report(expectations_report(forecasts,actuals,cutoff))

    def test_cutoff_inclusive_unknown_dates_and_quoted_actual_separate(self):
        rs=[forecast('old',100),forecast('day',110,published='2024-12-31'),forecast('future',120,published='2025-01-01'),forecast('unknown',130,published=None)]
        quoted=forecast('quoted',80);quoted['data_kind']='quoted_actual';rs.append(quoted)
        r=self.report(rs,[actual(121)])
        self.assertEqual([x['record'] for x in rows(r,'ledger_CNY_money')],['old','day'])
        self.assertEqual({x['record'] for x in rows(r,'excluded_CNY_money')},{'future','unknown','quoted'})
        out=rows(r)[0]
        self.assertEqual(D(out['value']),D(110000000));self.assertEqual(D(out['difference']),D(11000000))
        self.assertEqual(D(out['difference_rate']),D(10))
        self.assertEqual(out['actual_published_at'],'2025-04-30')
        self.assertIn('回测',out['actual_timing'])

    def test_same_institution_revision_then_latest_per_institution_ranking(self):
        r=self.report([forecast('a1',100),forecast('a2',110,published='2024-10-01'),forecast('b1',125,publisher='B')],[actual(120)])
        revisions=rows(r,'revisions_CNY_money')
        self.assertIsNone(revisions[0]['change'])
        self.assertEqual(D(revisions[1]['change']),D(10000000))
        out={x['publisher']:x for x in rows(r)}
        self.assertEqual(out['A']['published_at'],'2024-10-01')
        self.assertEqual(D(out['B']['difference']),D(-5000000))
        self.assertEqual(out['A']['rank'],'最大偏差');self.assertEqual(out['B']['rank'],'最小偏差')
        self.assertEqual(rows(r,'observations')[0]['rank'],'最大偏差')

    def test_eps_not_scaled_as_total_amounts_and_unit_normalization(self):
        eps=forecast('eps',D('1.78'),metric='basic_eps',unit='元/股');fact=actual('1.9','basic_eps','元/股')
        earnings=forecast('earn',100);earnings['value']='10000';earnings['unit']='万元'
        r=self.report([eps,earnings],[fact,actual(110)])
        self.assertEqual(D(rows(r,'actual_vs_expected_CNY_per_share')[0]['difference']),D('.12'))
        self.assertEqual(D(rows(r)[0]['value']),D(100000000))
        self.assertEqual(D(rows(r)[0]['difference']),D(10000000))
        self.assertEqual(r['tables']['actual_vs_expected_CNY_per_share']['columns']['value']['unit'],'元/股')

    def test_no_scope_currency_entity_period_or_eps_basis_mixing(self):
        base=forecast('a',100);facts=[]
        for field,value in [('scope','parent'),('currency','HKD'),('entity_id','e2'),('period','2025'),('basis','restated')]:
            a=actual(100);a[field]=value;facts.append(a)
        r=self.report([base],facts)
        self.assertIsNone(rows(r)[0]['difference'])
        self.assertIn('缺少相同',rows(r)[0]['status'])
        r=self.report([base],[actual(120)])
        self.assertEqual(D(rows(r)[0]['difference']),D(20000000))

    def test_scenarios_and_segments_have_separate_trajectories(self):
        bull=forecast('bull',200);bull['scenario']='bull'
        segment=forecast('segment',50,dimensions={'segment':'liquid_milk'})
        r=self.report([forecast('base',100),bull,segment],[actual(120)])
        out={x['record']:x for x in rows(r)}
        self.assertEqual(D(out['bull']['difference']),D(-80000000))
        self.assertEqual(D(out['base']['difference']),D(20000000))
        self.assertIsNone(out['segment']['difference'])
        self.assertEqual(len(rows(r,'revisions_CNY_money')),3)

    def test_conflicting_latest_same_day_not_replaced_by_earlier_prediction(self):
        r=self.report([forecast('old',80,published='2024-08-01'),forecast('v1',100),forecast('v2',110)],[actual(120)])
        out=rows(r)[0]
        self.assertIsNone(out['value']);self.assertIsNone(out['difference'])
        self.assertIn('冲突',out['status'])
        self.assertEqual(len(rows(r,'ledger_CNY_money')),3)
        evidence=r['tables']['actual_vs_expected_CNY_money']['evidence'][0]['value']['source']['inputs']
        self.assertEqual({x['record_id'] for x in evidence},{'v1','v2'})

    def test_identical_duplicate_source_combined_and_actual_conflict_missing(self):
        r=self.report([forecast('v1',100),forecast('v2',100)],[actual(120)])
        self.assertEqual(len(rows(r)),1);self.assertEqual(D(rows(r)[0]['value']),D(100000000))
        r=self.report([forecast('v1',100)],[actual(120),actual(125)])
        self.assertIsNone(rows(r)[0]['difference']);self.assertIn('实际值冲突',rows(r)[0]['status'])

    def test_zero_and_negative_predictions_and_tied_ranks(self):
        r=self.report([forecast('a',0),forecast('b',-100,publisher='B'),forecast('c',0,publisher='C')],[actual(-50)])
        out={x['publisher']:x for x in rows(r)}
        self.assertIsNone(out['A']['difference_rate']);self.assertEqual(D(out['B']['difference_rate']),D(50))
        self.assertTrue(all(x['rank']=='最大偏差、最小偏差' for x in out.values()))

    def test_raw_research_currency_share_contract_and_sources(self):
        raw=forecast('raw',1.78,metric='basic_eps');del raw['unit'];del raw['source']
        raw['currency']='CNY/share';raw['source_ref']={'page':3,'document_id':'d'}
        r=self.report([raw],[actual('1.9','basic_eps','元/股')])
        self.assertEqual(D(rows(r,'actual_vs_expected_CNY_per_share')[0]['difference']),D('.12'))
        evidence=r['tables']['actual_vs_expected_CNY_per_share']['evidence'][0]['value']['source']['inputs'][0]
        self.assertEqual(evidence['record_id'],'raw');self.assertEqual(evidence['source_ref']['page'],3)

    def test_no_cutoff_uses_all_known_dates_not_undated_no_mutation(self):
        rs=[forecast('future',150,published='2027-01-01'),forecast('unknown',130,published=None)]
        saved=copy.deepcopy(rs);r=self.report(rs,cutoff=None)
        self.assertEqual(rs,saved)
        self.assertEqual(rows(r,'ledger_CNY_money')[0]['published_at'],'2027-01-01')
        self.assertIsNone(rows(r)[0]['actual'])
        self.assertEqual(len(rows(r,'excluded_CNY_money')),1)

    def test_invalid_cutoff_raises_and_quoted_actual_rejected_as_filing(self):
        with self.assertRaises(ValueError):self.report([forecast('a',100)],cutoff='2024-02-30')
        a=actual(100);del a['fact_id'];a['data_kind']='quoted_actual'
        with self.assertRaises(WorkpaperInputError):self.report([forecast('a',100)],[a])


if __name__=='__main__':unittest.main()
