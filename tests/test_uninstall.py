"""`haejo uninstall` removes exactly what this installation made, into the Trash."""
import os, tempfile, unittest
from pathlib import Path
from unittest import mock
from haejo import uninstall


class UninstallTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.home = Path(self.tmp.name)/'home'; self.home.mkdir()
        apps = Path(self.tmp.name)/'Applications'; apps.mkdir()
        self.app = apps/'Haejo.app'
        (self.app/'Contents/Resources/runtime/launcher').mkdir(parents=True)
        (self.app/'Contents/Resources/runtime/skill').mkdir()
        (self.app/'Contents/Info.plist').write_text('<plist/>')
        (self.app/'Contents/Resources/runtime/launcher/haejo').write_text('')
        self.runtime = self.app/'Contents/Resources/runtime/haejo'; self.runtime.mkdir()
        for folder in ('.local/bin', '.claude/skills', '.codex/skills', '.agents/skills'):
            (self.home/folder).mkdir(parents=True)
        os.symlink(self.app/'Contents/Resources/runtime/launcher/haejo', self.home/'.local/bin/haejo')
        for f in ('.claude/skills', '.agents/skills'):
            os.symlink(self.app/'Contents/Resources/runtime/skill', self.home/f/'haejo')
        other = Path(self.tmp.name)/'checkout/skill'; other.mkdir(parents=True)
        os.symlink(other, self.home/'.codex/skills/haejo')  # another installation's link
        (self.home/'Library/Application Support/Haejo/Logs').mkdir(parents=True)
        (self.home/'.local/share/haejo/flows').mkdir(parents=True)
        self.env = mock.patch.dict(os.environ, {}, clear=False)
        for k in ('HAEJO_BIN_DIR', 'CLAUDE_CONFIG_DIR', 'CODEX_HOME'):
            os.environ.pop(k, None)

    def tearDown(self):
        self.tmp.cleanup()

    def run_main(self, *args):
        with mock.patch.object(uninstall.Path, 'home', return_value=self.home), \
             mock.patch.object(uninstall, '__file__', str(self.runtime/'uninstall.py')), \
             mock.patch.object(uninstall, 'stop_processes', return_value=[]):
            return uninstall.main(['--yes', *args])

    def test_removes_only_own_links_and_trashes_the_app_keeping_data(self):
        self.assertEqual(0, self.run_main())
        self.assertFalse((self.home/'.local/bin/haejo').is_symlink())
        self.assertFalse((self.home/'.claude/skills/haejo').is_symlink())
        self.assertTrue((self.home/'.codex/skills/haejo').is_symlink(), "another installation's link stays")
        self.assertFalse(self.app.exists())
        self.assertTrue((self.home/'.Trash/Haejo.app/Contents/Info.plist').exists())
        self.assertTrue((self.home/'Library/Application Support/Haejo').exists())
        self.assertTrue((self.home/'.local/share/haejo').exists())

    def test_remove_data_moves_history_and_flows_to_the_trash(self):
        self.assertEqual(0, self.run_main('--remove-data'))
        self.assertFalse((self.home/'Library/Application Support/Haejo').exists())
        self.assertTrue((self.home/'.Trash/Haejo 실행 기록·설정/Logs').exists())
        self.assertTrue((self.home/'.Trash/Haejo Flow/flows').exists())

    def test_trash_never_overwrites(self):
        (self.home/'.Trash').mkdir(); (self.home/'.Trash/Haejo.app').mkdir()
        self.assertEqual(0, self.run_main())
        self.assertTrue((self.home/'.Trash/Haejo 2.app/Contents/Info.plist').exists())

    def test_without_yes_and_no_terminal_nothing_changes(self):
        with mock.patch.object(uninstall.Path, 'home', return_value=self.home), \
             mock.patch.object(uninstall, '__file__', str(self.runtime/'uninstall.py')), \
             mock.patch('sys.stdin.isatty', return_value=False):
            self.assertEqual(3, uninstall.main([]))
        self.assertTrue(self.app.exists()); self.assertTrue((self.home/'.local/bin/haejo').is_symlink())

    def test_own_process_chain_is_never_stopped(self):
        self.assertEqual({5, 3, 2}, uninstall.ancestors(5, {5: 3, 3: 2, 2: 1}))


if __name__ == '__main__':
    unittest.main()
