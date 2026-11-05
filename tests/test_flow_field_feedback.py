"""Actionable parser errors with private payloads never reflected in hints."""
import copy
import json
import unittest
from tacto.command_help import calculator_example
from tacto.flow import Flow
from tacto.flow_errors import feedback


class FieldFeedbackTests(unittest.TestCase):
    def assert_feedback(self, step, field, hint):
        doc=calculator_example();doc['steps']=[step]
        with self.assertRaises(ValueError) as caught:
            Flow.from_json(json.dumps(doc),strict_checks=True)
        message=feedback(caught.exception)
        self.assertTrue(message.startswith('steps[0].'+field+':'),message)
        self.assertIn(hint,message)
        self.assertNotIn('PRIVATE',message)
        self.assertLess(len(message),250)
        return message

    def test_selector_locations_cover_nested_checks_and_wrong_types(self):
        base={'action':'read','selector':{'identifier':'result'}}
        self.assert_feedback({**base,'selector':{'description':'PRIVATE'}},'selector','desc, not description')
        self.assert_feedback({**base,'selector':{'identifier':{'PRIVATE':'PRIVATE'}}},'selector.identifier','nonempty text')
        self.assert_feedback({**base,'selector':{'identifier':'result','allow_nth':'PRIVATE'}},'selector.allow_nth','nonnegative integer')
        self.assert_feedback({**base,'selector':{'identifier':'result','in_focused_window':'PRIVATE'}},'selector.in_focused_window','true or false')
        for check in ('postcondition','skip_if'):
            self.assert_feedback({**base,check:{'field':'PRIVATE','equals':'PRIVATE'}},check+'.field','object')
            self.assert_feedback({**base,check:{'field':{'description':'PRIVATE'},'equals':'PRIVATE'}},check+'.field','desc, not description')
            self.assert_feedback({**base,check:{'all_of':[{'field':{'identifier':42},'equals':'PRIVATE'}]}},check+'.all_of[0].field.identifier','nonempty text')
            self.assert_feedback({**base,check:{'equals':['PRIVATE']}},check+'.equals','Use text')

    def test_constructor_fields_are_located_without_echoing_unknown_keys(self):
        base={'action':'read','selector':{'identifier':'result'}}
        for key in ('resource','destination'):
            self.assert_feedback({**base,'safety':{key:{'PRIVATE_KEY':'PRIVATE_VALUE'}}},'safety.'+key,'Allowed fields:')
        self.assert_feedback({**base,'safety':{'evidence':[{'source':'user_intent','PRIVATE_KEY':'PRIVATE_VALUE'}]}},'safety.evidence[0]','Required fields: source, field, value')
        self.assert_feedback({**base,'safety':{'evidence':[{'source':'user_intent','field':'asked','value':'PRIVATE','PRIVATE_KEY':'PRIVATE_VALUE'}]}},'safety.evidence[0]','Allowed fields:')
        self.assert_feedback({**base,'binding':{'PRIVATE_KEY':'PRIVATE_VALUE'}},'binding','Allowed fields include:')

    def test_scalar_and_selection_fields_have_short_corrections(self):
        base={'action':'read','selector':{'identifier':'result'}}
        for key in ('answers','is_submit','unverified_ok','require_enabled','into_sensitive_field'):
            self.assert_feedback({**base,key:'PRIVATE'},key,'true or false')
        self.assert_feedback({'action':'select_option','selector':{'identifier':'menu'},'params':{'option_label':42}},'params.option_label','option label as text')
        for key in ('resource','destination'):
            self.assert_feedback({**base,'safety':{key:'PRIVATE'}},'safety.'+key,'Use')

    def test_corrected_objects_keep_the_original_recipe_and_values(self):
        doc=calculator_example()
        doc['steps'][0]['safety']['evidence']=[{'source':'user_intent','field':'asked','value':'PRIVATE_VALUE','covers':['delete']}]
        before=copy.deepcopy(doc)
        flow=Flow.from_json(json.dumps(doc),strict_checks=True)
        self.assertEqual(before,doc)
        self.assertEqual('PRIVATE_VALUE',flow.steps[0].safety.evidence[0].value)
        self.assertEqual('entry',flow.steps[-1].safety.resource.scope)
