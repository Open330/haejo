"""`replay`/`run` refuse bad names and parameters with a named reason, not a traceback."""
import io
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from haejo import cli
from haejo.flow import _arith


class ReplayRefusalTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def run_cli(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        with patch.object(cli, '_run_flow', side_effect=AssertionError('replayed')), \
             patch('haejo.access_log.log_directory', lambda: Path(self.tmp.name)/'Logs'), \
             redirect_stdout(out), redirect_stderr(err):
            code = cli.main(list(argv))
        return code, out.getvalue() + err.getvalue()

    def test_unknown_recipe_name(self):
        code, out = self.run_cli('replay', 'no_such_recipe_7f3a')
        self.assertEqual(2, code)
        self.assertIn('unknown_flow', out)
        self.assertNotIn('Traceback', out)

    def test_operator_outside_the_grammar(self):
        for op in ('×', 'add', '1+'):
            code, out = self.run_cli('replay', 'calc_arith', '-p', 'a=6', '-p', 'b=7', '-p', f'op={op}')
            self.assertEqual(2, code, op)
            self.assertIn('invalid_parameters', out)

    def test_run_file_with_bad_operator(self):
        path = Path(self.tmp.name)/'calc.json'
        path.write_text(cli._load_recipe('calc_arith').to_json())
        code, out = self.run_cli('run', str(path), '-p', 'op=×')
        self.assertEqual((2, True), (code, 'invalid_parameters' in out))

    def test_arith_syntax_error_is_a_value_error(self):
        with self.assertRaises(ValueError):
            _arith('6 × 7')
        self.assertEqual(42, _arith('6 * 7'))


if __name__ == '__main__':
    unittest.main()
