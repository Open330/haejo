"""Menu approval decisions in the Haejo menu app, without showing a card."""
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]

PROBE = r'''
import Foundation
import AppKit
func check(_ ok: Bool, _ what: String) { if !ok { print("FAIL " + what); exit(1) } }
let dir = URL(fileURLWithPath: CommandLine.arguments[1])
let c = ApprovalCenter(directory: dir)
var team: String? = "TEAMA"
c.teamResolver = { _ in team }
func item(_ step: Int, _ effects: [String], dest: String = "slack:#team", object: String = "message",
          rev: String = "reversible", digest: String = "d") -> [String:Any] {
    ["step":step, "effects":effects, "destination":dest, "object_type":object, "reversibility":rev,
     "describe":"메시지를 전송합니다", "payload_digest":digest + String(step)]
}
func request(_ items: [[String:Any]], flow: String = "f1", task: String = "T1") -> [String:Any] {
    ["flow_digest":flow, "params_digest":"p", "target":"com.tinyspeck.slackmacgap", "items":items, "task_hint":task]
}
// Planning with no grant waits for the person; a short wait reports pending.
let planned = c.handle(["op":"plan", "request":request([item(2,["transmit"])]), "wait":1])
check(planned["status"] as? String == "pending", "pending without grant \(planned)")
let id = planned["approval_id"] as! String
check(id.hasPrefix("ap_"), "approval id")
// Resume checks the request is the same one.
check(c.handle(["op":"resume","approval_id":id,"request":request([item(2,["transmit"])], flow:"other")])["status"] as? String == "mismatch", "resume mismatch")
check(c.handle(["op":"claim","approval_id":id,"run_id":"r1"])["reason"] as? String == "pending", "no claim while pending")
// A changed contract on resume (another effect or recipient) is a different request.
check(c.handle(["op":"resume","approval_id":id,"request":request([item(2,["transmit","financial"])])])["status"] as? String == "mismatch", "resume effects mismatch")
check(c.handle(["op":"resume","approval_id":id,"request":request([item(2,["transmit"], dest:"slack:#other")])])["status"] as? String == "mismatch", "resume recipient mismatch")
// The person allows this run only.
c.decide(c.requests[id]!, .once)
check(c.handle(["op":"resume","approval_id":id,"request":request([item(2,["transmit"])])])["status"] as? String == "allowed", "resume allowed")
check(c.handle(["op":"claim","approval_id":id,"run_id":"r1"])["ok"] as? Bool == true, "first claim")
check(c.handle(["op":"claim","approval_id":id,"run_id":"r2"])["reason"] as? String == "claimed", "second claim refused")
check(c.handle(["op":"consume","approval_id":id,"run_id":"r2","step":2,"payload_digest":"d2"])["ok"] as? Bool == false, "other run cannot consume")
check(c.handle(["op":"consume","approval_id":id,"run_id":"r1","step":2,"payload_digest":"x"])["reason"] as? String == "mismatch", "payload must match")
check(c.handle(["op":"consume","approval_id":id,"run_id":"r1","step":2,"payload_digest":"d2"])["ok"] as? Bool == true, "consume once")
check(c.handle(["op":"consume","approval_id":id,"run_id":"r1","step":2,"payload_digest":"d2"])["reason"] as? String == "consumed", "once is once")
// A task grant answers the next matching plan at once, without a card.
let p2 = c.handle(["op":"plan", "request":request([item(1,["transmit"])], flow:"f2"), "wait":1])
c.decide(c.requests[p2["approval_id"] as! String]!, .task)
let p3 = c.handle(["op":"plan", "request":request([item(4,["transmit"])], flow:"f3"), "wait":30])
check(p3["status"] as? String == "allowed" && p3["scope"] as? String == "grant", "task grant passes at once \(p3)")
// It belongs to the task that asked: another task, or a request without one, gets a card.
check(c.handle(["op":"plan","request":request([item(4,["transmit"])], flow:"f3b", task:"T2"),"wait":1])["status"] as? String == "pending", "other task asks")
check(ApprovalCenter.choices([item(1,["transmit"])], task:false) == [.once, .always, .deny], "no task choice without a task")
// The same bundle signed by another team is another app.
team = "TEAMB"
check(c.handle(["op":"plan","request":request([item(4,["transmit"])], flow:"f3c"),"wait":1])["status"] as? String == "pending", "other team asks")
// An app Haejo cannot pin to one team (copies from different teams, a name) gets no broad grant.
team = nil
check(c.handle(["op":"plan","request":request([item(4,["transmit"])], flow:"f3e"),"wait":1])["status"] as? String == "pending", "unidentified asks")
check(ApprovalCenter.choices([item(1,["transmit"])], identified:false) == [.once, .deny], "unidentified choices")
team = "TEAMA"
// A broad grant still spends each step once, inside one serial check.
let g = c.handle(["op":"plan","request":request([item(5,["transmit"])], flow:"f3d"),"wait":30])
let gid = g["approval_id"] as! String
check(c.handle(["op":"claim","approval_id":gid,"run_id":"g1"])["ok"] as? Bool == true, "grant claim")
check(c.handle(["op":"consume","approval_id":gid,"run_id":"g1","step":5,"payload_digest":"d5"])["ok"] as? Bool == true, "grant consume")
check(c.handle(["op":"consume","approval_id":gid,"run_id":"g1","step":5,"payload_digest":"d5"])["reason"] as? String == "consumed", "grant consume once")
_ = c.handle(["op":"finish","approval_id":gid,"run_id":"g1","outcome":"completed"])
check(c.handle(["op":"consume","approval_id":gid,"run_id":"g1","step":5,"payload_digest":"d5"])["ok"] as? Bool == false, "no consume after finish")
// Credential entry is never covered by a broader grant.
check(ApprovalCenter.choices([item(1,["write_ephemeral","credential"])]) == [.once, .deny], "credential choices")
// The grant does not stretch to another effect, destination or object type.
for other in [item(1,["delete"]), item(1,["transmit"], dest:"slack:#other"), item(1,["transmit"], object:"file")] {
    check(c.handle(["op":"plan","request":request([other], flow:"f4"),"wait":1])["status"] as? String == "pending", "no widening \(other)")
}
// Payments are never covered by a broader grant and the card offers only once/deny.
check(ApprovalCenter.choices([item(1,["financial"])]) == [.once, .deny], "financial choices")
check(ApprovalCenter.choices([item(1,["delete"], rev:"irreversible")]) == [.once, .task, .deny], "irreversible delete has no always")
check(ApprovalCenter.choices([item(1,["transmit"])]) == [.once, .task, .always, .deny], "transmit choices")
let pay = c.handle(["op":"plan","request":request([item(1,["financial"])], flow:"f5"),"wait":1])
c.decide(c.requests[pay["approval_id"] as! String]!, .task)
check(c.handle(["op":"plan","request":request([item(1,["financial"])], flow:"f6"),"wait":1])["status"] as? String == "pending", "payment asks every time")
// Always grants persist in the app's own file and can be cleared.
let a = c.handle(["op":"plan","request":request([item(1,["transmit"], dest:"mail:a@b")], flow:"f7"),"wait":1])
c.decide(c.requests[a["approval_id"] as! String]!, .always)
check(ApprovalCenter(directory: dir).loadAlways().count == 1, "always persisted")
c.saveAlways([])
check(c.handle(["op":"plan","request":request([item(1,["transmit"], dest:"mail:a@b")], flow:"f8"),"wait":1])["status"] as? String == "pending", "cleared always asks again")
// A denied request cannot be claimed.
let d = c.handle(["op":"plan","request":request([item(1,["transmit"], dest:"x")], flow:"f9"),"wait":1])
c.decide(c.requests[d["approval_id"] as! String]!, .deny)
check(c.handle(["op":"claim","approval_id":d["approval_id"] as! String,"run_id":"r9"])["reason"] as? String == "denied", "denied not claimable")
// There is no operation that decides.
check(c.handle(["op":"decide","approval_id":id,"choice":"always"])["status"] as? String == "invalid", "no decide op")
print("ok")
'''


