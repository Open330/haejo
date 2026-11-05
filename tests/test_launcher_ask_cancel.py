"""Host cancellation through the launcher's real ask transport.

The harness compiles the launcher's own relayAsk/askModel/boundedModelProcess
and frame I/O source, runs the real tacto.ask_provider wrapper in an isolated
interpreter, and an owned fake provider CLI with a delayed-write descendant.
No model, network, helper, signed app or native GUI is involved.
"""
import json
import os
from pathlib import Path
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import uuid
from unittest.mock import patch

from tacto.helper import InheritedHelperDriver
from tacto.model_budget import ModelCancelled, model_cancellation
from tests.test_opencode_result import frames, stream

ROOT = Path(__file__).resolve().parents[1]


def harness_source():
    source = (ROOT / 'launcher/tacto.swift').read_text()
    io = source[source.index('func readJSONLine('):source.index('// MARK: - Environment')]
    ask = source[source.index('enum ModelProcessError:'):source.index('\n// MARK: - Relay')]
    ids = source[source.index('@Sendable func askCancelIDIsValid('):source.index('func vetted(')]
    return ('import Foundation\nimport Darwin\n'
            'let python = URL(fileURLWithPath: CommandLine.arguments[1])\n'
            'let root = URL(fileURLWithPath: CommandLine.arguments[2])\n'
            'let relayEnd = Int32(CommandLine.arguments[3])!\n'
            + io + ids + ask + r'''
if CommandLine.arguments.count > 4 {
    for id in ["0123456789abcdef", String(repeating: "a", count: 64), "ABCDEF0123456789",
               "short", String(repeating: "a", count: 65), "0123456789abcde!"] {
        print(askCancelIDIsValid(id))
    }
    print(askCancelFrameIsValid(["type": "ask_cancel", "cancel_id": "0123456789abcdef"]),
          askCancelFrameIsValid(["type": "ask_cancel", "cancel_id": "0123456789abcdef", "x": 1]),
          askCancelFrameIsValid(["type": "ask", "cancel_id": "0123456789abcdef"]))
    exit(0)
}
if let raw = ProcessInfo.processInfo.environment["HARNESS_HELPER_PID"], let pid = Int32(raw),
   let name = ProcessInfo.processInfo.environment["HARNESS_STATUS_NAME"] {
    helperStopWatch.bind(pid)
    startHelperStopObserver(Notification.Name(name))
}
// As in the launcher: the relay runs off the main thread, which services the
// main run loop (where distributed notifications arrive).
Thread {
    var fromChild = Data()
    while let msg = readJSONLine(relayEnd, &fromChild) {
        let type = msg["type"] as? String
        if type == "ask_cancel" { continue }
        if type == "ask" {
            relayAsk(msg, timeout: (msg["timeout_seconds"] as? NSNumber)?.doubleValue ?? 30, fromChild: &fromChild)
            continue
        }
        writeJSONLine(relayEnd, ["type": type == "ping" ? "pong" : "unexpected"])
    }
    _ = modelCleanupGroup.wait(timeout: .now() + 2)
    exit(0)
}.start()
while true { _ = CFRunLoopRunInMode(CFRunLoopMode.defaultMode, 0.05, false) }
''')


def fake_cli(path, ready, marker, *, hang=True):
    descendant = ('import pathlib,time;time.sleep(1.2);pathlib.Path('
                  + repr(str(marker)) + ').write_text("survived")')
    body = ('import json,os,pathlib,subprocess,sys,time\n'
            'sys.stdin.read()\n'
            'sys.stdout.write(' + repr(stream(frames()) + '\n') + ');sys.stdout.flush()\n')
    if hang:
        body += ('child=subprocess.Popen([sys.executable,"-c",' + repr(descendant) + '])\n'
                 'pathlib.Path(' + repr(str(ready)) + ').write_text(json.dumps({"group":os.getpid()}))\n'
                 'time.sleep(20)\n')
    path.write_text('#!' + sys.executable + '\n' + body)
    path.chmod(0o755)


def group_gone(group):
    try:
        os.killpg(group, 0)
    except ProcessLookupError:
        return True
    return False


def pid_gone(pid, wait=3.0):
    until = time.monotonic() + wait
    while time.monotonic() < until:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return True
        time.sleep(.05)
    return False


