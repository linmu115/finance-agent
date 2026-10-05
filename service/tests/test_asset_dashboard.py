"""Dashboard must preserve project, current-revision, entity and data-nature boundaries."""
import unittest
from service.tests.test_research_ingestion import ResearchIngestionTests


class AssetDashboardTests(unittest.TestCase):
    def setUp(self):
        self.fixture = ResearchIngestionTests('test_profile_change_invalidates_stale_result_and_retrieval')
        self.fixture.setUp()
        self.s = self.fixture.s

    def tearDown(self):
        self.fixture.tearDown()

    def test_ingested_forecasts_are_visible_without_saved_models(self):
        self.fixture.commit()
        catalog = self.s.get_asset_catalog('p')['data']
        self.assertEqual(catalog['summary']['facts'], 0)
        self.assertEqual(catalog['summary']['records'], 4)
        self.assertEqual(catalog['summary']['forecasts'], 2)
        self.assertEqual(catalog['publishers'], ['Broker A'])
        self.assertEqual(catalog['periods'], ['2024-FY', '2025-FY'])
        self.assertEqual(catalog['documents'][0]['published_at'], '2025-03-01')
        self.assertEqual(catalog['documents'][0]['authors'], ['Alice'])

    def test_entity_filter_does_not_adopt_other_company_records(self):
        self.fixture.commit()
        entities = self.s.get_asset_catalog('p')['data']['entities']
        alpha = next(e for e in entities if e['name']=='Alpha')
        beta = next(e for e in entities if e['name']=='Beta')
        self.assertEqual(self.s.get_asset_catalog('p', alpha['key'])['data']['summary']['records'], 4)
        self.assertEqual(self.s.get_asset_catalog('p', beta['key'])['data']['summary']['records'], 0)
        self.assertEqual(self.s.get_asset_catalog('q')['data']['summary']['documents'], 0)
        self.assertEqual(self.s.get_asset_catalog('q')['data']['entities'], [])
        with self.assertRaisesRegex(ValueError, 'asset_entity_not_found'):
            self.s.get_asset_catalog('q', alpha['key'])

    def test_catalog_excludes_superseded_profile_extraction(self):
        self.fixture.commit()
        profile = self.fixture.profile_input('2025-03-01')
        profile['title'] = 'Metadata correction invalidates prior extraction'
        self.fixture.set_profile(self.fixture.did, profile)
        catalog = self.s.get_asset_catalog('p')['data']
        self.assertEqual(catalog['summary']['records'], 0)
        self.assertEqual(catalog['metrics'], [])
        self.assertEqual(catalog['documents'][0]['title'], profile['title'])

    def test_forecast_cutoff_keeps_source_date_separate_from_forecast_period(self):
        self.fixture.commit()
        query = self.s.query_research_records('p', {'data_kind':'analyst_forecast','period':'2025-FY','as_of':'2025-02-28'})['data']
        self.assertEqual(query['total'], 0)
        query = self.s.query_research_records('p', {'data_kind':'analyst_forecast','period':'2025-FY','as_of':'2025-03-01'},limit=1)['data']
        self.assertEqual(query['total'], 2)
        self.assertIsNotNone(query['next_offset'])
        self.assertEqual(query['items'][0]['published_at'], '2025-03-01')
        self.assertEqual(query['items'][0]['period'], '2025-FY')


if __name__ == '__main__':
    unittest.main()
