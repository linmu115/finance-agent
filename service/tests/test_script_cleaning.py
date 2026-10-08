import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from service.core import FinanceService
from service.store import dumps


class Runner:
    def __init__(self,root):self.root=root
    def availability(self):return {'available':True}
    def run(self,code,inputs,**kwargs):
        # No generated code executes on the host, including in tests.
        return {'run_id':kwargs['run_id'],'status':'succeeded','artifacts':[]}
    def artifact_path(self,run_id,name,project_id):return self.root/run_id/name

class ScriptCleaningTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);self.s=FinanceService(self.root)
        self.s.create_project('p','Test');self.s.create_project('q','Other')
        p=self.root/'uploads/test.csv';p.write_text('label,2025,2024\nRevenue,100,80\nCost,40,30',encoding='utf-8')
        self.did=self.s.register_document('p',str(p),'test.csv')['data']['document_id']
        parsed={'company':'Test','report_year':2025,'pages':[{'page':1,'text':'Consolidated income statement 2025 2024 RMB thousand','width':100,'height':100}],
                'tables':[{'index':0,'page':1,'rows':[['label','2025','2024'],['Revenue','100','80'],['Cost','40','30']],'cells':{}}], 'warnings':[]}
        self.s._persist_prepared('p',self.did,parsed)
        self.s.sandbox=Runner(self.root/'output');self.pid=self.s.begin_script_cleaning('p',[self.did],'owner','fixture')['data']['processing_id']
        self.schema={'company':'Test','scope':'consolidated_IFRS','statement':'income','currency':'CNY','unit':'千元',
            'columns_json':dumps([{'column':2,'period':'2025-H1','start':'2025-01-01','end':'2025-06-30'},{'column':3,'period':'2024-H1','start':'2024-01-01','end':'2024-06-30'}]),
            'skipped_rows_json':dumps([{'row':1,'reason':'year header'}])}
        self.payload={'tables':[{'index':0,'schema':self.schema,'rows':[{'row':2,'attributes':{'metric':'revenue','label':'Revenue','value':'999999'}},{'row':3,'attributes':{'metric':'cost','label':'Cost'}}]}]}
        self.review=[{'table_index':0,'verdict':'accepted','evidence':'Consolidated income statement','note':'Compared source rows and both half-year columns; CNY thousand.'}]
    def tearDown(self):
        for pool in ['pool','analysis_pool','embedding_pool','processing_pool']:getattr(self.s,pool).shutdown(wait=True)
        self.tmp.cleanup()
    def job(self,payload=None):
        rid=self.s.run_cleaning_script('p',self.pid,self.did,'# code stays in sandbox')['data']['run_id']
        self.s.analysis_futures[rid].result(10)
        folder=self.root/'output'/rid;folder.mkdir(parents=True);(folder/'cleaning_result.json').write_text(dumps(payload or self.payload),encoding='utf-8')
        return rid
    def test_direct_commit_keeps_grounded_values_idempotence_and_resume(self):
        rid=self.job()
        self.s.commit_cleaning_result('p',self.pid,rid)
        result=self.s.get_cleaning_result('p',self.pid,rid)['data'];self.assertEqual(result['issue_count'],0)
        self.assertEqual(result['fact_count'],4)
        done=self.s.commit_cleaning_result('p',self.pid,rid,self.review)['data'];self.assertEqual(done['state'],'completed')
        with self.s.store.connect() as db:before=[dict(r) for r in db.execute('select * from facts order by fact_id')]
        self.assertIn('100000',[r['value'] for r in before]);self.assertNotIn('999999',[r['value'] for r in before])
        self.s.commit_cleaning_result('p',self.pid,rid,self.review)
        with self.s.store.connect() as db:self.assertEqual(before,[dict(r) for r in db.execute('select * from facts order by fact_id')])
        resumed=self.s.begin_script_cleaning('p',[self.did],'new-owner','fixture')['data'];self.assertEqual(resumed['pending_tables'][self.did],[])
        checkpoint=self.s.get_processing_checkpoint('p',self.did)['data']['documents'][0]
        self.assertEqual(checkpoint['counts']['pending'],0)
        self.assertEqual(self.s.get_document('p',self.did)['data']['normalization_engine'],'PythonScript')
        self.assertEqual(self.s.get_document('p',self.did)['data']['legacy_fact_count'],0)
    def test_source_normalization_retains_original_id_and_lists_unrecognized_ids(self):
        payload=json.loads(dumps(self.payload))
        payload['tables'][0]['rows'][0]['attributes']['metric']='bespoke_turnover'
        rid=self.job(payload)
        self.s.commit_cleaning_result('p',self.pid,rid)
        with self.s.store.connect() as db:
            rows=[dict(r) for r in db.execute("SELECT * FROM facts WHERE metric='revenue'")]
        self.assertEqual(len(rows),2)
        self.assertTrue(all(json.loads(r['source_json'])['normalization']['metric_aliases']==['bespoke_turnover'] for r in rows))
        details=self.s.get_normalization_details('p',self.did)['data']
        self.assertIn('cost',{r['metric'] for r in details['metric_review']['items']})
        reviewed=self.s.get_normalization_details('p',self.did,review_only=True)['data']
        self.assertEqual(reviewed['metric_review']['total'],details['metric_review']['total'])

    def test_empty_optional_reviews_commit_selected_tables_without_claiming_review(self):
        rid=self.job()
        result=self.s.commit_cleaning_result('p',self.pid,rid,reviews=[],table_indices=[0])['data']
        self.assertEqual(result['state'],'completed')
        self.assertEqual(result['pending_script_tables'],[])
        with self.s.store.connect() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM facts').fetchone()[0],4)
            batch=json.loads(db.execute('SELECT result_json FROM normalization_batches').fetchone()[0])
        self.assertEqual(batch['semantic_review']['verdict'],'unreviewed')

    def test_pending_facts_keep_raw_values_notes_and_local_review_access(self):
        rid=self.job();self.s.get_cleaning_result('p',self.pid,rid)
        review=[dict(self.review[0],verdict='needs_review',note='需结合相邻页再次核对期间表头，候选原值保留。')]
        self.s.commit_cleaning_result('p',self.pid,rid,review)
        result=self.s.query_financial_data('p',{'quality':'needs_review'})['data']
        self.assertEqual(result['total'],4)
        self.assertEqual(self.s.query_financial_data('p')['data']['total'],4)
        self.assertEqual(self.s.query_financial_data('p',{'qualities':[]})['data']['total'],0)
        self.assertEqual(self.s.query_financial_data('q',{'quality':'needs_review'})['data']['total'],0)
        self.assertEqual({r['raw_value'] for r in result['items']},{'100','80','40','30'})
        self.assertTrue(all(r['source_ref']['normalization']['semantic_review_note']==review[0]['note'] for r in result['items']))
        details=self.s.get_normalization_details('p',self.did)['data']
        self.assertTrue(any(i['reason']=='semantic_review_pending' for batch in details['batches'] for i in batch['result']['issues']))

    def test_missing_financial_row_blocks_commit(self):
        self.payload['tables'][0]['rows'].pop();rid=self.job()
        self.assertGreater(self.s.get_cleaning_result('p',self.pid,rid)['data']['issue_count'],0)
        with self.assertRaisesRegex(ValueError,'validation_errors'):self.s.commit_cleaning_result('p',self.pid,rid,self.review)
        self.assertEqual(self.s.get_document('p',self.did)['data']['fact_count'],0)

    def test_filename_is_not_silently_accepted_as_issuer(self):
        self.payload['tables'][0]['schema']['company']='test'
        rid=self.job();result=self.s.get_cleaning_result('p',self.pid,rid)['data']
        self.assertTrue(any(i['reason']=='unresolved_company' for t in result['tables'] for i in t['issues']))
        with self.assertRaisesRegex(ValueError,'validation_errors'):
            self.s.commit_cleaning_result('p',self.pid,rid,self.review)

    def test_conflicting_details_require_dimensions(self):
        self.payload['tables'][0]['rows'][1]['attributes']['metric']='revenue'
        rid=self.job();result=self.s.get_cleaning_result('p',self.pid,rid)['data']
        self.assertTrue(any(i['reason']=='ambiguous_fact_dimensions' for t in result['tables'] for i in t['issues']))
        for row,purpose in zip(self.payload['tables'][0]['rows'],['borrowing_repayment','working_capital']):
            row['attributes']['dimensions_json']=dumps({'purpose':purpose})
        fixed=self.job();self.assertEqual(self.s.get_cleaning_result('p',self.pid,fixed)['data']['issue_count'],0)

    def test_packed_values_can_disable_invented_row_dimension(self):
        from service.semantic import materialize
        table={'index':0,'page':1,'rows':[['Revenue\nCost','100\n40']]}
        columns=[{'column':2,'metric':metric,'period':'2025-H1','numeric_span':{'text':text,'start':start,'end':start+len(text),'polarity':'as_written'}}
                 for metric,text,start in [('revenue','100',0),('cost','40',4)]]
        ext=[{'class':'table_schema','text':'[[T0]]','span':[0,6],'attributes':self.schema|{'columns_json':dumps(columns)}},
             {'class':'financial_row','text':'[[T0:R1]]','span':[0,9],'attributes':{'metric':'revenue','row_subject':False}}]
        facts,issues=materialize(ext,[{'table':table,'rows':[1]}],self.did,'fixture')
        self.assertEqual(issues,[]);self.assertEqual([f['value'] for f in facts],['100000','40000'])
        self.assertTrue(all(f['source']['normalization']['dimensions']=={} for f in facts))
        ext[1]['attributes'].pop('row_subject')
        facts,_=materialize(ext,[{'table':table,'rows':[1]}],self.did,'fixture')
        self.assertEqual(facts[1]['source']['normalization']['dimensions'],{'financial_item':'revenue'})

    def test_packed_segment_dimensions_alias_does_not_drop_values(self):
        from service.semantic import materialize
        table={'index':0,'page':1,'rows':[['Segments','100\n40']]}
        columns=[{'column':2,'metric':'revenue','period':'2025-H1','dimensions_json':{'segment':name},
                  'numeric_span':{'text':text,'start':start,'end':start+len(text),'polarity':'as_written'}}
                 for name,text,start in [('A','100',0),('B','40',4)]]
        ext=[{'class':'table_schema','text':'[[T0]]','span':[0,6],'attributes':self.schema|{'columns_json':dumps(columns)}},
             {'class':'financial_row','text':'[[T0:R1]]','span':[0,9],'attributes':{'metric':'revenue','row_subject':False}}]
        facts,issues=materialize(ext,[{'table':table,'rows':[1]}],self.did,'fixture')
        self.assertEqual(issues,[]);self.assertEqual([f['value'] for f in facts],['100000','40000'])
        self.assertEqual([f['source']['normalization']['dimensions'] for f in facts],[{'segment':'A'},{'segment':'B'}])
        columns[0]['dimensions']={'segment':'conflicting'}
        ext[0]['attributes']['columns_json']=dumps(columns)
        _,issues=materialize(ext,[{'table':table,'rows':[1]}],self.did,'fixture')
        self.assertTrue(any(i['reason']=='invalid_dimensions' for i in issues))
        for c in columns:c.pop('dimensions',None);c.pop('dimensions_json',None)
        ext[0]['attributes']['columns_json']=dumps(columns)
        _,issues=materialize(ext,[{'table':table,'rows':[1]}],self.did,'fixture')
        self.assertTrue(any(i['reason']=='ambiguous_fact_dimensions' for i in issues))

    def test_same_row_different_columns_require_distinct_dimensions(self):
        columns=json.loads(self.schema['columns_json'])
        columns[1].update(period=columns[0]['period'],start=columns[0]['start'],end=columns[0]['end'])
        self.schema['columns_json']=dumps(columns)
        rid=self.job();result=self.s.get_cleaning_result('p',self.pid,rid)['data']
        self.assertTrue(any(i['reason']=='ambiguous_fact_dimensions' for t in result['tables'] for i in t['issues']))
    def test_project_boundary_and_fabricated_evidence(self):
        rid=self.job()
        with self.assertRaises(ValueError):self.s.get_cleaning_result('q',self.pid,rid)
        self.s.get_cleaning_result('p',self.pid,rid);self.review[0]['evidence']='made up source'
        with self.assertRaisesRegex(ValueError,'review_evidence'):self.s.commit_cleaning_result('p',self.pid,rid,self.review)
    def test_cancelled_attempt_cannot_commit(self):
        rid=self.job();self.s.get_cleaning_result('p',self.pid,rid);self.s.cancel_processing('p',self.pid)
        with self.assertRaisesRegex(ValueError,'stopped'):self.s.commit_cleaning_result('p',self.pid,rid,self.review)
    def test_changed_source_invalidates_result(self):
        rid=self.job();self.s.get_cleaning_result('p',self.pid,rid)
        doc=self.s.store.document('p',self.did);(self.root/doc['relative_path']).write_text('changed')
        with self.assertRaisesRegex(ValueError,'source_hash_changed'):self.s.commit_cleaning_result('p',self.pid,rid,self.review)

    def test_pending_review_survives_reuse(self):
        rid=self.job();self.s.get_cleaning_result('p',self.pid,rid,review_effort='high')
        self.review[0]['verdict']='needs_review'
        self.s.commit_cleaning_result('p',self.pid,rid,self.review)
        resumed=self.s.begin_script_cleaning('p',[self.did],'new-owner','fixture')['data']
        self.assertEqual(resumed['state'],'needs_review');self.assertTrue(resumed['review_issues'])

    def test_partial_repair_reports_remaining_candidate_tables(self):
        import copy
        doc,parsed=self.s._clean_source('p',self.did)
        parsed=copy.deepcopy(parsed);parsed['tables'].append(copy.deepcopy(parsed['tables'][0]));parsed['tables'][1]['index']=1
        self.s._persist_prepared('p',self.did,parsed)
        self.pid=self.s.begin_script_cleaning('p',[self.did],'second-owner','fixture',force=True)['data']['processing_id']
        payload=copy.deepcopy(self.payload);payload['tables'].append(copy.deepcopy(payload['tables'][0]));payload['tables'][1]['index']=1
        reviews=self.review+[self.review[0]|{'table_index':1}]
        first=self.job(payload);self.s.get_cleaning_result('p',self.pid,first)
        self.assertEqual(self.s.commit_cleaning_result('p',self.pid,first,reviews)['data']['pending_script_tables'],[])
        repair=self.job(payload);self.s.get_cleaning_result('p',self.pid,repair)
        partial=self.s.commit_cleaning_result('p',self.pid,repair,self.review)['data']
        self.assertEqual(partial['state'],'completed') # Previously stored document remains complete.
        self.assertEqual(partial['pending_script_tables'],[1]) # This repair still has work.

    def test_cents_per_share_are_not_yuan_or_thousands(self):
        from service.normalization import unit_info
        from decimal import Decimal
        for unit in ['分/股','RMB cents/share','HKD cents/share']:
            _,factor,currency=unit_info(unit)
            self.assertEqual(factor,Decimal('0.01'))
            self.assertEqual(currency,'HKD/share' if unit.startswith('HKD') else 'CNY/share')

    def test_quoted_thousands_are_scaled_once_when_committed(self):
        table=self.payload['tables'][0]
        table['schema']['unit']='RMB’000'
        table['schema']['currency']='RMB'
        columns=json.loads(table['schema']['columns_json'])
        for column in columns:
            column.update(unit='RMB’000',currency='RMB')
        table['schema']['columns_json']=dumps(columns)
        rid=self.job()
        self.s.commit_cleaning_result('p',self.pid,rid)
        rows=self.s.query_financial_data('p',{'metric':'revenue'})['data']['items']
        self.assertEqual({str(row['value']) for row in rows},{'100000','80000'})
        self.assertTrue(all(row['currency']=='CNY' for row in rows))
        self.assertTrue(all(row['source_ref']['normalization']['scale']=='1000' for row in rows))

    def test_merged_column_never_concatenates_amounts_and_spans_are_grounded(self):
        from service.normalization import decimal_value,numeric_candidate
        from service.semantic import _source_number
        from decimal import Decimal
        raw='68,491\n46,968\n3,832\n61,720\n181,011'
        self.assertIsNone(decimal_value(raw));self.assertTrue(numeric_candidate('1\n2'))
        for token in raw.splitlines():
            start=raw.index(token)
            number,span,error=_source_number(raw,{'numeric_span':{'text':token,'start':start,'end':start+len(token),'polarity':'as_written'}})
            self.assertEqual(number,Decimal(token.replace(',','')));self.assertIsNone(error)
        self.assertIsNotNone(_source_number('12,345',{'numeric_span':{'text':'12','start':0,'end':2,'polarity':'as_written'}})[2])

    def test_stale_script_cannot_overwrite_another_commit(self):
        first=self.job();second=self.job()
        self.s.get_cleaning_result('p',self.pid,first);self.s.get_cleaning_result('p',self.pid,second)
        self.s.commit_cleaning_result('p',self.pid,first,self.review)
        with self.assertRaisesRegex(ValueError,'target_changed'):
            self.s.commit_cleaning_result('p',self.pid,second,self.review)

    def test_result_read_does_not_certify_model_review(self):
        first=self.job();self.s.get_cleaning_result('p',self.pid,first,review_effort='high')
        second=self.job()
        done=self.s.commit_cleaning_result('p',self.pid,second,self.review)['data']
        self.assertEqual(done['state'],'completed')
        with self.s.store.connect() as db:
            detail=json.loads(db.execute('select result_json from normalization_batches').fetchone()[0])
        self.assertIsNone(detail['inference_policy']['review'])
        self.assertNotIn('inspected_mappings',self.s._clean_state('p',self.pid))

    def test_changed_mapping_commits_without_ceremonial_readback(self):
        _,parsed=self.s._clean_source('p',self.did)
        parsed['tables'][0]['rows'][1][0]='Special contract receipts'
        self.s._persist_prepared('p',self.did,parsed)
        first=self.job();self.s.get_cleaning_result('p',self.pid,first)
        self.payload['tables'][0]['rows'][0]['attributes']['metric']='different_revenue'
        second=self.job()
        self.s.commit_cleaning_result('p',self.pid,second)
        items=self.s.query_financial_data('p',{'metric':'different_revenue'})['data']['items']
        self.assertEqual(len(items),2)
        self.assertTrue(all(row['quality']=='script_normalized' for row in items))

    def test_conflicting_skip_and_mapping_cannot_silently_lose_comparatives(self):
        from service.cleaning_sdk import Cleaner
        cleaner=Cleaner.__new__(Cleaner)
        cleaner.source={'company':'Test'};cleaner.tables={0:{'rows':[['Revenue','100','80']]}};cleaner.results={}
        cleaner.map_table(0,[{'column':2,'period':'2025-H1'}],statement='income',scope='consolidated_IFRS',currency='CNY',unit='千元',skip_rows={1:'header'},row_overrides={1:{'metric':'revenue'}})
        self.assertIn('both skip_rows and row_overrides',cleaner.results[0]['mapping_error'])

    def test_per_share_metric_cannot_inherit_table_money_unit(self):
        _,parsed=self.s._clean_source('p',self.did)
        parsed['tables'][0]['rows'][1][0]='Basic earnings per share'
        self.s._persist_prepared('p',self.did,parsed)
        self.payload['tables'][0]['rows'][0]['attributes']['metric']='basic_earnings_per_share'
        rid=self.job();result=self.s.get_cleaning_result('p',self.pid,rid)['data']
        self.assertTrue(any(i['reason']=='metric_unit_mismatch' for t in result['tables'] for i in t['issues']))
        with self.assertRaisesRegex(ValueError,'validation_errors'):
            self.s.commit_cleaning_result('p',self.pid,rid,self.review)

    def test_review_selects_source_table_id_independently_of_page_offset(self):
        rid=self.job()
        result=self.s.get_cleaning_result('p',self.pid,rid,offset=99,table_indices=[0])['data']
        self.assertEqual([t['index'] for t in result['tables']],[0])
        self.assertEqual(result['table_order'],[0]);self.assertIsNone(result['next_offset'])
        with self.assertRaisesRegex(ValueError,'not_in_script_result'):
            self.s.get_cleaning_result('p',self.pid,rid,table_indices=[99])

    def test_parallel_script_submissions_keep_every_job(self):
        from concurrent.futures import ThreadPoolExecutor
        gate=__import__('threading').Barrier(3)
        def availability():gate.wait(timeout=10);return {'available':True}
        with patch.object(self.s.sandbox,'availability',side_effect=availability),ThreadPoolExecutor(max_workers=3) as pool:
            jobs=list(pool.map(lambda _:self.s.run_cleaning_script('p',self.pid,self.did,'# isolated'),range(3)))
        saved=self.s._clean_state('p',self.pid)
        self.assertEqual({r['data']['run_id'] for r in jobs},set(saved['jobs']))

if __name__=='__main__':unittest.main()
