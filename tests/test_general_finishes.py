"""A batch the planner says finishes the goal ends the run on its own evidence."""
import unittest

from haejo.general import candidates, run


class Counter:
    """Increment button and a display; clicks are AX actions (no reobservation)."""
    capabilities = set()

    def __init__(self, start=0):
        self.count = start
        self.calls = []

    def tree(self):
        return ('0 Window Title: Counter\n'
                '  1 Button Description: Increment, Identifier: increment\n'
                f'  2 StaticText Value: total {self.count}, Identifier: count')

    def observe(self, *a, **k):
        return {'type': 'observation', 'obs_id': f'o{len(self.calls)}', 'tree': self.tree()}

    def probe(self, obs_id, target, index):
        return {'type': 'probe', 'line': self.tree().splitlines()[index]}

    def act(self, obs_id, target, action, **kw):
        self.calls.append(action['name'])
        if action['name'] == 'click':
            self.count += 1
        return {'type': 'acted'}

    def wait_until(self, target, predicate, **kw):
        tree = self.tree()
        return {'type': 'observation', 'tree': tree} if predicate(tree) else {'type': 'error'}


def planner(plan, *, then_done=True):
    asked = []
    def ask(goal, cands, history):
        asked.append(len(asked))
        if len(asked) > 1:
            return {'done': True} if then_done else {'actions': []}
        by = {c['match']: c for c in cands}
        return {'actions': [{'do': d, 'candidate': by[m]} for d, m in plan['actions']],
                'expect': plan.get('expect'), 'finishes': plan.get('finishes', False)}
    return ask, asked


class FinishesTests(unittest.TestCase):
    def test_expected_text_appearing_ends_without_a_final_question(self):
        app = Counter()
        ask, asked = planner({'actions': [('click', 'Increment')] * 2,
                              'expect': 'total 2', 'finishes': True})
        result = run(app, 'counter', 'add two', ask)
        self.assertTrue(result.ok and result.verified, result.why)
        self.assertTrue(result.finished_without_asking)
        self.assertEqual(1, len(asked))
        self.assertEqual(['click', 'click'], app.calls)
        self.assertEqual(['confirmed', 'confirmed'], [e['state'] for e in result.events])

    def test_without_the_declaration_the_last_question_is_still_asked(self):
        app = Counter()
        ask, asked = planner({'actions': [('click', 'Increment')] * 2, 'expect': 'total 2'})
        result = run(app, 'counter', 'add two', ask)
        self.assertTrue(result.ok and result.verified)
        self.assertFalse(result.finished_without_asking)
        self.assertEqual(2, len(asked))

    def test_fresh_changed_display_precedes_unchanged_controls(self):
        app = Counter()
        calls = []
        def ask(goal, choices, history):
            calls.append([choice['match'] for choice in choices])
            action = 'click' if len(calls) == 1 else 'read'
            return {'actions': [{'do': action, 'candidate': choices[0]}],
                    'finishes': action == 'read'}
        result = run(app, 'counter', 'increment and read the resulting count', ask)
        self.assertTrue(result.verified, result.why)
        self.assertEqual(['total 1'], result.said)
        self.assertEqual([['Increment', 'count'], ['count', 'Increment']], calls)

    def test_new_document_starts_with_normal_candidate_order(self):
        class NavigatingCounter(Counter):
            def observe(self, *args, **kwargs):
                return dict(super().observe(*args, **kwargs), document_id=str(self.count))

        def ask(goal, choices, history):
            self.assertEqual('Increment', choices[0]['match'])
            if history:
                return {'actions': [{'do': 'read', 'candidate': choices[1]}], 'finishes': True}
            return {'actions': [{'do': 'click', 'candidate': choices[0]}]}

        result = run(NavigatingCounter(), 'counter', 'increment and read', ask)
        self.assertEqual(['total 1'], result.said)
        self.assertTrue(result.verified, result.why)

    def test_same_button_name_in_two_containers_is_two_plans(self):
        class Settings(Counter):
            def tree(self):
                return ('0 Window Title: Settings\n'
                        '  1 Group Title: First\n'
                        '    2 Button Title: Choose\n'
                        '  3 Group Title: Second\n'
                        '    4 Button Title: Choose')

        stages = iter(('First', 'Second', None))
        app = Settings()

        def ask(goal, choices, history):
            name = next(stages)
            if name is None:
                return {'done': True}
            button = next(c for c in choices if c['container'] == name)
            return {'actions': [{'do': 'click', 'candidate': button}]}

        result = run(app, 'settings', 'choose both sections', ask)
        self.assertTrue(result.ok, result.why)
        self.assertEqual(['click', 'click'], app.calls)

    def test_missing_or_already_shown_evidence_falls_back_to_asking(self):
        for start, expect in ((0, 'total 3'),   # never appears
                              (2, 'total 2')):  # already there, then 'total 3'
            with self.subTest(expect=expect, start=start):
                app = Counter(start)
                ask, asked = planner({'actions': [('click', 'Increment')],
                                      'expect': expect, 'finishes': True})
                result = run(app, 'counter', 'add one', ask)
                self.assertFalse(result.finished_without_asking)
                self.assertEqual(2, len(asked))

    def test_a_reading_batch_finishes_on_the_values_it_read(self):
        app = Counter(5)
        ask, asked = planner({'actions': [('read', 'count')], 'finishes': True})
        result = run(app, 'counter', 'what is the total', ask)
        self.assertTrue(result.ok and result.verified)
        self.assertEqual(['total 5'], result.said)
        self.assertEqual(1, len(asked))


class PlannerCheckTests(unittest.TestCase):
    def check(self, answer):
        from haejo.ask import what_to_do_here
        cands = candidates(Counter().tree())
        return what_to_do_here('goal', cands).check(answer), cands

    def test_finishes_must_be_boolean_and_carry_evidence(self):
        click = {'pick': 0, 'do': 'click'}
        out, _ = self.check({'actions': [click], 'expect': 'total 1', 'finishes': True})
        self.assertIs(True, out['finishes'])
        self.assertIsNone(self.check({'actions': [click], 'finishes': 'yes'})[0])
        self.assertIsNone(self.check({'actions': [click], 'finishes': True})[0])
        self.assertIsNone(self.check({'actions': [], 'expect': 'x', 'finishes': True})[0])
        _, cands = self.check({'actions': []})
        read = {'pick': next(i for i, c in enumerate(cands) if c['match'] == 'count'), 'do': 'read'}
        self.assertIs(True, self.check({'actions': [read], 'finishes': True})[0]['finishes'])
        self.assertIs(False, self.check({'actions': [click], 'expect': 'x'})[0]['finishes'])


if __name__ == '__main__':
    unittest.main()
