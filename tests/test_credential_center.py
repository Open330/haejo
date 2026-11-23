"""Native credential UI uses metadata previews and stdin-only local secrets."""
from pathlib import Path
import os
import subprocess
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]

@unittest.skipUnless(sys.platform=='darwin','AppKit required')
class CredentialCenterTests(unittest.TestCase):
    def test_native_management_actions_and_tab_layout(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory=Path(tmp);(directory/'ActivityCenter.swift').write_text((ROOT/'setup/ActivityCenter.swift').read_text().replace('private ',''))
            (directory/'main.swift').write_text(r'''
import AppKit
import QuartzCore
let app=NSApplication.shared;app.setActivationPolicy(.prohibited)
final class Recorder {
 let lock=NSLock();var calls:[[String]]=[]
 var vaults: [String: [String: Any]] = ["aaa-local":["kind":"keychain"]]
 var scopes: [String: [String: Any]] = [
  "aaa-login":["target":"com.apple.Safari","origin":"https://example.test","level":"login"]
 ]
 var failList = false
 func run(_ args:[String],_ data:Data?) throws -> [String:Any] {
  lock.lock()
  defer { lock.unlock() }
  calls.append(args)
  assert(!args.joined().contains("owned-ui-secret"))
  switch args.first {
  case "put":
   assert(data==Data("owned-ui-secret\n".utf8))
   return ["status":"credential_stored"]
  case "inspect":
   return ["target":"com.apple.Safari","origin":"https://example.test","level":"login","stages":2,"account_check":true,"review_digest":"owned-review-digest"]
  case "vault":
   let name = args[1]
   vaults[name] = args[2] == "--keychain" ? ["kind":"keychain"] : ["kind":"bitwarden","server":args[3]]
   return ["status":"vault_registered","vault":name]
  case "grant":
   let name = args[1]
   scopes[name] = ["target":"com.apple.Safari","origin":"https://example.test","level":args.contains("--fill-only") ? "fill" : "login"]
   return ["status":"credential_delegated","grant":name]
  case "revoke":
   scopes.removeValue(forKey:args[1])
   return ["status":"credential_grant_revoked"]
  case "list":
   if failList {
    failList = false
    return ["ok":false,"error":"credential_configuration_invalid"]
   }
   return ["grants":scopes.keys.sorted(),"scopes":scopes,"vaults":vaults]
  default:
   preconditionFailure("Unexpected credential operation")
  }
 }
}
let recorder=Recorder();let center=CredentialCenter(runner:recorder.run)
func settle() {
 let deadline=Date().addingTimeInterval(3)
 while center.busy && Date()<deadline {RunLoop.current.run(until:Date().addingTimeInterval(0.01))}
 assert(!center.busy)
}
center.reload();settle()
assert(center.grants.titleOfSelectedItem=="aaa-login")
center.providerName.stringValue="work"
center.provider.selectItem(at:1);center.providerChanged()
center.server.stringValue="https://vault.example.test"
center.registerProvider();settle()
assert(center.providers.titleOfSelectedItem=="work" && center.status.stringValue=="‘work’ 연결을 등록했습니다.")
center.server.stringValue="https://new.example.test"
center.registerProvider();settle()
assert(center.providers.titleOfSelectedItem=="work" && center.server.stringValue=="https://new.example.test")
assert(center.status.stringValue=="‘work’ 연결을 수정했습니다.")
center.server.stringValue="unsaved draft"
center.reload();settle()
assert(center.providers.titleOfSelectedItem=="work" && center.server.stringValue=="unsaved draft")
center.providers.selectItem(at:0);center.selectProvider()
assert(center.providerName.stringValue.isEmpty && center.server.stringValue.isEmpty && !center.server.isEnabled)

recorder.failList = true
center.providerName.stringValue="later"
center.registerProvider();settle()
assert(center.providers.item(withTitle:"work") != nil && center.providers.item(withTitle:"later") == nil)
assert(center.status.stringValue.contains("‘later’ 연결을 등록했습니다.") && center.status.stringValue.contains("목록을 갱신하지 못했습니다"))
center.reload();settle()
assert(center.providers.item(withTitle:"later") != nil)

center.secret.stringValue="owned-ui-secret";center.itemName.stringValue="owned-item";center.storeSecret();assert(center.secret.stringValue.isEmpty);settle()
center.review(URL(fileURLWithPath:"/owned-fixture.json"));settle();assert(center.savePlan.isEnabled)
center.grantName.stringValue="owned-login";center.level.selectItem(at:1);center.registerGrant();settle()
assert(recorder.calls.contains{ $0.contains("--review-digest") && $0.contains("owned-review-digest") && $0.contains("--fill-only") })
assert(center.grants.titleOfSelectedItem=="owned-login" && center.grantDetails.stringValue.contains("fill"))
assert(center.status.stringValue=="‘owned-login’ 위임을 저장했습니다." && !center.savePlan.isEnabled)
center.reload();settle();assert(center.grants.titleOfSelectedItem=="owned-login")
center.revoke();settle()
assert(recorder.calls.contains(["revoke","owned-login"]) && center.grants.item(withTitle:"owned-login")==nil)
assert(center.grants.titleOfSelectedItem=="aaa-login" && center.status.stringValue=="‘owned-login’ 위임을 취소했습니다.")
center.revoke();settle()
assert(center.grants.numberOfItems==0 && !center.revokeButton.isEnabled)
let workspace=ActivityCenter(refreshAutomatically:false)
workspace.credentialCenter=center
workspace.vaultTab.view=center.view
workspace.selectSettingsTab(.vault)
workspace.window!.setContentSize(NSSize(width:900,height:600))
let rootView=workspace.window!.contentView!
rootView.layoutSubtreeIfNeeded()
let content=center.view
content.layoutSubtreeIfNeeded()
assert(content.window === workspace.window)
let tabs=content.subviews.compactMap{$0 as? NSTabView}.first!
let output=URL(fileURLWithPath:CommandLine.arguments[1]);try! FileManager.default.createDirectory(at:output,withIntermediateDirectories:true)
for i in 0..<tabs.numberOfTabViewItems {
 tabs.selectTabViewItem(at:i);content.layoutSubtreeIfNeeded()
 let pane=tabs.selectedTabViewItem!.view!;pane.layoutSubtreeIfNeeded()
 func check(_ view:NSView) {
  if view.isHidden {return}
  if view is NSControl {
   let r=view.convert(view.bounds,to:content)
   let scroll=pane as! NSScrollView
   let document=scroll.documentView!
   let frame=view.convert(view.bounds,to:document)
   assert(r.minX>=0 && r.maxX<=content.bounds.width+1 && frame.minY>=0 && frame.maxY<=document.bounds.height+1,"control outside scrollable content: \(r)")
  }
  for v in view.subviews {check(v)}
 }
 check(pane)
 func redraw(_ view:NSView) {view.needsDisplay=true;view.displayIfNeeded();for v in view.subviews {redraw(v)}}
 redraw(rootView)
 CATransaction.flush();RunLoop.current.run(until:Date().addingTimeInterval(0.05));redraw(rootView)
 let image=rootView.bitmapImageRepForCachingDisplay(in:rootView.bounds)!
 rootView.cacheDisplay(in:rootView.bounds,to:image)
 try! image.representation(using:.png,properties:[:])!.write(to:output.appendingPathComponent("vault-tab-\(i).png"))
}
let permissions=NSView()
workspace.installPermissionsView(permissions)
center.secret.stringValue="owned-unsaved-secret"
let settingsNavigation=workspace.settingsNavigation
settingsNavigation.selectedSegment=1
assert(settingsNavigation.sendAction(settingsNavigation.action,to:settingsNavigation.target))
assert(workspace.isShowingPermissions && center.secret.stringValue.isEmpty && permissions.window === workspace.window)
workspace.selectSettingsTab(.vault)
tabs.selectTabViewItem(at:2)
assert(workspace.window!.makeFirstResponder(center.secret))
let activeEditor = center.secret.currentEditor()!
activeEditor.string="owned-unsaved-secret"
tabs.selectTabViewItem(at:0)
assert(center.secret.currentEditor() == nil && center.secret.stringValue.isEmpty && activeEditor.string.isEmpty)
center.secret.stringValue="owned-unsaved-secret"
workspace.navigate(workspace.historyButton)
assert(center.secret.stringValue.isEmpty)
workspace.selectSettingsTab(.vault)
center.secret.stringValue="owned-unsaved-secret"
workspace.window!.performClose(nil)
assert(center.secret.stringValue.isEmpty)
print("native credential management, stdin-only secret, immutable review and three tab layouts passed")
''')
            binary=directory/'fixture'
            result=subprocess.run(['swiftc','ActivityCenter.swift','main.swift','-o',str(binary)],cwd=directory,capture_output=True,text=True,timeout=90)
            self.assertEqual(0,result.returncode,result.stderr)
            artifacts=Path(os.environ.get('HAEJO_CREDENTIAL_UI_ARTIFACTS',str(directory/'render'))).absolute()
            result=subprocess.run([str(binary),str(artifacts)],capture_output=True,text=True,timeout=30)
            self.assertEqual(0,result.returncode,result.stderr)
            self.assertEqual(3,len(list(artifacts.glob('vault-tab-*.png'))))
