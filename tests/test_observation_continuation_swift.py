"""The helper's real walk + continuation source, compiled against a synthetic AX tree.

No app, window, helper process or input: AXUIElement is an Int and every
system call is a stub. The same fixture as the Python driver's tests.
"""
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


def segment(source, start, end):
    begin = source.index(start)
    return source[begin:source.index(end, begin)]


def parents(lines, elements):
    stack, result = [], {}
    for line in lines:
        head = line.lstrip().split()
        if not head or not head[0].isdigit():
            continue
        depth = len(line) - len(line.lstrip())
        node = elements[int(head[0])]
        while stack and stack[-1][0] >= depth:
            stack.pop()
        result[node] = stack[-1][1] if stack else None
        stack.append((depth, node))
    return result


STUBS = r'''
import Foundation
typealias AXUIElement = Int
typealias CGWindowID = UInt32
var maxTreeNodes = 2500
let maxChildrenPerNode = 60
let kAXRoleAttribute = "AXRole"
let kAXWindowRole = "AXWindow"
let kAXEnabledAttribute = "AXEnabled"
let kAXSelectedAttribute = "AXSelected"
let kAXChildrenAttribute = "AXChildren"
let kAXParentAttribute = "AXParent"
let truncationMark = "… (트리가 커서 여기서 잘렸습니다 — 더 좁은 창/앱을 대상으로 하세요)"
let interactableRoles: Set<String> = ["AXWindow", "AXButton"]
var graph: [Int: [Int]] = [0: Array(1...150), 70: [1001, 1002, 1003]]
func parentOf(_ node: Int) -> Int? { graph.first(where: { $0.value.contains(node) })?.key }
func CFEqual(_ a: Int, _ b: Int) -> Bool { a == b }
struct ObservationNodeSnapshot {
 init?(_ node: Int) { return nil }
 func string(_ name: String) -> String? { nil }
 func value(_ name: String) -> Any? { nil }
 func label(role: String, quoteValues: Bool) -> String { "" }
}
final class ObservationReadMetrics {
 var packetAttempts = 0, packetFallbacks = 0, secondaryActionReads = 0
 var packetNanos: UInt64 = 0, secondaryActionNanos: UInt64 = 0
 var metadata: [String: Any] { [:] }
}
final class ObservationRevealScan {
 var complete = true; var revealed = 0
 var available: Bool { false }
 func matches(_ node: Int) -> Bool { false }
}
func str(_ node: Int, _ key: String) -> String? {
 if key == "AXDocument" { return node == 0 ? "file:///tmp/pinned.txt" : nil }
 return key == "AXRole" ? (node == 0 ? "AXWindow" : graph[node] != nil ? "AXGroup" : "AXButton") : nil
}
func label(_ node: Int, quoteValues: Bool) -> String { "Title: fixture-\(node)" }
func attr(_ node: Int, _ key: String) -> Any? {
 if key == "AXChildren" { return graph[node] ?? [] }
 if key == "AXEnabled" { return true }
 return nil
}
func axParentElement(_ node: Int) -> Int? { parentOf(node) }
func secondaryActionsOf(_ node: Int) -> [String] { [] }
func windowControlElement(_ node: Int, _ key: String) -> Int? { nil }
var readSecondaryActions = true
var walkSeen: Set<Int>? = nil
func documentURLSyntaxPath(_ text: String) -> String? { text.hasPrefix("file://") ? String(text.dropFirst(7)) : nil }
func quotedLabelValue(_ text: String) -> String? { "\"" + text + "\"" }
struct Scope { let id: CGWindowID }
final class ParallelWindowState { static let shared = ParallelWindowState(); var current: Scope? = nil }
final class Abort { var isStopped = false }
let abortState = Abort()
var latestObsID = "", latestTargetName = "", latestDocumentToken: String? = nil
var latestElements: [Int] = [], latestTargetPID: pid_t = -1, latestProcessStart: Double? = nil
var launch: Double = 111
func pid(forBundle bundle: String) -> pid_t? { 42 }
func nativeProcessStartIdentity(_ pid: pid_t) -> Double? { launch }
func documentWindowForToken(_ target: String, _ token: String) throws -> Int { 0 }
func ensureVisibleControl(forPID pid: pid_t, windowless: Bool) -> Bool { true }
func indicatorRefusal() -> [String: Any] { ["type": "error", "error": "indicator"] }
func customSelects(_ p: pid_t, _ elements: [Int], obsID: String, candidates: [Int]) -> [String: Any] { [:] }
'''

