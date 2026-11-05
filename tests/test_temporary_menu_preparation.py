"""A disabled background menu command: one temporary window preparation, always undone (no GUI).

The actual behaviour is measured by the signed TextEdit Save As probe; these
checks pin the shape of the helper code that makes it safe.
"""
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = (ROOT / 'helper/TactoHelper.swift').read_text()


def menu_case():
    start = SOURCE.index('    case "menu":\n')
    return SOURCE[start:SOURCE.index('    case "reopen_window":', start)]


def function(name):
    start = SOURCE.index(name)
    return SOURCE[start:SOURCE.index('\n}\n', start) + 3]


class TemporaryMenuPreparationTests(unittest.TestCase):
    def test_only_a_disabled_item_of_a_background_app_is_prepared(self):
        case = menu_case()
        disabled = case[case.index('if (enabled as? Bool) == false {'):]
        self.assertLess(disabled.index('guard !wasFront else { return disabled(nil) }'),
                        disabled.index('beginTemporaryMenuPreparation('))
        # Nothing else in the menu path prepares a window.
        self.assertEqual(1, case.count('beginTemporaryMenuPreparation('))
        self.assertNotIn('prepareBackgroundWindow(', case)

    def test_every_exit_after_preparation_is_undone(self):
        case = menu_case()
        after = case[case.index('temporary = prepared'):]
        returns = re.findall(r'return (\S+?)\(', after)
        self.assertTrue(returns)
        self.assertEqual({'finish'}, set(returns), returns)
        self.assertIn('return finish(out)', after)
        self.assertIn('prepared.restore(pid: p)', case[:case.index('temporary = prepared')])

    def test_still_disabled_after_preparation_is_not_pressed(self):
        case = menu_case()
        settle = case[case.index('var nowEnabled = false'):case.index('AXUIElementPerformAction(item, kAXPressAction')]
        self.assertIn('guard nowEnabled else', settle)
        self.assertIn('return finish(disabled(nil))', settle)
        self.assertIn('guard !isFrontmost(pid: p), temporary?.stillBound(pid: p) == true', settle)
        self.assertEqual(1, case.count('AXUIElementPerformAction(item, kAXPressAction'))

    def test_eligibility_never_undoes_a_real_or_self_reported_foreground(self):
        begin = function('func beginTemporaryMenuPreparation(')
        self.assertIn('guard (selfFront as? Bool) == false else { return skip("target_self_reports_frontmost") }', begin)
        self.assertIn('CFEqual(focused, main)', begin)
        self.assertIn('latestElements.filter({ CFEqual($0, window) }).count == 1', begin)
        self.assertIn('temporaryMenuSheetCount(window) == 0', begin)
        self.assertLess(begin.index('target_self_reports_frontmost'), begin.index('prepareBackgroundWindow('))
        restore = SOURCE[SOURCE.index('mutating func restore(pid: pid_t)'):]
        restore = restore[:restore.index('\n    }\n') + 6]
        self.assertLess(restore.index('if isFrontmost(pid: pid)'), restore.index('nativePIDPost(event, pid)'))
        self.assertIn('windowNumber: Int(windowID)', restore)
        self.assertIn('applicationDeactivated', restore)
        self.assertIn('record["restored"] = frontmost == false', restore)

    def test_unconfirmed_undo_is_not_reported_as_not_started(self):
        case = menu_case()
        finish = case[case.index('func finish('):case.index('if (enabled as? Bool) == false {')]
        self.assertIn('out["effect"] = "unknown"', finish)
        self.assertIn('out["temporary_preparation"] = prepared.record', finish)

    def test_no_global_activation_or_pointer_route(self):
        for text in (menu_case(), function('func beginTemporaryMenuPreparation('),
                     SOURCE[SOURCE.index('struct TemporaryMenuPreparation {'):SOURCE.index('func temporaryMenuSheetCount(')]):
            for forbidden in ('activate(', 'NSRunningApplication', 'CGWarpMouseCursorPosition', '.cghidEventTap',
                              'kCGHIDEventTap', 'AXFrontmost" as CFString, kCFBooleanTrue'):
                self.assertNotIn(forbidden, text)


if __name__ == '__main__':
    unittest.main()
