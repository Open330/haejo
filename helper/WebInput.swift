import Foundation
import AppKit
import ApplicationServices

// Web content (an element under an AXWebArea) answers accessibility calls
// differently from AppKit controls. Measured on Safari 27.2, macOS 27.2,
// 2026-11-12, against an owned page that reports what it received
// (docs/safari-capability-matrix.md):
//
//  - AXValue on a text control is applied through the page's editing
//    selection: it lands in whichever control holds DOM focus. On an unfocused
//    control the call answers success and nothing changes; with another field
//    focused, that other field took the text.
//  - AXFocused = true focuses the control and also activates Safari.
//    AXSelectedTextRange focuses it and leaves the person's app in front.
//  - AXSelectedText (the insert `type_text` uses elsewhere) answers success
//    and inserts nothing.
//  - Key events addressed to the window reach the focused control while
//    Safari stays behind, once that window is Safari's main window.
//  - Pointer events addressed to the window are not delivered to the page
//    while Safari is behind; with Safari in front they are.
//  - AXShowMenu on a <select> opens Safari's context menu. AXPress opens the
//    real pop-up menu, which is on screen but absent from the element tree;
//    it is found under the control by hit-testing.
//
// Each route below starts with the quietest means that was measured to work
// and moves to the next only when the control did not take the input. The
// reply names the route (`input_route`) and its level (`route_level`: L1
// accessibility, L2 window-addressed events behind the person's app, L3 the
// same with Safari in front, given back afterwards).

/// Set while a caller already holds the cross-process input lease, so a web
/// route reached through another action does not wait on its own lock.
nonisolated(unsafe) var webInputLeaseHeld = false

func withWebInputLease(deadline: Double, _ body: () -> [String: Any]) -> [String: Any] {
    if webInputLeaseHeld { return body() }
    let lease = HaejoScopeLease()
    guard waitForResource(lease, "global-input", deadline: deadline) else {
        return abortState.isStopped
            ? ["type": "error", "error": "aborted_by_user", "effect": "not_started"]
            : parallelRefusal("input_busy")
    }
    webInputLeaseHeld = true
    defer { webInputLeaseHeld = false; withExtendedLifetime(lease) {} }
    return body()
}

/// The web area this element belongs to, when it is web content.
func webAreaAncestor(_ element: AXUIElement, limit: Int = 80) -> AXUIElement? {
    var node = element
    for _ in 0..<limit {
        if str(node, kAXRoleAttribute as String) == "AXWebArea" { return node }
        guard let raw = attr(node, kAXParentAttribute as String),
              CFGetTypeID(raw) == AXUIElementGetTypeID() else { return nil }
        node = raw as! AXUIElement
    }
    return nil
}

/// A page's text control whose value can be written.
func webTextControl(_ element: AXUIElement) -> Bool {
    guard ["AXTextField", "AXTextArea", "AXSearchField", "AXComboBox"]
            .contains(str(element, kAXRoleAttribute as String) ?? ""),
          webAreaAncestor(element) != nil else { return false }
    var settable = DarwinBoolean(false)
    return AXUIElementIsAttributeSettable(element, kAXValueAttribute as CFString, &settable) == .success
        && settable.boolValue
}

func webElementWindow(_ element: AXUIElement) -> AXUIElement? {
    guard let raw = attr(element, kAXWindowAttribute as String),
          CFGetTypeID(raw) == AXUIElementGetTypeID() else { return nil }
    return (raw as! AXUIElement)
}

func webElementFocused(_ element: AXUIElement) -> Bool {
    (attr(element, kAXFocusedAttribute as String) as? Bool) == true
}

private func webWait(_ seconds: Double, until done: () -> Bool) -> Bool {
    let end = ProcessInfo.processInfo.systemUptime + seconds
    repeat {
        if done() { return true }
        Thread.sleep(forTimeInterval: 0.02)
    } while ProcessInfo.processInfo.systemUptime < end
    return done()
}

