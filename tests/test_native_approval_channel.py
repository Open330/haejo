"""Stage 2 channel: the menu app answers native_check only for the signed helper, from what the helper read."""
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
let c = ApprovalCenter(directory: URL(fileURLWithPath: CommandLine.arguments[1]))
let item: [String:Any] = ["class":"transmit", "kind":"press", "role":"AXButton", "labels":["Send"], "target":"com.tinyspeck.slackmacgap",
                          "app_name":"Slack", "team":"BQR82RBBHL", "window":"#team", "pid":42]
// Python (or anything not the signed helper) cannot ask about native input.
check(c.handle(["op":"native_check","item":item])["status"] as? String == "refused", "not helper refused")
check(c.handle(["op":"native_check","item":["class":"nonsense"]], helperPeer:true)["status"] as? String == "invalid", "invalid class")
check(ApprovalCenter.nativeDescribe(item) == "전송: 'Send' (Slack)\n창: #team", "card text \(ApprovalCenter.nativeDescribe(item))")
check(ApprovalCenter.sensitive(["class":"financial"]) && ApprovalCenter.sensitive(["class":"credential"]) && !ApprovalCenter.sensitive(item), "sensitive classes")

func answered(_ choice: ApprovalCenter.Choice?) -> String {
    var reply: [String:Any] = [:]
    let done = DispatchSemaphore(value:0)
    DispatchQueue.global().async { reply = c.handle(["op":"native_check","item":item], helperPeer:true); done.signal() }
    if let choice {
        var entry: ApprovalCenter.Request?
        for _ in 0..<200 { entry = c.requests.values.first { $0.id.hasPrefix("nt_") && $0.status == "pending" }; if entry != nil { break }; usleep(10_000) }
        check(entry != nil, "card request exists")
        check((entry!.items.first?["describe"] as? String)?.hasPrefix("전송: 'Send'") == true, "card from helper item")
        c.decide(entry!, choice)
    }
    done.wait()
    return reply["status"] as? String ?? ""
}
check(answered(.once) == "allowed", "once allows")
check(answered(.deny) == "denied", "deny denies")
c.nativeWait = 1
check(answered(nil) == "timeout", "no answer times out")
check(!c.requests.keys.contains { $0.hasPrefix("nt_") }, "native requests are not kept")
// The helper dropped the request (Esc / its caller left): the wait ends, nothing is kept.
var gone = false
var dropped: [String:Any] = [:]
c.nativeWait = 30
let finished = DispatchSemaphore(value:0)
DispatchQueue.global().async { dropped = c.handle(["op":"native_check","item":item], helperPeer:true, callerGone:{ gone }); finished.signal() }
usleep(300_000); gone = true
check(finished.wait(timeout:.now() + 5) == .success, "cancel ends the wait promptly")
check(dropped["status"] as? String == "cancelled", "cancelled status \(dropped)")
check(!c.requests.keys.contains { $0.hasPrefix("nt_") }, "cancelled request dropped")
// A native answer creates no grant: the next identical input asks again.
c.nativeWait = 1
check(answered(nil) == "timeout", "no grant from once")
print("ok")
'''


@unittest.skipUnless(sys.platform == 'darwin' and shutil.which('swiftc'), 'macOS Swift toolchain')
class NativeApprovalChannelTests(unittest.TestCase):
    def test_menu_app_native_check(self):
        with tempfile.TemporaryDirectory() as d:
            folder = Path(d)
            (folder/'main.swift').write_text(PROBE)
            binary = folder/'probe'
            built = subprocess.run(['swiftc', str(folder/'main.swift'), str(ROOT/'setup/ApprovalCenter.swift'),
                                    str(ROOT/'RuntimeStatus.swift'), '-o', str(binary)], capture_output=True, text=True, timeout=240)
            self.assertEqual(0, built.returncode, built.stderr)
            run = subprocess.run([str(binary), str(folder/'state')], capture_output=True, text=True, timeout=60)
            self.assertEqual('ok', run.stdout.strip(), run.stdout + run.stderr)


class NativeApprovalChannelSourceTests(unittest.TestCase):
    def test_both_ends_authenticate_by_signature(self):
        client = (ROOT/'helper/NativeApprovalClient.swift').read_text()
        # The helper checks the listener before sending anything.
        self.assertLess(client.index('PeerAuth.satisfies(fd: fd, requirement: requirement)'), client.index('write(fd'))
        self.assertIn('ai.callabo.haejo.setup.standalone.preview', client)
        center = (ROOT/'setup/ApprovalCenter.swift').read_text()
        self.assertIn('identifier \\"ai.callabo.haejo.helper\\"', center)
        self.assertIn('LOCAL_PEERTOKEN', center)
        helper = (ROOT/'helper/HaejoHelper.swift').read_text()
        self.assertIn('NativeApproval.decide = NativeApprovalClient.check', helper)
        self.assertIn('NativeApprovalClient.swift', (ROOT/'helper/build.sh').read_text())

    def test_wait_is_interruptible_and_answer_rechecked(self):
        client = (ROOT/'helper/NativeApprovalClient.swift').read_text()
        self.assertIn('NativeApproval.callerGone()', client)
        parallel = (ROOT/'helper/ParallelWindows.swift').read_text()
        self.assertLess(parallel.index('NativeApproval.callerGone=cancelled'), parallel.index('var reply=handle(msg)'))
        center = (ROOT/'setup/ApprovalCenter.swift').read_text()
        self.assertIn('SO_NOSIGPIPE', center)
        self.assertIn('timer.invalidate(); watch.invalidate()', center)
        self.assertNotIn('ai.callabo.haejo.setup.preview"', client)   # dev preview is not an approver
        helper = (ROOT/'helper/HaejoHelper.swift').read_text()
        body = helper[helper.index('func act(_ obsID: String'):]
        self.assertIn('var deadline = min(clickDeadline', body)
        self.assertEqual(5, body.count('waitedForCard()') - 1)
        self.assertIn('menuDeadline = min(callerDeadline,', body)
        self.assertNotIn('min(clickDeadline ?? .infinity, ProcessInfo.processInfo.systemUptime + 10)', body)
        gate = (ROOT/'helper/NativeApproval.swift').read_text()
        self.assertIn('reobserve() == input && context(pid) == before', gate)


if __name__ == '__main__':
    unittest.main()
