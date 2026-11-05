"""Opt-in receiving proof for a real floating canvas through the signed helper."""
import json
import os
from pathlib import Path
import plistlib
import subprocess
import sys
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(sys.platform == 'darwin' and os.environ.get('TACTO_RUN_NATIVE_DRAG_TESTS') == '1',
                     'opt-in signed floating-window drag')
class FloatingDragNative(unittest.TestCase):
    def test_floating_canvas_receives_one_stroke_without_hid_pointer_move(self):
        from AppKit import NSWorkspace
        import Quartz
        with tempfile.TemporaryDirectory(prefix='tacto-floating-drag-') as directory:
            base = Path(directory)
            app = base / 'OwnedFloating.app'
            binary = app / 'Contents/MacOS/OwnedFloating'
            binary.parent.mkdir(parents=True)
            subprocess.run(['xcrun', 'swiftc', '-parse-as-library', str(ROOT / 'tests/fixtures/NativeDragFixture.swift'),
                            '-o', str(binary)], check=True, capture_output=True)
            target = 'ai.callabo.tacto.floatingfixture'
            (app / 'Contents/Info.plist').write_bytes(plistlib.dumps({
                'CFBundleIdentifier': target, 'CFBundleExecutable': 'OwnedFloating',
                'CFBundleName': 'Tacto Floating Fixture', 'CFBundlePackageType': 'APPL', 'LSUIElement': True}))
            subprocess.run(['codesign', '--force', '--sign', '-', str(app)], check=True, capture_output=True)
            process = subprocess.Popen([str(binary), str(base), '--floating'],
                                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            try:
                deadline = time.monotonic() + 10
                while not (base / 'slider.txt').exists():
                    self.assertLess(time.monotonic(), deadline)
                    time.sleep(.05)
                while True:
                    rows = Quartz.CGWindowListCopyWindowInfo(Quartz.kCGWindowListOptionOnScreenOnly, 0)
                    windows = [row for row in rows if row.get(Quartz.kCGWindowOwnerPID) == process.pid]
                    if any(row.get(Quartz.kCGWindowLayer) == 3 for row in windows):
                        break
                    self.assertLess(time.monotonic(), deadline)
                    time.sleep(.05)
                front = NSWorkspace.sharedWorkspace().frontmostApplication().processIdentifier()
                pointer = Quartz.CGEventGetLocation(Quartz.CGEventCreate(None))
                result = subprocess.run([str(ROOT / 'launcher/tacto'), 'drag', target, '--helper',
                                         '--window', 'Tacto Drag Fixture', '--from', '40', '80',
                                         '--to', '180', '100', '--duration', '0.2'],
                                        capture_output=True, text=True, timeout=40)
                self.assertEqual(0, result.returncode, result.stdout + result.stderr)
                deadline = time.monotonic() + 3
                while not (base / 'events.json').exists():
                    self.assertLess(time.monotonic(), deadline)
                    time.sleep(.05)
                events = json.loads((base / 'events.json').read_text())
                self.assertEqual(1, sum(e['kind'] == 'down' for e in events))
                self.assertEqual(1, sum(e['kind'] == 'up' for e in events))
                self.assertTrue(any(e['kind'] == 'drag' for e in events))
                self.assertEqual('down', events[0]['kind'])
                self.assertEqual('up', events[-1]['kind'])
                self.assertEqual(1, len({e['window'] for e in events}))
                self.assertEqual(front, NSWorkspace.sharedWorkspace().frontmostApplication().processIdentifier())
                self.assertEqual(pointer, Quartz.CGEventGetLocation(Quartz.CGEventCreate(None)))
            finally:
                process.terminate()
                process.wait(timeout=5)
