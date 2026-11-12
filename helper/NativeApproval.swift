// Menu approval enforced in the signed helper (stage 2).
//
// One gate at the common native dispatch: `act(...)` calls `gate` after the
// target and element are resolved and before any input is posted, for actions
// from the launcher connection and from warm mode alike. What is classified is
// what the helper reads from the element that will receive the input, never
// Python's safety declaration or its *_authorized flags.
//
// Enforcement follows the Keychain anchor the menu app writes when the
// person turns "메뉴에서 승인" on (`NativeApprovalAnchor`). While off, `gate`
// returns nil before reading anything, so behaviour is exactly as before.

import Foundation
import ApplicationServices
import AppKit

/// What a classified input would commit, as the helper read it (R7).
struct CommitView: Equatable {
    var digest: String = ""
    /// Shown on the card: "body", "items", "amount", "site".
    var summary: [String: String] = [:]
    /// Parts the helper could not read; the card says so.
    var unreadable: [String] = []
    /// Where it goes, when the helper read it (a web host). Empty: unknown.
    var destination: String = ""
}

enum NativeDecision: Equatable {
    case allowed, denied, timeout, unavailable, targetChanged, cancelled
}

enum NativeApproval {
    /// Wired to `NativeApprovalAnchor.enforcing` (Keychain, read by the helper).
    nonisolated(unsafe) static var enforcing: () -> Bool = { false }
    /// Asks the menu app (authenticated channel) for this input; blocking.
    nonisolated(unsafe) static var decide: (_ input: ObservedInput, _ cls: ApprovalClass, _ pid: pid_t, _ commit: CommitView) -> NativeDecision = { _, _, _, _ in .unavailable }
    /// Reads what the input would commit (wired to NativeCommit.read).
    nonisolated(unsafe) static var commitReader: (_ cls: ApprovalClass, _ anchor: AXUIElement?, _ pid: pid_t, _ payload: String?) -> CommitView = { _, _, _, _ in CommitView() }
    /// Process, signer and front window, compared before and after the card.
    nonisolated(unsafe) static var context: (pid_t) -> String = { _ in "" }
    /// The caller of this request has gone or pressed stop (set per request
    /// by the connection that carries it).
    nonisolated(unsafe) static var callerGone: () -> Bool = { false }
    nonisolated(unsafe) static var stopPressed: () -> Bool = { false }
    /// Told how long a card held the request, so request deadlines move.
    nonisolated(unsafe) static var onWaited: (Double) -> Void = { _ in }
    /// Seconds a card held the current act; `act` adds them to its input
    /// deadline (the wait is not input time).
    nonisolated(unsafe) static var waited: Double = 0
    static func takeWaited() -> Double { defer { waited = 0 }; return waited }
    /// Haejo's own apps: their approval and settings UI is never pressed
    /// through Haejo while enforcing.
    nonisolated(unsafe) static var bundleOf: (pid_t) -> String? = { NSRunningApplication(processIdentifier: $0)?.bundleIdentifier }
    static let haejoBundles: Set<String> = [
        "ai.callabo.haejo.setup.standalone.preview", "ai.callabo.haejo.setup.preview",
        "ai.callabo.haejo.setup", "ai.callabo.haejo.helper", "ai.callabo.haejo",
    ]

    static func refusal(_ error: String) -> [String: Any] {
        ["type": "error", "error": error, "effect": "not_started"]
    }

    /// Returns a refusal to send instead of dispatching, or nil to go on.
    static func gate(name: String, action: [String: Any], pid: pid_t,
                     anchor: () -> AXUIElement? = { nil },
                     observe: () -> ObservedInput) -> [String: Any]? {
        guard enforcing() else { return nil }
        // Reading Haejo's own windows is fine; any input into them is not.
        if name != "read", let bundle = bundleOf(pid), haejoBundles.contains(bundle) {
            return refusal("haejo_ui_input_refused")
        }
        // A menu is decided once its item is resolved (`gateMenuItem`), a
        // popup option at the item about to be pressed (`gateOption`): one
        // decision per input, on the element itself.
        if ["menu", "option"].contains(kind(name: name, action: action)) { return nil }
        return decided(observe(), pid: pid, anchor: anchor, payload: payload(action), reobserve: observe)
    }

    /// The text an input enters, compared by digest only (never shown).
    static func payload(_ action: [String: Any]) -> String? {
        (action["value"] as? String) ?? (action["text"] as? String)
    }

    /// The resolved menu item, before anything is pressed or prepared.
    static func gateMenuItem(_ item: AXUIElement, pid: pid_t) -> [String: Any]? {
        guard enforcing() else { return nil }
        var input = ObservedInput(kind: "menu")
        input.role = "AXMenuItem"
        input.labels = labels(item)
        input.focusIsText = focusIsText(pid)
        input.identity = identity(item)
        input.window = menuWindows(pid)
        let app = AXUIElementCreateApplication(pid)
        return decided(input, pid: pid, anchor: { element(app, kAXFocusedWindowAttribute as String) ?? element(app, kAXMainWindowAttribute as String) }, payload: nil) {
            var again = input; again.labels = labels(item); again.focusIsText = focusIsText(pid)
            again.identity = identity(item); again.window = menuWindows(pid); return again
        }
    }

