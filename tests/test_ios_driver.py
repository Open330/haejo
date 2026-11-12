"""Transport fixtures only: these results do not attest a physical iPhone."""
try:
    from tests import _isolation  # noqa: F401
except ImportError:  # discovered with tests/ as the top level
    import _isolation  # noqa: F401
from dataclasses import replace
import io
import json
from contextlib import redirect_stdout
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from haejo.flow import Flow
from haejo.ios_driver import IOSDriver, IOSNode, IOSSnapshot, ScreenProgressClock, run_ios_spike, parse_target

TARGET='ios://00000000-0000000000000000/com.example.OwnedCounter'
DEVICE,APP=parse_target(TARGET)


class Clock:
    def __init__(self):self.now=0
    def __call__(self):return self.now
    def sleep(self,seconds):self.now+=seconds


class Session:
    def __init__(self,mode='success'):
        self.value=0;self.taps=0;self.reads=0;self.closed=False;self.mode=mode;self.override={}
    def read_snapshot(self):
        assert not self.closed
        self.reads+=1
        return IOSSnapshot(DEVICE,APP,'connection-1','portrait',(390,844),(
            IOSNode('button','Button','increment','Increment','',(20,50,80,40),hittable=True),
            IOSNode('counter','StaticText','counter','Counter',str(self.value),(20,120,80,40))),
            input_ready=True,modal_present=False,**self.override)
    def tap_once(self,x,y):
        assert not self.closed
        self.taps+=1;self.point=(x,y)
        if self.mode=='lost_reply':self.value+=1;raise OSError('PRIVATE_DEVICE_PAYLOAD')
        if self.mode=='not_started':return False
        if self.mode=='partial':return None
        if self.mode=='success':self.value+=1
        return True
    def close(self):self.closed=True


def flow(expected='1'):
    return Flow.from_json(json.dumps({'schema':2,'name':'owned-counter','target':TARGET,'steps':[
        {'action':'click','selector':{'identifier':'increment'},
         'safety':{'effects':['write_ephemeral'],'reversibility':'reversible',
                   'resource':{'object_type':'fixture counter','scope':'entry'}},
         'postcondition':{'field':{'identifier':'counter'},'attribute':'Value','equals':expected}}]}))


