import unittest,tempfile
from pathlib import Path
from service.store import Store
from service.research_evidence import document_version

class DependencyVersionTests(unittest.TestCase):
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
