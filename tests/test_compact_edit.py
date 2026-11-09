"""Compact edits preserve explicit values, receiving checks and contracts."""
import copy,json,unittest
from haejo.flow import Flow
from haejo.flow_errors import feedback
from haejo.command_help import session_guide
from tests.test_document_session import DocumentSessionTests,TARGET,PATH

class CompactEditTests(unittest.TestCase):
    def document(self,value='A😀한글',**changes):
        return {'schema':2,'name':'edit','target':TARGET,
            'selector_defaults':{'role':'TextArea','identifier':'First Text View','ancestor':PATH},
            'check_defaults':{'field':{'role':'TextArea','identifier':'First Text View'},'attribute':'Value'},
            'steps':[{'set_value':value,'check_value':True,'safety':{'effects':['write_persistent'],
                     'resource':{'object_type':'document','scope':'item'},'reversibility':'reversible',
                     'evidence':[{'source':'user_intent','field':'asked','value':'Write the requested text',
                                  'covers':['write_persistent']}]},**changes}]}
    def parse(self,doc):return Flow.from_json(json.dumps(doc,ensure_ascii=False))
    def test_expands_to_exact_full_edit_and_serializes_without_aliases(self):
        for text in ('', 'A😀한글', '한글', 'line1\nline2'):
            doc=self.document(text);original=copy.deepcopy(doc);full=copy.deepcopy(doc)
            full['steps'][0].pop('set_value');full['steps'][0].pop('check_value')
            full['steps'][0].update(action='set_value',selector=doc['selector_defaults'],
                params={'value':text},postcondition={'field':doc['selector_defaults'],'attribute':'Value','equals':text})
            compact=self.parse(doc)
            self.assertEqual(self.parse(full),compact);self.assertEqual(original,doc)
            saved=json.loads(compact.to_json(compact=True))
            self.assertNotIn('check_value',saved['steps'][0])
            self.assertEqual(compact,Flow.from_json(json.dumps(saved)))
    def test_parameter_value_and_check_render_once_as_literal_data(self):
        doc=self.document('{{body}}');doc['params']={'body':'literal {{other}} 😀'}
        flow=self.parse(doc).bind(body='literal {{other}} 😀')
        self.assertEqual('literal {{other}} 😀',flow.steps[0].params['value'])
        self.assertEqual(flow.steps[0].params['value'],flow.steps[0].postcondition.equals)
    def test_explicit_selector_is_retained(self):
        flow=self.parse(self.document(selector={'identifier':'Another Text View'}))
        self.assertEqual('Another Text View',flow.steps[0].selector.identifier)
        self.assertEqual(PATH,flow.steps[0].selector.ancestor)
        self.assertEqual(flow.steps[0].selector,flow.steps[0].postcondition.field)
        self.assertEqual('Value',flow.steps[0].postcondition.attribute)
    def test_check_is_not_invented_when_omitted(self):
        doc=self.document();doc['steps'][0].pop('check_value')
        self.assertIsNone(self.parse(doc).steps[0].postcondition)
    def test_ambiguous_or_incomplete_forms_have_short_private_free_hints(self):
        changes=[{'action':'set_value'},{'params':{'value':'PRIVATE'}},{'click':'PRIVATE'},
                 {'equals':'PRIVATE'},{'check_value':False},{'check_value':1},
                 {'postcondition':{'equals':'PRIVATE'}},{'set_value':None}]
        for change in changes:
            with self.subTest(change=change):
                with self.assertRaises(ValueError) as caught:self.parse(self.document('PRIVATE',**change))
                message=feedback(caught.exception);self.assertNotIn('PRIVATE',message);self.assertLess(len(message),250)
        for missing in ('selector_defaults',):
            doc=self.document();del doc[missing]
            with self.assertRaises(ValueError):self.parse(doc)
    def test_sensitive_flag_and_evidence_remain_unchanged(self):
        doc=self.document(into_sensitive_field=True)
        flow=self.parse(doc);self.assertTrue(flow.steps[0].into_sensitive_field)
        self.assertEqual('Write the requested text',flow.steps[0].safety.evidence[0].value)
    def test_document_guide_edit_example_is_valid_json_and_has_one_body_value(self):
        guide=session_guide(TARGET,document=PATH)
        example=json.JSONDecoder().raw_decode(guide.split('For a requested edit send ONLY this step JSON on this pinned session (no Flow header): ',1)[1])[0]
        self.assertEqual(True,example['check_value']);self.assertEqual(1,json.dumps(example).count('<requested text>'))
        template=json.loads(guide.splitlines()[1]);template['steps']=[example]
        self.assertEqual('set_value',self.parse(template).steps[0].action)
    def test_scoped_replay_writes_once_and_keeps_body_only_verification(self):
        helper=DocumentSessionTests();inner=helper.inner();doc=self.document('changed')
        def receive(obs,target,action,**kwargs):
            inner.observe.return_value['tree']=inner.observe.return_value['tree'].replace('Value: owned','Value: changed')
            inner.document_text.return_value['text']='changed';return {'type':'acted'}
        inner.act.side_effect=receive
        code,_,messages=helper.run_session(inner,doc=doc)
        self.assertEqual(1,code);inner.act.assert_called_once()
        self.assertTrue(any(x.startswith('body_verified —') for x in messages))
        self.assertEqual(2,inner.document_text.call_count)

    def test_visible_completion_requires_no_pending_flow_save(self):
        from unittest.mock import patch
        from tempfile import TemporaryDirectory
        from pathlib import Path
        for save in (False, True):
            with self.subTest(save=save), TemporaryDirectory() as tmp:
                helper=DocumentSessionTests();inner=helper.inner();doc=self.document('changed')
                def receive(obs,target,action,**kwargs):
                    inner.observe.return_value['tree']=inner.observe.return_value['tree'].replace('Value: owned','Value: changed')
                    inner.document_text.return_value['text']='changed'
                    return {'type':'acted'}
                inner.act.side_effect=receive
                args=[TARGET,'--helper','--document',PATH,'--guide']
                saved=Path(tmp)/'flow.json'
                if save: args += ['--save',str(saved)]
                with patch('haejo.task.note_visible_document_result') as note:
                    code,_,messages=helper.run_session(inner,args=args,doc=doc)
                self.assertEqual(1,code)
                if save: note.assert_not_called()
                else: self.assertEqual(True,note.call_args.args[0]['matches_requested_text'])
                self.assertFalse(saved.exists())


