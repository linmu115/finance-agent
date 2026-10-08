import json
from pathlib import Path
from types import SimpleNamespace, MethodType
import unittest

from service.analysis_report import compile_report
from service.financial_workpapers import cell
from service.workpaper_analyst import AnalystData
from service.workpaper_explanations import driver_evidence, find_explanations
from service.workpaper_signal_followups import persistence, signal_followups
from service.workpaper_depth import enrich_workpaper_context
from service.workpaper_handoff import answer_handoff
from service.workpaper_expectations import expectations_report
from service.workpaper_expectations_data import context_tables, reference_tables, candidate_issue
from service.workpaper_comparison import comparison_report
from service.tests.test_workpaper_expectations import forecast, actual
from service.tests.test_expectations_data import record
from service.tests.test_workpaper_comparison import subject


FIXTURE = json.loads((Path(__file__).parent/'fixtures/workpapers/explanation_pages.json').read_text('utf8'))


def data(name='carote', pages=None):
    f = FIXTURE[name]
    a = SimpleNamespace(ps=[f['period'], str(int(f['period'][:4])-1)+f['period'][4:]], st=SimpleNamespace(scope='consolidated'),
                        d=SimpleNamespace(doc=f['document_id'], document={'original_name': name+'.pdf'},
                                          pages=pages if pages is not None else {int(p): t for p, t in f['pages'].items()}))
    a.source_text = MethodType(AnalystData.source_text, a)
    return a


class ManagementEvidenceTests(unittest.TestCase):
    def test_carote_specific_causes_and_headline_amounts_are_not_cause_amounts(self):
        a = data()
        for key, page, phrase in [('margin_effect',11,'tariffs imposed by the United States'),
                                 ('finance_net',12,'fixed deposits'), ('inventory',14,'stocked more finished goods'),
                                 ('receivables',14,'sales growth in offline channels'), ('payables',14,'decline in procurement')]:
            row = driver_evidence(a,key,key)
            self.assertEqual(row['disclosure_status'],'qualitative', key)
            self.assertTrue(any(r['page']==page and phrase in r['quote'] for r in row['evidence']),key)
        cfo = driver_evidence(a,'cfo','经营现金流')
        self.assertEqual(cfo['disclosure_status'],'quantitative')
        self.assertIn('41.2 million',cfo['evidence'][0]['quote'])
        self.assertIn('局部',cfo['quantitative_limit'])

    def test_yili_eight_manual_checks_and_quantified_volume_cause(self):
        a = data('yili')
        checks = [('selling',18,'广告营销费用'),('administrative',18,'职工薪酬费用'),
                  ('finance_costs',18,'利息支出减少'),('research',19,'折旧修理费用'),
                  ('cfo',19,'春节备货'),('inventory',20,'液体乳库存量'),
                  ('asset_impairment',25,'澳优乳业商誉减值'),('contract_liabilities',26,'预收经销商')]
        for key,page,phrase in checks:
            row=driver_evidence(a,key,key)
            self.assertEqual(row['disclosure_status'],'qualitative',key)
            self.assertTrue(any(r['page']==page and phrase in r['quote'] for r in row['evidence']),key)
        row=driver_evidence(a,'revenue_effect','营业收入')
        self.assertEqual(row['disclosure_status'],'quantitative')
        self.assertTrue(any('减少收入60.46' in r.get('quantified_cause_excerpt','') for r in row['evidence']))

    def test_quotes_are_verbatim_and_business_qualifiers_are_preserved(self):
        for name in FIXTURE:
            a=data(name)
            for key in ('revenue_effect','margin_effect','selling','finance_net','cfo','inventory','asset_impairment'):
                for ref in driver_evidence(a,key,key)['evidence']:
                    self.assertIn(ref['quote'],a.d.pages[ref['page']], (name,key,ref['quote']))
        refs=find_explanations(data('yili'),'inventory','存货')
        self.assertTrue(any(r['quote'].startswith('液体乳库存量') for r in refs))

    def test_no_keyword_in_definition_policy_forecast_or_previous_year_leak(self):
        a=data()
        self.assertEqual({r['page'] for r in find_explanations(a,'inventory','存货')},{14})
        self.assertFalse(find_explanations(a,'cfo','经营现金流',period='2024-H1'))
        a=data(pages={1:'Management Discussion and Analysis\n\nRevenue may decline next year due to tariffs.\n\nAccounting policies\nIncome tax is recognised due to taxable profits.'})
        self.assertFalse(find_explanations(a,'revenue_effect','营业收入'))
        self.assertFalse(find_explanations(a,'tax','所得税'))

    def test_unsearched_pages_are_not_evidence_of_no_disclosure(self):
        a=data(pages={1:'Management Discussion and Analysis',3:'Inventories 100 200'})
        r=driver_evidence(a,'inventory','存货')
        self.assertEqual(r['disclosure_status'],'not_stated')
        self.assertEqual(r['search']['missing_pages'],[2])
        self.assertIn('未检出',r['quantitative_limit'])

    def test_geographic_numbers_after_a_qualitative_cause_do_not_quantify_it(self):
        a=data()
        r=driver_evidence(a,'contribution_0','United States')
        self.assertEqual(r['disclosure_status'],'qualitative')
        self.assertTrue(any('offline sales channels' in e['quote'] for e in r['evidence']))


