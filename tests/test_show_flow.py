"""Inspecting reusable work should not dump expanded parser defaults."""
try:
    from tests import _isolation  # noqa: F401
except ImportError:  # discovered with tests/ as the top level
    import _isolation  # noqa: F401
from contextlib import redirect_stdout, redirect_stderr, chdir
from io import StringIO
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from haejo import cli
from haejo.flow import Flow, replay
from haejo.library import builders
from haejo.command_help import calculator_example
from tests.test_flow_safety_defaults import Calculator
import json


class ShowFlowTests(unittest.TestCase):
    def show(self, args):
        out = StringIO()
        with redirect_stdout(out), patch.object(cli, '_make_driver') as driver:
            code = cli._dispatch('show', args)
        driver.assert_not_called()
        return code, out.getvalue()

    def test_all_builtin_compact_outputs_preserve_executable_template_meaning(self):
        for name, build in builders().items():
            original = Flow.from_json(build().to_json())
            with self.subTest(name=name):
                code, output = self.show([name, '--compact'])
                self.assertEqual(0, code)
                self.assertEqual(original, Flow.from_json(output))
                full_code, full = self.show([name])
                self.assertEqual(0, full_code)
                self.assertEqual(original, Flow.from_json(full))
                self.assertLess(len(output.encode()), len(full.encode()))

    def test_file_inspection_is_read_only_and_result_can_replay(self):
        flow = Flow.from_json(json.dumps(calculator_example()))
        flow.steps[2].require_enabled = False
        with tempfile.TemporaryDirectory() as tmp:
            file = Path(tmp) / 'saved.json'
            file.write_text(flow.to_json())
            before = file.read_bytes()
            code, output = self.show([str(file), '--compact'])
            self.assertEqual(0, code)
            self.assertEqual(before, file.read_bytes())
            restored = Flow.from_json(output)
            self.assertFalse(restored.steps[2].require_enabled)
            app = Calculator()
            self.assertTrue(replay(app, restored).ok)
            self.assertEqual('408', app.value)
            with chdir(tmp):
                relative_code, relative_output = self.show(['saved.json', '--compact'])
            self.assertEqual((code, output), (relative_code, relative_output))

    def test_invalid_file_reports_short_error_without_repeating_contents(self):
        with tempfile.TemporaryDirectory() as tmp:
            file=Path(tmp)/'bad.json'
            file.write_text('{"schema": "PRIVATE_FLOW_CONTENT"}')
            err=StringIO()
            with redirect_stderr(err):
                code,output=self.show([str(file),'--compact'])
            self.assertEqual(2,code)
            self.assertIn('invalid_flow:',err.getvalue())
            self.assertNotIn('PRIVATE_FLOW_CONTENT',output+err.getvalue())

    def test_bad_arguments_and_help_do_not_load_or_run_a_flow(self):
        with patch.object(cli, '_load_recipe') as load:
            for args in ([], ['--compact'], ['name', '--unknown'], ['name', '--compact', 'extra']):
                with self.subTest(args=args):
                    code, output = self.show(args)
                    self.assertEqual(2, code)
                    self.assertIn('usage:', output)
            code, output = self.show(['--help'])
            self.assertEqual(0, code)
            self.assertIn('--compact', output)
            load.assert_not_called()
