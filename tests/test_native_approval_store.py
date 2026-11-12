"""Stage 2 state: Keychain anchor + MAC'd snapshot, grants from native cards, R6 delegations."""
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]

PROBE = r'''
import Foundation
import AppKit
func check(_ ok: Bool, _ what: String) { if !ok { print("FAIL " + what); exit(1) } }

final class FakeKeychain: NativeAnchorKeychain {
    var stored: NativeAnchorRead = .missing
    var failWrites = false
    func read() -> NativeAnchorRead { stored }
    func write(_ data: Data) -> Bool { if failWrites { return false }; stored = .value(data); return true }
    func delete() { stored = .missing }
    var anchor: NativeApprovalStore.Anchor? {
        if case .value(let d) = stored { return try? JSONDecoder().decode(NativeApprovalStore.Anchor.self, from: d) }
        return nil
    }
}

let root = URL(fileURLWithPath: CommandLine.arguments[1])
let folder = root.appendingPathComponent("approvals")
let fm = FileManager.default

// Never enabled: off, no file is trusted.
let kc = FakeKeychain()
var s = NativeApprovalStore(folder: folder, keychain: kc)
check(!s.enforcing && s.health == .off, "missing anchor is off")

// Turning on: anchor epoch 1, marker present.
check(s.setEnforcing(true), "enable")
check(s.enforcing && kc.anchor?.epoch == 1 && kc.anchor?.enforcing == true, "anchor written \(String(describing: kc.anchor))")
check(fm.fileExists(atPath: s.markerURL.path), "marker written")
let g1 = NativeApprovalStore.Grant(key: "k1", scope: "always", expires: nil, label: "a")
check(s.add(g1) && s.matching("k1", allowed: ["always"]) != nil, "grant stored")
check(s.matching("k1", allowed: ["task"]) == nil, "scope respected")
let old = try! Data(contentsOf: s.snapshotURL)          // epoch 2 with k1
let g2 = NativeApprovalStore.Grant(key: "k2", scope: "task", expires: Date().addingTimeInterval(60).timeIntervalSince1970, label: "b")
check(s.add(g2), "second grant")
s = NativeApprovalStore(folder: folder, keychain: kc)
check(s.matching("k2", allowed: ["task"]) != nil && s.matching("k1", allowed: ["always"]) != nil, "reload keeps grants")

// An older file (replay) is stale; an edited file fails its MAC. Enforcement
// itself comes from the anchor, so it stays on.
try! old.write(to: s.snapshotURL)
s = NativeApprovalStore(folder: folder, keychain: kc)
check(s.enforcing && s.grants.isEmpty, "older snapshot ignored")
check(s.add(g1), "re-add")
var text = try! String(contentsOf: s.snapshotURL, encoding: .utf8)
text = text.replacingOccurrences(of: "\"k1\"", with: "\"forged\"")
try! text.write(to: s.snapshotURL, atomically: true, encoding: .utf8)
s = NativeApprovalStore(folder: folder, keychain: kc)
check(s.enforcing && s.grants.isEmpty, "edited snapshot ignored")

// Expired task grants do not match.
let past = NativeApprovalStore.Grant(key: "k3", scope: "task", expires: Date().addingTimeInterval(-1).timeIntervalSince1970, label: "c")
check(s.add(past) && s.matching("k3", allowed: ["task"]) == nil, "expired grant")

// A change that stopped after the next snapshot but before the anchor moved
// rolls forward on start.
let a = kc.anchor!
var next = NativeApprovalStore.Snapshot(epoch: a.epoch + 1, enforcing: true, grants: [g1, g2])
next.mac = NativeApprovalStore.mac(next, key: a.key)
try! JSONEncoder().encode(next).write(to: s.nextURL)
s = NativeApprovalStore(folder: folder, keychain: kc)
check(kc.anchor?.epoch == a.epoch + 1 && s.grants == [g1, g2], "roll forward")
check(!fm.fileExists(atPath: s.nextURL.path), "next consumed")
// A roll-forward whose Keychain write fails keeps the anchor's state.
let held = kc.anchor!
var offNext = NativeApprovalStore.Snapshot(epoch: held.epoch + 1, enforcing: false, grants: [])
offNext.mac = NativeApprovalStore.mac(offNext, key: held.key)
try! JSONEncoder().encode(offNext).write(to: s.nextURL)
kc.failWrites = true
s = NativeApprovalStore(folder: folder, keychain: kc)
check(s.enforcing && kc.anchor == held && s.grants == [g1, g2], "failed roll forward keeps anchor state")
kc.failWrites = false
try? fm.removeItem(at: s.nextURL)
// A next snapshot signed with another key is ignored.
var bogus = NativeApprovalStore.Snapshot(epoch: kc.anchor!.epoch + 1, enforcing: false, grants: [])
bogus.mac = NativeApprovalStore.mac(bogus, key: NativeApprovalStore.newKey())
try! JSONEncoder().encode(bogus).write(to: s.nextURL)
s = NativeApprovalStore(folder: folder, keychain: kc)
check(s.enforcing && kc.anchor?.epoch == a.epoch + 1, "forged next ignored")
try? fm.removeItem(at: s.nextURL)

// A Keychain write that fails leaves everything as it was.
kc.failWrites = true
check(!s.add(NativeApprovalStore.Grant(key: "k4", scope: "always", expires: nil, label: "")), "write failure reported")
check(s.matching("k4", allowed: ["always"]) == nil && !fm.fileExists(atPath: s.nextURL.path), "no partial change")
kc.failWrites = false

// Anchor unreadable (overwritten by another process): enforcing, no grants.
kc.stored = .unreadable
s = NativeApprovalStore(folder: folder, keychain: kc)
check(s.enforcing && s.health == .unreadable && s.matching("k1", allowed: ["always"]) == nil, "unreadable fails closed")
kc.stored = .value(Data("not json".utf8))
s = NativeApprovalStore(folder: folder, keychain: kc)
check(s.health == .unreadable, "garbage anchor unreadable")
// The person's switch replaces it.
check(s.setEnforcing(false) && !s.enforcing && kc.anchor == nil, "off replaces unreadable")
check(!fm.fileExists(atPath: s.markerURL.path), "marker removed")

// --- the menu app ---
let ckc = FakeKeychain()
let dir = root.appendingPathComponent("center")
let c = ApprovalCenter(directory: dir, keychain: ckc)
c.teamResolver = { _ in "TEAMID1234" }
let plan: [String:Any] = ["op":"plan", "request":["target":"com.apple.Safari", "items":[["step":1, "effects":["transmit"]]]], "wait":1]
// R6: delegations listed once; the confirmed ones become credential grants.
let creds = dir.appendingPathComponent("Credentials")
try! fm.createDirectory(at: creds, withIntermediateDirectories: true)
try! #"{"schema":1,"plan":{"target":"com.apple.Safari","origin":"https://login.example.com","level":"login"}}"#.write(to: creds.appendingPathComponent("grant-work.json"), atomically: true, encoding: .utf8)
try! #"{"schema":1,"plan":{"target":"com.apple.Safari","origin":"https://other.example.com","level":"fill"}}"#.write(to: creds.appendingPathComponent("grant-other.json"), atomically: true, encoding: .utf8)
var listed: [ApprovalCenter.Delegation] = []
check(c.setEnforcing(true, confirmDelegations: { listed = $0; return $0.filter { $0.name == "work" } }), "enable from switch")
check(listed.map(\.name) == ["other", "work"], "delegations listed \(listed)")
check(c.handle(plan)["status"] as? String == "native", "plan answers native while enforcing")
check(c.handle(["op":"runtime","target":"com.apple.Safari","question":"q","item":["step":2,"effects":["credential"]],"wait":1])["status"] as? String == "native", "runtime step answers native")
c.nativeWait = 1
let free = c.handle(["op":"runtime","target":"com.apple.Safari","question":"free question","wait":1])["status"] as? String
check(free != "native", "a question without a step still gets its card \(String(describing: free))")
c.nativeWait = 30

func ask(_ item: [String:Any], answer: ApprovalCenter.Choice?) -> (String, [ApprovalCenter.Choice]) {
    var reply: [String:Any] = [:]
    var offered: [ApprovalCenter.Choice] = []
    let done = DispatchSemaphore(value:0)
    DispatchQueue.global().async { reply = c.handle(["op":"native_check","item":item], helperPeer:true); done.signal() }
    if let answer {
        var entry: ApprovalCenter.Request?
        for _ in 0..<300 { entry = c.requests.values.first { $0.id.hasPrefix("nt_") && $0.status == "pending" }; if entry != nil { break }; usleep(10_000) }
        if let entry { offered = entry.nativeChoices ?? []; c.decide(entry, answer) }
    }
    done.wait()
    return (reply["status"] as? String ?? "", offered)
}
let login: [String:Any] = ["class":"credential", "kind":"text", "target":"com.apple.Safari", "team":"TEAMID1234",
                           "app_name":"Safari", "destination":"login.example.com"]
check(ask(login, answer: nil).0 == "allowed", "confirmed delegation runs without a card")
var otherLogin = login; otherLogin["destination"] = "other.example.com"
c.nativeWait = 1
check(ask(otherLogin, answer: nil).0 == "timeout", "unconfirmed delegation still asks")
var spoofed = login; spoofed["team"] = "OTHERTEAM1"
check(ask(spoofed, answer: nil).0 == "timeout", "other signer asks")
c.nativeWait = 30

let send: [String:Any] = ["class":"transmit", "kind":"press", "labels":["Send"], "target":"com.apple.Safari", "team":"TEAMID1234",
                          "app_name":"Safari", "destination":"mail.example.com", "commit":["recipient":"kim@example.com"]]
let (first, offered) = ask(send, answer: .always)
check(first == "allowed" && offered == [.once, .task, .always, .deny], "transmit card offers broader \(offered)")
check(ask(send, answer: nil).0 == "allowed", "always grant answers")
var another = send; another["commit"] = ["recipient":"lee@example.com"]
c.nativeWait = 1
check(ask(another, answer: nil).0 == "timeout", "grant is per recipient")
var blind = send; blind["destination"] = ""
let (_, blindOffer) = ask(blind, answer: .once)
check(blindOffer == [.once, .deny], "no destination, once only")
var pay = send; pay["class"] = "financial"
let (_, payOffer) = ask(pay, answer: .once)
check(payOffer == [.once, .deny], "financial once only")
var del = send; del["class"] = "delete"
let (_, delOffer) = ask(del, answer: .task)
check(delOffer == [.once, .task, .deny], "delete has no always \(delOffer)")
check(ask(del, answer: nil).0 == "allowed", "task grant answers delete")
// A choice the card did not offer is a refusal.
check(ask(pay, answer: .always).0 == "denied", "unoffered choice denied")
// Clearing always grants removes native grants too.
c.store.clearGrants()
check(ask(send, answer: nil).0 == "timeout", "cleared")
// Off from the switch: plan is ordinary again.
check(c.setEnforcing(false) && !c.store.enforcing, "disable")
print("ok")
'''