/// Give this control DOM focus while Safari stays where it is. Returns the
/// means that worked, or nil when none did.
func webFocusBehind(_ element: AXUIElement) -> String? {
    if webElementFocused(element) { return "already_focused" }
    let length = (str(element, kAXValueAttribute as String) ?? "").utf16.count
    var caret = CFRange(location: length, length: 0)
    if let value = AXValueCreate(.cfRange, &caret),
       AXUIElementSetAttributeValue(element, kAXSelectedTextRangeAttribute as CFString, value) == .success,
       webWait(0.3, until: { webElementFocused(element) }) {
        return "ax_selected_text_range"
    }
    var advertised: CFArray?
    if AXUIElementCopyActionNames(element, &advertised) == .success,
       (advertised as? [String] ?? []).contains(kAXPressAction as String),
       AXUIElementPerformAction(element, kAXPressAction as CFString) == .success,
       webWait(0.3, until: { webElementFocused(element) }) {
        return "ax_press"
    }
    return nil
}

/// What taking the front for one input reports back.
struct WebForeground {
    var taken = false
    var restored = true
    var previousBundle = ""
    var fields: [String: Any] {
        guard taken else { return [:] }
        var out: [String: Any] = ["foreground_taken": true, "front_restored": restored,
                                  "previous_front": previousBundle, "pointer_moved": false]
        // Left in front: the run stops sending input, as for any step after
        // which the target was seen in front.
        if !restored { out["activated_target"] = true }
        return out
    }
}

/// Run `body` with the target app in front, then put the app that was in front
/// back. The real pointer is not moved. `body` receives false when the app
/// could not be brought forward, and nothing was sent.
func withWebForeground<T>(pid: pid_t, window: AXUIElement?, _ body: (Bool) -> T) -> (T, WebForeground) {
    var report = WebForeground()
    if isFrontmost(pid: pid) { return (body(true), report) }
    let previous = nativeFrontmostProcessPID()
    report.previousBundle = previous.flatMap { NSRunningApplication(processIdentifier: $0)?.bundleIdentifier } ?? ""
    if let window { _ = AXUIElementSetAttributeValue(window, kAXMainAttribute as CFString, kCFBooleanTrue) }
    NSRunningApplication(processIdentifier: pid)?.activate(options: [])
    let front = webWait(1.0, until: { isFrontmost(pid: pid) })
    report.taken = true
    let result = body(front)
    if let previous, previous != pid {
        report.restored = returnScreen(to: previous)
    } else {
        report.restored = false
    }
    return (result, report)
}

private func webRouteReply(_ name: String, _ obsID: String, route: String, level: String,
                           foreground: WebForeground = WebForeground(),
                           extra: [String: Any] = [:]) -> [String: Any] {
    var reply: [String: Any] = ["type": "acted", "action": name, "obs_id": obsID,
                                "input_route": route, "route_level": level]
    reply.merge(foreground.fields) { _, new in new }
    reply.merge(extra) { _, new in new }
    return reply
}

// MARK: - Keys addressed to the window

/// Post `text` one character at a time to the control's window. Stops when the
/// control loses focus, the person presses stop, or `stillFront` says the app
/// left the front. Returns how many characters were posted and why it stopped.
private func webPostText(_ text: String, element: AXUIElement, pid: pid_t, windowID: CGWindowID,
                         deadline: Double, stillFront: () -> Bool = { true }) -> (posted: Int, problem: String?) {
    var posted = 0
    for character in text {
        guard !abortState.isStopped else { return (posted, "aborted_by_user") }
        guard ProcessInfo.processInfo.systemUptime < deadline else { return (posted, "input_deadline_expired") }
        guard webElementFocused(element), stillFront() else { return (posted, "input_focus_changed") }
        do {
            let pair = try buildNativeWindowText(windowID, text: String(character))
            try withExtendedLifetime(pair.owners) {
                try nativePIDPost(pair.down, pid)
                try nativePIDPost(pair.up, pid)
            }
        } catch {
            return (posted, "key_event_unavailable")
        }
        posted += 1
        Thread.sleep(forTimeInterval: 0.012)
    }
    return (posted, nil)
}

