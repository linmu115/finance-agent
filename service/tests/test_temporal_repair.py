import copy
import json
import sqlite3
import unittest

from service.temporal_repair import enrich_sources, select_targets


class TemporalRepairTests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(":memory:")
        self.db.executescript("""CREATE TABLE documents(document_id TEXT,project_id TEXT);
            CREATE TABLE pages(document_id TEXT,page INTEGER,text TEXT);
            CREATE TABLE source_tables(document_id TEXT,page INTEGER,table_id TEXT,rows_json TEXT);""")
        self.db.executemany("INSERT INTO documents VALUES(?,?)", [("doc", "p"), ("other_doc", "other_project")])
        for page in range(1, 8):
            self.db.execute("INSERT INTO pages VALUES(?,?,?)", ("doc", page, f"第{page}页原文" + "完整段落" * 1400))
            self.db.execute("INSERT INTO source_tables VALUES(?,?,?,?)", ("doc", page, f"doc:t{page}",
                            json.dumps([["项目", "2024年12月31日"], ["示例余额", "100.00"]])))
        self.db.execute("INSERT INTO pages VALUES(?,?,?)", ("other_doc", 2, "不属于当前项目的原文"))

    def tearDown(self):
        self.db.close()

    def test_only_unresolved_changed_stale_pending_and_new_sources_are_selected(self):
        sources = [{"source_key": key, "source_fingerprint": "fp_" + key} for key in
                   ("completed", "unresolved", "stale", "pending", "changed", "new")]
        report = {"source_fingerprints": {source["source_key"]: source["source_fingerprint"] for source in sources[:-1]},
                  "unresolved": [{"source_key": "unresolved", "reason": "原表头缺失"}],
                  "stale_sources": ["stale"], "pending_new_sources": ["pending"]}
        report["source_fingerprints"]["changed"] = "old_fingerprint"
        before = copy.deepcopy(report)
        selected = select_targets(sources, report)
        self.assertEqual([source["source_key"] for source in selected], ["unresolved", "stale", "pending", "changed", "new"])
        self.assertEqual(report, before)
        self.assertIs(selected[0], sources[1])

    def test_221_completed_sources_are_not_replayed_to_repair_11_pending(self):
        sources = [{"source_key": str(index), "source_fingerprint": "unchanged"} for index in range(232)]
        report = {"source_fingerprints": {source["source_key"]: "unchanged" for source in sources},
                  "unresolved": [{"source_key": str(index)} for index in range(221, 232)]}
        self.assertEqual(len(select_targets(sources, report)), 11)
        self.assertEqual(select_targets(sources[:221], report), [])

    def test_enrichment_retains_full_pages_table_identities_and_source_identity(self):
        source = {"source_key": "target", "document_id": "doc", "page": 4, "table_id": "doc:t4", "row": 2, "column": 2,
                  "page_context": "旧的截断上下文", "source_fingerprint": "unchanged", "period": "2024-FY"}
        before = copy.deepcopy(source)
        enriched = enrich_sources(self.db, "p", [source])[0]
        self.assertEqual(source, before)
        self.assertEqual([page["page"] for page in enriched["context_pages"]], [2, 3, 4, 5])
        self.assertEqual([page["relative_page"] for page in enriched["context_pages"]], [-2, -1, 0, 1])
        for page in enriched["context_pages"]:
            self.assertGreater(len(page["text"]), 5000)
            self.assertEqual(page["document_id"], "doc")
            self.assertEqual(page["tables"][0]["table_id"], f"doc:t{page['page']}")
            self.assertEqual(page["tables"][0]["table_headers"][0], ["项目", "2024年12月31日"])
        self.assertEqual(enriched["page_context"], enriched["context_pages"][2]["text"])
        for field in ("source_key", "source_fingerprint", "table_id", "row", "column", "period"):
            self.assertEqual(enriched[field], source[field])

    def test_window_clamps_document_start_and_never_reads_other_project(self):
        enriched = enrich_sources(self.db, "p", [{"document_id": "doc", "page": 1}])[0]
        self.assertEqual([page["page"] for page in enriched["context_pages"]], [1, 2])
        self.assertNotIn("不属于当前项目", json.dumps(enriched, ensure_ascii=False))
        with self.assertRaisesRegex(ValueError, "outside_project"):
            enrich_sources(self.db, "p", [{"document_id": "other_doc", "page": 2}])

    def test_missing_page_is_preserved_as_missing_not_invented(self):
        source = {"document_id": "doc", "page": None, "period": "", "page_context": "无页码"}
        enriched = enrich_sources(self.db, "p", [source])[0]
        self.assertEqual(enriched["context_pages"], [])
        self.assertEqual(enriched["period"], "")

    def test_shared_context_returns_independent_source_objects(self):
        inputs = [{"source_key": "first", "document_id": "doc", "page": 4},
                  {"source_key": "second", "document_id": "doc", "page": 4}]
        enriched = enrich_sources(self.db, "p", inputs)
        enriched[0]["context_pages"][0]["tables"][0]["table_id"] = "changed"
        self.assertEqual(enriched[1]["context_pages"][0]["tables"][0]["table_id"], "doc:t2")
        self.assertNotIn("context_pages", inputs[0])


if __name__ == "__main__":
    unittest.main()
