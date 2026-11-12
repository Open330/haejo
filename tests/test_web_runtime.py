"""Playwright and Chromium live outside the app and are fetched on request."""
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from haejo import web_runtime

ROOT = Path(__file__).resolve().parents[1]


def fake_run(playwright='1.70.0', pip_code=0, browser_code=0):
    calls = []

    def run(command, **kwargs):
        calls.append((command, kwargs))
        if 'install' in command and '--target' in command:
            site = Path(command[command.index('--target')+1])
            if pip_code == 0:
                (site/'playwright').mkdir(parents=True)
                (site/f'playwright-{playwright}.dist-info').mkdir()
            return subprocess.CompletedProcess(command, pip_code, '', 'no matching distribution')
        browsers = Path(kwargs['env']['PLAYWRIGHT_BROWSERS_PATH'])
        if browser_code == 0:
            (browsers/'chromium-1200').mkdir(parents=True)
        return subprocess.CompletedProcess(command, browser_code, '', 'download failed')
    run.calls = calls
    return run


class WebRuntime(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)/'Web'

    def test_nothing_installed_names_the_next_command(self):
        state = web_runtime.status(self.root)
        self.assertFalse(state['installed'])
        self.assertFalse(state['ready'])
        self.assertEqual('haejo web install', state['next'])
        self.assertIn('haejo web install', web_runtime.missing_message())

    def test_install_fetches_playwright_then_its_chromium_into_the_data_folder(self):
        run = fake_run()
        state = web_runtime.install(root=self.root, run=run, emit=lambda _: None)
        self.assertTrue(state['ready'], state)
        self.assertEqual('1.70.0', state['playwright'])
        self.assertEqual(['chromium-1200'], state['chromium'])
        pip, browser = run.calls
        self.assertEqual('playwright', pip[0][-1])
        self.assertIn(':all:', pip[0])
        self.assertEqual(['install', 'chromium'], browser[0][-2:])
        self.assertEqual(str(self.root/'browsers'), browser[1]['env']['PLAYWRIGHT_BROWSERS_PATH'])
        self.assertFalse((self.root/'site.new').exists())
        record = json.loads((self.root/'runtime.json').read_text())
        self.assertEqual(web_runtime.python_tag(), record['python'])

    def test_a_named_version_is_requested_exactly_and_a_malformed_one_starts_nothing(self):
        run = fake_run('1.60.0')
        web_runtime.install('1.60.0', root=self.root, run=run, emit=lambda _: None)
        self.assertEqual('playwright==1.60.0', run.calls[0][0][-1])
        refused = fake_run()
        reply = web_runtime.install('1.60; rm', root=self.root, run=refused, emit=lambda _: None)
        self.assertEqual('web_runtime_version_invalid', reply['error'])
        self.assertEqual([], refused.calls)

    def test_a_failed_upgrade_leaves_the_working_install_in_place(self):
        web_runtime.install(root=self.root, run=fake_run('1.60.0'), emit=lambda _: None)
        for failing in (fake_run('1.70.0', pip_code=1), fake_run('1.70.0', browser_code=1)):
            reply = web_runtime.install(root=self.root, run=failing, emit=lambda _: None)
            self.assertEqual('error', reply['type'])
            self.assertEqual('not_started', reply['effect'])
            state = web_runtime.status(self.root)
            self.assertTrue(state['ready'])
            self.assertEqual('1.60.0', state['playwright'])
            self.assertFalse((self.root/'site.new').exists())

    def test_an_install_for_another_python_asks_for_a_new_install(self):
        web_runtime.install(root=self.root, run=fake_run(), emit=lambda _: None)
        record = json.loads((self.root/'runtime.json').read_text())
        record['python'] = '3.11'
        (self.root/'runtime.json').write_text(json.dumps(record))
        state = web_runtime.status(self.root)
        self.assertFalse(state['ready'])
        self.assertIn('3.11', state['reason'])
        with mock.patch.object(importlib.util, 'find_spec', return_value=None):
            self.assertFalse(web_runtime.activate(self.root))

    def test_activate_adds_the_fetched_packages_after_what_haejo_ships(self):
        web_runtime.install(root=self.root, run=fake_run(), emit=lambda _: None)
        (self.root/'site/playwright/__init__.py').write_text('')
        before = list(sys.path)
        real = importlib.util.find_spec
        seen = []

        def find(name, *args):
            seen.append(name)
            return None if len(seen) == 1 else real(name, *args)
        try:
            with mock.patch.object(importlib.util, 'find_spec', side_effect=find), \
                 mock.patch.dict(web_runtime.os.environ, {}, clear=False), \
                 mock.patch.dict(sys.modules):
                sys.modules.pop('playwright', None)
                if real('playwright') is None:
                    self.assertTrue(web_runtime.activate(self.root))
                else:
                    web_runtime.activate(self.root)
                self.assertEqual(str(self.root/'site'), sys.path[-1])
                self.assertEqual(before, sys.path[:-1])
                self.assertEqual(str(self.root/'browsers'), web_runtime.os.environ['PLAYWRIGHT_BROWSERS_PATH'])
        finally:
            sys.path[:] = before

    def test_remove_deletes_only_the_web_folder(self):
        web_runtime.install(root=self.root, run=fake_run(), emit=lambda _: None)
        (self.root.parent/'Logs').mkdir()
        self.assertTrue(web_runtime.remove(self.root)['removed'])
        self.assertFalse(self.root.exists())
        self.assertTrue((self.root.parent/'Logs').is_dir())
        self.assertFalse(web_runtime.remove(self.root)['removed'])

    def test_the_app_is_built_without_playwright(self):
        spec = importlib.util.spec_from_file_location('distribution_for_web', ROOT/'setup/build_distribution.py')
        sys.path.insert(0, str(ROOT/'setup'))
        try:
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
        finally:
            sys.path.remove(str(ROOT/'setup'))
        self.assertEqual(('native-visual', 'web-bridge'), module.RELEASE_EXTRA_NAMES)
        self.assertNotIn('web', module.RELEASE_EXTRA_NAMES)
        self.assertNotIn('all-extras', (ROOT/'setup/build_distribution.py').read_text())


if __name__ == '__main__':
    unittest.main()