/// Type into a focused web control with key events: first with Safari behind
/// (its window made Safari's main window), then with Safari in front.
func webTypeText(_ element: AXUIElement, pid: pid_t, text: String, obsID: String, name: String,
                 replaceAll: Bool, focusRoute: String?, deadline: Double) -> [String: Any] {
    guard let window = webElementWindow(element), let windowID = nativeWindowID(window) else {
        return ["type": "error", "error": "action_failed", "effect": "not_started",
                "detail": "web control has no window to address keys to"]
    }
    let app = AXUIElementCreateApplication(pid)
    func value() -> String { str(element, kAXValueAttribute as String) ?? "" }
    func selectAll() {
        guard replaceAll else { return }
        var all = CFRange(location: 0, length: value().utf16.count)
        if let range = AXValueCreate(.cfRange, &all) {
            _ = AXUIElementSetAttributeValue(element, kAXSelectedTextRangeAttribute as CFString, range)
        }
    }
    let before = value()
    func received() -> Bool {
        webWait(0.6, until: { replaceAll ? value() == text : value() != before })
    }
    var focus = focusRoute ?? webFocusBehind(element)
    if focus != nil {
        // L2: the app stays behind. Its main window is put back afterwards.
        let formerMain = attr(app, kAXMainWindowAttribute as String)
        let wasMain = (attr(window, kAXMainAttribute as String) as? Bool) == true
        if !wasMain { _ = AXUIElementSetAttributeValue(window, kAXMainAttribute as CFString, kCFBooleanTrue) }
        defer {
            if !wasMain, let raw = formerMain, CFGetTypeID(raw) == AXUIElementGetTypeID(), !isFrontmost(pid: pid) {
                _ = AXUIElementSetAttributeValue(raw as! AXUIElement, kAXMainAttribute as CFString, kCFBooleanTrue)
            }
        }
        if wasMain || webWait(0.4, until: { (attr(window, kAXMainAttribute as String) as? Bool) == true }) {
            selectAll()
            let sent = webPostText(text, element: element, pid: pid, windowID: windowID, deadline: deadline)
            if let problem = sent.problem {
                return ["type": "error", "error": problem, "effect": sent.posted > 0 ? "unknown" : "not_started",
                        "input_route": "window_keys", "route_level": "L2", "characters_posted": sent.posted]
            }
            if received() {
                return webRouteReply(name, obsID, route: "window_keys", level: "L2",
                                     extra: ["focus_route": focus!, "characters_posted": sent.posted,
                                             "value_read_back": replaceAll])
            }
        }
    }
    // L3: nothing arrived behind the person's app. Same keys, Safari in front.
    let (outcome, foreground) = withWebForeground(pid: pid, window: window) { front -> [String: Any] in
        guard front else {
            return ["type": "error", "error": "needs_foreground", "effect": "not_started", "needs_foreground": true,
                    "detail": "the browser did not come forward"]
        }
        if !webElementFocused(element) {
            _ = AXUIElementSetAttributeValue(element, kAXFocusedAttribute as CFString, kCFBooleanTrue)
            guard webWait(0.4, until: { webElementFocused(element) }) else {
                return ["type": "error", "error": "action_failed", "effect": "not_started",
                        "detail": "web control did not take focus"]
            }
            focus = "ax_focused"
        }
        selectAll()
        let sent = webPostText(text, element: element, pid: pid, windowID: windowID, deadline: deadline,
                               stillFront: { isFrontmost(pid: pid) })
        if let problem = sent.problem {
            return ["type": "error", "error": problem, "effect": sent.posted > 0 ? "unknown" : "not_started",
                    "characters_posted": sent.posted]
        }
        guard received() else {
            return ["type": "error", "error": "input_not_received", "effect": "unknown",
                    "characters_posted": sent.posted,
                    "detail": "keys were posted and the control's value did not change"]
        }
        return ["type": "acted", "characters_posted": sent.posted]
    }
    if outcome["type"] as? String == "acted" {
        var extra = outcome
        extra["focus_route"] = focus ?? "ax_focused"
        extra["value_read_back"] = replaceAll
        return webRouteReply(name, obsID, route: "foreground_keys", level: "L3", foreground: foreground, extra: extra)
    }
    var failure = outcome
    failure["input_route"] = "foreground_keys"
    failure["route_level"] = "L3"
    failure.merge(foreground.fields) { _, new in new }
    return failure
}

// MARK: - Text value

