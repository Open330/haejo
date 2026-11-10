"""A per-run popup is chosen by a stored selector, never a stored live ID."""
import contextlib
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from haejo import task as tasks
from haejo.flow import Flow
from haejo.window_scope import take_window_arg, resolve_window, bind_window, selector_problem
from tests import test_task as fixture

HOME = {'window_id': 20440, 'title': '[2026 법정필수교육] 과정', 'url': 'https://study.example.com/course'}
PORTAL = {'window_id': 20385, 'title': '연수원', 'url': 'https://www.example.com/'}
PLAYER = {'window_id': 22691, 'title': '[2026 법정필수교육] 과정', 'url': 'https://player.example.com/play'}


class Windows:
    def __init__(self, *listings):
        self.listings = list(listings)
        self.capabilities = {'observe.window_list', 'session.window_scope'}
        self.scoped = []

    def windows(self, target):
        rows = self.listings.pop(0) if len(self.listings) > 1 else self.listings[0]
        if isinstance(rows, dict):
            return rows
        return {'type': 'windows', 'target': target, 'windows': rows}

    def scope_window(self, target, window_id):
        self.scoped.append(window_id)
        return {'type': 'window_scope', 'window_id': window_id}


def flow_doc(**extra):
    return {'schema': 2, 'name': 'lesson', 'target': 'com.apple.Safari',
            'safety_defaults': {'effects': ['read'], 'reversibility': 'reversible',
                                'resource': {'object_type': 'page', 'scope': 'entry'}},
            'steps': [{'action': 'read', 'selector': {'role': 'StaticText'}, 'answers': True}], **extra}


class SelectorArgs(unittest.TestCase):
    def test_match_specs_become_one_selector(self):
        args, value = take_window_arg(['session', 'com.apple.Safari', '--window-match', 'url=player.example.com',
                                       '--window-match', 'newest', '--helper'])
        self.assertEqual(['session', 'com.apple.Safari', '--helper'], args)
        self.assertEqual({'url': 'player.example.com', 'newest': True}, value)
        self.assertEqual(7, take_window_arg(['--window-id', '7'])[1])
        self.assertIsNone(take_window_arg(['x'])[1])

    def test_bad_specs_are_refused(self):
        for argv in (['--window-match'], ['--window-match', 'host=x'], ['--window-match', 'url='],
                     ['--window-match', 'url=a', '--window-match', 'url=b'],
                     ['--window-id', '3', '--window-match', 'newest'],
                     ['--window-match', 'newest', '--document', '/tmp/a.txt']):
            with self.subTest(argv=argv), self.assertRaises(ValueError):
                take_window_arg(argv)
        self.assertIsNotNone(selector_problem({'window_id': 3}))
        self.assertIsNotNone(selector_problem({'url': '{{page}}'}))
        self.assertIsNotNone(selector_problem({'newest': False}))


class Resolution(unittest.TestCase):
    def test_url_tells_same_title_windows_apart(self):
        driver = Windows([HOME, PORTAL, PLAYER])
        self.assertEqual((22691, None), resolve_window(driver, 'com.apple.Safari', {'url': 'PLAYER.example'}))
        self.assertIsNone(bind_window(driver, 'com.apple.Safari', {'url': 'player.example.com'}))
        self.assertEqual([22691], driver.scoped)

    def test_ambiguous_lists_candidates_and_newest_takes_highest_id(self):
        driver = Windows([HOME, PORTAL, PLAYER])
        window_id, error = resolve_window(driver, 'com.apple.Safari', {'title': '법정필수교육'})
        self.assertIsNone(window_id)
        self.assertEqual('window_match_ambiguous', error['error'])
        self.assertEqual({20440, 22691}, {c['window_id'] for c in error['candidates']})
        self.assertEqual((22691, None), resolve_window(driver, 'com.apple.Safari', {'title': '법정필수교육', 'newest': True}))

    def test_waits_for_a_popup_that_is_still_opening(self):
        driver = Windows([HOME], [HOME], [HOME, PLAYER])
        sleeps = []
        self.assertEqual((22691, None), resolve_window(driver, 'com.apple.Safari', {'url': 'player'},
                                                       sleep=sleeps.append, clock=lambda: 0))
        self.assertEqual(2, len(sleeps))

    def test_none_carries_the_listing_reason(self):
        listing = {'type': 'windows', 'windows': [], 'reason': 'screen_locked',
                   'screen': {'locked': True}, 'unlisted': [{'window_id': 22691, 'reason': 'not_on_active_space'}]}
        ticks = iter([0, 0, 11])
        window_id, error = resolve_window(Windows(listing), 'com.apple.Safari', {'url': 'player'},
                                          sleep=lambda s: None, clock=lambda: next(ticks))
        self.assertIsNone(window_id)
        self.assertEqual(('window_match_none', 'screen_locked'), (error['error'], error['reason']))
        self.assertEqual('not_on_active_space', error['unlisted'][0]['reason'])

    def test_listing_errors_pass_through(self):
        refusal = {'type': 'error', 'error': 'target_not_found', 'effect': 'not_started'}
        self.assertEqual(refusal, resolve_window(Windows(refusal), 'x', {'url': 'a'})[1])
        old = Windows([HOME]);old.capabilities = set()
        self.assertEqual('window_list_unavailable', resolve_window(old, 'x', {'url': 'a'})[1]['error'])


