"""R7: the helper's reading of what an input commits (pure parts)."""
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
for t in ["₩12,000", "$12.00", "12,000원", "€ 9", "1,200円", "USD 5"] { check(NativeCommit.looksLikeAmount(t), "amount \(t)") }
for t in ["12", "Order 12345", "2026-11-11", "", "결제하기"] { check(!NativeCommit.looksLikeAmount(t), "not amount \(t)") }
check(NativeCommit.digest(["a", "b"]) == NativeCommit.digest(["a", "b"]), "stable digest")
check(NativeCommit.digest(["a", "b"]) != NativeCommit.digest(["ab"]), "separated digest")
check(NativeCommit.digest(["x"]).count == 64, "sha256 hex")
check(NativeCommit.digest(["a\u{1e}b"]) != NativeCommit.digest(["a", "b"]), "no separator collision")
check(NativeCommit.digest([["hint|", "hello"]]) != NativeCommit.digest([["hint", "|hello"]]), "no field boundary collision")
// Nothing to read (no window): every needed part is named unreadable.
let none = NativeCommit.read(.transmit, anchor: nil, pid: 0, payload: nil)
check(none.unreadable.contains("body") && none.unreadable.contains("failed") && none.summary.isEmpty, "unreadable body \(none)")
let pay = NativeCommit.read(.financial, anchor: nil, pid: 0, payload: nil)
check(pay.unreadable.contains("amount") && pay.unreadable.contains("site") && pay.destination.isEmpty, "unreadable payment")
let typed = NativeCommit.read(.credential, anchor: nil, pid: 0, payload: "a")
check(typed.digest != NativeCommit.read(.credential, anchor: nil, pid: 0, payload: "b").digest, "payload in digest")
print("ok")
'''


@unittest.skipUnless(sys.platform == 'darwin' and shutil.which('swiftc'), 'macOS Swift toolchain')
class NativeCommitTests(unittest.TestCase):
    def test_pure_parts(self):
        with tempfile.TemporaryDirectory() as d:
            main = Path(d)/'main.swift'; main.write_text(PROBE)
            binary = Path(d)/'probe'
            built = subprocess.run(['swiftc', str(main), str(ROOT/'helper/NativeCommit.swift'), str(ROOT/'helper/NativeApproval.swift'),
                                    str(ROOT/'helper/ApprovalClassifier.swift'), '-o', str(binary)], capture_output=True, text=True, timeout=240)
            self.assertEqual(0, built.returncode, built.stderr)
            run = subprocess.run([str(binary)], capture_output=True, text=True, timeout=30)
            self.assertEqual('ok', run.stdout.strip(), run.stdout + run.stderr)

    def test_wired_and_rechecked(self):
        gate = (ROOT/'helper/NativeApproval.swift').read_text()
        self.assertIn('commitReader(cls, anchor(), pid, payload).digest == commit.digest', gate)
        helper = (ROOT/'helper/HaejoHelper.swift').read_text()
        self.assertIn('NativeApproval.commitReader = NativeCommit.read', helper)
        self.assertIn('NativeCommit.swift', (ROOT/'helper/build.sh').read_text())
        # Secure field values are never read into the digest or the card.
        commit = (ROOT/'helper/NativeCommit.swift').read_text()
        self.assertIn('secure ? "" :', commit)
        self.assertIn('if string(el, kAXSubroleAttribute as String) == "AXSecureTextField" { return nil }', commit)
        # Every read spends the one budget and lowers the AX timeout to what is left.
        # Every AX call first lowers that element's timeout to the time left.
        self.assertIn('AXUIElementSetMessagingTimeout(el, Float(left)) != .success', commit)
        self.assertEqual(1, commit.count('AXUIElementCopyAttributeValue('))
        self.assertIn('if all.count > NativeCommit.maxList { truncated = true }', commit)
        self.assertIn('[cls.rawValue, host, walk.content, unreadable]', commit)
        self.assertIn('walk.content.append(["document", document])', commit)
        self.assertIn('anchor: { control }', gate)


if __name__ == '__main__':
    unittest.main()