/// Write a whole value into a web text control. The control is focused first
/// (the write follows DOM focus) and the value is read back; a control that
/// does not keep it is typed into instead.
func webSetValue(_ element: AXUIElement, pid: pid_t, value: String, obsID: String, name: String,
                 deadline: Double) -> [String: Any] {
    func current() -> String? { str(element, kAXValueAttribute as String) }
    var focus = webFocusBehind(element)
    var foreground = WebForeground()
    if focus == nil {
        // No quiet means focused it: AXFocused does, and brings Safari
        // forward, so the front is given back as soon as focus is held.
        let (took, report) = withWebForeground(pid: pid, window: webElementWindow(element)) { front -> Bool in
            guard front else { return false }
            _ = AXUIElementSetAttributeValue(element, kAXFocusedAttribute as CFString, kCFBooleanTrue)
            return webWait(0.4, until: { webElementFocused(element) })
        }
        foreground = report
        guard took, webElementFocused(element) else {
            var refusal: [String: Any] = ["type": "error", "error": "action_failed", "effect": "not_started",
                                          "detail": "web control did not take focus"]
            refusal.merge(foreground.fields) { _, new in new }
            return refusal
        }
        focus = "ax_focused"
    }
    let before = current()
    guard webElementFocused(element) else {
        return ["type": "error", "error": "action_failed", "effect": "not_started",
                "detail": "web control lost focus before the write"]
    }
    let wrote = AXUIElementSetAttributeValue(element, kAXValueAttribute as CFString, value as CFTypeRef)
    if wrote == .success, webWait(0.4, until: { current() == value }) {
        return webRouteReply(name, obsID, route: "ax_value_focused", level: foreground.taken ? "L3" : "L1",
                             foreground: foreground, extra: ["focus_route": focus!, "value_read_back": true])
    }
    if wrote == .success, current() != before {
        // Taken and reformatted by the page (a mask, a trimmed value).
        return webRouteReply(name, obsID, route: "ax_value_focused", level: foreground.taken ? "L3" : "L1",
                             foreground: foreground,
                             extra: ["focus_route": focus!, "value_read_back": false,
                                     "note": "the control holds a different text than was written — observe it"])
    }
    guard !value.isEmpty, nativeWindowTextValid(String(value.prefix(1))),
          !value.unicodeScalars.contains(where: { $0.value < 0x20 || $0.value == 0x7F }) else {
        return ["type": "error", "error": "action_failed", "effect": wrote == .success ? "unknown" : "not_started",
                "detail": "the control did not keep the value and it cannot be typed"]
    }
    var typed = webTypeText(element, pid: pid, text: value, obsID: obsID, name: name, replaceAll: true,
                            focusRoute: webElementFocused(element) ? focus : nil, deadline: deadline)
    typed["fallback_from"] = "ax_value_focused"
    return typed
}

// MARK: - <select>

private func webPopupWindows(_ pid: pid_t) -> [CGWindowID: CGRect] {
    var found: [CGWindowID: CGRect] = [:]
    guard let list = CGWindowListCopyWindowInfo([.optionOnScreenOnly], kCGNullWindowID) as? [[String: Any]] else {
        return found
    }
    for entry in list {
        guard (entry[kCGWindowOwnerPID as String] as? NSNumber)?.int32Value == pid,
              (entry[kCGWindowLayer as String] as? NSNumber)?.intValue == 101,
              let number = (entry[kCGWindowNumber as String] as? NSNumber)?.uint32Value,
              let raw = entry[kCGWindowBounds as String],
              let bounds = CGRect(dictionaryRepresentation: raw as! CFDictionary) else { continue }
        found[number] = bounds
    }
    return found
}

private func webMenu(at point: CGPoint, pid: pid_t) -> AXUIElement? {
    guard let hit = elementAtPoint(point, pid: pid) else { return nil }
    let role = str(hit, kAXRoleAttribute as String)
    if role == "AXMenu" { return hit }
    guard role == "AXMenuItem", let raw = attr(hit, kAXParentAttribute as String),
          CFGetTypeID(raw) == AXUIElementGetTypeID(),
          str(raw as! AXUIElement, kAXRoleAttribute as String) == "AXMenu" else { return nil }
    return (raw as! AXUIElement)
}

private func webMenuItems(_ menu: AXUIElement) -> [(title: String, item: AXUIElement)] {
    ((attr(menu, kAXChildrenAttribute as String) as? [AXUIElement]) ?? []).compactMap { item in
        guard let title = str(item, kAXTitleAttribute as String), !title.isEmpty else { return nil }
        return (title, item)
    }
}

