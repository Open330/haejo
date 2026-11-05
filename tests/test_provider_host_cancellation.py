"""Host cancellation of in-flight model requests: local only, never remote.

Owned local subprocesses only; no model, network or native GUI actions.
"""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from tacto import authoring
from tacto.model_budget import (ModelCancelled, model_cancellation, model_cancelled,
                                remaining_model_seconds)
from tacto.opencode_result import opencode_result
from tacto.provider_result import ProviderResult
from tests.test_opencode_result import frames as opencode_frames
from tests.test_claude_result import stream


def owned_cli(ready, marker, *, stdout=''):
    """A CLI that prints, starts a delayed-write descendant, then hangs."""
    descendant = ('import pathlib,time;time.sleep(1.2);pathlib.Path('
                  + repr(str(marker)) + ').write_text("survived")')
    return ('import json,os,pathlib,subprocess,sys,time;sys.stdin.read();'
            + 'sys.stdout.write(' + repr(stdout) + ');sys.stdout.flush();'
            + 'child=subprocess.Popen([sys.executable,"-c",' + repr(descendant) + ']);'
            + 'pathlib.Path(' + repr(str(ready)) + ').write_text(json.dumps({"group":os.getpid()}));'
            + 'time.sleep(20)')


def cancel_after_ready(ready, delay=0.2):
    """Cancel only once the owned CLI demonstrably started its descendant."""
    seen = []
    def predicate():
        if not ready.exists():
            return False
        seen.append(time.monotonic())
        return time.monotonic() - seen[0] >= delay
    return predicate


def group_gone(group):
    try:
        os.killpg(group, 0)
    except ProcessLookupError:
        return True
    except PermissionError:
        return False
    return False


@unittest.skipUnless(os.name == 'posix', 'owned POSIX process groups')
class HostCancellationTests(unittest.TestCase):
    def test_scope_nesting_and_failing_predicate(self):
        self.assertFalse(model_cancelled())
        with model_cancellation(None):
            self.assertFalse(model_cancelled())
            self.assertEqual(5, remaining_model_seconds(5))
        flag = []
        with model_cancellation(lambda: bool(flag)):
            self.assertFalse(model_cancelled())
            with model_cancellation(lambda: False):
                flag.append(1)
                # An outer scope's cancellation reaches nested requests.
                self.assertTrue(model_cancelled())
                with self.assertRaises(ModelCancelled):
                    remaining_model_seconds(5)
        self.assertFalse(model_cancelled())
        def broken():
            raise RuntimeError('cannot read stop state')
        with model_cancellation(broken):
            self.assertTrue(model_cancelled())
        with self.assertRaises(TypeError):
            with model_cancellation('not callable'):
                pass

    def test_cancellation_stops_owned_group_before_descendant_write(self):
        from tacto import codex_result, claude_result
        for runner in ('authoring', 'codex', 'claude'):
            with self.subTest(runner=runner), tempfile.TemporaryDirectory() as folder:
                ready, marker = Path(folder) / 'ready', Path(folder) / 'survived'
                argv = [sys.executable, '-c', owned_cli(ready, marker, stdout='partial-line\n')]
                started = time.monotonic()
                with model_cancellation(cancel_after_ready(ready)), self.assertRaises(ModelCancelled) as caught:
                    if runner == 'authoring':
                        authoring._run_provider(argv, 30, input_text='owned')
                    elif runner == 'codex':
                        codex_result._run_codex(argv, 'owned', 30)
                    else:
                        claude_result._run_claude(argv, 'owned', 30, None)
                elapsed = time.monotonic() - started
                self.assertTrue(ready.exists(), 'the CLI must have started, not a pre-launch refusal')
                self.assertLess(elapsed, 5, 'cancellation must not wait for the 30 s deadline')
                self.assertIn(b'partial-line', caught.exception.output)
                group = json.loads(ready.read_text())['group']
                self.assertTrue(group_gone(group))
                time.sleep(1.6)
                self.assertFalse(marker.exists(), 'descendant outlived host cancellation')

    def test_partial_observed_usage_survives_cancellation_without_answer(self):
        with tempfile.TemporaryDirectory() as folder:
            ready, marker = Path(folder) / 'ready', Path(folder) / 'survived'
            script = owned_cli(ready, marker, stdout=stream(opencode_frames()))
            original_run = authoring._run_provider
            def launch(*args, **kwargs):
                return original_run([sys.executable, '-c', script], 30, input_text='q')
            with patch('tacto.authoring._run_provider', side_effect=launch), \
                    model_cancellation(cancel_after_ready(ready)):
                result = opencode_result('q', timeout=30)
        self.assertEqual('cancelled', result.status)
        self.assertIsNone(result.text)
        self.assertEqual('ModelCancelled', result.error.code)
        self.assertIn('not confirmed stopped', result.error.message)
        self.assertEqual(18, result.total_input_tokens)
        self.assertFalse(result.cancellation_supported)

    def test_auto_fallback_never_starts_after_cancellation(self):
        calls = []
        def route(name, prompt, timeout):
            calls.append(name)
            if name == 'codex':
                return ProviderResult('r', 'codex', 'codex', 'cli-json', 'cancelled', None,
                                      None, 0.1, input_tokens=7, output_tokens=2,
                                      input_tokens_basis='total', total_input_tokens=7)
            self.fail('fallback provider started after cancellation')
        with patch.object(authoring, 'PROVIDER_ORDER', ('codex', 'gemini')), \
                patch.object(authoring, '_try_cli', side_effect=route), \
                patch.object(authoring, '_unavailable_until', {}):
            result = authoring.ask_model_result('q', 'auto', timeout=30)
        self.assertEqual(['codex'], calls)
        self.assertEqual('cancelled', result.status)
        self.assertEqual('ModelCancelled', result.error.code)
        self.assertFalse(result.cancellation_supported)
        last = result.attempts[-1]
        self.assertEqual(('codex', 'cli-json', 'cancelled'), (last.provider, last.transport, last.status))
        self.assertEqual((7, 2), (last.input_tokens, last.output_tokens))
        # The envelope still parses as a transport record.
        from tacto.provider_result import parse_provider_result
        self.assertEqual('cancelled', parse_provider_result(result.to_dict()).status)

    def test_generic_cli_cancellation_and_pre_start_cancellation(self):
        def raising(name, prompt, timeout):
            raise ModelCancelled(output=b'private')
        with patch.object(authoring, '_try_cli', side_effect=raising), \
                patch.object(authoring, '_unavailable_until', {}):
            result = authoring.ask_model_result('q', 'opencode', timeout=30)
        self.assertEqual('cancelled', result.status)
        self.assertEqual('cancelled', result.attempts[-1].status)
        self.assertNotIn('private', json.dumps(result.to_dict()))
        with patch.object(authoring, '_try_cli', side_effect=AssertionError('started')), \
                model_cancellation(lambda: True):
            result = authoring.ask_model_result('q', 'auto', timeout=30)
        self.assertEqual('cancelled', result.status)
        self.assertEqual((), result.attempts)

    def test_validation_retry_does_not_follow_cancellation(self):
        from tacto import ask as ask_module
        from tacto.ask import Q
        sent = []
        def reach(prompt, *args, **kwargs):
            sent.append(prompt)
            raise ModelCancelled()
        with patch.object(ask_module, 'reach_model', side_effect=reach):
            with self.assertRaises(ModelCancelled):
                ask_module.ask(Q('k', 'p', lambda raw: None), validation_retries=2)
        self.assertEqual(1, len(sent))


