"""Stage 2 gate in the signed helper: off until enforcing, then decided from what the helper saw."""
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]

PROBE = r'''
import Foundation
func check(_ ok: Bool, _ what: String) { if !ok { print("FAIL " + what); exit(1) } }
var observed = 0
var asked: [ApprovalClass] = []
let send = { () -> ObservedInput in observed += 1; var i = ObservedInput(kind: "press"); i.role = "AXButton"; i.labels = ["Send"]; return i }
let save = { () -> ObservedInput in observed += 1; var i = ObservedInput(kind: "press"); i.role = "AXButton"; i.labels = ["Save"]; return i }
NativeApproval.bundleOf = { _ in "com.tinyspeck.slackmacgap" }
NativeApproval.decide = { _, cls, _, _ in asked.append(cls); return .denied }

// Off (the default): nothing is read, nothing asked, nothing refused.
check(NativeApproval.gate(name: "click", action: [:], pid: 1, observe: send) == nil, "off passes")
check(observed == 0 && asked.isEmpty, "off reads nothing")

NativeApproval.enforcing = { true }
check(NativeApproval.gate(name: "click", action: [:], pid: 1, observe: save) == nil, "unclassified passes")
check(asked.isEmpty, "unclassified asks nothing")
let denied = NativeApproval.gate(name: "click", action: [:], pid: 1, observe: send)
check(denied?["error"] as? String == "approval_denied" && denied?["effect"] as? String == "not_started", "denied refusal")
check(asked == [.transmit], "asked with the helper's class")
for (decision, error) in [(NativeDecision.timeout, "approval_timeout"), (.unavailable, "approval_unavailable"), (.targetChanged, "approval_target_changed")] {
    NativeApproval.decide = { _, _, _, _ in decision }
    check(NativeApproval.gate(name: "click", action: [:], pid: 1, observe: send)?["error"] as? String == error, error)
}
NativeApproval.decide = { _, _, _, _ in .allowed }
check(NativeApproval.gate(name: "click", action: [:], pid: 1, observe: send) == nil, "allowed dispatches")

// The card's wait is reported so act can move its input deadline.
NativeApproval.decide = { _, _, _, _ in usleep(200_000); return .allowed }
_ = NativeApproval.takeWaited()
var moved = 0.0
NativeApproval.onWaited = { moved += $0 }
check(NativeApproval.gate(name: "click", action: [:], pid: 1, observe: send) == nil, "allowed after wait")
check(moved >= 0.2 && NativeApproval.takeWaited() >= 0.2 && NativeApproval.takeWaited() == 0, "wait measured once")
// Allowed, but the caller left meanwhile: not dispatched.
NativeApproval.callerGone = { true }
check(NativeApproval.gate(name: "click", action: [:], pid: 1, observe: send)?["error"] as? String == "client_disconnected", "caller gone")
NativeApproval.callerGone = { false }
// Allowed, but the element is another one with the same label: not dispatched.
var flip = 0
let moving = { () -> ObservedInput in flip += 1; var i = ObservedInput(kind: "press"); i.role = "AXButton"; i.labels = ["Send"]; i.identity = "e\(flip)"; return i }
check(NativeApproval.gate(name: "click", action: [:], pid: 1, observe: moving)?["error"] as? String == "approval_target_changed", "other element")
NativeApproval.decide = { _, _, _, _ in .cancelled }
check(NativeApproval.gate(name: "click", action: [:], pid: 1, observe: send)?["error"] as? String == "client_disconnected", "cancelled decision")
NativeApproval.decide = { _, _, _, _ in .allowed }

// What is committed changed while the card was up (another body, other items): not dispatched.
var reads = 0
NativeApproval.commitReader = { _, _, _, _ in reads += 1; return CommitView(digest: "d\(reads)") }
check(NativeApproval.gate(name: "click", action: [:], pid: 1, observe: send)?["error"] as? String == "approval_target_changed", "commit changed")
NativeApproval.commitReader = { _, _, _, payload in CommitView(digest: payload ?? "-") }
var seen: CommitView?
NativeApproval.decide = { _, _, _, commit in seen = commit; return .allowed }
check(NativeApproval.gate(name: "type_text", action: ["text": "pw"], pid: 1, observe: { var i = ObservedInput(kind: "text"); i.role = "AXTextField"; i.subrole = "AXSecureTextField"; return i }) == nil, "credential allowed")
check(seen?.digest == "pw", "payload reaches the commit reading")
NativeApproval.commitReader = { _, _, _, _ in CommitView() }
NativeApproval.decide = { _, _, _, _ in .allowed }

// Haejo's own UI is refused even for an unclassified press.
NativeApproval.bundleOf = { _ in "open330.haejo.app" }
check(NativeApproval.gate(name: "click", action: [:], pid: 1, observe: save)?["error"] as? String == "haejo_ui_input_refused", "self UI")
check(NativeApproval.gate(name: "read", action: [:], pid: 1, observe: save) == nil, "reading own UI is fine")
// A menu is decided at its resolved item, not from the path strings.
NativeApproval.bundleOf = { _ in "com.apple.finder" }
NativeApproval.decide = { _, _, _, _ in .denied }
observed = 0
check(NativeApproval.gate(name: "menu", action: ["path": ["File", "Delete"]], pid: 1, observe: send) == nil, "menu deferred")
check(observed == 0, "menu entry reads nothing")
check(NativeApproval.gate(name: "select_option", action: ["option_label": "Pay"], pid: 1, observe: send) == nil && observed == 0, "option decided at its item only")

// Which input each action posts.
let kinds: [(String, [String: Any], String)] = [
    ("click", [:], "press"), ("double_click", [:], "press"), ("click_point", [:], "press"),
    ("secondary_action", ["action": "AXPress"], "press"), ("select_option", [:], "option"), ("select_custom_option", [:], "option"),
    ("set_value", [:], "text"), ("type_text", [:], "text"),
    ("press_key", ["key": "Return"], "return"), ("press_key", ["key": "Tab"], "key"),
    ("window_input", ["key": "Enter"], "return"), ("window_input", ["text": "hi"], "text"),
    ("menu", [:], "menu"), ("drag", [:], "point"), ("hover", [:], "point"), ("read", [:], "none"), ("scroll", [:], "none"),
]
for (name, action, want) in kinds { check(NativeApproval.kind(name: name, action: action) == want, "kind \(name) \(action)") }
check(NativeApproval.kind(name: "secondary_action", action: ["action": "AXConfirm"]) == "press", "confirm presses")
for a in ["AXShowMenu", "AXCancel", "AXIncrement"] { check(NativeApproval.kind(name: "secondary_action", action: ["action": a]) == "key", a) }
print("ok")
'''


