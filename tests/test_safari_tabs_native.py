"""Opt-in: list and select real Safari tabs through the signed launcher/helper.

HAEJO_RUN_NATIVE_SAFARI_TAB_TESTS=1 python -m unittest tests.test_safari_tabs_native -v
(HAEJO_TEST_PORT picks the fixture port). The test works in a Safari window of
its own and closes its tabs afterwards.
"""
import json
import os
import subprocess
import sys
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from uuid import uuid4

try:
    from tests._safari import close_origin, current_tab, open_window, running as safari_running
except ImportError:  # discovered with tests/ as the top level
    from _safari import close_origin, current_tab, open_window, running as safari_running

ROOT = Path(__file__).resolve().parents[1]
LAUNCHER = ROOT / 'launcher/haejo'
SAFARI = 'com.apple.Safari'
BUSY = ('target_busy', 'input_busy', 'window_list_unavailable')


def front_app():
    out = subprocess.run(['osascript', '-e', 'tell application "System Events" to get bundle identifier '
                          'of first process whose frontmost is true'], capture_output=True, text=True, timeout=20)
    return out.stdout.strip()


@unittest.skipUnless(sys.platform == 'darwin' and os.environ.get('HAEJO_RUN_NATIVE_SAFARI_TAB_TESTS') == '1',
                     'opt-in signed Safari tab test')
class SafariTabsNative(unittest.TestCase):
    def haejo(self, *args):
        for _ in range(6):
            out = subprocess.run([str(LAUNCHER), *args], capture_output=True, text=True, timeout=60,
                                 env=dict(os.environ, HAEJO_HELPER_MODE='warm'))
            if not any(code in out.stdout for code in BUSY):
                break
            time.sleep(3)
        return out

    def test_tabs_are_listed_and_a_background_tab_is_selected_behind_the_app_in_use(self):
        token = uuid4().hex[:8]

        class Page(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_GET(self):
                name = self.path.strip('/').removesuffix('.html')
                self.send_response(200)
                self.send_header('Content-Type', 'text/html')
                self.end_headers()
                self.wfile.write(f'<!doctype html><title>Haejo {name}</title><h1>Page {name}</h1>'.encode())

        server = ThreadingHTTPServer(('127.0.0.1', int(os.environ.get('HAEJO_TEST_PORT', '0'))), Page)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        origin = f'http://127.0.0.1:{server.server_port}'
        names = [f'tab-{token}-{letter}' for letter in 'abc']
        started_safari = not safari_running()
        try:
            window_id = open_window([f'{origin}/{name}.html' for name in names])
            self.assertGreater(window_id, 0)
            before = front_app()
            deadline = time.monotonic() + 15
            while True:
                listed = self.haejo('windows', SAFARI, '--helper')
                rows = [row for row in json.loads(listed.stdout).get('windows', [])
                        if any(token in tab['title'] for tab in row.get('tabs', []))]
                # A tab just opened is "Untitled" until Safari names it.
                if rows and len(rows[0]['tabs']) == 3 and all(token in tab['title'] for tab in rows[0]['tabs']):
                    break
                self.assertLess(time.monotonic(), deadline, listed.stdout)
                time.sleep(0.5)
            self.assertEqual(1, len(rows), 'the three tabs are in one window')
            tabs = rows[0]['tabs']
            self.assertEqual([0, 1, 2], [tab['index'] for tab in tabs])
            self.assertEqual([True, False, False], [tab['selected'] for tab in tabs])
            self.assertEqual(f'{origin}/{names[0]}.html', tabs[0]['url'])
            self.assertFalse(any('url' in tab for tab in tabs[1:]), 'a background tab has a title and no address')
            for tab, name in zip(tabs, names):
                self.assertIn(name, tab['title'])

            chosen = self.haejo('observe', SAFARI, '--window-match', f'tab={names[2]}', '--helper', '--json')
            self.assertEqual(0, chosen.returncode, chosen.stdout + chosen.stderr)
            note = [line for line in chosen.stderr.splitlines() if line.startswith('HAEJO_TAB_SELECTED ')]
            self.assertEqual(1, len(note), chosen.stderr)
            selected = json.loads(note[0].split(' ', 1)[1])
            self.assertEqual((2, 'ax_press', f'{origin}/{names[2]}.html'),
                             (selected['index'], selected['route'], selected['url']))
            self.assertNotIn('front_taken', selected)
            tree = json.loads(chosen.stdout)['tree']
            self.assertIn(f'URL: "{origin}/{names[2]}.html"', tree)
            self.assertIn(f'Page {names[2]}', tree)
            self.assertEqual(3, current_tab(window_id), 'Safari itself shows the third tab')

            again = self.haejo('observe', SAFARI, '--window-match', f'tab={names[2]}', '--helper', '--json')
            self.assertEqual(0, again.returncode, again.stdout[:2000] + again.stderr)
            self.assertIn('"route": "already_selected"', again.stderr)
            after = self.haejo('windows', SAFARI, '--helper')
            mine = [row for row in json.loads(after.stdout)['windows'] if row['window_id'] == rows[0]['window_id']][0]
            self.assertEqual([False, False, True], [tab['selected'] for tab in mine['tabs']])
            self.assertEqual(f'{origin}/{names[2]}.html', mine['tabs'][2]['url'])
            front = front_app()
            if before != SAFARI:
                self.assertNotEqual(SAFARI, front, 'Safari stayed behind the app in use')
            print(f'Safari tab {names[2]} selected by AXPress in window {rows[0]["window_id"]}; front app {front}', flush=True)
        finally:
            close_origin(origin, quit_if_idle=started_safari)
            server.shutdown()
            server.server_close()


if __name__ == '__main__':
    unittest.main()
