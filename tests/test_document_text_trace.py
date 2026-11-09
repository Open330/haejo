"""Live document evidence must never be represented as replayable trace data."""
import unittest
from haejo.trace import Trace, TracingDriver, TraceDriver


class DocumentTextTraceTests(unittest.TestCase):
    def test_new_live_save_primitives_forward_without_retaining_body_or_tokens(self):
        from unittest.mock import Mock
        from haejo.document_snapshot import REQUIRED, SnapshotDriver, CAPABILITY
        live = Mock()
        live.capabilities = REQUIRED
        trace = Trace()
        wrapper = TracingDriver(live, trace)
        self.assertIn(CAPABILITY, SnapshotDriver(wrapper).capabilities)
        wrapper.document_text('com.apple.TextEdit', obs_id='current', window_element_index=3)
        live.document_text.assert_called_once_with('com.apple.TextEdit', document_token=None,
            max_utf16_units=1000000, obs_id='current', window_element_index=3)
        wrapper.document_mode('com.apple.TextEdit', 'pin')
        live.document_mode.assert_called_once_with('com.apple.TextEdit', document_token='pin')
        wrapper.save_panel('current','com.apple.TextEdit', commit_element_index=7, document_token='pin')
        live.save_panel.assert_called_once_with('current','com.apple.TextEdit',None,
            commit_element_index=7, document_token='pin', panel_token=None, require_format=False)
        self.assertEqual([], trace.events)
        offline = TraceDriver(trace)
        self.assertFalse(REQUIRED & offline.capabilities)
        self.assertEqual('not_started', offline.document_mode('com.apple.TextEdit','pin')['effect'])
        self.assertEqual('not_started', offline.save_panel('current','com.apple.TextEdit',commit_element_index=7)['effect'])
        self.assertEqual(0, offline._i)

    def test_save_panel_and_guard_forward_live_and_never_become_replayable(self):
        from unittest.mock import Mock
        live = Mock()
        live.capabilities = {'observe', 'evidence.save_panel', 'action.click.save_panel_guard'}
        trace = Trace(); wrapper = TracingDriver(live, trace)
        wrapper.save_panel('obs', 'owned', 0, panel_token='panel', require_format=True)
        live.save_panel.assert_called_once_with('obs', 'owned', 0, panel_token='panel',
            document_token=None, require_format=True)
        wrapper.act('obs', 'owned', {'name':'click','element_index':1},
                    risk_class='preapproved', approved=True, save_panel_token='panel')
        live.act.assert_called_once_with(obs_id='obs', target='owned',
            action={'name':'click','element_index':1}, expect=None, risk_class='preapproved',
            intent_text='', approved=True, save_panel_token='panel')
        self.assertEqual(trace.events, [])
        replay = TraceDriver(Trace(capabilities=list(live.capabilities)))
        self.assertEqual(replay.capabilities, frozenset({'observe'}))
        self.assertEqual(replay.save_panel('obs', 'owned', 0)['effect'], 'not_started')
        self.assertEqual(replay.act('obs', 'owned', {'name':'click','element_index':1},
            save_panel_token='panel', risk_class='preapproved', approved=True)['effect'], 'not_started')
        self.assertEqual(replay._i, 0)

    def test_live_path_and_scoped_observe_forward_without_recording_and_replay_refuses(self):
        from unittest.mock import Mock
        live = Mock()
        live.capabilities = {'evidence.document_text', 'evidence.document_text.path_selector', 'observe.document_token'}
        trace = Trace(); wrapper = TracingDriver(live, trace)
        wrapper.document_text('com.apple.TextEdit', document_path='/private/tmp/owned.rtf')
        live.document_text.assert_called_once_with('com.apple.TextEdit', document_token=None,
                                                  max_utf16_units=1000000, document_path='/private/tmp/owned.rtf')
        wrapper.observe('com.apple.TextEdit', document_token='token')
        live.observe.assert_called_once_with('com.apple.TextEdit', 'tree_full', require_window=True, document_token='token')
        self.assertEqual(trace.events, [])
        replay = TraceDriver(trace)
        self.assertEqual(replay.capabilities, frozenset())
        self.assertEqual(replay.observe('com.apple.TextEdit', document_token='token')['effect'], 'not_started')

    def test_live_reader_forwards_identity_and_budget_without_recording_body(self):
        class Live:
            capabilities = {'evidence.document_text'}
            def document_text(self, target, document_token=None, *, max_utf16_units):
                self.request = target, document_token, max_utf16_units
                return {'type': 'document_text', 'text': 'private document body',
                        'document_token': document_token, 'text_complete': True}
        live = Live(); trace = Trace(); wrapper = TracingDriver(live, trace)
        result = wrapper.document_text('com.apple.TextEdit', 'live-token', max_utf16_units=42)
        self.assertEqual(('com.apple.TextEdit', 'live-token', 42), live.request)
        self.assertTrue(result['text_complete'])
        self.assertEqual([], trace.events)
        self.assertNotIn('private document body', trace.to_json())
        self.assertIn('evidence.document_text', wrapper.capabilities)

    def test_reloaded_trace_cannot_claim_live_document_evidence(self):
        trace = Trace(capabilities=['observe', 'evidence.document_text',
                                    'evidence.document_snapshot'])
        replay = TraceDriver(trace)
        self.assertEqual(frozenset({'observe'}), replay.capabilities)