@unittest.skipUnless(sys.platform == 'darwin' and shutil.which('swiftc'), 'macOS Swift toolchain')
class NativeApprovalStoreTests(unittest.TestCase):
    def test_state_store_and_grants(self):
        with tempfile.TemporaryDirectory() as d:
            folder = Path(d)
            (folder/'main.swift').write_text(PROBE)
            binary = folder/'probe'
            built = subprocess.run(['swiftc', str(folder/'main.swift'), str(ROOT/'setup/ApprovalCenter.swift'),
                                    str(ROOT/'RuntimeStatus.swift'), '-o', str(binary)], capture_output=True, text=True, timeout=240)
            self.assertEqual(0, built.returncode, built.stderr)
            run = subprocess.run([str(binary), str(folder/'state')], capture_output=True, text=True, timeout=120)
            self.assertEqual('ok', run.stdout.strip(), run.stdout + run.stderr)


class NativeApprovalAnchorSourceTests(unittest.TestCase):
    def test_helper_reads_the_anchor_itself_without_prompting(self):
        client = (ROOT/'helper/NativeApprovalClient.swift').read_text()
        body = client[client.index('enum NativeApprovalAnchor'):]
        self.assertIn('kSecUseAuthenticationUIFail', body)
        self.assertIn('case .missing: return false', body)
        self.assertIn('case .unreadable: return true', body)
        self.assertNotIn('native-enabled', body)   # a file the agent can delete never turns it off
        self.assertIn('kSecReturnAttributes', body)
        self.assertIn('NativeApproval.enforcing = NativeApprovalAnchor.enforcing', (ROOT/'helper/HaejoHelper.swift').read_text())
        center = (ROOT/'setup/ApprovalCenter.swift').read_text()
        self.assertIn('kSecUseAuthenticationUIFail', center)
        self.assertIn('ai.callabo.haejo.native-approval', center)
        self.assertIn('ai.callabo.haejo.native-approval', body)

    def test_only_the_switch_turns_enforcement_on_or_off(self):
        activity = (ROOT/'setup/ActivityCenter.swift').read_text()
        self.assertIn('if (sender as AnyObject?) === approvalToggle,', activity)
        self.assertIn('!MenuApprovalHooks.setEnforcing(', activity)
        self.assertNotIn('ApprovalCenter', activity)   # built alone in some tests
        self.assertIn('ApprovalCenter.shared.setEnforcing(on)', (ROOT/'setup/main.swift').read_text())
        center = (ROOT/'setup/ApprovalCenter.swift').read_text()
        refresh = center[center.index('    func refresh() {'):center.index('    @discardableResult\n    func setEnforcing')]
        self.assertNotIn('setEnforcing', refresh)      # the preference file never changes it
        self.assertIn('on || store.enforcing', refresh)
        self.assertIn('ApprovalCenter.shared.trustHelper(helper)', (ROOT/'setup/main.swift').read_text())


if __name__ == '__main__':
    unittest.main()