/// The open pop-up menu of this <select>: on screen, not in the element tree.
/// It is drawn over the control, so it is looked for under the control's
/// centre and inside each pop-up window the browser shows, and accepted only
/// when it lists the control's current value.
private func webOpenMenu(for control: AXUIElement, pid: pid_t) -> AXUIElement? {
    let selected = str(control, kAXValueAttribute as String)
    func owned(_ menu: AXUIElement?) -> AXUIElement? {
        guard let menu else { return nil }
        let titles = webMenuItems(menu).map { $0.title }
        guard !titles.isEmpty, selected == nil || selected!.isEmpty || titles.contains(selected!) else { return nil }
        return menu
    }
    var points: [CGPoint] = []
    if let frame = try? windowInputFrame(control) { points.append(CGPoint(x: frame.midX, y: frame.midY)) }
    for bounds in webPopupWindows(pid).values {
        points.append(CGPoint(x: bounds.midX, y: bounds.midY))
        points.append(CGPoint(x: bounds.midX, y: bounds.minY + min(12, bounds.height / 2)))
    }
    for point in points {
        if let menu = owned(webMenu(at: point, pid: pid)) { return menu }
    }
    return nil
}

/// Close a pop-up this action opened and did not choose from.
private func webCloseMenu(_ menu: AXUIElement, control: AXUIElement, pid: pid_t) -> Bool {
    let before = Set(webPopupWindows(pid).keys)
    _ = AXUIElementPerformAction(menu, "AXCancel" as CFString)
    if webWait(0.5, until: { webOpenMenu(for: control, pid: pid) == nil }) { return true }
    // Choosing the value it already has changes nothing and closes it.
    if let selected = str(control, kAXValueAttribute as String),
       let same = webMenuItems(menu).first(where: { $0.title == selected }) {
        _ = AXUIElementPerformAction(same.item, kAXPressAction as CFString)
    }
    return webWait(0.5, until: { webOpenMenu(for: control, pid: pid) == nil })
        || Set(webPopupWindows(pid).keys).isSubset(of: before) && webOpenMenu(for: control, pid: pid) == nil
}

/// Choose an option of a page's <select> by its label.
func webSelectOption(_ control: AXUIElement, pid: pid_t, want: String, obsID: String, name: String,
                     gate: (AXUIElement) -> [String: Any]?) -> [String: Any] {
    if str(control, kAXValueAttribute as String) == want {
        return webRouteReply(name, obsID, route: "web_popup_menu", level: "L1",
                             extra: ["selected": want, "already_selected": true])
    }
    func open() -> AXUIElement? {
        if let menu = webOpenMenu(for: control, pid: pid) { return menu }
        if (attr(control, "AXExpanded") as? Bool) == true {
            // Marked open with no menu on screen: closed first, then opened once.
            _ = AXUIElementSetAttributeValue(control, "AXExpanded" as CFString, kCFBooleanFalse)
            _ = webWait(0.3, until: { (attr(control, "AXExpanded") as? Bool) != true })
        }
        let pressed = AXUIElementPerformAction(control, kAXPressAction as CFString)
        guard pressed == .success || pressed == .cannotComplete else { return nil }
        var menu: AXUIElement?
        _ = webWait(1.2, until: { menu = webOpenMenu(for: control, pid: pid); return menu != nil })
        return menu
    }
    func choose(_ menu: AXUIElement) -> [String: Any] {
        let items = webMenuItems(menu)
        let matches = items.filter { $0.title == want }
        func refuse(_ detail: String, _ extra: [String: Any] = [:]) -> [String: Any] {
            let closed = webCloseMenu(menu, control: control, pid: pid)
            var refusal: [String: Any] = ["type": "error", "error": "action_failed",
                                          "effect": closed ? "not_started" : "unknown",
                                          "menu_left_open": !closed, "option_selected": false,
                                          "reobserve_required": true, "detail": detail,
                                          "options": Array(items.map { $0.title }.prefix(40))]
            refusal.merge(extra) { _, new in new }
            return refusal
        }
        guard matches.count == 1 else {
            return refuse(matches.isEmpty ? "no option has this label" : "more than one option has this label")
        }
        if (attr(matches[0].item, kAXEnabledAttribute as String) as? Bool) == false {
            return refuse("this option is disabled")
        }
        if abortState.isStopped {
            return refuse("stopped before choosing", ["error": "aborted_by_user"])
        }
        if var refusal = gate(matches[0].item) {
            let closed = webCloseMenu(menu, control: control, pid: pid)
            refusal["menu_left_open"] = !closed
            return refusal
        }
        let pressed = AXUIElementPerformAction(matches[0].item, kAXPressAction as CFString)
        guard pressed == .success || pressed == .cannotComplete else {
            return refuse("the option could not be pressed (\(pressed.rawValue))")
        }
        let read = webWait(0.8, until: { str(control, kAXValueAttribute as String) == want })
        var reply: [String: Any] = ["type": "acted", "selected": want]
        if !read {
            reply["unverified"] = "selection_unconfirmed"
            reply["reads_as"] = str(control, kAXValueAttribute as String) ?? NSNull()
        }
        if webOpenMenu(for: control, pid: pid) != nil { reply["menu_left_open"] = true }
        return reply
    }
    if let menu = open() {
        var chosen = choose(menu)
        chosen["input_route"] = "web_popup_menu"
        chosen["route_level"] = "L1"
        if chosen["type"] as? String == "acted" { chosen["action"] = name; chosen["obs_id"] = obsID }
        return chosen
    }
    // The menu did not appear with the browser behind: once more in front.
    let (outcome, foreground) = withWebForeground(pid: pid, window: webElementWindow(control)) { front -> [String: Any] in
        guard front else {
            return ["type": "error", "error": "needs_foreground", "effect": "unknown", "needs_foreground": true,
                    "reobserve_required": true, "detail": "the pop-up menu did not open and the browser did not come forward"]
        }
        guard let menu = open() else {
            return ["type": "error", "error": "action_failed", "effect": "unknown", "reobserve_required": true,
                    "detail": "the pop-up menu did not open"]
        }
        return choose(menu)
    }
    var reply = outcome
    reply["input_route"] = "foreground_popup_menu"
    reply["route_level"] = "L3"
    reply.merge(foreground.fields) { _, new in new }
    if reply["type"] as? String == "acted" { reply["action"] = name; reply["obs_id"] = obsID }
    return reply
}

