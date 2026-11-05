import copy
import unittest
from unittest.mock import patch

from tacto.ask import ask_here_paged, what_to_do_here
from tacto.general import run
from tacto.observation_paging import continuation_candidate


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
                    page = copy.deepcopy(cs[-1])
                    if variant == 'forged':
                        page['element_index'] = 1
                    answer = {'actions': [{'do': 'set_value' if variant == 'write' else 'read', 'candidate': page}]}
                    if variant == 'mixed':
                        answer['actions'].append({'do': 'read', 'candidate': cs[0]})
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
        with patch('tacto.ask.reach_model', return_value='{"actions":[{"pick":0,"do":"read"}]}'):
            result = ask_here_paged('find', [page])
        self.assertEqual(page, result['actions'][0]['candidate'])
        self.assertNotIn('PRIVATE', repr(result))

    def test_no_cursor_does_not_invent_continuation(self):
        for obs in ({'truncated': True}, {'next_observation_cursor': ''}, {'next_observation_cursor': False}):
            self.assertIsNone(continuation_candidate(obs))


if __name__ == '__main__':
    unittest.main()
