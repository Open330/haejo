import Foundation
import AppKit
import ApplicationServices
import Darwin

struct ParallelWindowScope {
    let pid: pid_t
    let id: CGWindowID
    let start: Double
    let window: AXUIElement
}
final class ParallelWindowState: @unchecked Sendable {
    static let shared = ParallelWindowState()
    private let lock = NSLock()
    private var requestEnd:Double?
    var requestDeadline:Double? {
        get { lock.lock();defer { lock.unlock() };return requestEnd }
        set { lock.lock();requestEnd=newValue;lock.unlock() }
    }
    private var ownsForeground=false
    var foregroundOwned:Bool {
        get { lock.lock();defer { lock.unlock() };return ownsForeground }
        set { lock.lock();ownsForeground=newValue;lock.unlock() }
    }
    private var value: ParallelWindowScope?
    var current: ParallelWindowScope? {
        get { lock.lock(); defer { lock.unlock() }; return value }
        set { lock.lock(); value = newValue; lock.unlock() }
    }
}
func parallelRefusal(_ code: String) -> [String:Any] {
    ["type":"error","error":code,"effect":"not_started","retryable":code.hasSuffix("busy")]
}
func waitForResource(_ lease: TactoScopeLease, _ scope: String, shared: Bool = false,
                     deadline: Double? = nil, cancelled: () -> Bool = { abortState.isStopped }) -> Bool {
    if scope=="global-input", ParallelWindowState.shared.foregroundOwned { return true }
    let until = min(deadline ?? .infinity,ParallelWindowState.shared.requestDeadline ?? .infinity,ProcessInfo.processInfo.systemUptime+10)
    while true {
        if cancelled() { return false }
        if lease.take(scope,shared:shared) { return true }
        if ProcessInfo.processInfo.systemUptime >= until { return false }
        usleep(20_000)
    }
}
func windowScopePointerRefusal() -> [String:Any]? {
    ParallelWindowState.shared.current == nil ? nil : parallelRefusal("window_scope_requires_ax")
}
func windowScopeActionProblem(_ msg:[String:Any], _ scope:ParallelWindowScope) -> String? {
    guard ["observe","act","probe"].contains(msg["type"] as? String ?? ""),
          msg["document_token"] == nil else { return "window_scope_requires_app" }
    guard msg["type"] as? String == "act" else { return nil }
    guard msg["credential_origin"] == nil, msg["sensitive_input_authorized"] == nil, msg["save_panel_token"] == nil,
          let action=msg["action"] as? [String:Any],
          let name=action["name"] as? String,
          ["read","click","set_value","type_text"].contains(name), action["point"] == nil,
          let raw=action["element_index"] as? NSNumber,
          CFGetTypeID(raw) != CFBooleanGetTypeID(), raw.doubleValue==Double(raw.intValue),
          latestObsID==msg["obs_id"] as? String, latestTargetPID==scope.pid,
          latestElements.indices.contains(raw.intValue),
          nativeProcessStartIdentity(scope.pid)==scope.start else { return "window_scope_requires_ax" }
    var diagnostic=WindowListingDiagnostic()
    let windows=realWindows(of:AXUIElementCreateApplication(scope.pid),diagnostic:&diagnostic)
    guard diagnostic.status=="ok",let window=windows.first(where:{nativeWindowID($0)==scope.id && CFEqual($0,scope.window)})
    else { return "window_scope_lost" }
    // A sheet/modal can affect the whole application's responder chain.
    if name != "read", windows.contains(where: {
        (attr($0,kAXModalAttribute as String) as? Bool)==true ||
        !(attr($0,"AXSheets") as? [AXUIElement] ?? []).isEmpty
    }) { return "window_scope_requires_app" }
    let element=latestElements[raw.intValue]
    do { try documentValidateElement(element,window:window) }
    catch { return "window_scope_changed" }
    if name=="click" {
        if ["AXPopUpButton","AXComboBox","AXMenuItem","AXMenu","AXMenuButton"].contains(str(element,kAXRoleAttribute as String) ?? "") {
            return "window_scope_requires_app"
        }
        var names: CFArray?
        guard AXUIElementCopyActionNames(element,&names) == .success,
              (names as? [String] ?? []).contains(kAXPressAction as String) else {
            return "window_scope_requires_ax"
        }
    }
    if ["set_value","type_text"].contains(name),
       !["AXTextField","AXTextArea","AXSearchField"].contains(str(element,kAXRoleAttribute as String) ?? "") {
        return "window_scope_requires_app"
    }
    return nil
}
final class ParallelSession {
    private var targets=TactoScopeLease()
    private var scope:ParallelWindowScope?
    private var unscoped=false
    private var foreground:TactoScopeLease?
    private var foregroundTarget:String?
    private func beginForeground(_ target:String,deadline:Double?,cancelled:()->Bool) -> [String:Any] {
        if foreground==nil {
            let lease=TactoScopeLease()
            guard waitForResource(lease,"global-input",deadline:deadline,cancelled:cancelled)
            else { return parallelRefusal(cancelled() ? (abortState.isStopped ? "aborted_by_user" : "client_disconnected") : "input_busy") }
            foreground=lease;foregroundTarget=target
            ParallelWindowState.shared.foregroundOwned=true
        }
        return ["type":"foreground_lease","acquired":true]
    }
    func respond(_ msg:[String:Any],connection:Int32) -> [String:Any] {
        if msg["type"] as? String=="release_targets" {
            guard Set(msg.keys)==Set(["type"]) else {return parallelRefusal("invalid_release_targets")}
            // A coordinator may prepare an app, yield it to another connection,
            // then return for a fresh observation without losing document pins.
            targets=TactoScopeLease()
            foreground=nil;foregroundTarget=nil;scope=nil;unscoped=false
            ParallelWindowState.shared.foregroundOwned=false
            ParallelWindowState.shared.current=nil
            latestObsID="";latestElements=[];latestProcessStart=nil
            latestTargetPID = -1;latestTargetName="";latestDocumentToken=nil
            pendingSelect=nil;spentMenu=nil;savePanelTokens.removeAll()
            return ["type":"targets_released","observation_invalidated":true]
        }
        if msg["type"] as? String=="foreground_end" {
            guard foregroundTarget==msg["target"] as? String else { return parallelRefusal("foreground_scope_changed") }
            ParallelWindowState.shared.foregroundOwned=false
            foreground=nil;foregroundTarget=nil
            return ["type":"foreground_lease","acquired":false]
        }
        if msg["type"] as? String=="window_list" { return handle(msg) }
        guard let target=msg["target"] as? String else { return handle(msg) }
        let began=ProcessInfo.processInfo.systemUptime
        let deadline=min(msg["click_deadline_uptime"] as? Double ?? .infinity,began+10)
        ParallelWindowState.shared.requestDeadline=deadline
        defer { ParallelWindowState.shared.requestDeadline=nil }
        if targets.holderPID == 0 {
            var peer: pid_t = 0
            var size = socklen_t(MemoryLayout<pid_t>.size)
            if getsockopt(connection, SOL_LOCAL, LOCAL_PEERPID, &peer, &size) == 0 { targets.holderPID = peer }
        }
        func disconnected() -> Bool {
            var channel=pollfd(fd:connection,events:0,revents:0)
            _ = poll(&channel,1,0)
            if channel.revents & Int16(POLLHUP|POLLERR|POLLNVAL) != 0 { return true }
            var byte:UInt8=0
            return recv(connection,&byte,1,MSG_PEEK|MSG_DONTWAIT)==0
        }
        func cancelled() -> Bool { abortState.isStopped || disconnected() }
        // A closed client is not a person pressing stop (2026-11-05: four
        // "aborted_by_user" with nobody touching anything).
        func stopCode() -> String { abortState.isStopped ? "aborted_by_user" : "client_disconnected" }
        func busy(_ scope: String) -> [String:Any] {
            var refusal = parallelRefusal("target_busy")
            if let holder = TactoScopeLease.holder(scope) {
                refusal.merge(holder) { current, _ in current }
                refusal["detail"] = "another Tacto client holds this app; finish or end that command (an idle session holds it only until its flow arrives)"
            }
            return refusal
        }
        if scope != nil && msg["window_scope_id"] == nil { return parallelRefusal("window_scope_changed") }
        let appShared=msg["window_scope_id"] != nil
        if !waitForResource(targets,"app-id:"+target.lowercased(),shared:appShared,
                            deadline:deadline,cancelled:cancelled) {
            return cancelled() ? parallelRefusal(stopCode()) : busy("app-id:"+target.lowercased())
        }
        guard let pid=pid(forBundle:target) else {
            if msg["type"] as? String=="foreground_begin" { return beginForeground(target,deadline:deadline,cancelled:cancelled) }
            return handle(msg)
        }
        if let number=msg["window_scope_id"] as? NSNumber {
            guard !unscoped,CFGetTypeID(number) != CFBooleanGetTypeID(),
                  number.doubleValue.isFinite,number.doubleValue==Double(number.uint32Value),number.uint32Value>0,
                  let start=nativeProcessStartIdentity(pid) else { return parallelRefusal("window_scope_changed") }
            let id=number.uint32Value
            if let fixed=scope {
                guard fixed.pid==pid,fixed.id==id,fixed.start==start else { return parallelRefusal("window_scope_changed") }
            } else {
                guard msg["type"] as? String=="observe" else { return parallelRefusal("window_scope_requires_observation") }
            }
            guard waitForResource(targets,"app:\(pid)",shared:true,deadline:deadline,cancelled:cancelled),
                  waitForResource(targets,"window:\(pid):\(start):\(id)",deadline:deadline,cancelled:cancelled)
            else { return cancelled() ? parallelRefusal(stopCode()) : busy("app:\(pid)") }
            var listing=WindowListingDiagnostic()
            let matches=realWindows(of:AXUIElementCreateApplication(pid),diagnostic:&listing).filter { nativeWindowID($0)==id }
            guard listing.status=="ok",matches.count==1 else { return parallelRefusal("window_scope_lost") }
            if let previous=scope,!CFEqual(previous.window,matches[0]) { return parallelRefusal("window_scope_changed") }
            let fixed=scope ?? ParallelWindowScope(pid:pid,id:id,start:start,window:matches[0])
            scope=fixed;ParallelWindowState.shared.current=fixed
            if let problem=windowScopeActionProblem(msg,fixed) { return parallelRefusal(problem) }
        } else {
            guard scope==nil else { return parallelRefusal("window_scope_changed") }
            guard waitForResource(targets,"app:\(pid)",deadline:deadline,cancelled:cancelled)
            else { return cancelled() ? parallelRefusal(stopCode()) : busy("app:\(pid)") }
            unscoped=true
        }
        if msg["type"] as? String=="foreground_begin" {
            return beginForeground(target,deadline:deadline,cancelled:cancelled)
        }
        if cancelled() { return parallelRefusal(stopCode()) }
        var reply=handle(msg)
        let ms=Int((ProcessInfo.processInfo.systemUptime-began)*1000)
        if ms>20 { reply["coordination_elapsed_ms"]=ms }
        return reply
    }
}

// Metadata only: discovery must not need an exclusive app lease while another
// agent is already working in one of its windows. Every later action repins.
func parallelWindowList(_ target:String) -> [String:Any] {
    guard let pid=pid(forBundle:target),let start=nativeProcessStartIdentity(pid) else {
        return parallelRefusal("target_not_found")
    }
    var diagnostic=WindowListingDiagnostic()
    let windows=realWindows(of:AXUIElementCreateApplication(pid),diagnostic:&diagnostic)
    guard ["ok","no_value"].contains(diagnostic.status) else { return parallelRefusal("window_list_unavailable") }
    let rows=windows.prefix(128).compactMap { window -> [String:Any]? in
        guard let id=nativeWindowID(window) else { return nil }
        return ["window_id":Int(id),"title":String((str(window,kAXTitleAttribute as String) ?? "").prefix(200))]
    }
    guard nativeProcessStartIdentity(pid)==start else { return parallelRefusal("target_changed") }
    return ["type":"windows","target":target,"pid":Int(pid),"process_start":start,"windows":rows]
}
