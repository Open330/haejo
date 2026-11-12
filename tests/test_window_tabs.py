"""A browser window lists its tabs, and a selector can name one of them."""
try:
    from tests import _isolation  # noqa: F401
except ImportError:  # discovered with tests/ as the top level
    import _isolation  # noqa: F401
import copy
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from haejo.flow import Flow
from haejo.window_scope import (bind_window, parse_match, resolve_target, resolve_window, selector_problem,
                                tab_matches, tab_note, take_window_arg)

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = json.loads((ROOT / 'tests/fixtures/safari_27_tabs.json').read_text())
SAFARI = 'com.apple.Safari'
MINE = 38325


class Browser:
    """The listing measured on Safari 27.2, and a helper that selects tabs."""

    def __init__(self, replies=None, capabilities=('observe.window_list', 'session.window_scope', 'session.tab_select')):
        self.listing = copy.deepcopy(FIXTURE['listing'])
        self.capabilities = set(capabilities)
        self.replies = list(replies or [])
        self.scoped, self.selected = [], []

    def windows(self, target):
        return self.listing

    def scope_window(self, target, window_id):
        self.scoped.append(window_id)
        return {'type': 'window_scope', 'window_id': window_id}

    def select_tab(self, target, index, title=None, route=None):
        self.selected.append((index, title, route))
        if self.replies:
            return self.replies.pop(0)
        return {'type': 'tab_selected', 'window_id': self.scoped[-1], 'index': index, 'route': route or 'ax_press',
                'title': 'Tabfix ' + (title or '').removeprefix('Tabfix '),
                'url': 'http://127.0.0.1:8821/%s.html' % (title or '').removeprefix('Tabfix ')}


class Selector(unittest.TestCase):
    def test_tab_and_route_specs(self):
        args, value = take_window_arg(['session', SAFARI, '--window-match', 'tab=Tabfix gamma', '--helper'])
        self.assertEqual((['session', SAFARI, '--helper'], {'tab': 'Tabfix gamma'}), (args, value))
        self.assertEqual({'tab': 'beta', 'route': 'window_pointer', 'newest': True},
                         parse_match(['tab=beta', 'route=window_pointer', 'newest']))
        for bad in (['tab='], ['tab=a', 'tab=b'], ['route=ax_press'], ['tab=a', 'route=keyboard']):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                parse_match(bad)
        self.assertIsNotNone(selector_problem({'tab': '{{name}}'}))
        self.assertIsNone(selector_problem({'url': '127.0.0.1:8821', 'tab': 'gamma'}))

    def test_a_flow_keeps_the_tab_selector(self):
        doc = {'schema': 5, 'name': 'read tab', 'target': SAFARI, 'window': {'tab': 'Tabfix gamma'},
               'safety_defaults': {'effects': ['read'], 'reversibility': 'reversible',
                                   'resource': {'object_type': 'page', 'scope': 'entry'}},
               'steps': [{'action': 'read', 'selector': {'role': 'StaticText'}, 'answers': True}]}
        self.assertEqual({'tab': 'Tabfix gamma'}, Flow.from_json(json.dumps(doc)).window)

    def test_text_is_part_of_the_title_or_of_a_known_address(self):
        showing = {'index': 0, 'title': 'Tabfix alpha', 'selected': True, 'url': 'http://127.0.0.1:8821/alpha.html'}
        self.assertTrue(tab_matches(showing, 'TABFIX'))
        self.assertTrue(tab_matches(showing, '8821/alpha'))
        self.assertFalse(tab_matches({'index': 1, 'title': 'beta', 'selected': False}, '8821/beta'))


