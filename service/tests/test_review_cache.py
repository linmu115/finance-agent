import json
import sqlite3
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from contextlib import closing

from service.review_cache import accept_result, result_hash


class ImmutableReviewCacheTests(unittest.TestCase):
    def test_concurrent_outputs_accept_same_original_owner_and_never_replace(self):
        for table in ("temporal_review_cache","fact_definition_cache"):
            with self.subTest(table=table),tempfile.TemporaryDirectory() as directory:
                path=Path(directory)/"cache.sqlite"
                with closing(sqlite3.connect(path)) as db,db:db.execute(f"CREATE TABLE {table}(cache_key TEXT PRIMARY KEY,result_json TEXT,created_at TEXT)")
                barrier=threading.Barrier(2)
                def candidate(owner):
                    payload={"decisions":[{"reason":"不同输出 "+owner}],"_review_provenance":{"owner_run_id":owner}}
                    barrier.wait(timeout=5)
                    with closing(sqlite3.connect(path,timeout=10)) as db,db:return accept_result(db,table,{"cache_key":"same-input"},payload)
                with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(candidate,["pi-A","pi-B"]))
                self.assertEqual(results[0][0],results[1][0]);self.assertEqual(sum(x[1] for x in results),1)
                with closing(sqlite3.connect(path)) as db,db:
                    before=db.execute(f"SELECT * FROM {table}").fetchone()
                    accepted,inserted=accept_result(db,table,{"cache_key":"same-input"},{"_review_provenance":{"owner_run_id":"late-pi"}})
                    after=db.execute(f"SELECT * FROM {table}").fetchone()
                self.assertFalse(inserted);self.assertEqual(before,after);self.assertEqual(accepted,results[0][0])
                self.assertEqual(result_hash(accepted),result_hash(json.loads(before[1])))

    def test_catalog_composite_identity_preserves_accepted_output(self):
        with closing(sqlite3.connect(":memory:")) as db,db:
            db.execute("CREATE TABLE metric_directory_reviews(project_id TEXT,catalog_hash TEXT,prompt_hash TEXT,model TEXT,result_json TEXT,created_at TEXT,PRIMARY KEY(project_id,catalog_hash,prompt_hash,model))")
            keys={"project_id":"p","catalog_hash":"catalog","prompt_hash":"prompt","model":"deepseek"}
            first={"review":{"aliases":{}},"_review_provenance":{"owner_run_id":"first"}}
            accept_result(db,"metric_directory_reviews",keys,first)
            accepted,inserted=accept_result(db,"metric_directory_reviews",keys,{"review":{"aliases":{"wrong":"value"}}})
            self.assertEqual(accepted,first);self.assertFalse(inserted)
            second,inserted=accept_result(db,"metric_directory_reviews",keys|{"project_id":"q"},{"different_project":True})
            self.assertTrue(inserted);self.assertEqual(second,{"different_project":True})

    def test_untrusted_table_or_key_shape_rejected(self):
        with closing(sqlite3.connect(":memory:")) as db,db:
            for table,keys in (("facts",{"cache_key":"x"}),("temporal_review_cache",{"wrong":"x"})):
                with self.assertRaisesRegex(ValueError,"invalid_review_cache_identity"):accept_result(db,table,keys,{})
