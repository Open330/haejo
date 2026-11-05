"""Observed-window document pins and read-only editing mode (no GUI, no app).

Synthetic AX documents for the reader and drivers; the helper's pure mode rule
and the launcher's actual request validator are compiled with Swift.
"""
import io
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from tacto.native_document import (DocumentModeUnavailable, DocumentSnapshotError,
                                   TextEditDocumentReader, document_mode_from_format_menu)

ROOT = Path(__file__).resolve().parents[1]


class Adapter:
    """Two open TextEdit documents; each window has one body."""

    def __init__(self):
        self.paths = {'w1': 'file:///Users/me/a.rtf', 'w2': None}
        self.texts = {'b1': 'user document', 'b2': 'owned untitled'}
        self.main = 'w2'
        self.menu = [('Make Plain Text', True)]
        self.ready = True
        self.edited = (0, True)
        self.calls = []

    def equal(self, left, right):
        return left == right

    def process_identity(self, target):
        return (42, 1000.0)

    def documents(self, target):
        return [('w1', 'b1'), ('w2', 'b2')]

    def read_attribute(self, element, name):
        self.calls.append((element, name))
        if name == 'AXDocument':
            value = self.paths[element]
            return (-25212, None) if value is None else (0, value)
        if name == 'AXMain':
            return (0, element == self.main)
        if name == 'AXEdited':
            return self.edited
        if name == 'AXNumberOfCharacters':
            return (0, len(self.texts[element]))
        if name == 'AXValue':
            return (0, self.texts[element])
        return (-25205, None)

    def read_range(self, body, start, length):
        return (0, self.texts[body][start:start + length])

    def window_ready(self, target, window):
        if not self.ready:
            raise RuntimeError('sheet present')

    def format_menu_entries(self, target):
        return list(self.menu)


def reader():
    adapter = Adapter()
    return TextEditDocumentReader(adapter), adapter


class WindowSelectorReaderTests(unittest.TestCase):
    def setUp(self):
        self.reader, self.adapter = reader()
        patcher = patch('tacto.native_document._document_path', side_effect=lambda r: None if r[0] else r[1][7:])
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_without_selector_two_open_documents_stay_ambiguous(self):
        with self.assertRaises(DocumentSnapshotError):
            self.reader.read()

    def test_window_selection_pins_that_body_and_survives_save_as_url_change(self):
        first = self.reader.read(window='w2')
        self.assertEqual(('owned untitled', None), (first['text'], first['document_path']))
        self.adapter.paths['w2'] = 'file:///Users/me/Downloads/new.rtf'   # Save As
        again = self.reader.read(document_token=first['document_token'])
        self.assertEqual('/Users/me/Downloads/new.rtf', again['document_path'])
        self.assertEqual('owned untitled', again['text'])
        # The other user document was never selected, changed or closed.
        self.assertEqual('file:///Users/me/a.rtf', self.adapter.paths['w1'])

    def test_selectors_cannot_be_combined(self):
        first = self.reader.read(window='w2')
        for kwargs in ({'document_token': first['document_token']}, {'document_path': '/Users/me/a.rtf'}):
            with self.subTest(kwargs=kwargs), self.assertRaises(DocumentSnapshotError):
                self.reader.read(window='w2', **kwargs)

    def test_unknown_window_is_not_a_document(self):
        with self.assertRaises(DocumentSnapshotError):
            self.reader.read(window='w9')


