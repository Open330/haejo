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
func waitForResource(_ lease: HaejoScopeLease, _ scope: String, shared: Bool = false,
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
    guard ["observe","act","probe","tab_select"].contains(msg["type"] as? String ?? ""),
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
    private var targets=HaejoScopeLease()
    private var scope:ParallelWindowScope?
    private var unscoped=false
    private var foreground:HaejoScopeLease?
    private var foregroundTarget:String?
    private func beginForeground(_ target:String,deadline:Double?,cancelled:()->Bool) -> [String:Any] {
        if foreground==nil {
            let lease=HaejoScopeLease()
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
            targets=HaejoScopeLease()
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
            if let holder = HaejoScopeLease.holder(scope) {
                refusal.merge(holder) { current, _ in current }
                refusal["detail"] = "another Haejo client holds this app; finish or end that command (an idle session holds it only until its flow arrives)"
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
                guard ["observe","tab_select"].contains(msg["type"] as? String ?? "") else { return parallelRefusal("window_scope_requires_observation") }
            }
            guard waitForResource(targets,"app:\(pid)",shared:true,deadline:deadline,cancelled:cancelled),
                  waitForResource(targets,"window:\(pid):\(start):\(id)",deadline:deadline,cancelled:cancelled)
            else { return cancelled() ? parallelRefusal(stopCode()) : busy("app:\(pid)") }
            var listing=WindowListingDiagnostic()
            let matches=realWindows(of:AXUIElementCreateApplication(pid),diagnostic:&listing).filter { nativeWindowID($0)==id }
            guard listing.status=="ok",matches.count==1 else {
                var refusal=parallelRefusal("window_scope_lost")
                refusal["reason"]=windowAbsenceReason(pid,id)
                return refusal
            }
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
        // A native approval card waits inside handle(); it ends when this
        // request's caller goes away or stop is pressed.
        NativeApproval.callerGone=cancelled
        defer { NativeApproval.callerGone={ false } }
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
    let server=serverWindows(pid)
    var listed=Set<UInt32>()
    let rows=windows.prefix(128).compactMap { window -> [String:Any]? in
        guard let id=nativeWindowID(window) else { return nil }
        listed.insert(id)
        var row:[String:Any]=["window_id":Int(id),"title":String((str(window,kAXTitleAttribute as String) ?? "").prefix(200))]
        if let url=windowPageURL(window) { row["url"]=url }
        if let onScreen=server[id] { row["on_screen"]=onScreen }
        let tabs=browserTabRows(window,url:row["url"] as? String,title:row["title"] as? String ?? "")
        if !tabs.isEmpty { row["tabs"]=tabs }
        return row
    }
    guard nativeProcessStartIdentity(pid)==start else { return parallelRefusal("target_changed") }
    var reply:[String:Any]=["type":"windows","target":target,"pid":Int(pid),"process_start":start,"windows":rows,
                            "screen":screenState()]
    // Accessibility lists only what the app hands it. The window server also
    // knows windows on other Spaces; a window it has and accessibility omits
    // was seen missing for 30 s+ while `--window-id` still reached it
    // (Safari popup player, june-mba 2026-11-09), and read as "closed".
    let unlisted=server.filter { !listed.contains($0.key) }.sorted { $0.key < $1.key }.prefix(64).map { id,onScreen in
        ["window_id":Int(id),"reason":onScreen ? "enumeration_partial" : "not_on_active_space"] as [String:Any]
    }
    if !unlisted.isEmpty { reply["unlisted"]=Array(unlisted) }
    if rows.isEmpty, let reason=emptyListingReason(reply["screen"] as! [String:Any], unlisted:!unlisted.isEmpty) {
        reply["reason"]=reason
    }
    return reply
}

/// Layer-0 windows the window server has for this process: id -> on screen now.
/// Needs no screen-recording permission (ids and flags only, no titles).
func serverWindows(_ pid:pid_t) -> [UInt32:Bool] {
    guard let entries=CGWindowListCopyWindowInfo([.optionAll,.excludeDesktopElements],kCGNullWindowID) as? [[String:Any]] else { return [:] }
    // Browsers keep untitled internal surfaces at layer 0 (Safari: four
    // menu-bar-high strips, 18x20 badges, a 171x60 piece on screen;
    // jiun-MBP 2026-11-10). A real window has a title in the window server
    // when names are readable at all, and a window-sized frame otherwise.
    var rows:[(UInt32,Bool,String,CGRect)]=[]
    for entry in entries {
        guard (entry[kCGWindowOwnerPID as String] as? Int).map({ pid_t($0) })==pid,
              (entry[kCGWindowLayer as String] as? Int)==0,
              let number=entry[kCGWindowNumber as String] as? NSNumber,
              let bounds=entry[kCGWindowBounds as String] as? [String:Any],
              let rect=CGRect(dictionaryRepresentation:bounds as CFDictionary) else { continue }
        rows.append((number.uint32Value,(entry[kCGWindowIsOnscreen as String] as? Bool) ?? false,
                     entry[kCGWindowName as String] as? String ?? "",rect))
    }
    let namesReadable=rows.contains { !$0.2.isEmpty }
    var found:[UInt32:Bool]=[:]
    for (id,onScreen,name,rect) in rows {
        // Without screen recording no window has a name; a 215x131 untitled
        // Safari surface then passed a 160x120 floor (rc.38, 2026-11-10).
        if namesReadable ? name.isEmpty : (rect.width<320 || rect.height<200) { continue }
        found[id]=onScreen
    }
    return found
}

func screenState() -> [String:Any] {
    var state:[String:Any]=["display_asleep":CGDisplayIsAsleep(CGMainDisplayID()) != 0]
    if let session=CGSessionCopyCurrentDictionary() as? [String:Any] {
        state["locked"]=session["CGSSessionScreenIsLocked"] as? Bool == true
        state["on_console"]=session[kCGSessionOnConsoleKey as String] as? Bool ?? false
    }
    return state
}

func emptyListingReason(_ screen:[String:Any], unlisted:Bool) -> String? {
    if screen["locked"] as? Bool == true { return "screen_locked" }
    if screen["on_console"] as? Bool == false { return "session_not_on_console" }
    if screen["display_asleep"] as? Bool == true { return "display_asleep" }
    return unlisted ? "windows_not_listed" : nil
}

/// Why a window id this connection pinned cannot be found now.
func windowAbsenceReason(_ pid:pid_t,_ id:UInt32) -> String {
    let screen=screenState()
    if screen["locked"] as? Bool == true { return "screen_locked" }
    if screen["on_console"] as? Bool == false { return "session_not_on_console" }
    if screen["display_asleep"] as? Bool == true { return "display_asleep" }
    guard let onScreen=serverWindows(pid)[id] else { return "window_closed" }
    return onScreen ? "enumeration_partial" : "not_on_active_space"
}

/// The page a browser window shows, as origin + path (no query or fragment:
/// those can carry session tokens). A bounded breadth-first look for the
/// first AXWebArea; nil for non-web windows.
///
/// While a page shows a JavaScript alert, Safari replaces its web area with
/// the dialog and every window of that web process stops answering for page
/// content — exactly when a "lesson finished" popup must be found. The
/// address field still carries the full URL in AXHelp, so it is the fallback.
func windowPageURL(_ window:AXUIElement) -> String? {
    func cleaned(_ raw:String?) -> String? {
        guard let raw,raw.count<=4096,var parts=URLComponents(string:raw),
              let scheme=parts.scheme?.lowercased(),["http","https","file"].contains(scheme) else { return nil }
        parts.query=nil;parts.fragment=nil;parts.user=nil;parts.password=nil
        return parts.string.map { String($0.prefix(512)) }
    }
    var addressURL:String?=nil
    var queue:[(AXUIElement,Int)]=[(window,0)]
    var visited=0
    // Listing must stay cheap even when the app answers slowly.
    let deadline=ProcessInfo.processInfo.systemUptime+0.4
    while !queue.isEmpty && visited<400 && ProcessInfo.processInfo.systemUptime<deadline {
        let (node,depth)=queue.removeFirst();visited+=1
        _ = AXUIElementSetMessagingTimeout(node,0.25)
        if str(node,kAXRoleAttribute as String)=="AXWebArea" {
            if let url=cleaned((attr(node,"AXURL") as? URL)?.absoluteString ?? str(node,"AXURL")) { return url }
        }
        if addressURL==nil, depth<=4,
           str(node,kAXIdentifierAttribute as String)?.hasPrefix("WEB_BROWSER_ADDRESS_AND_SEARCH_FIELD")==true {
            // The address field shows the full URL in AXHelp while it is a
            // static label, and only host+path in AXValue as a text field
            // (no scheme; the window identifier says IsSecure=true|false).
            if let full=cleaned(str(node,kAXHelpAttribute as String)) {
                addressURL=full
            } else if let shown=str(node,kAXValueAttribute as String), !shown.isEmpty, !shown.contains(" ") {
                let secure=str(window,kAXIdentifierAttribute as String)?.contains("IsSecure=true")==true
                addressURL=cleaned(shown.contains("://") ? shown : (secure ? "https://" : "http://")+shown)
            }
        }
        guard depth<12,let children=attr(node,kAXChildrenAttribute as String) as? [AXUIElement] else { continue }
        for child in children.prefix(64) { queue.append((child,depth+1)) }
    }
    return addressURL
}

// MARK: - Browser tabs

struct BrowserTab {
    let element:AXUIElement
    let title:String
    let selected:Bool
    let pinned:Bool
}

/// The tabs of a browser window, in tab-bar order. Safari 27.2 lists them as
/// AXRadioButton (subrole AXTabButton) children of a group identified
/// "TabBar?isSeparate=…"; each carries AXTitle, AXValue 1 when selected, an
/// identifier "TabBarTab?…isPinned=…&isActive=…", AXPress, and no address.
/// Empty when the window shows no tab bar (one tab, or not a browser).
func browserTabs(_ window:AXUIElement) -> [BrowserTab] {
    var queue:[(AXUIElement,Int)]=[(window,0)]
    var visited=0
    let deadline=ProcessInfo.processInfo.systemUptime+0.4
    while !queue.isEmpty && visited<300 && ProcessInfo.processInfo.systemUptime<deadline {
        let (node,depth)=queue.removeFirst();visited+=1
        _ = AXUIElementSetMessagingTimeout(node,0.25)
        let role=str(node,kAXRoleAttribute as String) ?? ""
        if role=="AXWebArea" { continue }
        guard let children=attr(node,kAXChildrenAttribute as String) as? [AXUIElement] else { continue }
        if str(node,kAXIdentifierAttribute as String)?.hasPrefix("TabBar?")==true {
            let tabs=children.prefix(512).compactMap { child -> BrowserTab? in
                let id=str(child,kAXIdentifierAttribute as String) ?? ""
                guard str(child,kAXRoleAttribute as String)=="AXRadioButton",id.hasPrefix("TabBarTab") else { return nil }
                let title=str(child,kAXTitleAttribute as String) ?? str(child,kAXDescriptionAttribute as String) ?? ""
                let selected=id.contains("isActive=") ? id.contains("isActive=true")
                    : (attr(child,kAXValueAttribute as String) as? NSNumber)?.boolValue==true
                return BrowserTab(element:child,title:String(title.prefix(200)),selected:selected,
                                  pinned:id.contains("isPinned=true"))
            }
            if !tabs.isEmpty { return tabs }
        }
        guard depth<5 else { continue }
        for child in children.prefix(64) { queue.append((child,depth+1)) }
    }
    return []
}

/// Listing rows: `index`, `title`, `selected`, `pinned` when set, and `url`
/// for the selected tab (the only page whose web area exists; Safari gives a
/// background tab a title and no address). A browser window that shows no tab
/// bar has one tab: its page.
func browserTabRows(_ window:AXUIElement,url:String?,title:String) -> [[String:Any]] {
    let tabs=browserTabs(window)
    if tabs.isEmpty {
        guard let url else { return [] }
        return [["index":0,"title":title,"selected":true,"url":url]]
    }
    return tabs.prefix(256).enumerated().map { index,tab in
        // A tab opened in the background keeps a title made from its address
        // on its button even after its page loaded (Safari 27.2); the window
        // title is the page title of the tab that is showing.
        var row:[String:Any]=["index":index,"title":tab.selected && !title.isEmpty ? title : tab.title,"selected":tab.selected]
        if tab.pinned { row["pinned"]=true }
        if tab.selected, let url { row["url"]=url }
        return row
    }
}

let browserTabRoutes=["ax_press","window_pointer","front_pointer"]

/// Select one tab of the window this connection is pinned to, and say how.
/// Routes in order: AXPress on the tab button (background); a click bound to
/// the window, posted to the process (background); the real pointer with the
/// browser in front, the previous front app restored afterwards. Each route
/// is checked by the tab reporting selected; the reply carries the page the
/// window shows then.
func parallelTabSelect(_ request:[String:Any]) -> [String:Any] {
    guard Set(request.keys)==Set(["type","target","window_scope_id","tab"]),
          let msg=request["tab"] as? [String:Any],Set(msg.keys).isSubset(of:["index","title","route"]),
          let scope=ParallelWindowState.shared.current,
          let number=msg["index"] as? NSNumber,CFGetTypeID(number) != CFBooleanGetTypeID(),
          number.doubleValue==Double(number.intValue),number.intValue>=0,
          msg["title"] == nil || msg["title"] is String,
          msg["route"] == nil || browserTabRoutes.contains(msg["route"] as? String ?? "") else {
        return parallelRefusal("invalid_tab_select")
    }
    let window=scope.window,pid=scope.pid,index=number.intValue
    let before=windowPageURL(window)
    func page(_ route:String,_ extra:[String:Any]=[:]) -> [String:Any] {
        // The newly shown tab's web area can take a moment to replace the
        // previous one (two tabs on one address settle at the time limit).
        var url=windowPageURL(window)
        let until=ProcessInfo.processInfo.systemUptime+1.5
        while (url==nil || (route != "already_selected" && url==before)) && ProcessInfo.processInfo.systemUptime<until {
            usleep(100_000);url=windowPageURL(window)
        }
        let tabs=browserTabs(window)
        let shown=String((str(window,kAXTitleAttribute as String) ?? "").prefix(200))
        var reply:[String:Any]=["type":"tab_selected","window_id":Int(scope.id),"index":index,"route":route,
            "title":shown.isEmpty && tabs.indices.contains(index) ? tabs[index].title : shown]
        if let url { reply["url"]=url }
        return reply.merging(extra) { current,_ in current }
    }
    let tabs=browserTabs(window)
    if tabs.isEmpty {
        guard index==0,windowPageURL(window) != nil else { return parallelRefusal("tab_not_found") }
        return page("already_selected")
    }
    let windowTitle=String((str(window,kAXTitleAttribute as String) ?? "").prefix(200))
    guard tabs.indices.contains(index),
          (msg["title"] as? String).map({ $0==tabs[index].title || (tabs[index].selected && $0==windowTitle) }) ?? true else {
        var refusal=parallelRefusal("tab_changed")
        refusal["tabs"]=browserTabRows(window,url:windowPageURL(window),title:windowTitle)
        return refusal
    }
    if tabs[index].selected { return page("already_selected") }
    let tab=tabs[index].element
    func selected(within seconds:Double) -> Bool {
        let until=ProcessInfo.processInfo.systemUptime+seconds
        while true {
            let now=browserTabs(window)
            if now.indices.contains(index),now[index].selected { return true }
            if ProcessInfo.processInfo.systemUptime>=until || abortState.isStopped { return false }
            usleep(50_000)
        }
    }
    func described(_ error:Error) -> String {
        switch error {
        case NativeWindowInputError.refused(let text),NativeWindowInputError.unavailable(let text),
             NativeWindowInputError.needsForeground(let text): return text
        default: return "failed"
        }
    }
    func pointerFree(_ lease:HaejoScopeLease) -> String? {
        guard waitForResource(lease,"global-input",deadline:ProcessInfo.processInfo.systemUptime+5) else { return "input_busy" }
        return CGEventSource.buttonState(.combinedSessionState,button:.left) ? "pointer_in_use" : nil
    }
    var attempts:[[String:Any]]=[]
    var extra:[String:Any]=[:]
    for route in (msg["route"] as? String).map({ [$0] }) ?? browserTabRoutes {
        if abortState.isStopped { return parallelRefusal("aborted_by_user") }
        var problem:String?
        switch route {
        case "ax_press":
            var names:CFArray?
            if AXUIElementCopyActionNames(tab,&names) != .success || !(names as? [String] ?? []).contains(kAXPressAction as String) {
                problem="no_press_action"
            } else {
                let error=AXUIElementPerformAction(tab,kAXPressAction as CFString)
                // -25204 can report a press that did happen; the check decides.
                if error != .success && error.rawValue != -25204 { problem="press_failed_\(error.rawValue)" }
            }
        case "window_pointer":
            let lease=HaejoScopeLease()
            problem=pointerFree(lease)
            if problem==nil {
                _ = AXUIElementPerformAction(tab,"AXScrollToVisible" as CFString)
                do {
                    let click=try buildNativeWindowClick(captureNativeWindowBinding(tab,pid,expectedStart:scope.start))
                    try nativePIDPost(click.down,pid);usleep(40_000);try nativePIDPost(click.up,pid)
                    withExtendedLifetime(click.owners) {}
                } catch { problem=described(error) }
            }
            withExtendedLifetime(lease) {}
        default:
            let lease=HaejoScopeLease()
            problem=pointerFree(lease)
            if problem==nil { problem=frontPointerPress(tab,window:window,pid:pid,windowID:scope.id,done:{ selected(within:2) },report:&extra) }
            withExtendedLifetime(lease) {}
        }
        if problem==nil,selected(within:2) {
            if !attempts.isEmpty { extra["attempts"]=attempts }
            return page(route,extra)
        }
        attempts.append(["route":route,"result":problem ?? "not_selected"])
    }
    // A press or click that went out and left the tab unselected may have
    // landed on something else; a route that never sent one did nothing.
    var refusal=parallelRefusal("tab_select_failed")
    refusal["effect"]=attempts.contains { $0["result"] as? String=="not_selected" } ? "unknown" : "not_started"
    refusal["attempts"]=attempts
    return refusal.merging(extra) { current,_ in current }
}

/// The last route: the browser comes to the front, the real pointer presses
/// the tab, the pointer returns to where it was and the app that was in front
/// is put back.
func frontPointerPress(_ tab:AXUIElement,window:AXUIElement,pid:pid_t,windowID:CGWindowID,
                       done:() -> Bool,report:inout [String:Any]) -> String? {
    guard let previous=nativeFrontmostProcessPID(),let app=NSRunningApplication(processIdentifier:pid),
          let cursor=CGEvent(source:nil)?.location else { return "front_state_unavailable" }
    report["front_taken"]=previous != pid
    defer {
        CGWarpMouseCursorPosition(cursor)
        if previous != pid { report["front_restored"]=returnScreen(to:previous) }
    }
    _ = AXUIElementPerformAction(window,kAXRaiseAction as CFString)
    if previous != pid { _ = app.activate(options:[]) }
    let until=ProcessInfo.processInfo.systemUptime+2
    while nativeFrontmostProcessPID() != pid && ProcessInfo.processInfo.systemUptime<until { usleep(20_000) }
    guard nativeFrontmostProcessPID()==pid else { return "browser_not_in_front" }
    _ = AXUIElementPerformAction(tab,"AXScrollToVisible" as CFString)
    usleep(150_000)
    var raw:CFTypeRef?
    var origin=CGPoint.zero,size=CGSize.zero
    guard AXUIElementCopyAttributeValue(tab,kAXPositionAttribute as CFString,&raw) == .success,
          AXValueGetValue(raw as! AXValue,.cgPoint,&origin),
          AXUIElementCopyAttributeValue(tab,kAXSizeAttribute as CFString,&raw) == .success,
          AXValueGetValue(raw as! AXValue,.cgSize,&size),size.width>4,size.height>4 else { return "tab_frame_unavailable" }
    let point=CGPoint(x:origin.x+size.width/2,y:origin.y+size.height/2)
    // The pointer lands on whatever window is on top at that point: it must
    // be this browser window and this tab.
    let above=CGWindowListCopyWindowInfo([.optionOnScreenOnly,.excludeDesktopElements],kCGNullWindowID) as? [[String:Any]] ?? []
    let top=above.first { entry in
        guard (entry[kCGWindowLayer as String] as? Int)==0,
              let bounds=entry[kCGWindowBounds as String] as? [String:Any],
              let rect=CGRect(dictionaryRepresentation:bounds as CFDictionary) else { return false }
        return rect.contains(point)
    }
    guard (top?[kCGWindowNumber as String] as? NSNumber)?.uint32Value==windowID else { return "tab_covered" }
    var hit=elementAtPoint(point,pid:pid)
    var onTab=false
    for _ in 0..<8 {
        guard let node=hit else { break }
        if CFEqual(node,tab) { onTab=true;break }
        hit=attr(node,kAXParentAttribute as String).flatMap { CFGetTypeID($0)==AXUIElementGetTypeID() ? ($0 as! AXUIElement) : nil }
    }
    guard onTab,let source=CGEventSource(stateID:.hidSystemState),
          let down=CGEvent(mouseEventSource:source,mouseType:.leftMouseDown,mouseCursorPosition:point,mouseButton:.left),
          let up=CGEvent(mouseEventSource:source,mouseType:.leftMouseUp,mouseCursorPosition:point,mouseButton:.left)
    else { return "tab_not_under_pointer" }
    down.post(tap:.cghidEventTap);usleep(60_000);up.post(tap:.cghidEventTap)
    _ = done()
    return nil
}
