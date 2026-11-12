import AppKit
import ApplicationServices
import CryptoKit

// MARK: - choose_files: registered files into a page's file control
//
// A web page's file control opens the app's standard open panel as a sheet.
// Measured on Safari 27.2 / macOS 27.2 (2026-11-12), Safari in the background
// unless stated:
//   * AXPress on the control opens the sheet (identifier `open-panel`); its
//     Cancel button answers AXPress.
//   * Every listed item is a text field carrying AXURL, so a file is found by
//     identity, never by its displayed name. Setting the column list's
//     AXSelectedChildren on a folder moves the panel there; on files it reads
//     back as selected.
//   * The Upload button stays disabled for that selection until Safari is the
//     front app: about 0.6 s after activation it enables, stays enabled after
//     the previous app is put back, and answers AXPress.
//   * Go to Folder has no accessibility control. Command-Shift-G posted to the
//     Safari process or to the panel's service process opens nothing, in the
//     background or in front; the real key with Safari in front opens the
//     `GoToWindow` sheet, whose `PathTextField` takes its value through AX.
// So the order is: find and select through AX, come forward only for the
// moment the panel needs to accept the selection, and use the two real keys
// only for a folder the panel does not show (a hidden path).

struct OpenPanelFile {
    let path: String      // canonical: symlinks resolved
    let directory: String
    let name: String
    let sha256: String
}

func openPanelCanonicalPath(_ path: String) -> String {
    URL(fileURLWithPath: path).resolvingSymlinksInPath().standardizedFileURL.path
}

func openPanelFileDigest(_ path: String) -> String? {
    guard let handle = FileHandle(forReadingAtPath: path) else { return nil }
    defer { try? handle.close() }
    var hasher = SHA256()
    while true {
        // nil at the end of the file, an error when the read failed.
        let chunk: Data?
        do { chunk = try handle.read(upToCount: 1 << 20) } catch { return nil }
        guard let chunk, !chunk.isEmpty else { break }
        hasher.update(data: chunk)
    }
    return hasher.finalize().map { String(format: "%02x", $0) }.joined()
}

/// The registered files as the helper will use them, or why they cannot be
/// used. One to sixteen existing regular files of one folder, each named by
/// an absolute path and the SHA-256 its bytes had at registration.
func openPanelParseFiles(_ raw: Any?) -> (files: [OpenPanelFile], problem: String?) {
    guard let list = raw as? [[String: Any]], (1...16).contains(list.count) else {
        return ([], "files must list 1 to 16 entries")
    }
    var files: [OpenPanelFile] = []
    for entry in list {
        guard Set(entry.keys) == Set(["path", "sha256"]),
              let path = entry["path"] as? String, path.hasPrefix("/"), path.utf8.count <= 1024,
              let digest = entry["sha256"] as? String, digest.count == 64,
              digest.allSatisfy({ $0.isHexDigit && !$0.isUppercase }) else {
            return ([], "each file needs an absolute path and a lowercase sha256")
        }
        let canonical = openPanelCanonicalPath(path)
        var isDirectory: ObjCBool = false
        guard FileManager.default.fileExists(atPath: canonical, isDirectory: &isDirectory), !isDirectory.boolValue else {
            return ([], "not an existing file: \((path as NSString).lastPathComponent)")
        }
        let url = URL(fileURLWithPath: canonical)
        files.append(OpenPanelFile(path: canonical, directory: url.deletingLastPathComponent().path,
                                   name: url.lastPathComponent, sha256: digest))
    }
    guard Set(files.map { $0.directory }).count == 1 else { return ([], "the files of one step share one folder") }
    guard Set(files.map { $0.path }).count == files.count else { return ([], "a file is listed twice") }
    return (files, nil)
}

/// The first element within `depth` levels of `root` that `matches`.
func openPanelFind(_ root: AXUIElement, depth: Int, budget: Int = 4000,
                   where matches: (AXUIElement) -> Bool) -> AXUIElement? {
    var level = [root]
    var seen = 0
    for _ in 0...depth {
        var next: [AXUIElement] = []
        for node in level {
            seen += 1
            if seen > budget { return nil }
            if matches(node) { return node }
            next.append(contentsOf: (attr(node, kAXChildrenAttribute as String) as? [AXUIElement]) ?? [])
        }
        if next.isEmpty { return nil }
        level = next
    }
    return nil
}

