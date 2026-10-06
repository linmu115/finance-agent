import unittest,tempfile
from pathlib import Path
from service.store import Store
from service.research_evidence import document_version

class DependencyVersionTests(unittest.TestCase):
    def test_research_correction_and_profile_changes_invalidate_model_dependency(self):
        from service.tests.test_research_ingestion import ResearchIngestionTests
        fixture=ResearchIngestionTests('test_profile_change_invalidates_stale_result_and_retrieval')
        fixture.setUp()
        try:
            fixture.commit()
            store=fixture.s.store; did=fixture.did
            before=document_version(store,'p',did)
            with store.connect(write=True) as db:
                db.execute("UPDATE research_records SET content_hash='changed-forecast' WHERE document_id=? AND is_current=1",(did,))
            changed=document_version(store,'p',did)
            self.assertNotEqual(before['version'],changed['version'])
            self.assertEqual(before['original_sha256'],changed['original_sha256'])
            profile=fixture.profile_input('2025-03-01');profile['title']='Revised report attribution'
            fixture.set_profile(did,profile)
            self.assertNotEqual(changed['version'],document_version(store,'p',did)['version'])
        finally:
            fixture.tearDown()

    def test_fact_definition_change_invalidates_version_without_changing_original_file(self):
        with tempfile.TemporaryDirectory() as folder:
            store=Store(folder)
            with store.connect(write=True) as db:
                db.execute("INSERT INTO projects VALUES('p','P','now')")
                db.execute("INSERT INTO documents(document_id,project_id,original_name,sha256,relative_path,media_type,state,parser_version,created_at) VALUES('d','p','报告.pdf','original','d.pdf','application/pdf','ready','v1','now')")
                db.execute("INSERT INTO facts(fact_id,document_id,project_id,metric,value,period,scope,currency,source_json) VALUES('f','d','p','revenue','120','2025','consolidated','CNY','{}')")
            before=document_version(store,'p','d')
            self.assertEqual(before['fact_count'],1)
            with store.connect(write=True) as db:db.execute("UPDATE facts SET source_json=? WHERE fact_id='f'",('{"definition":"产品收入"}',))
            after=document_version(store,'p','d')
            self.assertNotEqual(before['version'],after['version']);self.assertEqual(before['original_sha256'],after['original_sha256'])
            self.assertEqual(after,document_version(store,'p','d'))

if __name__=='__main__':unittest.main()