class BoundEditSessionTests(unittest.TestCase):
    def test_single_step_uses_existing_scope_and_same_contract(self):
        from haejo.flow_session import decode_session_flow
        helper=CompactEditTests();step=helper.document()['steps'][0]
        flow=decode_session_flow(json.dumps(step),TARGET,PATH)
        expected=helper.parse(helper.document())
        self.assertEqual(expected.steps,flow.steps)
        self.assertEqual(TARGET,flow.target)
        self.assertNotIn('check_value',json.loads(flow.to_json())['steps'][0])
    def test_step_only_without_document_does_not_guess_a_target(self):
        from haejo.flow_session import decode_session_flow
        with self.assertRaises(ValueError) as caught:
            decode_session_flow('{"set_value":"PRIVATE"}',TARGET)
        self.assertNotIn('PRIVATE',feedback(caught.exception))
    def test_full_flow_is_unchanged_and_step_cannot_inject_a_target(self):
        from haejo.flow_session import decode_session_flow
        helper=CompactEditTests();full=helper.document()
        self.assertEqual(helper.parse(full),decode_session_flow(json.dumps(full),TARGET,PATH))
        with self.assertRaises(ValueError):
            decode_session_flow(json.dumps({'set_value':'PRIVATE','target':'another.app'}),TARGET,PATH)
    def test_single_step_performs_one_write_and_one_readback(self):
        helper=DocumentSessionTests();inner=helper.inner();step=CompactEditTests().document('changed')['steps'][0]
        def receive(obs,target,action,**kwargs):
            inner.observe.return_value['tree']=inner.observe.return_value['tree'].replace('Value: owned','Value: changed')
            inner.document_text.return_value['text']='changed';return {'type':'acted'}
        inner.act.side_effect=receive
        code,_,messages=helper.run_session(inner,doc=step)
        self.assertEqual(1,code);inner.act.assert_called_once()
        self.assertEqual(2,inner.document_text.call_count)
        self.assertTrue(any(x.startswith('body_verified —') for x in messages))


