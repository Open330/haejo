"""Regressions found in accumulated june-mba usage (2026-10-19..11-06)."""
try:
    from tests import _isolation  # noqa: F401
except ImportError:  # discovered with tests/ as the top level
    import _isolation  # noqa: F401
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


class AccessLogRetentionTests(unittest.TestCase):
    def test_a_polling_burst_does_not_evict_the_retention_window(self):
        from haejo import access_log
        # 77 observes in 24 s on 2026-11-04 evicted the whole history at 200.
        self.assertGreaterEqual(access_log.MAX_FILES, 2000)
        self.assertLessEqual(access_log.MAX_FILES * 4096, access_log.MAX_TOTAL * 2)

    def test_an_exit_two_without_a_reason_is_named(self):
        from haejo.access_log import AccessLog
        with tempfile.TemporaryDirectory() as folder:
            log = AccessLog('launch', root=Path(folder)/'Haejo/Logs')
            log.finish(2); log.close()
            events = [json.loads(l) for l in log.path.read_text().splitlines()]
        self.assertEqual(['command_start', 'task_result', 'command_end'], [e['event'] for e in events])
        self.assertEqual('unreported_refusal', events[1]['error'])

    def test_a_recorded_failure_is_not_overwritten(self):
        from haejo.access_log import AccessLog
        with tempfile.TemporaryDirectory() as folder:
            log = AccessLog('run', root=Path(folder)/'Haejo/Logs')
            log.task_result({'status': 'failed', 'stage': 'load', 'error': 'invalid_flow'})
            log.finish(2); log.close()
            errors = [json.loads(l).get('error') for l in log.path.read_text().splitlines()]
        self.assertEqual(['invalid_flow'], [e for e in errors if e])


class NavigationWordTests(unittest.TestCase):
    def effects(self, line):
        from haejo.safety import effects_of
        return effects_of({'name': 'click'}, line)[0]

    def test_go_to_folder_is_navigation(self):
        self.assertEqual({'write_ephemeral'}, self.effects('7 MenuItem  Title: 폴더로 이동…'))
        self.assertEqual({'write_ephemeral'}, self.effects('3 Button  Title: 다음 항목으로 이동'))

    def test_moving_data_still_counts(self):
        self.assertEqual({'write_persistent'}, self.effects('4 MenuItem  Title: 여기로 항목 이동'))
        self.assertEqual({'write_persistent'}, self.effects('4 Button  Title: 이동'))
        self.assertEqual({'delete'}, self.effects('5 MenuItem  Title: 휴지통으로 이동'))
        self.assertEqual({'write_persistent'}, self.effects('8 MenuItem  Title: 폴더로 이동 후 저장'))


class RefusalExplanationTests(unittest.TestCase):
    def test_no_terminal_names_the_flag(self):
        from haejo.cli import _confirmer
        from haejo.safety import unanswered_confirmation
        with patch('sys.stdin.isatty', return_value=False):
            ask = _confirmer([])
        self.assertFalse(ask('x'))
        self.assertIn('--yes', unanswered_confirmation(ask))
        self.assertIn('--yes', unanswered_confirmation(None))
        self.assertEqual('', unanswered_confirmation(lambda what: False))


class NotFoundHintTests(unittest.TestCase):
    def driver(self, reply):
        from haejo import helper
        d = object.__new__(helper.HelperDriver)
        d._last_action_at = 0
        d._send = lambda msg: dict(reply)
        return helper, d

    def test_a_stopped_app_names_launch(self):
        helper, d = self.driver({'type': 'error', 'error': 'target_not_found', 'target': 'com.apple.Home'})
        with patch('haejo.session.lock_state', return_value={'locked': False}):
            out = helper.HelperDriver.observe(d, 'com.apple.Home')
        self.assertIn('haejo launch com.apple.Home --helper', out['hint'])

    def test_a_locked_screen_is_said_instead(self):
        helper, d = self.driver({'type': 'error', 'error': 'target_not_found', 'target': 'com.apple.Home'})
        with patch('haejo.session.lock_state', return_value={'locked': True}):
            out = helper.HelperDriver.observe(d, 'com.apple.Home')
        self.assertEqual('screen_locked', out['reason'])
        self.assertNotIn('haejo launch', out['hint'])


