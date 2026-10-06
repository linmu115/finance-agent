"""Run inputs are stored once per distinct content and linked into run folders."""
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from sandbox.launcher import SHARED_FOLDER as LAUNCHER_FOLDER
from service import snapshots
from service.document_library import remove_document
from service.snapshots import SHARED_FOLDER, remove_unreferenced, write_input
from service.tests import test_research_ingestion as research_fixture


class SnapshotStoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.exports = Path(self.tmp.name) / 'exports'
        for run in ('run1', 'run2', 'run3'):
            (self.exports / 'p' / run).mkdir(parents=True)

    def tearDown(self):
        self.tmp.cleanup()

    def stored(self):
        return sorted(p.name for p in (self.exports / 'p' / SHARED_FOLDER).iterdir())

    def test_launcher_and_service_agree_on_the_folder(self):
        self.assertEqual(SHARED_FOLDER, LAUNCHER_FOLDER)

    def test_identical_content_is_one_file_under_every_run_name(self):
        data = json.dumps({'pages': ['营业收入'] * 1000}, ensure_ascii=False).encode()
        first = write_input(self.exports, 'p', self.exports / 'p' / 'run1' / 'pages.json', data)
        second = write_input(self.exports, 'p', self.exports / 'p' / 'run2' / 'pages.json', data)
        self.assertEqual(first, second)
        self.assertEqual(first.parent.name, SHARED_FOLDER)
        self.assertEqual(first.suffix, '.json')
        self.assertEqual(len(self.stored()), 1)
        for run in ('run1', 'run2'):
            placed = self.exports / 'p' / run / 'pages.json'
            self.assertEqual(placed.read_bytes(), data)
            self.assertTrue(os.path.samefile(placed, first))
        self.assertEqual(first.stat().st_nlink, 3)
        # Different content, even under the same name, is a different snapshot.
        other = write_input(self.exports, 'p', self.exports / 'p' / 'run3' / 'pages.json', data + b' ')
        self.assertNotEqual(other, first)
        self.assertEqual((self.exports / 'p' / 'run1' / 'pages.json').read_bytes(), data)
        self.assertEqual(len(self.stored()), 2)

    def test_projects_do_not_share_a_store(self):
        (self.exports / 'q' / 'run').mkdir(parents=True)
        mine = write_input(self.exports, 'p', self.exports / 'p' / 'run1' / 'facts.json', b'[]')
        theirs = write_input(self.exports, 'q', self.exports / 'q' / 'run' / 'facts.json', b'[]')
        self.assertFalse(os.path.samefile(mine, theirs))

    def test_volume_without_hard_links_keeps_one_ordinary_copy_per_run(self):
        with patch.object(snapshots.os, 'link', side_effect=OSError(1, 'Operation not permitted')):
            for run in ('run1', 'run2'):
                destination = self.exports / 'p' / run / 'pages.json'
                self.assertEqual(write_input(self.exports, 'p', destination, b'{"a":1}'), destination)
                self.assertEqual(destination.read_bytes(), b'{"a":1}')
        # No third copy is left behind in the store.
        self.assertEqual(self.stored(), [])

    def test_link_limit_falls_back_to_a_copy_and_keeps_the_existing_snapshot(self):
        first = write_input(self.exports, 'p', self.exports / 'p' / 'run1' / 'pages.json', b'{"a":1}')
        destination = self.exports / 'p' / 'run2' / 'pages.json'
        with patch.object(snapshots.os, 'link', side_effect=OSError(31, 'Too many links')):
            self.assertEqual(write_input(self.exports, 'p', destination, b'{"a":1}'), destination)
        self.assertEqual(destination.read_bytes(), b'{"a":1}')
        self.assertTrue(first.is_file())
        self.assertEqual((self.exports / 'p' / 'run1' / 'pages.json').read_bytes(), b'{"a":1}')

    def test_only_snapshots_without_a_run_are_removed(self):
        kept = write_input(self.exports, 'p', self.exports / 'p' / 'run1' / 'pages.json', b'kept')
        dropped = write_input(self.exports, 'p', self.exports / 'p' / 'run2' / 'pages.json', b'dropped')
        (self.exports / 'p' / 'run2' / 'pages.json').unlink()
        self.assertEqual(remove_unreferenced(self.exports, 'p'), [dropped.name])
        self.assertTrue(kept.is_file())
        self.assertFalse(dropped.exists())
        self.assertEqual(remove_unreferenced(self.exports, 'never-used'), [])


