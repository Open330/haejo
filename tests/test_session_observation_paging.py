import json
import os
import pty
import threading
import unittest
from unittest.mock import Mock, patch

from tacto.command_help import calculator_example
from tacto.flow_session import read_session_flow, run_session


class SessionObservationPagingTests(unittest.TestCase):
    def test_pinned_presence_wait_reads_tail_under_same_token_and_keeps_latest_indices(self):
        from tacto.document_scope import DocumentScopedDriver
        from tests import test_document_scoped_driver as cases
        inner = cases.ScopedDriverTests().inner()
        inner.capabilities = {*inner.capabilities, 'observe.continuation_v1'}
        first = dict(inner.observe.return_value, next_observation_cursor='oc123')
        tail = dict(inner.observe.return_value, obs_id='tail',
                    tree='0 Window Document: "/owned/document.txt"\n  4 TextArea Value: done')
        inner.observe.side_effect = [first, first, tail]  # constructor pin-read, fresh wait, continuation
        driver = DocumentScopedDriver(inner, cases.TARGET, cases.PATH)
        reply = driver.wait_until(cases.TARGET, lambda tree: 'Value: done' in tree, search_pages=True)
        self.assertEqual('tail', reply['obs_id'])
        self.assertEqual('tail', driver._obs_id)
        self.assertEqual(1, reply['observation_pages_checked'])
        self.assertEqual('pin', inner.observe.call_args.kwargs['document_token'])
        self.assertFalse(inner.observe.call_args.kwargs['_settle_after_action'])
        inner.document_text.assert_called_once()
        inner.act.assert_not_called()

    def test_pinned_document_continuation_keeps_one_token_and_current_indices(self):
        from tacto.document_scope import DocumentScopedDriver
        inner = Mock(capabilities={'evidence.document_text.path_selector', 'observe.document_token'})
        inner.document_text.return_value = {'type': 'document_text', 'document_path': '/owned/document.txt',
            'document_token': 'same-pin', 'text': 'owned', 'text_complete': True}
        inner.observe.return_value = {'type': 'observation', 'document_token': 'same-pin',
            'obs_id': 'next', 'tree': '0 Window Document: "/owned/document.txt"\n  4 TextArea Value: owned'}
        driver = DocumentScopedDriver(inner, 'com.apple.TextEdit', '/owned/document.txt')
        reply = driver.observe('com.apple.TextEdit', continuation='PRIVATE-cursor')
        self.assertEqual('observation', reply['type'])
        self.assertEqual({'require_window': True, 'document_token': 'same-pin', 'continuation': 'PRIVATE-cursor'},
                         inner.observe.call_args.kwargs)
        inner.document_text.assert_called_once()
        self.assertEqual('error', driver.act('next', 'com.apple.TextEdit', {'name': 'read', 'element_index': 1})['type'])
        inner.act.assert_not_called()
        inner.observe.return_value['tree'] = '0 Window Document: "/other/document.txt"\n  4 TextArea Value: personal'
        self.assertEqual('error', driver.observe('com.apple.TextEdit', continuation='next-cursor')['type'])
        inner.document_text.assert_called_once()  # No repin or app-wide read.

    def run_interactive(self, pages, replies, *, capabilities=()):
        app = Mock()
        app.capabilities = capabilities
        app.observe.side_effect = pages
        runner = Mock(return_value=0)
        messages = []
        replies = iter(replies)
        writers = []
        master, slave = pty.openpty()
        def emit(message):
            messages.append(message)
            if message.startswith('TACTO_SESSION_READY'):
                payload = (json.dumps(next(replies)) + '\n').encode()
                def write():
                    offset = 0
                    while offset < len(payload):
                        offset += os.write(master, payload[offset:])
                writer = threading.Thread(target=write, daemon=True)
                writers.append(writer)
                writer.start()
        try:
            with os.fdopen(os.dup(slave)) as stream:
                result = run_session(['com.apple.calculator', '--helper', '--guide'],
                    make_driver=lambda *args, **kwargs: app, run_flow=runner, stdin=stream, emit=emit)
        finally:
            for writer in writers:
                writer.join(2)
            os.close(master)
            os.close(slave)
        return result, app, runner, messages

    @staticmethod
    def page(cursor=None):
        result = {'type': 'observation', 'obs_id': 'owned', 'tree': '0 StaticText Value: 408'}
        if cursor:
            result['next_observation_cursor'] = cursor
        return result

    def test_same_connection_accepts_next_then_one_flow_without_cursor_in_output(self):
        result, app, runner, messages = self.run_interactive(
            [self.page('PRIVATE-cursor'), self.page()],
            [{'observe_next': True}, calculator_example()])
        self.assertEqual(0, result)
        self.assertEqual(2, app.observe.call_count)
        self.assertEqual({'continuation': 'PRIVATE-cursor'}, app.observe.call_args.kwargs)
        self.assertEqual(1, sum(m.startswith('TACTO_FLOW_GUIDE') for m in messages))
        self.assertEqual(2, sum(m.startswith('TACTO_SESSION_READY') for m in messages))
        self.assertIn('has_more_observation', '\n'.join(messages))
        self.assertNotIn('PRIVATE', '\n'.join(messages))
        runner.assert_called_once()
        app.act.assert_not_called()
        app.close.assert_called_once()

    def test_known_label_lookup_stays_on_same_session_and_no_native_input_is_sent(self):
        result, app, runner, messages = self.run_interactive(
            [self.page('PRIVATE-cursor'), self.page()],
            [{'find_in_observation': 'Item239'}, calculator_example()],
            capabilities={'observe.reveal'})
        self.assertEqual(0, result)
        self.assertEqual(2, app.observe.call_count)
        self.assertEqual({'reveal': ['Item239']}, app.observe.call_args.kwargs)
        self.assertIn('find_in_observation', '\n'.join(messages))
        self.assertNotIn('PRIVATE', '\n'.join(messages))
        app.act.assert_not_called()
        runner.assert_called_once()

    def test_unsupported_lookup_does_not_call_backend_or_restart_session(self):
        result, app, runner, messages = self.run_interactive(
            [self.page('PRIVATE-cursor')],
            [{'find_in_observation': 'Item239'}, calculator_example()])
        self.assertEqual(0, result)
        self.assertEqual(1, app.observe.call_count)
        self.assertIn('find_in_observation:', '\n'.join(messages))
        app.act.assert_not_called()
        runner.assert_called_once()

    def test_label_lookup_passes_the_existing_document_pin_without_widening(self):
        from tacto.document_scope import DocumentScopedDriver
        from tests import test_document_scoped_driver as cases
        inner = cases.ScopedDriverTests().inner()
        inner.capabilities = {*inner.capabilities, 'observe.reveal'}
        driver = DocumentScopedDriver(inner, cases.TARGET, cases.PATH)
        self.assertEqual('observation', driver.observe(cases.TARGET, reveal=['owned'])['type'])
        self.assertEqual({'require_window': True, 'document_token': 'pin', 'reveal': ['owned']},
                         inner.observe.call_args.kwargs)
        inner.document_text.assert_called_once()
        inner.act.assert_not_called()
        inner.observe.return_value['document_token'] = 'OTHER-PIN'
        self.assertEqual('error', driver.observe(cases.TARGET, reveal=['owned'])['type'])
        inner.document_text.assert_called_once()

    def test_rejected_continuation_does_not_dispatch_or_echo_transport_details(self):
        result, app, runner, messages = self.run_interactive(
            [self.page('PRIVATE-cursor'), {'type': 'error', 'error': 'PRIVATE-transport-detail'}],
            [{'observe_next': True}, calculator_example()])
        # The author may correct the request by submitting a fresh-replayed
        # Flow on this connection; the failed observation itself sends no input.
        self.assertEqual(0, result)
        self.assertIn('observe_next:', '\n'.join(messages))
        self.assertNotIn('PRIVATE', '\n'.join(messages))
        runner.assert_called_once()
        app.act.assert_not_called()

    def test_continuation_preserves_original_input_deadline(self):
        callback = Mock()
        with patch('tacto.flow_session.time.monotonic', side_effect=[100, 101, 104]), \
             patch('tacto.flow_session.read_flow_line', side_effect=['{"observe_next":true}', TimeoutError()]) as read:
            with self.assertRaises(TimeoutError):
                read_session_flow(3, 5, lambda _: None, observe_next=callback)
        self.assertEqual([4, 1], [call.args[1] for call in read.call_args_list])
        callback.assert_called_once()

    def test_mixed_command_is_repairable_before_observation_or_flow_dispatch(self):
        callback = Mock()
        with patch('tacto.flow_session.os.isatty', return_value=True), \
             patch('tacto.flow_session.read_flow_line', side_effect=[
                 '{"observe_next":true,"steps":["PRIVATE"]}', json.dumps(calculator_example())]):
            messages = []
            flow = read_session_flow(3, 5, messages.append, observe_next=callback)
        self.assertEqual('com.apple.calculator', flow.target)
        self.assertIn('observe_next:', '\n'.join(messages))
        self.assertNotIn('PRIVATE', '\n'.join(messages))
        callback.assert_not_called()

    def test_page_limit_ends_exploration_without_more_native_reads(self):
        pages = [self.page('PRIVATE-cursor-' + str(i)) for i in range(9)]
        result, app, runner, messages = self.run_interactive(
            pages, [{'observe_next': True}] * 9 + [calculator_example()])
        self.assertEqual(0, result)
        self.assertEqual(9, app.observe.call_count)  # initial + 8 continuation pages
        self.assertIn('Eight additional observations', '\n'.join(messages))
        self.assertNotIn('PRIVATE', '\n'.join(messages))
        app.act.assert_not_called()
        runner.assert_called_once()


if __name__ == '__main__':
    unittest.main()
