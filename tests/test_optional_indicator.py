"""Execute the actual optional-display gate with injected presentation results."""
from pathlib import Path
import json,shutil,subprocess,tempfile,unittest,sys
ROOT=Path(__file__).resolve().parents[1]
@unittest.skipUnless(sys.platform=='darwin' and shutil.which('swift'),'macOS Swift required')
class OptionalIndicatorTests(unittest.TestCase):
    def test_presentation_failures_do_not_block_but_lock_and_stop_do(self):
        source=(ROOT/'helper/HaejoHelper.swift').read_text()
        code=source[source.index('func readyControlTargetFrames('):source.index('/// Presentation diagnostic only.')].replace('CGSessionCopyCurrentDictionary()', 'testSessionDictionary()')
        harness=r'''
import Foundation
import CoreGraphics
struct DispatchQueue {
 static let main=DispatchQueue()
 func sync<T>(execute:()->T)->T {execute()}
}
struct NSScreen {
 let frame:CGRect
 static var screens=[NSScreen(frame:CGRect(origin:CGPoint(x:0,y:0),size:CGSize(width:1000,height:1000)))]
}
let kCGSessionOnConsoleKey="console"
var locked=false
func testSessionDictionary()->[String:Any]? { ["console":true,"CGSSessionScreenIsLocked":locked] }
final class Abort {var isStopped=false}
let abortState=Abort()
final class RuntimePublisher {static let shared=RuntimePublisher();var showBanner=true}
final class Panel {var hidden=false;func orderOut(_ sender:Any?){hidden=true}}
var controlPanel:Panel?=Panel()
var controlPanelDiagnostic:[String:Bool]=[:]
var lastIndicatorMode="",lastIndicatorRefusal="",mode=""
var reads=0,shows=0
func showControlIndicator(forPID pid:pid_t)->Bool {true}
func controlTargetFrames(forPID pid:pid_t,primaryTop:CGFloat)->[CGRect]? {
 reads+=1
 return mode=="missing_frames" ? nil:[]
}
func controlPanelHasNoRoom(_ value:[String:Bool])->Bool {value == ["frame_available":false]}
func showControlPanel(forPID pid:pid_t,targets:[CGRect])->Bool {
 shows+=1
 if mode=="no_room" {controlPanelDiagnostic=["frame_available":false]}
 if mode=="other_space" {controlPanelDiagnostic=["active_space":false]}
 if mode=="lock_during" {locked=true}
 if mode=="stop_during" {abortState.isStopped=true}
 return mode=="visible"
}
'''+code+r'''
var rows:[[String:Any]]=[]
for name in ["visible","banner_off","missing_frames","no_room","other_space","pending","locked","stopped","lock_during","stop_during"] {
 mode=name;reads=0;shows=0;controlPanelDiagnostic=[:];controlPanel=Panel()
 locked=name=="locked";abortState.isStopped=name=="stopped"
 RuntimePublisher.shared.showBanner=name != "banner_off"
 let allowed=ensureVisibleControl(forPID:42)
 rows.append(["case":name,"allowed":allowed,"reads":reads,"shows":shows,"mode":lastIndicatorMode,"reason":lastIndicatorRefusal])
}
print(String(data:try! JSONSerialization.data(withJSONObject:rows),encoding:.utf8)!)
'''
        with tempfile.TemporaryDirectory() as directory:
            p=Path(directory)/'main.swift';p.write_text(harness)
            r=subprocess.run(['swift',str(p)],capture_output=True,text=True,timeout=30)
        self.assertEqual(0,r.returncode,r.stderr)
        rows={x['case']:x for x in json.loads(r.stdout)}
        for name in ['visible','banner_off','missing_frames','no_room','other_space','pending']:
            self.assertTrue(rows[name]['allowed'],rows[name])
        for name in ['locked','stopped','lock_during','stop_during']:
            self.assertFalse(rows[name]['allowed'],rows[name])
        self.assertEqual('session_not_visible',rows['locked']['reason'])
        self.assertEqual('aborted_by_user',rows['stopped']['reason'])
        self.assertEqual(1,rows['missing_frames']['reads'])
        self.assertEqual(0,rows['missing_frames']['shows'])
        self.assertEqual(0,rows['banner_off']['reads'])
        self.assertEqual('menu_only_panel_pending',rows['pending']['mode'])
