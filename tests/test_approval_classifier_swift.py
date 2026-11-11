"""The helper's own reading of which inputs need the person's answer (stage 2, S1)."""
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT/'tests/fixtures/approval_classifier.json'

PROBE = r'''
import Foundation
let data = try! Data(contentsOf: URL(fileURLWithPath: CommandLine.arguments[1]))
let rows = try! JSONSerialization.jsonObject(with: data) as! [[Any]]
var failed = 0
for row in rows {
    var input = ObservedInput(kind: row[0] as! String)
    input.role = row[1] as! String; input.subrole = row[2] as! String
    input.labels = row[3] as! [String]
    if row.count > 5 { input.defaultButtonLabels = row[5] as! [String] }
    if row.count > 6 { input.focusIsText = row[6] as! Bool }
    if row.count > 7 { input.pressable = row[7] as! Bool }
    if row.count > 8 { input.returnPressesDefault = row[8] as! Bool }
    let got = ApprovalClassifier.classify(input).rawValue
    if got != row[4] as! String { failed += 1; print("MISMATCH \(row) -> \(got)") }
}
print("checked \(rows.count) failed \(failed)")
exit(failed == 0 ? 0 : 1)
'''


@unittest.skipUnless(sys.platform == 'darwin' and shutil.which('swiftc'), 'macOS Swift toolchain')
class ApprovalClassifierTests(unittest.TestCase):
    def test_fixture_table(self):
        with tempfile.TemporaryDirectory() as d:
            main = Path(d)/'main.swift'; main.write_text(PROBE)
            binary = Path(d)/'probe'
            built = subprocess.run(['swiftc', str(main), str(ROOT/'helper/ApprovalClassifier.swift'), '-o', str(binary)],
                                   capture_output=True, text=True, timeout=180)
            self.assertEqual(0, built.returncode, built.stderr)
            run = subprocess.run([str(binary), str(FIXTURES)], capture_output=True, text=True, timeout=30)
            self.assertEqual(0, run.returncode, run.stdout + run.stderr)

    def test_fixtures_cover_every_class_and_kind(self):
        rows = json.loads(FIXTURES.read_text())
        self.assertEqual({'none', 'credential', 'financial', 'transmit', 'delete'}, {r[4] for r in rows})
        self.assertEqual({'press', 'text', 'return', 'menu', 'key', 'point'}, {r[0] for r in rows})

    def test_built_into_the_helper_and_not_yet_wired(self):
        self.assertIn('ApprovalClassifier.swift', (ROOT/'helper/build.sh').read_text())
        # Step 1 ships the classifier only: no dispatch path calls it yet, so
        # behaviour with the setting on or off is unchanged.
        for name in ('HaejoHelper.swift', 'WindowInput.swift', 'WindowDispatch.swift', 'HelperModes.swift'):
            self.assertNotIn('ApprovalClassifier.classify', (ROOT/'helper'/name).read_text())


if __name__ == '__main__':
    unittest.main()
