"""Real Safari against an owned page: which route delivers each web action.

Every assertion is made on what the page RECEIVED (its own event reports and
collected form values, tests/fixtures/safari_matrix_server.py), together with
the route the run named. Safari stays behind the app in front for the whole
first class; the second class covers the two actions that need Safari in
front and checks that the front is given back.

    HAEJO_RUN_NATIVE_SAFARI_PAGE_TESTS=1 .venv/bin/python -B -m unittest tests.test_safari_page_native
    HAEJO_RUN_NATIVE_SAFARI_FRONT_TESTS=1   # additionally: the Safari-in-front class
    HAEJO_SAFARI_PAGE_PORTS=8811,8812       # optional fixed ports

The matrix these tests keep is docs/safari-capability-matrix.md.
"""
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from uuid import uuid4

try:
    from tests._safari import close_origin, running as safari_running
    from tests.fixtures.safari_matrix_server import MatrixServer
except ImportError:  # discovered with tests/ as the top level
    from _safari import close_origin, running as safari_running
    from fixtures.safari_matrix_server import MatrixServer

ROOT = Path(__file__).resolve().parents[1]
LAUNCHER = ROOT / 'launcher/haejo'
SAFARI = 'com.apple.Safari'
BUSY = ('target_busy', 'input_busy', 'window_list_unavailable', 'window_match_none', 'helper_busy')
PAGE_TESTS = sys.platform == 'darwin' and os.environ.get('HAEJO_RUN_NATIVE_SAFARI_PAGE_TESTS') == '1'
FRONT_TESTS = PAGE_TESTS and os.environ.get('HAEJO_RUN_NATIVE_SAFARI_FRONT_TESTS') == '1'


def front_app():
    out = subprocess.run(['osascript', '-e', 'tell application "System Events" to get bundle identifier '
                          'of first process whose frontmost is true'], capture_output=True, text=True, timeout=20)
    return out.stdout.strip()


def haejo(*args, timeout=90):
    return subprocess.run([str(LAUNCHER), *args], capture_output=True, text=True, timeout=timeout,
                          env=dict(os.environ, HAEJO_HELPER_MODE='warm'))


def field(role, **named):
    return {'role': role, **named}


def step(action, selector, params=None, **more):
    made = {'action': action, 'selector': selector}
    if params:
        made['params'] = params
    made.update(more)
    return made


def shows(selector, value):
    return {'field': selector, 'attribute': 'Value', 'equals': value}


class SafariPageCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        ports = [int(p) for p in os.environ.get('HAEJO_SAFARI_PAGE_PORTS', '0,0').split(',')]
        cls.started_safari = not safari_running()
        cls.server = MatrixServer(ports[0], ports[1], token=uuid4().hex[:10])
        cls.record = cls.server.record
        cls.origins = [cls.server.origin, f'http://127.0.0.1:{cls.server.cross_port}']

        def finish():
            for index, origin in enumerate(cls.origins):
                close_origin(origin, quit_if_idle=cls.started_safari and index == len(cls.origins) - 1)
            cls.server.close()
        cls.addClassCleanup(finish)

    def setUp(self):
        self.front_before = front_app()
        self.addCleanup(self.same_front)
        self.addCleanup(lambda: [close_origin(origin) for origin in self.origins])
        self.record.reset()

    def same_front(self):
        now = front_app()
        if now != self.front_before and self.front_before:
            subprocess.run(['osascript', '-e', f'tell application id "{self.front_before}" to activate'],
                           capture_output=True, timeout=20)
        self.assertEqual(self.front_before, now, 'the app in front changed during the test')

    def open(self, path):
        """Open a page of the fixture behind the app in front; returns the text that picks its window."""
        case = uuid4().hex[:12]
        url = f'{self.server.origin}{path}/{case}'
        for _ in range(5):
            opened = haejo('open-url', url, '--browser', SAFARI, '--helper')
            if opened.returncode == 0 or not any(code in opened.stdout + opened.stderr for code in BUSY):
                break
            time.sleep(3)
        self.assertIn('"front": false', opened.stdout)
        if opened.returncode != 0 and '"page_not_shown"' in opened.stdout:
            # Sent once and still loading (a busy browser): wait for the page itself.
            deadline = time.monotonic() + 45
            while time.monotonic() < deadline:
                listed = haejo('windows', SAFARI, '--helper').stdout
                try:
                    rows = json.loads(listed).get('windows', [])
                except ValueError:
                    rows = []
                if any(case in str(row.get('url')) and 'Haejo matrix' in str(row.get('title')) for row in rows):
                    break
                time.sleep(2)
            else:
                self.fail('the fixture page did not load: ' + opened.stdout)
        else:
            self.assertEqual(0, opened.returncode, opened.stdout + opened.stderr)
        return url.split('://', 1)[1]

    def run_steps(self, window, steps, expect_ok=True):
        """Replay `steps` in the window showing `window`; returns (output, routes)."""
        flow = {'schema': 5, 'name': 'safari page matrix', 'target': SAFARI, 'window': {'url': window},
                'safety_defaults': {'effects': ['write_ephemeral'], 'reversibility': 'reversible',
                                    'resource': {'object_type': 'fixture field', 'scope': 'entry'}},
                'steps': steps}
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'flow.json'
            path.write_text(json.dumps(flow))
            for _ in range(6):
                ran = haejo('run', str(path), '--helper', '--yes', timeout=180)
                output = ran.stdout + ran.stderr
                # Another Haejo client had the browser: nothing was sent, so run again.
                if ran.returncode != 0 and any(code in output for code in BUSY) and 'HAEJO_ROUTE' not in output:
                    time.sleep(3)
                    continue
                break
        routes = [json.loads(line[len('HAEJO_ROUTE '):]) for line in ran.stdout.splitlines()
                  if line.startswith('HAEJO_ROUTE ')]
        if expect_ok:
            self.assertEqual(0, ran.returncode, output)
        else:
            self.assertNotEqual(0, ran.returncode, output)
        return output, routes

    def received(self, element, kind, count=1, timeout=4):
        """The page's own reports of `kind` on `element`, waited for."""
        deadline = time.monotonic() + timeout
        while True:
            events = self.record.events(element, kind)
            if len(events) >= count or time.monotonic() >= deadline:
                break
            time.sleep(0.1)
        self.assertGreaterEqual(len(events), count, f'{element} {kind}: {self.record.snapshot()}')
        self.assertTrue(all(event.get('trusted') is True for event in events if 'trusted' in event), events)
        return events

    def collected(self, window):
        self.run_steps(window, [step('click', field('Button', title='Collect values'),
                                     postcondition=shows(field('StaticText', value='collected'), 'collected'))])
        deadline = time.monotonic() + 4
        while self.record.submitted() is None and time.monotonic() < deadline:
            time.sleep(0.1)
        self.assertIsNotNone(self.record.submitted(), self.record.snapshot())
        return self.record.submitted()

    def route(self, routes, index):
        found = [route for route in routes if route.get('step') == index and 'input_route' in route]
        self.assertEqual(1, len(found), routes)
        return found[0]