class DocumentModeTests(unittest.TestCase):
    def setUp(self):
        self.reader, self.adapter = reader()
        patcher = patch('tacto.native_document._document_path', side_effect=lambda r: None if r[0] else r[1][7:])
        patcher.start()
        self.addCleanup(patcher.stop)
        self.token = self.reader.read(window='w2')['document_token']

    def mode(self):
        return self.reader.mode('com.apple.TextEdit', self.token)

    def reason(self):
        with self.assertRaises(DocumentModeUnavailable) as caught:
            self.mode()
        return caught.exception.reason

    def test_rich_and_plain_modes_with_witness_and_no_format_claim(self):
        reply = self.mode()
        self.assertEqual(('rich_text', 'Make Plain Text', True, False),
                         (reply['editing_mode'], reply['witness']['menu_title'], reply['edited'],
                          reply['source_format_verified']))
        self.assertEqual({'source': 'format_menu', 'menu_title': 'Make Plain Text',
                          'menu_enabled': True, 'title_current_verified': True,
                          'main_window_before': True, 'main_window_after': True}, reply['witness'])
        self.adapter.menu = [('리치 텍스트 만들기', True)]
        self.adapter.edited = (-25205, None)
        reply = self.mode()
        self.assertEqual(('plain_text', None), (reply['editing_mode'], reply['edited']))

    def test_unprovable_states_are_unavailable_not_guessed(self):
        self.adapter.menu = [('Make Plain Text', True), ('Make Rich Text', True)]
        self.assertEqual('format_menu_ambiguous_or_absent', self.reason())
        self.adapter.menu = []
        self.assertEqual('format_menu_ambiguous_or_absent', self.reason())
        self.adapter.menu = [('Make Plain Text', True)]
        self.adapter.main = 'w1'
        self.assertEqual('not_main_window', self.reason())
        self.adapter.main = 'w2'
        self.adapter.ready = False
        self.assertEqual('window_not_ready', self.reason())
        self.adapter.ready = True
        original = self.adapter.format_menu_entries
        def switch_main(target):
            self.adapter.main = 'w1'
            return original(target)
        self.adapter.format_menu_entries = switch_main
        self.assertEqual('main_window_or_pin_changed', self.reason())

    def test_unknown_token_and_target(self):
        with self.assertRaises(DocumentModeUnavailable):
            self.reader.mode('com.apple.TextEdit', 'missing')
        with self.assertRaises(DocumentModeUnavailable):
            self.reader.mode('com.apple.Safari', self.token)

    def test_read_only_attributes_only(self):
        self.mode()
        names = {name for _, name in self.adapter.calls}
        self.assertLessEqual(names, {'AXDocument', 'AXMain', 'AXEdited', 'AXNumberOfCharacters', 'AXValue'})

    def test_pure_rule(self):
        self.assertEqual(('rich_text', '일반 텍스트 만들기'), document_mode_from_format_menu([('일반 텍스트 만들기', True), ('Copy', True)]))
        with self.assertRaises(DocumentModeUnavailable):
            document_mode_from_format_menu([('Make plain text', True)])     # not an exact known title

    def test_disabled_format_command_still_reports_read_only_editing_mode(self):
        for title, expected in [('Make Plain Text', 'rich_text'), ('Make Rich Text', 'plain_text')]:
            self.adapter.menu = [(title, False)]
            reply = self.mode()
            self.assertEqual(expected, reply['editing_mode'])
            self.assertIs(reply['witness']['menu_enabled'], False)
            self.assertIs(reply['witness']['title_current_verified'], False)


class DriverSelectorTests(unittest.TestCase):
    def driver(self):
        from tacto import driver
        d = driver.Driver.__new__(driver.Driver)
        class Obs:
            obs_id, pid, elements, process_launch_identity = 'obs1', 42, ['app', 'win'], 7.0
        d._latest = {'com.apple.textedit': Obs()}
        d._resolve = lambda target, launch=True: 42
        d.reads = []
        class Reader:
            def read(_, target, **kwargs):
                d.reads.append(kwargs)
                return {'type': 'document_text'}
        d._document_reader = Reader()
        return d

    def call(self, d, **kwargs):
        roles = {'app': 'AXApplication', 'win': 'AXWindow'}
        with patch('tacto.driver._attr', side_effect=lambda el, name: roles.get(el)), \
                patch('tacto.native_process_identity.process_start_identity', side_effect=lambda pid: 7.0):
            return d.document_text('com.apple.TextEdit', **kwargs)

    def test_current_observation_window_is_passed_to_the_reader(self):
        d = self.driver()
        self.assertEqual('document_text', self.call(d, obs_id='obs1', window_element_index=1)['type'])
        self.assertEqual('win', d.reads[0]['window'])

    def test_stale_non_window_combined_or_other_process_is_refused(self):
        cases = [dict(obs_id='old', window_element_index=1), dict(obs_id='obs1', window_element_index=0),
                 dict(obs_id='obs1', window_element_index=9), dict(obs_id='obs1', window_element_index=1, document_token='t'),
                 dict(obs_id='obs1'), dict(obs_id='obs1', window_element_index=True)]
        for kwargs in cases:
            with self.subTest(kwargs=kwargs):
                d = self.driver()
                self.assertEqual('document_snapshot_unavailable', self.call(d, **kwargs)['error'])
                self.assertEqual([], d.reads)
        d = self.driver()
        d._resolve = lambda target, launch=True: 43
        self.assertEqual('document_snapshot_unavailable', self.call(d, obs_id='obs1', window_element_index=1)['error'])


