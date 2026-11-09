"""save_panel by its observed commit button, without a new observation (no GUI)."""
import io
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class HelperClientTests(unittest.TestCase):
    def client(self, reply, caps=('evidence.save_panel', 'evidence.save_panel.commit_selector')):
        from haejo.helper import HelperDriver
        h = HelperDriver.__new__(HelperDriver)
        h.capabilities = set(caps)
        class Proc:
            stdin = io.StringIO()
            stdout = io.StringIO(json.dumps(reply) + '\n')
        h._proc = Proc()
        return h

    def sent(self, h):
        return [json.loads(line) for line in h._proc.stdin.getvalue().splitlines()]

    def panel(self, index):
        return {'type': 'save_panel', 'panel_token': 'p', 'commit_control':
                {'obs_id': 'o1', 'enabled': True, 'action': {'name': 'click', 'element_index': index}}}

    def test_commit_selector_is_sent_and_must_come_back_as_the_same_button(self):
        h = self.client(self.panel(17))
        reply = h.save_panel('o1', 'com.apple.TextEdit', commit_element_index=17, document_token='t',
                             require_format=True)
        self.assertEqual('save_panel', reply['type'])
        sent = self.sent(h)[0]
        self.assertEqual(17, sent['commit_element_index'])
        self.assertNotIn('window_element_index', sent)
        mismatch = self.client(self.panel(18)).save_panel('o1', 'com.apple.TextEdit', commit_element_index=17)
        self.assertEqual(('save_panel_unavailable', 'not_started'), (mismatch['error'], mismatch['effect']))

    def test_exclusive_bounded_and_capability_gated(self):
        for kwargs in ({'window_element_index': 3, 'commit_element_index': 17},
                       {'commit_element_index': -1}, {'commit_element_index': True}, {}):
            with self.subTest(kwargs=kwargs):
                h = self.client(self.panel(17))
                self.assertEqual('save_panel_unavailable', h.save_panel('o1', 'com.apple.TextEdit', **kwargs)['error'])
                self.assertEqual([], self.sent(h))
        h = self.client(self.panel(17), caps=('evidence.save_panel',))
        self.assertEqual('save_panel_unavailable',
                         h.save_panel('o1', 'com.apple.TextEdit', commit_element_index=17)['error'])
        self.assertEqual([], self.sent(h))

    def test_window_index_path_is_unchanged(self):
        h = self.client(self.panel(5))
        h.save_panel('o1', 'com.apple.TextEdit', 3)
        sent = self.sent(h)[0]
        self.assertEqual(3, sent['window_element_index'])
        self.assertNotIn('commit_element_index', sent)


