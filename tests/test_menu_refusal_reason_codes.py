"""Menu act refusals say which one they were, without parsing prose (no GUI)."""
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]


def menu_case():
    source = (ROOT / 'helper/TactoHelper.swift').read_text()
    start = source.index('    case "menu":\n')
    return source[start:source.index('    case "reopen_window":', start)]


class MenuRefusalReasonTests(unittest.TestCase):
    def refusals(self):
        case = menu_case()
        # Each refusal dictionary literal that reports action_failed.
        return [m.group(0) for m in re.finditer(r'\["type": "error", "error": "action_failed".*?\]', case, re.S)]

    def test_every_action_failed_has_a_reason_code_and_an_effect(self):
        refusals = self.refusals()
        codes = [re.search(r'"reason_code": (?:"([a-z_]+)"|(failure\.code))', r).group(1) or 'failure.code'
                 for r in refusals]
        self.assertEqual(['menu_path_invalid', 'menu_path_invalid', 'menu_item_not_unique',
                          'menu_item_disabled', 'menu_focused_document_mismatch', 'menu_text_invalid',
                          'menu_text_requires_preparation', 'menu_press_failed', 'failure.code'], codes)
        for refusal in refusals:
            self.assertIn('"effect":', refusal)

    def test_disabled_and_press_failures_carry_their_diagnostics(self):
        refusals = {m.group(1): r for r in self.refusals()
                    if (m := re.search(r'"reason_code": "([a-z_]+)"', r))}
        disabled = refusals['menu_item_disabled']
        self.assertIn('"effect": "not_started"', disabled)
        self.assertIn('"needs_foreground": !wasFront', disabled)
        self.assertIn('"target_was_front": wasFront', disabled)
        press = refusals['menu_press_failed']
        self.assertIn('"effect": axActionFailureEffect(menuError)', press)
        self.assertIn('"ax_error": Int(menuError.rawValue)', press)

    def test_disabled_item_is_still_refused_before_any_press(self):
        case = menu_case()
        self.assertLess(case.index('"reason_code": "menu_item_disabled"'),
                        case.index('AXUIElementPerformAction(item, kAXPressAction'))
        self.assertNotIn('postToPid', case)
        self.assertNotIn('activate(', case)

    def test_save_as_probe_keeps_the_refusal_reason(self):
        probe = (ROOT / 'examples/probes/signed_textedit_save_as.py').read_text()
        kept = probe[probe.index("entry['detail'] = {key:detail[key] for key in"):]
        kept = kept[:kept.index('if key in detail}')]
        for key in ('reason_code', 'needs_foreground', 'target_was_front', 'ax_error', "'detail'"):
            self.assertIn(key, kept)


if __name__ == '__main__':
    unittest.main()