    /// A popup option about to be pressed (AX press or pointer click), read
    /// from the item itself: title, description and value. The open popup
    /// stays as it is (an
    /// automatic cancel has left controls unable to post a menu again); the
    /// reply says so and that nothing was selected. `effect` describes the
    /// selection, which did not start.
    static func gateOption(_ item: AXUIElement, pid: pid_t, openedHere: Bool, control: AXUIElement?) -> [String: Any]? {
        guard enforcing() else { return nil }
        var input = ObservedInput(kind: "press")
        input.role = "AXMenuItem"
        input.labels = labels(item)
        input.identity = identity(item)
        input.window = windowIdentity(item)
        // The option acts on its control's window (not the popup's, and not
        // whichever window happens to be focused).
        guard var refusal = decided(input, pid: pid, anchor: { control }, payload: nil, reobserve: {
            var again = input; again.labels = labels(item); again.identity = identity(item)
            again.window = windowIdentity(item); return again
        }) else { return nil }
        refusal["menu_opened_by_this_action"] = openedHere
        refusal["menu_left_open"] = true
        refusal["option_selected"] = false
        refusal["selections_made"] = 0
        refusal["reobserve_required"] = true
        return refusal
    }

    /// Classify; ask when it matters; after "allowed", read the input again
    /// (S6): the card answered for what it showed, so a different element,
    /// label, process or front window is not dispatched.
    static func decided(_ input: ObservedInput, pid: pid_t, anchor: () -> AXUIElement?, payload: String?,
                        reobserve: () -> ObservedInput) -> [String: Any]? {
        let cls = ApprovalClassifier.classify(input)
        guard cls != .none else { return nil }
        let before = context(pid)
        // What is committed, not only what is clicked: the body, the selected
        // items, the amount and site; read again after the answer.
        let commit = commitReader(cls, anchor(), pid, payload)
        let asked = ProcessInfo.processInfo.systemUptime
        let decision = decide(input, cls, pid, commit)
        let elapsed = ProcessInfo.processInfo.systemUptime - asked
        waited += elapsed
        onWaited(elapsed)
        switch decision {
        case .allowed:
            if callerGone() { return refusal(stopPressed() ? "aborted_by_user" : "client_disconnected") }
            guard reobserve() == input, context(pid) == before,
                  commitReader(cls, anchor(), pid, payload).digest == commit.digest else { return refusal("approval_target_changed") }
            return nil
        case .denied: return refusal("approval_denied")
        case .timeout: return refusal("approval_timeout")
        case .unavailable: return refusal("approval_unavailable")
        case .targetChanged: return refusal("approval_target_changed")
        case .cancelled: return refusal(stopPressed() ? "aborted_by_user" : "client_disconnected")
        }
    }

    // MARK: what kind of input an action posts

    static func isReturn(_ key: String) -> Bool {
        ["return", "enter", "kpenter", "\r", "\n"].contains(key.lowercased())
    }

    static func kind(name: String, action: [String: Any]) -> String {
        switch name {
        case "click", "double_click", "click_point":
            return "press"
        case "select_option", "select_custom_option":
            return "option"
        case "secondary_action":
            // Showing a menu, stepping or cancelling commits nothing.
            return ["AXPress", "AXConfirm"].contains(action["action"] as? String ?? "") ? "press" : "key"
        case "set_value", "type_text":
            return "text"
        case "press_key":
            return isReturn(action["key"] as? String ?? "") ? "return" : "key"
        case "window_input":
            if let key = action["key"] as? String { return isReturn(key) ? "return" : "key" }
            return action["text"] != nil ? "text" : "key"
        case "menu":
            return "menu"
        case "drag", "hover", "vroid_drag", "vroid_focus":
            return "point"
        default:
            return "none"
        }
    }


    // MARK: reading the element (AX)

