"""Opt-in menu approval on the CLI side, against a stand-in menu app socket."""
import io
import json
import os
from pathlib import Path
import socket
import tempfile
import threading
import unittest
from contextlib import redirect_stdout
from unittest import mock

from haejo import menu_approval
from haejo.agent import Agent
from haejo.flow import Flow

SEND = {'effects': ['transmit'], 'data_classes': ['personal'], 'reversibility': 'irreversible', 'commit_point': True,
        'resource': {'object_type': 'message', 'scope': 'entry'},
        'destination': {'kind': 'third_party', 'identity': 'slack:#team'}}
DRAFT = {'effects': ['write_ephemeral'], 'reversibility': 'reversible',
         'resource': {'object_type': 'draft', 'scope': 'entry'}}


def flow(with_send=True):
    steps = [{'action': 'set_value', 'selector': {'identifier': 'msg'}, 'params': {'value': 'hi'}, 'safety': DRAFT,
              'postcondition': {'field': {'identifier': 'msg'}, 'attribute': 'Value', 'equals': 'hi'}}]
    if with_send:
        steps.append({'action': 'click', 'selector': {'identifier': 'send'}, 'safety': SEND})
    return Flow.from_json(json.dumps({'schema': 2, 'name': 'send-msg', 'target': 'com.example.Chat', 'steps': steps}))


class FakeMenu:
    """Answers like the menu app: decisions come from `self.decision`, never the caller."""
    def __init__(self, path, decision='allowed'):
        self.path, self.decision, self.calls = str(path), decision, []
        self.claimed, self.consumed = {}, set()
        self.server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.server.bind(self.path); self.server.listen(8)
        threading.Thread(target=self.loop, daemon=True).start()

    def loop(self):
        while True:
            try:
                conn, _ = self.server.accept()
            except OSError:
                return
            with conn:
                data = b''
                while not data.endswith(b'\n'):
                    chunk = conn.recv(65536)
                    if not chunk:
                        break
                    data += chunk
                message = json.loads(data)
                self.calls.append(message)
                conn.sendall(json.dumps(self.reply(message)).encode() + b'\n')

    def reply(self, m):
        op = m['op']
        if op in ('plan', 'resume'):
            return {'status': self.decision, 'approval_id': m.get('approval_id') or 'ap_test0001'}
        if op == 'claim':
            if m['approval_id'] in self.claimed:
                return {'ok': False, 'reason': 'claimed'}
            self.claimed[m['approval_id']] = m['run_id']; return {'ok': True}
        if op == 'consume':
            key = (m['approval_id'], m['step'])
            if self.claimed.get(m['approval_id']) != m['run_id'] or key in self.consumed:
                return {'ok': False, 'reason': 'consumed'}
            self.consumed.add(key); return {'ok': True}
        if op == 'runtime':
            return {'status': 'allowed' if self.decision == 'allowed' else 'denied'}
        return {'ok': True}

    def close(self):
        self.server.close()


class MenuApprovalTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='haejo-menu-')
        self.root = Path(self.temp.name)
        patch = mock.patch('haejo.preferences.product_directory', return_value=self.root)
        patch.start(); self.addCleanup(patch.stop); self.addCleanup(self.temp.cleanup)

    def turn_on(self):
        (self.root/'preferences.json').write_text(json.dumps({'schema': 1, 'require_menu_approval': True}))

    def menu(self, decision='allowed'):
        fake = FakeMenu(self.root/'approval.sock', decision)
        self.addCleanup(fake.close)
        return fake

    def test_off_by_default_keeps_the_existing_yes(self):
        from haejo import cli
        self.assertFalse(menu_approval.enabled())
        self.assertIs(True, cli._confirmer(['--yes'])('anything'))
        for value in (1, 'true', None):
            (self.root/'preferences.json').write_text(json.dumps({'schema': 1, 'require_menu_approval': value}))
            self.assertFalse(menu_approval.enabled())

    def test_on_ignores_yes_and_terminal(self):
        from haejo import cli
        self.turn_on()
        confirm = cli._confirmer(['--yes'])
        self.assertIsInstance(confirm, menu_approval.RuntimeConfirm)
        # No menu app: the answer is no, named, and nothing raises.
        self.assertFalse(confirm('메시지를 전송합니다'))
        self.assertEqual('approval_unavailable', confirm.last_outcome)

    def test_plan_pending_reports_resume_and_claims_nothing(self):
        fake = self.menu('pending')
        approvals, blocked, outcome = menu_approval.plan(flow(), Agent(driver=None))
        self.assertEqual([], blocked)
        self.assertEqual({'type': 'approval_pending', 'effect': 'not_started', 'approval_id': 'ap_test0001',
                          'resume': '--approval ap_test0001'}, outcome)
        self.assertEqual(['plan'], [c['op'] for c in fake.calls])
        item = fake.calls[0]['request']['items'][0]
        self.assertEqual((1, ['transmit'], 'slack:#team', 'message'),
                         (item['step'], item['effects'], item['destination'], item['object_type']))
        self.assertTrue(item['payload_digest'])

    def test_allowed_plan_claims_one_run_and_spends_each_step_once(self):
        fake = self.menu('allowed')
        f = flow()
        approvals, blocked, outcome = menu_approval.plan(f, Agent(driver=None))
        self.assertIsNone(outcome)
        token = approvals[1]
        self.assertIsInstance(token, menu_approval.MenuApprovalToken)
        self.assertNotIn(0, approvals)          # the draft step needs no approval
        ok, _ = token.authorizes(f.steps[1].binding, f.steps[1].safety)
        self.assertTrue(ok)
        token._spent = False                    # even a reused local token cannot spend twice
        ok, why = token.authorizes(f.steps[1].binding, f.steps[1].safety)
        self.assertFalse(ok); self.assertEqual('approval_consumed', why)
        # The same approval id run again is refused before any step.
        again = menu_approval.plan(flow(), Agent(driver=None), approval_id='ap_test0001')[2]
        self.assertEqual('approval_claimed', again['type'])

    def test_flow_without_confirm_steps_never_asks_the_menu(self):
        fake = self.menu('denied')
        approvals, blocked, outcome = menu_approval.plan(flow(with_send=False), Agent(driver=None))
        self.assertIsNone(outcome); self.assertEqual([], fake.calls)

    def test_denied_and_unavailable_are_typed(self):
        self.menu('denied')
        self.assertEqual('approval_denied', menu_approval.plan(flow(), Agent(driver=None))[2]['type'])

    def test_unavailable_menu_does_not_fall_back(self):
        outcome = menu_approval.plan(flow(), Agent(driver=None))[2]
        self.assertEqual('approval_unavailable', outcome['type'])
        self.assertEqual('not_started', outcome['effect'])

    def test_run_prints_pending_and_exits_4_before_any_input(self):
        from haejo import cli
        self.turn_on(); self.menu('pending')
        driver = mock.MagicMock()
        out = io.StringIO()
        with redirect_stdout(out), mock.patch.object(Agent, 'commit_adapter_for', side_effect=AssertionError('no run')):
            code = cli._run_flow(flow(), ['--helper', '--yes'], _driver=driver)
        self.assertEqual(4, code)
        self.assertEqual('approval_pending', json.loads(out.getvalue().strip().splitlines()[-1])['type'])
        self.assertFalse(driver.act.called)

    def test_approval_option_parsing(self):
        self.assertEqual((['x'], 'ap_1'), menu_approval.take_approval_arg(['x', '--approval', 'ap_1']))
        self.assertEqual((['x'], None), menu_approval.take_approval_arg(['x']))
        for bad in (['--approval'], ['--approval', 'nope'], ['--approval', 'ap_1', '--approval', 'ap_2']):
            with self.assertRaises(ValueError):
                menu_approval.take_approval_arg(bad)

    def test_approval_option_needs_the_setting(self):
        from haejo import cli
        out = io.StringIO()
        with redirect_stdout(out):
            code = cli._run_flow(flow(), ['--approval', 'ap_1'], _driver=mock.MagicMock())
        self.assertEqual(2, code); self.assertIn('approval_not_enabled', out.getvalue())

    def test_runtime_confirm_names_the_outcome(self):
        self.menu('denied')
        confirm = menu_approval.RuntimeConfirm('com.example.Chat', wait=5)
        f = flow()
        self.assertFalse(confirm.request(f.steps[1], '메시지를 전송합니다', 1))
        self.assertEqual('approval_denied', confirm.last_outcome)

    def test_runtime_item_carries_live_credential_effect(self):
        fake = self.menu('denied')
        confirm = menu_approval.RuntimeConfirm('com.example.Chat', wait=5)
        f = flow()
        confirm.request(f.steps[0], '요청한 입력란에 자격 증명을 입력합니다', 0, effects=['write_ephemeral', 'credential'])
        self.assertEqual(['credential', 'write_ephemeral'], fake.calls[-1]['item']['effects'])

    def test_request_digest_covers_contract_and_recipient(self):
        f1, f2 = flow(), flow()
        f2.steps[1].safety.destination.identity = 'slack:#other'
        self.assertNotEqual(menu_approval.request_for(f1, [])['flow_digest'],
                            menu_approval.request_for(f2, [])['flow_digest'])
        f3 = flow(); f3.steps[1].safety.effects.append('financial')
        self.assertNotEqual(menu_approval.request_for(f1, [])['flow_digest'],
                            menu_approval.request_for(f3, [])['flow_digest'])

    def test_do_keeps_the_menu_confirm_and_its_outcome(self):
        text = (Path(__file__).resolve().parents[1]/'haejo/agent.py').read_text()
        self.assertIn('confirm=ask if menu else', text)
        self.assertIn('menu_plan(flow, self, approval_id=approval_id)', text)

    def test_do_consumes_options_and_prints_one_json_outcome(self):
        from contextlib import nullcontext
        from haejo import cli
        from haejo.agent import Turn
        self.turn_on()
        seen = {}
        outcome = {'type': 'approval_pending', 'approval_id': 'ap_x', 'effect': 'not_started'}

        def handle(agent, intent, **kw):
            seen['intent'] = intent; seen['approval_id'] = kw.get('approval_id')
            print('  🗣  두 단계 작업을 시작합니다')      # narration during the run
            return Turn('needs_confirm', json.dumps(outcome), 'f', detail=outcome)
        out, err = io.StringIO(), io.StringIO()
        from contextlib import redirect_stderr
        with redirect_stdout(out), redirect_stderr(err), mock.patch.object(cli, '_make_driver', return_value=mock.MagicMock()), \
                mock.patch.object(cli, '_indicator_for', return_value=nullcontext()), \
                mock.patch('haejo.onboard.run', return_value=True), \
                mock.patch.object(Agent, 'handle', handle):
            # The permission gate reads this Mac's real grants; a checkout with a
            # built, unpermitted helper would stop here before the code under test.
            code = cli._dispatch_command('do', ['save this', '--strict', '--think', '0', '--json', '--approval', 'ap_x'])
        self.assertEqual(4, code)
        self.assertEqual('save this', seen['intent']); self.assertEqual('ap_x', seen['approval_id'])
        # stdout is exactly one JSON object; the narration went to stderr.
        self.assertEqual(outcome, json.loads(out.getvalue()))
        self.assertIn('두 단계 작업을 시작합니다', err.getvalue())

    def test_batch_and_repair_yes_go_through_the_menu_when_on(self):
        root = Path(__file__).resolve().parents[1]/'haejo'
        for name in ('flow_batch.py', 'auto_repair.py'):
            self.assertIn('_confirm=None if menu_enabled() else (lambda description:approved)', (root/name).read_text())

    def test_runtime_points_record_typed_outcomes(self):
        text = (Path(__file__).resolve().parents[1]/'haejo/flow.py').read_text()
        self.assertIn('gate=menu_outcome, action_effect="not_started"', text)
        self.assertIn('{"type": "approval_refused", "gate": confirm.last_outcome or "approval_denied"', text)
        self.assertIn('{"type": "approval_refused", "gate": menu_refusal', text)
        self.assertEqual(2, text.count('if r["type"] == "approval_refused":'))


if __name__ == '__main__':
    unittest.main()