class ServiceSnapshotTests(unittest.TestCase):
    def setUp(self):
        self.fixture = research_fixture.ResearchIngestionTests('test_routing_does_not_write_financial_facts')
        self.fixture.setUp()
        self.s = self.fixture.s
        self.exports = self.s.store.root / 'exports' / 'p'

    def tearDown(self):
        self.fixture.tearDown()

    def analyse(self):
        run = self.s.run_analysis('p', 'pass')['data']['run_id']
        self.s.analysis_futures[run].result(10)
        return run

    def test_repeated_analysis_runs_share_their_project_inputs(self):
        f = self.fixture
        f.commit()
        first, second = self.analyse(), self.analyse()
        names = ('pages.json', 'tables.json', 'facts.json', 'research_records.json')
        for name in names:
            a, b = self.exports / first / name, self.exports / second / name
            self.assertTrue(os.path.samefile(a, b), name)
            self.assertEqual(a.parent.name, first)
        # The exported content is what a private copy contained.
        tables = json.loads((self.exports / first / 'tables.json').read_text('utf-8'))
        self.assertEqual([t['table_id'] for t in tables], [f.did + ':t0'])
        self.assertEqual(tables[0]['rows'][1], ['Revenue', '100', '120'])
        self.assertEqual(list(tables[0]), ['table_id', 'document_id', 'page', 'sheet', 'bbox', 'rows', 'cells', 'row_source_refs', 'source_rows'])
        self.assertEqual(len(tables[0]['row_source_refs']), 3)
        self.assertEqual(len(json.loads((self.exports / first / 'pages.json').read_text('utf-8'))), 2)
        self.assertEqual(len(json.loads((self.exports / first / 'research_records.json').read_text('utf-8'))), 4)
        # Small per-run files stay private to their run.
        self.assertFalse(os.path.samefile(self.exports / first / 'analysis.py', self.exports / second / 'analysis.py'))
        # New project data makes a new snapshot for that file only; earlier runs keep theirs.
        before = (self.exports / first / 'research_records.json').read_bytes()
        f.finish_text()
        third = self.analyse()
        self.assertFalse(os.path.samefile(self.exports / first / 'research_records.json', self.exports / third / 'research_records.json'))
        self.assertEqual((self.exports / first / 'research_records.json').read_bytes(), before)
        self.assertTrue(os.path.samefile(self.exports / first / 'pages.json', self.exports / third / 'pages.json'))

    def test_cleaning_runs_on_one_document_share_its_parsed_source(self):
        f = self.fixture
        first, second = f.job(), f.job()
        a, b = self.exports / first / 'cleaning_source.json', self.exports / second / 'cleaning_source.json'
        self.assertTrue(os.path.samefile(a, b))
        self.assertEqual(json.loads(a.read_text('utf-8'))['tables'][0]['rows'][1], ['Revenue', '100', '120'])
        self.assertFalse(os.path.samefile(self.exports / first / 'cleaning_program.py', self.exports / second / 'cleaning_program.py'))

    def test_deleting_a_document_removes_the_snapshots_only_its_runs_used(self):
        f = self.fixture
        f.commit()
        self.analyse()
        store = self.exports / SHARED_FOLDER
        self.assertGreaterEqual(len(list(store.iterdir())), 5)
        remove_document(self.s, 'p', f.did)
        # Every run that linked these snapshots is gone, so nothing of the document stays in the store.
        self.assertEqual(list(store.iterdir()), [])


if __name__ == '__main__':
    unittest.main()
