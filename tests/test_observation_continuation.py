"""Explicit next pages of what an observation omitted (Python driver, synthetic AX).

No app, window or input is touched: the AX tree is a dictionary.
"""
import json
import unittest
from unittest.mock import patch

from tacto import driver
from tacto.flow import Selector


def parents(lines, elements):
    stack, result = [], {}
    for line in lines:
        head = line.lstrip().split()
        if not head or not head[0].isdigit():
            continue
        depth = len(line) - len(line.lstrip())
        node = elements[int(head[0])]
        while stack and stack[-1][0] >= depth:
            stack.pop()
        result[node] = stack[-1][1] if stack else None
        stack.append((depth, node))
    return result


class Fixture:
    """window 0 with 150 children; child 70 is a group with three children."""

    def __init__(self, graph=None):
        self.graph = graph or {0: list(range(1, 151)), 70: [1001, 1002, 1003]}
        self.launch = 111.0

    def parent(self, node):
        return next((p for p, kids in self.graph.items() if node in kids), None)

    def attr(self, node, key):
        if key == 'AXChildren':
            return list(self.graph.get(node, []))
        if key == 'AXParent':
            return self.parent(node)
        if key == 'AXRole':
            return 'AXWindow' if node == 0 else 'AXGroup' if node in self.graph else 'AXButton'
        if key == 'AXDocument':
            return 'file:///tmp/pinned%20file.txt' if node == 0 else None
        return True if key == 'AXEnabled' else None

    def label(self, node, **kwargs):
        return 'Title: ' + (json.dumps('fixture-0') if node == 0 else f'fixture-{node}')


