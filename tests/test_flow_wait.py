"""Long read-only waits, paused clocks and session/batch input lifetimes."""
from contextlib import contextmanager, nullcontext, redirect_stdout
import io
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from haejo.flow import Flow, Postcondition, Selector, Step, replay
from haejo import flow_wait


TARGET = 'com.example.wait'


def document(**step):
    return {'schema': 2, 'name': 'chapter-completion', 'target': TARGET,
            'steps': [{'action': 'wait_until', 'until': {'contains': 'finished'},
                       'timeout_s': 1200, **step}]}


def observation(text='loading', **extra):
    return {'type': 'observation', 'obs_id': 'fresh',
            'tree': '0 StaticText, Value: ' + text, **extra}


class Clock:
    def __init__(self):
        self.now = 0.0
        self.sleeps = []

    def monotonic(self):
        return self.now

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.now += seconds


class Driver:
    def __init__(self, replies):
        self.replies = iter(replies)
        self.last = observation()
        self.observations = 0
        self.act = Mock(side_effect=AssertionError('wait dispatched input'))
        self.close = Mock()

    def observe(self, target, mode='tree_full', **kwargs):
        self.observations += 1
        self.last = next(self.replies, self.last)
        return self.last


@contextmanager
def clocked(clock=None, pause=None):
    clock = clock or Clock()
    with patch.object(flow_wait.time, 'monotonic', clock.monotonic), \
         patch.object(flow_wait.time, 'sleep', clock.sleep), \
         patch.object(flow_wait, 'platform_pause_reason', side_effect=pause or (lambda target: None)):
        yield clock


class WaitSchemaTests(unittest.TestCase):
    def test_compact_full_saved_and_bound_roundtrip(self):
        doc = document(until={'field': {'identifier': 'status'}, 'equals': '{{answer}}', 'attribute': 'Value'},
                       timeout_s=7200, poll_s=15)
        doc['params'] = {'answer': 'finished'}
        flow = Flow.from_json(json.dumps(doc), strict_checks=True)
        for compact in (False, True):
            loaded = Flow.from_json(flow.to_json(compact=compact)).bind()
            self.assertEqual('finished', loaded.steps[0].until.equals)
            self.assertEqual((7200, 15), (loaded.steps[0].timeout_s, loaded.steps[0].poll_s))
            with clocked():
                result = replay(Driver([{'type': 'observation', 'tree': '0 StaticText, Identifier: status, Value: finished'}]), loaded)
            self.assertTrue(result.ok, result.log)

    def test_bad_waits_refuse_before_observing(self):
        bad = [{'timeout_s': value} for value in (None, True, 0, -1, 7201, 10**400, float('nan'), float('inf'), '30')]
        bad += [{'poll_s': value} for value in (True, 0, .5, 61, 10**400, float('inf'), '10')]
        bad += [{'until': value} for value in (None, {}, [], {'field': {'role': 'Button'}},
                 {'equals': 3}, {'exist': True}, {'exists': False, 'field': {'role': 'Button'}},
                 {'exists': True}, {'all_of': [{}]})]
        bad += [{'params': {'timeout_s': 30}}, {'selector': {'role': 'Button'}},
                {'safety': {'effects': ['write_ephemeral']}}, {'postcondition': {'contains': 'x'}}]
        for override in bad:
            with self.subTest(override=override), self.assertRaises(ValueError):
                Flow.from_json(json.dumps(document(**override)))
        driver = Driver([])
        result = replay(driver, Flow('bad', TARGET, [Step('wait_until', timeout_s=True)]))
        self.assertFalse(result.ok)
        self.assertEqual('invalid_wait', result.log[-1]['error'])
        self.assertEqual(0, driver.observations)

    def test_exists_and_composed_checks(self):
        flow = Flow.from_json(json.dumps(document(until={'all_of': [
            {'field': {'role': 'StaticText', 'value': 'finished'}, 'exists': True},
            {'absent_role': 'ProgressIndicator'}]})), strict_checks=True)
        with clocked():
            result = replay(Driver([observation('finished')]), flow)
        self.assertTrue(result.ok, result.log)
        self.assertFalse(Postcondition(field=Selector(role='Button'), exists=True).check('0 StaticText'))
        self.assertFalse(Postcondition(field=Selector(role='Button'), exists=True).check('0 Button\n1 Button'))

    def test_shared_check_defaults_and_write_defaults_do_not_change_read_wait(self):
        doc = document(until={'equals': 'finished'})
        doc.update(check_defaults={'field': {'identifier': 'status'}, 'attribute': 'Value'},
                   safety_defaults={'effects': ['write_persistent']})
        flow = Flow.from_json(json.dumps(doc))
        self.assertIsNone(flow.steps[0].safety)
        with clocked():
            self.assertTrue(replay(Driver([observation('finished, Identifier: status')]), flow).ok)


