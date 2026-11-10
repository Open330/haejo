"""Offline consent-form fixture: existing approval, exclusions and bound scope."""
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from haejo.agent import Agent
from haejo.commit_evidence import ArtifactEvidence, CommitEvidence
from haejo.cli import _confirmer
from haejo.contract import ContextBinding, Destination, Resource, SafetyContract, issue_approval, policy
from haejo.flow import Flow, Postcondition, Selector, Step, replay
from haejo.safety import classify

TARGET = 'example.owned.consent'


class ConsentForm:
    def __init__(self, path):
        self.path = path
        self.values = {'required-privacy': '0', 'required-sharing': '0', 'optional-marketing': '0'}
        self.clicks = []

    def observe(self, *args, **kwargs):
        rows = ['0 Window  Title: Owned consent form']
        for index, (identifier, value) in enumerate(self.values.items(), 1):
            rows.append(f'  {index} CheckBox  Identifier: {identifier}, Value: {value}')
        return {'type': 'observation', 'obs_id': 'owned-observation', 'tree': '\n'.join(rows)}

    def act(self, obs_id, target, action, **options):
        if options.get('risk_class') in ('confirm', 'preapproved') and options.get('approved') is not True:
            return {'type': 'confirm_request'}
        identifier = list(self.values)[action['element_index'] - 1]
        self.clicks.append(identifier)
        self.values[identifier] = '1'
        self.path.write_text(json.dumps(self.values))
        return {'type': 'acted'}

    def prepare_commit(self, event):
        return dict(self.values)

    def after_commit(self, event, response, before):
        # Independent fixture readback of the actual persisted artifact.
        data = self.path.read_bytes(); saved = json.loads(data)
        identifier = list(before)[event['action']['element_index'] - 1]
        assert before[identifier] == '0' and saved[identifier] == '1'
        assert saved['optional-marketing'] == '0'
        return CommitEvidence(event['event_id'], event['action_digest'],
            ArtifactEvidence('owned-consent', str(self.path), hashlib.sha256(data).hexdigest()))

    def wait_until(self, target, predicate, **kwargs):
        obs = self.observe()
        return obs if predicate(obs['tree']) else {'type': 'timeout', 'last_obs': obs}


def choice(identifier):
    # This fixture persists a choice on click; it is not downgraded to ephemeral.
    return Step('click', Selector(role='CheckBox', identifier=identifier),
        safety=SafetyContract(effects=['write_persistent'], data_classes=['personal'],
            reversibility='reversible', resource=Resource(object_type='consent choice', scope='item')),
        binding=ContextBinding(bundle_id=TARGET, role='CheckBox', identifier=identifier, operation='click'),
        postcondition=Postcondition(field=Selector(identifier=identifier), attribute='Value', equals='1'))


class ApprovedConsentTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory(); self.addCleanup(folder.cleanup)
        self.path = Path(folder.name)/'consents.json'

    def test_explicit_prior_approval_runs_required_choices_without_a_second_question(self):
        form = ConsentForm(self.path)
        flow = Flow('required-consents-only', TARGET,
                    [choice('required-privacy'), choice('required-sharing')], schema=2)
        approvals, blocked = Agent.authorize(object.__new__(Agent), flow, ask=_confirmer(['--yes']))
        self.assertEqual([], blocked)
        self.assertEqual({0, 1}, set(approvals))
        ask_again = Mock(side_effect=AssertionError('the unchanged approved steps must not ask again'))
        result = replay(form, flow, approvals=approvals, confirm=ask_again)
        self.assertTrue(result.ok, result.log)
        self.assertEqual(['required-privacy', 'required-sharing'], form.clicks)
        self.assertEqual('0', form.values['optional-marketing'])
        ask_again.assert_not_called()

    def test_unapproved_choice_is_not_dispatched(self):
        form = ConsentForm(self.path)
        result = replay(form, Flow('consent', TARGET, [choice('required-privacy')], schema=2))
        self.assertFalse(result.ok)
        self.assertEqual([], form.clicks)
        self.assertNotIn('handoff', str(result.log))

    def test_required_choice_token_does_not_authorize_optional_marketing(self):
        form = ConsentForm(self.path); required = choice('required-privacy')
        token = issue_approval(required.binding, required.safety)
        result = replay(form, Flow('optional', TARGET, [choice('optional-marketing')], schema=2),
                        approvals={0: token})
        self.assertFalse(result.ok)
        self.assertEqual([], form.clicks)
        self.assertEqual('0', form.values['optional-marketing'])

    def test_new_recipient_invalidates_the_existing_approval(self):
        contract = SafetyContract(effects=['transmit'], data_classes=['personal'],
            reversibility='irreversible', resource=Resource(object_type='consent form', scope='item'),
            destination=Destination(kind='third_party', identity='training.example'))
        binding = ContextBinding(bundle_id=TARGET, identifier='save-consents', operation='click',
                                 destination_identity='training.example')
        self.assertEqual('confirm', policy(contract).risk)
        flow = Flow('disclosure', TARGET, [Step('click', Selector(identifier='save-consents'),
                    safety=contract, binding=binding)], schema=2)
        approvals, blocked = Agent.authorize(object.__new__(Agent), flow, ask=_confirmer(['--yes']))
        self.assertEqual([], blocked)
        token = approvals[0]
        self.assertTrue(token.authorizes(binding, contract)[0])
        self.assertFalse(token.authorizes(replace(binding, destination_identity='other.example'), contract)[0])

    def test_consent_wording_is_not_a_security_handoff(self):
        for label in ('개인정보 수집 및 이용 동의(필수)', '개인정보 제3자 제공 및 위탁 동의(필수)',
                      '이용약관 동의', 'privacy consent', 'accept terms'):
            with self.subTest(label=label):
                self.assertNotEqual('handoff', classify({'name': 'click'}, '1 CheckBox  Title: '+label)[0])

    def test_noninteractive_path_reports_the_approval_route_without_claiming_manual_handoff(self):
        flow = Flow('required-consent', TARGET, [choice('required-privacy')], schema=2)
        with patch('sys.stdin.isatty', return_value=False):
            approvals, blocked = Agent.authorize(object.__new__(Agent), flow, ask=_confirmer([]))
        self.assertEqual({}, approvals)
        self.assertIn('--yes', ' '.join(blocked))
        self.assertNotIn('직접 해주셔야', ' '.join(blocked))


class SecurityWarningApprovalTests(unittest.TestCase):
    """A warning label the user told us to get past asks for approval, it does
    not become a step only the person can press."""
    def test_warning_labels_are_approvable(self):
        from haejo.safety import classify, merge
        for label in ('Proceed anyway', 'Not secure', '보안 우회', '안전하지 않은 사이트로 이동'):
            with self.subTest(label=label):
                self.assertEqual('confirm', classify({'name': 'click'}, '1 Button  Title: '+label)[0])
        self.assertEqual('confirm', merge('handoff', 'none'))
        self.assertEqual('confirm', merge('garbage', 'none'))
        self.assertEqual('confirm', merge('none', 'confirm'))
        self.assertEqual('none', merge('none', 'none'))

