"""Asking a command for help prints usage and starts nothing."""
try:
    from tests import _isolation  # noqa: F401
except ImportError:  # discovered with tests/ as the top level
    import _isolation  # noqa: F401
import contextlib
import io
import unittest
from unittest import mock

from haejo import cli
from haejo.command_help import command_help


class HelpNeverRuns(unittest.TestCase):
    COMMANDS = ('doctor', 'compile', 'do', 'launch', 'activate', 'open-url', 'apps', 'list', 'candidates',
                'promote', 'logs', 'uninstall', 'keep-awake', 'first-run', 'windows', 'menu-state', 'repair',
                'replay', 'parameterize', 'show', 'document-attachments', 'parallel', 'batch', 'observe',
                'session', 'run')

    def test_every_command_answers_help_with_its_usage(self):
        for command in self.COMMANDS:
            with self.subTest(command=command):
                text = command_help(command, ['--help'])
                self.assertIsNotNone(text)
                self.assertTrue(text.startswith(f'usage: haejo {command}'), text[:80])

    def test_help_beside_other_arguments_still_does_not_run_the_command(self):
        for command, args in (('observe', ['com.apple.calculator', '--helper', '--help']),
                              ('launch', ['--help', '--helper']), ('do', ['--learn', '--help']),
                              ('doctor', ['-h'])):
            with self.subTest(command=command):
                self.assertIsNotNone(command_help(command, args))

    def test_a_request_that_merely_mentions_help_runs(self):
        self.assertIsNone(command_help('do', ['help 메뉴 열어줘']))
        self.assertIsNone(command_help('run', ['flow.json', '-p', 'text=-h']))

    def test_commands_with_their_own_parser_keep_it(self):
        for command in ('task', 'auth', 'flows', 'hover', 'resize', 'capture', 'drag', 'web-upload'):
            self.assertIsNone(command_help(command, ['--help']))

    def test_the_cli_returns_before_any_driver_agent_or_settings_pane(self):
        refuse = mock.Mock(side_effect=AssertionError('help started the command'))
        for command in ('doctor', 'compile', 'do', 'launch', 'activate', 'apps'):
            with self.subTest(command=command), \
                 mock.patch.object(cli, '_make_driver', refuse), mock.patch.object(cli, 'Agent', refuse), \
                 mock.patch('subprocess.run', refuse), mock.patch('subprocess.Popen', refuse), \
                 contextlib.redirect_stdout(io.StringIO()) as out:
                self.assertEqual(0, cli.main([command, '--help']))
                self.assertIn(f'usage: haejo {command}', out.getvalue())

    def test_top_level_help_lists_the_commands_an_agent_starts_with(self):
        for command in ('observe', 'session', 'batch', 'windows', 'menu-state', 'flows', 'repair', 'hover', 'resize'):
            self.assertIn(f'\n  haejo {command} ', cli.__doc__)
        self.assertEqual(1, cli.__doc__.count('\n  haejo run '))


class Version(unittest.TestCase):
    def test_version_names_the_installed_release_or_the_checkout(self):
        import plistlib
        import tempfile
        from pathlib import Path
        with contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertEqual(0, cli.main(['--version']))
        self.assertTrue(out.getvalue().startswith('haejo '))
        with tempfile.TemporaryDirectory() as folder:
            contents = Path(folder)/'Haejo.app/Contents'
            module = contents/'Resources/runtime/site-packages/haejo/cli.py'
            module.parent.mkdir(parents=True)
            module.write_text('')
            (contents/'Info.plist').write_bytes(plistlib.dumps(
                {'HaejoReleaseTag': 'v1.0.0-rc.48', 'HaejoSourceCommit': '0123456789abcdef'}))
            self.assertEqual('haejo 1.0.0-rc.48 (0123456)', cli.version_text(module))


if __name__ == '__main__':
    unittest.main()
