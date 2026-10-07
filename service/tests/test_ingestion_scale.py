import copy
import unittest
from unittest.mock import patch
from service.tests import test_script_cleaning as fixtures
from service.cleaning_batches import structural_batches, batch_view
from service.cleaning_mapping import mapping_issues
from service.document_identity import candidates, ProfileEvidenceError


class IngestionScaleTests(unittest.TestCase):
    setUp=fixtures.ScriptCleaningTests.setUp
    tearDown=fixtures.ScriptCleaningTests.tearDown
    job=fixtures.ScriptCleaningTests.job

    def test_structural_groups_preserve_every_table_and_obey_source_budget(self):
        _,parsed=self.s._clean_source('p',self.did)
        parsed=copy.deepcopy(parsed)
        parsed['tables']=[dict(parsed['tables'][0],index=i) for i in range(23)]
        groups=structural_batches(parsed,budget_chars=2000)
        self.assertEqual([i for b in groups for i in b['tables']],list(range(23)))
        self.assertTrue(any(len(b['tables'])>1 for b in groups))
        self.assertTrue(all(b['source_chars']<=2000 for b in groups))
        view=batch_view(parsed,groups[0],self.did)
        self.assertEqual(view['tables'][0]['rows'],[{'row':i,'cells':r} for i,r in enumerate(parsed['tables'][0]['rows'],1)])

    def test_valid_table_commits_even_when_other_table_has_mapping_error(self):
        _,parsed=self.s._clean_source('p',self.did)
        parsed=copy.deepcopy(parsed);parsed['tables'].append(dict(parsed['tables'][0],index=1))
        self.s._persist_prepared('p',self.did,parsed)
        self.pid=self.s.begin_script_cleaning('p',[self.did],'owner2','fixture')['data']['processing_id']
        payload=copy.deepcopy(self.payload);bad=copy.deepcopy(payload['tables'][0]);bad['index']=1;bad['rows'].pop();payload['tables'].append(bad)
        rid=self.job(payload)
        result=self.s.commit_cleaning_result('p',self.pid,rid)['data']
        self.assertEqual(result['committed_tables'],[0])
        self.assertEqual(result['failed_tables'][0]['index'],1)
        self.assertEqual(result['pending_tables'][self.did],[1])
        self.assertEqual(result['fact_count'],4)

    def test_failed_table_does_not_block_untouched_batches(self):
        state={'documents':[{'document_id':'d','tables':[1,2,3],'completed_tables':[],
                            'batches':[{'tables':[1]},{'tables':[2,3]}]}],
               'jobs':{'run1':{'document_id':'d','candidate_tables':[1],'failed_tables':[1]}}}
        self.assertEqual(self.s._next_clean_batch(state)['tables'],[2,3])
        state['documents'][0]['completed_tables']=[2,3]
        self.assertEqual(self.s._next_clean_batch(state)['tables'],[1])

    def test_sdk_table_error_keeps_other_tables_committable(self):
        _,parsed=self.s._clean_source('p',self.did)
        parsed=copy.deepcopy(parsed);parsed['tables'].append(dict(parsed['tables'][0],index=1))
        self.s._persist_prepared('p',self.did,parsed)
        self.pid=self.s.begin_script_cleaning('p',[self.did],'owner2','fixture')['data']['processing_id']
        payload=copy.deepcopy(self.payload)
        payload['tables'].append({'index':1,'mapping_error':'Source has 2 values for 3 declared meanings','schema':{},'rows':[]})
        result=self.s.commit_cleaning_result('p',self.pid,self.job(payload))['data']
        self.assertEqual(result['committed_tables'],[0])
        self.assertEqual(result['failed_tables'][0]['issues'][0]['reason'],'script_mapping_error')
        self.assertEqual(result['fact_count'],4)

    def test_resume_rechecks_changed_rules_without_deleting_existing_facts(self):
        _,parsed=self.s._clean_source('p',self.did)
        parsed=copy.deepcopy(parsed);parsed['tables'][0]['rows'][1][0]='Unfamiliar financial concept'
        self.s._persist_prepared('p',self.did,parsed)
        self.payload['tables'][0]['rows'][0]['attributes']['metric']='row_2'
        rid=self.job()
        with patch('service.script_cleaning.mapping_issues',return_value=[]):
            self.s.commit_cleaning_result('p',self.pid,rid)
        resumed=self.s.begin_script_cleaning('p',[self.did],'new-owner','fixture')['data']
        self.assertEqual(resumed['pending_tables'][self.did],[0])
        self.assertEqual(resumed['fact_count'],4)

    def test_omitted_ratio_column_and_positional_metric_have_actionable_candidates(self):
        table={'index':1,'rows':[['Item','Amount','Composition %'],['Revenue','100','40%']]}
        schema={'columns_json':[{'column':2}]}
        rows=[{'row':2,'attributes':{'metric':'row_2','label':'Revenue'}}]
        issues=mapping_issues(table,schema,rows)
        missing=next(x for x in issues if x['reason']=='unmapped_numeric_column')
        self.assertEqual(missing['column'],3);self.assertEqual(missing['metric_candidates'],['revenue_share'])
        self.assertTrue(any(x['reason']=='row_number_metric_id' for x in issues))
        schema['skipped_columns_json']=[{'column':3,'reason':'contains position text'}]
        self.assertTrue(any(x['reason']=='skipped_numeric_data_column' for x in mapping_issues(table,schema,rows)))
        del schema['skipped_columns_json']
        rows[0]['attributes']['unresolved_cells_json']=[{'column':3,'reason':'Column header is unreadable in this source'}]
        issues=mapping_issues(table,schema,rows)
        saved=next(x for x in issues if x['reason']=='unresolved_cell_semantics')
        self.assertEqual(saved['raw_value'],'40%');self.assertEqual(saved['severity'],'review')
        rows[0]['attributes']['metric']='revenue'
        schema['columns_json'][0]['metric']='amount'
        issues=mapping_issues(table,schema,rows)
        masked=next(x for x in issues if x['reason']=='generic_metric_masks_financial_meaning')
        self.assertEqual(masked['row_metric'],'revenue')

    def test_profile_name_and_ticker_can_be_grounded_on_different_pages(self):
        _,parsed=self.s._clean_source('p',self.did)
        parsed=copy.deepcopy(parsed)
        parsed['pages'][0]['text']='示例科技股份有限公司 2025 年度报告'
        parsed['pages'].append({'page':2,'text':'证券代码：600123','width':100,'height':100})
        self.s._persist_prepared('p',self.did,parsed)
        profile={'kind':'financial_report','publisher':None,'authors':[],'published_at':None,'evidence':[{'field':'kind','page':1,'quote':'2025 年度报告'}],
                 'entities':[{'name':'示例科技股份有限公司','kind':'company','identifiers':{'ticker':'600123'},'evidence':[{'page':1,'quote':'示例科技股份有限公司'},{'page':2,'quote':'证券代码：600123'}]}]}
        result=self.s.set_document_profile('p',self.did,profile)
        self.assertEqual(result['data']['profile']['entities'][0]['identifiers']['ticker'],'600123')
        profile['entities'][0]['identifiers']['exchange']='SSE'
        with self.assertRaises(ProfileEvidenceError) as raised:self.s.set_document_profile('p',self.did,profile)
        self.assertEqual(raised.exception.details['candidates']['identifiers'][0]['ticker'],'600123')

    def test_complex_financial_table_cannot_be_excluded_to_claim_completion(self):
        issues=mapping_issues({'index':1},{'statement':'nonfinancial'},[],'结构复杂，保留原文待核验')
        self.assertEqual(issues[0]['reason'],'financial_complexity_is_not_exclusion')

    def test_series_pairs_packed_and_fragmented_columns_without_rewriting_numbers(self):
        from service.cleaning_sdk import Cleaner
        from service.semantic import materialize
        c=Cleaner.__new__(Cleaner)
        c.source={'company':'Test'};c.results={}
        c.tables={0:{'index':0,'page':1,'rows':[['Item','2025','2024'],['Income\nExpense','','8\n9'],['','10',''],['','11','']],'cells':{}}}
        c.map_series(0,[{'column':2,'period':'2025-FY'},{'column':3,'period':'2024-FY'}],
                     [{'metric':'income','label':'Income'},{'metric':'expense','label':'Expense'}],data_rows=range(2,5),
                     statement='notes',scope='consolidated_IFRS',currency='CNY',unit='元')
        result=c.results[0];ext=[{'class':'table_schema','text':'[[T0]]','span':[0,6],'attributes':result['schema']}]
        ext.extend({'class':'financial_row','text':f'[[T0:R{r["row"]}]]','span':[0,9],'attributes':r['attributes']} for r in result['rows'])
        facts,issues=materialize(ext,[{'table':c.tables[0],'rows':[1,2,3,4]}],'d','fixture')
        self.assertEqual(issues,[])
        self.assertEqual({(f['metric'],f['period'],f['value']) for f in facts},{('income','2025-FY','10'),('expense','2025-FY','11'),('income','2024-FY','8'),('expense','2024-FY','9')})
        self.assertEqual(mapping_issues(c.tables[0],result['schema'],result['rows']),[])
        c.map_table(0,[],statement='notes',scope='consolidated_IFRS',currency='CNY',unit='元')
        self.assertIn('already mapped',c.results[0]['mapping_error'])

    def test_series_dash_slots_preserve_alignment_without_zero_or_shared_mutation(self):
        import json
        from service.cleaning_sdk import Cleaner
        c=Cleaner.__new__(Cleaner);c.source={'company':'Test'};c.results={}
        c.tables={0:{'index':0,'rows':[['Item','2025','2024'],['Income\nExpense','10\n20','–\n8']]},
                  1:{'index':1,'rows':[['Item','2025'],['Revenue','4']]}}
        skip={1:'year header'}
        c.map_series(0,[{'column':2,'period':'2025-FY'},{'column':3,'period':'2024-FY'}],
                     [{'metric':'income'},{'metric':'expense'}],data_rows=[2],skip_rows=skip,
                     statement='notes',scope='unspecified',currency='CNY',unit='元')
        columns=json.loads(c.results[0]['rows'][0]['attributes']['columns_json'])
        self.assertEqual([(v['metric'],v['numeric_span']['text']) for v in columns],[('income','10'),('expense','20'),('expense','8')])
        self.assertEqual(skip,{1:'year header'})
        c.map_series(0,[{'column':2}],[{'metric':'income'}],data_rows=[2],statement='notes',scope='unspecified',currency='CNY',unit='元')
        c.map_table(1,[{'column':2,'period':'2025-FY'}],skip_rows={1:'year header'},statement='notes',scope='unspecified',currency='CNY',unit='元')
        self.assertIn('mapping_error',c.results[0]);self.assertNotIn('mapping_error',c.results[1])

if __name__=='__main__':unittest.main()