class SystemSurfaceTests(unittest.TestCase):
    def test_dock_is_not_called_a_menu_bar_app(self):
        from haejo import driver
        app = type('App', (), {'isHidden': lambda self: False, 'activationPolicy': lambda self: 1,
                               'bundleIdentifier': lambda self: 'com.apple.dock'})()
        fake = type('NSRunningApplication', (), {
            'runningApplicationWithProcessIdentifier_': staticmethod(lambda pid: app)})
        with patch('AppKit.NSRunningApplication', fake), \
             patch.object(driver, 'AXUIElementCreateApplication', return_value='ax'), \
             patch.object(driver, '_attr', side_effect=lambda el, name: [] if name == 'AXWindows' else el):
            reason, detail = driver._why_no_window(1, {'locked': False})
        self.assertEqual('system_ui_surface', reason)
        self.assertNotIn('사람', detail)

    def test_no_window_hints_hand_nothing_to_a_person(self):
        source = Path(__file__).resolve().parents[1].joinpath('haejo/driver.py').read_text()
        start = source.index('def _why_no_window')
        body = source[start:source.index('\ndef ', start + 1)]
        self.assertNotIn('사람이', body)
        self.assertIn('{\\"action\\":\\"reopen_window\\"}', body)


class AuthoringHintTests(unittest.TestCase):
    def feedback(self, step):
        from haejo.flow import Flow
        from haejo.flow_errors import feedback
        flow = {"schema": 2, "name": "x", "target": "com.example.app", "steps": [step]}
        try:
            Flow.from_json(json.dumps(flow))
        except Exception as error:
            return feedback(error)
        return None

    SAFETY = {"effects": ["write_ephemeral"], "reversibility": "reversible",
              "resource": {"object_type": "field", "scope": "entry"}}

    def test_params_hint_names_this_actions_params(self):
        out = self.feedback({"action": "type_text", "selector": {"role": "TextField"},
                             "params": {"value": "SECRET"}, "safety": self.SAFETY})
        self.assertIn("type_text takes params: text", out)
        self.assertNotIn("SECRET", out)

    def test_step_fields_inside_safety_are_named(self):
        out = self.feedback({"action": "click", "selector": {"role": "Button", "title": "Install"},
                             "safety": {**self.SAFETY, "intent_text": "SECRET", "binding": {}}})
        self.assertIn("Move binding, intent_text to the step itself", out)
        self.assertNotIn("SECRET", out)

    def test_unknown_safety_field_is_refused_without_echo(self):
        out = self.feedback({"action": "click", "selector": {"role": "Button", "title": "Install"},
                             "safety": {**self.SAFETY, "SECRET_KEY": 1}})
        self.assertIn("safety takes:", out)
        self.assertNotIn("SECRET", out)


class EmptyEqualsTests(unittest.TestCase):
    TREE = ('0 Window  Title: "Untitled" [focused]\n  1 ScrollArea\n'
            '    2 TextArea  Identifier: First Text View, Secondary Actions: ShowMenu')

    def test_an_absent_value_is_empty(self):
        from haejo.flow import Postcondition, Selector
        check = Postcondition(field=Selector(identifier="First Text View"), equals="")
        self.assertTrue(check.check(self.TREE))
        self.assertFalse(check.check(self.TREE.replace("Identifier: First", "Value: hi, Identifier: First")))

    def test_a_child_value_is_not_empty(self):
        from haejo.flow import Postcondition, Selector
        tree = self.TREE + "\n      3 StaticText  Value: hi"
        self.assertFalse(Postcondition(field=Selector(identifier="First Text View"), equals="").check(tree))


