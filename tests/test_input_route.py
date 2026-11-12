"""Input routes: the reply names the means, and a page click whose result never
shows goes once more as pointer events — only where that is known to help."""
from dataclasses import replace
from pathlib import Path
import unittest

from haejo.contract import Envelope
from haejo.flow import Flow, Step, Selector, Postcondition, replay
from haejo.helper import HelperDriver
from haejo.input_route import (POINTER_ROUTE_CAPABILITY, describe, level_of, pointer_fallback_applies,
                               route_of, under_web_area)
from haejo.protocol import ACTION_PARAMS, element_click_reobservation

ROOT = Path(__file__).resolve().parents[1]

PAGE = ('0 Window  Title: "Shop"\n'
        '  1 Group\n'
        '    2 WebArea  Description: "Shop"\n'
        '      3 ComboBox  Title: Size choice, Value: {value}\n'
        '{options}'
        '  4 Button  Description: Reload')
FOREGROUND_CLICK = {'type': 'acted', 'action': 'click', 'input_route': 'foreground_element_click',
                    'route_level': 'L3', 'posted_events': 2, 'unverified': 'observe_effect',
                    'reobserve_required': True, 'foreground_taken': True, 'front_restored': True,
                    'previous_front': 'com.example.editor', 'pointer_moved': False}


class Page:
    """A page control that ignores the accessibility press and opens on pointer events."""

    def __init__(self, *, capabilities=(POINTER_ROUTE_CAPABILITY, 'click.window_bound_element'),
                 opens_on_press=False, pointer_reply=None):
        self.capabilities = set(capabilities)
        self.open = False
        self.calls = []
        self.opens_on_press = opens_on_press
        self.pointer_reply = pointer_reply or dict(FOREGROUND_CLICK)

    def observe(self, *args, **kwargs):
        options = '      5 StaticText  Value: Large\n' if self.open else ''
        return {'type': 'observation', 'obs_id': f'obs{len(self.calls)}',
                'tree': PAGE.format(value='Pick a size', options=options)}

    def act(self, obs, target, action, **kwargs):
        self.calls.append(dict(action))
        if action.get('route') == 'pointer':
            if self.pointer_reply.get('type') == 'acted':
                self.open = True
            return dict(self.pointer_reply)
        if self.opens_on_press:
            self.open = True
        return {'type': 'acted', 'action': 'click', 'note': 'not verified — observe again'}

    def wait_until(self, target, predicate, **kwargs):
        seen = self.observe()
        return seen if predicate(seen['tree']) else {'type': 'timeout', 'last_obs': seen}


def click_flow(*, effects=('write_ephemeral',), selector=None, params=None):
    step = Step('click', selector or Selector(role='ComboBox', title='Size choice'), params=params or {},
                safety=Envelope.minimal().contract_for(set(effects), 'size'),
                postcondition=Postcondition(contains='StaticText  Value: Large'))
    return Flow('pick size', 'com.apple.Safari', [step], schema=2)