DRIVER = r'''
func firstObservation() -> [String: Any] {
 var lines: [String] = [], elements: [Int] = [], visited = 0, truncated = false
 var entries: [(window: AXUIElement, omission: ObservationOmission)] = []
 var pending: [(Int, Int)] = []
 walkSeen = []
 observationOmission = { entries.append((window: 0, omission: $0)) }
 walk(0, depth: 0, out: &lines, elements: &elements, visited: &visited, truncated: &truncated,
      nodeLimit: maxTreeNodes, deferred: { pending.append(($0, $1)) })
 observationOmission = nil; walkSeen = nil
 entries += pending.map { (window: 0, omission: .node($0.0, depth: $0.1)) }
 latestObsID = "s-first"; latestElements = elements; latestTargetPID = 42
 latestProcessStart = launch; latestTargetName = "app"; latestDocumentToken = nil
 let cursor = issueContinuation(entries, obsID: "s-first", target: "app", pid: 42,
                                processStart: launch, documentToken: nil, page: 0)
 return ["lines": lines, "elements": elements, "cursor": cursor as Any? ?? NSNull()]
}
func pages(_ first: [String: Any]) -> [[String: Any]] {
 var out: [[String: Any]] = []
 var cursor = first["cursor"] as? String
 while let current = cursor, out.count < 20 {
  var page = observeContinuation("app", cursor: current, documentToken: nil)
  page["elements"] = latestElements
  out.append(page)
  cursor = page["next_observation_cursor"] as? String
 }
 return out
}
var report: [String: Any] = [:]
let first = firstObservation()
report["first"] = first
report["pages"] = pages(first)
// Single use, then refusal when the list changed or the process did.
let again = firstObservation()
_ = observeContinuation("app", cursor: again["cursor"] as! String, documentToken: nil)
report["reuse"] = observeContinuation("app", cursor: again["cursor"] as! String, documentToken: nil)["error"]
let changing = firstObservation()
graph[0] = Array(1...151)
report["stale"] = observeContinuation("app", cursor: changing["cursor"] as! String, documentToken: nil)["error"]
graph[0] = Array(1...150)
let moved = firstObservation()
launch = 222
report["process"] = observeContinuation("app", cursor: moved["cursor"] as! String, documentToken: nil)["error"]
launch = 111
let other = firstObservation()
report["target"] = observeContinuation("other", cursor: other["cursor"] as! String, documentToken: nil)["error"]
let replaced = firstObservation()
latestObsID = "s-newer"
report["newer"] = observeContinuation("app", cursor: replaced["cursor"] as! String, documentToken: nil)["error"]
// Node budget: a deep tree across several pages.
graph = [0: [1, 2, 3, 4, 5]]
for i in 1...5 { graph[i] = (1...5).map { 10 * i + $0 } }
maxTreeNodes = 12
let deep = firstObservation()
report["deep_first"] = deep
report["deep_pages"] = pages(deep)
print(String(data: try! JSONSerialization.data(withJSONObject: report), encoding: .utf8)!)
'''