@unittest.skipUnless(sys.platform == 'darwin', 'menu app is macOS')
class MenuApprovalSwiftTests(unittest.TestCase):
    def test_grants_claims_and_single_use(self):
        with tempfile.TemporaryDirectory(prefix='haejo-approval-') as folder:
            folder = Path(folder)
            (folder/'main.swift').write_text(PROBE)
            binary = folder/'probe'
            built = subprocess.run(['swiftc', str(folder/'main.swift'), str(ROOT/'setup/ApprovalCenter.swift'),
                                    str(ROOT/'RuntimeStatus.swift'), '-o', str(binary)],
                                   capture_output=True, text=True, timeout=240)
            self.assertEqual(0, built.returncode, built.stderr)
            state = folder/'state'; state.mkdir()
            run = subprocess.run([str(binary), str(state)], capture_output=True, text=True, timeout=120)
            self.assertEqual('ok', run.stdout.strip().splitlines()[-1] if run.stdout.strip() else run.stderr, run.stdout + run.stderr)

    def test_source_keeps_decisions_inside_the_app(self):
        text = (ROOT/'setup/ApprovalCenter.swift').read_text()
        handle = text.split('func handle(_ message:', 1)[1].split('\n    }\n', 1)[0]
        self.assertNotIn('"decide"', handle)
        self.assertIn('getpeereid', text)
        self.assertIn('chmod(path, 0o600)', text)
        main = (ROOT/'setup/main.swift').read_text()
        self.assertIn('ApprovalCenter.shared.refresh()', main)


if __name__ == '__main__':
    unittest.main()