class WaitReplayTests(unittest.TestCase):
    def test_platform_lock_and_all_displays_asleep_are_cheap_checks(self):
        session = SimpleNamespace(lock_state=lambda: {'locked': False})
        quartz = SimpleNamespace(CGGetOnlineDisplayList=lambda *args: (0, (1, 2), 2),
                                 CGDisplayIsAsleep=lambda display: display == 1)
        with patch.object(flow_wait.sys, 'platform', 'darwin'), \
             patch.dict('sys.modules', {'haejo.session': session, 'Quartz': quartz}):
            self.assertIsNone(flow_wait.platform_pause_reason(TARGET))
            quartz.CGDisplayIsAsleep = lambda display: True
            self.assertEqual('display_asleep', flow_wait.platform_pause_reason(TARGET))
            session.lock_state = lambda: {'locked': True}
            self.assertEqual('screen_locked', flow_wait.platform_pause_reason(TARGET))
            self.assertIsNone(flow_wait.platform_pause_reason('page'))
            self.assertIsNone(flow_wait.platform_pause_reason('https://example.test'))

    def test_met_after_polls_uses_no_actions_and_no_model(self):
        driver = Driver([observation(), observation(), observation('finished')])
        with clocked() as clock:
            result = replay(driver, Flow.from_json(json.dumps(document())))
        self.assertTrue(result.ok, result.log)
        self.assertEqual([10, 10], clock.sleeps)
        self.assertEqual((3, 20, 0, 'none'), tuple(result.log[0][k] for k in
                         ('polls', 'active_seconds', 'paused_seconds', 'effect')))
        driver.act.assert_not_called()

    def test_timeout_and_backend_failure_are_structured(self):
        with clocked() as clock:
            result = replay(Driver([observation()]), Flow.from_json(json.dumps(document(timeout_s=23))))
        self.assertFalse(result.ok)
        self.assertEqual([10, 10, 3], clock.sleeps)
        self.assertEqual(('wait_timeout', 'none', 23), tuple(result.log[-1][k] for k in
                         ('error', 'effect', 'active_seconds')))
        with clocked():
            result = replay(Driver([{'type': 'error', 'error': 'permission_denied'}]),
                            Flow.from_json(json.dumps(document())))
        self.assertEqual('wait_observation_failed', result.log[-1]['error'])

    def test_backend_lock_pause_excluded_from_deadline(self):
        driver = Driver([observation(), {'type': 'error', 'reason': 'screen_locked', 'error': 'no_window_content'},
                         {'type': 'error', 'lock': {'locked': True}, 'error': 'no_window_content'},
                         observation(), observation('finished')])
        with clocked():
            result = replay(driver, Flow.from_json(json.dumps(document(timeout_s=25))))
        self.assertTrue(result.ok, result.log)
        wait = result.log[0]
        self.assertEqual((20, 20, 40), tuple(wait[k] for k in ('active_seconds', 'paused_seconds', 'elapsed_seconds')))
        self.assertEqual([{'reason': 'screen_locked', 'seconds': 20}], wait['pauses'])

    def test_platform_pause_avoids_ax_reads_then_resumes(self):
        for reason in ('screen_locked', 'display_asleep'):
            driver = Driver([observation('finished')])
            reasons = iter([reason] * 70 + [None])
            with self.subTest(reason=reason), clocked(pause=lambda target: next(reasons)):
                result = replay(driver, Flow.from_json(json.dumps(document(timeout_s=1))))
            self.assertTrue(result.ok, result.log)
            self.assertEqual((1, 700, 0), (driver.observations, result.log[0]['paused_seconds'], result.log[0]['active_seconds']))

    def test_off_space_pause_and_fresh_condition_check(self):
        driver = Driver([{'type': 'error', 'error': 'no_window_content', 'reason': 'window_offscreen'},
                         observation(), observation('finished')])
        with clocked():
            result = replay(driver, Flow.from_json(json.dumps(document(timeout_s=12))))
        self.assertTrue(result.ok, result.log)
        self.assertEqual([{'reason': 'window_offscreen', 'seconds': 10}], result.log[0]['pauses'])

    def test_a_pause_that_never_ends_stops_after_the_pause_cap(self):
        driver = Driver([{'type': 'error', 'error': 'no_window_content', 'reason': 'window_offscreen'}])
        with clocked(), patch.object(flow_wait, 'MAX_PAUSED_S', 100):
            result = replay(driver, Flow.from_json(json.dumps(document(timeout_s=12))))
        self.assertFalse(result.ok)
        self.assertEqual(('wait_paused_too_long', 'window_offscreen'), (result.log[-1]['error'], result.log[-1]['reason']))
        self.assertGreaterEqual(result.log[-1]['paused_seconds'], 100)

    def test_pause_does_not_turn_unreadable_or_missing_state_into_success(self):
        driver = Driver([{'type': 'error', 'reason': 'screen_locked', 'error': 'no_window_content'},
                         {'type': 'error', 'error': 'target_not_found'}])
        with clocked():
            result = replay(driver, Flow.from_json(json.dumps(document(until={'absent': 'loading'}))))
        self.assertFalse(result.ok)
        self.assertEqual('wait_observation_failed', result.log[-1]['error'])

    def test_interrupt_propagates(self):
        driver = Driver([])
        driver.observe = Mock(side_effect=KeyboardInterrupt)
        with clocked(), self.assertRaises(KeyboardInterrupt):
            replay(driver, Flow.from_json(json.dumps(document())))

    def test_successive_waits_reobserve_instead_of_reusing_the_previous_match(self):
        doc = document()
        doc['steps'].append({'action': 'wait_until', 'until': {'contains': 'next'}, 'timeout_s': 20})
        driver = Driver([observation('finished'), observation('finished'), observation('next')])
        with clocked():
            result = replay(driver, Flow.from_json(json.dumps(doc)))
        self.assertTrue(result.ok, result.log)
        self.assertEqual(3, driver.observations)
        self.assertEqual([1, 2], [row['polls'] for row in result.log if row.get('action') == 'wait_until'])