// MARK: - Pointer click with the browser in front

/// The part of `click` that concerns page content and the pointer route.
/// Returns nil for an ordinary click, which goes on to AXPress.
func webClickRoute(_ action: [String: Any], _ element: AXUIElement, pid: pid_t, obsID: String, target: String,
                   deadline: Double, guarded: Bool, pointerClick: () -> [String: Any]) -> [String: Any]? {
    let web = webAreaAncestor(element) != nil
    guard let route = action["route"] else {
        guard web, str(element, kAXRoleAttribute as String) == "AXPopUpButton" else { return nil }
        // Pressing a page's <select> only opens its pop-up menu, which stays
        // on the person's screen: choosing is select_option.
        return ["type": "error", "error": "use_select_option", "effect": "not_started",
                "detail": "a page's <select> is chosen with select_option and option_label (or set_value with the label)"]
    }
    // The caller asks for real pointer events: a control that answers AXPress
    // with nothing (it opens on pointerdown).
    guard route as? String == "pointer", !guarded, action["point"] == nil else {
        return ["type": "error", "error": "action_failed", "effect": "not_started",
                "detail": "click route must be \"pointer\" on an observed element"]
    }
    guard web else {
        var pointer = pointerClick()
        pointer["route_level"] = "L2"
        return pointer
    }
    // Addressed by the element's centre as a window point: a control that acts
    // on pointerdown may be gone before the release, which an element-bound
    // click would stop at.
    guard let window = webElementWindow(element), let frame = try? windowInputFrame(element),
          let windowFrame = try? windowInputFrame(window) else {
        return ["type": "error", "error": "action_failed", "effect": "not_started",
                "detail": "the page control has no position in its window"]
    }
    let centre = CGPoint(x: frame.midX, y: frame.midY)
    let inWindow = CGPoint(x: centre.x - windowFrame.minX, y: centre.y - windowFrame.minY)
    return withWebInputLease(deadline: deadline) {
        webPointerClick(pid: pid, window: window, element: element, at: centre) {
            prepareBackgroundWindow(obsID, target, window, pid, deadline: deadline, point: inWindow)
        }
    }
}

