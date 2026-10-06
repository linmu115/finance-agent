import json
import tempfile
import unittest
from pathlib import Path

from service.core import FinanceService
from service.evidence_review import review_details
from service.store import dumps


class EvidenceReviewTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.s = FinanceService(Path(self.temp.name))
        self.s.create_project('p', 'Project')
        self.s.create_project('q', 'Other')
        path = self.s.store.root/'uploads'/'input.csv'
        path.write_text('项目,本期\n复杂数据,1 234', encoding='utf-8')
        self.did = self.s.register_document('p', str(path), path.name)['data']['document_id']
        self.s._persist_prepared('p', self.did, {'company':'Company', 'report_year':2024, 'warnings':[],
            'pages':[{'page':1, 'text':'复杂数据 1 234；金额单位待确认'}],
            'tables':[{'index':0,'page':1,'rows':[['项目','本期'],['复杂数据','1 234']],'cells':{}}]})

    def tearDown(self):
        for pool in (self.s.processing_pool,self.s.pool,self.s.analysis_pool,self.s.embedding_pool):
            pool.shutdown(wait=True,cancel_futures=True)
        self.temp.cleanup()

    def batch(self, key, issues, stamp, **extra):
        document = self.s.store.document('p', self.did)
        result = {'script_table':0,'document_sha256':document['sha256'],'issues':issues,
                  'coordinates':[[f'{self.did}:t0',2,2]],**extra}
        with self.s.store.connect(write=True) as db:
            db.execute('INSERT INTO normalization_batches VALUES(?,?,?,?,?)',(self.did,key,'owner',dumps(result),stamp))

    def test_unstructured_information_remains_searchable_and_points_to_original(self):
        self.batch('old',[{'table':0,'row':2,'column':2,'reason':'semantic_review_pending','detail':'无法可靠拆分原格中的多个金额'}],'2026-01-01')
        result = self.s.get_normalization_details('p',self.did,review_only=True,query='金额')['data']
        self.assertEqual(result['total'],1)
        self.assertEqual(result['summary']['tables_preserved'],1)
        self.assertEqual(result['summary']['facts_needing_review'],0)
        self.assertEqual(result['items'][0]['source'],{'document_id':self.did,'table_id':self.did+':t0','page':1,'row':2,'column':2})
        self.assertEqual(self.s.query_financial_data('p')['data']['total'],0)
        original = self.s.get_source_table('p',self.did,self.did+':t0')['data']['items'][0]
        self.assertEqual(original['rows'][1][1],'1 234')
        catalog = self.s.get_asset_catalog('p')['data']
        self.assertEqual(catalog['documents'][0]['review']['extraction_issues'],1)
        with self.assertRaises(ValueError):
            review_details(self.s.store,'q',self.did)

    def test_successful_local_repair_replaces_prior_issue_but_does_not_delete_history(self):
        self.batch('old',[{'table':0,'reason':'unresolved_period'}],'2026-01-01')
        self.batch('new',[],'2026-01-02')
        current = review_details(self.s.store,'p',self.did)
        self.assertEqual(current['total'],0)
        self.assertEqual(current['summary']['tables_with_decisions'],1)
        with self.s.store.connect() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM normalization_batches').fetchone()[0],2)

    def test_old_source_and_profile_issues_do_not_masquerade_as_current(self):
        self.batch('source',[{'table':0,'reason':'old source'}],'2026-01-03',document_sha256='old')
        self.batch('profile',[{'table':0,'reason':'old profile'}],'2026-01-02',profile_revision='old')
        self.assertEqual(review_details(self.s.store,'p',self.did)['total'],0)

    def test_profile_revision_is_read_from_metadata_not_profile_content(self):
        document = self.s.store.document('p',self.did)
        with self.s.store.connect(write=True) as db:
            db.execute('INSERT INTO document_profiles(document_id,project_id,revision_id,source_hash,profile_json,updated_at) VALUES(?,?,?,?,?,?)',
                       (self.did,'p','current',document['sha256'],dumps({'kind':'financial_report'}),'2026-01-01'))
            db.execute('INSERT INTO research_page_reviews(document_id,profile_revision,page,source_hash,review_json,updated_at) VALUES(?,?,?,?,?,?)',
                       (self.did,'current',1,document['sha256'],dumps({'verdict':'needs_review','note':'图中金额未完整提取'}),'2026-01-01'))
        self.batch('current',[{'table':0,'reason':'unresolved_period'}],'2026-01-02',profile_revision='current')
        result = review_details(self.s.store,'p',self.did)
        self.assertEqual(result['summary']['extraction_issues'],1)
        self.assertEqual(result['summary']['page_issues'],1)
        self.assertEqual(result['summary']['tables_with_decisions'],1)
        self.assertEqual(self.s.get_asset_catalog('p')['data']['documents'][0]['review'],result['summary'])

    def test_pagination_and_raw_candidate_values_are_preserved_without_numeric_coercion(self):
        with self.s.store.connect(write=True) as db:
            for i in range(3):
                source={'page':1,'table_id':self.did+':t0','row':2,'column':2,'normalization':{'label':'待确认金额','review_warnings':['unresolved_currency']}}
                db.execute('''INSERT INTO facts(fact_id,document_id,project_id,company,metric,value,raw_value,raw_unit,quality,source_json)
                    VALUES(?,?,?,?,?,?,?,?,?,?)''',(f'f{i}',self.did,'p','Company','amount','1234.0000','1 234','未知单位','needs_review',dumps(source)))
        one = review_details(self.s.store,'p',self.did,limit=2)
        two = review_details(self.s.store,'p',self.did,offset=one['next_offset'],limit=2)
        self.assertEqual(one['total'],3)
        self.assertEqual(len(one['items'])+len(two['items']),3)
        self.assertIsNone(two['next_offset'])
        self.assertEqual(one['items'][0]['raw_value'],'1 234')
        self.assertEqual(one['items'][0]['value'],'1234.0000')
        translated = review_details(self.s.store,'p',self.did,query='币种 待确认')
        self.assertEqual(translated['total'],3)
        self.assertEqual(translated['items'][0]['message'],'unresolved_currency')


if __name__ == '__main__':
    unittest.main()
