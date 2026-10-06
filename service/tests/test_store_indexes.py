"""Per-document reads use indexes, and retired research records leave no search entries behind."""
import sqlite3
import tempfile
import unittest
from pathlib import Path

from service.store import Store
from service.tests import test_research_ingestion as research_fixture


def plan(db, sql, args=()):
    return ' | '.join(row[3] for row in db.execute('EXPLAIN QUERY PLAN ' + sql, args))


class IndexTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.tmp.name))

    def tearDown(self):
        self.tmp.cleanup()

    def test_document_scoped_reads_do_not_scan_whole_tables(self):
        cases = {
            # get_source_page / run_analysis row sources
            "SELECT source_json FROM chunks WHERE project_id=? AND document_id=? AND source_id IS NOT NULL AND source_id!='' ORDER BY rowid": 'chunks_document',
            "SELECT source_id,text,source_json FROM chunks WHERE project_id=? AND document_id=? AND page=? AND source_id IS NOT NULL AND source_id!='' ORDER BY rowid": 'chunks_document',
            # retired research record lookup
            "SELECT chunk_id FROM chunks WHERE document_id=? AND project_id=? AND json_extract(source_json,'$.research_record_id') IN (?,?)": 'chunks_document',
            # get_document counts, table listings, deletion
            'SELECT count(*) FROM source_tables WHERE document_id=?': 'source_tables_document',
            'SELECT * FROM source_tables WHERE document_id=? ORDER BY page,table_id': 'source_tables_document',
            'SELECT count(*) FROM current_financial_facts WHERE document_id=?': 'facts_document',
            'SELECT * FROM facts WHERE document_id=? ORDER BY fact_id': 'facts_document',
            'SELECT count(*) FROM fact_history WHERE document_id=?': 'fact_history_document',
            'DELETE FROM chunks WHERE document_id=?': 'chunks_document',
        }
        with self.store.connect() as db:
            for sql, index in cases.items():
                with self.subTest(sql=sql):
                    found = plan(db, sql, ('x',) * sql.count('?'))
                    self.assertIn(index, found)
                    for table in ('chunks', 'source_tables', 'facts', 'fact_history', 'f'):
                        self.assertNotIn('SCAN ' + table + ' ', found + ' ')

    def test_indexes_are_added_to_a_database_created_before_them(self):
        legacy = Path(self.tmp.name) / 'legacy'
        legacy.mkdir()
        Store(legacy)
        with sqlite3.connect(legacy / 'finance.sqlite') as db:
            for name in ('chunks_document', 'source_tables_document', 'facts_document', 'fact_history_document'):
                db.execute('DROP INDEX ' + name)
            db.execute("INSERT INTO chunks VALUES('c1','p','d',1,NULL,'text','{\"document_id\":\"d\"}')")
        reopened = Store(legacy)
        with reopened.connect() as db:
            names = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='index'")}
            self.assertEqual(db.execute('SELECT count(*) FROM chunks WHERE document_id=?', ('d',)).fetchone()[0], 1)
        self.assertLessEqual({'chunks_document', 'source_tables_document', 'facts_document', 'fact_history_document', 'facts_lookup'}, names)


class RetiredRecordSearchTests(unittest.TestCase):
    def setUp(self):
        self.fixture = research_fixture.ResearchIngestionTests('test_routing_does_not_write_financial_facts')
        self.fixture.setUp()
        self.s = self.fixture.s

    def tearDown(self):
        self.fixture.tearDown()

    def search_state(self):
        with self.s.store.connect() as db:
            return {
                'records': {r[0] for r in db.execute("SELECT record_id FROM research_records WHERE project_id='p' AND is_current=1")},
                'indexed': {r[0] for r in db.execute("SELECT json_extract(source_json,'$.research_record_id') FROM chunks WHERE project_id='p' AND json_extract(source_json,'$.research_record_id') IS NOT NULL")},
                'chunks': db.execute('SELECT count(*) FROM chunks').fetchone()[0],
                'fts': db.execute('SELECT count(*) FROM chunks_fts').fetchone()[0],
                'orphans': db.execute('SELECT count(*) FROM chunks_fts WHERE chunk_id NOT IN (SELECT chunk_id FROM chunks)').fetchone()[0],
            }

    def test_recleaning_a_table_replaces_exactly_the_changed_records_in_search(self):
        f = self.fixture
        f.commit()
        other = f.document('Second', '2025-03-05')
        f.set_profile(other, f.profile_input('2025-03-05'))
        other_pid = self.s.begin_script_cleaning('p', [other], 'owner2', 'fixture')['data']['processing_id']
        f.commit(other_pid, other)
        before = self.search_state()
        self.assertEqual(before['records'], before['indexed'])
        self.assertEqual(before['chunks'], before['fts'])
        self.assertEqual(len(before['records']), 8)
        # The first document's table is cleaned again with one metric renamed; the second document is untouched.
        changed = {'tables': [dict(f.payload['tables'][0], rows=[{'row': 2, 'attributes': {'metric': 'revenue', 'label': '营业收入'}},
                                                                {'row': 3, 'attributes': {'metric': 'net_income', 'label': '归母净利润'}}])]}
        again = self.s.begin_script_cleaning('p', [f.did], 'owner3', 'fixture', force=True)['data']['processing_id']
        f.commit(again, f.did, changed)
        after = self.search_state()
        self.assertEqual(after['records'], after['indexed'])
        self.assertEqual(after['chunks'], after['fts'])
        self.assertEqual(after['orphans'], 0)
        self.assertEqual(len(after['records']), 8)
        retired, added = before['records'] - after['records'], after['records'] - before['records']
        self.assertEqual(len(retired), len(added))
        self.assertGreaterEqual(len(retired), 2)
        found = lambda query: {i['source_ref'].get('research_record_id') for i in self.s.search_evidence('p', query, limit=30)['data']['items']}
        self.assertTrue(found('归母净利润') & added)
        self.assertFalse(found('净利润 Profit') & retired)
        # Records of the other document keep their search entries.
        with self.s.store.connect() as db:
            untouched = {r[0] for r in db.execute("SELECT record_id FROM research_records WHERE document_id=? AND is_current=1", (other,))}
        self.assertEqual(len(untouched), 4)
        self.assertLessEqual(untouched, after['indexed'])


if __name__ == '__main__':
    unittest.main()
