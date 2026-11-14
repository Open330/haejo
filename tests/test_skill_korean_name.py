"""The skill is also reachable as 해줘: a second link to a small alias skill."""
try:
    from tests import _isolation  # noqa: F401
except ImportError:  # discovered with tests/ as the top level
    import _isolation  # noqa: F401
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT/'skill/install.sh'
NAME = '해줘'


class AliasSkill(unittest.TestCase):
    def test_the_alias_names_the_word_and_points_at_the_haejo_skill(self):
        text = (ROOT/'skill/ko/SKILL.md').read_text(encoding='utf-8')
        self.assertIn(f'\nname: {NAME}\n', text)
        self.assertIn('haejo/SKILL.md', text)
        main = (ROOT/'skill/SKILL.md').read_text(encoding='utf-8')
        self.assertIn('\nname: haejo\n', main)
        description = next(line for line in main.splitlines() if line.startswith('description: '))
        self.assertIn(NAME, description)
        self.assertLess(len(description), 400)

    def test_uninstall_and_the_app_know_the_second_link(self):
        from haejo.uninstall import link_places
        places = link_places(Path('/home/x'))
        self.assertIn(Path('/home/x/.claude/skills')/NAME, places)
        self.assertIn(Path('/home/x/.agents/skills')/'haejo', places)
        swift = (ROOT/'setup/PermissionState.swift').read_text(encoding='utf-8')
        self.assertIn(f'appendingPathComponent("{NAME}"), root.appendingPathComponent("skill/ko")', swift)
        self.assertIn('if expected.lastPathComponent == "ko" { continue }', swift)


class AliasInstall(unittest.TestCase):
    def setUp(self):
        if not os.access(ROOT/'launcher/haejo', os.X_OK):
            self.skipTest('no built entry point in this checkout')
        tmp = tempfile.TemporaryDirectory(); self.addCleanup(tmp.cleanup)
        self.home = Path(tmp.name); self.skills = self.home/'skills'; self.bin = self.home/'bin'

    def run_script(self, *args):
        env = {'HOME': str(self.home), 'PATH': f'{self.bin}:/usr/bin:/bin', 'LC_ALL': 'en_US.UTF-8'}
        return subprocess.run(['bash', str(SCRIPT), '--bin-dir', str(self.bin), '--skill-dir', str(self.skills), *args],
                              env=env, capture_output=True, text=True, timeout=30)

    def test_install_links_both_names_and_check_agrees(self):
        result = self.run_script()
        self.assertEqual(0, result.returncode, result.stdout+result.stderr)
        self.assertEqual(str(ROOT/'skill'), os.readlink(self.skills/'haejo'))
        self.assertEqual(str(ROOT/'skill/ko'), os.readlink(self.skills/NAME))
        self.assertEqual(0, self.run_script('--check').returncode)
        (self.skills/NAME).unlink()
        check = self.run_script('--check')
        self.assertEqual(1, check.returncode)
        self.assertIn(f'missing: {self.skills/NAME}', check.stdout)

    def test_someone_elses_skill_of_that_name_is_left_alone(self):
        theirs = self.skills/NAME; theirs.mkdir(parents=True)
        (theirs/'SKILL.md').write_text('---\nname: 해줘\ndescription: mine\n---\n', encoding='utf-8')
        result = self.run_script()
        self.assertEqual(0, result.returncode, result.stdout+result.stderr)
        self.assertFalse(theirs.is_symlink())
        self.assertIn('mine', (theirs/'SKILL.md').read_text(encoding='utf-8'))
        self.assertEqual(0, self.run_script('--check').returncode)


if __name__ == '__main__':
    unittest.main()
