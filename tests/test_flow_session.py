"""A session reuses only its driver, accepts one bounded flow and closes it."""
import contextlib
import io
import json
import os
import pty
import threading
import unittest
from unittest.mock import Mock, patch
from haejo.command_help import calculator_example
from haejo.flow_session import run_session, read_flow_line, flow_input_mode
from tests.test_flow_safety_defaults import Calculator


class FlowSessionTests(unittest.TestCase):
    def test_target_and_parameter_repairs_prepare_once_and_keep_template(self):
        from haejo.flow_session import read_session_flow,prepare_session_flow
        target='com.apple.calculator'
        doc={'name':'read','target':target,'params':{'id':None},'steps':[{
            'action':'read','selector':{'identifier':'{{id}}'},
            'safety':{'effects':['read'],'reversibility':'reversible'}}]}
        wrong={**doc,'target':'PRIVATE_TARGET'}
        corrected={**doc,'params':{'id':'StandardInputView'}}
        messages=[]
        with patch('haejo.flow_session.os.isatty',return_value=True), \
             patch('haejo.flow_session.read_flow_line',side_effect=[json.dumps(wrong),json.dumps(doc),json.dumps(corrected)]):
            flow,template=read_session_flow(42,5,messages.append,
                prepare=lambda parsed:prepare_session_flow(parsed,target))
        self.assertEqual('StandardInputView',flow.steps[0].selector.identifier)
        self.assertIn('{{id}}',template)
        self.assertIn('target:','\n'.join(messages));self.assertIn('params:','\n'.join(messages))
        self.assertNotIn('PRIVATE_TARGET','\n'.join(messages))

    def test_authoring_metrics_count_repairs_without_input_values(self):
        from haejo.flow_session import read_session_flow
        metrics={};good=json.dumps(calculator_example());bad='{"private":"PRIVATE_SENTINEL"}'
        with patch('haejo.flow_session.os.isatty',return_value=True), \
             patch('haejo.flow_session.read_flow_line',side_effect=['{',bad,good]):
            read_session_flow(42,5,lambda _:None,metrics=metrics)
        self.assertEqual(3,metrics['flow_input_attempts'])
        self.assertEqual(2,metrics['flow_input_corrections'])
        self.assertEqual(len(('{'+bad+good).encode()),metrics['flow_input_utf8_bytes'])
        self.assertNotIn('PRIVATE',str(metrics))

    def test_default_observation_preserves_task_data_and_hides_only_diagnostics(self):
        observe=Calculator.observe
        def measured(app,*args,**kwargs):
            data=observe(app,*args,**kwargs)
            data.update(observation_timing_ms={'read':5},observation_metrics={'nodes':8},
                        window_listing_diagnostic={'scope':'diagnostic'},coordination_elapsed_ms=2)
            return data
        for timed in (False,True):
            with self.subTest(timed=timed),patch.object(Calculator,'observe',measured):
                args=['com.apple.calculator','--helper']+(['--timings'] if timed else [])
                code,app,_,messages=self.run_with(calculator_example(),args=args)
                packet=json.loads(next(m for m in messages if m.startswith('{') and json.loads(m).get('type')=='observation'))
                self.assertEqual(0,code);self.assertEqual('408',app.value)
                self.assertIn('tree',packet);self.assertIn('obs_id',packet)
                self.assertEqual(timed,'observation_metrics' in packet)
                self.assertEqual(timed,'window_listing_diagnostic' in packet)

    def test_windows_corrections_share_one_input_reader(self):
        from haejo.flow_session import read_session_flow
        reader=Mock(side_effect=[b'{}\n',(json.dumps(calculator_example())+'\n').encode()])
        with patch('haejo.flow_session.sys.platform','win32'), \
             patch('haejo.flow_session.os.isatty',return_value=True), \
             patch('haejo.flow_session._windows_reader',return_value=reader) as factory:
            flow=read_session_flow(42,5,lambda message:None)
        self.assertEqual('com.apple.calculator',flow.target)
        factory.assert_called_once_with(42)
        self.assertEqual(2,reader.call_count)

    def test_interactive_schema_repair_reuses_observation_and_dispatches_once(self):
        app=Calculator();app.close=Mock();make=Mock(return_value=app)
        runner=Mock(return_value=0);messages=[]
        master,slave=pty.openpty();writers=[]
        def emit(message):
            messages.append(message)
            if message.startswith('HAEJO_SESSION_READY send'):
                os.write(master,b'{"private":"PRIVATE_SENTINEL"}\n')
            elif message.startswith('session_invalid_flow:'):
                self.assertEqual([],app.calls)
                runner.assert_not_called()
                payload=(json.dumps(calculator_example())+'\n').encode()
                def write_correction():
                    offset=0
                    while offset<len(payload):offset+=os.write(master,payload[offset:])
                writer=threading.Thread(target=write_correction,daemon=True)
                writers.append(writer);writer.start()
        try:
            with os.fdopen(os.dup(slave)) as stream:
                result=run_session(['com.apple.calculator','--helper','--guide'],make_driver=make,
                                   run_flow=runner,stdin=stream,emit=emit)
        finally:
            for writer in writers:writer.join(2)
            os.close(master);os.close(slave)
        self.assertEqual(0,result);make.assert_called_once();runner.assert_called_once()
        self.assertEqual(1,app.observations)
        self.assertEqual(1,sum(m.startswith('HAEJO_FLOW_GUIDE') for m in messages))
        self.assertEqual(2,sum(m.startswith('HAEJO_SESSION_READY') for m in messages))
        self.assertNotIn('PRIVATE_SENTINEL','\n'.join(messages))
        app.close.assert_called_once()

    def test_repair_keeps_original_deadline_and_eof_does_not_loop(self):
        from haejo.flow_session import read_session_flow
        with patch('haejo.flow_session.os.isatty',return_value=True), \
             patch('haejo.flow_session.time.monotonic',side_effect=[100,101,104]), \
             patch('haejo.flow_session.read_flow_line',side_effect=['{}',TimeoutError()]) as read:
            with self.assertRaises(TimeoutError):read_session_flow(3,5,lambda message:None)
            self.assertEqual([4,1],[call.args[1] for call in read.call_args_list])
        with patch('haejo.flow_session.read_flow_line',side_effect=ValueError('session_input_closed')) as read:
            with self.assertRaisesRegex(ValueError,'session_input_closed'):
                read_session_flow(3,5,lambda message:None)
            read.assert_called_once()

    def test_stored_comparisonless_skip_keeps_legacy_load_and_execution(self):
        from haejo.flow import Flow, replay
        doc=calculator_example()
        doc['steps'][0]['skip_if']={'field':{'identifier':'StandardInputView'}}
        flow=Flow.from_json(json.dumps(doc))
        self.assertFalse(flow.steps[0].skip_if.check('0 TextArea Value: 0'))
        app=Calculator()
        self.assertTrue(replay(app,flow).ok)
        self.assertEqual('408',app.value)
        result,app,make,messages=self.run_with(doc)
        self.assertEqual(2,result)
        self.assertEqual([],app.calls)

    def test_comparisonless_check_refuses_before_any_input(self):
        for check in ({'field':{'identifier':'StandardInputView'},'value':'PRIVATE'},
                      {'field':{'identifier':'StandardInputView'}},
                      {'all_of':[{'field':{'identifier':'StandardInputView'}}]}):
            with self.subTest(check=check):
                doc=calculator_example()
                doc['steps'][0]['postcondition']=check
                result,app,make,messages=self.run_with(doc)
                self.assertEqual(2,result)
                self.assertEqual([],app.calls)
                text='\n'.join(messages)
                self.assertIn('steps[0].postcondition',text)
                self.assertIn('equals',text)
                self.assertNotIn('PRIVATE',text)

    def run_with(self, doc, args=None, runner=None):
        from haejo.cli import _run_flow
        app=Calculator();app.close=Mock()
        make=Mock(return_value=app);messages=[]
        read,write=os.pipe()
        try:
            os.write(write,(json.dumps(doc,ensure_ascii=False)+'\n').encode());os.close(write);write=None
            with os.fdopen(read) as stream,contextlib.redirect_stdout(io.StringIO()),contextlib.redirect_stderr(io.StringIO()), \
                 patch('haejo.cli._make_driver',side_effect=AssertionError('second startup')), \
                 patch('haejo.cli._indicator_for',return_value=contextlib.nullcontext()):
                result=run_session(args or ['com.apple.calculator','--helper'],make_driver=make,
                                   run_flow=runner or _run_flow,stdin=stream,emit=messages.append)
        finally:
            if write is not None:os.close(write)
        return result,app,make,messages

    def test_one_driver_is_reused_and_replay_refreshes_observations(self):
        result,app,make,messages=self.run_with(calculator_example())
        self.assertEqual(0,result);self.assertEqual('408',app.value)
        self.assertEqual(1,make.call_count);app.close.assert_called_once()
        self.assertGreater(app.observations,1)
        self.assertTrue(any(line.startswith('HAEJO_SESSION_READY') for line in messages))

    def test_guide_is_opt_in_and_precedes_observation_without_extra_driver(self):
        for guide in (False, True):
            args=['com.apple.calculator','--helper'] + (['--guide'] if guide else [])
            result,app,make,messages=self.run_with(calculator_example(),args=args)
            self.assertEqual(0,result);self.assertEqual(1,make.call_count)
            self.assertEqual('408',app.value)
            self.assertEqual(guide, messages[0].startswith('HAEJO_FLOW_GUIDE'))
            if guide:
                self.assertEqual('observation', json.loads(messages[1])['type'])

    def test_session_timings_separate_flow_input_wait_from_replay(self):
        result,app,make,messages=self.run_with(calculator_example(),args=[
            'com.apple.calculator','--helper','--guide','--timings'])
        self.assertEqual(0,result)
        timing=json.loads(messages[-1].removeprefix('HAEJO_SESSION_TIMINGS '))
        keys=('observation_ready_seconds','input_ready_seconds','flow_received_seconds',
              'replay_done_seconds','session_done_seconds')
        self.assertEqual(list(keys),list(sorted(keys,key=lambda k:timing[k])))
        self.assertEqual(set(keys)|{"flow_input_attempts","flow_input_utf8_bytes"},set(timing))
        self.assertEqual(1,timing["flow_input_attempts"])
        self.assertGreater(timing["flow_input_utf8_bytes"],0)

    def test_target_mismatch_and_malformed_json_are_before_input(self):
        for doc in ({**calculator_example(),'target':'another.app'}, {'private':'PERSONAL_TEXT'}):
            result,app,make,messages=self.run_with(doc)
            self.assertEqual(2,result);self.assertEqual([],app.calls);app.close.assert_called_once()
            self.assertNotIn('PERSONAL_TEXT','\n'.join(messages))

    def test_same_callback_cannot_be_used_as_interactive_approval(self):
        runner=Mock(return_value=1)
        result,app,make,messages=self.run_with(calculator_example(),runner=runner)
        self.assertIs(app,runner.call_args.kwargs['_driver'])
        self.assertFalse(runner.call_args.kwargs['_confirm']('approve'))
        self.assertEqual(1,result);app.close.assert_called_once()

    def test_failed_flow_is_not_replayed(self):
        runner=Mock(return_value=1)
        result,app,make,messages=self.run_with(calculator_example(),runner=runner)
        self.assertEqual(1,result);self.assertEqual(1,runner.call_count)

    def test_invalid_flags_never_start_a_driver(self):
        for args in (['com.apple.calculator'],['--helper','--helper','com.apple.calculator'],
                     ['com.apple.calculator','--helper','--yes'],
                     ['com.apple.calculator','--helper','--document','/path'],
                     ['com.apple.calculator','--helper','--idle-timeout','0']):
            with self.subTest(args=args):
                result,app,make,messages=self.run_with(calculator_example(),args=args)
                self.assertEqual(2,result);make.assert_not_called();app.close.assert_not_called()

    def test_model_judgment_is_refused_before_input(self):
        doc=calculator_example();doc['steps']=[{'action':'decide','params':{
            'question':'Which?','choices':['yes','no'],'into':'choice'}}]
        result,app,make,messages=self.run_with(doc)
        self.assertEqual(2,result);self.assertEqual([],app.calls);app.close.assert_called_once()

    def test_extra_flow_and_over_budget_input_are_rejected(self):
        for data in (b'{}\n{}\n',b'x'*101):
            read,write=os.pipe()
            try:
                os.write(write,data)
                with patch('haejo.flow_session.MAX_FLOW_BYTES',100),self.assertRaises(ValueError):
                    read_flow_line(read,1)
            finally:os.close(read);os.close(write)

    def test_idle_timeout_and_eof_are_terminal(self):
        read,write=os.pipe()
        try:
            with self.assertRaises(TimeoutError):read_flow_line(read,.01)
            os.close(write);write=None
            with self.assertRaisesRegex(ValueError,'session_input_closed'):read_flow_line(read,1)
        finally:
            os.close(read)
            if write is not None:os.close(write)

    def test_tty_flags_restored_and_long_json_not_echoed(self):
        import termios
        master,slave=pty.openpty();before=termios.tcgetattr(slave)
        try:
            with self.assertRaisesRegex(RuntimeError,'stop'):
                with flow_input_mode(slave):
                    current=termios.tcgetattr(slave)
                    self.assertFalse(current[3]&termios.ICANON)
                    self.assertFalse(current[3]&termios.ECHO)
                    payload=b'"'+b'x'*5000+b'"\n'
                    def write_payload():
                        offset=0
                        while offset<len(payload):offset+=os.write(master,payload[offset:])
                    writer=threading.Thread(target=write_payload,daemon=True)
                    writer.start()
                    self.assertEqual(payload[:-1].decode(),read_flow_line(slave,1))
                    writer.join(1)
                    self.assertFalse(writer.is_alive())
                    raise RuntimeError('stop')
            after=termios.tcgetattr(slave)
            # Darwin may set its kernel-managed PENDIN flag when canonical
            # mode is restored. All configured flags and control chars match.
            before[3]&=~getattr(termios,'PENDIN',0)
            after[3]&=~getattr(termios,'PENDIN',0)
            self.assertEqual(before,after)
        finally:os.close(master);os.close(slave)
