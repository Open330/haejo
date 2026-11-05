"""wait_until may look past the first page for presence predicates (no GUI)."""
import unittest
from unittest.mock import patch

from tacto import driver
from tacto.observation_wait import MAX_WAIT_PAGES, match_in_pages


class Pages:
    """A first page, then continuation pages; records every observe call."""

    def __init__(self, trees, *, fail_at=None, repeat=False, endless=False):
        self.trees, self.fail_at, self.repeat, self.endless = trees, fail_at, repeat, endless
        self.calls = []

    def cursor(self, index):
        if self.repeat:
            return 'occursor'
        if self.endless or index + 1 < len(self.trees):
            return f'oc{index + 1}'
        return None

    def observe(self, target, mode='tree_full', **kwargs):
        self.calls.append(kwargs)
        cursor = kwargs.get('continuation')
        index = 0 if cursor is None else (len(self.calls) - 1 if self.repeat or self.endless
                                          else int(cursor[2:]))
        if self.fail_at is not None and index == self.fail_at:
            return {'type': 'error', 'error': 'continuation_stale', 'effect': 'not_started'}
        tree = self.trees[min(index, len(self.trees) - 1)]
        reply = {'type': 'observation', 'obs_id': f's{len(self.calls)}', 'tree': tree}
        if self.cursor(index):
            reply['next_observation_cursor'] = self.cursor(index)
        return reply


class MatchInPagesTests(unittest.TestCase):
    def run_pages(self, pages, predicate, deadline=float('inf')):
        first = pages.observe('app')
        return match_in_pages(pages.observe, 'app', predicate, first, deadline=deadline)

    def test_finds_result_on_a_later_page_and_returns_that_current_page(self):
        pages = Pages(['row1', 'row61', 'Item239'])
        page, read = self.run_pages(pages, lambda t: 'Item239' in t)
        self.assertEqual(('Item239', 2), (page['tree'], read))
        self.assertEqual(['oc1', 'oc2'], [c.get('continuation') for c in pages.calls[1:]])
        self.assertTrue(all(c.get('_settle_after_action') is False for c in pages.calls[1:]))

    def test_no_cursor_failed_page_repeated_cursor_and_bounds(self):
        self.assertEqual((None, 0), self.run_pages(Pages(['only']), lambda t: False))
        self.assertEqual((None, 1), self.run_pages(Pages(['a', 'b', 'c'], fail_at=1), lambda t: t == 'c'))
        self.assertEqual((None, 1), self.run_pages(Pages(['a', 'b'], repeat=True), lambda t: False))
        page, read = self.run_pages(Pages(['x'], endless=True), lambda t: False)
        self.assertEqual((None, MAX_WAIT_PAGES), (page, read))

    def test_deadline_is_respected_and_predicate_errors_propagate(self):
        pages = Pages(['a', 'b'])
        self.assertEqual((None, 0), self.run_pages(pages, lambda t: True, deadline=0))
        with self.assertRaises(ZeroDivisionError):
            self.run_pages(Pages(['a', 'b']), lambda t: 1 / 0 if t == 'b' else False)

    def test_document_token_is_forwarded(self):
        pages = Pages(['a', 'b'])
        first = pages.observe('app')
        match_in_pages(pages.observe, 'app', lambda t: t == 'b', first, deadline=float('inf'),
                       document_token='tok')
        self.assertEqual('tok', pages.calls[1]['document_token'])


