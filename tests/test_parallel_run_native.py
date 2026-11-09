"""Opt-in signed CLI receiving and stop test; only owned fixture windows."""
import json
import os
from pathlib import Path
import plistlib
import subprocess
import sys
import tempfile
import threading
import time
import unittest

ROOT=Path(__file__).resolve().parents[1]


@unittest.skipUnless(sys.platform=='darwin' and os.environ.get('HAEJO_RUN_NATIVE_PARALLEL_TESTS')=='1',
                     'opt-in signed parallel command receiving test')
class ParallelCommandNative(unittest.TestCase):
    def test_four_window_receiving_conflict_refusal_and_scoped_stop(self):
        import Quartz
        def pointer():
            point=Quartz.CGEventGetLocation(Quartz.CGEventCreate(None))
            return [point.x,point.y]
        with tempfile.TemporaryDirectory(prefix='haejo-parallel-command-') as directory:
            base=Path(directory);app=base/'OwnedParallel.app'
            binary=app/'Contents/MacOS/OwnedParallel';binary.parent.mkdir(parents=True)
            subprocess.run(['swiftc',str(ROOT/'tests/fixtures/NativeWindowParallelFixture.swift'),'-o',str(binary)],check=True,capture_output=True)
            target='ai.callabo.haejo.parallelcommandfixture';name='Haejo Parallel Command Fixture'
            (app/'Contents/Info.plist').write_bytes(plistlib.dumps({'CFBundleIdentifier':target,
                'CFBundleExecutable':'OwnedParallel','CFBundleName':name,'CFBundlePackageType':'APPL','LSUIElement':True}))
            subprocess.run(['codesign','--force','--sign','-',str(app)],check=True,capture_output=True)
            state=base/'state.json'
            fixture=subprocess.Popen([str(binary),str(state)],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
            def read():return json.loads(state.read_text())
            def execute(manifest):
                path=base/'jobs.json';path.write_text(json.dumps(manifest))
                result=subprocess.run([str(ROOT/'launcher/haejo'),'parallel',str(path),'--helper','--json'],
                                      capture_output=True,text=True,timeout=80)
                try:receipt=json.loads(result.stdout)
                except ValueError:self.fail('parallel command did not return one JSON report: '+result.stderr)
                return result.returncode,receipt
            def job(i):
                value=f'parallel-value-{i}'
                safety={'effects':['write_ephemeral'],'reversibility':'reversible',
                        'resource':{'object_type':'owned fixture entry','scope':'entry'}}
                field={'identifier':'window-editor'}
                return {'id':f'worker-{i}','window_id':ids[i], 'flow':{
                    'schema':2,'name':'owned-window-edit','target':target,'steps':[
                        {'action':'set_value','selector':field,'params':{'value':value},'safety':safety,
                         'postcondition':{'field':field,'attribute':'Value','equals':value}},
                        {'action':'click','selector':{'identifier':'window-press'},'safety':safety,
                         'postcondition':{'field':field,'attribute':'Value','equals':value+'|pressed'}}]}}
            try:
                end=time.monotonic()+10
                while not state.exists():
                    self.assertLess(time.monotonic(),end);time.sleep(.05)
                before=read();ids=[row['window_id'] for row in before['windows']];original_pointer=pointer()
                code,result=execute({'schema':1,'jobs':[job(i) for i in range(4)]})
                self.assertEqual(0,code,result);self.assertTrue(result['ok'],result)
                self.assertEqual(4,len({row['helper_pid'] for row in result['jobs']}),result)
                after=read()
                self.assertEqual([f'parallel-value-{i}|pressed' for i in range(4)], [row['value'] for row in after['windows']])
                self.assertEqual([1]*4,[row['presses'] for row in after['windows']])
                self.assertEqual([0]*4,[row['input_events'] for row in after['windows']])
                self.assertEqual(before['front'],after['front']);self.assertEqual(original_pointer,pointer())
                duplicate=job(0);duplicate['id']='duplicate'
                code,refusal=execute({'schema':1,'jobs':[job(0),duplicate]})
                self.assertEqual(2,code);self.assertEqual('parallel_duplicate_window',refusal['error'])
                self.assertEqual('not_started',refusal['effect']);self.assertEqual(after['windows'],read()['windows'])
                stale=job(0);stale['window_id']=0xffffffff
                code,lost=execute({'schema':1,'jobs':[stale]})
                self.assertEqual(1,code,lost);self.assertEqual('window_scope_lost',lost['jobs'][0]['error'])
                self.assertEqual('not_started',lost['jobs'][0]['effect'])

                # Use the same runtime stop protocol as the installed menu, but
                # target only this fixture's runs. Never stop other user work.
                source=base/'main.swift';stopper=base/'stop-owned-runs'
                source.write_text('''import Foundation
let wanted = CommandLine.arguments[1]
let output = CommandLine.arguments[2]
let stopAllWindow = CommandLine.arguments.count>3 ? UInt32(CommandLine.arguments[3]) : nil
var runs:[String:HaejoRuntimeStatus.Run] = [:]
var done = false
let center = DistributedNotificationCenter.default()
let observer = center.addObserver(forName:HaejoRuntimeStatus.status,object:nil,queue:.main) { note in
    guard !done, let info=note.userInfo, let run=HaejoRuntimeStatus.Run(info), run.target==wanted else { return }
    if let window=stopAllWindow {
        guard run.active, run.windowID==window else { return }
        done=true
        center.postNotificationName(Notification.Name("ai.callabo.haejo.runtime.stop-all"),object:nil,
            userInfo:["schema":1,"uid":getuid(),"targets":[CommandLine.arguments[4]]],deliverImmediately:true)
        try! JSONSerialization.data(withJSONObject:["stop_all":true]).write(to:URL(fileURLWithPath:output))
        return
    }
    if run.active { runs[run.id]=run } else { runs.removeValue(forKey:run.id) }
    if runs.count>=2 {
        done=true
        for id in runs.keys { center.postNotificationName(HaejoRuntimeStatus.stop,object:nil,userInfo:["id":id],deliverImmediately:true) }
        try! JSONSerialization.data(withJSONObject:["stopped_runs":runs.count]).write(to:URL(fileURLWithPath:output))
    }
}
let end=Date().addingTimeInterval(15)
while !done && Date()<end {
    center.postNotificationName(HaejoRuntimeStatus.query,object:nil,userInfo:nil,deliverImmediately:true)
    RunLoop.current.run(until:Date().addingTimeInterval(0.05))
}
center.removeObserver(observer)
exit(done ? 0 : 1)
''')
                subprocess.run(['swiftc',str(source),str(ROOT/'RuntimeStatus.swift'),'-o',str(stopper)],check=True,capture_output=True)
                stop_report=base/'stopped.json'
                listener=subprocess.Popen([str(stopper),name,str(stop_report)])
                try:
                    pending=[]
                    for i in range(2):
                        item=job(i);step=item['flow']['steps'][0]
                        step.update(action='read',params={},safety={'effects':['read'],'reversibility':'reversible'})
                        step['postcondition']['equals']='never-the-current-value'
                        item['flow']['steps']=[step];pending.append(item)
                    code,stopped=execute({'schema':1,'jobs':pending})
                    self.assertEqual(0,listener.wait(timeout=18),'runtime stop did not find both owned runs')
                    self.assertEqual(1,code,stopped)
                    self.assertTrue(all(row['error']=='aborted_by_user' for row in stopped['jobs']),stopped)
                    self.assertEqual(after['windows'],read()['windows'])
                finally:
                    if listener.poll() is None:listener.kill();listener.wait()

                # One window is held by another live session. Stop-all must
                # cancel the batch's blocked child as well as its visible run.
                held=subprocess.Popen([str(ROOT/'launcher/haejo'),'session',target,'--helper','--window-id',str(ids[0])],
                    stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,text=True,bufsize=1,start_new_session=True)
                ready=threading.Event()
                def drain():
                    try:
                        for line in held.stdout:
                            if line.startswith('HAEJO_SESSION_READY'):ready.set()
                    except ValueError:pass
                reader=threading.Thread(target=drain,daemon=True);reader.start()
                all_listener=None
                try:
                    self.assertTrue(ready.wait(15),'owned holding session not ready')
                    all_listener=subprocess.Popen([str(stopper),name,str(base/'stop-all.json'),str(ids[1]),target])
                    blocked=job(0);visible=job(1)
                    visible['flow']['steps']=[pending[1]['flow']['steps'][0]]
                    code,cancelled=execute({'schema':1,'jobs':[blocked,visible]})
                    self.assertEqual(0,all_listener.wait(timeout=18))
                    self.assertEqual(1,code,cancelled);self.assertTrue(cancelled.get('cancelled'),cancelled)
                    from haejo.parallel_run import _stop
                    _stop(held);reader.join(2)
                    time.sleep(.25)
                    self.assertEqual(after['windows'],read()['windows'],'a cancelled waiting job dispatched after release')
                finally:
                    if all_listener is not None and all_listener.poll() is None:all_listener.kill();all_listener.wait()
                    if held.poll() is None:
                        from haejo.parallel_run import _stop
                        _stop(held)
                    held.stdin.close();held.stdout.close()
                print(json.dumps({'passed':True,'four_distinct_helpers':True,'four_window_values_received':True,
                      'same_window_rejected_before_dispatch':True,'stale_window_refused':True,
                      'two_owned_runs_stopped':True,'stop_all_cancels_waiting_job':True,'no_input_after_release':True,
                      'global_input_events':0,'foreground_unchanged':True,
                      'pointer_unchanged':True,'model_calls':0}),flush=True)
            finally:
                fixture.terminate();fixture.wait(timeout=5)
