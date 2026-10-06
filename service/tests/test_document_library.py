import json
import unittest
from concurrent.futures import Future
from service.document_library import remove_document, DOCUMENT_TABLES
from service.store import dumps, utcnow
from service.tests.test_research_ingestion import ResearchIngestionTests as Fixture


class DocumentLibraryTests(unittest.TestCase):
    def setUp(self):
        self.fixture=Fixture('test_routing_does_not_write_financial_facts')
        self.fixture.setUp()
        self.s=self.fixture.s
    def tearDown(self): self.fixture.tearDown()

    def test_delete_all_ingested_revisions_and_search_but_preserve_other_documents(self):
        f=self.fixture;rid=f.commit();f.finish_text();did=f.did
        f.finish_text('Updated view keeps history')
        other=f.document('Other','2025-03-02')
        foreign=f.document('Foreign','2025-03-02',project='q')
        original=self.s.store.root/self.s.store.document('p',did)['relative_path']
        with self.s.store.connect(write=True) as db:
            db.execute('INSERT INTO fact_history VALUES(?,?,?,?,?,?)',('old','p',did,f.pid,dumps({'document_id':did,'value':'42'}),utcnow()))
            db.execute('INSERT INTO facts(fact_id,document_id,project_id,value,source_json) VALUES(?,?,?,?,?)',('value',did,'p','42','{}'))
            db.execute('INSERT INTO embedding_cache VALUES(?,?,?,?,?,?)',('vector','p','fake',1,'[1]',utcnow()))
        removed=remove_document(self.s,'p',did)
        self.assertGreater(removed['removed']['research_records'],6)
        self.assertEqual(removed['removed']['facts'],1)
        self.assertFalse(original.exists())
        self.assertFalse(self.s._prepared_path('p',did).exists())
        self.assertFalse((self.s.store.root/'exports'/'p'/rid).exists())
        with self.s.store.connect() as db:
            tables={r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            for table in DOCUMENT_TABLES:
                if table in tables:self.assertEqual(db.execute(f'SELECT count(*) FROM {table} WHERE document_id=?',(did,)).fetchone()[0],0,table)
            self.assertEqual(db.execute('SELECT count(*) FROM chunks_fts WHERE chunk_id NOT IN (SELECT chunk_id FROM chunks)').fetchone()[0],0)
            self.assertEqual(db.execute('SELECT count(*) FROM embedding_cache WHERE project_id=?',('p',)).fetchone()[0],0)
        self.assertEqual(self.s.query_research_records('p')['data']['total'],0)
        self.assertEqual(self.s.store.document('p',other)['document_id'],other)
        self.assertEqual(self.s.store.document('q',foreign)['document_id'],foreign)
        self.assertEqual(self.s.get_asset_catalog('p')['data']['summary']['records'],0)
        # Re-registering the same source creates a new identity, no stale dedup or cache result.
        again=self.s.register_document('p',str(f.root/'uploads/First.csv'),'First.csv')['data']
        self.assertNotEqual(again['document_id'],did)
        self.assertEqual(again['fact_count'],0)

    def test_cross_project_deletion_rejected(self):
        with self.assertRaisesRegex(ValueError,'document_not_found_in_project'):
            remove_document(self.s,'q',self.fixture.did)
        self.assertTrue(self.s.get_document('p',self.fixture.did)['data'])

    def test_running_analysis_rejects_and_rolls_back_progress_change(self):
        f=self.fixture;rid=f.commit()
        before=self.s._clean_state('p',f.pid)
        pending=Future();self.s.analysis_futures[rid]=pending
        with self.assertRaisesRegex(ValueError,'计算任务'):
            remove_document(self.s,'p',f.did)
        self.assertEqual(self.s._clean_state('p',f.pid),before)
        self.assertEqual(self.s.query_research_records('p')['data']['total'],4)
        pending.set_result(None)

if __name__=='__main__':unittest.main()
