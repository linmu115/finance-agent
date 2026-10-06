"""Document listings and the data catalog: same answers as per-document queries, in a fixed number of statements."""
import json
import sqlite3
import unittest
import uuid
from unittest.mock import patch

from service.store import dumps
from service.tests import test_research_ingestion as research_fixture


class ListingQueryTests(unittest.TestCase):
    def setUp(self):
        self.fixture = research_fixture.ResearchIngestionTests('test_routing_does_not_write_financial_facts')
        self.fixture.setUp()
        self.s = self.fixture.s
        f = self.fixture
        f.commit()
        f.finish_text()
        self.second = f.document('Second', '2025-03-05')
        self.plain = f.document('Plain', '2025-03-06')
        self.foreign = f.document('Foreign', '2025-03-07', project='q')
        self.add_facts(self.plain, 'p', [('PythonScript', 'income', '公司', 'revenue', '2024-FY', 'CNY', {'segment': '国内'}, 'original'),
                                         ('LangExtract', 'income', '公司', 'revenue', '2023-FY', 'CNY', {'segment': '海外'}, 'restated'),
                                         (None, None, None, 'capex', None, None, {}, None),
                                         ('PythonScript', 'balance', '甲公司', 'assets', '2024-12-31', 'HKD', {}, 'original')])
        self.add_facts(self.foreign, 'q', [('PythonScript', 'income', '乙公司', 'revenue', '2024-FY', 'USD', {}, 'original')])

    def tearDown(self):
        self.fixture.tearDown()

    def add_facts(self, document_id, project, rows):
        with self.s.store.connect(write=True) as db:
            for engine, statement, company, metric, period, currency, dimensions, version in rows:
                meta = {k: v for k, v in {'engine': engine, 'statement': statement, 'label': metric and metric.upper(), 'dimensions': dimensions,
                                          'dimension_labels': {'segment': '分部'}, 'restatement': version}.items() if v is not None}
                db.execute('INSERT INTO facts VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)', (uuid.uuid4().hex, document_id, project, company, metric, 2024, period,
                           'consolidated_CAS', currency, '1', '元', '1', dumps({'document_id': document_id, 'page': 1, 'normalization': meta}), 5, 'ok'))

    def reference_document(self, project_id, document_id):
        """The earlier per-document queries, kept here as the definition of each field."""
        doc = self.s.store.document(project_id, document_id)
        with self.s.store.connect() as db:
            one = lambda sql: db.execute(sql, (document_id,)).fetchone()[0]
            doc['table_count'] = one('SELECT count(*) FROM source_tables WHERE document_id=?')
            doc['fact_count'] = one('SELECT count(*) FROM current_financial_facts WHERE document_id=?')
            doc['normalized_fact_count'] = one("SELECT count(*) FROM current_financial_facts WHERE document_id=? AND json_extract(source_json,'$.normalization.engine') IN ('LangExtract','PythonScript')")
            doc['legacy_fact_count'] = doc['fact_count'] - doc['normalized_fact_count']
            engines = {r[0] for r in db.execute("SELECT DISTINCT json_extract(result_json,'$.engine') FROM normalization_batches WHERE document_id=?", (document_id,)) if r[0]}
            doc['normalization_engine'] = next(iter(engines)) if len(engines) == 1 else 'mixed' if engines else 'legacy_rules' if doc['fact_count'] else 'unprocessed'
            doc['research_record_count'] = one('SELECT count(*) FROM research_records r LEFT JOIN document_profiles p USING(document_id) WHERE r.document_id=? AND r.is_current=1 AND (r.profile_revision IS NULL OR r.profile_revision=p.revision_id)')
        doc['profile'] = self.s._document_profile(project_id, document_id)
        return doc

    def statements(self, call):
        """Number of SQL statements a call executes."""
        seen = []
        real = sqlite3.connect
        def connect(*args, **kwargs):
            db = real(*args, **kwargs)
            db.set_trace_callback(seen.append)
            return db
        with patch('service.store.sqlite3.connect', side_effect=connect):
            call()
        return len([sql for sql in seen if not sql.upper().startswith(('PRAGMA', 'BEGIN', 'COMMIT', 'ROLLBACK'))])

    def test_listing_equals_the_per_document_definition(self):
        for project in ('p', 'q'):
            listed = self.s.list_documents(project)['data']['items']
            with self.s.store.connect() as db:
                order = [r[0] for r in db.execute('SELECT document_id FROM documents WHERE project_id=? ORDER BY created_at DESC', (project,))]
            self.assertEqual([d['document_id'] for d in listed], order)
            for doc in listed:
                expected = self.reference_document(project, doc['document_id'])
                self.assertEqual(doc, expected)
                self.assertEqual(list(doc), list(expected))
                single = self.s.get_document(project, doc['document_id'])
                self.assertEqual(single['data'], expected)
                self.assertEqual(single['warnings'], expected['warnings'])
        by_id = {d['document_id']: d for d in self.s.list_documents('p')['data']['items']}
        self.assertEqual((by_id[self.plain]['fact_count'], by_id[self.plain]['normalized_fact_count'], by_id[self.plain]['legacy_fact_count']), (4, 3, 1))
        self.assertEqual(by_id[self.fixture.did]['research_record_count'], 6)
        self.assertEqual(by_id[self.second]['research_record_count'], 0)
        self.assertNotIn(self.foreign, by_id)
        with self.assertRaisesRegex(ValueError, 'document_not_found_in_project'):
            self.s.get_document('p', self.foreign)

    def test_listing_cost_does_not_grow_with_the_number_of_documents(self):
        before = self.statements(lambda: self.s.list_documents('p'))
        for index in range(9):
            self.fixture.document(f'More{index}', '2025-04-01')
        self.assertEqual(len(self.s.list_documents('p')['data']['items']), 12)
        self.assertEqual(self.statements(lambda: self.s.list_documents('p')), before)

    def test_catalog_totals_and_filters_match_direct_queries(self):
        with self.s.store.connect() as db:
            direct = lambda column: [r[0] for r in db.execute(f"SELECT DISTINCT {column} FROM current_financial_facts WHERE project_id='p' ORDER BY {column}")]
            expected = {'companies': direct('company'), 'periods': direct('period'), 'scopes': direct('scope'), 'currencies': direct('currency')}
            total = db.execute("SELECT count(*) FROM current_financial_facts WHERE project_id='p'").fetchone()[0]
        self.assertEqual(expected['companies'], [None, '公司', '甲公司'])
        catalog = self.s.get_data_catalog('p')['data']
        self.assertEqual(catalog['counts']['facts'], total)
        self.assertEqual(total, 4)
        for key, values in expected.items():
            self.assertEqual(catalog[key], values, key)
        self.assertEqual(catalog['versions'], ['original', 'restated'])
        self.assertEqual(catalog['dimensions'], {'segment': ['国内', '海外']})
        self.assertEqual(catalog['dimension_labels'], {'segment': {'国内': '分部', '海外': '分部'}})
        # A metric page reports the dimensions of its own metrics only, while totals stay project-wide.
        page = self.s.get_data_catalog('p', limit=1)['data']
        self.assertEqual([m['metric'] for m in page['metrics']], ['assets'])
        self.assertEqual(page['counts']['facts'], total)
        self.assertEqual(page['dimensions'], {})
        self.assertEqual(page['versions'], ['original'])
        self.assertEqual(page['companies'], expected['companies'])
        revenue = self.s.get_data_catalog('p', query='revenue', limit=5)['data']
        self.assertEqual(revenue['dimensions'], {'segment': ['国内', '海外']})
        self.assertEqual(revenue['versions'], ['original', 'restated'])
        beyond = self.s.get_data_catalog('p', limit=5, offset=50)['data']
        self.assertEqual((beyond['metrics'], beyond['dimensions'], beyond['versions']), ([], {}, []))
        self.assertEqual(self.s.get_data_catalog('p', company='甲公司')['data']['counts']['facts'], 1)


if __name__ == '__main__':
    unittest.main()