func openPanelSheet(of window: AXUIElement) -> AXUIElement? {
    ((attr(window, kAXChildrenAttribute as String) as? [AXUIElement]) ?? []).first {
        str($0, kAXRoleAttribute as String) == "AXSheet"
    }
}

func openPanelButton(_ sheet: AXUIElement, attribute: String, identifier: String) -> AXUIElement? {
    if let value = attr(sheet, attribute), CFGetTypeID(value) == AXUIElementGetTypeID() {
        return (value as! AXUIElement)
    }
    return openPanelFind(sheet, depth: 3) {
        str($0, kAXRoleAttribute as String) == (kAXButtonRole as String)
            && str($0, kAXIdentifierAttribute as String) == identifier
    }
}

/// The Go to Folder sheet's path field. The sheet hangs directly under the
/// open panel (measured), and while it is open its field holds the focus.
func openPanelGoToField(_ sheet: AXUIElement, pid: pid_t) -> AXUIElement? {
    guard let goTo = ((attr(sheet, kAXChildrenAttribute as String) as? [AXUIElement]) ?? []).first(where: {
        str($0, kAXRoleAttribute as String) == "AXSheet" && str($0, kAXIdentifierAttribute as String) == "GoToWindow"
    }) else { return nil }
    if let raw = attr(AXUIElementCreateApplication(pid), kAXFocusedUIElementAttribute as String),
       CFGetTypeID(raw) == AXUIElementGetTypeID(),
       str(raw as! AXUIElement, kAXIdentifierAttribute as String) == "PathTextField" {
        return (raw as! AXUIElement)
    }
    return openPanelFind(goTo, depth: 5) {
        str($0, kAXRoleAttribute as String) == (kAXTextFieldRole as String)
            && str($0, kAXIdentifierAttribute as String) == "PathTextField"
    }
}

struct OpenPanelItem {
    let element: AXUIElement
    let path: String
}

/// Every item the panel lists, with the file it stands for. One request per
/// node (role, children and URL together) keeps a folder of hundreds within a
/// second. With `toward`, a long list that shows some other folder than one
/// on the way to that directory is passed over after its first entry: the
/// per-user temporary folder lists tens of thousands of entries (measured:
/// 43,062), and reading them all would spend the whole budget.
func openPanelItems(_ sheet: AXUIElement, deadline: Double, toward directory: String? = nil,
                    budget: Int = 40000) -> [OpenPanelItem] {
    var out: [OpenPanelItem] = []
    var stack: [AXUIElement] = [sheet]
    var seen = 0
    let names = [kAXChildrenAttribute as String, "AXURL", kAXRoleAttribute as String] as CFArray
    func read(_ node: AXUIElement) -> (children: [AXUIElement], path: String?, role: String?)? {
        var values: CFArray?
        guard AXUIElementCopyMultipleAttributeValues(node, names, AXCopyMultipleAttributeOptions(rawValue: 0), &values) == .success,
              let triple = values as? [AnyObject], triple.count == 3 else { return nil }
        var path: String?
        if CFGetTypeID(triple[1]) == CFURLGetTypeID(), let url = (triple[1] as! NSURL).filePathURL {
            path = openPanelCanonicalPath(url.path)
        }
        let children = CFGetTypeID(triple[0]) == CFArrayGetTypeID() ? (triple[0] as? [AXUIElement]) ?? [] : []
        return (children, path, triple[2] as? String)
    }
    /// The folder a list shows, read from its first entry.
    func folderShown(by first: AXUIElement) -> String? {
        var level = [first]
        for _ in 0..<3 {
            var next: [AXUIElement] = []
            for node in level.prefix(8) {
                guard let got = read(node) else { continue }
                if let path = got.path { return (path as NSString).deletingLastPathComponent }
                next.append(contentsOf: got.children)
            }
            level = next
        }
        return nil
    }
    while let node = stack.popLast() {
        seen += 1
        if seen > budget || ProcessInfo.processInfo.systemUptime >= deadline { break }
        guard let got = read(node) else { continue }
        if let path = got.path { out.append(OpenPanelItem(element: node, path: path)) }
        if let directory, got.children.count > 64,
           [kAXListRole as String, kAXOutlineRole as String, kAXTableRole as String].contains(got.role ?? ""),
           let shown = folderShown(by: got.children[0]),
           !(directory == shown || directory.hasPrefix(shown == "/" ? "/" : shown + "/")) {
            continue
        }
        stack.append(contentsOf: got.children)
    }
    return out
}

