"""Coordinator contracts, independent transports, receipts and cancellation."""
import io
import json
import os
from pathlib import Path
import subprocess
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from haejo.parallel_run import parse_jobs, run_parallel_jobs, SessionReceipt, BatchControl
from haejo.flow_session import run_session


def manifest(count=2):
    return {'schema':1, 'jobs':[
        {'id':f'job-{i}', 'window_id':100+i, 'flow':{
            'schema':2, 'name':f'flow-{i}', 'target':'ai.callabo.haejo.fixture', 'steps':[
                {'action':'set_value', 'selector':{'identifier':'editor'}, 'params':{'value':f'private-{i}'},
                 'safety':{'effects':['write_ephemeral'],'reversibility':'reversible',
                           'resource':{'object_type':'fixture entry','scope':'entry'}},
                 'postcondition':{'field':{'identifier':'editor'},'attribute':'Value','equals':f'private-{i}'}}
            ]}} for i in range(count)]}


class ValidationTests(unittest.TestCase):
    def test_distinct_windows_and_immutable_bound_snapshots(self):
        source=manifest(4); jobs=parse_jobs(source)
        source['jobs'][0]['flow']['steps'][0]['params']['value']='changed'
        self.assertEqual(4,len(jobs));self.assertNotIn('changed',jobs[0].flow_json)
        source=manifest(1);flow=source['jobs'][0]['flow'];flow['params']={'text':'bound'}
        flow['steps'][0]['params']['value']='{{text}}'
        self.assertIn('bound',parse_jobs(source)[0].flow_json)

    def test_invalid_batch_is_rejected_before_any_process_starts(self):
        cases=[manifest(0),manifest(5),{'schema':True,'jobs':manifest()['jobs']}]
        for window in (0,-1,True,1.5,2**32):
            m=manifest();m['jobs'][0]['window_id']=window;cases.append(m)
        for field in ('id','window_id'):
            m=manifest();m['jobs'][1][field]=m['jobs'][0][field];cases.append(m)
        m=manifest();m['jobs'][1]['window_id']=100;m['jobs'][1]['flow']['target']='AI.CALLABO.HAEJO.FIXTURE';cases.append(m)
        m=manifest();del m['jobs'][1]['window_id'];cases.append(m)
        for m in cases:
            with self.subTest(m=m),patch('haejo.parallel_run.subprocess.Popen') as launch:
                with self.assertRaises(ValueError):run_parallel_jobs(m)
                launch.assert_not_called()

    def test_unsupported_or_unchecked_operations_never_start(self):
        modifications=[lambda s:s.update(action='menu',params={'path':['File']}),
                       lambda s:s.pop('postcondition'),lambda s:s.update(unverified_ok=True),
                       lambda s:s['params'].update(input_method='paste'),
                       lambda s:s['safety'].update(effects=['write_persistent']),
                       lambda s:s.update(on_uncertain=['action_failed'])]
        for change in modifications:
            m=manifest();change(m['jobs'][1]['flow']['steps'][0])
            with self.subTest(change=change),self.assertRaises(ValueError):parse_jobs(m)


