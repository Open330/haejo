import copy
import json
import unittest
from unittest.mock import patch

from haejo.ask import ask_here_paged, what_to_do_here
from haejo.general import run
from haejo.observation_paging import continuation_candidate


class PagedApp:
    """Each snapshot deliberately reuses index 1 for a different element."""
    def __init__(self):
        self.observed = []
        self.actions = []
        self.page = 0
        self.cancelled = False

    def observe(self, target, mode, require_window=False, **options):
        cursor = options.get('continuation')
        self.observed.append(cursor)
        self.page = 0 if cursor is None else int(cursor.removeprefix('PRIVATE-cursor-'))
        result = {'type': 'observation', 'obs_id': f'obs-{self.page}',
                  'tree': f'0 Window Title: Large list\n  1 StaticText Title: row-{self.page}, Value: value-{self.page}',
                  'truncated': self.page < 3}
        if self.page < 3:
            result['next_observation_cursor'] = f'PRIVATE-cursor-{self.page + 1}'
        return result

    def act(self, obs_id, target, action, **kwargs):
        self.actions.append((obs_id, action.copy()))
        return {'type': 'acted'}


def find_last(goal, cands, history):
    wanted = next((c for c in cands if c['match'] == 'row-3'), None)
    if wanted:
        return {'actions': [{'candidate': wanted, 'do': 'read'}], 'finishes': True}
    more = next(c for c in cands if c.get('_observation_page'))
    return {'actions': [{'candidate': more, 'do': 'read'}]}