/// Select these items in the list or table that holds them, judged by reading
/// the selection back. The items of one call share one container.
func openPanelSelect(_ items: [AXUIElement]) -> Bool {
    var container: AXUIElement?
    var attribute = ""
    var members: [AXUIElement] = []
    for item in items {
        var node = item
        var placed = false
        for _ in 0..<5 {
            guard let raw = attr(node, kAXParentAttribute as String), CFGetTypeID(raw) == AXUIElementGetTypeID() else { break }
            let parent = raw as! AXUIElement
            let parentRole = str(parent, kAXRoleAttribute as String) ?? ""
            var name: String?
            if parentRole == (kAXListRole as String) {
                name = kAXSelectedChildrenAttribute as String
            } else if str(node, kAXRoleAttribute as String) == (kAXRowRole as String),
                      [kAXOutlineRole as String, kAXTableRole as String].contains(parentRole) {
                name = kAXSelectedRowsAttribute as String
            }
            if let name {
                if let held = container, !(CFEqual(held, parent) && attribute == name) { return false }
                container = parent
                attribute = name
                members.append(node)
                placed = true
                break
            }
            node = parent
        }
        if !placed { return false }
    }
    guard let list = container else { return false }
    // The panel answers the set with an error even when it took effect
    // (measured: -25205 for a file); only the read-back decides.
    _ = AXUIElementSetAttributeValue(list, attribute as CFString, members as CFArray)
    for _ in 0..<12 {
        let now = (attr(list, attribute) as? [AXUIElement]) ?? []
        if now.count == members.count, members.allSatisfy({ member in now.contains(where: { CFEqual($0, member) }) }) {
            return true
        }
        Thread.sleep(forTimeInterval: 0.05)
    }
    return false
}

/// Show `directory` or the nearest folder above it by choosing the sidebar
/// place with that folder's displayed name. True only when the panel then
/// lists that folder's own entries (checked by URL), so a place that merely
/// shares the name is not taken for it.
func openPanelSidebarJump(_ sheet: AXUIElement, toward directory: String, deadline: Double) -> String? {
    guard let sidebar = openPanelFind(sheet, depth: 4, where: {
        str($0, kAXRoleAttribute as String) == (kAXOutlineRole as String)
    }) else { return nil }
    let rows = ((attr(sidebar, kAXChildrenAttribute as String) as? [AXUIElement]) ?? [])
        .filter { str($0, kAXRoleAttribute as String) == (kAXRowRole as String) }
    func label(_ row: AXUIElement) -> String? {
        guard let text = openPanelFind(row, depth: 3, where: {
            str($0, kAXRoleAttribute as String) == (kAXStaticTextRole as String)
        }) else { return nil }
        return str(text, kAXValueAttribute as String)?.replacingOccurrences(of: "\u{a0}", with: " ")
    }
    let labelled = rows.compactMap { row in label(row).map { (row, $0) } }
    var place = directory
    while place != "/" {
        let shown = FileManager.default.displayName(atPath: place)
        for (row, text) in labelled where text == shown {
            guard ProcessInfo.processInfo.systemUptime < deadline, !abortState.isStopped else { return nil }
            _ = AXUIElementSetAttributeValue(sidebar, kAXSelectedRowsAttribute as CFString, [row] as CFArray)
            for _ in 0..<4 {
                Thread.sleep(forTimeInterval: 0.3)
                let prefix = place + "/"
                if openPanelItems(sheet, deadline: deadline, toward: directory).contains(where: {
                    $0.path.hasPrefix(prefix) && !$0.path.dropFirst(prefix.count).contains("/")
                }) { return place }
            }
        }
        place = (place as NSString).deletingLastPathComponent
    }
    return nil
}