class FlowField(unittest.TestCase):
    def test_round_trip_and_bind_keep_the_selector(self):
        flow = Flow.from_json(json.dumps(flow_doc(window={'url': 'player.example.com', 'newest': True})))
        self.assertEqual({'url': 'player.example.com', 'newest': True}, flow.window)
        self.assertEqual(flow.window, Flow.from_json(flow.to_json()).window)
        self.assertEqual(flow.window, flow.bind().window)
        self.assertNotIn('window', json.loads(Flow.from_json(json.dumps(flow_doc())).to_json()))

    def test_live_ids_are_not_a_selector(self):
        for bad in ({'window_id': 22691}, {}, {'url': 3}, 'player'):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                Flow.from_json(json.dumps(flow_doc(window=bad)))

    def test_session_stores_its_selector_and_refuses_a_different_one(self):
        from haejo.flow_session import prepare_session_flow
        selector = {'url': 'player.example.com'}
        flow = Flow.from_json(json.dumps(flow_doc()))
        _, template = prepare_session_flow(flow, 'com.apple.Safari', selector)
        self.assertEqual(selector, json.loads(template)['window'])
        _, template = prepare_session_flow(Flow.from_json(json.dumps(flow_doc())), 'com.apple.Safari', 22691)
        self.assertNotIn('window', json.loads(template))
        for window, doc in ((selector, flow_doc(window={'url': 'other'})), (None, flow_doc(window=selector))):
            with self.subTest(window=window), self.assertRaises(ValueError) as caught:
                prepare_session_flow(Flow.from_json(json.dumps(doc)), 'com.apple.Safari', window)
            self.assertIn('session_window_mismatch', str(caught.exception))


class RunAndBatch(unittest.TestCase):
    def test_run_binds_the_flow_window(self):
        from haejo.cli import _run_flow
        flow = Flow.from_json(json.dumps(flow_doc(window={'url': 'player'})))
        driver = Windows([HOME, PLAYER])
        with patch('haejo.cli._indicator_for', return_value=contextlib.nullcontext()), \
             contextlib.redirect_stdout(io.StringIO()), patch('haejo.flow.replay', side_effect=RuntimeError('stop')):
            try:
                _run_flow(flow, ['--helper', '--think', '0'], _driver=driver, _confirm=lambda d: False)
            except RuntimeError:
                pass
        self.assertEqual([22691], driver.scoped)

    def test_batch_opens_a_fresh_connection_per_job_for_a_window_flow(self):
        from haejo.flow_batch import run_batch
        for window, connections in (({'url': 'player'}, 3), (None, 1)):
            with self.subTest(window=window), tempfile.TemporaryDirectory() as tmp:
                src = Path(tmp)/'flow.json'
                src.write_text(json.dumps(flow_doc(**({'window': window} if window else {}))))
                drivers = []
                def make(flags):
                    d = Mock();d.activated = False;drivers.append(d);return d
                read, write = os.pipe()
                os.write(write, b'{"params":{}}\n'*3);os.close(write)
                with os.fdopen(read) as stream:
                    code = run_batch([str(src), '--helper', '--max-jobs', '3'], make_driver=make,
                                     run_flow=Mock(return_value=0), stdin=stream, emit=lambda line: None)
                self.assertEqual(0, code)
                self.assertEqual(connections, len(drivers))
                for d in drivers:
                    d.close.assert_called_once()


class ReuseHint(unittest.TestCase):
    setUp = fixture.TaskStoreTests.setUp
    tearDown = fixture.TaskStoreTests.tearDown

    def run_once(self, task_id, flow):
        binding = tasks.bind(task_id, 'session')
        binding.admit()
        token = tasks.current.set(binding)
        try:
            return tasks.note_session_success(flow)
        finally:
            tasks.current.reset(token)

    def test_hint_once_when_the_same_shape_repeats(self):
        task_id = tasks.start('20차시 수강')['id']
        lesson = Flow.from_json(json.dumps(flow_doc()))
        other = Flow.from_json(json.dumps(flow_doc(name='other')))
        self.assertIsNone(self.run_once(task_id, lesson))
        self.assertIsNone(self.run_once(task_id, other))
        hint = self.run_once(task_id, lesson)
        self.assertTrue(hint.startswith('HAEJO_HINT reuse:'))
        self.assertIn('haejo batch', hint);self.assertIn('--reuse-guide --save', hint)
        self.assertIsNone(self.run_once(task_id, lesson))
        self.assertIsNone(tasks.note_session_success(lesson))   # no task bound

    def test_guide_names_the_batch_path(self):
        from haejo.command_help import session_guide
        self.assertIn('haejo batch', session_guide('com.apple.Safari'))
        self.assertNotIn('haejo batch', session_guide('com.apple.calculator'))


if __name__ == '__main__':
    unittest.main()
