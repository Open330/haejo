"""The CLI picks the UI Automation driver on Windows and refuses --helper there."""
try:
    from tests import _isolation  # noqa: F401
except ImportError:  # discovered with tests/ as the top level
    import _isolation  # noqa: F401
import sys
import unittest
from unittest.mock import patch

from haejo import cli


class WindowsCliTests(unittest.TestCase):
    def setUp(self):
        # cli.main records an access log; with sys.platform patched it would
        # otherwise land in the real profile (or ~/AppData on a Mac).
        import tempfile
        from pathlib import Path
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        logs = patch("haejo.access_log.log_directory", return_value=Path(folder.name) / "Haejo/Logs")
        logs.start()
        self.addCleanup(logs.stop)

    def test_windows_uses_uia_driver_and_never_falls_back_to_helper(self):
        made = []
        class Fake:
            def __init__(self):
                made.append(self)
        with patch.object(cli.sys, "platform", "win32"), \
             patch("haejo.windows_driver.WindowsDriver", Fake):
            self.assertIsInstance(cli._make_driver([]), Fake)
            with self.assertRaises(SystemExit):
                cli._make_driver(["--helper"])
        self.assertEqual(1, len(made))

    def test_screen_commands_skip_macos_session_probes_on_windows(self):
        import sys
        dispatched = []
        blocked = dict.fromkeys(("haejo.session", "Quartz"))
        with patch.object(cli.sys, "platform", "win32"), \
             patch.dict(sys.modules, blocked), \
             patch("haejo.windows_driver.keep_awake.__enter__", lambda self: self), \
             patch("haejo.windows_driver.keep_awake.__exit__", lambda self, *exc: False), \
             patch("haejo.windows_control.control.__enter__", lambda self: self), \
             patch("haejo.windows_control.control.__exit__", lambda self, *exc: False), \
             patch.object(cli, "_dispatch", side_effect=lambda cmd, rest: dispatched.append((cmd, rest)) or 0):
            self.assertEqual(0, cli.main(["apps"]))
            for macos_only in ("doctor", "launch", "first-run", "capture", "drag"):
                self.assertEqual(2, cli.main([macos_only]))
            # The notice flag is consumed before the command parses its args.
            self.assertEqual(0, cli.main(["observe", "notepad", "--no-indicator"]))
        self.assertEqual([("apps", []), ("observe", ["notepad"])], dispatched)

    def test_run_and_do_never_load_macos_modules_on_windows(self):
        import sys
        blocked = dict.fromkeys(("haejo.driver", "haejo.overlay", "haejo.onboard", "haejo.session",
                                 "AppKit", "Quartz", "ApplicationServices"))
        with patch.object(cli.sys, "platform", "win32"), patch.dict(sys.modules, blocked):
            with cli._indicator_for("notepad", []):
                pass
            from pathlib import Path
            source = Path(cli.__file__).read_text(encoding="utf-8")
        do = source[source.index('    if cmd == "do":'):]
        do = do[:do.index('learning = "--learn" in rest')]
        self.assertIn('if sys.platform != "win32":', do)
        self.assertLess(do.index('if sys.platform != "win32":'), do.index("from . import onboard"))

    def test_scroll_amounts_match_uia_enum(self):
        import ast, pathlib
        tree = ast.parse(pathlib.Path(cli.__file__).with_name("uia_backend.py").read_text())
        values = {}
        for node in ast.walk(tree):
            if (isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Tuple)
                    and isinstance(node.value, ast.Tuple)):
                for name, value in zip(node.targets[0].elts, node.value.elts):
                    if isinstance(name, ast.Name) and isinstance(value, ast.Constant):
                        values[name.id] = value.value
        # UIA ScrollAmount: LargeDecrement 0, SmallDecrement 1, NoAmount 2, LargeIncrement 3.
        self.assertEqual({"LARGE_DECREMENT": 0, "NO_AMOUNT": 2, "LARGE_INCREMENT": 3},
                         {k: values[k] for k in ("LARGE_DECREMENT", "NO_AMOUNT", "LARGE_INCREMENT")})

    def test_authoring_names_windows_apps_by_executable(self):
        from haejo import authoring
        class Driver:
            def list_targets(self):
                return {"apps": [{"id": "notepad.exe", "displayName": "Notepad", "pid": 1, "isRunning": True}]}
            def _resolve(self, target, launch=False):
                return 1 if target == "notepad.exe" else None
        prompts = []
        with patch.object(authoring.sys, "platform", "win32"):
            self.assertEqual("notepad.exe", authoring.guess_target("메모장에 적어줘", Driver()))
            self.assertIsNone(authoring.guess_target("계산기로 계산", Driver()))
            with patch.object(authoring, "reach_model", side_effect=lambda prompt, provider: prompts.append(prompt) or "notepad.exe"):
                self.assertEqual("notepad.exe", authoring.pick_target("write a note", Driver()))
        self.assertIn("executable name", prompts[0])
        self.assertNotIn("bundle identifier", prompts[0])
        with patch.object(authoring.sys, "platform", "darwin"):
            self.assertEqual(("bundle identifier", "com.apple.calculator"), authoring._target_kind())

    def test_session_observes_receives_and_replays_without_a_helper(self):
        import contextlib, io, json, os
        from tests.test_windows_driver import Backend, notepad
        from haejo.flow_session import run_session
        from haejo.windows_driver import WindowsDriver
        window, named = notepad()
        made = []
        def make(argv):
            made.append(list(argv))
            return WindowsDriver(Backend([window]))
        flow = {"schema": 2, "name": "note", "target": "notepad",
                "safety_defaults": {"effects": ["write_ephemeral"], "reversibility": "reversible",
                                    "resource": {"object_type": "editor entry", "scope": "entry"}},
                "steps": [{"action": "set_value", "selector": {"identifier": "body"}, "params": {"value": "hi"},
                           "postcondition": {"field": {"identifier": "body"}, "attribute": "Value", "equals": "hi"}}]}
        read, write = os.pipe()
        os.write(write, (json.dumps(flow) + "\n").encode()); os.close(write)
        messages = []
        out = io.StringIO()
        with patch.object(cli.sys, "platform", "win32"), os.fdopen(read) as stdin, \
             contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
            self.assertEqual(2, run_session(["notepad", "--helper"], make_driver=make, run_flow=cli._run_flow,
                                            stdin=stdin, emit=messages.append))
            self.assertEqual([], made)
            result = run_session(["notepad"], make_driver=make, run_flow=cli._run_flow, stdin=stdin,
                                 emit=messages.append)
        self.assertEqual(0, result, (messages, out.getvalue()))
        self.assertEqual([[]], made)
        self.assertEqual("hi", named["Text editor"].props["value"])
        self.assertTrue(any(m.startswith("HAEJO_SESSION_READY") for m in messages))

    def test_output_is_utf8_on_windows_even_where_the_code_page_cannot_hold_it(self):
        """Korean Windows pipes default to cp949; an emoji in a window title
        raised UnicodeEncodeError (jiun-home, 2026-11-10)."""
        import io
        streams = {name: io.TextIOWrapper(io.BytesIO(), encoding="cp949", newline="\n") for name in ("stdin", "stdout", "stderr")}
        with patch.object(cli.sys, "platform", "win32"), \
             patch.multiple(cli.sys, **streams):
            cli._utf8_streams()
            print("신청서 \u2705", file=cli.sys.stdout, flush=True)
            self.assertEqual("utf-8", cli.sys.stdin.encoding)
        self.assertEqual("신청서 \u2705\n".encode("utf-8"), streams["stdout"].buffer.getvalue())

    def test_journal_dir_is_refused_on_windows_before_anything_runs(self):
        import io
        import os
        from contextlib import redirect_stdout
        out = io.StringIO()
        with patch.object(cli.sys, "platform", "win32"), \
             patch.object(cli, "_dispatch_command", side_effect=AssertionError("dispatched")), \
             redirect_stdout(out):
            code = cli._dispatch("run", ["flow.json", "--journal-dir", os.path.abspath("runs-a")])
        self.assertEqual(2, code)
        self.assertIn("--journal-dir is macOS-only", out.getvalue())

    def test_every_text_read_names_its_encoding(self):
        """Without one, Windows reads with the ANSI code page: `batch` refused
        a UTF-8 Flow file holding Korean as an invalid schema (jiun-home,
        2026-11-10)."""
        import re
        from pathlib import Path
        source = Path(cli.__file__).parent
        offenders = [f"{path.name}:{number}" for path in sorted(source.glob("*.py"))
                     for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1)
                     if re.search(r"\.read_text\(\s*\)", line)]
        self.assertEqual([], offenders)

    def test_windows_guidance_never_suggests_the_refused_helper(self):
        from haejo import command_help
        with patch.object(command_help.sys, "platform", "win32"):
            guide = command_help.session_guide("notepad.exe", reusable=True)
        self.assertIn("haejo batch <file>", guide)
        self.assertNotIn("--helper", guide)

    def test_model_providers_are_refused_on_windows_without_starting_any(self):
        from haejo import authoring
        with patch.object(authoring.os, "name", "nt"), \
             patch.object(authoring, "_try_cli", side_effect=AssertionError("started")):
            with self.assertRaises(RuntimeError) as raised:
                authoring._ask_model("prompt")
        self.assertIn("macOS-only", str(raised.exception))

    def test_a_locked_product_folder_names_itself_and_the_repair(self):
        from pathlib import Path
        from haejo import private_fs
        folder = Path("Users/p/AppData/Local/Haejo")  # before os.name changes which Path class is made
        with patch("haejo.preferences.product_directory", return_value=folder), \
             patch.object(private_fs.os, "name", "nt"):
            hint = private_fs.access_repair_hint(PermissionError(13, "denied"))
            other = private_fs.access_repair_hint(FileNotFoundError())
        self.assertIn("/reset", hint)
        self.assertIn("Haejo", hint)
        self.assertEqual("", other)
        with patch.object(private_fs.os, "name", "posix"):
            self.assertEqual("", private_fs.access_repair_hint(PermissionError()))

    def test_private_folders_on_windows_inherit_the_profile_acl(self):
        """A mode makes Python write an owner-only ACL, and a folder an
        elevated process created then locks out the person's normal runs."""
        from haejo import private_fs
        calls = []
        class Folder:
            def mkdir(self, **kwargs):
                calls.append(kwargs)
        with patch.object(private_fs.os, "name", "nt"):
            private_fs.mkdir_private(Folder(), parents=True, exist_ok=True)
        with patch.object(private_fs.os, "name", "posix"):
            private_fs.mkdir_private(Folder())
        self.assertEqual([{"parents": True, "exist_ok": True},
                          {"mode": 0o700, "parents": False, "exist_ok": False}], calls)

    @unittest.skipUnless(sys.platform == "darwin", "haejo.driver imports macOS frameworks")
    def test_macos_selection_is_unchanged(self):
        with patch.object(cli.sys, "platform", "darwin"), \
             patch("haejo.driver.Driver") as driver, \
             patch("haejo.helper.InheritedHelperDriver") as helper:
            cli._make_driver([])
            cli._make_driver(["--helper"])
        driver.assert_called_once_with()
        helper.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
