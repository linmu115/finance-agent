"""Invented fixtures test attribution/version boundaries, never financial advice."""
import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from service.core import FinanceService
from service.store import dumps
from service.tests.test_script_cleaning import Runner


class ResearchIngestionTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        self.s=FinanceService(self.root);self.s.create_project('p','Research fixture');self.s.create_project('q','Other')
        self.s.sandbox=Runner(self.root/'output')
        self.did=self.document('First','2025-03-01')
        self.profile=self.profile_input('2025-03-01')
        self.set_profile(self.did,self.profile)
        self.pid=self.s.begin_script_cleaning('p',[self.did],'owner','fixture')['data']['processing_id']
        self.payload={'tables':[{'index':0,'schema':{'company':'Alpha','statement':'income','scope':'unspecified','currency':'CNY','unit':'百万元',
            'columns_json':dumps([{'column':2,'period':'2024-FY','data_kind':'quoted_actual'},{'column':3,'period':'2025-FY','data_kind':'analyst_forecast'}]),
            'skipped_rows_json':dumps([{'row':1,'reason':'header'}])},
            'rows':[{'row':2,'attributes':{'metric':'revenue','label':'营业收入'}},{'row':3,'attributes':{'metric':'net_profit','label':'净利润'}}]}]}
        self.review=[{'table_index':0,'verdict':'accepted','evidence':'2024A 2025E','note':'Actual / estimate columns, CNY million, same company.'}]
    def tearDown(self):
        for name in ['pool','analysis_pool','embedding_pool','processing_pool']:getattr(self.s,name).shutdown(wait=True)
        self.tmp.cleanup()
    def document(self,name,day,publisher='Broker A',project='p'):
        path=self.root/'uploads'/(name+'.csv');path.write_text(name+'\nitem,2024A,2025E\nRevenue,100,120\nProfit,10,13',encoding='utf-8')
        did=self.s.register_document(project,str(path),name+'.csv')['data']['document_id']
        parsed={'company':name,'report_year':2025,'pages':[
            {'page':1,'text':f'Company Research. {publisher}. Analyst Alice. Published {day}. Alpha company. Beta company. Dairy industry. 2024A 2025E. A actual, E estimates. Revenue 100 120. Profit 10 13.','width':100,'height':100},
            {'page':2,'text':'Alpha margins should recover. Management of Alpha says demand is improving. Beta competition is a risk.','width':100,'height':100}],
            'tables':[{'index':0,'page':1,'rows':[['item','2024A','2025E'],['Revenue','100','120'],['Profit','10','13']],'cells':{}}],'warnings':[]}
        self.s._persist_prepared(project,did,parsed)
        return did
    def profile_input(self,day,publisher='Broker A'):
        return {'kind':'broker_research','publisher':publisher,'authors':['Alice'],'published_at':day,
            'entities':[{'name':'Alpha','kind':'company','evidence':{'page':1,'quote':'Alpha company'}},
                        {'name':'Beta','kind':'company','evidence':{'page':1,'quote':'Beta company'}}],
            'evidence':[{'field':'kind','page':1,'quote':'Company Research'},
                        {'field':'publisher','page':1,'quote':publisher},{'field':'authors','page':1,'quote':'Analyst Alice'},
                        {'field':'published_at','page':1,'quote':'Published '+day}]}
    def set_profile(self,did,profile):return self.s.set_document_profile('p',did,profile)['data']
    def job(self,pid=None,did=None,payload=None):
        pid=pid or self.pid;did=did or self.did
        rid=self.s.run_cleaning_script('p',pid,did,'# never executed on host')['data']['run_id']
        self.s.analysis_futures[rid].result(10)
        folder=self.root/'output'/rid;folder.mkdir(parents=True)
        (folder/'cleaning_result.json').write_text(dumps(payload or self.payload),encoding='utf-8')
        return rid
    def commit(self,pid=None,did=None,payload=None):
        pid=pid or self.pid;rid=self.job(pid,did,payload)
        check=self.s.get_cleaning_result('p',pid,rid)['data']
        self.assertEqual(check['issue_count'],0,check)
        self.s.commit_cleaning_result('p',pid,rid,self.review)
        return rid
    def finish_text(self,text='Margins recover'):
        return self.s.save_research_claims('p',self.pid,self.did,[
            {'page':1,'empty_reason':'Metadata and numeric table; no additional viewpoint.','claims':[]},
            {'page':2,'verdict':'accepted','note':'Reviewed author judgement and attributed quote.','claims':[
                {'kind':'opinion','text':text,'quote':'Alpha margins should recover.','entity':{'name':'Alpha'},'attribution':{'kind':'author'}},
                {'kind':'company_guidance','text':'Management expects better demand','quote':'Management of Alpha says demand is improving.',
                 'entity':{'name':'Alpha'},'attribution':{'kind':'quoted','speaker':'Management of Alpha'}}]}])

    def test_routing_does_not_write_financial_facts(self):
        did=self.document('Unclassified','2025-03-02')
        got=self.s.begin_script_cleaning('p',[did],'route','fixture',require_profile=True)['data']
        self.assertEqual(got['state'],'routing_required')
        self.assertEqual(self.s.query_financial_data('p')['data']['total'],0)
        self.assertEqual(got['routing']['documents'][0]['pages'],2)

    def test_partial_claim_batch_saves_valid_records_and_retains_failed_candidates(self):
        pages=[{'page':2,'claims':[
            {'kind':'opinion','text':'利润率有望修复','quote':'Alpha margins should recover.','entity':'Alpha'},
            {'kind':'risk','text':'竞争风险','quote':'Beta competition is a risk.','entity':'Beta'},
            {'kind':'opinion','text':'无证据的说法','quote':'Invented quotation','entity':'Alpha'}]}]
        result=self.s.save_research_claims('p',self.pid,self.did,pages)['data']
        self.assertEqual(result['pages'][0]['content_state'],'partial')
        self.assertEqual(len(result['pages'][0]['candidate_claims']),1)
        claims=self.s.query_research_records('p')['data']['items']
        self.assertEqual(len(claims),2)
        empty=self.s.save_research_claims('p',self.pid,self.did,[{'page':2,'claims':[]}])['data']
        self.assertEqual(empty['pages'][0]['content_state'],'unresolved')
        self.assertEqual(len(self.s.query_research_records('p')['data']['items']),2)
        status=self.s.get_research_ingestion_status('p',self.did)['data']
        self.assertIn(2,status['text_coverage']['pending_pages'])

    def test_force_rechecks_pages_without_erasing_records(self):
        self.commit();self.finish_text()
        fresh=self.s.begin_script_cleaning('p',[self.did],'forced','fixture',force=True)['data']
        self.assertEqual(fresh['pending_pages'][self.did],[1,2])
        self.assertEqual(self.s.query_research_records('p')['data']['total'],6)
        self.s.save_research_claims('p',fresh['processing_id'],self.did,[{'page':1,'empty_reason':'Metadata and numeric table only','claims':[]}])
        status=self.s._clean_state('p',fresh['processing_id'])
        self.assertEqual(status['documents'][0]['text_coverage']['pending_pages'],[2])

    def test_repair_refreshes_only_its_own_completed_attachment_snapshot(self):
        self.commit();self.finish_text()
        old_id=self.pid
        reused=self.s.begin_script_cleaning('p',[self.did],'repeat-owner','fixture')['data']['processing_id']
        self.assertEqual(reused,old_id)
        # A new historical snapshot belongs to an explicit rewash. Ordinary
        # repeated requests now reuse the original processing attempt.
        self.pid=self.s.begin_script_cleaning('p',[self.did],'repair-owner','fixture',force=True)['data']['processing_id']
        self.assertNotEqual(self.pid,old_id)
        self.commit()
        self.finish_text('Updated interpretation, same exact source')
        with self.s.store.connect() as db:
            snapshots={r['flow_id']:json.loads(r['snapshot_json']) for r in db.execute('SELECT * FROM attachment_flows')}
        texts=lambda pid:[r.get('text') for r in snapshots[pid+':'+self.did]['research_records'] if r['record_type']=='claim']
        self.assertIn('Margins recover',texts(old_id))
        self.assertIn('Updated interpretation, same exact source',texts(self.pid))
        changed=copy.deepcopy(self.payload);changed['tables'][0]['rows'][0]['attributes']['metric']='operating_revenue'
        self.commit(payload=changed)
        with self.s.store.connect() as db:
            fresh=json.loads(db.execute('SELECT snapshot_json FROM attachment_flows WHERE flow_id=?',(self.pid+':'+self.did,)).fetchone()[0])
        self.assertIn('operating_revenue',{r.get('metric') for r in fresh['research_records']})

    def test_unresolved_research_semantics_preserve_raw_numbers_with_warning(self):
        payload=copy.deepcopy(self.payload)
        payload['tables'][0]['rows'][0]['attributes'].update(metric='installed_capacity',unit='GWh')
        cols=json.loads(payload['tables'][0]['schema']['columns_json']);cols[1].update(period='unknown',period_label='远期',data_kind='unclassified')
        payload['tables'][0]['schema']['columns_json']=dumps(cols)
        rid=self.job(payload=payload);check=self.s.get_cleaning_result('p',self.pid,rid)['data']
        self.assertGreater(check['issue_count'],0)
        self.assertTrue(all(i.get('severity')=='review' for i in check['tables'][0]['issues']))
        self.s.commit_cleaning_result('p',self.pid,rid,self.review)
        rows=self.s.query_research_records('p',{'metric':'installed_capacity'})['data']['items']
        self.assertEqual({r['value'] for r in rows},{'100','120'})
        self.assertTrue(all(r['quality']=='needs_review' and r['raw_unit']=='GWh' for r in rows))
        self.assertEqual(next(r for r in rows if r['data_kind']=='unclassified')['period'],'unknown')

    def test_ungrounded_entity_identifier_cannot_merge_companies(self):
        payload=copy.deepcopy(self.payload)
        payload['tables'][0]['rows'][0]['attributes'].update(company='Dairy',entity_kind='industry',entity_identifiers={'exchange':'FAKE','ticker':'123'})
        rid=self.job(payload=payload);result=self.s.get_cleaning_result('p',self.pid,rid)['data']
        self.assertTrue(any(i['reason']=='entity_identifier_requires_grounded_profile' for i in result['tables'][0]['issues']))

    def test_reclassifying_document_hides_previous_disclosures_without_erasing(self):
        profile=copy.deepcopy(self.profile);profile['kind']='financial_report';self.set_profile(self.did,profile)
        pid=self.s.begin_script_cleaning('p',[self.did],'financial','fixture')['data']['processing_id']
        payload=copy.deepcopy(self.payload);cols=json.loads(payload['tables'][0]['schema']['columns_json'])
        for col in cols:col['data_kind']='disclosed_actual'
        payload['tables'][0]['schema']['columns_json']=dumps(cols);self.commit(pid,payload=payload)
        self.assertEqual(self.s.query_financial_data('p')['data']['total'],4)
        self.set_profile(self.did,self.profile)
        self.assertEqual(self.s.query_financial_data('p')['data']['total'],0)
        self.assertFalse(self.s.get_financial_metrics('p',['revenue'])['data']['items'])
        self.assertEqual(self.s.get_data_catalog('p')['data']['counts']['facts'],0)
        with self.s.store.connect() as db:self.assertEqual(db.execute('SELECT count(*) FROM facts').fetchone()[0],4)

    def test_report_valuation_inconsistency_is_flagged_without_rewriting(self):
        from service.research_checks import valuation_warnings
        def fact(metric,value,period,currency,column,kind):
            return {'company':'Alpha','scope':'unspecified','metric':metric,'value':value,'raw_unit':'元/股' if currency.endswith('/share') else '倍','period':period,'currency':currency,
                    'source':{'table_id':'d:t0','row':2,'column':column,'cell':chr(64+column)+'2','normalization':{'data_kind':kind}}}
        facts=[fact('close_price','129.4','2025-07-22','CNY/share',2,'quoted_actual'),fact('eps_forecast','6.40','2025-FY','CNY/share',3,'analyst_forecast'),fact('pe_forecast','45.9','2025-FY','倍',4,'analyst_forecast')]
        result=valuation_warnings(facts)
        self.assertEqual(result[0]['reason'],'price_eps_pe_requires_reconciliation')
        self.assertEqual([r['value'] for r in facts],['129.4','6.40','45.9'])
        facts[-1]['value']='20.2';self.assertEqual(valuation_warnings(facts),[])

    def test_research_unknown_currency_is_not_overridden_by_yuan_unit(self):
        payload=copy.deepcopy(self.payload);payload['tables'][0]['schema']['currency']='unknown'
        rid=self.job(payload=payload);check=self.s.get_cleaning_result('p',self.pid,rid,details=True)['data']
        self.assertTrue(all(f['currency']=='unknown' for f in check['tables'][0]['sample_facts']))
        self.assertTrue(any(i['reason']=='unresolved_currency' for i in check['tables'][0]['issues']))
        self.s.commit_cleaning_result('p',self.pid,rid,self.review)
        self.assertTrue(all(r['quality']=='needs_review' for r in self.s.query_research_records('p')['data']['items']))
        pending=self.s.query_research_records('p',{'quality':'needs_review'})['data']
        self.assertEqual(pending['total'],4)
        self.assertTrue(all(r['currency']=='unknown' and r['raw_value'] for r in pending['items']))
        self.assertEqual(self.s.query_research_records('p',{'quality':[]})['data']['total'],0)
        self.assertEqual(self.s.query_research_records('q',{'quality':'needs_review'})['data']['total'],0)
    def test_mixed_table_once_separate_records_and_text_completion(self):
        rid=self.commit()
        self.assertEqual(self.s.query_financial_data('p')['data']['total'],0)
        found=self.s.query_research_records('p')['data']
        self.assertEqual(found['total'],4)
        self.assertEqual({i['data_kind'] for i in found['items']},{'quoted_actual','analyst_forecast'})
        forecast=self.s.query_research_records('p',{'data_kind':'analyst_forecast','metric':'revenue'})['data']['items'][0]
        self.assertEqual(forecast['value'],'120000000');self.assertEqual(forecast['publisher'],'Broker A')
        self.assertEqual(forecast['source_ref']['column'],3)
        status=self.s._clean_state('p',self.pid)
        self.assertEqual(status['state'],'normalizing');self.assertEqual(status['coverage']['tables_completed'],1)
        self.assertEqual(self.finish_text()['data']['state'],'completed')
        again=self.s.begin_script_cleaning('p',[self.did],'resume','fixture')['data']
        self.assertEqual(again['state'],'completed');self.assertEqual(again['pending_tables'][self.did],[])
        self.assertEqual(again['pending_pages'][self.did],[])
        self.s.commit_cleaning_result('p',self.pid,rid,self.review)
        self.assertEqual(self.s.query_research_records('p')['data']['total'],6)
    def test_forecast_cannot_pollute_disclosures_or_omit_type(self):
        for kind in ['disclosed_actual',None]:
            payload=copy.deepcopy(self.payload)
            cols=json.loads(payload['tables'][0]['schema']['columns_json'])
            cols[1]['data_kind']=kind;payload['tables'][0]['schema']['columns_json']=dumps(cols)
            rid=self.job(payload=payload);result=self.s.get_cleaning_result('p',self.pid,rid)['data']
            self.assertGreater(result['issue_count'],0)
            with self.assertRaisesRegex(ValueError,'script_validation_errors'):self.s.commit_cleaning_result('p',self.pid,rid,self.review)
        self.assertEqual(self.s.query_financial_data('p')['data']['total'],0)
    def test_multicompany_rows_keep_entities(self):
        self.payload['tables'][0]['rows'][1]['attributes'].update(company='Beta',metric='revenue')
        self.commit()
        self.assertEqual(self.s.query_research_records('p',{'entity':'Alpha'})['data']['total'],2)
        beta=self.s.query_research_records('p',{'entity':'Beta','data_kind':'analyst_forecast'})['data']['items'][0]
        self.assertEqual(beta['value'],'13000000')
        result=self.s.search_evidence('p','revenue',company='Beta',filters={'data_kind':'analyst_forecast'})
        self.assertTrue(result['data']['items'])
    def test_grounded_metadata_unknown_fields_and_project_boundary(self):
        for key,value in [('publisher','Fake Broker'),('authors',['Fake Analyst']),('published_at','2025-04-01')]:
            bad=copy.deepcopy(self.profile);bad[key]=value
            with self.assertRaises(ValueError):self.set_profile(self.did,bad)
        before=self.s._document_profile('p',self.did)['revision_id']
        self.assertTrue(self.set_profile(self.did,self.profile)['reused'])
        self.assertEqual(before,self.s._document_profile('p',self.did)['revision_id'])
        with self.assertRaises(ValueError):self.s.set_document_profile('q',self.did,self.profile)
        self.assertEqual(self.s.query_research_records('q')['data']['total'],0)
    def test_claim_idempotence_revision_and_literal_quote_gate(self):
        self.finish_text();before=self.s.query_research_records('p')['data']['items']
        self.finish_text();self.assertEqual({r['record_id'] for r in before},{r['record_id'] for r in self.s.query_research_records('p')['data']['items']})
        self.finish_text('Reworded same original judgement')
        self.assertEqual(self.s.query_research_records('p')['data']['total'],2)
        self.assertEqual(self.s.query_research_records('p',{'include_history':True})['data']['total'],3)
        failed=self.s.save_research_claims('p',self.pid,self.did,[{'page':2,'claims':[{'kind':'opinion','text':'x','quote':'fabricated quote','entity':'Alpha'}]}])['data']
        self.assertEqual(failed['pages'][0]['content_state'],'failed')
        self.assertIn('quote_not_in_source',failed['pages'][0]['candidate_claims'][0]['error'])
        self.assertIn(2,failed['pending_pages'][self.did])
        self.assertEqual(self.s.query_research_records('p')['data']['total'],2)

    def test_pdf_whitespace_quote_is_saved_as_exact_source_span(self):
        from service.research_ingestion import grounded_quote
        parsed={'pages':[{'page':3,'text':'Evidence: Alpha\n margins  should recover. Other text.'}]}
        ref=grounded_quote(parsed,{'page':3,'quote':'Alpha margins should recover.'})
        self.assertEqual(ref['quote'],parsed['pages'][0]['text'][ref['start']:ref['end']])
        self.assertIn('\n',ref['quote']);self.assertNotEqual(ref['quote'],'Alpha margins should recover.')
        with self.assertRaisesRegex(ValueError,'page_3_read_get_source_page'):
            grounded_quote(parsed,{'page':3,'quote':'Alpha margins will recover.'})
    def test_asof_latest_and_different_institutions(self):
        self.commit()
        for name,day,publisher in [('Later','2025-06-01','Broker A'),('Other','2025-05-01','Broker B')]:
            did=self.document(name,day,publisher);self.set_profile(did,self.profile_input(day,publisher))
            pid=self.s.begin_script_cleaning('p',[did],name,'fixture')['data']['processing_id'];self.commit(pid,did)
        f={'data_kind':'analyst_forecast','metric':'revenue','entity':'Alpha'}
        self.assertEqual(self.s.query_research_records('p',f)['data']['total'],3)
        past=self.s.query_research_records('p',f|{'as_of':'2025-04-01','latest_per_series':True})['data']['items']
        self.assertEqual(len(past),1);self.assertEqual(past[0]['published_at'],'2025-03-01')
        latest=self.s.query_research_records('p',f|{'latest_per_series':True})['data']['items']
        self.assertEqual({(r['publisher'],r['published_at']) for r in latest},{('Broker A','2025-06-01'),('Broker B','2025-05-01')})
        undated=self.document('Undated','2025-07-01');p=self.profile_input('2025-07-01');p['published_at']=None;self.set_profile(undated,p)
        pid=self.s.begin_script_cleaning('p',[undated],'undated','fixture')['data']['processing_id'];self.commit(pid,undated)
        self.assertEqual(self.s.query_research_records('p',f|{'as_of':'2025-12-31'})['data']['total'],3)

    def test_latest_ignores_table_decoration_but_preserves_business_dimensions(self):
        decorated=copy.deepcopy(self.payload)
        decorated['tables'][0]['rows'][0]['attributes']['dimensions_json']=dumps({'rating':'Buy','report_table':'Forecasts','ticker':'123','financial_item':'Alpha','region':'China','product':'milk'})
        self.commit(payload=decorated)
        for name,day,region in [('SameSeries','2025-06-01','China'),('OtherRegion','2025-07-01','Europe')]:
            did=self.document(name,day);self.set_profile(did,self.profile_input(day))
            pid=self.s.begin_script_cleaning('p',[did],name,'fixture')['data']['processing_id']
            updated=copy.deepcopy(self.payload)
            updated['tables'][0]['rows'][0]['attributes']['dimensions_json']=dumps({'product':'milk','region':region,'financial_item':'company_forecast_summary','exchange':'SH'})
            self.commit(pid,did,updated)
        rows=self.s.query_research_records('p',{'metric':'revenue','data_kind':'analyst_forecast','latest_per_series':True})['data']['items']
        self.assertEqual({(r['dimensions']['region'],r['published_at']) for r in rows},{('China','2025-06-01'),('Europe','2025-07-01')})
    def test_profile_change_invalidates_stale_result_and_retrieval(self):
        self.commit();rid=self.job();self.s.get_cleaning_result('p',self.pid,rid)
        profile=copy.deepcopy(self.profile);profile['authors']=[];self.set_profile(self.did,profile)
        with self.assertRaisesRegex(ValueError,'profile_changed'):self.s.commit_cleaning_result('p',self.pid,rid,self.review)
        self.assertEqual(self.s.query_research_records('p')['data']['total'],0)
        self.assertEqual(self.s.query_research_records('p',{'include_history':True})['data']['total'],4)
        self.assertFalse(self.s.search_evidence('p','Revenue',filters={'data_kind':'analyst_forecast'})['data']['items'])
    def test_hybrid_respects_publication_and_project_filters(self):
        self.commit();other=self.document('After','2025-07-01');self.set_profile(other,self.profile_input('2025-07-01'))
        self.document('Private','2025-01-01',project='q')
        cfg={'enabled':True,'base_url':'https://example.invalid','model':'fixture'};self.s.configs['p']={'embedding':cfg}
        with self.s.store.connect(write=True) as db:
            for row in db.execute("SELECT text FROM chunks WHERE project_id='p'").fetchall():
                db.execute('INSERT OR IGNORE INTO embedding_cache VALUES(?,?,?,?,?,?)',(self.s._embedding_key('p',row[0],cfg),'p','fixture',2,'[1,0]','test'))
        with patch.object(self.s,'_schedule_embedding_index'),patch.object(self.s,'_embeddings',return_value=[[1,0]]):
            found=self.s.search_evidence('p','Revenue',filters={'as_of':'2025-04-01'})['data']
        self.assertEqual(found['retrieval'],'hybrid_rrf')
        self.assertTrue(all(i['source_ref']['document_id']==self.did for i in found['items']))
    def test_pagination_and_attachment_snapshot_destinations(self):
        self.commit();self.finish_text()
        got=self.s.query_research_records('p',limit=2)['data'];self.assertEqual(got['next_offset'],2)
        self.assertEqual(len(self.s.query_research_records('p',offset=got['next_offset'],limit=2)['data']['items']),2)
        from service.attachment_flows import read
        flow=read(self.s.store,'p',['owner'])['flows'][0]
        detail=read(self.s.store,'p',['owner'],flow['flow_id'])
        self.assertEqual(detail['destinations']['facts'],0)
        self.assertEqual(detail['destinations']['research_observations'],4)
        self.assertEqual(detail['destinations']['research_claims'],2)
        self.assertEqual(detail['research_total'],6)

    def test_query_matches_independent_terms_and_preserves_scope_and_pagination(self):
        self.commit()
        found=self.s.query_research_records('p',{'document_id':self.did,'query':'revenue net_profit'},limit=2)['data']
        self.assertEqual(found['total'],4)
        self.assertEqual(found['next_offset'],2)
        self.assertEqual(found['query_match'],'any_term')
        rest=self.s.query_research_records('p',{'document_id':self.did,'query':'revenue net_profit'},offset=2,limit=2)['data']
        self.assertEqual(len({x['record_id'] for x in found['items']+rest['items']}),4)
        self.assertEqual(self.s.query_research_records('q',{'query':'revenue net_profit'})['data']['total'],0)
        self.assertEqual(self.s.query_research_records('p',{'query':'%'})['data']['total'],0)

    def test_financial_acronym_matches_stored_metric_without_new_ingestion(self):
        payload=copy.deepcopy(self.payload)
        payload['tables'][0]['rows'][0]['attributes']['metric']='free_cash_flow_firm'
        self.commit(payload=payload)
        got=self.s.query_research_records('p',{'query':'FCFF','record_type':'observation'})['data']
        self.assertEqual(got['total'],2)
        self.assertEqual({r['metric'] for r in got['items']},{'free_cash_flow_firm'})
        self.assertIn('free_cash_flow_firm',got['query_terms'])
        self.assertEqual(self.s.query_research_records('p',{'query':'企业自由现金流'})['data']['total'],2)
    def test_stale_concurrent_numeric_commit_rejected(self):
        first=self.job();second=self.job()
        self.s.get_cleaning_result('p',self.pid,first);self.s.get_cleaning_result('p',self.pid,second)
        self.s.commit_cleaning_result('p',self.pid,first,self.review)
        with self.assertRaisesRegex(ValueError,'target_changed'):self.s.commit_cleaning_result('p',self.pid,second,self.review)
    def test_unreadable_chart_is_finished_but_needs_review(self):
        self.commit()
        result=self.s.save_research_claims('p',self.pid,self.did,[{'page':1,'claims':[],'empty_reason':'Only table'}, {'page':2,'claims':[],'verdict':'needs_review','note':'Unresolved chart readings'}])
        self.assertEqual(result['data']['state'],'needs_review')
        self.assertEqual(result['data']['pending_pages'][self.did],[])

    def test_reparse_preserves_identical_index_and_invalidates_changed_coordinates(self):
        self.commit();self.finish_text()
        doc=self.s.store.document('p',self.did);parsed=self.s._read_prepared('p',doc)
        self.s._persist_prepared('p',self.did,parsed)
        self.assertTrue(self.s.search_evidence('p','Revenue',filters={'data_kind':'analyst_forecast'})['data']['items'])
        changed=copy.deepcopy(parsed);changed['tables'][0]['rows'][1][1]='101'
        self.s._persist_prepared('p',self.did,changed)
        self.assertEqual(self.s.query_research_records('p')['data']['total'],0)
        self.assertEqual(self.s.query_research_records('p',{'include_history':True})['data']['total'],6)
        self.assertIsNone(self.s._document_profile('p',self.did))
        self.assertEqual(self.s.begin_script_cleaning('p',[self.did],'reparse','fixture',require_profile=True)['data']['state'],'routing_required')


if __name__=='__main__':unittest.main()