@unittest.skipUnless(sys.platform == 'darwin' and shutil.which('swift'), 'macOS Swift required')
class SwiftTests(unittest.TestCase):
    def run_swift(self, code):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'main.swift'
            path.write_text(code)
            result = subprocess.run(['swift', str(path)], capture_output=True, text=True, timeout=90)
        self.assertEqual(0, result.returncode, result.stderr[-3000:])
        return json.loads(result.stdout)

    def test_helper_routes_commit_button_to_its_window_without_observing(self):
        source = (ROOT / 'helper/HaejoHelper.swift').read_text()
        function = source[source.index('func readSavePanelForCommit('):]
        function = function[:function.index('\n}\n') + 3]
        code = r'''
import Foundation
typealias AXUIElement = Int
let kAXRoleAttribute = "AXRole", kAXButtonRole = "AXButton", kAXWindowRole = "AXWindow"
final class Abort { var isStopped = false }
let abortState = Abort()
var latestObsID = "o1", latestTargetName = "com.apple.TextEdit"
// 0 window, 1 sheet, 2 save button, 3 cancel button; 9 is not in the map.
var latestElements = [0, 1, 2, 3]
let parents = [1: 0, 2: 1, 3: 1, 7: 9]
let roles = [0: "AXWindow", 1: "AXSheet", 2: "AXButton", 3: "AXButton", 7: "AXButton", 9: "AXWindow"]
func str(_ el: Int, _ key: String) -> String? { roles[el] }
func axParentElement(_ el: Int) -> Int? { parents[el] }
func CFEqual(_ a: Int, _ b: Int) -> Bool { a == b }
func documentIsWholeNumber(_ raw: Any) -> NSNumber? {
 guard let n = raw as? NSNumber, CFGetTypeID(n) != CFBooleanGetTypeID(), n.doubleValue == Double(n.intValue) else { return nil }
 return n }
var forwarded: [[String: Any]] = []
var commitIndex = 2
func readSavePanel(_ msg: [String: Any], operationDeadline: Double? = nil) -> [String: Any] {
 forwarded.append(msg)
 return ["type": "save_panel", "commit_control": ["action": ["name": "click", "element_index": commitIndex]]]
}
''' + function + r'''
var out: [Any] = []
let base: [String: Any] = ["type": "save_panel", "target": "com.apple.TextEdit", "obs_id": "o1",
                           "commit_element_index": 2, "document_token": "t", "require_format": true]
out.append(readSavePanelForCommit(base)["type"] as Any)
out.append(forwarded.last.map { ($0["window_element_index"] as? Int ?? -1, $0["commit_element_index"] == nil) }.map { [$0.0, $0.1] } as Any)
commitIndex = 3
out.append(readSavePanelForCommit(base)["error"] as Any)           // panel's commit is another button
commitIndex = 2
var stale = base; stale["obs_id"] = "o0"
out.append(readSavePanelForCommit(stale)["error"] as Any)
var both = base; both["window_element_index"] = 0
out.append(readSavePanelForCommit(both)["error"] as Any)
var notButton = base; notButton["commit_element_index"] = 1
out.append(readSavePanelForCommit(notButton)["error"] as Any)
latestElements = [0, 1, 2, 3, 7]
var orphan = base; orphan["commit_element_index"] = 4             // its window is not in the map
out.append(readSavePanelForCommit(orphan)["error"] as Any)
out.append(forwarded.count)
print(String(data: try! JSONSerialization.data(withJSONObject: out), encoding: .utf8)!)
'''
        out = self.run_swift(code)
        self.assertEqual('save_panel', out[0])
        self.assertEqual([0, True], out[1], 'delegated with the button\'s window, selector removed')
        self.assertEqual(['save_panel_unavailable'] * 5, out[2:7])
        self.assertEqual(2, out[7], 'only the two well-formed requests reached readSavePanel')
        self.assertNotIn('observe(', function)
        self.assertIn('if msg["commit_element_index"] != nil { return readSavePanelForCommit(msg) }', source)
        self.assertIn('"evidence.save_panel.commit_selector"', source)

    def test_launcher_validator(self):
        source = (ROOT / 'launcher/haejo.swift').read_text()
        schema = source[source.index('let allowedTypes:'):source.index('// MARK: - Socket plumbing')]
        checks = r'''
let base: [String: Any] = ["type":"save_panel","target":"com.apple.TextEdit","obs_id":"o1"]
var rows: [[String: Any]] = []
var a = base; a["commit_element_index"] = 4; rows.append(a)
var b = base; b["window_element_index"] = 4; rows.append(b)
var c = base; c["commit_element_index"] = 4; c["window_element_index"] = 0; rows.append(c)
rows.append(base)
var d = base; d["commit_element_index"] = true; rows.append(d)
rows.append(["type":"observe","target":"x","commit_element_index":1])
print(String(data: try! JSONSerialization.data(withJSONObject: rows.map { vetted($0) == nil }), encoding: .utf8)!)
'''
        out = self.run_swift('import Foundation\nimport CoreFoundation\nfunc modelTimeout(_ raw:Any?)->Double? {1}\n'
                             + schema + checks)
        self.assertEqual([True, True, False, False, False, False], out)


if __name__ == '__main__':
    unittest.main()
