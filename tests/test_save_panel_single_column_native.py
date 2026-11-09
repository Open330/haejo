"""Actual owned NSSavePanel: multi-column and sidebar single-column witnesses.

Opt-in (HAEJO_RUN_NATIVE_SAVE_PANEL_TESTS=1). Only the test's own accessory
fixture is driven: its disclosure triangle and its sidebar Downloads row, by AX
within that process. Nothing is saved; folder contents are never printed. The
reader's directory must equal the panel's own in-process directoryURL.
"""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]

DRIVER = r'''
import AppKit
import ApplicationServices
let pid = pid_t(CommandLine.arguments[1])!, mode = CommandLine.arguments[2]
func attr(_ e: AXUIElement, _ n: String) -> AnyObject? {
    var v: AnyObject?; return AXUIElementCopyAttributeValue(e, n as CFString, &v) == .success ? v : nil }
let app = AXUIElementCreateApplication(pid)
var windows = (attr(app, "AXWindows") as? [AXUIElement]) ?? []
func find(_ test: (AXUIElement) -> Bool) -> [AXUIElement] {
    var out: [AXUIElement] = []
    func walk(_ e: AXUIElement, _ d: Int) {
        if test(e) { out.append(e) }
        let r = attr(e, "AXRole") as? String
        if r == "AXBrowser" || r == "AXList" || r == "AXOutline" || d > 30 { return }
        for k in (attr(e, "AXChildren") as? [AXUIElement]) ?? [] { walk(k, d + 1) }
    }
    for w in windows { walk(w, 0) }
    return out
}
func emit(_ value: [String: Any]) {
    print(String(data: try! JSONSerialization.data(withJSONObject: value), encoding: .utf8)!) }
switch mode {
case "expand":
    let hits = find { attr($0, "AXIdentifier") as? String == "NS_OPEN_SAVE_DISCLOSURE_TRIANGLE" }
    guard hits.count == 1 else { emit(["ok": false, "found": hits.count]); exit(0) }
    emit(["ok": AXUIElementPerformAction(hits[0], kAXPressAction as CFString) == .success])
case "sidebar":
    func texts(_ e: AXUIElement, _ d: Int) -> [String] {
        var out = ["AXValue", "AXTitle", "AXDescription"].compactMap { attr(e, $0) as? String }
        if d < 4 { for k in (attr(e, "AXChildren") as? [AXUIElement]) ?? [] { out += texts(k, d + 1) } }
        return out
    }
    let outlines = find { attr($0, "AXRole") as? String == "AXOutline" }
    guard outlines.count == 1, let rows = attr(outlines[0], "AXRows") as? [AXUIElement] else {
        emit(["ok": false, "reason": "sidebar"]); exit(0) }
    let hits = rows.filter { texts($0, 0).contains { $0 == "Downloads" || $0 == "다운로드" } }
    guard hits.count == 1 else { emit(["ok": false, "reason": "downloads_row", "found": hits.count]); exit(0) }
    emit(["ok": AXUIElementSetAttributeValue(hits[0], "AXSelected" as CFString, kCFBooleanTrue) == .success])
default:
    let read: NativeSavePanelReader.AttributeReader = { element, key in
        var value: AnyObject?
        let error = AXUIElementCopyAttributeValue(element, key as CFString, &value)
        return (error, value)
    }
    let resource: (AnyObject) throws -> NativeSaveDirectoryResource = { raw in
        guard let url = raw as? URL, url.isFileURL else { throw NativeSavePanelError.unavailable("url") }
        // As AX gives it: standardizing would rewrite /private/tmp to /tmp.
        let canonical = url.path
        var info = stat()
        guard stat(canonical, &info) == 0, (info.st_mode & S_IFMT) == S_IFDIR else {
            throw NativeSavePanelError.unavailable("not a directory") }
        return NativeSaveDirectoryResource(path: canonical, device: Int64(info.st_dev), inode: UInt64(info.st_ino))
    }
    do {
        let reader = try NativeSavePanelReader(readAttribute: read, directoryResource: resource)
        let window = windows.first { attr($0, "AXTitle") as? String == "HAEJO Owned Save Single Column Fixture" }!
        let witness = try reader.read(window)
        emit(["ok": true, "directory": witness.directory.path, "levels": witness.resources.count,
              "single_column_entries_witnessed": reader.budgetUsage["single_column_entries_witnessed"] ?? -1])
    } catch NativeSavePanelError.unavailable(let detail) {
        emit(["ok": false, "unavailable": detail])
    }
}
'''