class RouteRecordTests(unittest.TestCase):
    def test_levels_follow_the_named_route(self):
        self.assertEqual('L1', level_of(None))
        self.assertEqual('L1', level_of('ax_value_focused'))
        self.assertEqual('L1', level_of('web_popup_menu'))
        self.assertEqual('L2', level_of('window_keys'))
        self.assertEqual('L2', level_of('window_bound_element_click'))
        self.assertEqual('L3', level_of('foreground_element_click'))
        self.assertEqual('L3', level_of('global_pointer'))
        self.assertEqual('L3', level_of('native_paste'))
        self.assertIsNone(level_of('something_new'))
        self.assertIsNone(level_of(7))

    def test_reply_becomes_a_small_record(self):
        self.assertEqual({'input_route': 'ax_action', 'route_level': 'L1'},
                         route_of({'type': 'acted', 'action': 'click'}))
        record = route_of(FOREGROUND_CLICK)
        self.assertEqual('L3', record['route_level'])
        self.assertIs(True, record['foreground_taken'])
        self.assertIs(True, record['front_restored'])
        self.assertEqual('com.example.editor', record['previous_front'])
        self.assertNotIn('posted_events', record)
        # The helper's own level wins over the table; an unknown one is read from the route.
        self.assertEqual('L2', route_of({'type': 'acted', 'input_route': 'web_date_picker',
                                         'route_level': 'L2'})['route_level'])
        self.assertEqual('L2', route_of({'type': 'acted', 'input_route': 'window_keys',
                                         'route_level': 'L9'})['route_level'])

    def test_a_refusal_before_input_has_no_route(self):
        self.assertIsNone(route_of({'type': 'error', 'error': 'input_busy', 'effect': 'not_started'}))
        self.assertIsNone(route_of(None))
        self.assertEqual('L3', route_of({'type': 'error', 'error': 'input_not_received', 'effect': 'unknown',
                                         'input_route': 'foreground_keys', 'route_level': 'L3'})['route_level'])

    def test_description_says_what_happened_to_the_front(self):
        text = describe(route_of(FOREGROUND_CLICK))
        self.assertIn('foreground_element_click (L3)', text)
        self.assertIn('returned it to com.example.editor', text)
        kept = describe(route_of({**FOREGROUND_CLICK, 'front_restored': False}))
        self.assertIn('could not return it', kept)
        self.assertIn('after ax_value_focused', describe(
            {'input_route': 'window_keys', 'route_level': 'L2', 'fallback_from': 'ax_value_focused'}))

    def test_page_content_is_what_sits_under_a_web_area(self):
        tree = PAGE.format(value='x', options='      5 StaticText  Value: Large\n')
        self.assertTrue(under_web_area(tree, 3))
        self.assertTrue(under_web_area(tree, 5))
        self.assertFalse(under_web_area(tree, 4))   # browser toolbar
        self.assertFalse(under_web_area(tree, 2))   # the web area itself
        self.assertFalse(under_web_area(tree, 99))
        self.assertFalse(under_web_area(None, 3))


class PointerFallbackTests(unittest.TestCase):
    def test_unanswered_page_click_goes_once_more_as_pointer_events(self):
        page = Page()
        result = replay(page, click_flow())
        self.assertTrue(result.ok, result.log)
        self.assertEqual([{'name': 'click', 'element_index': 3},
                          {'name': 'click', 'element_index': 3, 'route': 'pointer'}], page.calls)
        fallback = [entry for entry in result.log if entry.get('status') == 'route_fallback']
        self.assertEqual(1, len(fallback))
        self.assertEqual('ax_press', fallback[0]['from'])
        self.assertEqual('foreground_element_click', fallback[0]['to'])
        self.assertEqual('L3', fallback[0]['route_level'])
        ok = next(entry for entry in result.log if entry.get('status') == 'ok')
        self.assertEqual('L3', ok['route']['route_level'])
        self.assertIs(True, ok['route']['front_restored'])
        self.assertEqual('L3', result.events[-1]['route']['route_level'])

    def test_a_press_that_worked_is_not_repeated(self):
        page = Page(opens_on_press=True)
        result = replay(page, click_flow())
        self.assertTrue(result.ok, result.log)
        self.assertEqual(1, len(page.calls))
        self.assertEqual('L1', result.events[0]['route']['route_level'])
        self.assertFalse([entry for entry in result.log if entry.get('status') == 'route_fallback'])

    def test_no_second_click_without_the_capability_or_outside_a_page(self):
        cases = {
            'helper without the route': (Page(capabilities=()), click_flow()),
            'browser toolbar button': (Page(), replace(click_flow(), steps=[replace(
                click_flow().steps[0], selector=Selector(role='Button', desc='Reload'))])),
            'step with consequences': (Page(), click_flow(effects=('write_ephemeral', 'transmit'))),
        }
        for name, (page, flow) in cases.items():
            with self.subTest(name):
                result = replay(page, flow)
                self.assertFalse(result.ok, result.log)
                self.assertLessEqual(len(page.calls), 1)
                self.assertFalse([e for e in result.log if e.get('status') == 'route_fallback'])

    def test_failed_pointer_click_is_reported_and_not_sent_again(self):
        refusal = {'type': 'error', 'error': 'needs_foreground', 'effect': 'not_started',
                   'needs_foreground': True, 'route_level': 'L3'}
        page = Page(pointer_reply=refusal)
        result = replay(page, click_flow())
        self.assertFalse(result.ok, result.log)
        self.assertEqual(2, len(page.calls))
        fallback = next(entry for entry in result.log if entry.get('status') == 'route_fallback')
        self.assertEqual('needs_foreground', fallback['to'])
        self.assertIs(False, fallback['dispatched'])

    def test_fallback_decision_needs_a_plain_press_and_a_result_check(self):
        step = click_flow().steps[0]
        tree = PAGE.format(value='x', options='')
        caps = {POINTER_ROUTE_CAPABILITY}
        action = {'name': 'click', 'element_index': 3}
        pressed = {'type': 'acted', 'action': 'click'}
        self.assertTrue(pointer_fallback_applies(step, action, pressed, tree, caps))
        self.assertFalse(pointer_fallback_applies(step, {**action, 'route': 'pointer'}, pressed, tree, caps))
        self.assertFalse(pointer_fallback_applies(replace(step, postcondition=None), action, pressed, tree, caps))
        self.assertFalse(pointer_fallback_applies(replace(step, action='double_click'), action, pressed, tree, caps))
        self.assertFalse(pointer_fallback_applies(
            step, action, {**pressed, 'input_route': 'window_bound_element_click'}, tree, caps))
        self.assertFalse(pointer_fallback_applies(
            step, action, {**pressed, 'unverified': 'cannot_complete'}, tree, caps))
        self.assertFalse(pointer_fallback_applies(step, action, {'type': 'error'}, tree, caps))
        self.assertFalse(pointer_fallback_applies(step, action, pressed, tree, set()))