@unittest.skipUnless(PAGE_TESTS, 'opt-in real Safari page matrix (HAEJO_RUN_NATIVE_SAFARI_PAGE_TESTS=1)')
class SafariPageBehindTests(SafariPageCase):
    """L1 and L2: Safari stays behind the app in front."""

    def test_press_controls_through_accessibility(self):
        page = self.open('/p/basic')
        _, routes = self.run_steps(page, [
            step('click', field('Button', title='Press me'),
                 postcondition=shows(field('StaticText', value='presses:1'), 'presses:1')),
            step('click', field('CheckBox', title='Agree box'),
                 postcondition=shows(field('CheckBox', title='Agree box'), '1')),
            step('click', field('RadioButton', title='Color green'),
                 postcondition=shows(field('RadioButton', title='Color green'), '1')),
            step('click', field('ComboBox', title='City choice'),
                 postcondition=shows(field('StaticText', value='Seoul'), 'Seoul')),
            step('click', field('StaticText', value='Seoul'),
                 postcondition=shows(field('ComboBox', title='City choice'), 'Seoul')),
        ])
        self.assertEqual([], routes, 'plain accessibility presses name no further route')
        self.received('btn', 'click')
        self.assertIs(True, self.received('agree', 'change')[-1]['checked'])
        self.assertEqual('green', self.received('green', 'change')[-1]['value'])
        self.received('dd', 'open:click')
        self.assertEqual('Seoul', self.received('dd', 'pick:click')[-1]['value'])

    def test_text_lands_in_the_named_field_and_fires_input_events(self):
        page = self.open('/p/basic')
        values = {'Plain name': ('TextField', 'plain 값 one'), 'Notes area': ('TextArea', 'notes two'),
                  'Controlled field': ('TextField', 'ctl three'), 'Rich editor': ('TextArea', 'rich four')}
        _, routes = self.run_steps(page, [
            step('set_value', field(role, title=title), {'value': value},
                 postcondition=shows(field(role, title=title), value))
            for title, (role, value) in values.items()])
        for index in range(len(values)):
            route = self.route(routes, index)
            self.assertEqual(('ax_value_focused', 'L1'), (route['input_route'], route['route_level']))
        self.assertEqual('ctl three', self.received('ctl', 'input')[-1]['value'])
        self.assertEqual([], self.record.events('ctl', 'revert'), 'the controlled field kept its state')
        got = self.collected(page)
        self.assertEqual(('plain 값 one', 'notes two', 'ctl three', 'rich four'),
                         (got['plain'], got['notes'], got['ctl'], got['rich']))

    def test_key_driven_field_takes_typed_keys_behind_the_front_app(self):
        page = self.open('/p/basic')
        keys = field('TextField', title='Keydown field')
        _, routes = self.run_steps(page, [
            step('type_text', keys, {'text': 'Key 1'},
                 postcondition=shows(field('StaticText', value='keys:Key 1'), 'keys:Key 1'))])
        route = self.route(routes, 0)
        self.assertEqual(('window_keys', 'L2'), (route['input_route'], route['route_level']))
        self.assertEqual(['K', 'e', 'y', ' ', '1'], [e['key'] for e in self.received('keyonly', 'keydown', 5)])
        # A value write reaches the field and fires no key events: the page's
        # key-built state stays as typed.
        self.record.reset()
        self.run_steps(page, [step('set_value', keys, {'value': 'written'}, postcondition=shows(keys, 'written'))])
        self.assertEqual([], self.record.events('keyonly', 'keydown'))
        self.assertEqual('Key 1', self.collected(page)['keys'])

    def test_native_select_is_chosen_from_its_own_menu(self):
        page = self.open('/p/basic')
        fruit = field('PopUpButton', title='Fruit choice')
        _, routes = self.run_steps(page, [
            step('select_option', fruit, {'option_label': 'Banana'}, postcondition=shows(fruit, 'Banana'))])
        route = self.route(routes, 0)
        self.assertEqual(('web_popup_menu', 'L1'), (route['input_route'], route['route_level']))
        self.assertEqual('Banana', self.received('fruit', 'change')[-1]['value'])
        _, routes = self.run_steps(page, [
            step('set_value', fruit, {'value': 'Cherry'}, postcondition=shows(fruit, 'Cherry'))])
        self.assertEqual('web_popup_menu', self.route(routes, 0)['input_route'])
        self.assertEqual('Cherry', self.received('fruit', 'change', 2)[-1]['value'])
        # A label the menu does not have: the menu is closed again and the options are named.
        missing, _ = self.run_steps(page, [
            step('select_option', fruit, {'option_label': 'Durian'}, postcondition=shows(fruit, 'Durian'))],
            expect_ok=False)
        self.assertIn("'menu_left_open': False", missing)
        self.assertIn("'Apple', 'Banana', 'Cherry'", missing)
        # Pressing it would only leave its menu open on screen.
        pressed, _ = self.run_steps(page, [step('click', fruit, unverified_ok=True)], expect_ok=False)
        self.assertIn('use_select_option', pressed)
        self.assertEqual('Cherry', self.collected(page)['fruit'])

    def test_date_field_takes_a_date_through_its_picker(self):
        page = self.open('/p/basic')
        _, routes = self.run_steps(page, [
            step('set_value', field('DateTimeArea', title='Day field'), {'value': '2027-03-15'},
                 unverified_ok=True)])
        self.assertEqual('web_date_picker', self.route(routes, 0)['input_route'])
        self.assertEqual('2027-03-15', self.received('day', 'change')[-1]['value'])
        self.assertEqual('2027-03-15', self.collected(page)['day'])

    def test_waiting_alert_and_new_windows(self):
        page = self.open('/p/basic')
        self.run_steps(page, [
            step('click', field('Button', title='Load later'), unverified_ok=True),
            {'action': 'wait_until', 'until': {'contains': 'late-text-arrived'}, 'timeout_s': 15, 'poll_s': 1},
            step('click', field('Button', title='Show alert'),
                 postcondition={'contains': 'matrix alert text'}),
            step('click', field('Button', title='Close', ancestor='AXSafariModalDialog'),
                 postcondition=shows(field('StaticText', value='late-text-arrived'), 'late-text-arrived')),
        ])
        self.received('dl', 'click')
        self.received('al', 'alert-open')
        self.received('al', 'alert-closed')
        self.run_steps(page, [step('click', field('Button', title='Open by script'), unverified_ok=True)])
        self.assertIs(True, self.received('wo', 'window-open')[-1]['opened'])
        deadline = time.monotonic() + 5
        while not self.record.visits('/popup') and time.monotonic() < deadline:
            time.sleep(0.1)
        self.assertEqual('by=script', self.record.visits('/popup')[-1]['query'])

    def test_links_open_their_pages(self):
        page = self.open('/p/basic')
        self.run_steps(page, [step('click', field('Link', title='Open new window'), unverified_ok=True)])
        self.received('nw', 'click')
        deadline = time.monotonic() + 5
        while not self.record.visits('/popup') and time.monotonic() < deadline:
            time.sleep(0.1)
        self.assertEqual('by=link', self.record.visits('/popup')[-1]['query'])
        close_origin(self.server.origin)
        page = self.open('/p/basic')
        self.run_steps(page, [step('click', field('Link', title='Go linked page'), unverified_ok=True)])
        self.received('lnk', 'click')
        deadline = time.monotonic() + 5
        while not self.record.visits('/linked') and time.monotonic() < deadline:
            time.sleep(0.1)
        self.assertTrue(self.record.visits('/linked'), self.record.snapshot())

    def test_same_and_cross_origin_frames(self):
        page = self.open('/p/frames')
        steps = []
        for who in ('same', 'cross'):
            entry = field('TextField', title=f'Frame field {who}')
            steps.append(step('click', field('Button', title=f'Frame button {who}'), unverified_ok=True))
            steps.append(step('set_value', entry, {'value': f'in {who}'}, postcondition=shows(entry, f'in {who}')))
        _, routes = self.run_steps(page, steps)
        for who, index in (('same', 1), ('cross', 3)):
            self.received(f'frame-{who}-button', 'click')
            self.assertEqual(f'in {who}', self.received(f'frame-{who}-field', 'input')[-1]['value'])
            self.assertEqual('L1', self.route(routes, index)['route_level'])

    def test_long_page_scrolls_and_reads_past_the_first_rows(self):
        page = self.open('/p/long')
        self.run_steps(page, [
            # Scrolling is asked of an element inside the page; its scroll bar is found from there.
            step('scroll', field('Heading', title='Haejo matrix long'),
                 {'direction': 'down', 'pages': 3}, unverified_ok=True),
            # Row 900 is past the rows the first observation lists.
            step('read', field('StaticText', value='Row 900')),
            step('click', field('Button', title='Deep button'), unverified_ok=True),
        ])
        self.assertGreater(self.received('window', 'scroll')[-1]['y'], 0)
        self.assertGreater(self.received('deep-btn', 'click')[-1]['y'], 0)