class GeneralObservationPagingTests(unittest.TestCase):
    def test_presence_expectation_opts_in_but_legacy_driver_call_stays_compatible(self):
        from tests import test_general_finishes as finish
        for caps in (set(), {'observe.continuation_v1'}):
            app = finish.Counter()
            app.capabilities = caps
            original = app.wait_until
            with patch.object(app, 'wait_until', wraps=original) as wait:
                plan, _ = finish.planner({'actions': [('click', 'Increment')],
                    'expect': 'total 1', 'finishes': True})
                result = run(app, 'counter', 'increment once', plan)
            self.assertTrue(result.verified, result.why)
            self.assertEqual({'search_pages': True} if caps else {}, wait.call_args.kwargs)

    def test_trace_keeps_presence_search_option_and_rejects_changed_request(self):
        from haejo.trace import TracingDriver, TraceDriver
        from unittest.mock import Mock
        app = Mock(capabilities={'observe.continuation_v1'})
        app.wait_until.return_value = {'type': 'observation', 'tree': 'owned result'}
        live = TracingDriver(app)
        live.wait_until('owned', lambda tree: 'result' in tree, search_pages=True)
        self.assertTrue(app.wait_until.call_args.kwargs['search_pages'])
        recorded = TraceDriver(live.trace)
        self.assertEqual('observation', recorded.wait_until('owned', lambda t: 'result' in t, search_pages=True)['type'])
        replay = TraceDriver(live.trace)
        self.assertEqual('error', replay.wait_until('owned', lambda t: True)['type'])

    def test_recorded_continuation_can_be_replayed_offline_with_original_cursor(self):
        from haejo.trace import TracingDriver, TraceDriver
        from unittest.mock import Mock
        app = Mock(capabilities={'observe.continuation_v1'})
        app.observe.side_effect = [
            {'type': 'observation', 'tree': 'first', 'next_observation_cursor': 'oc123'},
            {'type': 'observation', 'tree': 'tail'}]
        live = TracingDriver(app)
        first = live.observe('owned')
        live.observe('owned', continuation=first['next_observation_cursor'], _settle_after_action=False)
        self.assertEqual({'continuation': 'oc123', '_settle_after_action': False}, app.observe.call_args.kwargs)
        replay = TraceDriver(live.trace)
        first = replay.observe('owned')
        self.assertEqual('tail', replay.observe('owned', continuation=first['next_observation_cursor'], _settle_after_action=False)['tree'])

    def test_exact_name_lookup_replaces_page_scan_and_uses_fresh_native_index(self):
        class SearchApp(PagedApp):
            capabilities = {'observe.reveal'}
            def observe(self, *args, **kwargs):
                if kwargs.get('reveal'):
                    self.revealed = kwargs['reveal']
                    return super().observe(*args, continuation='PRIVATE-cursor-3')
                return super().observe(*args, **kwargs)
        app = SearchApp()
        def planner(goal, cands, history):
            if not any(c['match'] == 'row-3' for c in cands):
                self.assertTrue(cands[0]['_observation_reveal'])
                return {'find_in_observation': 'row-3'}
            return find_last(goal, cands, history)
        result = run(app, 'owned', 'read row-3', planner)
        self.assertTrue(result.verified, result.why)
        self.assertEqual(['row-3'], app.revealed)
        self.assertEqual(1, result.observation_searches)
        self.assertEqual(0, result.observation_pages)
        self.assertEqual(['value-3'], result.said)
        self.assertEqual([('obs-3', {'name': 'read', 'element_index': 1})], app.actions)

    def test_lookup_requires_advertised_support_and_no_input_or_completion(self):
        page = continuation_candidate({'next_observation_cursor': 'private'}, reveal_supported=True)
        q = what_to_do_here('find', [page])
        good = {'find_in_observation': 'Item239'}
        self.assertEqual('Item239', q.check(good)['find_in_observation'])
        self.assertIsNone(what_to_do_here('find', [dict(page, _observation_reveal=False)]).check(good))
        for extra in ({'done': True}, {'actions': [{'pick': 0, 'do': 'read'}]},
                      {'expect': 'done'}, {'finishes': False}, {'unknown': 'PRIVATE'}):
            self.assertIsNone(q.check({**good, **extra}))
        for label in ('', 'a\nb', 'x'*257, None, ['Item239']):
            self.assertIsNone(q.check({'find_in_observation': label}))
        with patch('haejo.ask.reach_model', return_value=json.dumps(good)):
            result = ask_here_paged('find', [page])
        self.assertEqual('Item239', result['find_in_observation'])

    def test_reaches_omitted_page_without_dispatching_fake_read_or_old_index(self):
        app = PagedApp()
        result = run(app, 'owned', 'read row-3', find_last)
        self.assertTrue(result.verified, result.why)
        self.assertEqual(['value-3'], result.said)
        self.assertEqual(3, result.observation_pages)
        # General mode retains its normal final read-only completion check.
        self.assertEqual([None, 'PRIVATE-cursor-1', 'PRIVATE-cursor-2', 'PRIVATE-cursor-3', None], app.observed)
        self.assertEqual([('obs-3', {'name': 'read', 'element_index': 1})], app.actions)
        self.assertEqual(1, len(result.visits))

    def test_cancellation_after_page_request_never_reads_next_page(self):
        app = PagedApp()
        def planner(*args):
            result = find_last(*args)
            app.cancelled = True
            return result
        result = run(app, 'owned', 'find', planner, cancelled=lambda: app.cancelled)
        self.assertEqual('cancelled', result.stop_reason)
        self.assertEqual([None], app.observed)
        self.assertEqual([], app.actions)

    def test_page_requests_use_existing_total_screen_budget(self):
        app = PagedApp()
        result = run(app, 'owned', 'find', find_last, max_screens=2)
        self.assertEqual('screen_limit', result.stop_reason)
        self.assertEqual([None, 'PRIVATE-cursor-1'], app.observed)
        self.assertEqual(1, result.observation_pages)
        self.assertFalse(result.verified)
        self.assertEqual([], app.actions)

    def test_stale_cursor_is_reported_without_restart_or_dispatch(self):
        app = PagedApp()
        original = app.observe
        def observe(*args, **kwargs):
            if kwargs.get('continuation'):
                return {'type': 'error', 'error': 'observation_cursor_stale'}
            return original(*args, **kwargs)
        app.observe = observe
        result = run(app, 'owned', 'find', find_last)
        self.assertIn('observation_cursor_stale', result.why)
        self.assertFalse(result.ok)
        self.assertEqual([], app.actions)

    def test_mixed_forged_or_finishing_page_request_never_dispatches(self):
        for variant in ('mixed', 'forged', 'finishes', 'expect', 'write'):
            with self.subTest(variant=variant):
                app = PagedApp()
                def planner(goal, cs, history):
                    page = copy.deepcopy(next(c for c in cs if c.get('_observation_page')))
                    if variant == 'forged':
                        page['element_index'] = 1
                    answer = {'actions': [{'do': 'set_value' if variant == 'write' else 'read', 'candidate': page}]}
                    if variant == 'mixed':
                        answer['actions'].append({'do': 'read', 'candidate': next(c for c in cs if not c.get('_observation_page'))})
                    if variant == 'finishes':
                        answer['finishes'] = True
                    if variant == 'expect':
                        answer['expect'] = 'done'
                    return answer
                result = run(app, 'owned', 'find', planner)
                self.assertFalse(result.ok)
                self.assertEqual([None], app.observed)
                self.assertEqual([], app.actions)

    def test_cursor_never_enters_candidate_prompt_and_mixed_answer_rejected(self):
        page = continuation_candidate({'next_observation_cursor': 'PRIVATE-cursor-value'})
        q = what_to_do_here('find', [page])
        self.assertNotIn('PRIVATE', q.prompt)
        self.assertIn('아직 전체 항목을 확인한 것은 아닙니다', q.prompt)
        self.assertIsNotNone(q.check({'actions': [{'pick': 0, 'do': 'read'}]}))
        for extra in ({'finishes': True}, {'expect': 'done'}):
            self.assertIsNone(q.check({'actions': [{'pick': 0, 'do': 'read'}], **extra}))
        self.assertIsNone(q.check({'actions': [{'pick': 0, 'do': 'read'}, {'pick': 0, 'do': 'read'}]}))

    def test_token_paging_preserves_host_affordance(self):
        page = continuation_candidate({'next_observation_cursor': 'PRIVATE-cursor-value'})
        with patch('haejo.ask.reach_model', return_value='{"actions":[{"pick":0,"do":"read"}]}'):
            result = ask_here_paged('find', [page])
        self.assertEqual(page, result['actions'][0]['candidate'])
        self.assertNotIn('PRIVATE', repr(result))

    def test_no_cursor_does_not_invent_continuation(self):
        for obs in ({'truncated': True}, {'next_observation_cursor': ''}, {'next_observation_cursor': False}):
            self.assertIsNone(continuation_candidate(obs))

    def test_observation_affordance_is_not_offered_as_a_commit_witness(self):
        from haejo.general import _witness
        page = continuation_candidate({'next_observation_cursor': 'private-cursor'})
        with patch('haejo.general._probe') as probe, patch('haejo.general._probe_response') as read:
            def ask(*args):
                self.fail('A page request is not a readable recipient/body witness')
            self.assertIsNone(_witness(object(), {'obs_id': 'owned'}, 'owned', 'recipient', [page], ask, lambda _: None))
        probe.assert_not_called()
        read.assert_not_called()


if __name__ == '__main__':
    unittest.main()
