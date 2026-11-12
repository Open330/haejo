"""The notice a window-scoped session prints is text, with its example braces intact."""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class WindowScopeNotice(unittest.TestCase):
    def test_the_notice_renders_and_shows_the_route_example(self):
        source = (ROOT/'haejo/flow_session.py').read_text()
        lines = [line.strip() for line in source.splitlines() if 'HAEJO_WINDOW_SCOPE {chosen}' in line]
        self.assertEqual(1, len(lines))
        match = re.fullmatch(r'emit\((.*)\)', lines[0])
        self.assertIsNotNone(match)
        # A lone {"route":"pointer"} inside the f-string is a format spec and
        # raised when a window session started (2026-11-12).
        text = eval(match.group(1), {'chosen': 7, 'stored': ' kept'})
        self.assertTrue(text.startswith('HAEJO_WINDOW_SCOPE 7: '))
        self.assertIn('{"route":"pointer"}', text)
        self.assertTrue(text.endswith(' kept'))


if __name__ == '__main__':
    unittest.main()
