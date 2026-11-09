"""Canonical command discovery with isolated user profiles."""
from tests import test_skill_install_isolated as fixtures
import unittest
import os


class HaejoBrandingTests(unittest.TestCase):
    setUp = fixtures.IsolatedSkillInstallTests.setUp
    run_script = fixtures.IsolatedSkillInstallTests.run_script

    def test_installs_one_command_and_one_skill_per_agent(self):
        self.assertEqual(0, self.run_script().returncode)
        self.assertEqual(['haejo'], sorted(p.name for p in self.bin.iterdir()))
        self.assertEqual(str(self.entry), os.readlink(self.bin/'haejo'))
        for agent in ('.codex', '.claude'):
            parent = self.home/agent/'skills'
            self.assertEqual(['haejo'], sorted(p.name for p in parent.iterdir()))
        self.assertEqual(0, self.run_script('--check').returncode)

    def test_foreign_command_prevents_skill_mutations(self):
        self.bin.mkdir(parents=True)
        other = self.bin/'haejo'; other.write_text('foreign program')
        result = self.run_script()
        self.assertEqual(1, result.returncode)
        self.assertEqual('foreign program', other.read_text())
        self.assertFalse((self.home/'.codex/skills').exists())

    def test_unrelated_skill_is_not_adopted_or_deleted(self):
        foreign = self.home/'.codex/skills/haejo'; foreign.mkdir(parents=True)
        (foreign/'SKILL.md').write_text('---\nname: unrelated\n---\nkeep me\n')
        result = self.run_script()
        self.assertEqual(1, result.returncode)
        self.assertFalse(foreign.is_symlink())
        self.assertIn('keep me', (foreign/'SKILL.md').read_text())

    def test_branded_bin_override_controls_only_command_destination(self):
        branded = self.home/'branded bin'
        result = self.run_script(HAEJO_BIN_DIR=str(branded))
        self.assertEqual(0, result.returncode, result.stdout+result.stderr)
        self.assertEqual(['haejo'], sorted(p.name for p in branded.iterdir()))
        self.assertFalse(self.bin.exists())


class RetiredDiscoveryCleanupTests(HaejoBrandingTests):
    def test_owned_retired_links_are_removed_and_check_reports_them(self):
        self.assertEqual(0, self.run_script().returncode)
        alias = self.bin/'nlc'; alias.symlink_to(self.entry)
        old_skill = self.home/'.codex/skills/nlc'; old_skill.symlink_to(self.root/'skill')
        self.assertEqual(1, self.run_script('--check').returncode)
        self.assertTrue(alias.is_symlink())
        self.assertTrue(old_skill.is_symlink())
        self.assertEqual(0, self.run_script().returncode)
        self.assertFalse(alias.is_symlink())
        self.assertFalse(old_skill.is_symlink())
        self.assertEqual(['haejo'], sorted(p.name for p in self.bin.iterdir()))
        self.assertEqual(0, self.run_script('--check').returncode)

    def test_owned_tacto_links_from_before_the_rename_are_removed(self):
        self.assertEqual(0, self.run_script().returncode)
        alias = self.bin/'tacto'; alias.symlink_to(self.root/'launcher/tacto')
        old_skill = self.home/'.claude/skills/tacto'; old_skill.symlink_to(self.root/'skill')
        self.assertEqual(1, self.run_script('--check').returncode)
        self.assertEqual(0, self.run_script().returncode)
        self.assertFalse(alias.is_symlink())
        self.assertFalse(old_skill.is_symlink())
        self.assertEqual(['haejo'], sorted(p.name for p in self.bin.iterdir()))

    def test_tacto_link_into_another_program_is_preserved(self):
        self.bin.mkdir(parents=True)
        foreign = self.home/'unrelated-tacto'; foreign.write_text('not our command')
        alias = self.bin/'tacto'; alias.symlink_to(foreign)
        self.assertEqual(0, self.run_script().returncode)
        self.assertEqual(str(foreign), os.readlink(alias))

    def test_foreign_retired_name_is_preserved(self):
        self.bin.mkdir(parents=True)
        foreign = self.home/'unrelated'; foreign.write_text('not our command')
        alias = self.bin/'nlc'; alias.symlink_to(foreign)
        self.assertEqual(0, self.run_script().returncode)
        self.assertEqual(str(foreign), os.readlink(alias))