def signal(period, triggered='是', value='0.5'):
    return {'key':period+'_cash_conversion','signal':'CFO/合并净利润','family':'利润与现金流',
            'value':cell(value,'ratio'),'triggered':triggered}


class SignalFollowupTests(unittest.TestCase):
    def test_two_observations_are_not_a_continuous_trend(self):
        a=data(); rows=[signal(p) for p in a.ps]
        follows, evidence, readable=signal_followups(a,rows)
        self.assertEqual(len(follows),2)
        for r in follows:
            self.assertEqual(r['persistence']['known_sample_count'],2)
            self.assertFalse(r['persistence']['allow_continuous_claim'])
            self.assertNotIn('连续',r['persistence']['summary'])
            self.assertTrue(r['tracking_metrics'])
            self.assertTrue(all(x['status']=='candidate_not_evidence' and x['test'] for x in r['alternative_explanations']))
        self.assertEqual(evidence[0]['disclosure_status'],'quantitative')
        self.assertEqual(evidence[1]['disclosure_status'],'not_stated')
        self.assertEqual(len(readable['rows']),2)

    def test_three_samples_need_matching_adjacent_windows_and_actual_repetition(self):
        periods=['2025-H1','2024-H1','2023-H1'];rows=[signal(p) for p in periods]
        self.assertTrue(persistence(rows[0],rows,periods)['allow_continuous_claim'])
        rows[-1]['triggered']='否'
        self.assertFalse(persistence(rows[0],rows,periods)['allow_continuous_claim'])
        rows[-1]=signal(periods[-1],'未知',None)
        p=persistence(rows[0],rows,periods)
        self.assertEqual(p['known_sample_count'],2);self.assertEqual(p['missing_periods'],['2023-H1'])
        periods[-1]='2021-H1';rows[-1]=signal(periods[-1])
        self.assertFalse(persistence(rows[0],rows,periods)['allow_continuous_claim'])

    def test_a_change_is_one_signal_observation_and_only_triggered_get_followups(self):
        a=data(); r={'key':'inventory_growth_gap','signal':'存货增速差','family':'存货','value':cell(25,'%'),'triggered':'是'}
        rows=[r,signal(a.ps[0],'否','2'),signal(a.ps[1],'未知',None)]
        follows,_,_=signal_followups(a,rows)
        self.assertEqual(len(follows),1)
        self.assertEqual(follows[0]['persistence']['known_sample_count'],1)
        self.assertTrue(any('库龄' in x for x in follows[0]['tracking_metrics']))