class HelperClientTests(unittest.TestCase):
    def client(self, reply, caps=('evidence.document_mode', 'evidence.document_text.window_selector')):
        from tacto.helper import HelperDriver
        h = HelperDriver.__new__(HelperDriver)
        h.capabilities = set(caps)
        class Proc:
            stdin = io.StringIO()
            stdout = io.StringIO(json.dumps(reply) + '\n')
        h._proc = Proc()
        return h

    def sent(self, h):
        return [json.loads(l) for l in h._proc.stdin.getvalue().splitlines()]

    def good(self):
        return {'type': 'document_mode', 'document_token': 'tok', 'editing_mode': 'rich_text',
                'witness': {'source': 'format_menu', 'menu_title': 'Make Plain Text',
                          'menu_enabled': True, 'title_current_verified': True,
                            'main_window_before': True, 'main_window_after': True},
                'edited': None, 'source_format_verified': False}

    def test_valid_mode_reply_passes_and_tampering_is_refused(self):
        self.assertEqual('rich_text', self.client(self.good()).document_mode('com.apple.TextEdit', 'tok')['editing_mode'])
        timed = {**self.good(), 'coordination_elapsed_ms':31}
        self.assertEqual(timed, self.client(timed).document_mode('com.apple.TextEdit','tok'))
        for change in ({'editing_mode': 'plain_text'}, {'source_format_verified': True},
                       {'extra': 1}, {'document_token': 'other'}, {'edited': 'yes'}):
            with self.subTest(change=change):
                reply = {**self.good(), **change}
                self.assertEqual('document_mode_unavailable',
                                 self.client(reply).document_mode('com.apple.TextEdit', 'tok')['error'])

    def test_disabled_hint_is_preserved_and_inconsistent_witness_is_refused(self):
        reply = self.good()
        reply['witness'].update(menu_enabled=False, title_current_verified=False)
        self.assertEqual(reply, self.client(reply).document_mode('com.apple.TextEdit', 'tok'))
        reply['witness']['title_current_verified'] = True
        self.assertEqual('document_mode_unavailable',
                         self.client(reply).document_mode('com.apple.TextEdit', 'tok')['error'])

    def test_no_capability_or_bad_request_sends_nothing(self):
        h = self.client(self.good(), caps=())
        self.assertEqual('document_mode_unavailable', h.document_mode('com.apple.TextEdit', 'tok')['error'])
        self.assertEqual([], self.sent(h))
        h = self.client(self.good())
        self.assertEqual('document_mode_unavailable', h.document_mode('com.apple.Safari', 'tok')['error'])
        self.assertEqual([], self.sent(h))

    def test_document_text_window_selector_is_forwarded_or_refused(self):
        h = self.client({'type': 'document_text'})
        h.document_text('com.apple.TextEdit', obs_id='obs1', window_element_index=2)
        sent = self.sent(h)[0]
        self.assertEqual(('obs1', 2), (sent['obs_id'], sent['window_element_index']))
        self.assertNotIn('document_token', sent)
        h = self.client({'type': 'document_text'}, caps=())
        self.assertEqual('document_snapshot_unavailable',
                         h.document_text('com.apple.TextEdit', obs_id='obs1', window_element_index=2)['error'])
        self.assertEqual([], self.sent(h))