/// A real key press, for the Go to Folder sheet only. The caller has just
/// checked that the target app is in front and holds the focus.
func openPanelRealKey(_ code: CGKeyCode, flags: CGEventFlags) -> Bool {
    guard let source = CGEventSource(stateID: .hidSystemState),
          let down = CGEvent(keyboardEventSource: source, virtualKey: code, keyDown: true),
          let up = CGEvent(keyboardEventSource: source, virtualKey: code, keyDown: false) else { return false }
    down.flags = flags
    up.flags = flags
    down.post(tap: .cghidEventTap)
    usleep(30_000)
    up.post(tap: .cghidEventTap)
    return true
}

/// The front app, taken for as short a time as the panel needs and given back
/// to the app the person was using.
final class OpenPanelFront {
    let pid: pid_t
    let window: AXUIElement
    private var previous: pid_t?
    private var began: Double?
    private(set) var seconds = 0.0
    private(set) var taken = false
    init(pid: pid_t, window: AXUIElement) { self.pid = pid; self.window = window }

    func take() -> Bool {
        if isFrontmost(pid: pid) { return true }
        guard !abortState.isStopped else { return false }
        previous = nativeFrontmostProcessPID()
        began = ProcessInfo.processInfo.systemUptime
        taken = true
        _ = AXUIElementPerformAction(window, kAXRaiseAction as CFString)
        NSRunningApplication(processIdentifier: pid)?.activate(options: [])
        for _ in 0..<75 {
            if isFrontmost(pid: pid) { return true }
            Thread.sleep(forTimeInterval: 0.02)
        }
        return isFrontmost(pid: pid)
    }

    /// True when the person's app is in front again, or was never left.
    func giveBack() -> Bool {
        guard let start = began else { return true }
        defer {
            seconds += ProcessInfo.processInfo.systemUptime - start
            began = nil
        }
        // Someone else moved on in the meantime: their choice stands.
        guard isFrontmost(pid: pid), let person = previous, person != pid else { return true }
        return returnScreen(to: person)
    }
}

/// Close the Go to Folder sheet and the panel, so no sheet is left on the
/// window whatever happened. True when the window has no sheet afterwards.
func openPanelDismiss(window: AXUIElement, pid: pid_t) -> Bool {
    for _ in 0..<4 {
        guard let sheet = openPanelSheet(of: window) else { return true }
        if let goTo = ((attr(sheet, kAXChildrenAttribute as String) as? [AXUIElement]) ?? []).first(where: {
            str($0, kAXIdentifierAttribute as String) == "GoToWindow"
        }) {
            // Its own Close button first; Escape only while the app is in front.
            if let close = openPanelFind(goTo, depth: 2, where: {
                str($0, kAXIdentifierAttribute as String) == "CloseButton"
            }) {
                _ = AXUIElementPerformAction(close, kAXPressAction as CFString)
                Thread.sleep(forTimeInterval: 0.4)
            }
            if openPanelGoToField(sheet, pid: pid) != nil, isFrontmost(pid: pid) {
                _ = openPanelRealKey(53, flags: [])
                Thread.sleep(forTimeInterval: 0.4)
            }
        }
        if let cancel = openPanelButton(sheet, attribute: "AXCancelButton", identifier: "CancelButton") {
            _ = AXUIElementPerformAction(cancel, kAXPressAction as CFString)
        }
        for _ in 0..<15 {
            if openPanelSheet(of: window) == nil { return true }
            Thread.sleep(forTimeInterval: 0.1)
        }
    }
    return openPanelSheet(of: window) == nil
}