class BasisConstraintTests(unittest.TestCase):
    def test_unknown_profit_identity_is_never_parent_profit_even_in_a_version_link(self):
        old=record('old',100,metric='net_profit',published='2024-05-01');old['exclusion_reason']=candidate_issue(old,[])
        new=record('new',110,metric='net_profit_parent',published='2024-11-01')
        report=expectations_report([old,new],[actual(120)])
        limits=report['answer_constraints']
        c=next(c for c in limits if c['code']=='profit_attribution_unknown')
        self.assertIn('label_as_parent_profit',c['prohibited_uses']);self.assertEqual(c['subject']['record_ids'],['old'])
        tabs,_=context_tables([old,new],[],None)
        link=tabs['version_links_CNY_money']
        self.assertIsNone(link['rows'][0]['change']['value'])
        self.assertIn('parent_profit_comparison',link['answer_constraints'][0]['prohibited_uses'])
        identity=next(c for c in link['answer_constraints'] if c['code']=='profit_attribution_unknown')
        self.assertEqual(identity['subject']['columns'],['previous'])
        self.assertNotIn('new',identity['subject']['record_ids'])

    def test_revenue_reference_retains_gap_but_forbids_same_basis_error(self):
        r=record('r',100,metric='revenue');r['label']='收入'
        a=actual(110,'revenue',unit='元');a['label']='营业总收入'
        t=reference_tables([r],[a])['reference_gaps_CNY_money']
        self.assertEqual(t['rows'][0]['difference']['value'],'10')
        c=t['answer_constraints'][0]
        self.assertIn('same_basis_error',c['prohibited_uses'])
        self.assertIn('beat_miss_conclusion',c['prohibited_uses'])
        self.assertIn('revenue_boundary',[i['dimension'] for i in c['issues']])
        self.assertEqual(c['subject']['row_key'],'r')

    def test_aligned_comparison_has_no_limit_unaligned_scope_and_window_do(self):
        a=subject();b=subject('old',2023)
        self.assertEqual(comparison_report([a,b])['answer_constraints'],[])
        b['scope']='parent';b['period_end']='2023-06-30';b['metadata'].pop('accounting_standard')
        r=comparison_report([a,b]);self.assertEqual(len(r['answer_constraints']),1)
        c=r['answer_constraints'][0]
        self.assertEqual(set(c['subject']['columns']),{'a24','old'})
        self.assertIn('net_profit',c['subject']['row_keys'])
        self.assertTrue({'scope','period_window','accounting_standard'}<={i['dimension'] for i in c['issues']})

    def test_constraints_survive_compile_and_tool_handoff_and_do_not_block_other_values(self):
        f=forecast('f',100);f['scope']='unspecified'
        raw=expectations_report([f],[actual(110)])
        compiled=compile_report(raw)
        self.assertEqual(compiled['answer_constraints'],raw['answer_constraints'])
        self.assertEqual(answer_handoff(compiled)['answer_constraints'],raw['answer_constraints'])
        self.assertIsNotNone(compiled['tables']['ledger_CNY_money']['rows'][0]['value'])
        self.assertIsNone(compiled['tables']['actual_vs_expected_CNY_money']['rows'][0]['difference'])


class PipelineAdapterTests(unittest.TestCase):
    def test_n2_namespaced_refs_deduplicated_quotes_and_no_pending_as_not_stated(self):
        a=data(); rows=[signal(a.ps[0])]
        follows,evidence,_=signal_followups(a,rows)
        variance={'drivers_evidence':[driver_evidence(a,'cfo','经营现金流',{'table':'context_changes','row_key':'cfo','column':'change'})]}
        signals={'drivers_evidence':evidence,'signal_followups':follows}
        ext=enrich_workpaper_context(None,'p',selection={},reports={'variance_attribution':variance,'anomaly_signals':signals},context={})
        cfo=[r for r in ext['management_evidence'] if r['quotes'] and 'cash used in operating' in r['quotes'][0]['quote']]
        self.assertEqual(len(cfo),1)
        self.assertIn('variance_context_changes.cfo.change',cfo[0]['linked_refs'])
        self.assertIn('signals_signals.2025-H1_cash_conversion.value',cfo[0]['linked_refs'])
        self.assertIn(cfo[0]['id'],ext['signal_followups'][0]['management_evidence_ids'])
        self.assertEqual(ext['extensions']['management_evidence'],'ready')
        self.assertEqual(ext['extensions']['comparability_constraints'],'not_provided')
        empty=enrich_workpaper_context(None,'p',selection={},reports={'variance_attribution':{}},context={})
        self.assertEqual(empty['extensions']['management_evidence'],'pending');self.assertFalse(empty['management_evidence'])

    def test_n2_constraint_ref_points_at_every_declared_cell(self):
        a=subject();b=subject('old',2023);b['metadata']={}
        report=comparison_report([a,b])
        ext=enrich_workpaper_context(None,'p',selection={},reports={'comparison':report},context={})
        c=ext['comparability_constraints'][0]
        self.assertIn('comparison_amounts.revenue.a24',c['affected_refs'])
        self.assertIn('same_basis_comparison',c['forbidden_claims'])
        self.assertEqual(ext['extensions']['comparability_constraints'],'ready')


if __name__=='__main__': unittest.main()