class Resolution(unittest.TestCase):
    def test_a_background_tab_is_found_in_its_window(self):
        window_id, tab, problem = resolve_target(Browser(), SAFARI, {'tab': 'gamma'})
        self.assertEqual((MINE, 2, None), (window_id, tab['index'], problem))
        # The window-only form is unchanged.
        self.assertEqual((MINE, None), resolve_window(Browser(), SAFARI, {'url': '127.0.0.1:8821'}))

    def test_one_tab_window_is_its_own_tab(self):
        window_id, tab, _ = resolve_target(Browser(), SAFARI, {'tab': '8835'})
        self.assertEqual((38404, 0, True), (window_id, tab['index'], tab['selected']))

    def test_the_same_title_in_two_windows_is_ambiguous_until_narrowed(self):
        driver = Browser()
        _, _, problem = resolve_target(driver, SAFARI, {'tab': 'Upload Fixture'})
        self.assertEqual('window_match_ambiguous', problem['error'])
        self.assertEqual([(38404, 0), (38333, 0)], [(c['window_id'], c['tab']['index']) for c in problem['candidates']])
        self.assertEqual(38333, resolve_target(driver, SAFARI, {'tab': 'Upload Fixture', 'url': '127.0.0.1:8811'})[0])
        window_id, tab, _ = resolve_target(driver, SAFARI, {'tab': 'Upload Fixture', 'newest': True})
        self.assertEqual((38404, 0), (window_id, tab['index']))
        window_id, tab, _ = resolve_target(driver, SAFARI, {'tab': 'Tabfix', 'newest': True})
        self.assertEqual((MINE, 0), (window_id, tab['index']), 'the showing tab is preferred among several')

    def test_no_match_lists_tab_titles(self):
        ticks = iter(range(0, 1000, 6))
        _, _, problem = resolve_target(Browser(), SAFARI, {'tab': 'nosuch'}, sleep=lambda s: None,
                                       clock=lambda: next(ticks))
        self.assertEqual('window_match_none', problem['error'])
        mine = [row for row in problem['listed'] if row['window_id'] == MINE][0]
        self.assertEqual(['Tabfix alpha', 'beta', 'Tabfix gamma', 'delta'], mine['tabs'])


