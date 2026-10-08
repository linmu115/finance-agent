import copy
import json
from pathlib import Path
import unittest

from service.cleaning_mapping import mapping_issues
from service.cleaning_consistency import table_semantics
from service.semantic import materialize
from service.source_numbers import policy_table_exclusion

FIXTURES=json.loads((Path(__file__).parent/'fixtures/policy-comparison-development.json').read_text('utf-8'))


def mapped(table,columns=None,unit='元',metric='revenue',skip=True):
    columns=columns or [{'column':2,'period':'2024-FY','start':'2024-01-01','end':'2024-12-31'},
                        {'column':3,'period':'2023-FY','start':'2023-01-01','end':'2023-12-31'}]
    schema={'company':'开发公司','scope':'consolidated_CAS','statement':'notes','currency':'CNY','unit':unit,
            'columns_json':columns,'skipped_rows_json':[{'row':1,'reason':'header'}],
            'skipped_columns_json':[{'column':4,'reason':'comparison'}] if skip else []}
    rows=[{'row':i,'attributes':{'metric':metric,'label':row[0]}} for i,row in enumerate(table['rows'],1) if i>1]
    ext=[{'class':'table_schema','text':f'[[T{table["index"]}]]','span':[0,1],'attributes':schema}]
    ext.extend({'class':'financial_row','text':f'[[T{table["index"]}:R{x["row"]}]]','span':[0,1],'attributes':x['attributes']} for x in rows)
    facts,issues=materialize(ext,[{'table':table,'rows':list(range(1,len(table['rows'])+1))}],'d','fixture')
    issues+=mapping_issues(table,schema,rows,facts=facts)
    return facts,issues,schema,rows


class PolicyTests(unittest.TestCase):
    def test_development_policy_tables_exclude_with_specific_source_evidence(self):
        for name in ('yili-t116','haier-t131'):
            t=FIXTURES[name]
            result=policy_table_exclusion(t)
            self.assertEqual(result['reason'],'nonfinancial_policy_parameters')
            self.assertTrue(result['cells'])
            self.assertEqual(mapping_issues(t,{'statement':'nonfinancial'},[],exclusion_reason=result['note']),[])
            self.assertEqual(table_semantics(t,{'statement':'nonfinancial'},[]),[])

    def test_policy_prose_does_not_excuse_actual_paid_amounts(self):
        for t in (FIXTURES['yili-t39'],{'index':1,'page':1,'rows':[['重要性标准','2024年金额'],['营业收入','100.00']]},
                  {'index':1,'page':1,'rows':[['项目','重要性标准'],['政策阈值','大于100万元'],['实际支付','120万元']]}):
            self.assertIsNone(policy_table_exclusion(t))
            self.assertIn('financial_complexity_is_not_exclusion',{x['reason'] for x in mapping_issues(t,{'statement':'nonfinancial'},[],exclusion_reason='政策')})
            self.assertIn('numeric_table_without_records',{x['reason'] for x in table_semantics(t,{},[])})

    def test_numeric_threshold_in_policy_column_is_not_report_amount(self):
        t={'index':1,'page':1,'rows':[['判断项目','会计政策判断标准'],['重要性比例','5%']]}
        self.assertIsNotNone(policy_table_exclusion(t))