class CaptureElementIndexTests(unittest.TestCase):
    PNG = (b"\x89PNG\r\n\x1a\n" + b"\x00\x00\x00\rIHDR" + (2).to_bytes(4, "big") + (3).to_bytes(4, "big")
           + b"\x08\x06\x00\x00\x00")

    def driver(self, capabilities):
        import hashlib
        png = self.PNG
        calls = []

        class Driver:
            def capture(self, target, *, obs_id, path, timeout_seconds, **index):
                calls.append(index)
                Path(path).write_bytes(png)
                return {"type": "capture", "obs_id": obs_id, "target": target, "pid": 7, "window_id": 9,
                        "window_index": 1, "element_index": index.get("element_index"),
                        "image_mapping": "full_window_no_shadow", "window_frame": [0, 0, 2, 3],
                        "width": 2, "height": 3, "capture_id": "c", "sha256": hashlib.sha256(png).hexdigest()}
        d = Driver()
        d.capabilities = capabilities
        return d, calls

    def test_the_window_line_number_is_sent_as_an_element(self):
        from haejo.native_visual_actions import capture_window
        d, calls = self.driver({"capture.element_index"})
        image = capture_window(d, "o", "com.example.app", window_index=118)
        self.assertEqual([{"element_index": 118}], calls)
        self.assertEqual(118, image.window_index)

    def test_an_older_helper_keeps_the_previous_request(self):
        from haejo.native_visual_actions import capture_window
        d, calls = self.driver(set())
        with self.assertRaises(Exception):
            capture_window(d, "o", "com.example.app", window_index=118)
        self.assertEqual([{"window_index": 118}], calls)

    def test_the_helper_announces_and_accepts_it(self):
        source = Path(__file__).resolve().parents[1].joinpath("helper/HaejoHelper.swift").read_text()
        self.assertIn('"capture.element_index"', source)
        self.assertIn('"element_index", "timeout_seconds"]', source)


class UnregisteredRunningAppTests(unittest.TestCase):
    def backend(self):
        from tests.test_app_launch import Backend
        b = Backend()
        b.path = None
        b.apps = [dict(pid=7, path='/var/folders/x/Itda Native Quit.app', ready=True)]
        return b

    def test_launch_reports_the_running_copy(self):
        from haejo.app_launch import launch_app
        b = self.backend()
        result = launch_app('dev.jiun.itda', backend=b, clock=lambda: b.time)
        self.assertEqual(('already_running', 7, 0), (result.get('status'), result.get('pid'), b.starts))

    def test_activate_does_not_say_not_installed(self):
        from haejo import app_launch
        b = self.backend()
        with patch.object(app_launch, 'present_app', return_value={'type': 'app_activation', 'pid': 7}) as present:
            result = app_launch._activate_app('dev.jiun.itda', backend=b, clock=lambda: 0)
        self.assertNotEqual('application_not_installed', result.get('error'))
        self.assertEqual(7, present.call_args.args[1])

    def test_two_unregistered_copies_stay_ambiguous(self):
        from haejo import app_launch
        b = self.backend()
        b.apps = b.apps * 2
        self.assertEqual('application_identity_ambiguous',
                         app_launch._activate_app('dev.jiun.itda', backend=b, clock=lambda: 0)['error'])

    def test_launch_timeout_names_the_running_process(self):
        from haejo.app_launch import launch_app
        from tests.test_app_launch import Backend
        b = Backend()
        b.finish = False
        def pump(seconds):
            b.time += seconds
            b.apps = [dict(pid=9, path=b.path, ready=False)]
        b.pump = pump
        result = launch_app('com.example.app', backend=b, clock=lambda: b.time, timeout=0.2)
        self.assertEqual(('launch_timeout', 9, True), (result['error'], result.get('pid'), result.get('application_running')))


class QuitStepTests(unittest.TestCase):
    def run_quit(self, steps):
        from haejo.flow import Flow, replay
        flow = Flow.from_json(json.dumps({"schema": 2, "name": "quit", "target": "com.example.app", "steps": steps}))

        class App:
            capabilities = set()
            acted = False
            def observe(self, target, mode="tree_full", **kwargs):
                if self.acted:
                    return {"type": "error", "error": "target_not_found", "target": target}
                return {"type": "observation", "obs_id": "o", "tree": '0 Window  Title: "Main" [focused]\n  1 Button  Title: Next'}
            def act(self, obs, target, action, **kwargs):
                self.acted = True
                return {"type": "acted", "action": action["name"], "obs_id": obs}
            def wait_until(self, target, predicate, **kwargs):
                return self.observe(target)
        app = App()
        return app, replay(app, flow)

    MENU = {"action": "menu", "params": {"path": ["Example", "Quit Example"]}, "unverified_ok": True,
            "safety": {"effects": ["write_ephemeral"], "reversibility": "reversible",
                       "resource": {"object_type": "app", "scope": "item"}}}

    def test_a_final_quit_is_done(self):
        app, result = self.run_quit([self.MENU])
        self.assertTrue(result.ok, result.log)
        self.assertTrue(any(e.get("target_terminated") for e in result.log))

    def test_an_exit_before_more_steps_stops_without_resend(self):
        click = {"action": "click", "selector": {"role": "Button", "title": "Next"},
                 "safety": self.MENU["safety"], "unverified_ok": True}
        app, result = self.run_quit([self.MENU, click])
        self.assertFalse(result.ok)
        self.assertTrue(result.log[-1].get("target_terminated"))
        self.assertEqual("acted", result.log[-1].get("effect"))


