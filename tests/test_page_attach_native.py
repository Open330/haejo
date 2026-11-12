"""Owned form in the person's Safari: registered files reach the server byte for byte.

Opt-in (`HAEJO_RUN_NATIVE_ATTACH_TESTS=1`): it opens its own Safari window on
a local fixture, attaches files it created through `attach_files`, submits the
form and compares what the fixture server received with the registered
SHA-256. Two files sit in a folder the open panel lists (the accessibility
route), two in a hidden folder of the home folder (Go to Folder).
"""
import email.parser
import email.policy
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from uuid import uuid4

try:
    from tests._safari import close_origin, running as safari_running
except ImportError:  # discovered with tests/ as the top level
    from _safari import close_origin, running as safari_running

ROOT = Path(__file__).resolve().parents[1]
LAUNCHER = ROOT / 'launcher/haejo'

PAGE = '''<!doctype html><html><head><meta charset="utf-8"><title>TITLE</title></head><body>
<h1>TITLE</h1>
<form method="post" action="/upload" enctype="multipart/form-data">
<p><input type="file" id="single" name="single" aria-label="Single file"></p>
<p><input type="file" id="multi" name="multi" multiple aria-label="Many files"></p>
<p><input type="file" id="hidden" name="hidden" style="display:none">
<button type="button" onclick="document.getElementById('hidden').click()">Attach document</button></p>
<p id="status">nothing attached</p>
<p><button type="submit">Continue</button></p>
</form>
<script>
const names = {};
for (const id of ['single', 'multi', 'hidden']) {
  document.getElementById(id).addEventListener('change', e => {
    names[id] = [...e.target.files].map(f => f.name).join('+');
    document.getElementById('status').textContent =
      ['single', 'multi', 'hidden'].filter(k => names[k]).map(k => k + '=' + names[k]).join(' ');
  });
}
</script></body></html>'''