class ComparisonTests(unittest.TestCase):
    def test_omitted_or_skipped_growth_is_materialized_and_checked(self):
        t={'index':1,'page':1,'rows':[['项目','2024','2023','同比增减（%）'],['营业收入','120.00','100.00','20.00']]}
        for skip in (False,True):
            facts,issues,_,_=mapped(t,skip=skip)
            self.assertFalse([i for i in issues if i.get('severity')!='review'],issues)
            growth=next(f for f in facts if f['metric']=='revenue_growth_rate')
            self.assertEqual(growth['value'],'20.00')
            self.assertEqual(growth['source']['normalization']['derived_comparison_check']['status'],'consistent')
            self.assertEqual(len(facts),3)

    def test_percentage_points_and_change_amount_keep_units_and_source_sign(self):
        for header,raw,unit,a,b,metric,expected,currency in [
            ('比上年增减','减少4.39个百分点','%','15.81','20.20','roe','-4.39','percentage_points'),
            ('增减额','20.00','万元','120','100','revenue','200000.00','CNY')]:
            t={'index':1,'page':1,'rows':[['项目','2024','2023',header],['财务指标',a,b,raw]]}
            fs,issues,_,_=mapped(t,unit=unit,metric=metric)
            self.assertFalse([i for i in issues if i.get('severity')!='review'],issues)
            f=next(f for f in fs if f['source']['column']==4)
            self.assertEqual(f['value'],expected);self.assertEqual(f['currency'],currency)
            self.assertEqual(f['source']['normalization']['derived_comparison_check']['status'],'consistent')

    def test_ambiguous_comparison_is_review_only_but_missing_amount_is_blocking(self):
        t={'index':1,'page':1,'rows':[['项目','2024','2023','同比变动'],['营业收入','120','100','20']]}
        fs,issues,_,_=mapped(t)
        self.assertEqual(len(fs),2)
        self.assertEqual({i['reason'] for i in issues},{'derived_comparison_not_materialized'})
        self.assertTrue(all(i['severity']=='review' for i in issues))
        t['rows'][0][3]='第三方销售额'
        _,issues,_,_=mapped(t,skip=False)
        self.assertIn('unmapped_numeric_column',{i['reason'] for i in issues})

    def test_unequal_periods_do_not_supply_a_fictitious_comparison_pair(self):
        t={'index':1,'page':1,'rows':[['项目','全年','半年','同比增减（%）'],['营业收入','120','100','20']]}
        columns=[{'column':2,'period':'2024-FY'},{'column':3,'period':'2023-H1'}]
        fs,issues,_,_=mapped(t,columns=columns,skip=False)
        self.assertEqual(len(fs),2)
        self.assertIn('unmapped_numeric_column',{i['reason'] for i in issues})

    def test_invalid_coordinate_stays_a_mapping_issue_not_an_extension_crash(self):
        t={'index':1,'page':1,'rows':[['项目','2024','2023','同比增减（%）'],['营业收入','120','100','20']]}
        fs,issues,_,_=mapped(t,columns=[{'column':2,'period':'2024-FY'},{'column':99,'period':'2023-FY'}],skip=False)
        self.assertEqual(len(fs),1)
        self.assertIn('unmapped_numeric_column',{i['reason'] for i in issues})

    def test_existing_mismatched_growth_is_flagged_without_rewriting_amounts(self):
        t={'index':1,'page':1,'rows':[['项目','2024','2023','变动比例（%）'],['营业收入','120','100','25']]}
        columns=[{'column':2,'period':'2024-FY'},{'column':3,'period':'2023-FY'},
                 {'column':4,'period':'2024-FY','metric':'revenue_growth_rate','unit':'%','currency':'percent'}]
        fs,issues,_,_=mapped(t,columns=columns)
        self.assertEqual([f['value'] for f in fs],['120','100','25'])
        mismatch=next(i for i in issues if i['reason']=='derived_comparison_mismatch')
        self.assertEqual(mismatch['severity'],'review');self.assertEqual(mismatch['evidence']['expected'],'20.0')

    def test_percentage_point_disclosure_is_not_excused_by_a_growth_type(self):
        t={'index':1,'page':1,'rows':[['项目','2024','2023','比上年增减（百分点）'],['利润率','20','10','10']]}
        columns=[{'column':2,'period':'2024-FY'},{'column':3,'period':'2023-FY'},
                 {'column':4,'period':'2024-FY','metric':'margin_growth','semantic_type':'growth_rate','unit':'%','currency':'percent'}]
        _,issues,_,_=mapped(t,columns=columns,unit='%',metric='margin')
        self.assertIn('derived_comparison_mismatch',{i['reason'] for i in issues})

    def test_negative_base_is_explicitly_unverified(self):
        t={'index':1,'page':1,'rows':[['项目','2024','2023','同比增减（%）'],['利润','10','-5','300']]}
        _,issues,_,_=mapped(t)
        reason=next(i for i in issues if i['reason']=='derived_comparison_unverified')
        self.assertIn('非正',reason['evidence']['reason'])

    def test_two_amount_aliases_resolve_through_the_shared_metric_contract(self):
        t={'index':1,'page':1,'rows':[['项目','2024','2023','变动比例（%）'],['经营活动产生的现金流量净额','120','100','20']]}
        columns=[{'column':2,'period':'2024-FY','metric':'operating_cash_flow_net'},
                 {'column':3,'period':'2023-FY','metric':'operating_cash_flow_net'}]
        fs,issues,_,_=mapped(t,columns=columns,metric='operating_cash_flow')
        self.assertFalse([i for i in issues if i.get('severity')!='review'],issues)
        self.assertEqual(next(f for f in fs if f['source']['column']==4)['value'],'20')

    def test_development_amount_and_sparse_header_tables(self):
        for name,cols in [('yili-t14',(2,3)),('haier-t19',(4,7))]:
            t=FIXTURES[name]
            definitions=[{'column':c,'period':f'{y}-FY','start':f'{y}-01-01','end':f'{y}-12-31'} for c,y in zip(cols,(2024,2023))]
            fs,issues,_,_=mapped(t,columns=definitions,skip=False)
            self.assertFalse([i for i in issues if i.get('severity')!='review'],issues)
            checks=[f['source']['normalization']['derived_comparison_check'] for f in fs if f['metric'].endswith('_growth_rate')]
            self.assertTrue(checks)
            self.assertTrue(all(c['status'] in {'consistent','unverified'} for c in checks),checks)


