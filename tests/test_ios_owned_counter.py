"""Owned qualification barrier/receipts; transport fixture, not device evidence."""
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock

from tacto.ios_ax_probe import IOSAXProbeError

spec = importlib.util.spec_from_file_location('qualify_owned_counter',
    Path(__file__).resolve().parents[1]/'spike/ios-ax-bridge/qualify_owned_counter.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

CONFIG = {'binary':'/tmp/owned-counter-spike', 'device_id':'00000000-0000000000000000',
          'expected_pid':123, 'fixture_url':'http://127.0.0.1:12345/'+'a'*32+'/',
          'fixture_heading':'Tacto test aaaaaaaa'}


class FakeProbe:
    def __init__(self):
        self.closed = False; self.inputs = 0; self.mode = 'success'
    def capabilities(self):
        return ['deviceInspectorMoveWithOptions:', 'deviceElement:valueForAttribute:']
    def service_readiness(self):
        return {'hid_transport_ping':True}
    def _exchange(self, request):
        command = request['command']
        if command == 'prepare_owned_counter':
            if self.mode == 'wrong_target':
                raise IOSAXProbeError('ios_ax_probe_failed', stage='owned_counter_preflight')
            return {'counter':0, 'target_pid_verified':True, 'button_measured':True,
                    'fixture_heading_seen':True, 'current_orientation':'portrait'}
        if command == 'tap_owned_counter_once':
            if self.mode == 'pre_tap_refused':
                raise IOSAXProbeError('ios_ax_probe_failed', stage='owned_counter_tap_preflight', touch_attempted=False)
            self.inputs += 1
            if self.mode == 'lost_reply':
                raise IOSAXProbeError('ios_ax_probe_disconnected')
            return {'sent':True,'transport_ping':True,'gesture_count':1,'contact_reports':2,'release_reports':1}
        if command == 'read_owned_counter':
            return {'counter':1,'ax_transition_verified':True}
        raise AssertionError(command)
    def state(self, _):
        return {'count':self.inputs, 'pointer_types':['touch']*self.inputs}
    def close(self):
        self.closed = True


class OwnedCounterTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.probe = FakeProbe()
        self.factory = Mock(return_value=self.probe)
    def run_qualification(self, **kwargs):
        return module.qualify(CONFIG, self.temp.name, probe_factory=self.factory,
                              read_state=self.probe.state, **kwargs)
    def test_one_gesture_requires_both_ax_and_independent_receiving_count(self):
        result = self.run_qualification()
        self.assertTrue(result['ok'], result)
        self.assertEqual(1, self.probe.inputs)
        self.assertTrue(result['receipts'][0]['screen_change_verified'])
        self.assertFalse(result['promotion_allowed'])
        self.assertTrue(self.probe.closed)
        self.assertTrue((Path(self.temp.name)/'touch-requested.json').exists())
    def test_prepare_only_never_requests_input_or_creates_dispatch_marker(self):
        result = self.run_qualification(prepare_only=True)
        self.assertTrue(result['ok'], result)
        self.assertFalse(result['qualification_complete'])
        self.assertEqual(0, self.probe.inputs)
        self.assertFalse((Path(self.temp.name)/'touch-requested.json').exists())
    def test_reply_loss_never_starts_a_second_worker_with_the_same_journal(self):
        self.probe.mode = 'lost_reply'
        first = self.run_qualification()
        self.assertFalse(first['ok'])
        self.assertIsNone(first['receipts'][0]['sent'])
        self.assertEqual('unknown', first['effect'])
        self.assertEqual(1, self.probe.inputs)
        factory = Mock(side_effect=AssertionError('must not create another worker'))
        second = module.qualify(CONFIG, self.temp.name, probe_factory=factory)
        self.assertEqual('fixture_input_unresolved_or_already_attempted', second['error'])
        factory.assert_not_called()
    def test_simulated_reply_loss_retains_unknown_even_if_input_happened(self):
        result = self.run_qualification(simulate_reply_loss=True)
        self.assertFalse(result['ok'])
        self.assertEqual(1, self.probe.inputs)
        self.assertIsNone(result['receipts'][0]['sent'])
        self.assertTrue(self.probe.closed)
    def test_failed_target_preflight_does_not_dispatch(self):
        self.probe.mode = 'wrong_target'
        result = self.run_qualification()
        self.assertFalse(result['ok'])
        self.assertFalse(result['physical_input_requested'])
        self.assertEqual(0, self.probe.inputs)
    def test_native_pre_tap_refusal_keeps_marker_but_reports_not_started(self):
        self.probe.mode = 'pre_tap_refused'
        result = self.run_qualification()
        self.assertFalse(result['ok'])
        self.assertEqual('not_started', result['effect'])
        self.assertEqual(0, self.probe.inputs)
        self.assertIs(result['receipts'][0]['sent'], False)
        self.assertTrue((Path(self.temp.name)/'touch-requested.json').exists())
    def test_existing_receiving_count_refuses_before_starting_worker(self):
        self.probe.inputs = 1
        result = self.run_qualification()
        self.assertFalse(result['ok'])
        self.factory.assert_not_called()
    def test_unrelated_receiving_change_never_verifies_the_tap(self):
        def state(_):
            return {'count':0 if self.probe.inputs == 0 else 2, 'pointer_types':['touch','touch']}
        result = module.qualify(CONFIG, self.temp.name, probe_factory=self.factory, read_state=state)
        self.assertFalse(result['ok'])
        self.assertFalse(result['receipts'][0]['screen_change_verified'])
        self.assertEqual(1, self.probe.inputs)