class Fixture(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def reply(self, body):
        data = body.encode()
        self.send_response(200)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        self.reply(PAGE.replace('TITLE', self.server.title))

    def do_POST(self):
        raw = self.rfile.read(int(self.headers['Content-Length']))
        message = email.parser.BytesParser(policy=email.policy.HTTP).parsebytes(
            b'Content-Type: ' + self.headers['Content-Type'].encode() + b'\r\n\r\n' + raw)
        received = []
        for part in message.iter_parts():
            if part.get_filename():
                data = part.get_payload(decode=True) or b''
                received.append((part.get_param('name', header='content-disposition'), part.get_filename(),
                                 hashlib.sha256(data).hexdigest(), len(data)))
        self.server.received.append(received)
        self.reply('<title>Received</title><p>Received %d files</p>' % len(received))


def fixture_server():
    for port in (*range(8831, 8840), 0):
        try:
            return ThreadingHTTPServer(('127.0.0.1', port), Fixture)
        except OSError:
            continue
    raise AssertionError('no local port for the fixture')


def front_app():
    return subprocess.run(['osascript', '-e', 'tell application "System Events" to get bundle identifier '
                           'of first process whose frontmost is true'], capture_output=True, text=True,
                          timeout=20).stdout.strip()


@unittest.skipUnless(sys.platform == 'darwin' and os.environ.get('HAEJO_RUN_NATIVE_ATTACH_TESTS') == '1',
                     'opt-in native Safari file attachment')
class PageAttachNative(unittest.TestCase):
    def command(self, *args, timeout=180):
        return subprocess.run([str(LAUNCHER), *args], capture_output=True, text=True, timeout=timeout,
                              env=dict(os.environ, HAEJO_HELPER_MODE='warm'))

    def test_registered_files_reach_the_server_with_their_exact_bytes(self):
        tag = uuid4().hex[:8]
        server = fixture_server()
        server.title = 'Haejo attach fixture ' + tag
        server.received = []
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        origin = f'http://127.0.0.1:{server.server_port}'
        started_safari = not safari_running()
        # A folder the open panel lists and a hidden one, so both ways of
        # reaching a file run. Not the temporary folder: Go to Folder into a
        # folder with tens of thousands of siblings loads for minutes.
        shown = Path.home() / f'haejo-attach-test-{tag}'
        hidden = Path.home() / f'.haejo-attach-test-{tag}'
        work = Path(tempfile.mkdtemp(prefix='haejo-attach-'))
        scopes = {name: f'attach_test_{tag}_{name}' for name in ('one', 'two', 'styled')}
        front_before = front_app()
        try:
            shown.mkdir()
            hidden.mkdir()
            contents = {'cv.txt': b'cv ' + os.urandom(24), 'photo-1.bin': os.urandom(4096),
                        'photo-2.bin': os.urandom(70000), 'letter.txt': b'letter ' + os.urandom(24)}
            (shown / 'cv.txt').write_bytes(contents['cv.txt'])
            (shown / 'letter.txt').write_bytes(contents['letter.txt'])
            (hidden / 'photo-1.bin').write_bytes(contents['photo-1.bin'])
            (hidden / 'photo-2.bin').write_bytes(contents['photo-2.bin'])
            digest = {name: hashlib.sha256(data).hexdigest() for name, data in contents.items()}
            for scope, paths in ((scopes['one'], [shown / 'cv.txt']),
                                 (scopes['two'], [hidden / 'photo-1.bin', hidden / 'photo-2.bin']),
                                 (scopes['styled'], [shown / 'letter.txt'])):
                registered = self.command('attach', scope, *map(str, paths))
                self.assertEqual(registered.returncode, 0, registered.stdout + registered.stderr)
                self.assertEqual([f['sha256'] for f in json.loads(registered.stdout)['files']],
                                 [digest[p.name] for p in paths])

            if started_safari:
                opened = self.command('open-url', origin + '/', '--browser', 'com.apple.Safari', '--helper')
                self.assertEqual(opened.returncode, 0, opened.stdout + opened.stderr)
            else:
                # Its own window, made without bringing Safari forward, so the
                # open panel's sheet hangs on a window nothing else is using.
                subprocess.run(['osascript', '-e', 'tell application "Safari" to make new document '
                                f'with properties {{URL:"{origin}/"}}'], check=True, capture_output=True, timeout=30)
            listed = {}
            deadline = time.monotonic() + 30
            while time.monotonic() < deadline:
                listed = json.loads(self.command('windows', 'com.apple.Safari', '--helper').stdout or '{}')
                if any(origin in (w.get('url') or '') for w in listed.get('windows', [])):
                    break
                time.sleep(1)
            self.assertTrue(any(origin in (w.get('url') or '') for w in listed.get('windows', [])), listed)

            def status(text):
                return {'field': {'role': 'StaticText', 'value': text}, 'attribute': 'Value', 'equals': text}
            flow = {'schema': 5, 'name': 'attach fixture files', 'target': 'com.apple.Safari',
                    'window': {'url': origin},
                    'safety_defaults': {'effects': ['write_ephemeral'], 'reversibility': 'reversible',
                                        'resource': {'object_type': 'owned fixture form', 'scope': 'entry'}},
                    'steps': [
                        {'action': 'attach_files', 'selector': {'role': 'Button', 'desc': 'Single file'},
                         'params': {'scope': scopes['one']}, 'postcondition': status('single=cv.txt')},
                        {'action': 'attach_files', 'selector': {'role': 'Button', 'desc': 'Many files'},
                         'params': {'scope': scopes['two']},
                         'postcondition': status('single=cv.txt multi=photo-1.bin+photo-2.bin')},
                        {'action': 'attach_files', 'selector': {'role': 'Button', 'title': 'Attach document'},
                         'params': {'scope': scopes['styled']},
                         'postcondition': status('single=cv.txt multi=photo-1.bin+photo-2.bin hidden=letter.txt')},
                        {'action': 'click', 'selector': {'role': 'Button', 'title': 'Continue'},
                         'postcondition': status('Received 4 files')}]}
            flow_file = work / 'flow.json'
            flow_file.write_text(json.dumps(flow))
            # Bytes that changed after registration are refused before the
            # control is pressed; the registered bytes then go back in place.
            (shown / 'cv.txt').write_bytes(b'changed after registration')
            changed = self.command('run', str(flow_file), '--helper')
            self.assertNotEqual(changed.returncode, 0)
            self.assertIn('attachment_changed', changed.stdout)
            self.assertNotIn('HAEJO_ATTACH', changed.stdout)
            (shown / 'cv.txt').write_bytes(contents['cv.txt'])
            ran = None
            for _ in range(4):   # another session may hold Safari for a moment
                ran = self.command('run', str(flow_file), '--helper', timeout=300)
                if ran.returncode == 0 or not any(code in ran.stdout for code in (
                        'target_busy', 'input_busy', 'window_list_unavailable', 'window_scope_requires_app',
                        'open_panel_busy')):
                    break
                time.sleep(5)
            self.assertEqual(ran.returncode, 0, ran.stdout + ran.stderr)
            routes = [json.loads(line.split(' ', 1)[1]) for line in ran.stdout.splitlines()
                      if line.startswith('HAEJO_ATTACH ')]
            self.assertEqual(len(routes), 3, ran.stdout)
            for route in routes:
                self.assertIn(route['route'], ('ax_background', 'ax_brief_front', 'go_to_folder_front'))
                self.assertTrue(route['front_restored'], route)
                self.assertLess(route['front_seconds'], 6, route)
            self.assertIn(routes[0]['route'], ('ax_background', 'ax_brief_front'), routes)
            self.assertEqual(routes[0]['real_keys'], 0, routes)
            self.assertTrue(routes[0]['control_names_files'], routes)

            deadline = time.monotonic() + 10
            while not server.received and time.monotonic() < deadline:
                time.sleep(.1)
            self.assertEqual(len(server.received), 1, server.received)
            self.assertEqual(sorted(server.received[0]), sorted([
                ('single', 'cv.txt', digest['cv.txt'], len(contents['cv.txt'])),
                ('multi', 'photo-1.bin', digest['photo-1.bin'], 4096),
                ('multi', 'photo-2.bin', digest['photo-2.bin'], 70000),
                ('hidden', 'letter.txt', digest['letter.txt'], len(contents['letter.txt']))]))

            front_after = front_app()
            print(f'Native attach: 4 files received with registered SHA-256; routes '
                  f'{[r["route"] for r in routes]}, front seconds {[r["front_seconds"] for r in routes]}, '
                  f'real keys {[r["real_keys"] for r in routes]}; front app {front_before} -> {front_after}',
                  flush=True)
        finally:
            for scope in scopes.values():
                self.command('attach', '--forget', scope)
            close_origin(origin, quit_if_idle=started_safari)
            server.shutdown()
            server.server_close()
            thread.join()
            shutil.rmtree(shown, ignore_errors=True)
            shutil.rmtree(hidden, ignore_errors=True)
            shutil.rmtree(work, ignore_errors=True)


if __name__ == '__main__':
    unittest.main()