@unittest.skipUnless(sys.platform == 'darwin' and shutil.which('swiftc'), 'macOS Swift toolchain')
class NativeApprovalGateTests(unittest.TestCase):
    def test_gate_decisions(self):
        with tempfile.TemporaryDirectory() as d:
            main = Path(d)/'main.swift'; main.write_text(PROBE)
            binary = Path(d)/'probe'
            built = subprocess.run(['swiftc', str(main), str(ROOT/'helper/NativeApproval.swift'),
                                    str(ROOT/'helper/ApprovalClassifier.swift'), '-o', str(binary)],
                                   capture_output=True, text=True, timeout=240)
            self.assertEqual(0, built.returncode, built.stderr)
            run = subprocess.run([str(binary)], capture_output=True, text=True, timeout=30)
            self.assertEqual('ok', run.stdout.strip(), run.stdout + run.stderr)


class NativeApprovalWiringTests(unittest.TestCase):
    def test_one_gate_after_resolution_before_dispatch(self):
        text = (ROOT/'helper/HaejoHelper.swift').read_text()
        body = text[text.index('func act(_ obsID: String'):]
        gate = body.index('NativeApproval.gate(')
        self.assertLess(body.index('mismatch(want, element: element(), pid: p)'), gate)
        self.assertLess(gate, body.index('    switch name {'))
        self.assertEqual(1, text.count('NativeApproval.gate('))
        # Menus: decided on the item menuItem() resolved, before any press.
        menu = body.index('menuItem(pid: p, path: path)')
        item_gate = body.index('NativeApproval.gateMenuItem(item, pid: p)')
        self.assertLess(menu, item_gate)
        self.assertLess(item_gate, body.index('AXUIElementPerformAction(item, kAXPressAction'))
        # Popup options: the item itself, right before its press, after the
        # open menu is recorded.
        for item, opened in (('matches[0]', 'true'), ('items[0]', 'false')):
            g = body.index(f'NativeApproval.gateOption({item}, pid: p, openedHere: {opened}, control: el)')
            self.assertLess(g, body.index(f'AXUIElementPerformAction({item}', g))
        pointer = body.index('NativeApproval.gateOption(chosen,pid:p,openedHere:false,control:el)')
        self.assertLess(pointer, body.index('let result=prepareBackgroundWindow(obsID,target,chosen', pointer))
        # A page's <select> takes the same gate inside its own route, before any press.
        web = body.index('webSelectOption(el, pid: p, want: want, obsID: obsID, name: name) { item in')
        self.assertLess(web, body.index('NativeApproval.gateOption(item, pid: p, openedHere: true, control: el)', web))
        web_route = (ROOT/'helper/WebInput.swift').read_text()
        choose = web_route[web_route.index('func choose(_ menu: AXUIElement)'):]
        self.assertLess(choose.index('gate(matches[0].item)'),
                        choose.index('AXUIElementPerformAction(matches[0].item, kAXPressAction as CFString)'))
        self.assertEqual(4, text.count('NativeApproval.gateOption('))
        custom = body.index('NativeApproval.gateOption(items[0]')
        self.assertLess(body.rindex('spentMenu = (pid: p, control: el, menu: menu,popupWindowID:pending.popupWindowID', 0, custom), custom)
        self.assertIn('NativeApproval.swift', (ROOT/'helper/build.sh').read_text())

    def test_python_records_native_refusals_as_gated(self):
        from haejo.flow import native_approval_refusal, NATIVE_APPROVAL_ERRORS
        for error in NATIVE_APPROVAL_ERRORS:
            self.assertEqual({'type': 'approval_refused', 'gate': error, 'effect': 'not_started'},
                             native_approval_refusal({'type': 'error', 'error': error, 'effect': 'not_started'}))
        # Anything that may have happened stays an ordinary error.
        self.assertEqual('error', native_approval_refusal({'type': 'error', 'error': 'approval_denied', 'effect': 'unknown'})['type'])
        self.assertEqual('error', native_approval_refusal({'type': 'error', 'error': 'action_failed', 'effect': 'not_started'})['type'])
        text = (ROOT/'haejo/flow.py').read_text()
        self.assertEqual(2, text.count('r = native_approval_refusal(r)'))


if __name__ == '__main__':
    unittest.main()