class ObserveUntilTests(unittest.TestCase):
    def run_cli(self, args, trees):
        import contextlib, io
        from haejo import cli

        class D:
            def wait_until(self, target, predicate, timeout_ms, poll_ms):
                self.timeout_ms = timeout_ms
                for tree in trees:
                    if predicate(tree):
                        return {"type": "observation", "tree": tree, "obs_id": "o"}
                return {"type": "timeout", "last_obs": {"tree": trees[-1]}}
        out = io.StringIO()
        with patch.object(cli, "_make_driver", return_value=D()), contextlib.redirect_stdout(out):
            code = cli._main(["observe", "com.example.app", *args])
        return code, out.getvalue()

    TREES = ['0 Window  Title: "A"\n  1 StaticText  Identifier: s, Value: pending',
             '0 Window  Title: "A"\n  1 StaticText  Identifier: s, Value: done']

    def test_text_and_field_conditions(self):
        code, out = self.run_cli(["--until-text", "done", "--json"], self.TREES)
        self.assertEqual(0, code); self.assertIn("waited_s", out)
        code, _ = self.run_cli(["--until", '{"field":{"identifier":"s"},"equals":"done"}'], self.TREES)
        self.assertEqual(0, code)
        code, out = self.run_cli(["--until-gone", "Window"], self.TREES)
        self.assertEqual(1, code); self.assertIn("until_timeout", out)

    def test_bad_conditions_are_usage_errors(self):
        self.assertEqual(2, self.run_cli(["--until-text", "a", "--until-gone", "b"], self.TREES)[0])
        self.assertEqual(2, self.run_cli(["--until-text", "a", "--timeout", "0"], self.TREES)[0])
        code, out = self.run_cli(["--until", '{"field":{"SECRET":1},"equals":"x"}'], self.TREES)
        self.assertEqual(2, code); self.assertNotIn("SECRET", out)


class NearAndPlaceholderTests(unittest.TestCase):
    TREE = """0 Window  Title: "Itda" [focused]
  1 Group
    2 StaticText  Value: jiun-MBP
    3 Button  Description: 더보기
  4 Group
    5 StaticText  Value: june-MBA
    6 Button  Description: 더보기
  7 TextField  Placeholder: 검색하거나 입력"""

    def test_near_picks_the_repeat_next_to_its_label(self):
        from haejo.flow import Selector, TargetAmbiguous, TargetMissing
        self.assertEqual(6, Selector(role="Button", desc="더보기", near="june-MBA").resolve(self.TREE)[0])
        self.assertEqual(3, Selector(role="Button", desc="더보기", near="jiun-MBP").resolve(self.TREE)[0])
        with self.assertRaises(TargetAmbiguous):
            Selector(role="Button", desc="더보기").resolve(self.TREE)
        with self.assertRaises(TargetMissing):
            Selector(role="Button", desc="더보기", near="nobody").resolve(self.TREE)

    def test_placeholder_names_a_field(self):
        from haejo.flow import Selector, _selector_from
        self.assertEqual(7, Selector(placeholder="검색하거나 입력").resolve(self.TREE)[0])
        self.assertEqual("검색하거나 입력", _selector_from({"placeholder": "검색하거나 입력"}).placeholder)
        with self.assertRaises(ValueError):
            _selector_from({"role": "Button", "near": 3})