func chooseFiles(obsID: String, control: AXUIElement, pid: pid_t, rawFiles: Any?) -> [String: Any] {
    var steps: [[String: Any]] = []
    func refused(_ code: String, effect: String = "not_started", detail: String? = nil,
                 extra: [String: Any] = [:]) -> [String: Any] {
        var out: [String: Any] = ["type": "error", "error": code, "effect": effect, "steps": steps]
        if let detail { out["detail"] = detail }
        for (key, value) in extra { out[key] = value }
        return out
    }
    let parsed = openPanelParseFiles(rawFiles)
    guard parsed.problem == nil else { return refused("invalid_files", detail: parsed.problem) }
    let files = parsed.files
    func pinned() -> Bool { files.allSatisfy { openPanelFileDigest($0.path) == $0.sha256 } }
    guard pinned() else {
        return refused("attachment_changed", detail: "a file no longer has its registered bytes")
    }
    var window: AXUIElement?
    if let raw = attr(control, kAXWindowAttribute as String), CFGetTypeID(raw) == AXUIElementGetTypeID() {
        window = (raw as! AXUIElement)
    }
    guard let window else { return refused("action_failed", detail: "the control's window is not readable") }
    guard openPanelSheet(of: window) == nil else {
        return refused("open_panel_busy", detail: "the window already shows a sheet", extra: ["retryable": true])
    }
    var names: CFArray?
    guard AXUIElementCopyActionNames(control, &names) == .success,
          (names as? [String] ?? []).contains(kAXPressAction as String) else {
        return refused("action_failed", detail: "the file control offers no AXPress")
    }
    func label() -> String {
        str(control, kAXTitleAttribute as String) ?? str(control, kAXValueAttribute as String) ?? ""
    }
    let labelBefore = label()
    let deadline = ProcessInfo.processInfo.systemUptime + 40
    func live() -> Bool { !abortState.isStopped && ProcessInfo.processInfo.systemUptime < deadline }
    guard live() else { return refused("aborted_by_user") }

    guard AXUIElementPerformAction(control, kAXPressAction as CFString) == .success else {
        return refused("action_failed", effect: "unknown", detail: "AXPress on the file control failed")
    }
    var sheet: AXUIElement?
    for _ in 0..<40 {
        if let shown = openPanelSheet(of: window), str(shown, kAXIdentifierAttribute as String) == "open-panel",
           openPanelButton(shown, attribute: "AXDefaultButton", identifier: "OKButton") != nil {
            sheet = shown
            break
        }
        Thread.sleep(forTimeInterval: 0.1)
    }
    guard let sheet, let ok = openPanelButton(sheet, attribute: "AXDefaultButton", identifier: "OKButton") else {
        let closed = openPanelDismiss(window: window, pid: pid)
        return refused("open_panel_not_shown", effect: "unknown",
                       detail: "pressing the control opened no open panel", extra: ["panel_closed": closed])
    }
    steps.append(["step": "open_panel", "means": "ax_press", "front": isFrontmost(pid: pid)])

    let front = OpenPanelFront(pid: pid, window: window)
    var realKeys = 0
    var route = "ax_background"
    func failed(_ code: String, _ detail: String) -> [String: Any] {
        let closed = openPanelDismiss(window: window, pid: pid)
        let restored = front.giveBack()
        return refused(code, effect: closed ? "not_started" : "unknown", detail: detail, extra: [
            "panel_closed": closed, "files_attached": false, "took_front": front.taken,
            "front_seconds": (front.seconds * 100).rounded() / 100, "front_restored": restored,
            "real_keys": realKeys])
    }
    func enabled() -> Bool { (attr(ok, kAXEnabledAttribute as String) as? Bool) == true }
    func waitEnabled(_ seconds: Double) -> Bool {
        let until = ProcessInfo.processInfo.systemUptime + seconds
        while ProcessInfo.processInfo.systemUptime < until {
            if enabled() { return true }
            Thread.sleep(forTimeInterval: 0.05)
        }
        return enabled()
    }
    let directory = files[0].directory
    func located(_ items: [OpenPanelItem]) -> [AXUIElement]? {
        var found: [AXUIElement] = []
        for file in files {
            guard let hit = items.first(where: { $0.path == file.path }) else { return nil }
            found.append(hit.element)
        }
        return found
    }
    /// The files' own entries, after moving the panel to their folder through
    /// the items it lists. nil when the folder is not reachable that way.
    func walk() -> [AXUIElement]? {
        var last: String?
        var stalls = 0
        var hops = 0
        var jumped = false
        func gaveUp(_ why: String, listed: Int) -> [AXUIElement]? {
            steps.append(["step": "navigate", "means": "ax_selection", "result": why, "hops": hops,
                          "sidebar": jumped, "entries_read": listed])
            return nil
        }
        while live(), hops < 48 {
            let items = openPanelItems(sheet, deadline: deadline, toward: directory)
            if let found = located(items) {
                steps.append(["step": "navigate", "means": "ax_selection", "hops": hops, "sidebar": jumped])
                return found
            }
            let above = items.filter {
                $0.path == directory || directory.hasPrefix($0.path == "/" ? "/" : $0.path + "/")
            }
            guard let next = above.max(by: { $0.path.count < $1.path.count }) else {
                if !jumped, openPanelSidebarJump(sheet, toward: directory, deadline: deadline) != nil {
                    jumped = true
                    continue
                }
                // A folder made a moment ago can be missing from the listing
                // the panel just loaded; it gets a few more reads to arrive.
                stalls += 1
                if stalls > 6 { return gaveUp("folder_not_listed", listed: items.count) }
                Thread.sleep(forTimeInterval: 0.5)
                continue
            }
            if next.path == last {
                // The folder is selected; its entries are still arriving, or
                // the file is one the panel does not list (a hidden name).
                stalls += 1
                if stalls > 6 { return gaveUp(next.path == directory ? "file_not_listed" : "folder_did_not_open", listed: items.count) }
                Thread.sleep(forTimeInterval: 0.3)
                continue
            }
            guard openPanelSelect([next.element]) else { return gaveUp("selection_not_taken", listed: items.count) }
            last = next.path
            stalls = 0
            hops += 1
            Thread.sleep(forTimeInterval: 0.3)
        }
        return gaveUp("stopped", listed: 0)
    }

    var ready = false
    if let targets = walk(), openPanelSelect(targets) {
        steps.append(["step": "select", "means": "ax_selection", "count": targets.count])
        if !waitEnabled(0.4), front.take() {
            // The panel accepts the selection once its app is in front.
            route = "ax_brief_front"
            if !waitEnabled(2.0) {
                _ = openPanelSelect(targets)
                _ = waitEnabled(1.0)
            }
        }
        ready = enabled()
    }
    if !ready {
        // Go to Folder: the one part that takes real keys, with the app in front.
        route = "go_to_folder_front"
        func focusedInPanel() -> Bool {
            guard isFrontmost(pid: pid),
                  let raw = attr(AXUIElementCreateApplication(pid), kAXFocusedWindowAttribute as String),
                  CFGetTypeID(raw) == AXUIElementGetTypeID() else { return false }
            let focused = raw as! AXUIElement
            return CFEqual(focused, sheet) || str(focused, kAXIdentifierAttribute as String) == "GoToWindow"
        }
        guard live(), front.take() else { return failed("needs_foreground", "the app could not be brought forward for Go to Folder") }
        var focusedReady = false
        for _ in 0..<20 {
            if focusedInPanel() { focusedReady = true; break }
            Thread.sleep(forTimeInterval: 0.05)
        }
        guard focusedReady, live() else { return failed("open_panel_not_focused", "the open panel did not take the keyboard focus") }
        // A key sent in the first moment after activation is dropped
        // (measured: 0.24 s after coming forward opened nothing, a second
        // key about a second later did), so the panel gets a short settle
        // and the key is sent again once if no sheet appeared.
        Thread.sleep(forTimeInterval: 0.7)
        var field: AXUIElement?
        for _ in 0..<2 where field == nil {
            guard live(), focusedInPanel() else { break }
            guard openPanelRealKey(5, flags: [.maskCommand, .maskShift]) else { return failed("action_failed", "the key event could not be made") }
            realKeys += 1
            for _ in 0..<14 {
                if let shown = openPanelGoToField(sheet, pid: pid) { field = shown; break }
                Thread.sleep(forTimeInterval: 0.1)
            }
        }
        guard let field else { return failed("go_to_folder_not_shown", "Command-Shift-G opened no Go to Folder sheet") }
        let goal = files.count == 1 ? files[0].path : directory
        _ = AXUIElementSetAttributeValue(field, kAXValueAttribute as CFString, goal as CFString)
        Thread.sleep(forTimeInterval: 0.3)
        guard str(field, kAXValueAttribute as String) == goal else {
            return failed("go_to_folder_path_unset", "the path field did not take the path")
        }
        guard live(), focusedInPanel(), openPanelGoToField(sheet, pid: pid) != nil else {
            return failed("open_panel_not_focused", "the focus left Go to Folder before Return")
        }
        guard openPanelRealKey(36, flags: []) else { return failed("action_failed", "the key event could not be made") }
        realKeys += 1
        for _ in 0..<40 {
            if openPanelGoToField(sheet, pid: pid) == nil { break }
            Thread.sleep(forTimeInterval: 0.1)
        }
        // Measured: a folder inside one with tens of thousands of entries (the
        // per-user temporary folder) keeps the sheet on "Loading…" for minutes.
        guard openPanelGoToField(sheet, pid: pid) == nil else {
            return failed("go_to_folder_unconfirmed",
                          "Go to Folder was still loading the folder; a file kept in a smaller folder attaches at once")
        }
        steps.append(["step": "navigate", "means": "go_to_folder", "real_keys": realKeys])
        if files.count == 1, waitEnabled(1.5) {
            ready = true
        } else {
            // The folder is shown now. Reading and selecting its entries
            // needs no front app, so the person's app goes back first and
            // the panel gets one more short moment in front to accept.
            _ = front.giveBack()
            var targets: [AXUIElement]?
            for _ in 0..<6 {
                targets = located(openPanelItems(sheet, deadline: deadline, toward: directory))
                if targets != nil || !live() { break }
                Thread.sleep(forTimeInterval: 0.3)
            }
            if let targets, openPanelSelect(targets) {
                steps.append(["step": "select", "means": "ax_selection", "count": targets.count])
                if !waitEnabled(0.4), front.take(), !waitEnabled(2.0) {
                    _ = openPanelSelect(targets)
                    _ = waitEnabled(1.0)
                }
                ready = enabled()
            }
        }
    }
    guard ready else { return failed("files_not_selectable", "the panel did not accept the files") }
    guard live() else { return failed("aborted_by_user", "stopped before choosing") }
    guard pinned() else { return failed("attachment_changed", "a file changed while the panel was open") }
    guard AXUIElementPerformAction(ok, kAXPressAction as CFString) == .success else {
        return failed("action_failed", "the panel's choose button did not take AXPress")
    }
    steps.append(["step": "choose", "means": "ax_press", "front": isFrontmost(pid: pid)])
    // The press is in; the person's app comes back before the sheet finishes closing.
    let restored = front.giveBack()
    var closed = false
    for _ in 0..<40 {
        if openPanelSheet(of: window) == nil { closed = true; break }
        Thread.sleep(forTimeInterval: 0.1)
    }
    guard closed else {
        let dismissed = openPanelDismiss(window: window, pid: pid)
        return refused("open_panel_unconfirmed", effect: "unknown", detail: "the panel stayed open after choosing", extra: [
            "panel_closed": dismissed, "took_front": front.taken, "front_restored": restored,
            "front_seconds": (front.seconds * 100).rounded() / 100, "real_keys": realKeys])
    }
    // What the page's own control says now: a plain file input names the file
    // (or counts several); a styled button keeps its label, and the page's
    // own text is the evidence a Flow postcondition reads.
    var labelAfter = label()
    func shows(_ text: String) -> Bool {
        files.count == 1 ? text.contains(files[0].name) : (text != labelBefore && text.contains(String(files.count)))
    }
    for _ in 0..<20 where !shows(labelAfter) {
        Thread.sleep(forTimeInterval: 0.1)
        labelAfter = label()
    }
    return ["type": "acted", "action": "choose_files", "obs_id": obsID, "route": route,
            "took_front": front.taken, "front_seconds": (front.seconds * 100).rounded() / 100,
            "front_restored": restored, "real_keys": realKeys, "steps": steps,
            "control_label": labelAfter, "control_names_files": shows(labelAfter),
            "files": files.map { ["filename": $0.name, "sha256": $0.sha256] },
            "note": "files chosen in the open panel — observe the page again"]
}
