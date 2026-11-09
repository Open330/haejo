"""A disabled background menu command: one temporary window preparation, always undone (no GUI).

The actual behaviour is measured by the signed TextEdit Save As probe; these
checks pin the shape of the helper code that makes it safe.
"""
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = (ROOT / 'helper/HaejoHelper.swift').read_text()


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
        self.assertIn('CFEqual(focusedRaw, main)', begin)
        self.assertIn('focusError != .noValue', begin)
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


class TemporaryMenuPreparationScopeTests(unittest.TestCase):
    def test_only_a_dialog_command_waits_and_never_past_the_deadline(self):
        case = menu_case()
        wait = case[case.index('if let prepared = temporary {'):case.index('var activated = false')]
        self.assertIn('title.hasSuffix("\\u{2026}") || title.hasSuffix("...")', wait)
        self.assertIn('min(3, max(0, menuDeadline - ProcessInfo.processInfo.systemUptime))', wait)
        self.assertIn('"not_a_dialog_command"', wait)
        self.assertNotIn('waitForSheet(seconds: 3)', case)

    def test_prepared_deadline_is_bounded_and_respects_the_caller(self):
        case = menu_case()
        self.assertEqual(1, case.count('menuDeadline = min(clickDeadline ?? .infinity, ProcessInfo.processInfo.systemUptime + 10)'))
        before = case[:case.index('menuDeadline = min(clickDeadline')]
        self.assertNotIn('menuDeadline = ', before.replace('var menuDeadline = deadline', ''))

    def test_toolbar_titlebar_is_only_for_the_temporary_menu_preparation(self):
        self.assertIn('prepareBackgroundWindow(obsID, target, window, pid, deadline: deadline, toolbarTitlebar: true)',
                      function('func beginTemporaryMenuPreparation('))
        self.assertEqual(1, SOURCE.count('toolbarTitlebar: true'))
        self.assertIn('toolbarTitlebar: Bool = false', SOURCE)
        standalone = function('func prepareWindow(')
        self.assertIn('return prepareBackgroundWindow(obsID, target, element, pid, deadline: deadline)', standalone)
        window_input = (ROOT / 'helper/WindowInput.swift').read_text()
        clear = window_input[window_input.index('func nativeToolbarPointIsClear('):]
        clear = clear[:clear.index('\n}\n')]
        for required in ('"AXToolbar"', 'CFEqual(parent, window)', 'isSubset(of: ["AXShowMenu"])',
                         'guard CFEqual(hit, toolbar) else { return false }', '!CFEqual(hit, window)'):
            self.assertIn(required, clear)
        capture = window_input[window_input.index('if pointKind == .titlebarToolbar {'):]
        capture = capture[:capture.index('throw NativeWindowInputError.refused("no blank native titlebar point")')]
        self.assertIn('insetBy(dx: -8, dy: -8).contains(point)', capture)


class MenuPreparationPerEventValidationTests(unittest.TestCase):
    def validator(self):
        source = (ROOT / 'helper/WindowInput.swift').read_text()
        start = source.index('func validateNativeMenuPreparationBinding(')
        return source[start:source.index('\n}\n', start) + 3]

    def test_only_the_menu_preparation_binding_skips_the_full_walk_per_event(self):
        prepare = function('func prepareBackgroundWindow(')
        branch = prepare[prepare.index('} else if previous.pointKind == .titlebarToolbar {'):]
        branch = branch[:branch.index('}, key: key,')]
        self.assertIn('validateNativeMenuPreparationBinding(previous,scope:scope)', branch)
        self.assertIn('else {try scope.withBindingContext {try validateNativeWindowBinding(previous,scope:scope)}}', branch)
        self.assertEqual(1, SOURCE.count('validateNativeMenuPreparationBinding('))
        # The initial binding is still captured with the full readiness walk.
        window_input = (ROOT / 'helper/WindowInput.swift').read_text()
        capture = window_input[window_input.index('if pointKind == .titlebar || pointKind == .titlebarToolbar {'):]
        self.assertTrue(capture.split('\n', 2)[1].strip().startswith('try nativeRequireWindowReady(window, pid, scope: scope)'))

    def test_cheap_validation_still_rejects_what_could_redirect_the_pair(self):
        body = self.validator()
        self.assertNotIn('nativeRequireWindowReady', body)
        for required in ('binding.pointKind == .titlebarToolbar',
                         'nativeProcessStartIdentity(binding.pid) == binding.processStart',
                         'windowInputCGFrame(binding.windowID, binding.pid, scope: scope) == binding.windowBounds',
                         'kAXMainWindowAttribute', 'kAXFocusedWindowAttribute', 'focusError != .noValue',
                         '"AXModal"', '"modal or unknown window"', '"AXSheet"',
                         'nativeTitlebarPointIsClear(binding.point', 'nativeToolbarPointIsClear(binding.point'):
            self.assertIn(required, body)
        self.assertGreaterEqual(body.count('try scope?.ready()'), 3)

    def test_dispatcher_keeps_context_abort_deadline_and_user_input_checks_per_event(self):
        dispatch = (ROOT / 'helper/WindowDispatch.swift').read_text()
        loop = dispatch[dispatch.index('for (number, event) in events.enumerated() {'):]
        loop = loop[:loop.index('attempted += 1')]
        for required in ('try ready(); try validated(); try ready()', 'let before = try observedInput()',
                         'guard expectedInput.matches(before) else'):
            self.assertIn(required, loop)