@unittest.skipUnless(sys.platform == 'darwin' and shutil.which('swift'), 'macOS Swift required')
class SwiftContinuationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        source = (ROOT / 'helper/HaejoHelper.swift').read_text()
        walker = source[source.index('func walk(_ el: AXUIElement, depth: Int, out:'):]
        walker = walker[:walker.index('\n}\n') + 3]
        omission = segment(source, '/// What an observation left unread', '// MARK: - Session state')
        state = segment(source, '/// The most a continuation remembers.', '// Only the newest observation is actionable.')
        functions = segment(source, '/// Keep what an observation left unread, behind an opaque single-use id.',
                            'func observe(_ target: String, requireWindow')
        script = STUBS + omission + state + walker + functions + DRIVER
        with tempfile.TemporaryDirectory(prefix='haejo-continuation-') as directory:
            path = Path(directory) / 'main.swift'
            path.write_text(script)
            run = subprocess.run(['swift', str(path)], capture_output=True, text=True, timeout=120)
        if run.returncode != 0:
            raise AssertionError(run.stderr[-4000:])
        cls.report = json.loads(run.stdout)

    def graph_parent(self, node, deep=False):
        if deep:
            graph = {0: [1, 2, 3, 4, 5], **{i: [10 * i + j for j in range(1, 6)] for i in range(1, 6)}}
        else:
            graph = {0: list(range(1, 151)), 70: [1001, 1002, 1003]}
        return next((p for p, kids in graph.items() if node in kids), None)

    def coverage(self, first, pages, deep=False):
        seen = set(first['elements'])
        for page in pages:
            self.assertEqual('observation', page['type'], page)
            lines = page['tree'].splitlines()
            elements = page['elements']
            indices = [int(l.split()[0]) for l in lines if l.split() and l.split()[0].isdigit()]
            self.assertEqual(list(range(len(elements))), sorted(indices))
            for node, parent in parents(lines, elements).items():
                self.assertEqual(self.graph_parent(node, deep), parent)
            seen |= set(elements)
        return seen

    def test_cap_pages_cover_everything_with_parent_context(self):
        r = self.report
        self.assertEqual([0, *range(1, 61)], r['first']['elements'])
        seen = self.coverage(r['first'], r['pages'])
        self.assertEqual({0, *range(1, 151), 1001, 1002, 1003}, seen)
        ids = [p['obs_id'] for p in r['pages']]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertNotIn('next_observation_cursor', r['pages'][-1])
        self.assertFalse(r['pages'][-1]['truncated'])
        self.assertTrue(all(p['elements'][0] == 0 for p in r['pages']), 'window context first')

    def test_page_window_context_names_the_same_document(self):
        r = self.report
        first = next(l for l in r['first']['lines'] if l.startswith('0 Window'))
        self.assertIn('Document: "/tmp/pinned.txt"', first)
        for page in r['pages']:
            self.assertEqual(first, next(l for l in page['tree'].splitlines() if l.startswith('0 Window')))

    def test_node_budget_pages_cover_deep_tree(self):
        r = self.report
        seen = self.coverage(r['deep_first'], r['deep_pages'], deep=True)
        self.assertEqual({0, 1, 2, 3, 4, 5, *[10 * i + j for i in range(1, 6) for j in range(1, 6)]}, seen)
        self.assertGreater(len(r['deep_pages']), 1)

    def test_refusals(self):
        r = self.report
        self.assertEqual('continuation_unknown_or_expired', r['reuse'])
        self.assertEqual('continuation_stale', r['stale'])
        self.assertEqual('continuation_target_changed', r['process'])
        self.assertEqual('continuation_unknown_or_expired', r['target'])
        self.assertEqual('continuation_unknown_or_expired', r['newer'])


class ContinuationWiringSourceTests(unittest.TestCase):
    def test_any_action_retires_and_observe_routes_continuation(self):
        source = (ROOT / 'helper/HaejoHelper.swift').read_text()
        act = source[source.index('    case "act":'):]
        self.assertIn('latestContinuation = nil', act[:act.index('var sensitiveInputAuthorized')])
        observe = source[source.index('    case "observe":'):source.index('    case "act":')]
        self.assertIn('return observeContinuation(', observe)
        self.assertIn('"observe.continuation_v1"', source)
        launcher = (ROOT / 'launcher/haejo.swift').read_text()
        self.assertIn('"continuation"]', launcher)
        self.assertIn('guard type == "observe", msg["reveal"] == nil, msg["window_identity"] == nil', launcher)


if __name__ == '__main__':
    unittest.main()