class ReceiptTests(unittest.TestCase):
    def test_refusals_and_unknown_effects_are_distinct_and_content_free(self):
        inner=SimpleNamespace(act=Mock(return_value={'type':'error','error':'window_scope_lost',
              'effect':'not_started','detail':'PRIVATE','coordination_elapsed_ms':20}))
        receipt=SessionReceipt();driver=receipt.wrap(inner)
        driver.act('o','app',{'name':'click'})
        summary=receipt.summary(1)
        self.assertEqual('window_scope_lost',summary['error']);self.assertEqual('not_started',summary['effect'])
        self.assertNotIn('PRIVATE',json.dumps(summary));self.assertEqual(20,summary['coordination_elapsed_ms'])
        receipt.replayed=SimpleNamespace(ok=False,log=[{'status':'error','error':'postcondition_timeout'}])
        self.assertEqual('window_scope_lost',receipt.summary(1)['error'])
        inner.act.side_effect=OSError('PRIVATE')
        with self.assertRaises(OSError):driver.act('o','app',{'name':'click'})
        self.assertEqual('unknown',receipt.summary(1)['effect']);self.assertEqual(2,inner.act.call_count)

    def test_acted_is_not_verified_and_partial_effect_is_never_not_started(self):
        receipt=SessionReceipt();inner=SimpleNamespace(act=Mock(side_effect=[
            {'type':'acted'}, {'type':'error','error':'target_busy','effect':'not_started'}]))
        driver=receipt.wrap(inner);driver.act('o','app',{});driver.act('o','app',{})
        self.assertFalse(receipt.summary(0)['ok']);self.assertEqual('unknown',receipt.summary(1)['effect'])
        receipt.replayed=SimpleNamespace(ok=True,log=[])
        self.assertEqual('observed',receipt.summary(0)['effect'])

    def test_session_receipt_comes_from_real_replay_observer_and_is_private(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'receipt.json';received=[]
            def session(args,*,make_driver,run_flow,**kwargs):
                self.assertNotIn('--receipt',args)
                def replay(*args,**kwargs):pass
                run_flow(object(),[],_driver=make_driver([]))
                return 0
            def replay(*args,**kwargs):
                kwargs['_driver'].act('o','app',{'name':'set_value'})
                kwargs['_result_observer'](SimpleNamespace(ok=True,log=[]))
                return 0
            with patch('haejo.flow_session._run_session',side_effect=session):
                code=run_session(['app','--helper','--receipt',str(path)],make_driver=lambda _:SimpleNamespace(
                    act=lambda *args:{'type':'acted'}),run_flow=replay,stdin=None,emit=received.append)
            self.assertEqual(0,code);self.assertTrue(json.loads(path.read_text())['ok'])
            self.assertEqual(0o600,path.stat().st_mode & 0o777)
            with patch('haejo.flow_session._run_session') as run:
                self.assertEqual(2,run_session(['--receipt',str(path)],make_driver=None,run_flow=None,stdin=None,emit=received.append))
                run.assert_not_called()


class BatchControlTests(unittest.TestCase):
    def test_stop_notifications_require_matching_user_and_cannot_resume(self):
        center=Mock();loop=Mock();callbacks=[]
        center.addObserverForName_object_queue_usingBlock_.side_effect=lambda name,obj,queue,callback:callbacks.append(callback) or 'observer'
        foundation=SimpleNamespace(NSDistributedNotificationCenter=SimpleNamespace(defaultCenter=lambda:center),
            NSRunLoop=SimpleNamespace(currentRunLoop=lambda:loop),NSDate=Mock())
        with patch.dict('sys.modules',{'Foundation':foundation}):
            with BatchControl(targets=['com.example.owned']) as control:
                for info in (None,{}, {'schema':True,'uid':os.getuid()}, {'schema':1,'uid':-1}):
                    callbacks[0](SimpleNamespace(userInfo=lambda:info));self.assertFalse(control.stopped)
                callbacks[0](SimpleNamespace(userInfo=lambda:{'schema':1,'uid':os.getuid(),'targets':['com.other.app']}))
                self.assertFalse(control.stopped)
                callbacks[0](SimpleNamespace(userInfo=lambda:{'schema':1,'uid':os.getuid()}))
                self.assertTrue(control.stopped)
                callbacks[0](SimpleNamespace(userInfo=lambda:{'schema':0,'uid':os.getuid()}))
                self.assertTrue(control.stopped)
                control.pump();loop.runUntilDate_.assert_called_once()
        center.removeObserver_.assert_called_once_with('observer')

    def test_bridged_integer_subclasses_are_accepted(self):
        class BridgedInteger(int):pass
        center=Mock();callbacks=[]
        center.addObserverForName_object_queue_usingBlock_.side_effect=lambda name,obj,queue,callback:callbacks.append(callback) or 'observer'
        foundation=SimpleNamespace(NSDistributedNotificationCenter=SimpleNamespace(defaultCenter=lambda:center),
            NSRunLoop=SimpleNamespace(currentRunLoop=Mock()),NSDate=Mock())
        with patch.dict('sys.modules',{'Foundation':foundation}),BatchControl() as control:
            callbacks[0](SimpleNamespace(userInfo=lambda:{'schema':BridgedInteger(1),'uid':BridgedInteger(os.getuid())}))
            self.assertTrue(control.stopped)


class CoordinatorTests(unittest.TestCase):
    def setUp(self):
        class Control:
            stopped=False
            def __enter__(self):return self
            def __exit__(self,*args):pass
            def pump(self):time.sleep(.005)
        self.control=Control()
        self.patch_control=patch('haejo.parallel_run.BatchControl',return_value=self.control)
        self.patch_control.start();self.addCleanup(self.patch_control.stop)

    def test_independent_processes_overlap_and_do_not_inherit_authority_or_values_in_results(self):
        real_popen=subprocess.Popen
        barrier=threading.Barrier(2);commands=[];events=[]
        with tempfile.TemporaryDirectory() as directory:
            script=Path(directory)/'worker.py'
            script.write_text('''import json,sys,os
flow=json.loads(sys.stdin.readline())
path=sys.argv[sys.argv.index('--receipt')+1]
assert 'HAEJO_HELPER_FD' not in os.environ
assert os.environ['HAEJO_HELPER_MODE']=='warm'
with open(path,'w') as f:json.dump({'schema':1,'ok':True,'effect':'observed','error':None,'coordination_elapsed_ms':12,'helper_pid':os.getpid()},f)
''')
            def launch(command,**kwargs):
                commands.append(command)
                process=real_popen([os.sys.executable,str(script),*command[1:]],**kwargs)
                communicate=process.communicate
                def overlap(*args,**kw):
                    barrier.wait(timeout=3);return communicate(*args,**kw)
                process.communicate=overlap
                return process
            with patch('haejo.parallel_run.subprocess.Popen',side_effect=launch),patch.dict(os.environ,{'HAEJO_HELPER_FD':'999'}),patch('haejo.parallel_run.sys.platform','darwin'):
                result=run_parallel_jobs(manifest(),on_event=events.append)
        self.assertTrue(result['ok'],result);self.assertEqual(2,len(commands))
        self.assertEqual(2,len({job['helper_pid'] for job in result['jobs']}))
        self.assertNotIn('private-',json.dumps(result));self.assertNotIn('private-',json.dumps(events))
        self.assertEqual(['job-0','job-1'],[job['id'] for job in result['jobs']])
        self.assertEqual(2,sum(event['state']=='verified' for event in events))

    def test_timeout_kills_group_and_is_not_retried(self):
        process=Mock(pid=987654,stdin=Mock());process.poll.return_value=None
        process.communicate.side_effect=subprocess.TimeoutExpired('worker',1)
        with patch('haejo.parallel_run.sys.platform','darwin'),patch('haejo.parallel_run.subprocess.Popen',return_value=process) as start,patch('haejo.parallel_run.os.killpg') as kill:
            result=run_parallel_jobs(manifest(1),timeout=1)
        self.assertFalse(result['ok']);self.assertEqual('unknown',result['jobs'][0]['effect'])
        self.assertEqual('parallel_timeout',result['jobs'][0]['error']);start.assert_called_once()
        self.assertEqual(2,kill.call_count);process.wait.assert_called()

    def test_missing_receipt_cannot_become_success_from_exit_code(self):
        process=Mock(pid=987654,stdin=Mock(),returncode=0);process.poll.return_value=0
        with patch('haejo.parallel_run.sys.platform','darwin'),patch('haejo.parallel_run.subprocess.Popen',return_value=process) as start:
            result=run_parallel_jobs(manifest(1))
        self.assertFalse(result['ok']);self.assertEqual('parallel_receipt_unavailable',result['jobs'][0]['error'])
        start.assert_called_once()

    def test_explicit_refusal_is_preserved_and_malformed_receipts_remain_unknown(self):
        cases=[({'schema':1,'ok':False,'effect':'not_started','error':'window_scope_requires_ax',
                 'coordination_elapsed_ms':50,'helper_pid':123},1,'window_scope_requires_ax','not_started'),
               ({'schema':1,'ok':True,'effect':'not_started','error':None,
                 'coordination_elapsed_ms':0,'helper_pid':123},0,'parallel_invalid_receipt','unknown'),
               ({'schema':1,'ok':True,'effect':'observed','error':None,
                 'coordination_elapsed_ms':0,'helper_pid':True},0,'parallel_invalid_receipt','unknown')]
        for raw,code,error,effect in cases:
            def launch(command,**kwargs):
                process=Mock(pid=987654,stdin=Mock(),returncode=code);process.poll.return_value=code
                def communicate(*args,**kwargs):
                    Path(command[command.index('--receipt')+1]).write_text(json.dumps(raw))
                process.communicate.side_effect=communicate
                return process
            with self.subTest(raw=raw),patch('haejo.parallel_run.sys.platform','darwin'),patch('haejo.parallel_run.subprocess.Popen',side_effect=launch) as start:
                result=run_parallel_jobs(manifest(1))
            self.assertEqual(error,result['jobs'][0]['error']);self.assertEqual(effect,result['jobs'][0]['effect'])
            start.assert_called_once()

    def test_interrupt_after_launch_stops_the_group_before_any_dispatch(self):
        process=Mock(pid=987654,stdin=Mock());process.poll.return_value=None
        def event(row):
            if row['state']=='running':raise KeyboardInterrupt()
        with patch('haejo.parallel_run.sys.platform','darwin'),patch('haejo.parallel_run.subprocess.Popen',return_value=process),patch('haejo.parallel_run.os.killpg') as kill:
            with self.assertRaises(KeyboardInterrupt):run_parallel_jobs(manifest(1),on_event=event)
        kill.assert_called();process.wait.assert_called();process.communicate.assert_not_called()

    def test_stop_all_cancels_a_worker_waiting_before_any_receipt(self):
        released=threading.Event();ready=threading.Event();process=Mock(pid=987654,stdin=Mock(),returncode=1)
        process.poll.side_effect=lambda:1 if released.is_set() else None
        def communicate(*args,**kwargs):
            ready.set();released.wait(2)
        process.communicate.side_effect=communicate
        def pump():
            ready.wait(2);self.control.stopped=True
        self.control.pump=pump
        with patch('haejo.parallel_run.sys.platform','darwin'),patch('haejo.parallel_run.subprocess.Popen',return_value=process),patch('haejo.parallel_run.os.killpg',side_effect=lambda *args:released.set()) as kill:
            result=run_parallel_jobs(manifest(1))
        self.assertTrue(result['cancelled']);self.assertFalse(result['ok'])
        self.assertEqual('parallel_cancelled',result['jobs'][0]['error']);kill.assert_called()

    def test_cli_help_is_native_free_and_bad_manifest_starts_nothing(self):
        from haejo.cli import main
        from contextlib import redirect_stdout
        with redirect_stdout(io.StringIO()) as output:
            self.assertEqual(0,main(['parallel','--help']))
        self.assertIn('manifest',output.getvalue())
        with tempfile.TemporaryDirectory() as directory,redirect_stdout(io.StringIO()),patch('haejo.session.KeepAwake'),patch('haejo.parallel_run.subprocess.Popen') as start:
            path=Path(directory)/'invalid.json';path.write_text('{')
            self.assertEqual(2,main(['parallel',str(path),'--helper']))
            start.assert_not_called()


class ParallelTaskPropagationTests(unittest.TestCase):
    """Children of a task-bound `parallel` run join the same task."""
    def setUp(self):
        from haejo import task as task_mod
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)/'Tasks'
        p = patch.object(task_mod, 'tasks_root', lambda r=None: root); p.start(); self.addCleanup(p.stop)

    def test_parallel_executor_children_receive_task_env(self):
        from haejo import task as task_mod
        from unittest.mock import Mock
        from haejo.parallel_run import run_parallel_jobs
        task_id = task_mod.start('goal')['id']
        binding = task_mod.bind(task_id, 'parallel')
        process = Mock(pid=987654, stdin=Mock(), returncode=1); process.poll.return_value = 1
        process.communicate.return_value = ('', '')
        token = task_mod.current.set(binding)
        try:
            with patch('haejo.parallel_run.sys.platform', 'darwin'), \
                 patch('haejo.parallel_run.subprocess.Popen', return_value=process) as start, \
                 patch.dict(os.environ, {'HAEJO_TASK': 't-' + 'f' * 24, 'HAEJO_TASK_PARENT': 'raw'}):
                run_parallel_jobs(manifest(2))
        finally:
            task_mod.current.reset(token)
        self.assertEqual(2, start.call_count)
        for call in start.call_args_list:
            env = call.kwargs['env']
            self.assertEqual((task_id, binding.invocation), (env.get('HAEJO_TASK'), env.get('HAEJO_TASK_PARENT')))
        with patch('haejo.parallel_run.sys.platform', 'darwin'), \
             patch('haejo.parallel_run.subprocess.Popen', return_value=process) as start, \
             patch.dict(os.environ, {'HAEJO_TASK': 't-' + 'f' * 24}):
            run_parallel_jobs(manifest(1))      # unbound parent: raw env is not forwarded
        self.assertNotIn('HAEJO_TASK', start.call_args.kwargs['env'])

