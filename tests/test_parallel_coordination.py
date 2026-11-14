import json
import socket
import threading
import unittest
from types import SimpleNamespace
from haejo.foreground_scope import foreground_scope
from haejo.window_scope import take_window_arg,bind_window
from haejo.helper import InheritedHelperDriver

class ParallelCoordination(unittest.TestCase):
    def test_explicit_handoff_resets_scope_only_after_helper_receipt(self):
        from unittest.mock import Mock
        driver=object.__new__(InheritedHelperDriver)
        driver.capabilities={'session.release_targets'}
        driver._window_scope=('app',42)
        driver._send=Mock(return_value={'type':'error','error':'unavailable'})
        driver.release_targets()
        self.assertEqual(('app',42),driver._window_scope)
        driver._send.return_value={'type':'targets_released','observation_invalidated':True}
        self.assertEqual('targets_released',driver.release_targets()['type'])
        self.assertIsNone(driver._window_scope)
        driver._send.assert_called_with({'type':'release_targets'})
        driver.capabilities=set();driver._send.reset_mock()
        self.assertEqual('target_release_unavailable',driver.release_targets()['error'])
        driver._send.assert_not_called()

    def test_window_id_is_live_host_scope_and_invalid_values_are_rejected(self):
        self.assertEqual((['app','--helper'],42),take_window_arg(['app','--window-id','42','--helper']))
        for value in ('0','-1','4294967296','1.5','True','１'):
            with self.subTest(value=value),self.assertRaises(ValueError):take_window_arg(['app','--window-id',value])
        with self.assertRaises(ValueError):take_window_arg(['--document','/owned/file','--window-id','2'])
        self.assertEqual('window_scope_unavailable',bind_window(object(),'app',42)['error'])

    def test_bound_channel_attaches_scope_and_never_sends_another_target(self):
        client,peer=socket.socketpair()
        driver=object.__new__(InheritedHelperDriver);driver._sock=client
        driver._f=client.makefile('rw',encoding='utf-8',newline='\n')
        driver.capabilities={'session.window_scope'};received=[]
        self.addCleanup(driver._f.close);self.addCleanup(client.close);self.addCleanup(peer.close)
        def server():
            stream=peer.makefile('rb')
            try:
                received.append(json.loads(stream.readline()))
                peer.sendall(b'{"type":"observation","tree":"owned"}\n')
            finally:stream.close()
        worker=threading.Thread(target=server);worker.start()
        self.assertIsNone(bind_window(driver,'app',42))
        self.assertEqual('observation',driver._send({'type':'observe','target':'app'})['type'])
        self.assertEqual('window_scope_changed',driver._send({'type':'observe','target':'other'})['error'])
        worker.join(2);self.assertFalse(worker.is_alive())
        self.assertEqual([{'type':'observe','target':'app','window_scope_id':42}],received)
        self.assertEqual('window_scope_changed',driver.scope_window('app',43)['error'])
        self.assertEqual('window_scope_requires_app',driver.foreground_begin('app')['error'])

    def test_busy_reply_does_not_cause_host_input_retransmission(self):
        client,peer=socket.socketpair();driver=object.__new__(InheritedHelperDriver)
        driver._sock=client;driver._f=client.makefile('rw',encoding='utf-8',newline='\n')
        self.addCleanup(driver._f.close);self.addCleanup(client.close);self.addCleanup(peer.close)
        received=[]
        def server():
            received.append(peer.recv(4096));peer.sendall(b'{"type":"error","error":"input_busy","effect":"not_started"}\n')
        worker=threading.Thread(target=server);worker.start()
        result=driver._send({'type':'act','target':'app','action':{'name':'click','element_index':2}})
        worker.join(2);self.assertEqual('input_busy',result['error']);self.assertEqual(1,len(received))

    def test_foreground_lease_wraps_success_failure_and_busy_without_repeating_body(self):
        calls=[]
        driver=SimpleNamespace(capabilities={'session.foreground_lease'},
            foreground_begin=lambda target:calls.append('begin') or {'type':'foreground_lease','acquired':True},
            foreground_end=lambda target:calls.append('end'))
        with foreground_scope(driver,'app') as error:
            self.assertIsNone(error);calls.append('activate')
        self.assertEqual(['begin','activate','end'],calls)
        calls.clear()
        with self.assertRaises(RuntimeError):
            with foreground_scope(driver,'app'):
                calls.append('activate');raise RuntimeError('owned failure')
        self.assertEqual(['begin','activate','end'],calls)
        calls.clear();driver.foreground_begin=lambda target:{'type':'error','error':'target_busy','effect':'not_started'}
        with foreground_scope(driver,'app') as error:self.assertEqual('target_busy',error['error'])
        self.assertEqual([],calls)

    def channel(self,capabilities,replies):
        client,peer=socket.socketpair();driver=object.__new__(InheritedHelperDriver)
        driver._sock=client;driver._f=client.makefile('rw',encoding='utf-8',newline='\n')
        driver.capabilities=set(capabilities);received=[]
        self.addCleanup(driver._f.close);self.addCleanup(client.close);self.addCleanup(peer.close)
        def server():
            stream=peer.makefile('rb')
            try:
                for reply in replies:
                    received.append(json.loads(stream.readline()))
                    peer.sendall(json.dumps(reply).encode()+b'\n')
            finally:stream.close()
        worker=threading.Thread(target=server);worker.start()
        self.addCleanup(worker.join,2)
        return driver,received

    def test_bound_task_is_named_on_target_requests_only(self):
        from haejo import task
        binding=SimpleNamespace(task_id='t-'+'1'*24,invocation='2'*32)
        ok={'type':'observation','tree':''}
        driver,received=self.channel({'session.task_claims'},[ok]*4)
        token=task.current.set(binding)
        try:
            driver._send({'type':'observe','target':'app'})
            driver._send({'type':'foreground_begin','target':'app'})
            driver._send({'type':'release_targets'})
        finally:task.current.reset(token)
        driver._send({'type':'act','target':'app','action':{'name':'click','element_index':1}})
        identity={'task_id':binding.task_id,'invocation_id':binding.invocation}
        self.assertEqual([{'type':'observe','target':'app',**identity},{'type':'foreground_begin','target':'app',**identity},
                          {'type':'release_targets'},
                          {'type':'act','target':'app','action':{'name':'click','element_index':1}}],received)
        # A helper that does not know claims gets the request as before.
        driver,received=self.channel({'session.window_scope'},[ok])
        token=task.current.set(binding)
        try:driver._send({'type':'observe','target':'app'})
        finally:task.current.reset(token)
        self.assertEqual([{'type':'observe','target':'app'}],received)

    def test_lease_wait_rides_on_target_requests_when_set(self):
        from unittest import mock
        ok={'type':'observation','tree':''}
        for raw,sent in (('60',60),('1',1),('120',120),('0',None),('121',None),('6.5',None),('-3',None),('',None)):
            with self.subTest(raw=raw),mock.patch.dict('os.environ',{'HAEJO_LEASE_WAIT_SECONDS':raw}):
                driver,received=self.channel({'session.lease_wait'},[ok]*2)
                driver._send({'type':'observe','target':'app'})
                driver._send({'type':'release_targets'})
                extra={} if sent is None else {'lease_wait_seconds':sent}
                self.assertEqual([{'type':'observe','target':'app',**extra},{'type':'release_targets'}],received)
        with mock.patch.dict('os.environ',{'HAEJO_LEASE_WAIT_SECONDS':'60'}):
            # A helper that has no such field gets the request as before.
            driver,received=self.channel({'session.task_claims'},[ok])
            driver._send({'type':'observe','target':'app'})
            self.assertEqual([{'type':'observe','target':'app'}],received)

    def test_busy_reply_says_which_task_and_how_long(self):
        busy={'type':'error','error':'target_busy','effect':'not_started','retryable':True,
              'holder_task':'t-'+'a'*24,'claim_expires_in':42,'retry_after_ms':42000}
        plain={'type':'error','error':'target_busy','effect':'not_started','retryable':True,'holder_pid':7,'retry_after_ms':1000}
        front=dict(busy,error='input_busy',retry_after_ms=1500)
        driver,_=self.channel(set(),[busy,plain,front])
        reply=driver._send({'type':'act','target':'app','action':{'name':'click','element_index':2}})
        self.assertEqual((42000,'t-'+'a'*24,42),(reply['retry_after_ms'],reply['holder_task'],reply['claim_expires_in']))
        self.assertIn('t-'+'a'*24,reply['hint']);self.assertIn('42초',reply['hint'])
        self.assertNotIn('hint',driver._send({'type':'observe','target':'app'}))
        self.assertIn('2초',driver.foreground_begin('app')['hint'])
        for banned in ('never','do not','must not','마세요','금지'):self.assertNotIn(banned,reply['hint'].lower())

    def test_task_end_asks_for_the_front_back_only_over_a_launcher_channel(self):
        from unittest import mock
        from haejo import helper,task
        task_id='t-'+'3'*24
        with mock.patch.object(InheritedHelperDriver,'_shared',None),mock.patch.dict('os.environ',clear=False) as env:
            env.pop('HAEJO_HELPER_FD',None)
            self.assertIsNone(helper.release_task_claims(task_id))
            client,peer=socket.socketpair()
            self.addCleanup(client.close);self.addCleanup(peer.close)
            env['HAEJO_HELPER_FD']=str(client.fileno())
            peer.sendall(b'{"type":"task_released","front_returned":true}\n')
            self.assertEqual({'type':'task_released','front_returned':True},helper.release_task_claims(task_id))
            self.assertEqual({'type':'task_release','task_id':task_id},json.loads(peer.recv(4096)))
            client.fileno()                                  # the inherited descriptor stays open
        driver,received=self.channel({'session.task_claims'},[{'type':'task_released','front_returned':False}])
        driver._ready=True
        with mock.patch.object(InheritedHelperDriver,'_shared',driver):
            self.assertFalse(helper.release_task_claims(task_id)['front_returned'])
        self.assertEqual([{'type':'task_release','task_id':task_id}],received)
        # A task kept somewhere other than the product directory is not this computer's screen task.
        with mock.patch('haejo.helper.release_task_claims') as release,__import__('tempfile').TemporaryDirectory() as root:
            task._release_claims(task_id,root);release.assert_not_called()
            task._release_claims(task_id,task.tasks_root());release.assert_called_once_with(task_id)

