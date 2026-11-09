"""Tacto -> Haejo per-user data migration."""
from pathlib import Path
import tempfile
import unittest

from haejo.legacy_data import legacy_pairs, migrate_legacy_data
from haejo import access_log


class LegacyDataMigrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.home = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def test_macos_support_directory_and_flows_move_when_haejo_paths_are_free(self):
        old = self.home/'Library/Application Support/Tacto'
        (old/'Logs').mkdir(parents=True)
        (old/'preferences.json').write_text('{"schema": 1}')
        flows = self.home/'.local/share/tacto/flows'
        flows.mkdir(parents=True)
        (flows/'calc.json').write_text('{}')
        moved = migrate_legacy_data(self.home, {}, 'darwin')
        self.assertEqual(2, len(moved))
        new = self.home/'Library/Application Support/Haejo'
        self.assertEqual('{"schema": 1}', (new/'preferences.json').read_text())
        self.assertTrue((new/'Logs').is_dir())
        self.assertFalse(old.exists())
        self.assertEqual('{}', (self.home/'.local/share/haejo/flows/calc.json').read_text())

    def test_existing_haejo_directory_is_never_merged_or_overwritten(self):
        old = self.home/'Library/Application Support/Tacto'
        old.mkdir(parents=True)
        (old/'preferences.json').write_text('old')
        new = self.home/'Library/Application Support/Haejo'
        new.mkdir(parents=True)
        (new/'preferences.json').write_text('new')
        self.assertEqual([], migrate_legacy_data(self.home, {}, 'darwin'))
        self.assertEqual('old', (old/'preferences.json').read_text())
        self.assertEqual('new', (new/'preferences.json').read_text())

    def test_symlinked_legacy_directory_is_left_alone(self):
        target = self.home/'elsewhere'
        target.mkdir()
        support = self.home/'Library/Application Support'
        support.mkdir(parents=True)
        (support/'Tacto').symlink_to(target)
        self.assertEqual([], migrate_legacy_data(self.home, {}, 'darwin'))
        self.assertTrue((support/'Tacto').is_symlink())
        self.assertFalse((support/'Haejo').exists())

    def test_second_run_moves_nothing(self):
        (self.home/'Library/Application Support/Tacto').mkdir(parents=True)
        self.assertEqual(1, len(migrate_legacy_data(self.home, {}, 'darwin')))
        self.assertEqual([], migrate_legacy_data(self.home, {}, 'darwin'))

    def test_relative_xdg_data_home_is_ignored_like_the_flow_store(self):
        pairs = legacy_pairs(self.home, {'XDG_DATA_HOME': 'relative'}, 'linux')
        self.assertEqual(self.home/'.local/share/tacto', pairs[1][0])
        self.assertEqual(self.home/'.local/state/tacto', pairs[0][0])

    def test_activity_history_written_before_the_rename_stays_readable(self):
        self.assertTrue(access_log._NAMES.match(
            'tacto-20261107T194956814759Z-07dc5f6f3a6c44299f8b27831373386e.jsonl'))
        self.assertTrue(access_log._NAMES.match(
            'haejo-20261109T102036920234Z-20f435ec2db94344914f9690c712016d.jsonl'))


if __name__ == '__main__':
    unittest.main()
