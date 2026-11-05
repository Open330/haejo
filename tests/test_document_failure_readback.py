"""Unknown edits yield fresh visible state, without replay or save claims."""
import copy
import json
import unittest
from unittest.mock import Mock
from tacto.document_scope import DocumentScopedDriver
from tacto.document_readback import failure_readback
from tacto.flow import Flow, ReplayResult
from tests import test_document_session as sessions
PATH, TARGET = sessions.PATH, sessions.TARGET


class FailureReadbackTests(unittest.TestCase):
    def make(self, text='A😀한글'):
        helper=sessions.DocumentSessionTests();inner=helper.inner()
        driver=DocumentScopedDriver(inner,TARGET,PATH)
        inner.document_text.reset_mock()
        inner.document_text.return_value={**inner.document_text.return_value,'text':text}
        flow=Flow.from_json(json.dumps({'name':'edit','target':TARGET,'steps':[{
            'action':'set_value','selector':{'role':'TextArea','identifier':'First Text View'},
            'params':{'value':text},'safety':{'effects':['write_persistent']}}]}))
        result=ReplayResult()
        result.events=[{'event_id':'event','target':TARGET,'state':'dispatched','action':{'name':'set_value','value':text}}]
        result.record(status='unverified',error='commit_unverified',step=0,event_id='event')
        return inner,driver,flow,result

    def test_reads_once_on_same_pin_without_disclosing_text_or_changing_failure(self):
        inner,driver,flow,result=self.make('PRIVATE😀한글')
        before=copy.deepcopy((result.log,result.events,result.commit_evidence))
        report=failure_readback(driver,flow,result)
        self.assertTrue(report['matches_requested_text'])
        self.assertFalse(report['save_verified']);self.assertFalse(report['dispatch_confirmed'])
        self.assertFalse(report['write_retried']);self.assertEqual(0,report['remaining_steps'])
        self.assertNotIn('PRIVATE',json.dumps(report));self.assertNotIn('pin',json.dumps(report))
        self.assertFalse(result.ok);self.assertEqual(before,(result.log,result.events,result.commit_evidence))
        inner.document_text.assert_called_once_with(TARGET,document_token='pin',max_utf16_units=12)
        inner.act.assert_not_called();inner.observe.assert_called_once()  # initial pin only

    def test_mismatch_is_false_and_remaining_work_is_not_lost(self):
        inner,driver,flow,result=self.make()
        flow.steps.append(copy.deepcopy(flow.steps[0]))
        inner.document_text.return_value['text']='different'
        report=failure_readback(driver,flow,result)
        self.assertFalse(report['matches_requested_text']);self.assertEqual(1,report['remaining_steps'])
        self.assertEqual(1,inner.document_text.call_count);inner.act.assert_not_called()

    def test_read_errors_incomplete_snapshots_and_token_loss_are_unknown_without_repin(self):
        for change in ({'type':'error'},{'document_token':'different'},
                       {'text_complete':False},{'document_path':'/other.txt'}):
            inner,driver,flow,result=self.make()
            inner.document_text.return_value.update(change)
            report=failure_readback(driver,flow,result)
            self.assertIsNone(report['matches_requested_text']);self.assertEqual('readback_unavailable',report['reason'])
            inner.document_text.assert_called_once();inner.act.assert_not_called()
        inner,driver,flow,result=self.make();inner.document_text.side_effect=ValueError('PRIVATE')
        self.assertNotIn('PRIVATE',json.dumps(failure_readback(driver,flow,result)))

    def test_unrelated_or_sensitive_failures_do_not_read(self):
        for change in ('ok','not_dispatched','menu','secret','other_effect','other_body','other_event','absent_action'):
            inner,driver,flow,result=self.make()
            if change=='ok':result.ok=True
            elif change=='not_dispatched':result.log[-1]['error']='target_not_found'
            elif change=='menu':flow.steps[0].action='menu'
            elif change=='secret':flow.steps[0].into_sensitive_field=True
            elif change=='other_effect':flow.steps[0].safety.effects.append('transmit')
            elif change=='other_body':flow.steps[0].selector.identifier='other'
            elif change=='other_event':result.events[0]['action']['value']='other'
            elif change=='absent_action':result.events[0]['action']=None
            self.assertIsNone(failure_readback(driver,flow,result),change)
            inner.document_text.assert_not_called();inner.act.assert_not_called()
        inner,driver,flow,result=self.make()
        self.assertIsNone(failure_readback(inner,flow,result))  # unscoped backend