@unittest.skipUnless(sys.platform == 'darwin' and shutil.which('swift'), 'macOS Swift required')
class SwiftSourceTests(unittest.TestCase):
    def run_swift(self, code):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'main.swift'
            path.write_text(code)
            result = subprocess.run(['swift', str(path)], capture_output=True, text=True, timeout=90)
        self.assertEqual(0, result.returncode, result.stderr[-3000:])
        return json.loads(result.stdout)

    def test_helper_pure_mode_rule_matches_python(self):
        source = (ROOT / 'helper/TactoHelper.swift').read_text()
        rule = source[source.index('let documentModeRichTitles'):source.index('func documentMode(_ msg')]
        cases = [[['Make Plain Text', True]], [['Make Rich Text', True]], [['일반 텍스트 만들기', True]],
                 [['리치 텍스트 만들기', True]], [['Make Plain Text', False]], [],
                 [['Make Plain Text', True], ['Make Rich Text', True]], [['Copy', True]]]
        literal = '[' + ', '.join('[' + ', '.join(f'({json.dumps(t, ensure_ascii=False)}, {str(e).lower()})'
                                                  for t, e in case) + ']' for case in cases) + ']'
        code = 'import Foundation\n' + rule + '''
let cases: [[(String, Bool)]] = ''' + literal + '''
print(String(data: try! JSONSerialization.data(withJSONObject: cases.map { c -> [Any] in
  let r = documentModeFromFormatMenu(c.map { (title: $0.0, enabled: $0.1) })
  return [r.rich.map { $0 as Any } ?? NSNull(), r.reason] }), encoding: .utf8)!)
'''
        swift = self.run_swift(code)
        for case, (rich, reason) in zip(cases, swift):
            try:
                mode, _ = document_mode_from_format_menu([tuple(e) for e in case])
                self.assertEqual(mode == 'rich_text', rich)
            except DocumentModeUnavailable as exc:
                self.assertIsNone(rich)
                self.assertEqual(exc.reason, reason)

    def test_document_mode_is_read_only_and_advertised(self):
        source = (ROOT / 'helper/TactoHelper.swift').read_text()
        body = source[source.index('func documentMode(_ msg'):]; body = body[:body.index('\n}\n')]
        for forbidden in ('AXUIElementPerformAction', 'AXUIElementSetAttributeValue', 'activate', 'CGEvent', 'kAXPressAction'):
            self.assertNotIn(forbidden, body)
        self.assertIn('nativeRequireWindowReady(pinned.window, pinned.pid)', body)
        self.assertEqual(2, body.count('try isMain()'))
        self.assertIn('"source_format_verified": false', body)
        self.assertIn('case "document_mode":\n        return documentMode(msg)', source)
        self.assertIn('"evidence.document_text.window_selector", "evidence.document_mode"', source)

    def test_launcher_validator(self):
        source = (ROOT / 'launcher/tacto.swift').read_text()
        schema = source[source.index('let allowedTypes:'):source.index('// MARK: - Socket plumbing')]
        checks = r'''
let rows: [[String: Any]] = [
 ["type":"document_text","target":"com.apple.TextEdit","obs_id":"o1","window_element_index":2],
 ["type":"document_text","target":"com.apple.TextEdit","obs_id":"o1"],
 ["type":"document_text","target":"com.apple.TextEdit","obs_id":"o1","window_element_index":2,"document_token":"t"],
 ["type":"document_text","target":"com.apple.TextEdit","obs_id":"o1","window_element_index":true],
 ["type":"document_text","target":"com.apple.TextEdit","obs_id":"o1","window_element_index":-1],
 ["type":"document_mode","target":"com.apple.TextEdit","document_token":"t"],
 ["type":"document_mode","target":"com.apple.Safari","document_token":"t"],
 ["type":"document_mode","target":"com.apple.TextEdit","document_token":"t","obs_id":"o1"],
 ["type":"document_mode","target":"com.apple.TextEdit"]]
print(String(data: try! JSONSerialization.data(withJSONObject: rows.map { vetted($0) == nil }), encoding: .utf8)!)
'''
        result = self.run_swift('import Foundation\nimport CoreFoundation\nfunc modelTimeout(_ raw:Any?)->Double? {1}\n'
                                + schema + checks)
        self.assertEqual([True, False, False, False, False, True, False, False, False], result)


if __name__ == '__main__':
    unittest.main()
