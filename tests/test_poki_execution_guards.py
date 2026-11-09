"""Promotion context/intervention and content-free batch interruption evidence."""
from copy import deepcopy
import json
import tempfile
from types import SimpleNamespace
import unittest

from haejo.promote import Candidate,CandidateStore,candidate_from,gate,route_key,to_flow
from haejo.execution_summary import interruption_summary
from haejo.flow import ReplayResult


def candidate():
    return Candidate(goal='click 1',target='com.apple.calculator',verified=True,
        target_identity='fixture-v1',screens=['initial','done'],actions=[
            {'do':'click','attr':'Identifier','match':'One','role':'Button','label':'1','expect':'1'}])


class PromotionGuardTests(unittest.TestCase):
    def test_human_assisted_walk_never_becomes_a_candidate(self):
        result=SimpleNamespace(ok=True,verified=True,human_intervened=True)
        self.assertIsNone(candidate_from(result,'com.example.App','goal'))
        c=candidate();c.human_intervened=True
        self.assertTrue(any('사람 개입' in reason for reason in gate(c,to_flow(c,'example'),'click 1')))

    def test_request_and_initial_context_must_match_for_repeat_count(self):
        with tempfile.TemporaryDirectory() as directory:
            store=CandidateStore(directory);c=candidate();c.initial_constraints={'orientation':'portrait','app_version':'1'}
            first=store.record(c,'request exactly','route')
            second=store.record(c,'request exactly','route')
            self.assertEqual(2,second['runs']);self.assertEqual(first['route_key'],second['route_key'])
            changed_request=store.record(c,'request exactly ','route')
            self.assertEqual(1,changed_request['runs']);self.assertNotEqual(second['route_key'],changed_request['route_key'])
            c.initial_constraints['app_version']='2'
            changed_context=store.record(c,'request exactly ','route')
            self.assertEqual(1,changed_context['runs']);self.assertNotEqual(changed_request['route_key'],changed_context['route_key'])
            self.assertEqual({'orientation':'portrait','app_version':'2'},changed_context['candidate']['initial_constraints'])

    def test_route_context_is_json_and_key_order_is_not_a_constraint(self):
        self.assertEqual(route_key('r','t','v',{'a':1,'b':2}),route_key('r','t','v',{'b':2,'a':1}))
        self.assertNotEqual(route_key('r','t','v',{}),route_key('r','other','v',{}))
        first=candidate();second=candidate()
        first.initial_constraints={'mode':False};second.initial_constraints={'mode':0}
        self.assertFalse(first.same_path_as(second))
        for context in ({'bad':float('nan')},{'bad':object()},[]):
            with self.assertRaises(ValueError):route_key('r','t','v',context)

    def test_intervention_flag_survives_persistence_and_blocks_manual_candidates(self):
        with tempfile.TemporaryDirectory() as directory:
            c=candidate();c.human_intervened=True
            record=CandidateStore(directory).record(c,'click 1','assisted')
            self.assertTrue(record['candidate']['human_intervened'])
            self.assertTrue(any('사람 개입' in reason for reason in record['blocked_by']))


class InterruptionTests(unittest.TestCase):
    def test_failed_step_remaining_and_next_never_authorize_resume(self):
        result=ReplayResult();result.record(status='ok',step=0)
        result.record(status='error',step=1,error='postcondition_timeout',detail='PRIVATE_APP_TEXT')
        summary=interruption_summary(result,4)
        self.assertEqual(1,summary['failed_step']);self.assertEqual(3,summary['remaining_steps'])
        self.assertEqual({'action':'inspect_receiving_state','automatic_resume':False},summary['next'])
        self.assertNotIn('PRIVATE',json.dumps(summary))
        self.assertIsNone(interruption_summary(None,4)['failed_step'])
        self.assertIsNone(interruption_summary(None,4)['remaining_steps'])
        mapped=interruption_summary(result,10,step_offset=5)
        self.assertEqual((6,4),(mapped['failed_step'],mapped['remaining_steps']))

    def test_success_has_no_remaining_or_next(self):
        result=ReplayResult()
        self.assertEqual({'failed_step':None,'remaining_steps':0,'next':None},interruption_summary(result,2))
        self.assertFalse(interruption_summary(result,2,failed=True)['next']['automatic_resume'])
