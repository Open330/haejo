"""Exercise the native metadata parser and preference reader, without live input."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]

@unittest.skipUnless(sys.platform == 'darwin', 'native Foundation implementation')
class RuntimeStatusTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix='tacto-runtime-test-')
        cls.folder = Path(cls.temp.name)
        source = cls.folder/'main.swift'
        source.write_text('''import Foundation
if CommandLine.arguments[1] == "preference" {
    print(TactoRuntimeStatus.showBanner(in:URL(fileURLWithPath:CommandLine.arguments[2])))
} else if CommandLine.arguments[1] == "helper" {
    let raw = try! JSONSerialization.jsonObject(with:Data(CommandLine.arguments[2].utf8)) as! [String:Any]
    let settings = TactoRuntimeStatus.helperSettings(raw["object"] as! [String:Any],environment:raw["environment"] as! [String:String])
    print("\\(settings.mode) \\(settings.idleSeconds)")
} else if CommandLine.arguments[1] == "summary" {
    var info = try! JSONSerialization.jsonObject(with:Data(CommandLine.arguments[2].utf8)) as! [String:Any]
    info["uid"] = getuid()
    if let run = TactoRuntimeStatus.Run(info) {
        print("\(run.windowID.map(String.init) ?? "-")|\(run.phase ?? "-")|\(run.action ?? "-")|\(run.outcome ?? "-")|\(run.summary)")
    } else { print("invalid") }
} else {
    let raw = try! JSONSerialization.jsonObject(with:Data(CommandLine.arguments[2].utf8)) as! [String:Any]
    var info = raw
    if info["uid"] as? String == "current" { info["uid"] = getuid() }
    if let run = TactoRuntimeStatus.Run(info) {
        print("valid \\(run.active) \\(run.stopped)")
    } else { print("invalid") }
}
''')
        cls.binary=cls.folder/'probe'
        subprocess.run(['swiftc',str(source),str(ROOT/'RuntimeStatus.swift'),'-o',str(cls.binary)],check=True,capture_output=True,text=True)
    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()
    def probe(self, mode, value):
        return subprocess.check_output([str(self.binary),mode,value],text=True).strip()
    def test_metadata_lifecycle_and_invalid_types(self):
        valid=dict(schema=1,uid='current',id='A9CC39E1-CCDD-46C5-8815-0ABABC136FEA',pid=123,target='Calculator',active=True,stopped=False)
        self.assertEqual(self.probe('metadata',json.dumps(valid)),'valid true false')
        self.assertEqual(self.probe('metadata',json.dumps(dict(valid,active=False,stopped=True))),'valid false true')
        for key,value in [('schema',True),('schema',1.5),('uid',-1),('uid',True),('id','not-uuid'),('pid',True),('pid',1.5),('pid',0),('pid',2**40),('target',''),('target','x'*257),('target','x\ny'),('active',1),('stopped','false')]:
            with self.subTest(key=key,value=value):
                self.assertEqual(self.probe('metadata',json.dumps(dict(valid,**{key:value}))),'invalid')
    def test_parallel_status_fields_are_optional_strict_and_truthful(self):
        base=dict(schema=1,id='A9CC39E1-CCDD-46C5-8815-0ABABC136FEA',pid=123,target='TextEdit',active=True,stopped=False)
        # Older helpers omit every extension; the run is still valid and plain.
        self.assertEqual(self.probe('summary',json.dumps(base)),'-|-|-|-|TextEdit')
        full=dict(base,window_id=4242,phase='waiting',action='set_value',outcome='dispatched')
        line=self.probe('summary',json.dumps(full))
        self.assertEqual(line,'4242|waiting|set_value|dispatched|TextEdit · 창 4242 · 대기 · 값 입력 전달됨(검증 전)')
        self.assertNotIn('검증됨',line); self.assertNotIn('verified',line)
        self.assertTrue(self.probe('summary',json.dumps(dict(base,phase='running',action='observe'))).endswith('TextEdit · 관측 중'))
        self.assertTrue(self.probe('summary',json.dumps(dict(base,phase='running',action='click',window_id=7))).endswith('창 7 · 클릭 중'))
        self.assertTrue(self.probe('summary',json.dumps(dict(full,outcome='not_started'))).endswith('값 입력 시작 안 됨'))
        self.assertTrue(self.probe('summary',json.dumps(dict(full,outcome='unknown'))).endswith('값 입력 결과 불명'))
        self.assertTrue(self.probe('summary',json.dumps(dict(full,stopped=True))).endswith('창 4242 · 중단됨'))
        self.assertTrue(self.probe('summary',json.dumps(dict(base,phase='running',action='type_text'))).endswith('텍스트 입력 중'))
        # A step the menu has no words for is still shown truthfully as sent.
        self.assertTrue(self.probe('summary',json.dumps(dict(base,phase='running',action='new_step'))).endswith('new_step 중'))
        # A malformed extension is dropped, never guessed, and never invalidates the run.
        for key,value in [('window_id',0),('window_id',True),('window_id',1.5),('window_id',2**33),('window_id','42'),
                          ('phase','done'),('phase',''),('action','Click'),('action','x'*33),('action','a b'),('action','클릭'),
                          ('outcome','verified'),('outcome','ok'),('outcome',True)]:
            with self.subTest(key=key,value=value):
                fields=self.probe('summary',json.dumps(dict(full,**{key:value}))).split('|')
                index=['window_id','phase','action','outcome'].index(key)
                self.assertEqual(fields[index],'-')
    def test_helper_publishes_only_accepted_scope_and_helper_owned_outcomes(self):
        text=(ROOT/'helper/TactoHelper.swift').read_text()
        publisher=text.split('final class RuntimePublisher {',1)[1].split('\n}\n',1)[0]
        for forbidden in ('title','value','"verified"','kAXTitle'):
            self.assertNotIn(forbidden,publisher.split('func publish(',1)[1].split('postNotificationName',1)[0])
        outcome=text.split('func runtimeOutcome(',1)[1].split('\n}\n',1)[0]
        self.assertIn('"acted"?: return "dispatched"',outcome)
        self.assertNotIn('verified',outcome)
        serve=text.split('@Sendable func serve(connection fd: Int32) {',1)[1].split('\n}\n',1)[0]
        self.assertIn('ParallelWindowState.shared.current?.id',serve)
        self.assertLess(serve.index('phase:"running"'),serve.index('session.respond('))
        self.assertLess(serve.index('session.respond('),serve.index('phase:"waiting"'))
        self.assertIn('kind != "ping"',serve)
        # Extensions are attached only to active publishes; inactive cleanup stays minimal.
        self.assertIn('if active {',publisher.split('func publish(',1)[1])
        reset=text.split('func resetPersistentSession(',1)[1].split('\n}\n',1)[0]
        self.assertIn('resetActivity()',reset)
    def test_esc_during_a_served_run_also_stops_waiting_parallel_jobs(self):
        text=(ROOT/'helper/TactoHelper.swift').read_text()
        monitor=text.split('func watchForAbort() {',1)[1].split('\n}\n',1)[0]
        forward=monitor.split('if abortState.isStopped && RuntimePublisher.shared.active {',1)[1]
        self.assertIn('TactoRuntimeStatus.stopAll',forward)
        self.assertIn('"schema":1,"uid":getuid()',forward)
        # The press is still judged against this run's epoch first.
        self.assertLess(monitor.index('abortState.note(at: ev.timestamp)'),monitor.index('TactoRuntimeStatus.stopAll'))

    def test_setup_menu_keeps_global_stop_and_adds_per_run_stop(self):
        text=(ROOT/'setup/main.swift').read_text()
        stop_all=text.split('@objc func stopRuntime() {',1)[1].split('\n    }\n',1)[0]
        self.assertIn('for id in runtimeRuns.keys',stop_all)
        self.assertIn('TactoRuntimeStatus.stopAll',stop_all)
        self.assertIn('"uid":getuid()',stop_all)
        one=text.split('@objc func stopRuntimeRun(',1)[1].split('\n    }\n',1)[0]
        self.assertIn('runtimeRuns[id] != nil',one)
        self.assertIn('userInfo:["id":id]',one)
        rows=text.split('func updateRuntimeRunItems() {',1)[1].split('\n    }\n',1)[0]
        self.assertIn('run.summary',rows)
        self.assertIn('!live.contains(id)',rows)
    def test_banner_preference_strict_default_and_opt_out(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder); file=root/'preferences.json'
            self.assertEqual(self.probe('preference',folder),'true')
            for value,expected in [(False,'false'),(True,'true'),(0,'true'),('false','true'),(None,'true')]:
                file.write_text(json.dumps(dict(schema=1,show_control_banner=value)))
                self.assertEqual(self.probe('preference',folder),expected)
            for text in ['{',json.dumps(dict(schema=True,show_control_banner=False)),json.dumps(dict(schema=2,show_control_banner=False)),' '*17000]:
                file.write_text(text)
                self.assertEqual(self.probe('preference',folder),'true')
            file.unlink()
            target=root/'elsewhere';target.write_text('{"schema":1,"show_control_banner":false}')
            file.symlink_to(target)
            self.assertEqual(self.probe('preference',folder),'true')
    def test_helper_defaults_gui_values_and_environment_priority(self):
        def probe(obj=None, env=None):
            return self.probe('helper',json.dumps({'object':obj or {},'environment':env or {}}))
        self.assertEqual('per_command 120',probe())
        self.assertEqual('warm 600',probe({'keep_helper_warm':True,'helper_idle_minutes':10}))
        self.assertEqual('warm 60',probe({'keep_helper_warm':True,'helper_idle_minutes':1}))
        self.assertEqual('per_command 120',probe({'keep_helper_warm':True},{'TACTO_HELPER_MODE':'per_command'}))
        self.assertEqual('warm 3',probe({}, {'TACTO_HELPER_MODE':'warm','TACTO_HELPER_IDLE_SECONDS':'3'}))
        self.assertEqual('per_command 120',probe({'keep_helper_warm':True},{'TACTO_HELPER_MODE':'resident'}))
        for value in (True,0,11,2.5,'10'):
            self.assertEqual('warm 120',probe({'keep_helper_warm':True,'helper_idle_minutes':value}))
        for value in (1,'true',None):
            self.assertEqual('per_command 120',probe({'keep_helper_warm':value}))
        for value in ('0','601','NaN','oops'):
            self.assertEqual('warm 120',probe({}, {'TACTO_HELPER_MODE':'warm','TACTO_HELPER_IDLE_SECONDS':value}))

    def test_opt_out_keeps_abort_and_session_guards_before_panel_placement(self):
        text=(ROOT/'helper/TactoHelper.swift').read_text()
        gate=text.split('func ensureVisibleControl(',1)[1].split('/// Why the last',1)[0]
        self.assertLess(gate.index('guard sessionVisible()'),gate.index('if !banner'))
        self.assertLess(gate.index('guard !abortState.isStopped'),gate.index('if !banner'))
        self.assertLess(gate.index('if !banner'),gate.index('readyControlTargetFrames('))
        self.assertNotIn('NSStatusBar.system.statusItem',text)
        self.assertIn('watchForAbort()',text)