from service.tests import test_script_cleaning as cleaning_fixture


class PolicyCommitTests(unittest.TestCase):
    setUp=cleaning_fixture.ScriptCleaningTests.setUp
    tearDown=cleaning_fixture.ScriptCleaningTests.tearDown
    job=cleaning_fixture.ScriptCleaningTests.job

    def test_policy_zero_facts_commits_and_source_remains_queryable(self):
        _,parsed=self.s._clean_source('p',self.did)
        t=copy.deepcopy(FIXTURES['haier-t131']);t.update(index=0,page=1)
        parsed['tables']=[t]
        self.s._persist_prepared('p',self.did,parsed)
        result=self.s.begin_script_cleaning('p',[self.did],'owner','fixture')['data']
        self.assertEqual(result['coverage']['tables_completed'],1)
        self.assertEqual(result['fact_count'],0)
        raw=self.s.get_source_table('p',self.did,'t0')['data']['items'][0]['rows']
        self.assertEqual(raw,t['rows'])
        with self.s.store.connect() as db:
            batch=json.loads(db.execute('SELECT result_json FROM normalization_batches').fetchone()[0])
        self.assertEqual(json.loads(batch['exclusion_reason'])['reason'],'nonfinancial_policy_parameters')

    def test_ambiguous_comparison_does_not_shelve_amounts(self):
        _,parsed=self.s._clean_source('p',self.did)
        parsed['tables'][0]['rows']=[['label','2025','2024','同比变动'],['Revenue','100','80','25'],['Cost','40','30','33']]
        self.s._persist_prepared('p',self.did,parsed)
        result=self.s.commit_cleaning_result('p',self.pid,self.job())['data']
        self.assertEqual(result['coverage']['tables_completed'],1)
        self.assertEqual(result['fact_count'],4)
        with self.s.store.connect() as db:
            batch=json.loads(db.execute('SELECT result_json FROM normalization_batches').fetchone()[0])
        self.assertEqual({i['reason'] for i in batch['issues']},{'derived_comparison_not_materialized'})

    def test_reported_comparison_mismatch_commits_with_local_warning(self):
        _,parsed=self.s._clean_source('p',self.did)
        parsed['tables'][0]['rows']=[['label','2025','2024','同比增减（%）'],['Revenue','100','80','30'],['Cost','40','30','33']]
        self.s._persist_prepared('p',self.did,parsed)
        for row in self.payload['tables'][0]['rows']:
            attrs=row['attributes']
            attrs['columns_json']=json.loads(self.schema['columns_json'])+[
                {'column':4,'period':'2025-H1','metric':attrs['metric']+'_growth_rate','unit':'%','currency':'percent','semantic_type':'growth_rate'}]
        result=self.s.commit_cleaning_result('p',self.pid,self.job())['data']
        self.assertEqual(result['coverage']['tables_completed'],1)
        self.assertEqual(result['fact_count'],6)
        with self.s.store.connect() as db:
            facts=[dict(r) for r in db.execute('SELECT * FROM facts')]
        growth=next(f for f in facts if f['metric']=='revenue_growth_rate')
        self.assertEqual(growth['value'],'30')
        self.assertEqual(growth['quality'],'needs_review')
        self.assertEqual(json.loads(growth['source_json'])['normalization']['derived_comparison_check']['status'],'mismatch')


if __name__=='__main__':unittest.main()