class PreparedMenuTextTests(unittest.TestCase):
    def enter_text(self):
        start = SOURCE.index('func enterText(_ text: String, pid: pid_t')
        return SOURCE[start:SOURCE.index('    /// Undo the app-internal activation', start)]

    def test_text_is_only_typed_inside_a_temporary_preparation(self):
        case = menu_case()
        guard = case[case.index('let enterText = action["text"] as? String'):case.index('let menuError = AXUIElementPerformAction(item')]
        self.assertIn('guard temporary != nil else', guard)
        self.assertIn('"menu_text_requires_preparation"', guard)
        self.assertIn('enterText.utf16.count <= 255', guard)
        self.assertIn('generalCategory == .control', guard)
        after = case[case.index('if let enterText, let prepared = temporary {'):]
        after = after[:after.index('var activated = false')]
        self.assertIn('"effect": "unknown"', after)
        self.assertIn('return finish(', after)
        self.assertIn('"action.menu.prepared_text"', SOURCE)

    def test_editor_is_new_focus_of_this_process_inside_the_window_and_committed_once(self):
        body = self.enter_text()
        for required in ('focusBefore.map { !CFEqual($0, candidate) }', '"AXTextField"',
                         'AXUIElementGetPid(candidate, &owner) == .success, owner == pid',
                         'bounds.contains(frame)', 'AXUIElementIsAttributeSettable(field, kAXValueAttribute',
                         '(attr(field, kAXValueAttribute as String) as? String) == text',
                         '!isFrontmost(pid: pid)', 'CFEqual(focusedNow, field)',
                         'buildNativeWindowKey(windowID, key: "Return", submit: true)', 'nativePIDPost(pair.down, pid)'):
            self.assertIn(required, body)
        self.assertEqual(1, body.count('nativePIDPost(pair.down, pid)'))
        self.assertNotIn('postToPid', body)

    def test_python_and_launcher_accept_text_only_for_menu_with_the_capability(self):
        from haejo.helper import HelperDriver
        from haejo.protocol import ACTION_PARAMS
        self.assertIn('text', ACTION_PARAMS['menu'])
        h = HelperDriver.__new__(HelperDriver)
        h.capabilities = set()
        self.assertEqual('menu_text_unavailable',
                         h.act('o1', 'com.apple.finder', {'name': 'menu', 'path': ['File', 'New Folder'], 'text': 'x'})['error'])
        launcher = (ROOT / 'launcher/haejo.swift').read_text()
        self.assertIn('"menu":             (["name", "path"], ["focused_document", "text"]),', launcher)
        # A direct backend must not drop the name and create an unnamed folder.
        import sys
        if sys.platform == 'darwin':
            from haejo.driver import Driver
            direct=Driver.__new__(Driver)
            response=direct.act('o1','com.apple.finder',{'name':'menu','path':['File','New Folder'],'text':'x'})
            self.assertEqual('menu_text_unavailable',response['error'])
            self.assertEqual('not_started',response['effect'])
            self.assertIn('--helper',response['detail'])


class PreparedMenuTextGuardTests(unittest.TestCase):
    def test_main_window_is_rechecked_before_write_and_return_and_key_up_is_recovered(self):
        body = PreparedMenuTextTests().enter_text()
        write_guard=body.index('mainUnchanged()', body.index('AXUIElementIsAttributeSettable(field'))
        self.assertLess(write_guard, body.index('AXUIElementSetAttributeValue(field'))
        second = body.index('guard mainUnchanged()', body.index('AXUIElementSetAttributeValue(field'))
        self.assertLess(second, body.index('buildNativeWindowKey(windowID, key: "Return", submit: true)'))
        recover = body[body.index('} catch {', body.index('downAttempted = true')):]
        self.assertIn('if downAttempted, let start = latestProcessStart, nativeProcessStartIdentity(pid) == start', recover)
        self.assertIn('try nativePIDPost(pair.up, pid)', recover)
        self.assertIn('"committed": "unknown"', recover)

    def test_skill_shows_the_minimal_menu_text_example(self):
        guide = (ROOT / 'skill/references/finder-menus.md').read_text()
        self.assertIn('"text": "Reports"', guide)
        self.assertNotIn('"text"', (ROOT / 'skill/SKILL.md').read_text())
