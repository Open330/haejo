"""The first-run VM check's screen reading, without a VM (no GUI)."""
import importlib.util
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('first_run_vm', ROOT / 'setup/first_run_vm/check.py')
check = importlib.util.module_from_spec(spec)
spec.loader.exec_module(check)


def line(text, x, y, w=200, h=30):
    return {'text': text, 'x': x, 'y': y, 'w': w, 'h': h, 'cx': x + w // 2, 'cy': y + h // 2}


class FirstRunVMTests(unittest.TestCase):
    def setUp(self):
        self.vm = check.VM.__new__(check.VM)

    def test_guide_over_the_sidebar_leaves_the_list_row_and_ignores_other_windows(self):
        # Guide over the Settings sidebar; a Finder window to the right of Settings.
        lines = [line('Haejo 권한 도우미', 538, 125, 160), line('Haejo Helper', 517, 514, 160),
                 line('Device Control and Data Access', 937, 151, 400),
                 line('this access can view and send email, edit contacts and photos,', 940, 263, 780),
                 line('ur keyboard, track websites, record your screen, control any', 937, 300, 760),
                 line('Helper', 943, 407, 86), line('Console', 1750, 470, 100)]
        lay = self.vm.layout(lines, Path('shot.png'), r'Device Control and Data Access')
        self.assertEqual(1760, lay['right'])   # from the description, not the Finder label
        self.assertEqual('Helper', self.vm.list_row(lay, 'Haejo Helper')['text'])

    def test_guide_name_is_not_taken_for_the_list_row(self):
        lines = [line('Haejo 권한 도우미', 538, 125, 160), line('Haejo', 568, 514, 80),
                 line('Screen & System Audio Recording', 937, 154, 480),
                 line('plications below to record the content of your screen', 940, 283, 700),
                 line('No Items', 1215, 382, 80)]
        lay = self.vm.layout(lines, Path('shot.png'), r'Screen & System Audio Recording')
        self.assertIsNone(self.vm.list_row(lay, 'Haejo'))
        self.assertEqual(['No Items'], [l['text'] for l in check.VM.find(lay['pane'], r'^No Items$', exact=True)])

    def test_password_prompt_fragments_match_when_partly_covered(self):
        for text in ('1odify Settings', 'password to continue', 'Modify Settings'):
            self.assertTrue(check.VM.find([line(text, 0, 0)], check.PASSWORD_PROMPT))

    @unittest.skipUnless(sys.platform == 'darwin', 'Vision OCR')
    def test_ocr_tool_typechecks(self):
        result = subprocess.run(['swiftc', '-typecheck', str(ROOT / 'setup/first_run_vm/ocr.swift')],
                                capture_output=True, text=True, timeout=120)
        self.assertEqual(0, result.returncode, result.stderr)


if __name__ == '__main__':
    unittest.main()