def cancel_after(ready, delay=0.2):
    seen = []
    def predicate():
        if not ready.exists():
            return False
        seen.append(time.monotonic())
        return time.monotonic() - seen[0] >= delay
    return predicate


@unittest.skipUnless(sys.platform == 'darwin' and shutil.which('xcrun'), 'macOS Swift required')
class LauncherAskCancelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.folder = tempfile.TemporaryDirectory()
        base = Path(cls.folder.name)
        (base / 'main.swift').write_text(harness_source())
        cls.binary = base / 'relay'
        subprocess.run(['xcrun', 'swiftc', str(base / 'main.swift'), str(ROOT / 'RuntimeStatus.swift'),
                        '-o', str(cls.binary)], check=True, capture_output=True, timeout=120)
        (base / 'poster.swift').write_text(POSTER)
        cls.poster = base / 'poster'
        subprocess.run(['xcrun', 'swiftc', str(base / 'poster.swift'), '-o', str(cls.poster)],
                       check=True, capture_output=True, timeout=120)
        # The launcher runs the wrapper with -I; give it this checkout only.
        subprocess.run([sys.executable, '-m', 'venv', '--without-pip', str(base / 'venv')],
                       check=True, capture_output=True, timeout=60)
        purelib = subprocess.run([str(base / 'venv/bin/python'), '-c',
                                  'import sysconfig;print(sysconfig.get_paths()["purelib"])'],
                                 check=True, capture_output=True, text=True).stdout.strip()
        Path(purelib, 'checkout.pth').write_text(str(ROOT) + '\n')
        cls.python = base / 'venv/bin/python'

    @classmethod
    def tearDownClass(cls):
        cls.folder.cleanup()

    def setUp(self):
        self.work = tempfile.TemporaryDirectory()
        self.addCleanup(self.work.cleanup)
        self.base = Path(self.work.name)
        (self.base / 'bin').mkdir()
        self.ready, self.marker = self.base / 'ready', self.base / 'survived'
        # A private notification name: the person's Tacto menu never sees it.
        self.status_name = 'ai.callabo.tacto.test.status.' + uuid.uuid4().hex

    def post(self, pid, *, active=True, stopped=True, uid=None):
        subprocess.run([str(self.poster), self.status_name, str(pid), str(int(active)), str(int(stopped)),
                        str(os.getuid() if uid is None else uid)], check=True, timeout=10)

    def owned_helper(self):
        helper = subprocess.Popen([sys.executable, '-c', 'import time;time.sleep(60)'])
        self.addCleanup(lambda: (helper.kill(), helper.wait()))
        return helper.pid

    def start(self, python=None, helper_pid=None):
        mine, theirs = socket.socketpair()
        env = dict(os.environ, PATH=f'{self.base / "bin"}:/usr/bin:/bin')
        if helper_pid is not None:
            env.update(HARNESS_HELPER_PID=str(helper_pid), HARNESS_STATUS_NAME=self.status_name)
        for key in ('TACTO_HELPER_FD', 'TACTO_LAUNCHER', 'TACTO_HELPER_TOKEN'):
            env.pop(key, None)
        relay = subprocess.Popen([str(self.binary), str(python or self.python), str(ROOT), str(theirs.fileno())],
                                 pass_fds=(theirs.fileno(),), env=env)
        theirs.close()
        def stop():
            mine.close()
            try:
                relay.wait(timeout=5)
            except subprocess.TimeoutExpired:
                relay.kill(); relay.wait()
        self.addCleanup(stop)
        driver = object.__new__(InheritedHelperDriver)
        driver._sock = mine
        driver._f = mine.makefile('rw', encoding='utf-8', newline='\n')
        driver._ready = True
        driver.capabilities = set()
        driver.launcher_capabilities = frozenset({'ask_cancel_v1'})
        return driver

    def test_id_and_frame_validation(self):
        out = subprocess.run([str(self.binary), '/x', '/x', '0', 'validate'],
                             capture_output=True, text=True, timeout=10).stdout.split()
        self.assertEqual(['true', 'true', 'false', 'false', 'false', 'false', 'true', 'false', 'false'], out)

    def test_cancel_stops_wrapper_cli_group_and_keeps_usage_and_framing(self):
        fake_cli(self.base / 'bin/opencode', self.ready, self.marker)
        driver = self.start()
        started = time.monotonic()
        with model_cancellation(cancel_after(self.ready)):
            result = driver.ask_launcher_result('plan', provider='opencode', timeout_seconds=30)
        elapsed = time.monotonic() - started
        self.assertTrue(self.ready.exists(), 'the provider CLI must have started')
        self.assertLess(elapsed, 6, 'cancellation must not wait for the 30 s deadline')
        self.assertEqual('cancelled', result.status)
        self.assertEqual('launcher', result.transport)
        self.assertIsNone(result.text)
        self.assertEqual('ModelCancelled', result.error.code)
        self.assertFalse(result.cancellation_supported)
        # As for timeouts, partial usage lives on the attempt, not the
        # logical (unaccepted) result.
        last = result.attempts[-1]
        self.assertEqual(('opencode', 'cli-json', 'cancelled'), (last.provider, last.transport, last.status))
        self.assertEqual(18, last.total_input_tokens, 'partial observed usage crossed the launcher')
        self.assertTrue(group_gone(json.loads(self.ready.read_text())['group']))
        time.sleep(1.6)
        self.assertFalse(self.marker.exists(), 'descendant outlived host cancellation')
        # Exactly one reply per request: the channel is neither poisoned nor
        # desynchronized, and a stale cancel for a finished id gets no reply.
        driver._sock.sendall((json.dumps({'type': 'ask_cancel', 'cancel_id': uuid.uuid4().hex}) + '\n').encode())
        self.assertEqual('pong', driver._send({'type': 'ping'})['type'])

    def test_text_api_raises_cancelled_and_no_fallback_starts(self):
        fake_cli(self.base / 'bin/opencode', self.ready, self.marker)
        driver = self.start()
        with model_cancellation(cancel_after(self.ready)), self.assertRaises(ModelCancelled):
            driver.ask_launcher('plan', provider='opencode', timeout_seconds=30)
        self.assertEqual('pong', driver._send({'type': 'ping'})['type'])

    def test_uncooperative_wrapper_is_stopped_after_bounded_grace(self):
        stubborn = self.base / 'stubborn'
        pid_file = self.base / 'pid'
        stubborn.write_text('#!' + sys.executable + '\nimport os,signal,time,pathlib\n'
                            'signal.signal(signal.SIGUSR1,signal.SIG_IGN)\n'
                            'pathlib.Path(' + repr(str(pid_file)) + ').write_text(str(os.getpid()))\n'
                            'time.sleep(30)\n')
        stubborn.chmod(0o755)
        driver = self.start(python=stubborn)
        started = time.monotonic()
        with model_cancellation(cancel_after(pid_file, 0.1)):
            result = driver.ask_launcher_result('plan', provider='opencode', timeout_seconds=30)
        elapsed = time.monotonic() - started
        self.assertEqual('cancelled', result.status)
        self.assertIsNone(result.text)
        self.assertLess(elapsed, 6)
        self.assertGreater(elapsed, 1.5, 'the cooperative grace precedes forced cleanup')
        self.assertTrue(pid_gone(int(pid_file.read_text())))
        self.assertEqual('pong', driver._send({'type': 'ping'})['type'])

    def test_uncancelled_request_is_unchanged(self):
        fake_cli(self.base / 'bin/opencode', self.ready, self.marker, hang=False)
        driver = self.start()
        with model_cancellation(lambda: False):
            result = driver.ask_launcher_result('plan', provider='opencode', timeout_seconds=30)
        self.assertEqual('ok', result.status)
        self.assertEqual('{"ok":true}', result.text)
        self.assertEqual(18, result.total_input_tokens)

    def test_general_run_cancel_reaches_launcher_routed_request(self):
        from tacto import authoring
        from tacto.general import run
        from tests.test_provider_host_cancellation import App
        fake_cli(self.base / 'bin/opencode', self.ready, self.marker)
        driver = self.start()
        stop = threading.Event()
        def press_stop():
            while not self.ready.exists():
                time.sleep(.01)
            time.sleep(.2)
            stop.set()
        threading.Thread(target=press_stop, daemon=True).start()
        def planner(goal, candidates, history):
            return authoring.reach_model('plan', 'opencode', expect_json=True, timeout_seconds=30)
        app = App()
        started = time.monotonic()
        with patch.object(InheritedHelperDriver, '_shared', driver), \
                patch.object(InheritedHelperDriver, 'available', classmethod(lambda cls: True)):
            result = run(app, 'app', 'read Entry', planner, cancelled=stop.is_set, timeout_seconds=60)
        self.assertLess(time.monotonic() - started, 8)
        self.assertEqual('cancelled', result.stop_reason)
        self.assertEqual([], app.calls)
        self.assertEqual(1, len(result.provider_calls))
        call = result.provider_calls[0]
        self.assertEqual(('cancelled', 'launcher'), (call['status'], call['transport']))
        self.assertEqual('cancelled', call['attempts'][-1]['status'])
        self.assertEqual(18, call['attempts'][-1]['total_input_tokens'])
        self.assertFalse(call['cancellation_supported'])
        time.sleep(1.6)
        self.assertFalse(self.marker.exists())


    def run_with_status(self, *, post_pid, active=True, stopped=True, uid=None, scoped=True):
        fake_cli(self.base / 'bin/opencode', self.ready, self.marker)
        helper = self.owned_helper()
        driver = self.start(helper_pid=helper)
        def stop_once_started():
            while not self.ready.exists():
                time.sleep(.01)
            time.sleep(.2)
            self.post(helper if post_pid == 'helper' else post_pid, active=active, stopped=stopped, uid=uid)
        threading.Thread(target=stop_once_started, daemon=True).start()
        started = time.monotonic()
        # The client is not cancelling: only the helper's published stop can.
        with model_cancellation((lambda: False) if scoped else None):
            try:
                result = driver.ask_launcher_result('plan', provider='opencode', timeout_seconds=4)
            except TimeoutError:
                result = None   # ran to its own deadline: not cancelled
        return result, time.monotonic() - started, driver

    def test_helper_stop_status_cancels_in_flight_request(self):
        result, elapsed, driver = self.run_with_status(post_pid='helper')
        self.assertEqual('cancelled', result.status)
        self.assertLess(elapsed, 3.5, 'the published stop, not the 4 s deadline, ended it')
        self.assertEqual(18, result.attempts[-1].total_input_tokens)
        self.assertTrue(group_gone(json.loads(self.ready.read_text())['group']))
        time.sleep(1.6)
        self.assertFalse(self.marker.exists())
        self.assertEqual('pong', driver._send({'type': 'ping'})['type'])

    def test_helper_stop_needs_no_client_cancellation_scope(self):
        result, elapsed, driver = self.run_with_status(post_pid='helper', scoped=False)
        self.assertEqual('cancelled', result.status)
        self.assertLess(elapsed, 3.5)
        self.assertEqual('pong', driver._send({'type': 'ping'})['type'])

    def test_status_from_other_process_or_not_stopped_is_ignored(self):
        for case in ({'post_pid': os.getpid()}, {'post_pid': 'helper', 'stopped': False},
                     {'post_pid': 'helper', 'active': False}, {'post_pid': 'helper', 'uid': os.getuid() + 1}):
            with self.subTest(**case):
                self.setUp()
                result, elapsed, _ = self.run_with_status(**case)
                # Not cancelled: the request ran to its own 4 s deadline.
                self.assertIsNone(result)
                self.assertGreaterEqual(elapsed, 3.5)