class PointerRouteParameterTests(unittest.TestCase):
    def test_click_accepts_only_the_pointer_route(self):
        self.assertEqual(frozenset({'route'}), ACTION_PARAMS['click'])
        page = Page()
        asked = replay(page, click_flow(params={'route': 'pointer'}))
        self.assertTrue(asked.ok, asked.log)
        self.assertEqual([{'name': 'click', 'element_index': 3, 'route': 'pointer'}], page.calls)
        for flow, driver in ((click_flow(params={'route': 'keys'}), Page()),
                             (click_flow(params={'route': 'pointer'}), Page(capabilities=()))):
            result = replay(driver, flow)
            self.assertFalse(result.ok)
            self.assertEqual('invalid_action', result.log[-1]['error'])
            self.assertEqual([], driver.calls)

    def test_reobservation_contract_covers_the_asked_route_only(self):
        caps = {'click.window_bound_element', POINTER_ROUTE_CAPABILITY}
        asked = {'name': 'click', 'element_index': 3, 'route': 'pointer'}
        plain = {'name': 'click', 'element_index': 3}
        window = {**FOREGROUND_CLICK, 'input_route': 'window_bound_element_click'}
        self.assertTrue(element_click_reobservation(asked, FOREGROUND_CLICK, caps))
        self.assertTrue(element_click_reobservation(asked, window, caps))
        self.assertTrue(element_click_reobservation(plain, window, caps))
        self.assertFalse(element_click_reobservation(plain, FOREGROUND_CLICK, caps))
        self.assertFalse(element_click_reobservation(asked, FOREGROUND_CLICK, {'click.window_bound_element'}))
        self.assertFalse(element_click_reobservation(asked, {**FOREGROUND_CLICK, 'posted_events': 1}, caps))
        self.assertFalse(element_click_reobservation({**asked, 'route': 'keys'}, FOREGROUND_CLICK, caps))

    def test_helper_driver_refuses_a_malformed_route_before_sending(self):
        driver = HelperDriver.__new__(HelperDriver)
        driver.capabilities = {POINTER_ROUTE_CAPABILITY, 'action.click'}
        sent = []
        driver._send = lambda message: sent.append(message) or {'type': 'acted'}
        driver._last_action_at = 0.0
        for action in ({'name': 'click', 'element_index': 1, 'route': 'keys'},
                       {'name': 'set_value', 'element_index': 1, 'value': 'x', 'route': 'pointer'},
                       {'name': 'click', 'point': {'x': 1, 'y': 1}, 'route': 'pointer'}):
            reply = driver.act('obs', 'com.apple.Safari', action)
            self.assertEqual(('invalid_click_route', 'not_started'), (reply['error'], reply['effect']))
        self.assertEqual([], sent)
        driver.capabilities = {'action.click'}
        self.assertEqual('invalid_click_route', driver.act(
            'obs', 'com.apple.Safari', {'name': 'click', 'element_index': 1, 'route': 'pointer'})['error'])
        self.assertEqual([], sent)
        driver.capabilities = {POINTER_ROUTE_CAPABILITY}
        self.assertEqual('acted', driver.act(
            'obs', 'com.apple.Safari', {'name': 'click', 'element_index': 1, 'route': 'pointer'})['type'])
        self.assertEqual('pointer', sent[0]['action']['route'])