class WaitEntryPointTests(unittest.TestCase):
    def test_session_wait_longer_than_stdin_idle_and_saves_template(self):
        from haejo.cli import _run_flow
        from haejo.flow_session import run_session
        driver = Driver([observation()] * 4 + [observation('finished')])
        incoming, outgoing = os.pipe()
        os.write(outgoing, (json.dumps(document()) + '\n').encode())
        os.close(outgoing)
        messages = []
        with tempfile.TemporaryDirectory() as folder, os.fdopen(incoming) as stream, clocked() as clock, \
             redirect_stdout(io.StringIO()), patch('haejo.cli._indicator_for', return_value=nullcontext()):
            saved = Path(folder)/'wait.json'
            code = run_session([TARGET, '--helper', '--idle-timeout', '1', '--save', str(saved)],
                               make_driver=lambda argv: driver, run_flow=_run_flow, stdin=stream, emit=messages.append)
            self.assertEqual(0, code, messages)
            self.assertGreater(clock.now, 1)
            self.assertEqual('wait_until', Flow.from_json(saved.read_text()).steps[0].action)
        driver.act.assert_not_called()
        driver.close.assert_called_once()

    def test_saved_run_and_batch_long_jobs_reset_stdin_idle(self):
        from haejo.cli import _run_flow
        from haejo.flow_batch import run_batch
        driver = Driver([observation(), observation(), observation('finished')])
        with clocked(), redirect_stdout(io.StringIO()), patch('haejo.cli._indicator_for', return_value=nullcontext()):
            self.assertEqual(0, _run_flow(Flow.from_json(json.dumps(document())), [], _driver=driver))
        driver = Driver([observation(), observation('finished'), observation(), observation('finished')])
        messages = []
        incoming, outgoing = os.pipe()
        os.write(outgoing, b'{"params":{}}\n{"params":{}}\n')
        os.close(outgoing)
        with tempfile.TemporaryDirectory() as folder, os.fdopen(incoming) as stream, clocked() as clock, \
             redirect_stdout(io.StringIO()), patch('haejo.cli._indicator_for', return_value=nullcontext()):
            saved = Path(folder)/'wait.json'
            saved.write_text(json.dumps(document()))
            code = run_batch([str(saved), '--helper', '--idle-timeout', '1', '--max-jobs', '2'],
                             make_driver=lambda argv: driver, run_flow=_run_flow, stdin=stream, emit=messages.append)
        self.assertEqual(0, code, messages)
        self.assertEqual(20, clock.now)
        self.assertEqual(2, sum(message.startswith('HAEJO_BATCH_RESULT ') for message in messages))
        driver.act.assert_not_called()


if __name__ == '__main__':
    unittest.main()