@unittest.skipUnless(FRONT_TESTS, 'opt-in: brings Safari in front briefly (HAEJO_RUN_NATIVE_SAFARI_FRONT_TESTS=1)')
class SafariPageFrontTests(SafariPageCase):
    """L3: the two actions a page takes only with Safari in front."""

    def test_pointer_only_control_gets_pointer_events_and_the_front_is_given_back(self):
        page = self.open('/p/basic')
        size = field('ComboBox', title='Size choice')
        _, routes = self.run_steps(page, [
            # The accessibility press is answered and opens nothing; the run
            # sends the click once more as pointer events and says so.
            step('click', size, postcondition=shows(field('StaticText', value='Large'), 'Large')),
            step('click', field('StaticText', value='Large'), {'route': 'pointer'},
                 postcondition=shows(size, 'Large')),
        ])
        fallback = [route for route in routes if route.get('status') == 'route_fallback']
        self.assertEqual([('ax_press', 'foreground_element_click', 'L3')],
                         [(f['from'], f['to'], f['route_level']) for f in fallback])
        for index in (0, 1):
            route = self.route(routes, index)
            self.assertEqual(('foreground_element_click', 'L3'), (route['input_route'], route['route_level']))
            self.assertIs(True, route['foreground_taken'])
            self.assertIs(True, route['front_restored'])
            self.assertIs(False, route['pointer_moved'])
            self.assertEqual(self.front_before, route['previous_front'])
        self.received('pd', 'open:pointerdown')
        self.assertEqual('Large', self.received('pd', 'pick:pointerdown')[-1]['value'])
        self.assertEqual('Large', self.collected(page)['size'])

    def test_hover_reaches_the_page_only_with_safari_in_front(self):
        self.open('/p/basic')
        title = f'Haejo matrix basic {self.record.token}'
        # The page's hover zone is its first 300x140 block, under the toolbar.
        at = ['--to', '150', '140', '--hold', '0.8', '--duration', '0.2']
        behind = haejo('hover', SAFARI, '--helper', '--window', title, *at)
        self.assertEqual(0, behind.returncode, behind.stdout + behind.stderr)
        time.sleep(0.5)
        self.assertEqual([], self.record.events('hov', 'mouseenter'), 'hover behind the front app is not delivered')
        shown = haejo('activate', SAFARI, '--window', title, '--helper')
        try:
            self.assertEqual(0, shown.returncode, shown.stdout + shown.stderr)
            hovered = haejo('hover', SAFARI, '--helper', '--window', title, *at)
            self.assertEqual(0, hovered.returncode, hovered.stdout + hovered.stderr)
            self.assertIn('"pointer_restored": true', hovered.stdout)
        finally:
            subprocess.run(['osascript', '-e', f'tell application id "{self.front_before}" to activate'],
                           capture_output=True, timeout=20)
            time.sleep(0.8)
        self.received('hov', 'mouseenter')


if __name__ == '__main__':
    unittest.main()