class WebRouteSourceTests(unittest.TestCase):
    """The helper's page routes, read from source (the native suite runs them)."""

    def setUp(self):
        self.web = (ROOT / 'helper/WebInput.swift').read_text()
        self.helper = (ROOT / 'helper/HaejoHelper.swift').read_text()
        self.code = '\n'.join(line for line in self.web.splitlines()
                              if not line.lstrip().startswith(('//', '///')))

    def test_helper_is_built_with_the_web_routes_and_announces_them(self):
        self.assertIn('"WebInput.swift"', (ROOT / 'helper/build.sh').read_text())
        self.assertIn('"web.input_routes", "click.route_pointer"', self.helper)

    def test_page_select_never_uses_the_context_menu_action(self):
        select = self.helper[self.helper.index('case "select_option":'):self.helper.index('case "open_select":')]
        web_branch = select.index('webSelectOption(')
        self.assertLess(web_branch, select.index('"AXShowMenu" as CFString'))
        self.assertNotIn('AXShowMenu', self.code)

    def test_text_write_focuses_quietly_and_reads_back(self):
        focus = self.code[self.code.index('func webFocusBehind('):self.code.index('struct WebForeground')]
        self.assertLess(focus.index('kAXSelectedTextRangeAttribute'), focus.index('kAXPressAction'))
        self.assertNotIn('kAXFocusedAttribute as CFString', focus)
        write = self.code[self.code.index('func webSetValue('):self.code.index('private func webPopupWindows(')]
        self.assertLess(write.index('webFocusBehind('), write.index('kAXValueAttribute as CFString'))
        self.assertIn('"value_read_back": true', write)
        self.assertIn('fallback_from', write)

    def test_front_is_taken_only_inside_the_give_back_wrapper(self):
        self.assertEqual(1, self.code.count('.activate(options: [])'))
        wrapper = self.code[self.code.index('func withWebForeground<T>('):self.code.index('private func webRouteReply(')]
        self.assertIn('.activate(options: [])', wrapper)
        self.assertIn('returnScreen(to: previous)', wrapper)
        # AXFocused brings the browser forward, so it is written only there.
        outside = self.code.replace(wrapper, '')
        for at in [i for i in range(len(outside)) if outside.startswith('kAXFocusedAttribute as CFString', i)]:
            before = outside[:at]
            self.assertGreater(before.rfind('withWebForeground('), before.rfind('\nfunc '), 'AXFocused outside the wrapper')

    def test_page_events_go_through_the_one_pid_post_boundary(self):
        for banned in ('.postToPid(', 'CGEventPost(', '.post(tap:', 'CGWarpMouseCursorPosition(',
                       'NSApplication.shared.activate('):
            self.assertNotIn(banned, self.code)
        self.assertIn('nativePIDPost(', self.code)

    def test_launcher_passes_only_the_pointer_route(self):
        launcher = (ROOT / 'launcher/haejo.swift').read_text()
        self.assertIn('["element_index", "point", "window_index", "route"]', launcher)
        self.assertIn('case "route": if name != "click" || v as? String != "pointer"', launcher)


if __name__ == '__main__':
    unittest.main()
