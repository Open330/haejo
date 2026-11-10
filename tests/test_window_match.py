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
    return {'schema': 5 if 'window' in extra else 2, 'name': 'lesson', 'target': 'com.apple.Safari',
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
        self.assertEqual((22691, None), resolve_window(driver, 'com.apple.Safari', {'url': 'PLAYER.example.com'}))
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
        self.assertEqual((22691, None), resolve_window(driver, 'com.apple.Safari', {'url': 'player.example.com'},
                                                       sleep=sleeps.append, clock=lambda: 0))
        self.assertEqual(2, len(sleeps))

    def test_none_carries_the_listing_reason(self):
        listing = {'type': 'windows', 'windows': [], 'reason': 'screen_locked',
                   'screen': {'locked': True}, 'unlisted': [{'window_id': 22691, 'reason': 'not_on_active_space'}]}
        ticks = iter(range(0, 1000, 6))
        window_id, error = resolve_window(Windows(listing), 'com.apple.Safari', {'url': 'player.example.com'},
                                          sleep=lambda s: None, clock=lambda: next(ticks))
        self.assertIsNone(window_id)
        self.assertEqual(('window_match_none', 'screen_locked'), (error['error'], error['reason']))
        self.assertEqual('not_on_active_space', error['unlisted'][0]['reason'])

    def test_listing_errors_pass_through(self):
        refusal = {'type': 'error', 'error': 'target_not_found', 'effect': 'not_started'}
        self.assertEqual(refusal, resolve_window(Windows(refusal), 'x', {'url': 'a.example.com'})[1])
        old = Windows([HOME]);old.capabilities = set()
        self.assertEqual('window_list_unavailable', resolve_window(old, 'x', {'url': 'a.example.com'})[1]['error'])


class UrlMatching(unittest.TestCase):
    def test_host_boundary_scheme_and_case_sensitive_path(self):
        from haejo.window_scope import url_matches
        url = 'https://player.example.com/LessonA/play'
        for pattern, expected in (('example.com', True), ('player.example.com/LessonA', True),
                                  ('https://player.example.com/LessonA', True), ('PLAYER.EXAMPLE.COM', True),
                                  ('player.example.com/lessona', False), ('http://player.example.com', False),
                                  ('ample.com', False), ('other.example.com', False)):
            with self.subTest(pattern=pattern):
                self.assertEqual(expected, url_matches(pattern, url))
        self.assertFalse(url_matches('player.example.com', 'https://unrelated.test/player.example.com/'))
        self.assertFalse(url_matches('player.example.com', None))
        self.assertIsNotNone(selector_problem({'url': 'player'}))
        self.assertIsNone(selector_problem({'url': 'localhost:8000/home.html'}))

    def test_patient_resolution_waits_through_a_lock(self):
        locked = {'type': 'windows', 'windows': [], 'reason': 'screen_locked'}
        driver = Windows(locked, locked, locked, [HOME, PLAYER])
        sleeps = []
        self.assertEqual((22691, None), resolve_window(driver, 'com.apple.Safari', {'url': 'player.example.com'},
                                                       sleep=sleeps.append, clock=lambda: 100, patient=True))
        self.assertEqual(3, len(sleeps))
        impatient = Windows(locked)
        ticks = iter(range(0, 1000, 6))
        self.assertEqual('window_match_none', resolve_window(impatient, 'x', {'url': 'player.example.com'},
                         sleep=lambda s: None, clock=lambda: next(ticks))[1]['error'])

    def test_paused_time_is_measured_including_slow_listings(self):
        now = [0.0]
        locked = {'type': 'windows', 'windows': [], 'reason': 'screen_locked'}
        class Slow(Windows):
            def windows(self, target):
                now[0] += 4
                return super().windows(target)
        def sleep(seconds):
            now[0] += seconds
        driver = Slow(locked, locked, locked, [HOME], [HOME, PLAYER])
        self.assertEqual((22691, None), resolve_window(driver, 'x', {'url': 'player.example.com'}, wait=10,
                                                       sleep=sleep, clock=lambda: now[0], patient=True))
        error_lock = {'type': 'error', 'error': 'window_list_unavailable', 'reason': 'screen_locked'}
        self.assertEqual((22691, None), resolve_window(Windows(error_lock, [PLAYER]), 'x', {'url': 'player.example.com'},
                                                       sleep=lambda s: None, clock=lambda: 0, patient=True))
        self.assertEqual('window_list_unavailable', resolve_window(Windows(error_lock), 'x', {'url': 'player.example.com'},
                                                                   sleep=lambda s: None, clock=lambda: 0)[1]['error'])

    def test_a_resume_after_the_pause_cap_is_refused(self):
        now = [0.0]
        def sleep(seconds):
            now[0] += 30          # host suspended past the cap
        locked = {'type': 'windows', 'windows': [], 'reason': 'screen_locked'}
        with patch('haejo.window_scope.MAX_PAUSE_SECONDS', 20):
            window_id, error = resolve_window(Windows(locked, [PLAYER]), 'x', {'url': 'player.example.com'},
                                              sleep=sleep, clock=lambda: now[0], patient=True)
        self.assertIsNone(window_id)
        self.assertEqual('window_match_paused_too_long', error['error'])

    def test_explicit_ports_must_match(self):
        from haejo.window_scope import url_matches
        self.assertFalse(url_matches('https://player.example.com:8443/play', 'https://player.example.com:9443/play'))
        self.assertTrue(url_matches('player.example.com:8443', 'https://player.example.com:8443/play'))
        self.assertTrue(url_matches('https://player.example.com:443', 'https://player.example.com/play'))
        self.assertTrue(url_matches('player.example.com', 'https://player.example.com:9443/play'))
        self.assertIsNotNone(selector_problem({'url': 'player.example.com:notaport'}))


class FlowField(unittest.TestCase):
    def test_round_trip_and_bind_keep_the_selector(self):
        flow = Flow.from_json(json.dumps(flow_doc(window={'url': 'player.example.com', 'newest': True})))
        self.assertEqual({'url': 'player.example.com', 'newest': True}, flow.window)
        self.assertEqual(flow.window, Flow.from_json(flow.to_json()).window)
        self.assertEqual(flow.window, flow.bind().window)
        self.assertNotIn('window', json.loads(Flow.from_json(json.dumps(flow_doc())).to_json()))

    def test_window_needs_schema_5_so_older_runtimes_refuse_it(self):
        doc = flow_doc(window={'url': 'player.example.com'})
        self.assertEqual(5, json.loads(Flow.from_json(json.dumps(doc)).to_json())['schema'])
        for bad in (dict(doc, schema=2), dict(flow_doc(), schema=5)):
            with self.subTest(schema=bad['schema']), self.assertRaises(ValueError):
                Flow.from_json(json.dumps(bad))
        flow = Flow.from_json(json.dumps(flow_doc()));flow.window = {'url': 'player.example.com'}
        self.assertEqual(5, json.loads(flow.to_json())['schema'])

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
        for window, doc in ((selector, flow_doc(window={'url': 'other.example.com'})), (None, flow_doc(window=selector)),
                            (22691, flow_doc(window=selector))):
            with self.subTest(window=window), self.assertRaises(ValueError) as caught:
                prepare_session_flow(Flow.from_json(json.dumps(doc)), 'com.apple.Safari', window)
            self.assertIn('session_window_mismatch', str(caught.exception))


class RunAndBatch(unittest.TestCase):
    def test_run_binds_the_flow_window(self):
        from haejo.cli import _run_flow
        flow = Flow.from_json(json.dumps(flow_doc(window={'url': 'player.example.com'})))
        driver = Windows([HOME, PLAYER])
        with patch('haejo.cli._indicator_for', return_value=contextlib.nullcontext()), \
             contextlib.redirect_stdout(io.StringIO()), patch('haejo.flow.replay', side_effect=RuntimeError('stop')):
            try:
                _run_flow(flow, ['--helper', '--think', '0'], _driver=driver, _confirm=lambda d: False)
            except RuntimeError:
                pass
        self.assertEqual([22691], driver.scoped)

    def test_an_existing_session_pin_is_kept(self):
        from haejo.cli import _run_flow
        flow = Flow.from_json(json.dumps(flow_doc(window={'url': 'player.example.com'})))
        driver = Windows([HOME, PLAYER]);driver._window_scope = ('com.apple.Safari', 22000)
        driver._window_selector = ('com.apple.Safari', {'url': 'player.example.com'})
        with patch('haejo.cli._indicator_for', return_value=contextlib.nullcontext()), \
             contextlib.redirect_stdout(io.StringIO()), patch('haejo.flow.replay', side_effect=RuntimeError('stop')):
            try:
                _run_flow(flow, ['--helper', '--think', '0'], _driver=driver, _confirm=lambda d: False)
            except RuntimeError:
                pass
        self.assertEqual([], driver.scoped)

    def test_a_pin_made_for_another_selector_is_refused(self):
        from haejo.agent import Agent
        from haejo.window_scope import bind_window
        player = Flow.from_json(json.dumps(flow_doc(window={'url': 'player.example.com'})))
        home = Flow.from_json(json.dumps(flow_doc(window={'url': 'study.example.com'})))
        driver = Windows([HOME, PORTAL, PLAYER])
        driver.scope_window = lambda target, window_id: (setattr(driver, '_window_scope', (target, window_id))
                                                          or {'type': 'window_scope', 'window_id': window_id})
        agent = Agent(driver=driver)
        self.assertIsNone(agent.pin_window(home))
        self.assertEqual(('com.apple.Safari', 20440), driver._window_scope)
        self.assertIsNone(agent.pin_window(home))                         # same selector: kept
        self.assertEqual('window_scope_conflict', agent.pin_window(player)['error'])
        live = Windows([HOME]);live._window_scope = ('com.apple.Safari', 20440)
        self.assertEqual('window_scope_conflict', Agent(driver=live).pin_window(home)['error'])  # pinned by --window-id

    def test_agent_binds_the_flow_window_or_refuses(self):
        from haejo.agent import Agent
        flow = Flow.from_json(json.dumps(flow_doc(window={'url': 'player.example.com'})))
        driver = Windows([HOME, PLAYER])
        self.assertIsNone(Agent(driver=driver).pin_window(flow))
        self.assertEqual([22691], driver.scoped)
        with patch('haejo.window_scope.MATCH_WAIT_SECONDS', 0):
            self.assertEqual('window_match_none', Agent(driver=Windows([HOME])).pin_window(flow)['error'])
        self.assertIsNone(Agent(driver=Windows([HOME])).pin_window(Flow.from_json(json.dumps(flow_doc()))))
        source = Path(__import__('haejo.agent').agent.__file__).read_text(encoding='utf-8')
        self.assertLess(source.index('problem = self.pin_window(flow)'), source.index('res = replay(self.driver, flow'))

    def test_batch_opens_a_fresh_connection_per_job_for_a_window_flow(self):
        from haejo.flow_batch import run_batch
        for window, connections in (({'url': 'player.example.com'}, 3), (None, 1)):
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


class ClosingTheOwnWindow(unittest.TestCase):
    def replay(self, steps, after):
        from haejo.flow import replay
        flow = Flow.from_json(json.dumps({'schema': 2, 'name': 't', 'target': 'com.apple.Safari', 'steps': steps}))
        class App:
            capabilities = set()
            acted = None
            def observe(self, target, mode='tree_full', **kwargs):
                if self.acted:
                    return after
                return {'type': 'observation', 'obs_id': 'o',
                        'tree': '0 Window  Title: "Player" [focused]\n  1 Button  Subrole: AXCloseButton'}
            def act(self, obs, target, action, **kwargs):
                self.acted = action
                return {'type': 'acted', 'action': action['name'], 'obs_id': obs}
            def wait_until(self, target, predicate, **kwargs):
                return self.observe(target)
        return replay(App(), flow)

    SAFETY = {'effects': ['write_ephemeral'], 'reversibility': 'reversible',
              'resource': {'object_type': 'window', 'scope': 'item'}}

    def test_close_button_closing_the_pinned_window_is_done(self):
        close = {'action': 'click', 'selector': {'role': 'Button', 'subrole': 'AXCloseButton'}, 'safety': self.SAFETY}
        closed = {'type': 'error', 'error': 'window_scope_lost', 'reason': 'window_closed', 'effect': 'not_started'}
        result = self.replay([close], closed)
        self.assertTrue(result.ok, result.log)
        self.assertEqual('window_closed', result.log[0]['verified'])
        for after in ({**closed, 'reason': 'not_on_active_space'}, {**closed, 'reason': 'screen_locked'}):
            with self.subTest(reason=after['reason']):
                self.assertFalse(self.replay([close], after).ok)
        other = {'action': 'click', 'selector': {'role': 'Button', 'title': 'Next'}, 'safety': self.SAFETY}
        self.assertFalse(self.replay([other], closed).ok)


if __name__ == '__main__':
    unittest.main()