@unittest.skipUnless(sys.platform == 'darwin' and os.environ.get('HAEJO_RUN_NATIVE_SAVE_PANEL_TESTS') == '1',
                     'opt-in owned native save panel test')
class OwnedSavePanelColumnTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.folder = tempfile.TemporaryDirectory(prefix='haejo-save-columns-')
        base = Path(cls.folder.name)
        cls.fixture, cls.driver = base / 'fixture', base / 'driver'
        for source, binary, extra in ((ROOT / 'tests/fixtures/NativeSaveSingleColumnFixture.swift', cls.fixture, []),
                                      (base / 'main.swift', cls.driver, [str(ROOT / 'helper/SavePanelObservation.swift')])):
            if binary is cls.driver:
                source.write_text(DRIVER)
            subprocess.run(['xcrun', 'swiftc', str(source), *extra, '-o', str(binary)],
                           check=True, capture_output=True, timeout=180)

    @classmethod
    def tearDownClass(cls):
        cls.folder.cleanup()

    def drive(self, pid, mode):
        out = subprocess.run([str(self.driver), str(pid), mode], capture_output=True, text=True, timeout=60)
        self.assertEqual(0, out.returncode, out.stderr[-2000:])
        return json.loads(out.stdout.strip().splitlines()[-1])

    def state(self, log):
        lines = [l for l in Path(log).read_text().splitlines() if l.startswith('{')]
        return json.loads(lines[-1]) if lines else {}

    def test_multi_column_then_sidebar_single_column_match_the_panel(self):
        # An owned, symlink-free folder under this checkout: its parent columns
        # stay small (a huge /private/tmp exceeds the reader's array budget).
        with tempfile.TemporaryDirectory(prefix='haejo-owned-panel-', dir=str(ROOT)) as folder:
            target = Path(folder).resolve() / 'a' / 'b'
            target.mkdir(parents=True)
            log = Path(folder) / 'fixture.log'
            with open(log, 'w') as stream:
                process = subprocess.Popen([str(self.fixture), str(target)], stdout=stream, stderr=subprocess.STDOUT)
            try:
                deadline = time.monotonic() + 15
                while not self.state(log) and time.monotonic() < deadline:
                    time.sleep(.1)
                time.sleep(.5)
                pid = self.state(log)['pid']
                # The panel service remembers expansion: press only if collapsed.
                if not self.state(log)['expanded']:
                    self.assertTrue(self.drive(pid, 'expand')['ok'])
                    time.sleep(1.5)
                self.assertTrue(self.state(log)['expanded'])
                multi = self.drive(pid, 'read')
                self.assertTrue(multi['ok'], multi)
                self.assertEqual(str(target), multi['directory'])
                self.assertGreaterEqual(multi['levels'], 2)
                selected = self.drive(pid, 'sidebar')
                if not selected['ok']:
                    self.skipTest('no unique Downloads sidebar row in this account: %s' % selected)
                time.sleep(1.5)
                truth = self.state(log)['directory']
                single = self.drive(pid, 'read')
                downloads = Path(truth)
                visible = [p for p in downloads.iterdir() if not p.name.startswith('.')] if downloads.is_dir() else []
                if single['ok']:
                    self.assertEqual(str(downloads), single['directory'])
                    self.assertEqual(1, single['levels'])
                    self.assertGreaterEqual(single['single_column_entries_witnessed'], 1)
                else:
                    # Honest limit: an empty folder column has nothing to witness it.
                    self.assertEqual([], visible, single)
            finally:
                process.kill()
                process.wait(timeout=5)


if __name__ == '__main__':
    unittest.main()