    static func string(_ el: AXUIElement, _ name: String) -> String? {
        var value: CFTypeRef?
        guard AXUIElementCopyAttributeValue(el, name as CFString, &value) == .success else { return nil }
        return value as? String
    }
    static func element(_ el: AXUIElement, _ name: String) -> AXUIElement? {
        var value: CFTypeRef?
        guard AXUIElementCopyAttributeValue(el, name as CFString, &value) == .success,
              let v = value, CFGetTypeID(v) == AXUIElementGetTypeID() else { return nil }
        return (v as! AXUIElement)
    }
    static func labels(_ el: AXUIElement) -> [String] {
        var out: [String] = []
        for name in [kAXTitleAttribute, kAXDescriptionAttribute, kAXValueAttribute] as [String] {
            if let s = string(el, name), !s.isEmpty, s.count <= 200 { out.append(s) }
        }
        return out
    }
    static func size(_ el: AXUIElement) -> CGSize? {
        var value: CFTypeRef?
        guard AXUIElementCopyAttributeValue(el, kAXSizeAttribute as CFString, &value) == .success,
              let v = value, CFGetTypeID(v) == AXValueGetTypeID() else { return nil }
        var size = CGSize.zero
        return AXValueGetValue(v as! AXValue, .cgSize, &size) ? size : nil
    }
    /// This AX element (its hash is stable for the same element) and where it is.
    static func identity(_ el: AXUIElement) -> String {
        let p = position(el) ?? CGPoint(x: -1, y: -1), z = size(el) ?? .zero
        return "\(CFHash(el))@\(Int(p.x)),\(Int(p.y)),\(Int(z.width)),\(Int(z.height))"
    }
    /// The element's own window: identity and title (the card shows the title).
    static func windowIdentity(_ el: AXUIElement) -> String {
        guard let window = element(el, kAXWindowAttribute as String) else { return "" }
        return identity(window) + "\u{1f}" + (string(window, kAXTitleAttribute as String) ?? "")
    }
    /// A menu acts on the app's focused or main window, not on a window of
    /// its own: both are recorded, with the focused window's title first.
    static func menuWindows(_ pid: pid_t) -> String {
        let app = AXUIElementCreateApplication(pid)
        func one(_ name: String) -> (String, String) {
            guard let w = element(app, name) else { return ("", "") }
            return (identity(w), string(w, kAXTitleAttribute as String) ?? "")
        }
        let focused = one(kAXFocusedWindowAttribute as String), main = one(kAXMainWindowAttribute as String)
        return focused.0 + "|" + main.0 + "\u{1f}" + (focused.1.isEmpty ? main.1 : focused.1)
    }
    static func windowTitle(fromIdentity window: String) -> String {
        window.split(separator: "\u{1f}", omittingEmptySubsequences: false).dropFirst().joined()
    }

    static func focusIsText(_ pid: pid_t) -> Bool {
        guard let focused = element(AXUIElementCreateApplication(pid), kAXFocusedUIElementAttribute as String) else { return false }
        return ["AXTextField", "AXTextArea", "AXComboBox", "AXSearchField"].contains(string(focused, kAXRoleAttribute as String) ?? "")
    }
    static func position(_ el: AXUIElement) -> CGPoint? {
        var value: CFTypeRef?
        guard AXUIElementCopyAttributeValue(el, kAXPositionAttribute as CFString, &value) == .success,
              let v = value, CFGetTypeID(v) == AXValueGetTypeID() else { return nil }
        var point = CGPoint.zero
        return AXValueGetValue(v as! AXValue, .cgPoint, &point) ? point : nil
    }
    static func elementAt(_ app: AXUIElement, _ point: CGPoint) -> AXUIElement? {
        var hit: AXUIElement?
        guard AXUIElementCopyElementAtPosition(app, Float(point.x), Float(point.y), &hit) == .success else { return nil }
        return hit
    }
    static func pressable(_ el: AXUIElement) -> Bool {
        var names: CFArray?
        guard AXUIElementCopyActionNames(el, &names) == .success, let list = names as? [String] else { return false }
        return list.contains(kAXPressAction as String)
    }

    /// The observed input for `act`: the resolved (or hit-tested) element for
    /// presses and text, the focused element for keys and window input, the
    /// window's default button for Return.
    static func observe(name: String, action: [String: Any], element: AXUIElement?, pid: pid_t) -> ObservedInput {
        var input = ObservedInput(kind: kind(name: name, action: action))
        let app = AXUIElementCreateApplication(pid)
        switch input.kind {
        case "menu", "option", "none", "point", "key":
            return input
        default:
            break
        }
        // click_point names a window and a window-relative point; what it
        // presses is the element at that point.
        if name == "click_point", let window = element, let point = action["point"] as? [String: Any],
           let x = (point["x"] as? NSNumber)?.doubleValue, let y = (point["y"] as? NSNumber)?.doubleValue,
           let origin = position(window), let hit = elementAt(app, CGPoint(x: origin.x + x, y: origin.y + y)) {
            input.role = string(hit, kAXRoleAttribute as String) ?? ""
            input.subrole = string(hit, kAXSubroleAttribute as String) ?? ""
            input.labels = labels(hit)
            input.pressable = pressable(hit)
            input.identity = identity(hit)
            input.window = windowIdentity(hit)
            return input
        }
        if name == "click_point" { return input }   // no element at the point: nothing to classify
        let focusedTarget = name == "window_input" || (name == "press_key" && element == nil)
        guard let el = focusedTarget ? Self.element(app, kAXFocusedUIElementAttribute as String) : element else { return input }
        input.role = string(el, kAXRoleAttribute as String) ?? ""
        input.subrole = string(el, kAXSubroleAttribute as String) ?? ""
        input.identity = identity(el)
        input.window = windowIdentity(el)
        if input.kind == "press" {
            input.labels = labels(el)
            input.pressable = pressable(el)
        }
        if input.kind == "return", let window = Self.element(el, kAXWindowAttribute as String),
           let button = Self.element(window, kAXDefaultButtonAttribute as String) {
            input.defaultButtonLabels = labels(button)
        }
        return input
    }
}
