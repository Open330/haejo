"""The person's Safari, in the background: read a tab that is not selected and fill with page events.

Opt-in: HAEJO_RUN_NATIVE_PAGE_SCRIPT_TESTS=1. Skips, naming the switch, when
Safari's "Allow JavaScript from Apple Events" or the host's Automation
permission is off. HAEJO_PAGE_SCRIPT_TEST_PORT picks the fixture port.
"""
import json, os, subprocess, sys, threading, time, unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from uuid import uuid4
try:
    from tests._safari import close_origin
except ImportError:  # discovered with tests/ as the top level
    from _safari import close_origin
ROOT = Path(__file__).resolve().parents[1]
LAUNCHER = ROOT/'launcher/haejo'

FORM = b'''<!doctype html><title>Haejo page script form</title><h1>form page</h1>
<input id="name" aria-label="Name"><input id="pw" type="password" value="kept-secret"><output id="seen"></output>
<script>
// A controlled field: only an input event updates the state the page submits.
var state = '', inputs = 0, changes = 0, field = document.getElementById('name');
field.addEventListener('input', function () { state = field.value; inputs++; document.getElementById('seen').textContent = state; });
field.addEventListener('change', function () { changes++; });
function report() { var r = new XMLHttpRequest(); r.open('GET', '/proof?state=' + encodeURIComponent(state) + '&inputs=' + inputs + '&changes=' + changes); r.send(); }
</script>'''
OTHER = b'<!doctype html><title>Haejo page script other</title><p id="note">text-of-the-tab-behind</p>'


class Page(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_GET(self):
        if self.path.startswith('/proof?'):
            self.server.proof = parse_qs(urlparse(self.path).query)
            self.send_response(204); self.end_headers(); return
        self.send_response(200)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        # A strict page policy, as signed-in sites have: the route still reads and fills.
        self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self' 'unsafe-inline'")
        self.end_headers()
        self.wfile.write(OTHER if self.path.startswith('/other') else FORM)


# Adds a tab to the one window whose first tab shows the given address, and
# keeps that first tab selected.
ADD_TAB = '''on run argv
  tell application "Safari"
    repeat with w in windows
      try
        if (URL of tab 1 of w) is (item 1 of argv) then
          tell w to make new tab with properties {URL:item 2 of argv}
          set current tab of w to tab 1 of w
          return (index of current tab of w) as text
        end if
      end try
    end repeat
    return "no window"
  end tell
end run'''


def osa(script, *args):
    return subprocess.run(['osascript', '-e', script, *args], capture_output=True, text=True, timeout=20)


def front_app():
    return osa('tell application "System Events" to get bundle identifier of first process whose frontmost is true').stdout.strip()


@unittest.skipUnless(sys.platform == 'darwin' and os.environ.get('HAEJO_RUN_NATIVE_PAGE_SCRIPT_TESTS') == '1',
                     'opt-in native Safari page script (HAEJO_RUN_NATIVE_PAGE_SCRIPT_TESTS=1)')
class SafariPageScriptNative(unittest.TestCase):
    def page(self, *args):
        done = subprocess.run([str(LAUNCHER), 'page', *args], capture_output=True, text=True, timeout=60)
        try:
            return json.loads(done.stdout.strip().splitlines()[-1])
        except (ValueError, IndexError):
            self.fail(done.stdout + done.stderr)

    def loaded(self, url):
        deadline = time.monotonic() + 15
        while True:
            seen = self.page('eval', url, '--js', 'document.readyState')
            if seen.get('value') == 'complete':
                return
            self.assertLess(time.monotonic(), deadline, seen)
            time.sleep(.3)

    def test_reads_a_background_tab_and_fills_with_page_events(self):
        status = self.page('status')
        if not status.get('available'):
            self.skipTest(f"Safari page scripts are not on here: {status.get('reason')}; turn on: {status.get('turn_on')}")
        server = ThreadingHTTPServer(('127.0.0.1', int(os.environ.get('HAEJO_PAGE_SCRIPT_TEST_PORT', '0'))), Page)
        server.proof = {}
        threading.Thread(target=server.serve_forever, daemon=True).start()
        origin = f'http://127.0.0.1:{server.server_port}'
        case = uuid4().hex
        form, other = f'{origin}/?case={case}', f'{origin}/other?case={case}'
        before = front_app()
        try:
            # An own window behind everything, found again by its address rather
            # than by being in front; its first tab is made the selected one.
            osa('tell application "Safari" to make new document with properties {URL:"%s"}' % form)
            self.loaded(form)
            made = osa(ADD_TAB, form, other)
            self.assertEqual('1', made.stdout.strip(), made.stderr)
            self.loaded(form); self.loaded(other)

            hidden = self.page('eval', other, '--js', 'document.visibilityState')
            self.assertEqual('hidden', hidden.get('value'), hidden)
            text = self.page('text', other)
            self.assertEqual(('page_text', other, 'page_data'), (text.get('type'), text.get('url'), text.get('content')), text)
            self.assertIn('text-of-the-tab-behind', text['text'])
            self.assertEqual('te', self.page('text', other, '--selector', '#note', '--max-chars', '2').get('text'))

            value = 'Haejo "quoted" \\ 한글 </script>'
            filled = self.page('fill', form, '--selector', '#name', '--value', value)
            self.assertEqual({'type': 'page_filled', 'url': form, 'filled': True, 'events': ['input', 'change']}, filled)
            self.assertIsNone(self.page('eval', form, '--js', 'report()').get('value'))
            deadline = time.monotonic() + 5
            while not server.proof:
                self.assertLess(time.monotonic(), deadline); time.sleep(.05)
            held = value
            self.assertEqual(([held], ['1'], ['1']), tuple(server.proof.get(k) for k in ('state', 'inputs', 'changes')))

            values = self.page('value', form, '--selector', 'input, output')
            self.assertEqual(3, values.get('matched'), values)
            self.assertEqual([held, None, held], [item['value'] for item in values['values']])
            self.assertNotIn('kept-secret', json.dumps(values))

            # A single-line field drops a line break: the route reports what the field holds.
            self.assertEqual('fill_not_held', self.page('fill', form, '--selector', '#name', '--value', 'a\nb').get('error'))
            self.assertEqual('field_not_unique', self.page('fill', form, '--selector', 'input', '--value', 'x').get('error'))
            self.assertEqual('page_not_found', self.page('text', f'{origin}/absent').get('error'))
            self.assertEqual('script_error', self.page('eval', form, '--js', 'not js (').get('error'))
            self.assertEqual('script_error', self.page('eval', form, '--js', 'missing.name').get('error'))
            large = self.page('eval', form, '--js', 'Array(5000).fill("ab")', '--max-chars', '1000')
            self.assertEqual('result_too_large', large.get('error'), large)

            # A second tab on the same address: the route asks for a unique page instead of guessing.
            self.assertEqual('1', osa(ADD_TAB, form, other).stdout.strip())
            deadline = time.monotonic() + 10
            while True:
                twin = self.page('text', other)
                if twin.get('error') == 'page_ambiguous':
                    break
                self.assertLess(time.monotonic(), deadline, twin); time.sleep(.3)
            self.assertEqual(2, twin.get('tabs'))
            self.assertEqual(before, front_app(), 'the app in front changed')
        finally:
            close_origin(origin)
            server.shutdown(); server.server_close()


if __name__ == '__main__':
    unittest.main()
