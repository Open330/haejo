"""Exact browser receiving proof, not canonical-equivalence password matching."""
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
import unicodedata
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(sys.platform == 'darwin' and os.environ.get('TACTO_RUN_NATIVE_CREDENTIAL_TESTS') == '1',
                     'opt-in owned Safari Unicode credential receiving')
class CredentialUnicodeNative(unittest.TestCase):
    def test_nfc_nfd_replacement_input_events_and_clipboard(self):
        from AppKit import NSPasteboard

        def clipboard():
            return [[(str(t), bytes(item.dataForType_(t))) for t in item.types()]
                    for item in NSPasteboard.generalPasteboard().pasteboardItems() or []]

        class Page(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_GET(self):
                if self.path.startswith('/proof?'):
                    proof = parse_qs(urlparse(self.path).query)
                    if proof.get('case') == [self.server.title]:
                        self.server.proof = proof
                    self.send_response(204)
                    self.end_headers()
                    return
                self.send_response(200)
                self.send_header('Content-Type', 'text/html; charset=utf-8')
                self.end_headers()
                # Values are synthetic; only equality booleans leave this page.
                html = ('<title>' + self.server.title + '</title>'
                        '<input type="' + self.server.kind + '" aria-label="Owned Unicode input" id="p">'
                        '<input aria-label="Other owned input" id="other">'
                        '<script>const expected=' + json.dumps(self.server.expected) + ';'
                        'const interrupt=' + json.dumps(self.server.interrupt) + ';'
                        'const p=document.getElementById("p");let state="",events=0;'
                        'p.addEventListener("input",()=>{state=p.value;events++;if(interrupt)document.getElementById("other").focus()});'
                        'setInterval(()=>fetch("/proof?exact="+(p.value===expected)'
                        '+"&state="+(state===expected)+"&events="+events+"&other_empty="+(document.getElementById("other").value==="")+"&case="+encodeURIComponent(document.title)),50)</script>')
                self.wfile.write(html.encode())

        server = ThreadingHTTPServer(('127.0.0.1', 0), Page)
        server.interrupt = False
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()

        def command(*args):
            return subprocess.run([str(ROOT / 'launcher/tacto'), *args], capture_output=True,
                                  text=True, timeout=40, env=dict(os.environ, TACTO_HELPER_MODE='warm'))

        try:
            values = ['Tacto-테스트🔐-47!', unicodedata.normalize('NFD', 'Tacto-테스트🔐-47!'),
                      'Accent-e\u0301-a\u0315\u0300-{\\}-47!',
                      'x' * 63 + '🔐' + 'e\u0301' * 100]
            for kind in ('password', 'text'):
                for value in values:
                    with self.subTest(kind=kind, form='NFC' if unicodedata.is_normalized('NFC', value) else 'decomposed'):
                        server.expected = value
                        server.title = 'Tacto owned Unicode ' + uuid4().hex
                        server.kind = kind
                        server.proof = {}
                        opened = command('open-url', f'http://127.0.0.1:{server.server_port}/?case={uuid4().hex}', '--helper')
                        self.assertEqual(0, opened.returncode, opened.stdout + opened.stderr)
                        before = clipboard()
                        with tempfile.TemporaryDirectory() as directory:
                            flow = Path(directory) / 'flow.json'
                            trace = Path(directory) / 'trace.json'
                            step = {'action': 'set_value',
                                    'selector': {'role': 'TextField', 'title': 'Owned Unicode input', 'ancestor': server.title},
                                    'params': {'value': value, 'input_method': 'paste'},
                                    'safety': {'effects': ['credential'], 'reversibility': 'reversible', 'resource': {'scope': 'entry'}},
                                    'unverified_ok': True}
                            flow.write_text(json.dumps({'name': 'owned Unicode input', 'target': 'com.apple.Safari', 'steps': [step, step]}))
                            flow.chmod(0o600)
                            result = command('run', str(flow), '--helper', '--yes', '--trace', str(trace))
                            self.assertEqual(0, result.returncode, result.stdout + result.stderr)
                            deadline = time.monotonic() + 3
                            # Unicode input is chunked into <=64 UTF-16 units.
                            chunks, units = 1, 0
                            for scalar in value:
                                width = 2 if ord(scalar) > 0xffff else 1
                                if units + width > 64:
                                    chunks += 1
                                    units = 0
                                units += width
                            expected_events = 2 if unicodedata.is_normalized('NFC', value) else 2 * chunks
                            while server.proof.get('events') != [str(expected_events)]:
                                self.assertLess(time.monotonic(), deadline, str(server.proof))
                                time.sleep(.05)
                            self.assertEqual(['true'], server.proof.get('exact'))
                            self.assertEqual(['true'], server.proof.get('state'))
                            self.assertEqual(before, clipboard())
                            self.assertNotIn(value, result.stdout + result.stderr + trace.read_text())
                            if kind == 'password' and value == values[1]:
                                from tacto.credential_grants import CredentialStore
                                from tacto.credential_vault import KeychainVault
                                name = 'owned-unicode-' + uuid4().hex
                                store, vault = CredentialStore(), KeychainVault()
                                try:
                                    vault.put(name, value)
                                    store.add_vault(name, {'kind': 'keychain'})
                                    store.grant(name, {'target': 'com.apple.Safari',
                                                      'origin': f'http://127.0.0.1:{server.server_port}', 'level': 'fill',
                                                      'fields': [{'name': 'password', 'selector': step['selector'],
                                                                  'secret': {'vault': name, 'item': name, 'field': 'password'},
                                                                  'input_method': 'paste'}]})
                                    filled = command('auth', 'fill', name, '--helper')
                                    self.assertEqual(0, filled.returncode, filled.stdout + filled.stderr)
                                    self.assertNotIn(value, filled.stdout + filled.stderr)
                                    deadline = time.monotonic() + 3
                                    while server.proof.get('events') != [str(3 * chunks)]:
                                        self.assertLess(time.monotonic(), deadline, str(server.proof))
                                        time.sleep(.05)
                                    self.assertEqual(['true'], server.proof.get('exact'))
                                    self.assertEqual(['true'], server.proof.get('state'))
                                    self.assertEqual(before, clipboard())
                                finally:
                                    store.revoke(name)
                                    store._path('vault', name).unlink(missing_ok=True)
                                    vault.delete(name)
            # A real website moves focus after the first chunk. Do not send
            # remaining secret text into the second field or retry the operation.
            server.interrupt = True
            server.expected = values[-1]
            server.kind = 'password'
            server.title = 'Tacto owned interrupted Unicode ' + uuid4().hex
            server.proof = {}
            opened = command('open-url', f'http://127.0.0.1:{server.server_port}/?case={uuid4().hex}', '--helper')
            self.assertEqual(0, opened.returncode, opened.stdout + opened.stderr)
            before = clipboard()
            with tempfile.TemporaryDirectory() as directory:
                flow = Path(directory) / 'interrupted.json'
                step['selector']['ancestor'] = server.title
                flow.write_text(json.dumps({'name': 'owned interrupted Unicode', 'target': 'com.apple.Safari', 'steps': [step, step]}))
                flow.chmod(0o600)
                result = command('run', str(flow), '--helper', '--yes')
                self.assertNotEqual(0, result.returncode)
                self.assertIn('unicode_input_interrupted', result.stdout)
                self.assertIn('unknown', result.stdout)
                self.assertNotIn(server.expected, result.stdout + result.stderr)
                deadline = time.monotonic() + 3
                while server.proof.get('events') != ['1']:
                    self.assertLess(time.monotonic(), deadline, str(server.proof))
                    time.sleep(.05)
                self.assertEqual(['true'], server.proof.get('other_empty'))
                self.assertEqual(['false'], server.proof.get('exact'))
                self.assertEqual(before, clipboard())
        finally:
            server.shutdown()
            server.server_close()
            thread.join()