class DriverWaitTests(unittest.TestCase):
    def drivers(self, pages):
        from tacto.helper import HelperDriver
        d = driver.Driver.__new__(driver.Driver)
        d.observe = pages.observe
        h = HelperDriver.__new__(HelperDriver)
        h.observe = pages.observe
        h.capabilities = {'observe.continuation_v1'}
        return (('driver', d), ('helper', h))

    def test_default_wait_never_reads_pages(self):
        for name, factory in (('driver', 0), ('helper', 1)):
            with self.subTest(name), patch('tacto.driver.time.sleep'), patch('tacto.helper.time.sleep'):
                pages = Pages(['a', 'Item239'])
                d = self.drivers(pages)[factory][1]
                reply = d.wait_until('app', lambda t: 'Item239' in t, timeout_ms=0)
                self.assertEqual('timeout', reply['type'])
                self.assertTrue(all('continuation' not in c for c in pages.calls))

    def test_search_pages_finds_tail_result_without_sleeping(self):
        for name, factory in (('driver', 0), ('helper', 1)):
            with self.subTest(name), patch('tacto.driver.time.sleep') as s1, patch('tacto.helper.time.sleep') as s2:
                pages = Pages(['a', 'b', 'Item239'])
                d = self.drivers(pages)[factory][1]
                reply = d.wait_until('app', lambda t: 'Item239' in t, timeout_ms=4000, search_pages=True)
                self.assertEqual(('observation', 'Item239', 2),
                                 (reply['type'], reply['tree'], reply['observation_pages_checked']))
                self.assertEqual(0, s1.call_count + s2.call_count, 'a match in pages adds no sleep')

    def test_first_page_match_costs_exactly_one_observation(self):
        for name, factory in (('driver', 0), ('helper', 1)):
            with self.subTest(name):
                pages = Pages(['Item239', 'b'])
                d = self.drivers(pages)[factory][1]
                reply = d.wait_until('app', lambda t: 'Item239' in t, search_pages=True)
                self.assertEqual(1, len(pages.calls))
                self.assertNotIn('observation_pages_checked', reply)

    def test_timeout_reports_the_first_page_and_pages_checked(self):
        for name, factory in (('driver', 0), ('helper', 1)):
            with self.subTest(name), patch('tacto.driver.time.sleep'), patch('tacto.helper.time.sleep'):
                pages = Pages(['first', 'second'])
                d = self.drivers(pages)[factory][1]
                reply = d.wait_until('app', lambda t: False, timeout_ms=30, search_pages=True)
                self.assertEqual('timeout', reply['type'])
                self.assertEqual('first', reply['last_obs']['tree'])
                self.assertGreaterEqual(reply['observation_pages_checked'], 1)
                # Every poll re-observes first; a page is only ever read right after.
                kinds = ['page' if 'continuation' in c else 'first' for c in pages.calls]
                self.assertEqual('first', kinds[0])
                self.assertNotIn(['page', 'page'], [kinds[i:i+2] for i in range(len(kinds) - 1)])
            with self.subTest(name + ' expired'):
                pages = Pages(['first', 'second'])
                d = self.drivers(pages)[factory][1]
                reply = d.wait_until('app', lambda t: False, timeout_ms=0, search_pages=True)
                self.assertEqual(0, reply['observation_pages_checked'], 'no page past the deadline')

    def test_helper_without_continuation_capability_does_not_page(self):
        pages = Pages(['a', 'Item239'])
        h = self.drivers(pages)[1][1]
        h.capabilities = set()
        with patch('tacto.helper.time.sleep'):
            reply = h.wait_until('app', lambda t: 'Item239' in t, timeout_ms=0, search_pages=True)
        self.assertEqual('timeout', reply['type'])
        self.assertEqual(1, len(pages.calls))


class RealDriverPagesTests(unittest.TestCase):
    """The in-process driver's actual continuation, on the synthetic AX fixture."""

    def test_tail_row_is_found_by_wait_through_real_pages(self):
        from tests.test_observation_continuation import ContinuationTests
        case = ContinuationTests('test_invalid_cursor_shapes')
        case.setUp()
        try:
            reply = case.d.wait_until('app', lambda t: 'fixture-140' in t, timeout_ms=1000, search_pages=True)
            self.assertEqual('observation', reply['type'])
            self.assertIn('fixture-140', reply['tree'])
            self.assertEqual(2, reply['observation_pages_checked'])
            self.assertEqual(reply['obs_id'], case.d._latest['app'].obs_id, 'the returned page is current')
        finally:
            case.doCleanups()


if __name__ == '__main__':
    unittest.main()
