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
LAUNCHER = ROOT / 'launcher/tacto'


@unittest.skipUnless(sys.platform == 'darwin' and os.environ.get('TACTO_RUN_NATIVE_DRAG_TESTS') == '1',
                     'opt-in signed floating-window drag')
class FloatingDragNative(unittest.TestCase):
    def test_floating_canvas_receives_one_stroke_without_hid_pointer_move(self):
        self.run_panel(borderless=False)

    def test_borderless_nonkey_overlay_drag_and_ax_resize(self):
        self.run_panel(borderless=True)

    def test_fixed_window_content_button_is_not_a_resize_grip(self):
        self.run_panel(borderless=True,interactive_grip=True)

    def run_panel(self, borderless, interactive_grip=False):
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
            process = subprocess.Popen([str(binary), str(base), '--floating', *(['--borderless'] if borderless else []),
                                        *(['--interactive-grip'] if interactive_grip else [])],
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
                result = subprocess.run([str(LAUNCHER), 'drag', target, '--helper', '--json',
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
                resized = subprocess.run([str(LAUNCHER), 'resize', target, '--helper',
                                          '--window', 'Tacto Drag Fixture', '--width', '600', '--height', '360'],
                                         capture_output=True, text=True, timeout=30)
                if interactive_grip:
                    self.assertNotEqual(0,resized.returncode)
                    self.assertIn('resize grip is an interactive control',resized.stdout)
                    self.assertIn('not_started',resized.stdout)
                    self.assertFalse((base/'grip-clicked').exists())
                    self.assertFalse((base/'resize-events.json').exists())
                    return
                self.assertEqual(0, resized.returncode, resized.stdout + resized.stderr)
                proof = json.loads(resized.stdout)
                self.assertTrue(proof['size_verified'])
                self.assertEqual('window_resize_drag' if borderless else 'ax_window_size', proof['input_route'])
                deadline = time.monotonic() + 3
                while True:
                    received = json.loads((base / 'geometry.json').read_text())
                    if received['width'] == 600 and received['height'] == 360:
                        break
                    self.assertLess(time.monotonic(), deadline, str(received))
                    time.sleep(.05)
                self.assertEqual(events, json.loads((base / 'events.json').read_text()),
                                 'Resize must not send events into the canvas')
                if borderless:
                    resize_events=json.loads((base/'resize-events.json').read_text())
                    self.assertEqual(1,resize_events['downs'])
                    self.assertEqual(1,resize_events['ups'])
                    self.assertGreater(resize_events['drags'],0)
                self.assertEqual(front, NSWorkspace.sharedWorkspace().frontmostApplication().processIdentifier())
                self.assertEqual(pointer, Quartz.CGEventGetLocation(Quartz.CGEventCreate(None)))
            finally:
                process.terminate()
                process.wait(timeout=5)
