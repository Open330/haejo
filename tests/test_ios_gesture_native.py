"""Compile the actual gesture sender with injected I/O; never open a device."""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

SWIFT = shutil.which('swiftc')
HARNESS = r'''
import Foundation
enum Fault: Error { case injected }
let scenario = CommandLine.arguments[1]
var reports = [Data]()
var pingCount = 0
var failedRelease = false
let gesture = OneGesture(send: { data in
    reports.append(data)
    if scenario == "partial-contact" && reports.count == 1 { throw Fault.injected }
    if scenario == "failed-release" && data[3] == 0x02 && !failedRelease {
        failedRelease = true; throw Fault.injected
    }
}, ping: {
    pingCount += 1
    if scenario == "failed-ping" { throw Fault.injected }
}, pause: { _ in })
var succeeded = false
do {
    try gesture.tapOnce(x: scenario == "invalid" ? -1 : 0xABCD, y: 0x1234)
    succeeded = true
} catch {}
let states = reports.map { $0[3] }
switch scenario {
case "success":
    precondition(succeeded && states == [0xC2, 0xC2, 0x02] && pingCount == 1)
    precondition(gesture.contactReports == 2 && gesture.releaseReports == 1)
    for report in reports {
        precondition(report.count == 58)
        precondition(Array(report.prefix(3)) == [9, 1, 5])
        precondition(Array(report[4..<8]) == [0xCD, 0xAB, 0x34, 0x12])
    }
case "partial-contact":
    precondition(!succeeded && states == [0xC2, 0x02] && pingCount == 0)
    precondition(gesture.cleanupReleaseAttempts == 1)
case "failed-release":
    precondition(!succeeded && states == [0xC2, 0xC2, 0x02, 0x02] && pingCount == 0)
    precondition(gesture.cleanupReleaseAttempts == 1)
case "failed-ping":
    precondition(!succeeded && states == [0xC2, 0xC2, 0x02] && pingCount == 1)
    precondition(gesture.cleanupReleaseAttempts == 0)
case "invalid":
    precondition(!succeeded && reports.isEmpty && !gesture.attempted)
    print("ok"); exit(0)
default: fatalError("unknown test")
}
let before = reports.count
do { try gesture.tapOnce(x: 1, y: 1); fatalError("second gesture accepted") } catch {}
precondition(reports.count == before && gesture.attempted)
print("ok")
'''


@unittest.skipUnless(SWIFT, 'Swift compiler required for the native gesture fault tests')
class IOSGestureNativeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.temp.cleanup)
        directory = Path(cls.temp.name)
        main = directory/'main.swift'
        main.write_text(HARNESS)
        cls.binary = directory/'gesture-fault-tests'
        source = Path(__file__).resolve().parents[1]/'spike/ios-ax-bridge/Sources/OneGesture.swift'
        result = subprocess.run([SWIFT, str(source), str(main), '-o', str(cls.binary)],
                                capture_output=True, text=True, timeout=60)
        if result.returncode:
            raise AssertionError(result.stderr)

    def check_scenario(self, scenario):
        result = subprocess.run([str(self.binary), scenario], capture_output=True, text=True, timeout=3)
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual('ok', result.stdout.strip())

    def test_one_gesture_packet_coordinates_and_no_second_down(self): self.check_scenario('success')
    def test_partial_contact_allows_only_one_cleanup_release(self): self.check_scenario('partial-contact')
    def test_failed_release_allows_one_release_only_cleanup(self): self.check_scenario('failed-release')
    def test_ping_failure_never_replays_contact_or_release(self): self.check_scenario('failed-ping')
    def test_invalid_coordinates_send_nothing(self): self.check_scenario('invalid')