class HelperSourceTests(unittest.TestCase):
    """The Swift halves; behavior is checked on a signed helper, wording here."""
    ROOT = Path(__file__).resolve().parents[1]

    def test_status_item_is_announced_and_windowless(self):
        source = (self.ROOT / "helper/HaejoHelper.swift").read_text()
        self.assertIn('"action.status_item"', source)
        self.assertIn('case "status_item":', source)
        self.assertIn('"close_menu", "status_item"].contains', source)
        from haejo.protocol import ACTION_PARAMS
        self.assertEqual(frozenset({"title"}), ACTION_PARAMS["status_item"])

    def test_aborts_name_their_source_and_disconnects_are_not_stops(self):
        source = (self.ROOT / "helper/HaejoHelper.swift").read_text()
        self.assertIn('abortState.stopNow("indicator_stop")', source)
        self.assertIn('named["abort_source"] = abortState.source', source)
        self.assertEqual(3, source.count("withAbortSource("))  # definition + two writers
        parallel = (self.ROOT / "helper/ParallelWindows.swift").read_text()
        self.assertIn('"client_disconnected"', parallel)
        self.assertNotIn('cancelled() ? "aborted_by_user" : "target_busy"', parallel)

    def test_busy_names_the_holder(self):
        lease = (self.ROOT / "HelperModeProtocol.swift").read_text()
        self.assertIn("static func holder(", lease)
        self.assertIn('"holder_pid"', lease)
        self.assertIn("LOCAL_PEERPID", (self.ROOT / "helper/ParallelWindows.swift").read_text())

    def test_show_menu_error_checks_for_an_opened_menu(self):
        source = (self.ROOT / "helper/HaejoHelper.swift").read_text()
        body = source[source.index('    case "secondary_action":'):]
        body = body[:body.index("    default:")]
        self.assertIn("menusBefore", body)
        self.assertIn('"ax_error"', body)


class SessionLeaseTests(unittest.TestCase):
    def test_an_idle_session_releases_the_app(self):
        source = Path(__file__).resolve().parents[1].joinpath("haejo/flow_session.py").read_text()
        body = source[source.index("def show_observation"):source.index("def additional_observation")]
        self.assertIn("release_targets", body)
        self.assertIn("window_id is None and document is None", body)


if __name__ == '__main__':
    unittest.main()