/// A click the page must receive as real pointer events (a control that opens
/// on pointerdown). Window-addressed pointer events reach web content only
/// while the browser is in front, so the front is taken for the click and
/// given back; the person's pointer stays where it is.
func webPointerClick(pid: pid_t, window: AXUIElement?, element: AXUIElement, at centre: CGPoint,
                     click: () -> [String: Any]) -> [String: Any] {
    /// The control, or something inside it, is what is under its centre.
    func uncovered() -> Bool {
        guard var hit = elementAtPoint(centre, pid: pid) else { return false }
        for _ in 0..<12 {
            if CFEqual(hit, element) { return true }
            guard let raw = attr(hit, kAXParentAttribute as String),
                  CFGetTypeID(raw) == AXUIElementGetTypeID() else { return false }
            hit = raw as! AXUIElement
        }
        return false
    }
    let (outcome, foreground) = withWebForeground(pid: pid, window: window) { front -> [String: Any] in
        guard front else {
            return ["type": "error", "error": "needs_foreground", "effect": "not_started", "needs_foreground": true,
                    "detail": "the browser did not come forward"]
        }
        // The window server needs a moment to make the window key.
        Thread.sleep(forTimeInterval: 0.15)
        guard uncovered() else {
            return ["type": "error", "error": "action_failed", "effect": "not_started",
                    "detail": "something else is shown over the page control"]
        }
        return click()
    }
    var reply = outcome
    if reply["type"] as? String == "acted" {
        reply["input_route"] = "foreground_element_click"
        reply["action"] = "click"
    }
    reply["route_level"] = "L3"
    reply.merge(foreground.fields) { _, new in new }
    return reply
}

// MARK: - <input type="date">

/// The browser's date picker for a page's date field: a small window of its
/// own holding one date control whose value can be written.
private func webDatePickers(_ pid: pid_t) -> [(window: AXUIElement, area: AXUIElement)] {
    let app = AXUIElementCreateApplication(pid)
    return ((attr(app, kAXWindowsAttribute as String) as? [AXUIElement]) ?? []).compactMap { window in
        guard str(window, kAXSubroleAttribute as String) != "AXStandardWindow",
              let area = ((attr(window, kAXChildrenAttribute as String) as? [AXUIElement]) ?? [])
                .first(where: { str($0, kAXRoleAttribute as String) == "AXDateTimeArea" }) else { return nil }
        var settable = DarwinBoolean(false)
        guard AXUIElementIsAttributeSettable(area, kAXValueAttribute as CFString, &settable) == .success,
              settable.boolValue else { return nil }
        return (window, area)
    }
}

private func webDate(_ text: String) -> (date: Date, year: Int, month: Int, day: Int)? {
    let parts = text.split(separator: "-", omittingEmptySubsequences: false)
    guard parts.count == 3, parts[0].count == 4, parts[1].count == 2, parts[2].count == 2,
          let year = Int(parts[0]), let month = Int(parts[1]), let day = Int(parts[2]) else { return nil }
    var components = DateComponents()
    components.year = year; components.month = month; components.day = day; components.hour = 12
    let calendar = Calendar(identifier: .gregorian)
    guard let date = calendar.date(from: components),
          calendar.dateComponents([.year, .month, .day], from: date) == DateComponents(year: year, month: month, day: day)
    else { return nil }
    return (date, year, month, day)
}