class ContinuationTests(unittest.TestCase):
    def setUp(self):
        self.fx = Fixture()
        fx = self.fx
        self.patches = [
            patch.object(driver, '_real_windows', side_effect=lambda pid: [0]),
            patch.object(driver, '_attr', side_effect=lambda n, k: fx.attr(n, k)),
            patch.object(driver, '_elem_label', side_effect=lambda n, **kw: fx.label(n, **kw)),
            patch.object(driver, '_secondary_actions', return_value=[]),
            patch.object(driver, 'CFEqual', side_effect=lambda a, b: a == b),
            patch.object(driver, 'CFGetTypeID', side_effect=lambda value: 7),
            patch.object(driver, 'AXUIElementGetTypeID', side_effect=lambda: 7),
            patch('tacto.native_process_identity.process_start_identity', side_effect=lambda pid: fx.launch),
        ]
        for item in self.patches:
            item.start()
            self.addCleanup(item.stop)
        d = driver.Driver.__new__(driver.Driver)
        d._latest, d._last_action_at = {}, 0.0
        d._resolve = lambda target, launch=True: 42
        d._showing_control = lambda pid: None
        d._custom_selects = lambda obs: {}
        d.visual_read = lambda: None
        self.d = d

    def first(self):
        return self.d.observe('app', 'tree_full')

    def page(self, cursor):
        return self.d.observe('app', 'tree_full', continuation=cursor)

    def elements(self):
        return self.d._latest['app'].elements

    def test_pages_cover_every_omitted_child_once_with_fresh_indices(self):
        first = self.first()
        self.assertTrue(first['truncated'])
        self.assertEqual([0, *range(1, 61)], self.elements())
        cursor = first['next_observation_cursor']
        seen = set(self.elements())
        pages, ids = [], [first['obs_id']]
        while cursor:
            reply = self.page(cursor)
            self.assertEqual('observation', reply['type'], reply)
            ids.append(reply['obs_id'])
            lines = reply['tree'].splitlines()
            indices = [int(line.split()[0]) for line in lines if line.split()[0].isdigit()]
            self.assertEqual(list(range(len(self.elements()))), sorted(indices), 'indices restart per page')
            context = set(self.d._latest['app'].context)
            fresh = [e for e in self.elements() if e not in context]
            self.assertFalse(seen & set(fresh), 'no omitted element is shown twice as content')
            seen |= set(fresh)
            # Each element keeps its real parent (window/ancestors as context).
            for node, parent in parents(lines, self.elements()).items():
                self.assertEqual(self.fx.parent(node), parent)
            pages.append(reply)
            cursor = reply.get('next_observation_cursor')
        self.assertEqual(len(ids), len(set(ids)))
        everything = {0, *range(1, 151), 1001, 1002, 1003}
        self.assertEqual(everything, seen)
        self.assertFalse(pages[-1]['truncated'])
        self.assertEqual(0, pages[-1]['continuation']['entries_remaining'])
        self.assertFalse(pages[-1]['continuation']['frontier_queue_capped'])

    def test_page_window_context_names_the_same_document_as_the_first_walk(self):
        first = self.first()
        window_line = next(l for l in first['tree'].splitlines() if l.startswith('0 Window'))
        self.assertIn('Document: ', window_line)
        reply = self.page(first['next_observation_cursor'])
        context_line = next(l for l in reply['tree'].splitlines() if l.startswith('0 Window'))
        self.assertEqual(window_line.replace(' [focused]', ''), context_line)

    def test_page_selectors_resolve_with_ancestor_context(self):
        reply = self.page(self.first()['next_observation_cursor'])
        tree = reply['tree']
        index = Selector(role='Button', title='fixture-1002', ancestor='fixture-70').resolve(tree)[0]
        self.assertEqual(1002, self.elements()[index])
        index = Selector(role='Button', title='fixture-99', ancestor='fixture-0').resolve(tree)[0]
        self.assertEqual(99, self.elements()[index])

    def test_earlier_page_indices_are_stale_and_cursor_is_single_use(self):
        first = self.first()
        cursor = first['next_observation_cursor']
        self.assertEqual('observation', self.page(cursor)['type'])
        self.assertEqual('continuation_unknown_or_expired', self.page(cursor)['error'])
        stale = self.d.act(first['obs_id'], 'app', {'name': 'click', 'element_index': 5})
        self.assertEqual('stale_observation', stale['error'])
        self.assertEqual('not_started', stale['effect'])

    def test_new_observation_or_any_action_retires_the_cursor(self):
        cursor = self.first()['next_observation_cursor']
        self.first()
        self.assertEqual('continuation_unknown_or_expired', self.page(cursor)['error'])
        first = self.first()
        self.d.act(first['obs_id'], 'app', {'name': 'click', 'element_index': 1}, risk_class='bogus')
        self.assertEqual('continuation_unknown_or_expired', self.page(first['next_observation_cursor'])['error'])

    def test_changed_list_or_process_refuses_instead_of_guessing(self):
        cursor = self.first()['next_observation_cursor']
        self.fx.graph[0] = list(range(1, 152))           # one more child: indices may have moved
        self.assertEqual('continuation_stale', self.page(cursor)['error'])
        self.fx.graph[0] = list(range(1, 151))
        cursor = self.first()['next_observation_cursor']
        self.fx.launch = 222.0                            # same PID, another process
        self.assertEqual('continuation_target_changed', self.page(cursor)['error'])

    def test_document_scope_or_target_mismatch_is_refused(self):
        cursor = self.first()['next_observation_cursor']
        self.assertEqual('continuation_unknown_or_expired',
                         self.d.observe('other', 'tree_full', continuation=cursor)['error'])
        cursor = self.first()['next_observation_cursor']
        self.assertEqual('continuation_unknown_or_expired',
                         self.d.observe('app', 'tree_full', continuation=cursor, document_token='tok')['error'])

    def test_invalid_cursor_shapes(self):
        for cursor in ('', 'UPPER', 'a' * 129, 'has-dash', 5):
            with self.subTest(cursor=cursor):
                self.assertEqual('invalid_continuation', self.page(cursor)['error'])
        self.assertEqual('invalid_continuation',
                         self.d.observe('app', continuation='ocabc', reveal=['x'])['error'])

    def test_node_budget_frontier_pages_and_parents(self):
        graph = {0: [1, 2, 3, 4, 5]}
        for i in range(1, 6):
            graph[i] = [10 * i + j for j in range(1, 6)]
        self.fx.graph = graph
        with patch.object(driver, 'MAX_TREE_NODES', 12):
            first = self.first()
            seen = set(self.elements())
            cursor, pages = first.get('next_observation_cursor'), 0
            self.assertIsNotNone(cursor)
            while cursor:
                reply = self.page(cursor)
                pages += 1
                lines = reply['tree'].splitlines()
                for node, parent in parents(lines, self.elements()).items():
                    self.assertEqual(self.fx.parent(node), parent)
                context = set(self.d._latest['app'].context)
                seen |= {e for e in self.elements() if e not in context}
                cursor = reply.get('next_observation_cursor')
                self.assertLess(pages, 10)
        everything = {0} | set(graph[0]) | {n for i in range(1, 6) for n in graph[i]}
        self.assertEqual(everything, seen)
        self.assertGreater(pages, 1)

    def test_queue_cap_is_reported_not_hidden(self):
        self.fx.graph = {0: list(range(1, 70)), 5: list(range(500, 570))}
        with patch.object(driver, 'MAX_CONTINUATION_ENTRIES', 1):
            first = self.first()
            reply = self.page(first['next_observation_cursor'])
        self.assertTrue(reply['continuation']['frontier_queue_capped'])
        self.assertEqual(4096, driver.MAX_CONTINUATION_ENTRIES)


if __name__ == '__main__':
    unittest.main()


class RawHelperDriverScopeTests(unittest.TestCase):
    """The spawned-helper driver carries window scope like the inherited one."""

    def driver(self):
        import io
        from tacto.helper import HelperDriver
        d = HelperDriver.__new__(HelperDriver)
        class Proc:
            stdin = io.StringIO()
            stdout = io.StringIO('{"type":"ok"}\n' * 4)
        d._proc = Proc()
        return d

    def sent(self, d):
        return [json.loads(line) for line in d._proc.stdin.getvalue().splitlines()]

    def test_scoped_requests_carry_the_window_and_other_targets_are_refused(self):
        d = self.driver()
        d._window_scope = ('com.apple.finder', 77)
        self.assertEqual('ok', d._send({'type': 'observe', 'target': 'com.apple.finder'})['type'])
        refused = d._send({'type': 'observe', 'target': 'com.apple.TextEdit'})
        self.assertEqual(('window_scope_changed', 'not_started'), (refused['error'], refused['effect']))
        d._send({'type': 'list_targets'})
        sent = self.sent(d)
        self.assertEqual(2, len(sent), 'the refused request was never written')
        self.assertEqual(77, sent[0]['window_scope_id'])
        self.assertNotIn('window_scope_id', sent[1])

    def test_unscoped_driver_is_unchanged(self):
        d = self.driver()
        d._send({'type': 'observe', 'target': 'app'})
        self.assertNotIn('window_scope_id', self.sent(d)[0])