class LiveCheckFollowUpTests(unittest.TestCase):
    """Found driving the rebuilt helper on a real Mac (2026-11-06)."""
    ROOT = Path(__file__).resolve().parents[1]

    def run_until(self, raw):
        import contextlib, io
        from haejo import cli
        driver = unittest.mock.MagicMock()
        out = io.StringIO()
        with patch.object(cli, "_make_driver", return_value=driver), contextlib.redirect_stdout(out):
            code = cli._main(["observe", "com.example.app", "--until", raw, "--timeout", "1"])
        return code, out.getvalue(), driver

    def test_an_until_that_can_never_pass_is_refused_before_waiting(self):
        for raw, words in (('{"not":1}', "unknown key"),
                           ('{"field":{"title":"A"}}', "add equals"),
                           ('{"field":{"role":"Window"},"contains":"x"}', "names no element"),
                           ('{nope', "not JSON")):
            code, out, driver = self.run_until(raw)
            self.assertEqual(2, code, raw); self.assertIn(words, out)
            driver.wait_until.assert_not_called()
        self.assertNotIn("not,", self.run_until('{"not":1}')[1].split("use only")[0])

    def test_a_read_only_wait_gives_the_app_back_between_polls(self):
        from haejo.helper import HelperDriver
        driver = HelperDriver.__new__(HelperDriver)
        driver.capabilities = {"session.release_targets"}
        replies = iter([{"type": "error", "error": "target_busy", "effect": "not_started"},
                        {"type": "observation", "tree": "pending", "obs_id": "a"},
                        {"type": "observation", "tree": "done", "obs_id": "b"}])
        driver.observe = lambda target, **kwargs: next(replies)
        driver.release_targets = unittest.mock.MagicMock(return_value={"type": "targets_released"})
        obs = driver.wait_until("x", lambda tree: tree == "done", timeout_ms=5000, poll_ms=1, yield_between=True)
        self.assertEqual("b", obs["obs_id"])
        self.assertEqual(2, driver.release_targets.call_count)

    def test_without_yield_a_busy_app_still_stops_the_wait(self):
        from haejo.helper import HelperDriver
        driver = HelperDriver.__new__(HelperDriver)
        driver.capabilities = set()
        driver.observe = lambda target, **kwargs: {"type": "error", "error": "target_busy"}
        self.assertEqual("target_busy", driver.wait_until("x", bool, timeout_ms=5000, poll_ms=1)["error"])

    def replay(self, steps, after):
        from haejo.flow import Flow, replay
        flow = Flow.from_json(json.dumps({"schema": 2, "name": "t", "target": "com.example.app", "steps": steps}))

        class App:
            capabilities = set()
            acted = None
            def observe(self, target, mode="tree_full", **kwargs):
                if self.acted:
                    return after
                return {"type": "observation", "obs_id": "o", "tree": '0 Window  Title: "Main" [focused]'}
            def act(self, obs, target, action, **kwargs):
                self.acted = action
                reply = {"type": "acted", "action": action["name"], "obs_id": obs}
                if action["name"] == "close_menu":
                    reply.update(menus_closed=1, menus_open=0)
                return reply
            def wait_until(self, target, predicate, **kwargs):
                return self.observe(target)
        app = App()
        return app, replay(app, flow)

    SAFETY = {"effects": ["write_ephemeral"], "reversibility": "reversible",
              "resource": {"object_type": "menu", "scope": "item"}}

    def test_a_quit_checked_by_absence_is_done(self):
        # Menu steps refuse to run without a check, and "gone" is the natural one.
        step = {"action": "menu", "params": {"path": ["Example", "Quit Example"]},
                "postcondition": {"absent": "Main"}, "safety": self.SAFETY}
        _, result = self.replay([step], {"type": "error", "error": "target_not_found"})
        self.assertTrue(result.ok, result.log)
        self.assertEqual("target_terminated", result.log[0]["verified"])

    def test_a_quit_checked_by_presence_still_stops(self):
        step = {"action": "menu", "params": {"path": ["Example", "Quit Example"]},
                "postcondition": {"contains": "Saved"}, "safety": self.SAFETY}
        _, result = self.replay([step], {"type": "error", "error": "target_not_found"})
        self.assertFalse(result.ok)
        self.assertTrue(result.log[-1].get("target_terminated"))

    def test_closing_a_menu_bar_apps_menu_leaves_no_window_and_is_done(self):
        step = {"action": "close_menu", "unverified_ok": True, "safety": self.SAFETY}
        after = {"type": "error", "error": "no_window_content", "reason": "menu_bar_app"}
        _, result = self.replay([step], after)
        self.assertTrue(result.ok, result.log)
        self.assertEqual("menus_closed", result.log[0]["verified"])

    def test_secondary_action_takes_the_name_the_tree_prints(self):
        from haejo.flow import Flow
        from haejo.flow_errors import FlowFieldError
        def parse(name):
            return Flow.from_json(json.dumps({"schema": 2, "name": "t", "target": "com.example.app", "steps": [
                {"action": "secondary_action", "selector": {"role": "Button", "title": "A"},
                 "params": {"action": name}}]}))
        self.assertEqual("AXShowMenu", parse("ShowMenu").steps[0].params["action"])
        self.assertEqual("AXShowMenu", parse("AXShowMenu").steps[0].params["action"])
        with self.assertRaises(FlowFieldError):
            parse("AXRaise")

    def test_a_blocked_step_says_why(self):
        from haejo.agent import Agent
        from haejo.flow import Flow
        flow = Flow.from_json(json.dumps({"schema": 2, "name": "t", "target": "com.example.app", "steps": [
            {"action": "menu", "params": {"path": ["A", "B"]}, "unverified_ok": True,
             "safety": {**self.SAFETY, "resource": {"object_type": "app", "scope": "app"}}}]}))
        agent = Agent.__new__(Agent)
        _, blocked = agent.authorize(flow, ask=None)
        self.assertEqual(1, len(blocked)); self.assertIn("unknown resource scope", blocked[0])

    def test_the_launcher_lets_the_new_requests_through(self):
        source = (self.ROOT / "launcher/haejo.swift").read_text()
        self.assertIn('"status_item":      (["name"], ["title"])', source)
        self.assertIn('"window_index", "element_index", "timeout_seconds"', source)
        self.assertIn('capture element_index 오류', source)

    def test_an_open_status_menu_is_observed_and_closable(self):
        source = (self.ROOT / "helper/HaejoHelper.swift").read_text()
        self.assertIn("func openStatusMenus(_ p: pid_t)", source)
        self.assertIn('reply["status_menu_open"] = true', source)
        self.assertIn("openContextMenus(pid: p) + openStatusMenus(p)", source)