class Binding(unittest.TestCase):
    def test_the_tab_is_selected_after_the_window_is_pinned(self):
        driver = Browser()
        self.assertIsNone(bind_window(driver, SAFARI, {'tab': 'gamma'}))
        self.assertEqual(([MINE], [(2, 'Tabfix gamma', None)]), (driver.scoped, driver.selected))
        note = tab_note(driver)
        self.assertTrue(note.startswith('HAEJO_TAB_SELECTED '))
        self.assertEqual({'window_id': MINE, 'index': 2, 'title': 'Tabfix gamma', 'route': 'ax_press',
                          'url': 'http://127.0.0.1:8821/gamma.html'}, json.loads(note.split(' ', 1)[1]))
        self.assertEqual((SAFARI, {'tab': 'gamma'}), driver._window_selector)

    def test_a_named_route_reaches_the_helper_and_the_note(self):
        driver = Browser([{'type': 'tab_selected', 'window_id': MINE, 'index': 1, 'title': 'Tabfix beta',
                           'url': 'http://127.0.0.1:8821/beta.html', 'route': 'front_pointer',
                           'front_taken': True, 'front_restored': True,
                           'attempts': [{'route': 'ax_press', 'result': 'no_press_action'}]}])
        self.assertIsNone(bind_window(driver, SAFARI, {'tab': 'beta', 'route': 'front_pointer'}))
        self.assertEqual([(1, 'beta', 'front_pointer')], driver.selected)
        chosen = json.loads(tab_note(driver).split(' ', 1)[1])
        self.assertEqual(('front_pointer', True, True), (chosen['route'], chosen['front_taken'], chosen['front_restored']))
        self.assertEqual('no_press_action', chosen['attempts'][0]['result'])

    def test_a_title_that_changed_while_loading_is_taken_from_the_fresh_list(self):
        fresh = {'type': 'error', 'error': 'tab_changed', 'effect': 'not_started',
                 'tabs': [{'index': 0, 'title': 'Tabfix alpha', 'selected': True},
                          {'index': 1, 'title': 'Tabfix beta', 'selected': False}]}
        driver = Browser([fresh])
        self.assertIsNone(bind_window(driver, SAFARI, {'tab': 'beta'}))
        self.assertEqual([(1, 'beta', None), (1, 'Tabfix beta', None)], driver.selected)
        gone = Browser([dict(fresh, tabs=[{'index': 0, 'title': 'Tabfix alpha', 'selected': True}])])
        self.assertEqual('tab_changed', bind_window(gone, SAFARI, {'tab': 'beta'})['error'])

    def test_a_page_still_loading_is_read_again(self):
        loading = {'type': 'tab_selected', 'window_id': MINE, 'index': 2, 'title': 'Untitled', 'route': 'window_pointer'}
        loaded = {'type': 'tab_selected', 'window_id': MINE, 'index': 2, 'title': 'Tabfix gamma',
                  'url': 'http://127.0.0.1:8821/gamma.html', 'route': 'already_selected'}
        driver = Browser([loading, dict(loading, route='already_selected'), loaded])
        with patch('haejo.window_scope.time.sleep') as sleep:
            self.assertIsNone(bind_window(driver, SAFARI, {'tab': 'gamma'}))
        self.assertEqual(2, sleep.call_count)
        chosen = json.loads(tab_note(driver).split(' ', 1)[1])
        self.assertEqual(('Tabfix gamma', 'window_pointer'), (chosen['title'], chosen['route']))

    def test_another_page_after_selecting_is_reported(self):
        wrong = {'type': 'tab_selected', 'window_id': MINE, 'index': 2, 'title': 'Sign in',
                 'url': 'http://127.0.0.1:8821/login', 'route': 'ax_press'}
        driver = Browser([wrong] * 9)
        with patch('haejo.window_scope.time.sleep'):
            problem = bind_window(driver, SAFARI, {'tab': 'gamma'})
        self.assertEqual(('tab_select_unverified', 'unknown'), (problem['error'], problem['effect']))
        self.assertEqual('Sign in', problem['selected']['title'])
        self.assertIsNone(tab_note(driver))

    def test_refusals_pass_through_and_an_older_helper_is_named(self):
        busy = {'type': 'error', 'error': 'target_busy', 'effect': 'not_started', 'retryable': True}
        self.assertEqual(busy, bind_window(Browser([busy]), SAFARI, {'tab': 'gamma'}))
        failed = {'type': 'error', 'error': 'tab_select_failed', 'effect': 'not_started',
                  'attempts': [{'route': 'window_pointer', 'result': 'hit-test does not identify element or descendant'}]}
        self.assertEqual(failed, bind_window(Browser([failed]), SAFARI, {'tab': 'gamma'}))
        old = Browser(capabilities=('observe.window_list', 'session.window_scope'))
        self.assertEqual('tab_select_unavailable', bind_window(old, SAFARI, {'tab': 'gamma'})['error'])
        self.assertEqual([], old.selected)


class HelperMessage(unittest.TestCase):
    def test_select_tab_is_sent_inside_the_window_pin(self):
        from haejo.helper import HelperDriver
        driver = HelperDriver.__new__(HelperDriver)
        driver.capabilities = {'session.window_scope', 'session.tab_select'}
        sent = []
        driver._send = lambda msg: sent.append(msg) or {'type': 'tab_selected'}
        self.assertEqual('invalid_tab_select', driver.select_tab(SAFARI, 1)['error'])
        driver.scope_window(SAFARI, MINE)
        driver.select_tab(SAFARI, 1, 'beta', route='window_pointer')
        self.assertEqual([{'type': 'tab_select', 'target': SAFARI,
                           'tab': {'index': 1, 'title': 'beta', 'route': 'window_pointer'}}], sent)
        self.assertEqual('invalid_tab_select', driver.select_tab(SAFARI, True)['error'])


