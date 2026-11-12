"""`session A --then B`: B's guide and observation follow A's checked result in one command."""
import json
import os
import unittest
from unittest.mock import Mock, patch

from haejo.flow_session import run_session


def driver(target_tree='AXWindow'):
    d = Mock()
    d.capabilities = ()
    d._window_scope = None
    d.observe.return_value = {'type': 'observation', 'tree': target_tree}
    return d


class SessionThenTests(unittest.TestCase):
    def run_chain(self, args, flows, results, prepare=None):
        read, write = os.pipe()
        messages, ran = [], []
        pending = list(flows)

        def emit(line):
            messages.append(line)
            # The author answers each READY with that app's Flow, as an agent would.
            if line.startswith('HAEJO_SESSION_READY') and pending:
                os.write(write, (json.dumps(pending.pop(0)) + '\n').encode())

        outcomes = list(results)

        def run_flow(flow, flags, **kwargs):
            ran.append(flow.target)
            return outcomes.pop(0)

        drivers = []

        def make(flags):
            drivers.append(driver())
            if prepare:
                prepare(drivers[-1])
            return drivers[-1]

        with os.fdopen(read) as stream:
            code = run_session(args, make_driver=make, run_flow=run_flow, stdin=stream, emit=emit)
        os.close(write)
        return code, messages, ran, drivers

    def test_second_app_follows_the_first_result_in_the_same_command(self):
        step = {'steps': [{'action': 'read'}]}
        code, messages, ran, drivers = self.run_chain(
            ['com.example.a', '--helper', '--steps', '--then', 'com.example.b'], [step, step], [0, 0])
        self.assertEqual(0, code)
        self.assertEqual(['com.example.a', 'com.example.b'], ran)
        ready = [m for m in messages if m.startswith('HAEJO_SESSION_READY')]
        self.assertEqual(['target=com.example.a', 'target=com.example.b'], [m.split()[-1] for m in ready])
        nxt = messages.index('HAEJO_SESSION_NEXT com.example.b (2/2)')
        self.assertLess(messages.index(ready[0]), nxt)
        self.assertLess(nxt, messages.index(ready[1]))
        # One helper channel per process: every app uses it; it closes once at the end.
        self.assertEqual(1, len(drivers))
        drivers[0].close.assert_called_once()
        self.assertEqual(['com.example.a', 'com.example.b'],
                         [c.args[0] for c in drivers[0].observe.call_args_list])

    def test_failure_stops_before_later_apps(self):
        step = {'steps': [{'action': 'read'}]}
        code, messages, ran, drivers = self.run_chain(
            ['com.example.a', '--helper', '--steps', '--then', 'com.example.b'], [step, step], [1])
        self.assertEqual(1, code)
        self.assertEqual(['com.example.a'], ran)
        self.assertEqual(1, len(drivers))
        drivers[0].close.assert_called_once()
        self.assertIn('HAEJO_SESSION_STOPPED later apps not started: com.example.b', messages)
        # The rest of the chain is one command away, starting at the app that stopped.
        self.assertEqual('HAEJO_SESSION_RESUME after handling the failure above, continue from this app: '
                         'haejo session com.example.a --helper --steps --then com.example.b', messages[-1])

    def test_resume_starts_at_the_middle_app_and_keeps_its_options(self):
        step = {'steps': [{'action': 'read'}]}
        _, messages, ran, _ = self.run_chain(
            ['com.example.a', '--helper', '--steps', '--then', 'com.example.b',
             '--then', 'com.example.c', '--document', '/tmp/x y.txt'], [step, step], [0, 1])
        self.assertEqual(['com.example.a', 'com.example.b'], ran)
        self.assertEqual("HAEJO_SESSION_RESUME after handling the failure above, continue from this app: "
                         "haejo session com.example.b --helper --steps --then com.example.c --document '/tmp/x y.txt'",
                         messages[-1])

    def test_flags_are_inherited_and_misuse_is_refused(self):
        step = {'steps': [{'action': 'read'}]}
        code, _, ran, _ = self.run_chain(
            ['com.example.a', '--helper', '--steps', '--then', 'com.example.b', '--then', 'com.example.c'],
            [step, step, step], [0, 0, 0])
        self.assertEqual((0, ['com.example.a', 'com.example.b', 'com.example.c']), (code, ran))
        for bad in (['com.example.a', '--helper', '--then'], ['com.example.a', '--helper', '--then', '--steps'],
                    ['com.example.a', '--helper'] + ['--then', 'com.example.b'] * 4):
            code, messages, ran, drivers = self.run_chain(bad, [], [])
            self.assertEqual(2, code, bad)
            self.assertEqual([], drivers)
            self.assertTrue(messages[-1].startswith('session_then:'), messages)

    def test_window_pin_ends_with_its_app(self):
        step = {'steps': [{'action': 'read'}]}
        released = []

        def make_pinned(d):
            d._window_scope = ('com.example.a', 7)
            def release():
                released.append(True); d._window_scope = None
                return {'type': 'targets_released', 'observation_invalidated': True}
            d.release_targets.side_effect = release
        code, _, ran, drivers = self.run_chain(
            ['com.example.a', '--helper', '--steps', '--then', 'com.example.b'], [step, step], [0, 0],
            prepare=make_pinned)
        self.assertEqual((0, ['com.example.a', 'com.example.b'], [True]), (code, ran, released))

        def make_stuck(d):
            d._window_scope = ('com.example.a', 7)
        code, messages, ran, _ = self.run_chain(
            ['com.example.a', '--helper', '--steps', '--then', 'com.example.b'], [step, step], [0, 0],
            prepare=make_stuck)
        self.assertEqual((1, ['com.example.a']), (code, ran))
        self.assertIn('HAEJO_SESSION_STOPPED later apps not started: com.example.b', messages)
        self.assertTrue(messages[-1].startswith('HAEJO_SESSION_RESUME com.example.a already finished its task'), messages)

    def test_save_failure_after_the_task_resumes_with_the_next_app(self):
        step = {'steps': [{'action': 'read'}]}
        with patch('haejo.storage.write_private', side_effect=OSError('disk')):
            code, messages, ran, _ = self.run_chain(
                ['com.example.a', '--helper', '--steps', '--save', '/tmp/never-written.json', '--then', 'com.example.b'],
                [step, step], [0, 0])
        self.assertEqual((1, ['com.example.a']), (code, ran))
        self.assertEqual('HAEJO_SESSION_RESUME com.example.a already finished its task; continue with the next app: '
                         'haejo session com.example.b --helper --steps', messages[-1])

    def test_windows_chain_reads_every_flow_through_one_reader(self):
        import haejo.flow_session as fs
        made = []
        real = fs._windows_reader

        def counting(fd, **kw):
            made.append(fd); return real(fd, **kw)
        step = {'steps': [{'action': 'read'}]}
        with patch.object(fs.sys, 'platform', 'win32'), patch.object(fs, '_windows_reader', counting), \
                patch.object(fs, 'flow_input_mode', lambda fd: __import__('contextlib').nullcontext()):
            code, _, ran, _ = self.run_chain(['com.example.a', '--steps', '--then', 'com.example.b'],
                                             [step, step], [0, 0])
        self.assertEqual((0, ['com.example.a', 'com.example.b']), (code, ran))
        self.assertEqual(1, len(made))
        self.assertEqual({}, fs._CHAIN_READER)


if __name__ == '__main__':
    unittest.main()
