"""Fresh result checks replace blind waits; reads do not delay later reads."""
from dataclasses import replace
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from tacto.flow import Flow, Step, replay
from tacto.helper import HelperDriver, InheritedHelperDriver
from tests.test_ready_hints import Clock, Pad, SAFETY, press, run


class ExpectReadinessTests(unittest.TestCase):
    def test_calculator_guide_names_the_observed_operator_symbols(self):
        from tacto.command_help import session_guide
        guide = session_guide('com.apple.calculator')
        self.assertIn('EACH digit/operator', guide)
        self.assertIn('spaces and +, − (U+2212), ×, ÷', guide)

    def test_new_expected_result_polls_before_sending_the_next_input(self):
        for lag in (0.0, 0.6, 1.5):
            clock = Clock(); pad = Pad(clock, lag=lag, loading=True)
            flow = Flow('digits', 'pad', [
                replace(press('one'), expect='Value: 1'),
                replace(press('two'), expect='Value: 12')])
            result = run(pad, clock, flow)
            with self.subTest(lag=lag):
                self.assertTrue(result.ok, result.log)
                self.assertEqual('12', pad.display)
                self.assertGreaterEqual(pad.presses[1] - pad.presses[0], lag)
                if not lag:
                    self.assertEqual(0, pad.presses[1] - pad.presses[0])

    def test_preexisting_expect_keeps_settle_before_the_next_input(self):
        clock = Clock(); pad = Pad(clock, lag=0.6)
        flow = Flow('digits', 'pad', [
            replace(press('one'), expect='Button'), press('two')])
        result = run(pad, clock, flow)
        self.assertTrue(result.ok, result.log)
        self.assertGreaterEqual(pad.presses[1] - pad.presses[0], 1.0)

    def test_unmet_expect_times_out_without_repeating_or_next_input(self):
        clock = Clock(); pad = Pad(clock)
        result = run(pad, clock, Flow('digits', 'pad', [
            replace(press('one'), expect='not produced'), press('two')]))
        self.assertFalse(result.ok)
        self.assertEqual('expect_not_met', result.log[-1]['error'])
        self.assertEqual(1, len(pad.presses))
        self.assertEqual(4.0, clock.now - 100)

    def test_terminal_observation_failure_never_sends_the_next_input(self):
        clock = Clock(); pad = Pad(clock, error_after_press='aborted_by_user')
        result = run(pad, clock, Flow('digits', 'pad', [
            replace(press('one'), expect='Value: 1'), press('two')]))
        self.assertFalse(result.ok)
        self.assertEqual('aborted_by_user', result.log[-1]['error'])
        self.assertEqual(1, len(pad.presses))


class ReadSettleTests(unittest.TestCase):
    def test_helper_read_preserves_pending_write_time_without_renewing_it(self):
        for cls in (HelperDriver, InheritedHelperDriver):
            driver = object.__new__(cls)
            driver._last_action_at = 99.5
            driver._send = Mock(return_value={'type': 'acted'})
            with patch('tacto.helper.time.monotonic', return_value=100.0):
                self.assertEqual('acted', driver.act('o', 'pad', {'name': 'read'})['type'])
            self.assertEqual(99.5, driver._last_action_at)
            driver._send.return_value = {'type': 'observation', 'tree': 'fresh'}
            with patch('tacto.helper.time.monotonic', return_value=100.0), \
                 patch('tacto.helper.time.sleep') as sleep:
                driver.observe('pad')
            sleep.assert_called_once_with(0.5)

    def test_repeated_helper_reads_still_fetch_new_observations_without_sleep(self):
        driver = object.__new__(HelperDriver)
        driver._last_action_at = 0
        driver._send = Mock(side_effect=[{'type': 'acted'}, {'type': 'observation', 'tree': 'first'},
                                        {'type': 'acted'}, {'type': 'observation', 'tree': 'second'}])
        with patch('tacto.helper.time.monotonic', return_value=100.0), \
             patch('tacto.helper.time.sleep') as sleep:
            seen = []
            for _ in range(2):
                driver.act('o', 'pad', {'name': 'read'})
                seen.append(driver.observe('pad')['tree'])
        self.assertEqual(['first', 'second'], seen)
        sleep.assert_not_called()

    def test_in_process_read_does_not_renew_pending_write_time(self):
        try:
            from tacto.driver import Driver
        except ImportError:
            self.skipTest('macOS driver unavailable')
        driver = object.__new__(Driver)
        driver._latest = {'pad': SimpleNamespace(obs_id='o', pid=1)}
        driver._showing_control = Mock()
        driver._perform = Mock(return_value=None)
        driver._last_action_at = 99.5
        with patch('tacto.driver.time.monotonic', return_value=100.0):
            self.assertEqual('acted', driver.act('o', 'pad', {'name': 'read'})['type'])
        self.assertEqual(99.5, driver._last_action_at)