/// Set a page's date field to `YYYY-MM-DD`: open its picker with AXPress,
/// write the picker's date, then close the picker with Escape addressed to the
/// page's window (the picker offers no accessibility action that closes it).
func webSetDate(_ control: AXUIElement, pid: pid_t, value: String, obsID: String, name: String) -> [String: Any] {
    guard let wanted = webDate(value) else {
        return ["type": "error", "error": "action_failed", "effect": "not_started",
                "detail": "a page's date field takes YYYY-MM-DD"]
    }
    func shows() -> Bool {
        guard let raw = attr(control, kAXValueAttribute as String), let date = raw as? Date else { return false }
        let got = Calendar(identifier: .gregorian).dateComponents([.year, .month, .day], from: date)
        return got.year == wanted.year && got.month == wanted.month && got.day == wanted.day
    }
    func owned(_ picker: AXUIElement, _ before: [AXUIElement]) -> Bool {
        !before.contains(where: { CFEqual($0, picker) })
    }
    let before = webDatePickers(pid).map { $0.window }
    guard before.isEmpty else {
        return ["type": "error", "error": "action_failed", "effect": "not_started", "reobserve_required": true,
                "detail": "a date picker is already open in this browser"]
    }
    let pressed = AXUIElementPerformAction(control, kAXPressAction as CFString)
    guard pressed == .success || pressed == .cannotComplete else {
        return ["type": "error", "error": "action_failed", "effect": axActionFailureEffect(pressed),
                "detail": "the date field could not be opened (\(pressed.rawValue))"]
    }
    var picker: (window: AXUIElement, area: AXUIElement)?
    _ = webWait(1.2, until: { picker = webDatePickers(pid).first(where: { owned($0.window, before) }); return picker != nil })
    guard let picker else {
        return ["type": "error", "error": "action_failed", "effect": "unknown", "reobserve_required": true,
                "detail": "the date picker did not open"]
    }
    let wrote = AXUIElementSetAttributeValue(picker.area, kAXValueAttribute as CFString, wanted.date as CFTypeRef)
    let read = wrote == .success && webWait(0.8, until: shows)
    // Close what this action opened, whether or not the date was taken.
    var closedBy = "none"
    func open() -> Bool { webDatePickers(pid).contains(where: { CFEqual($0.window, picker.window) }) }
    if open(), let window = webElementWindow(control), let windowID = nativeWindowID(window) {
        let wasMain = (attr(window, kAXMainAttribute as String) as? Bool) == true
        if !wasMain { _ = AXUIElementSetAttributeValue(window, kAXMainAttribute as CFString, kCFBooleanTrue) }
        if wasMain || webWait(0.4, until: { (attr(window, kAXMainAttribute as String) as? Bool) == true }) {
            for kind in [NSEvent.EventType.keyDown, .keyUp] {
                guard open(), let event = NSEvent.keyEvent(with: kind, location: .zero, modifierFlags: [],
                        timestamp: ProcessInfo.processInfo.systemUptime, windowNumber: Int(windowID), context: nil,
                        characters: "\u{1B}", charactersIgnoringModifiers: "\u{1B}", isARepeat: false, keyCode: 53),
                      let key = event.cgEvent else { break }
                try? withExtendedLifetime(event) { try nativePIDPost(key, pid) }
                closedBy = "window_escape_key"
                Thread.sleep(forTimeInterval: 0.03)
            }
        }
    }
    let closed = webWait(0.8, until: { !open() })
    guard read else {
        return ["type": "error", "error": "action_failed", "effect": wrote == .success ? "unknown" : "not_started",
                "input_route": "web_date_picker", "route_level": "L1", "picker_left_open": !closed,
                "reobserve_required": true, "detail": "the date field does not show the date that was written"]
    }
    return webRouteReply(name, obsID, route: "web_date_picker", level: closedBy == "window_escape_key" ? "L2" : "L1",
                         extra: ["value_read_back": true, "picker_closed": closed, "picker_closed_by": closedBy])
}

// MARK: - A page's alert / confirm dialog

/// The browser's dialog for a page's `alert()`/`confirm()` that holds this button.
private func pageDialogAncestor(_ element: AXUIElement) -> AXUIElement? {
    var node = element
    for _ in 0..<6 {
        guard let raw = attr(node, kAXParentAttribute as String),
              CFGetTypeID(raw) == AXUIElementGetTypeID() else { return nil }
        node = raw as! AXUIElement
        if str(node, "AXIdentifier") == "AXSafariModalDialog" { return node }
    }
    return nil
}

/// After AXPress on a button of a page's dialog: the dialog answers every
/// button by going away, and a press was measured to be taken without effect
/// (the dialog stayed, the page's script stayed blocked; 2026-11-12). While
/// the same dialog is still there the press did nothing, so it is made once
/// more. Returns nil for any other element, else whether it pressed again.
func pageDialogPress(_ button: AXUIElement) -> Bool? {
    guard str(button, kAXRoleAttribute as String) == "AXButton",
          let dialog = pageDialogAncestor(button) else { return nil }
    func open() -> Bool {
        guard str(dialog, "AXIdentifier") == "AXSafariModalDialog",
              let raw = attr(button, kAXParentAttribute as String),
              CFGetTypeID(raw) == AXUIElementGetTypeID() else { return false }
        return true
    }
    if webWait(0.7, until: { !open() }) { return false }
    _ = AXUIElementPerformAction(button, kAXPressAction as CFString)
    _ = webWait(0.7, until: { !open() })
    return true
}