POSTER = r'''
import Foundation
let a = CommandLine.arguments
DistributedNotificationCenter.default().postNotificationName(Notification.Name(a[1]), object: nil,
    userInfo: ["schema": 1, "uid": Int(a[5])!, "pid": Int(a[2])!, "id": UUID().uuidString,
               "target": "Test", "active": a[3] == "1", "stopped": a[4] == "1"],
    deliverImmediately: true)
// Let the post leave this process before it exits.
RunLoop.current.run(until: Date().addingTimeInterval(0.3))
'''


class CooperativeStopTests(unittest.TestCase):
    def test_first_signal_cancels_then_restores_disposition(self):
        from tacto.cli import cooperative_stop
        before = signal.getsignal(signal.SIGTERM)
        with cooperative_stop() as stop:
            self.assertFalse(stop.is_set())
            os.kill(os.getpid(), signal.SIGTERM)
            deadline = time.monotonic() + 2
            while not stop.is_set() and time.monotonic() < deadline:
                time.sleep(.01)
            self.assertTrue(stop.is_set())
            # A second signal behaves as before the run.
            self.assertIs(before, signal.getsignal(signal.SIGTERM))
        self.assertIs(before, signal.getsignal(signal.SIGTERM))


if __name__ == '__main__':
    unittest.main()