class EditCheckSemanticsTests(unittest.TestCase):
    def test_check_follows_written_selector_not_unrelated_check_defaults(self):
        helper=CompactEditTests();doc=helper.document(selector={'identifier':'Other'})
        doc['check_defaults']={'field':{'identifier':'Unrelated'},'attribute':'Title'}
        flow=helper.parse(doc);step=flow.steps[0]
        self.assertEqual(step.selector,step.postcondition.field)
        self.assertEqual('Value',step.postcondition.attribute)
    def test_no_check_defaults_needed_for_written_value_check(self):
        helper=CompactEditTests();doc=helper.document();doc.pop('check_defaults')
        flow=helper.parse(doc);self.assertEqual(flow.steps[0].selector,flow.steps[0].postcondition.field)
    def test_postcondition_timeout_does_not_send_protected_values_to_repair(self):
        from haejo.command_help import calculator_example
        from haejo.flow import replay
        from tests.test_flow_safety_defaults import Calculator
        secret='PRIVATE_PASSWORD_SENTINEL'
        flow=Flow.from_json(__import__('json').dumps(calculator_example()))
        flow.steps[-1].postcondition.equals=secret
        flow.steps[-1].on_uncertain=['postcondition_timeout']
        class SecretCalculator(Calculator):
            @property
            def tree(self):return super().tree+'\n  9 ScrollArea Identifier: other, Value: '+secret
        app=SecretCalculator();app.wait_until=lambda target,predicate,**kwargs: app.observe(target) if predicate(app.tree) else {'type':'timeout','last_obs':app.observe(target)}
        seen=[]
        result=replay(app,flow,escalate=lambda uncertainty: seen.append(str((uncertainty.detail,uncertainty.options))),
                      budget=1,_seed_secrets=(secret,))
        self.assertFalse(result.ok);self.assertEqual(1,len(seen))
        self.assertNotIn(secret,seen[0])
        self.assertNotIn(secret,str(result.log))


class LiteralEditSessionTests(unittest.TestCase):
    def test_template_looking_body_scope_and_evidence_remain_literal(self):
        from haejo.flow_session import decode_session_flow,prepare_session_flow
        text='literal {{name}} and 😀'
        doc=CompactEditTests().document(text);step=doc['steps'][0]
        step['safety']['evidence'][0]['value']='Write literal {{name}}'
        flow=decode_session_flow(json.dumps(step),TARGET,'/owned/{{folder}}.txt')
        ready,saved=prepare_session_flow(flow,TARGET)
        self.assertEqual(text,ready.steps[0].params['value'])
        self.assertEqual(text,ready.steps[0].postcondition.equals)
        self.assertEqual('/owned/{{folder}}.txt',ready.steps[0].selector.ancestor)
        self.assertEqual('Write literal {{name}}',ready.steps[0].safety.evidence[0].value)
        restored=Flow.from_json(saved).bind()
        self.assertEqual(text,restored.steps[0].params['value'])
        self.assertEqual(text,restored.steps[0].postcondition.equals)
    def test_step_only_unknown_header_keys_are_not_silently_ignored(self):
        from haejo.flow_session import decode_session_flow
        for name in ('tables','derived','literal_params','description','unknown'):
            with self.subTest(name=name),self.assertRaises(ValueError):
                decode_session_flow(json.dumps({'set_value':'PRIVATE',name:{}}),TARGET,PATH)