class IOSDriverTests(unittest.TestCase):
    def driver(self,session=None,**kwargs):
        session=session or Session();clock=Clock()
        return IOSDriver(TARGET,session,clock=clock,sleep=clock.sleep,**kwargs),session,clock

    def test_existing_flow_replays_and_verifies_one_tap_on_same_open_session(self):
        session=Session();clock=Clock()
        report=run_ios_spike(flow(),session,authorize_tap=lambda target,node:True,clock=clock,sleep=clock.sleep)
        self.assertTrue(report['ok'],report);self.assertEqual(1,session.taps)
        self.assertGreaterEqual(session.reads,3);self.assertTrue(session.closed)
        receipt=report['receipts'][0]
        self.assertEqual((True,True,True),(receipt['sent'],receipt['screen_changed'],receipt['screen_change_verified']))
        self.assertEqual((None,0,None),(report['failed_step'],report['remaining_steps'],report['next']))

    def test_host_send_is_not_receiving_proof_and_no_change_never_retries(self):
        session=Session('drop');clock=Clock()
        report=run_ios_spike(flow(),session,authorize_tap=lambda *args:True,clock=clock,sleep=clock.sleep)
        self.assertFalse(report['ok']);self.assertEqual(1,session.taps)
        receipt=report['receipts'][0]
        self.assertEqual((True,False,False),(receipt['sent'],receipt['screen_changed'],receipt['screen_change_verified']))
        self.assertEqual(0,report['failed_step']);self.assertEqual(1,report['remaining_steps'])
        self.assertFalse(report['next']['automatic_resume'])

    def test_unknown_dispatch_is_sticky_even_after_screen_matches(self):
        for mode in ('lost_reply','partial'):
            driver,session,clock=self.driver(Session(mode),authorize_tap=lambda *a:True)
            obs=driver.observe(TARGET)
            reply=driver.act(obs['obs_id'],TARGET,{'name':'click','element_index':1})
            self.assertEqual('unknown',reply['effect']);self.assertNotIn('PRIVATE',str(reply))
            seen=driver.observe(TARGET)
            self.assertEqual('ios_input_unresolved',driver.act(seen['obs_id'],TARGET,{'name':'click','element_index':1})['error'])
            self.assertEqual('ios_dispatch_unknown',driver.wait_until(TARGET,lambda tree:True)['error'])
            self.assertEqual(1,session.taps)

    def test_unrelated_screen_change_is_not_the_requested_result(self):
        session=Session();clock=Clock()
        report=run_ios_spike(flow('2'),session,authorize_tap=lambda *a:True,clock=clock,sleep=clock.sleep)
        self.assertFalse(report['ok']);self.assertEqual(1,session.taps)
        self.assertEqual((True,True,False),tuple(report['receipts'][0][key] for key in ('sent','screen_changed','screen_change_verified')))

    def test_preexisting_postcondition_does_not_verify_ignored_tap(self):
        session=Session('drop');clock=Clock()
        result=run_ios_spike(flow('0'),session,authorize_tap=lambda *a:True,clock=clock,sleep=clock.sleep)
        self.assertFalse(result['ok']);self.assertEqual([],result['receipts'])
        self.assertEqual(0,session.taps)

    def test_no_implicit_input_permission_and_stale_indices_are_refused(self):
        driver,session,_=self.driver();obs=driver.observe(TARGET)
        self.assertEqual('ios_tap_not_authorized',driver.act(obs['obs_id'],TARGET,{'name':'click','element_index':1})['error'])
        driver.observe(TARGET)
        self.assertEqual('stale_observation',driver.act(obs['obs_id'],TARGET,{'name':'click','element_index':1})['error'])
        self.assertEqual(0,session.taps)

    def test_backend_exception_text_is_never_a_public_error_code(self):
        driver,session,_=self.driver()
        session.read_snapshot=Mock(side_effect=ValueError('ios_PRIVATE_PERSONAL_DATA'))
        self.assertEqual('ios_snapshot_unavailable',driver.observe(TARGET)['error'])

    def test_failed_observation_invalidates_old_read_and_click_indices(self):
        driver,session,_=self.driver(authorize_tap=lambda *a:True)
        old=driver.observe(TARGET)
        session.read_snapshot=Mock(side_effect=OSError('PRIVATE'))
        self.assertEqual('error',driver.observe(TARGET)['type'])
        for name in ('read','click'):
            self.assertEqual('stale_observation',driver.act(old['obs_id'],TARGET,{'name':name,'element_index':1})['error'])
        self.assertEqual(0,session.taps)

    def test_close_and_cancellation_block_reads_from_previous_observation(self):
        for close in (False,True):
            stopped=[False]
            driver,session,_=self.driver(cancelled=lambda:stopped[0])
            old=driver.observe(TARGET)
            if close:driver.close()
            else:stopped[0]=True
            self.assertEqual('ios_session_stopped',driver.act(old['obs_id'],TARGET,{'name':'read','element_index':1})['error'])

    def test_handle_and_enumeration_churn_are_not_screen_progress(self):
        driver,session,clock=self.driver();original=session.read_snapshot
        def churn():
            snap=original()
            nodes=tuple(replace(n,handle=n.handle+str(session.reads),identifier=n.identifier+str(session.reads)) for n in snap.nodes)
            return replace(snap,nodes=nodes if session.reads%2 else tuple(reversed(nodes)))
        session.read_snapshot=churn
        first=driver.observe(TARGET)
        clock.sleep(6);second=driver.observe(TARGET)
        self.assertEqual(first['screen_fingerprint'],second['screen_fingerprint'])
        clock.sleep(5)
        self.assertEqual('ios_screen_stalled',driver.observe(TARGET)['error'])

    def test_changed_handle_cannot_be_used_for_tap_even_when_screen_matches(self):
        driver,session,_=self.driver(authorize_tap=lambda *a:True)
        old=driver.observe(TARGET);original=session.read_snapshot
        def changed():
            snap=original()
            return replace(snap,nodes=tuple(replace(n,handle=n.handle+'new') for n in snap.nodes))
        session.read_snapshot=changed
        self.assertEqual('ios_input_identity_changed',driver.act(old['obs_id'],TARGET,{'name':'click','element_index':1})['error'])
        self.assertEqual(0,session.taps)

    def test_authorization_cannot_replace_the_original_observation_binding(self):
        driver,session,_=self.driver()
        def authorize(*args):
            session.value=4
            driver.observe(TARGET)
            return True
        driver.authorize_tap=authorize
        old=driver.observe(TARGET)
        self.assertEqual('stale_observation',driver.act(old['obs_id'],TARGET,{'name':'click','element_index':1})['error'])
        self.assertEqual(0,session.taps)

    def test_cleanup_failure_keeps_verified_receipt_and_stops_overall_success(self):
        session=Session();session.close=Mock(side_effect=OSError('PRIVATE_CLEANUP_ERROR'))
        clock=Clock()
        report=run_ios_spike(flow(),session,authorize_tap=lambda *a:True,clock=clock,sleep=clock.sleep)
        self.assertFalse(report['ok']);self.assertFalse(report['session_closed'])
        self.assertEqual('ios_session_close_failed',report['cleanup_error'])
        self.assertTrue(report['receipts'][0]['screen_change_verified'])
        self.assertFalse(report['next']['automatic_resume']);self.assertNotIn('PRIVATE',str(report))
        self.assertEqual(1,session.taps)

    def test_target_connection_orientation_lock_and_malformed_tree_are_closed(self):
        changes=[{'device_id':'different'},{'bundle_id':'com.other.App'},{'orientation':'landscape'},
                 {'locked':True},{'nodes':()},{'viewport':(float('nan'),844)}]
        for changeset in changes:
            driver,session,_=self.driver(authorize_tap=lambda *a:True)
            original=session.read_snapshot
            session.read_snapshot=lambda:replace(original(),**changeset)
            self.assertEqual('error',driver.observe(TARGET)['type']);self.assertEqual(0,session.taps)
        driver,session,_=self.driver(authorize_tap=lambda *a:True);driver.observe(TARGET)
        original=session.read_snapshot;session.read_snapshot=lambda:replace(original(),connection_id='reconnected')
        self.assertEqual('ios_connection_changed',driver.observe(TARGET)['error'])

    def test_fresh_target_is_rechecked_after_authorization(self):
        session=Session()
        def authorize(*args):session.value=4;return True
        driver,session,_=self.driver(session,authorize_tap=authorize);obs=driver.observe(TARGET)
        self.assertEqual('ios_screen_changed_before_tap',driver.act(obs['obs_id'],TARGET,{'name':'click','element_index':1})['error'])
        self.assertEqual(0,session.taps)

    def test_cancel_before_or_during_final_snapshot_prevents_input(self):
        stopped=[False]
        driver,session,_=self.driver(authorize_tap=lambda *a:True,cancelled=lambda:stopped[0])
        observed=driver.observe(TARGET);original=session.read_snapshot
        def read_and_stop():
            snap=original();stopped[0]=True;return snap
        session.read_snapshot=read_and_stop
        self.assertEqual('ios_preflight_unavailable',driver.act(observed['obs_id'],TARGET,{'name':'click','element_index':1})['error'])
        self.assertEqual(0,session.taps)
        stopped=[False]
        def stop(*args):stopped[0]=True;return True
        driver,session,_=self.driver(authorize_tap=stop,cancelled=lambda:stopped[0]);obs=driver.observe(TARGET)
        self.assertEqual('ios_preflight_unavailable',driver.act(obs['obs_id'],TARGET,{'name':'click','element_index':1})['error'])
        self.assertEqual(0,session.taps)

    def test_journal_refuses_second_worker_after_lost_touch_reply(self):
        from haejo.dispatch_journal import DurableDispatchDriver
        with tempfile.TemporaryDirectory() as directory:
            session=Session('lost_reply');driver,_,_=self.driver(session,authorize_tap=lambda *a:True)
            with DurableDispatchDriver(driver,directory) as guarded:
                obs=driver.observe(TARGET);first=guarded.act(obs['obs_id'],TARGET,{'name':'click','element_index':1})
            self.assertEqual('unknown',first['effect'])
            replacement,_,_=self.driver(session,authorize_tap=lambda *a:True)
            with DurableDispatchDriver(replacement,directory) as guarded:
                obs=replacement.observe(TARGET);second=guarded.act(obs['obs_id'],TARGET,{'name':'click','element_index':1})
            self.assertEqual('not_started',second['effect']);self.assertEqual(1,session.taps)

    def test_protocol_never_accepts_arbitrary_unverified_click(self):
        from haejo.protocol import ios_tap_reobservation
        driver,session,_=self.driver(authorize_tap=lambda *a:True);obs=driver.observe(TARGET)
        action={'name':'click','element_index':1};reply=driver.act(obs['obs_id'],TARGET,action)
        self.assertTrue(ios_tap_reobservation(action,reply,driver.capabilities,target=TARGET))
        for changed in ({'sent':False},{'screen_change_verified':True},{'input_route':'native_mouse'},{'reobserve_required':False}):
            self.assertFalse(ios_tap_reobservation(action,{**reply,**changed},driver.capabilities,target=TARGET))
        self.assertFalse(ios_tap_reobservation(action,reply,set(),target=TARGET))
        self.assertFalse(ios_tap_reobservation(action,reply,driver.capabilities,target='com.apple.finder'))

    def test_cli_never_falls_back_to_a_mac_driver_for_ios(self):
        from haejo.cli import _run_flow,main
        with patch('haejo.cli._make_driver') as make,redirect_stdout(io.StringIO()) as output:
            self.assertEqual(2,_run_flow(flow(),['--helper']))
            self.assertEqual(2,main(['observe',TARGET,'--helper']))
        make.assert_not_called();self.assertNotIn('PRIVATE',output.getvalue())

    def test_clock_only_resets_when_fingerprint_changes(self):
        clock=Clock();progress=ScreenProgressClock(clock)
        self.assertEqual(0,progress.observe('page-a'))
        clock.sleep(5);self.assertEqual(5,progress.observe('page-a'))
        clock.sleep(3);self.assertEqual(0,progress.observe('page-b'))
        clock.now=1
        with self.assertRaises(ValueError):progress.observe('page-b')

    def test_reobserving_same_page_does_not_extend_its_budget(self):
        driver,session,clock=self.driver()
        self.assertEqual('observation',driver.observe(TARGET)['type'])
        clock.sleep(6);self.assertEqual('observation',driver.observe(TARGET)['type'])
        clock.sleep(5);self.assertEqual('ios_screen_stalled',driver.observe(TARGET)['error'])
        session.value=1
        self.assertEqual('observation',driver.observe(TARGET)['type'])

    def test_unsupported_flow_fails_before_any_transport_access(self):
        recipe=flow();recipe.steps[0].action='type_text'
        session=Session()
        with self.assertRaises(ValueError):run_ios_spike(recipe,session)
        self.assertEqual(0,session.reads);self.assertEqual(0,session.taps)
