"""A bound authoring message expands to the same executable Flow, not extra authority."""
import json,unittest,tempfile
from pathlib import Path
from tacto.flow import Flow
from tacto.flow_session import decode_session_flow
from tacto.command_help import session_guide,session_defaults
from tests.test_document_session import DocumentSessionTests,TARGET,PATH

class BoundStepsTests(unittest.TestCase):
    def test_calculator_matches_full_guide_defaults_and_explicit_checks(self):
        full=json.loads(session_guide('com.apple.calculator').splitlines()[1])
        steps=[{'click':'Two','equals':'2'},{'click':'Equals','equals':'2','answers':True}]
        full['steps']=steps
        actual=decode_session_flow(json.dumps({'steps':steps}),'com.apple.calculator',steps=True)
        self.assertEqual(Flow.from_json(json.dumps(full)),actual)
        self.assertEqual(actual,Flow.from_json(actual.to_json()))
    def test_no_checks_or_consent_are_invented(self):
        flow=decode_session_flow('{"steps":[{"click":"Two"}]}','com.apple.calculator',steps=True)
        self.assertIsNone(flow.steps[0].postcondition)
        self.assertFalse(flow.steps[0].safety.evidence)
        self.assertEqual({'write_ephemeral'},set(flow.steps[0].safety.effects))
    def test_other_apps_get_only_structural_header_and_explicit_steps(self):
        self.assertEqual({'schema':2,'name':'task','target':'com.example.app'},session_defaults('com.example.app'))
        actual=decode_session_flow('{"steps":[{"action":"read","selector":{"identifier":"body"}}]}','com.example.app',steps=True)
        self.assertEqual('body',actual.steps[0].selector.identifier)
    def test_headerless_requires_flag_and_full_flow_stays_unchanged(self):
        with self.assertRaises(ValueError):decode_session_flow('{"steps":[{"click":"Two"}]}','com.apple.calculator')
        full={'schema':2,'name':'owned','target':'com.example.app','steps':[{'action':'read'}]}
        self.assertEqual(Flow.from_json(json.dumps(full)),decode_session_flow(json.dumps(full),'com.example.app',steps=True))
        with self.assertRaises(ValueError):decode_session_flow('{"steps":[],"target":"other"}','com.apple.calculator',steps=True)
    def test_document_read_stays_inside_pin(self):
        helper=DocumentSessionTests();inner=helper.inner()
        step={'action':'read','postcondition':{'equals':'owned'}}
        code,_,messages=helper.run_session(inner,args=[TARGET,'--helper','--document',PATH,'--guide','--steps'],doc={'steps':[step]})
        self.assertEqual(0,code)
        for call in inner.observe.call_args_list:self.assertEqual('pin',call.kwargs['document_token'])
        self.assertEqual('read',inner.act.call_args.args[2]['name'])
    def test_save_expands_structure_and_reloads_with_same_meaning(self):
        helper=DocumentSessionTests();inner=helper.inner()
        payload={'steps':[{'action':'read','postcondition':{'equals':'owned'}}]}
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'flow.json'
            code,_,_=helper.run_session(inner,args=[TARGET,'--helper','--document',PATH,'--steps','--save',str(path)],doc=payload)
            self.assertEqual(0,code)
            self.assertEqual(decode_session_flow(json.dumps(payload),TARGET,PATH,steps=True),Flow.from_json(path.read_text()))
    def test_literals_and_parameter_rules_are_the_full_flow_rules(self):
        payload={'steps':[{'action':'read','postcondition':{'field':{'identifier':'body'},'equals':'line\\n한글'}}]}
        full={**session_defaults('com.example.app'),**payload}
        self.assertEqual(Flow.from_json(json.dumps(full)),decode_session_flow(json.dumps(payload),'com.example.app',steps=True))
    def test_unknown_or_nonlist_steps_do_not_dispatch(self):
        helper=DocumentSessionTests()
        for payload in ({'steps':'bad'},{'steps':[{'action':'unknown'}]}):
            inner=helper.inner()
            code,_,_=helper.run_session(inner,args=[TARGET,'--helper','--document',PATH,'--steps'],doc=payload)
            self.assertNotEqual(0,code);inner.act.assert_not_called()

    def test_document_write_still_requires_explicit_effects_and_evidence(self):
        helper=DocumentSessionTests();inner=helper.inner()
        code,_,_=helper.run_session(inner,args=[TARGET,'--helper','--document',PATH,'--steps'],
                                   doc={'steps':[{'set_value':'changed','check_value':True}]})
        self.assertNotEqual(0,code);inner.act.assert_not_called()

    def test_reuse_guide_keeps_full_parameterizable_template(self):
        guide=session_guide('com.apple.calculator',steps=True,reusable=True)
        template=json.loads(guide.splitlines()[1])
        self.assertIn('target',template);self.assertIn('safety_defaults',template)

    def test_reuse_flow_with_params_and_schema_three_is_not_rebound(self):
        full={'schema':3,'name':'reuse','target':'com.example.app','params':{'text':'owned'},
              'steps':[{'action':'read','postcondition':{'all_of':[{'field':{'identifier':'body'},'attribute':'Value','equals':'{{text}}'}]}}]}
        self.assertEqual(Flow.from_json(json.dumps(full)),decode_session_flow(json.dumps(full),'com.example.app',steps=True))
