"""Failures seen in real use (three Macs, 2026-11-04 to 11-18) that were not
failures: the input had been delivered and worked, or the authored JSON said
what was meant. Each test names the record it came from."""
import json
import unittest
from unittest.mock import patch

from haejo.contract import Envelope
from haejo.flow import Flow, Postcondition, Selector, Step, replay
from haejo.flow_errors import feedback


class SendApp:
    """A chat app with no host receipt: pressing Send moves the text into the transcript."""
    capabilities = {'action.click'}

    def __init__(self, *, delivers=True, acknowledges=True, already=False):
        self.delivers, self.acknowledges, self.sent, self.calls = delivers, acknowledges, already, []

    def observe(self, *args, **kwargs):
        tree = ('0 Window  Title: Chat\n  1 Button  Identifier: send\n'
                f'  2 StaticText  Identifier: last, Value: {"hello" if self.sent else "none"}\n'
                '  3 Button  Identifier: next')
        return {'type': 'observation', 'obs_id': f'o{len(self.calls)}', 'tree': tree}

    def act(self, obs, target, action, **kwargs):
        self.calls.append(action)
        if self.delivers and action['element_index'] == 1:
            self.sent = True
        return {'type': 'acted', 'action': 'click'} if self.acknowledges else \
            {'type': 'acted', 'action': 'click', 'unverified': 'observe_effect'}

    def wait_until(self, target, predicate, **kwargs):
        seen = self.observe()
        return seen if predicate(seen['tree']) else {'type': 'timeout', 'last_obs': seen}


def send(postcondition=True):
    safety = Envelope.minimal().contract_for({'transmit'}, 'send the message')
    return Step('click', Selector(identifier='send'), safety=safety,
                postcondition=Postcondition(field=Selector(identifier='last'), attribute='Value', equals='hello')
                if postcondition else None)


def after():
    return Step('click', Selector(identifier='next'),
                safety=Envelope.minimal().contract_for({'write_ephemeral'}, 'next'))


def run(app, steps):
    with patch('haejo.flow._approved', return_value=True):
        return replay(app, Flow('send', 'fixture.chat', steps, schema=2))


class ConsequentialStepTests(unittest.TestCase):
    """`commit_unverified`: 1,500 records, among them a TestFlight install, a
    CloudKit deploy and chat sends that had all worked."""

    def test_the_named_result_showing_completes_the_step_and_the_flow_goes_on(self):
        app = SendApp()
        result = run(app, [send(), after()])
        self.assertTrue(result.ok, result.log)
        self.assertEqual([1, 3], [call['element_index'] for call in app.calls])
        self.assertEqual('postcondition', result.events[0].get('checked_by'))
        self.assertNotEqual('confirmed', result.events[0]['state'], 'a result check is not a host receipt')

    def test_a_result_that_does_not_show_stays_unverified_and_is_not_resent(self):
        app = SendApp(delivers=False)
        result = run(app, [send(), after()])
        self.assertFalse(result.ok)
        self.assertEqual(('unverified', 'commit_unverified', False),
                         (result.log[-1]['status'], result.log[-1]['error'], result.log[-1]['postcondition_observed']))
        self.assertEqual(1, len(app.calls))

    def test_without_a_named_result_it_stays_unverified(self):
        app = SendApp()
        result = run(app, [send(postcondition=False), after()])
        self.assertFalse(result.ok)
        self.assertEqual('commit_unverified', result.log[-1]['error'])
        self.assertEqual(1, len(app.calls))

    def test_an_unacknowledged_press_stays_unverified(self):
        app = SendApp(acknowledges=False)
        result = run(app, [send()])
        self.assertFalse(result.ok)
        self.assertEqual(1, len(app.calls))


class AuthoringTests(unittest.TestCase):
    def flow(self, **changes):
        base = {'schema': 2, 'name': 'n', 'target': 'com.example.app', 'steps': [
            {'action': 'click', 'selector': {'role': 'Button', 'title': 'Go'},
             'safety': {'effects': ['write_ephemeral'], 'reversibility': 'reversible',
                        'resource': {'object_type': 'entry', 'scope': 'entry'}}}]}
        return json.dumps({**base, **changes})

    def test_description_names_the_same_field_the_observation_prints(self):
        """`Use desc, not description` cost a round trip per authored Flow."""
        raw = json.loads(self.flow())
        raw['steps'][0]['selector'] = {'role': 'TextArea', 'description': 'Write a message...'}
        flow = Flow.from_json(json.dumps(raw))
        self.assertEqual('Write a message...', flow.steps[0].selector.desc)

    def test_window_with_an_earlier_schema_number_is_read_and_saved_as_schema_5(self):
        """`Set "schema": 5` refusals: the author had said which window."""
        flow = Flow.from_json(self.flow(window={'url': 'appstoreconnect.apple.com'}))
        self.assertEqual({'url': 'appstoreconnect.apple.com'}, dict(flow.window))
        self.assertEqual(5, json.loads(flow.to_json())['schema'])

    def test_a_top_level_problem_is_named(self):
        for change, word in (({'steps': {}}, 'steps'), ({'name': ''}, 'name/target'), ({'schema': 1}, 'schema')):
            with self.subTest(change=change):
                with self.assertRaises(ValueError) as caught:
                    Flow.from_json(self.flow(**change))
                self.assertTrue(feedback(caught.exception).startswith(word), feedback(caught.exception))


if __name__ == '__main__':
    unittest.main()