class StopWiringSourceTests(unittest.TestCase):
    """The parts the harness cannot run without real Esc input or a helper."""

    def test_esc_publishes_stopped_status_like_the_indicator_stop(self):
        source = (ROOT / 'helper/TactoHelper.swift').read_text()
        body = source[source.index('func watchForAbort()'):]
        body = body[:body.index('\n}\n')]
        note = body.index('abortState.note(at: ev.timestamp)')
        publish = body.index('if abortState.isStopped && RuntimePublisher.shared.active { RuntimePublisher.shared.publish() }')
        self.assertLess(note, publish)
        menu = source[source.index('@objc func stopNow(_ sender: Any?)'):]
        self.assertIn('RuntimePublisher.shared.publish()', menu[:menu.index('\n    }\n')])

    def test_launcher_binds_authenticated_helper_and_services_main_run_loop(self):
        source = (ROOT / 'launcher/tacto.swift').read_text()
        connect = source[source.index('            helperFD = fd\n'):]
        connect = connect[:connect.index('        }\n')]
        self.assertIn('if let token = peerToken(fd) {', connect)
        self.assertIn('helperStopWatch.bind(pid_t(token.val.5))', connect)
        self.assertIn('startHelperStopObserver()', connect)
        self.assertIn('let status = waitForChildServicingMainRunLoop(childPID)', source)
        self.assertNotIn('waitpid(childPID, &status, 0)', source)
        self.assertIn('cancelled: { childCancelled() || helperStopWatch.isStopped }', source)