@unittest.skipUnless(sys.platform == 'darwin' and shutil.which('swiftc'), 'macOS Swift required')
class SwiftSources(unittest.TestCase):
    def run_swift(self, source):
        with tempfile.TemporaryDirectory(prefix='haejo-tabs-') as directory:
            src, exe = Path(directory) / 'main.swift', Path(directory) / 'check'
            src.write_text(source)
            built = subprocess.run(['swiftc', str(src), '-o', str(exe)], capture_output=True, text=True, timeout=120)
            self.assertEqual(0, built.returncode, built.stderr)
            run = subprocess.run([str(exe)], capture_output=True, text=True, timeout=20)
            self.assertEqual(0, run.returncode, run.stderr)
        return json.loads(run.stdout)

    def test_listing_reads_the_observed_safari_tab_bar(self):
        # The helper's own tab reader, compiled against the tree Safari 27.2
        # gave. No accessibility call, app or helper is involved.
        helper = (ROOT / 'helper/HaejoHelper.swift').read_text()
        readers = helper[helper.index('@Sendable func attr('):helper.index('// The same budgets the Python driver applies')]
        source = (ROOT / 'helper/ParallelWindows.swift').read_text()
        tabs = source[source.index('struct BrowserTab {'):source.index('let browserTabRoutes')]
        harness = r'''
import Foundation
import ApplicationServices
var nodes:[pid_t:[String:CFTypeRef]]=[:]
var next:pid_t=0
var reads=0
func build(_ raw:[String:Any]) -> AXUIElement {
    next+=1;let id=next
    var row:[String:CFTypeRef]=[:]
    for (key,name) in [("role","AXRole"),("subrole","AXSubrole"),("title","AXTitle"),("identifier","AXIdentifier"),("description","AXDescription")] {
        if let text=raw[key] as? String { row[name]=text as CFString }
    }
    if let value=raw["value"] as? NSNumber { row["AXValue"]=value }
    if let value=raw["value"] as? String { row["AXValue"]=value as CFString }
    if let children=raw["children"] as? [[String:Any]] { row["AXChildren"]=children.map(build) as CFArray }
    nodes[id]=row
    return AXUIElementCreateApplication(id)
}
func AXUIElementCopyAttributeValue(_ el:AXUIElement,_ key:CFString,_ out:UnsafeMutablePointer<CFTypeRef?>) -> AXError {
    var id:pid_t=0;_ = AXUIElementGetPid(el,&id);reads+=1
    guard let value=nodes[id]?[key as String] else { return .attributeUnsupported }
    out.pointee=value;return .success
}
func AXUIElementSetMessagingTimeout(_ el:AXUIElement,_ seconds:Float) -> AXError { .success }
''' + readers + tabs + r'''
let fixture=try! JSONSerialization.jsonObject(with:Data(contentsOf:URL(fileURLWithPath:CommandLine.arguments[1]))) as! [String:Any]
var out:[String:Any]=[:]
for name in ["four_tabs","one_tab"] {
    let raw=fixture[name] as! [String:Any]
    let window=build(raw)
    let title=raw["title"] as! String
    out[name]=browserTabRows(window,url:"http://127.0.0.1:8821/page",title:title)
    out[name+"_no_page"]=browserTabRows(window,url:nil,title:title)
}
print(String(data:try! JSONSerialization.data(withJSONObject:out),encoding:.utf8)!)
'''.replace('CommandLine.arguments[1]', json.dumps(str(ROOT / 'tests/fixtures/safari_27_tabs.json')))
        result = self.run_swift(harness)
        self.assertEqual([
            {'index': 0, 'title': 'Tabfix alpha', 'selected': False},
            {'index': 1, 'title': 'beta', 'selected': False},
            # The showing tab takes the window's page title and address.
            {'index': 2, 'title': 'Tabfix gamma', 'selected': True, 'url': 'http://127.0.0.1:8821/page'},
            {'index': 3, 'title': 'delta', 'selected': False}], result['four_tabs'])
        self.assertEqual([0, 1, 2, 3], [row['index'] for row in result['four_tabs_no_page']])
        self.assertNotIn('url', result['four_tabs_no_page'][2])
        # No tab bar: the page is the window's one tab; a window without a page has none.
        self.assertEqual([{'index': 0, 'title': 'Haejo Upload Fixture', 'selected': True,
                           'url': 'http://127.0.0.1:8821/page'}], result['one_tab'])
        self.assertEqual([], result['one_tab_no_page'])

    def test_pinned_and_value_only_tabs(self):
        helper = (ROOT / 'helper/HaejoHelper.swift').read_text()
        readers = helper[helper.index('@Sendable func attr('):helper.index('// The same budgets the Python driver applies')]
        source = (ROOT / 'helper/ParallelWindows.swift').read_text()
        tabs = source[source.index('struct BrowserTab {'):source.index('let browserTabRoutes')]
        harness = r'''
import Foundation
import ApplicationServices
var nodes:[pid_t:[String:CFTypeRef]]=[:]
func node(_ id:pid_t,_ row:[String:CFTypeRef]) -> AXUIElement { nodes[id]=row;return AXUIElementCreateApplication(id) }
func AXUIElementCopyAttributeValue(_ el:AXUIElement,_ key:CFString,_ out:UnsafeMutablePointer<CFTypeRef?>) -> AXError {
    var id:pid_t=0;_ = AXUIElementGetPid(el,&id)
    guard let value=nodes[id]?[key as String] else { return .attributeUnsupported }
    out.pointee=value;return .success
}
func AXUIElementSetMessagingTimeout(_ el:AXUIElement,_ seconds:Float) -> AXError { .success }
''' + readers + tabs + r'''
let pinned=node(3,["AXRole":"AXRadioButton" as CFString,"AXTitle":"Mail" as CFString,"AXValue":0 as CFNumber,
    "AXIdentifier":"TabBarTab?isNarrow=true&isPinned=true&isActive=false" as CFString])
let plain=node(4,["AXRole":"AXRadioButton" as CFString,"AXDescription":"Docs" as CFString,"AXValue":1 as CFNumber,
    "AXIdentifier":"TabBarTab?" as CFString])
let other=node(5,["AXRole":"AXButton" as CFString,"AXIdentifier":"NewTabButton" as CFString])
let bar=node(2,["AXRole":"AXOpaqueProviderGroup" as CFString,"AXIdentifier":"TabBar?isSeparate=true" as CFString,
    "AXChildren":[pinned,other,plain] as CFArray])
let window=node(1,["AXRole":"AXWindow" as CFString,"AXChildren":[bar] as CFArray])
print(String(data:try! JSONSerialization.data(withJSONObject:browserTabRows(window,url:nil,title:"")),encoding:.utf8)!)
'''
        self.assertEqual([{'index': 0, 'title': 'Mail', 'selected': False, 'pinned': True},
                          {'index': 1, 'title': 'Docs', 'selected': True}], self.run_swift(harness))

    def test_launcher_accepts_only_a_well_formed_tab_request(self):
        source = (ROOT / 'launcher/haejo.swift').read_text()
        schema = source[source.index('let allowedTypes:'):source.index('// MARK: - Socket plumbing')]
        checks = r'''
let base:[String:Any]=["type":"tab_select","target":"com.apple.Safari","window_scope_id":38325,
    "tab":["index":2,"title":"Tabfix gamma"]]
var requests=[base]
for tab:Any in [["index":0],["index":1,"route":"window_pointer"],["index":1,"route":"front_pointer"],
                ["index":-1],["index":true],["index":1.5],["index":4096],["title":"x"],["index":1,"route":"keys"],
                ["index":1,"title":String(repeating:"x",count:513)],["index":1,"extra":1],"gamma"] {
    var row=base;row["tab"]=tab;requests.append(row)
}
var unpinned=base;unpinned["window_scope_id"]=nil;requests.append(unpinned)
var extra=base;extra["obs_id"]="owned";requests.append(extra)
requests.append(["type":"observe","target":"com.apple.Safari","tab":["index":1]])
print(String(data:try! JSONSerialization.data(withJSONObject:requests.map { vetted($0)==nil }),encoding:.utf8)!)
'''
        result = self.run_swift('import Foundation\nimport CoreFoundation\nfunc modelTimeout(_ raw:Any?)->Double? {1}\n'
                                + schema + checks)
        self.assertEqual([True, True, True, True] + [False] * 12, result)


if __name__ == '__main__':
    unittest.main()