class App:
    tree = "0 Window Title: Test\n  1 TextField Title: Entry, Value: hello"

    def __init__(self):
        self.calls = []

    def observe(self, *args, **kwargs):
        return {"type": "observation", "obs_id": "obs", "tree": self.tree}

    def probe(self, *args, **kwargs):
        return {"type": "probe", "line": self.tree.splitlines()[1]}

    def act(self, obs_id, target, action, **kwargs):
        self.calls.append(action)
        return {"type": "acted"}

    def wait_until(self, *args, **kwargs):
        return {"type": "observation", "tree": self.tree}


@unittest.skipUnless(os.name == 'posix', 'owned POSIX process groups')
class GeneralMidRequestCancellationTests(unittest.TestCase):
    def test_general_cancel_during_request_stops_cli_and_keeps_attempt(self):
        from tacto.general import run
        with tempfile.TemporaryDirectory() as folder:
            ready, marker = Path(folder) / 'ready', Path(folder) / 'survived'
            script = owned_cli(ready, marker, stdout=stream(opencode_frames()))
            def route(name, prompt, timeout):
                if name != 'opencode':
                    raise AssertionError('fallback provider started after cancellation')
                with patch('tacto.authoring._run_provider', side_effect=lambda *a, **k:
                           original_run([sys.executable, '-c', script], timeout, input_text=prompt)):
                    return opencode_result(prompt, timeout=timeout)
            original_run = authoring._run_provider
            stop = threading.Event()
            def press_stop_once_started():
                while not ready.exists():
                    time.sleep(.01)
                time.sleep(.2)
                stop.set()
            def planner(goal, candidates, history):
                return authoring.reach_model('plan', 'auto', expect_json=True, timeout_seconds=60)
            app = App()
            threading.Thread(target=press_stop_once_started, daemon=True).start()
            started = time.monotonic()
            with patch.object(authoring, 'PROVIDER_ORDER', ('opencode', 'gemini')), \
                    patch.object(authoring, '_try_cli', side_effect=route), \
                    patch.object(authoring, '_unavailable_until', {}), \
                    patch('tacto.helper.InheritedHelperDriver.available', return_value=False):
                result = run(app, 'app', 'read Entry', planner, cancelled=stop.is_set,
                             timeout_seconds=60)
            elapsed = time.monotonic() - started
            self.assertLess(elapsed, 8, 'the in-flight request must stop, not run to its deadline')
            self.assertEqual('cancelled', result.stop_reason)
            self.assertFalse(result.ok)
            self.assertEqual([], app.calls)
            group = json.loads(ready.read_text())['group']
            self.assertTrue(group_gone(group))
            time.sleep(1.6)
            self.assertFalse(marker.exists())
        self.assertEqual(1, len(result.provider_calls))
        call = result.provider_calls[0]
        self.assertEqual('cancelled', call['status'])
        self.assertFalse(call['cancellation_supported'])
        self.assertIn('not confirmed stopped', call['error']['message'])
        statuses = [(a['provider'], a['transport'], a['status']) for a in call['attempts']]
        self.assertEqual(('opencode', 'cli-json', 'cancelled'), statuses[-1])
        self.assertNotIn('gemini', [a['provider'] for a in call['attempts']])
        self.assertEqual(18, call['attempts'][-1]['total_input_tokens'])


if __name__ == '__main__':
    unittest.main()