class WatcherLifecycleTests(unittest.TestCase):
    """The cancel watcher never outlives or stalls its request (no Swift)."""

    def driver(self, sock):
        driver = object.__new__(InheritedHelperDriver)
        driver._sock = sock
        driver._f = sock.makefile('rw', encoding='utf-8', newline='\n')
        driver._ready = True
        driver.capabilities = set()
        driver.launcher_capabilities = frozenset({'ask_cancel_v1'})
        return driver

    def watchers(self):
        return [t for t in threading.enumerate() if t.name == 'tacto-ask-cancel' and t.is_alive()]

    def test_send_failure_before_frame_is_written_returns_promptly(self):
        mine, theirs = socket.socketpair()
        theirs.close()                       # the ask frame cannot be written
        driver = self.driver(mine)
        started = time.monotonic()
        with model_cancellation(lambda: False), self.assertRaises(Exception) as caught:
            driver._ask_launcher_response('plan', provider='opencode', timeout_seconds=300)
        self.assertNotIsInstance(caught.exception, ModelCancelled)
        self.assertLess(time.monotonic() - started, 2, 'must not wait for the 300 s request timeout')
        self.assertEqual([], self.watchers())

    def test_unwritable_cancel_frame_closes_channel_without_blocking(self):
        mine, theirs = socket.socketpair()
        self.addCleanup(theirs.close)
        class WouldBlock:
            """The real socket, except a cancel frame cannot be sent now."""
            def __init__(self, inner): self.inner = inner
            def send(self, *args): raise BlockingIOError()
            def __getattr__(self, name): return getattr(self.inner, name)
        driver = self.driver(mine)
        driver._sock = WouldBlock(mine)
        started = time.monotonic()
        # The peer reads the ask and never answers; cancellation is at once.
        with model_cancellation(lambda: True), self.assertRaises(ModelCancelled):
            driver._ask_launcher_response('plan', provider='opencode', timeout_seconds=300)
        self.assertLess(time.monotonic() - started, 2)
        self.assertTrue(driver._poisoned, 'a cancel that could not be framed closes the channel')
        self.assertEqual([], self.watchers())
