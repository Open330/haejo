"""Exercise real AppKit run rows and selected-stop routing without showing UI."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]


@unittest.skipUnless(sys.platform=='darwin','AppKit menu implementation')
class RuntimeMenuTests(unittest.TestCase):
    def test_rows_are_stable_removed_and_stopped_individually(self):
        source=(ROOT/'setup/main.swift').read_text()
        start=source.index('    func updateRuntimeRunItems() {')
        methods=source[start:source.index('    @objc func stopRuntime() {',start)]
        harness='''import AppKit
final class Controller:NSObject {
    var runtimeRuns:[String:(HaejoRuntimeStatus.Run,Date)] = [:]
    var runtimeRunItems:[String:NSMenuItem] = [:]
    var runtimeStop:NSMenuItem?
'''+methods+'''
}
let app=NSApplication.shared
app.setActivationPolicy(.prohibited)
let controller=Controller(), menu=NSMenu()
controller.runtimeStop=menu.addItem(withTitle:"all",action:nil,keyEquivalent:"")
menu.addItem(.separator())
let a=UUID().uuidString,b=UUID().uuidString,c=UUID().uuidString
func run(_ id:String,_ window:Int,_ stopped:Bool=false)->HaejoRuntimeStatus.Run {
    HaejoRuntimeStatus.Run(["schema":1,"uid":getuid(),"id":id,"pid":getpid(),"target":"Owned Fixture",
        "active":true,"stopped":stopped,"window_id":window,"phase":"running","action":"click"])!
}
controller.runtimeRuns=[a:(run(a,1),Date()),b:(run(b,2),Date())]
controller.updateRuntimeRunItems()
let original=controller.runtimeRunItems[b]!
controller.updateRuntimeRunItems()
let stable=menu.items.count==4 && controller.runtimeRunItems[b] === original
controller.runtimeRuns=[b:(run(b,2,true),Date()),c:(run(c,3),Date())]
controller.updateRuntimeRunItems()
let removed=controller.runtimeRunItems[a]==nil && menu.items.count==4
let disabled=controller.runtimeRunItems[b]!.submenu!.items[0].isEnabled == false
var received:[String]=[]
let center=DistributedNotificationCenter.default()
let observer=center.addObserver(forName:HaejoRuntimeStatus.stop,object:nil,queue:.main) { note in
    if let id=note.userInfo?["id"] as? String, [a,b,c].contains(id) { received.append(id) }
}
let selected=controller.runtimeRunItems[c]!.submenu!.items[0]
controller.stopRuntimeRun(selected)
RunLoop.current.run(until:Date().addingTimeInterval(0.15))
controller.runtimeRuns.removeValue(forKey:c)
controller.updateRuntimeRunItems()
controller.stopRuntimeRun(selected)
RunLoop.current.run(until:Date().addingTimeInterval(0.15))
center.removeObserver(observer)
let result:[String:Bool]=["stable_rows":stable,"stale_removed":removed,"stopped_disabled":disabled,
    "selected_stop_only":received == [c],"remaining_rows":menu.items.count==3]
print(String(data:try! JSONSerialization.data(withJSONObject:result),encoding:.utf8)!)
'''
        with tempfile.TemporaryDirectory(prefix='haejo-runtime-menu-') as directory:
            base=Path(directory);swift=base/'main.swift';swift.write_text(harness);binary=base/'menu-test'
            built=subprocess.run(['swiftc','-sdk','/Library/Developer/CommandLineTools/SDKs/MacOSX.sdk',str(swift),
                                  str(ROOT/'RuntimeStatus.swift'),'-o',str(binary)],capture_output=True,text=True,timeout=60)
            self.assertEqual(0,built.returncode,built.stderr)
            checked=subprocess.run([str(binary)],capture_output=True,text=True,timeout=15)
            self.assertEqual(0,checked.returncode,checked.stderr)
            self.assertEqual({'stable_rows':True,'stale_removed':True,'stopped_disabled':True,
                              'selected_stop_only':True,'remaining_rows':True},json.loads(checked.stdout))
