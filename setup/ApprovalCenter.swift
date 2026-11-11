import AppKit
import Darwin
import Security

/// Menu approval (opt-in, `require_menu_approval`). The CLI asks here for
/// consequential confirm steps; the person answers on a card. Grants given on
/// the card (this run, this task, always) answer later requests at once.
/// This process is the only place a decision or grant is made: the socket has
/// no operation that decides, it only asks, claims and consumes.
final class ApprovalCenter {
    static let shared = ApprovalCenter()
    static let changed = Notification.Name("ai.callabo.haejo.menu-approval.changed")
    static let clearAlways = Notification.Name("ai.callabo.haejo.menu-approval.clear-always")

    enum Choice: String { case once, task, always, deny }

    struct Grant: Equatable { let key: String; let owner: String; let expires: Date }

    final class Request {
        let id: String
        let request: [String:Any]
        let items: [[String:Any]]
        var status = "pending"          // pending allowed denied expired claimed completed partial
        var scope = ""
        var runID: String?
        var consumed = Set<Int>()
        let created = Date()
        let decided = DispatchSemaphore(value:0)
        init(id: String, request: [String:Any], items: [[String:Any]]) { self.id = id; self.request = request; self.items = items }
    }

    let directory: URL
    private let state = DispatchQueue(label:"ai.callabo.haejo.approval.state")
    var requests: [String:Request] = [:]   // internal for tests
    private var taskGrants: [Grant] = []
    private var listener: Int32 = -1
    private var observers: [NSObjectProtocol] = []
    static let pendingLifetime: TimeInterval = 30*60
    static let taskLifetime: TimeInterval = 60*60

    init(directory: URL = FileManager.default.homeDirectoryForCurrentUser
            .appendingPathComponent("Library/Application Support/Haejo")) {
        self.directory = directory
    }
    var socketURL: URL { directory.appendingPathComponent("approval.sock") }
    var alwaysURL: URL { directory.appendingPathComponent("approvals/always.json") }

    // MARK: lifecycle

    func refresh() {
        if observers.isEmpty {
            observers.append(NotificationCenter.default.addObserver(forName:Self.changed, object:nil, queue:.main) { [weak self] _ in self?.refresh() })
            observers.append(NotificationCenter.default.addObserver(forName:Self.clearAlways, object:nil, queue:.main) { [weak self] _ in self?.saveAlways([]) })
        }
        let on = (HaejoRuntimeStatus.preferences(in:directory)["require_menu_approval"] as? NSNumber)
            .map { CFGetTypeID($0) == CFBooleanGetTypeID() && $0.boolValue } ?? false
        if on && listener < 0 { start() } else if !on && listener >= 0 { stop() }
    }

    private func start() {
        guard (try? FileManager.default.createDirectory(at:directory, withIntermediateDirectories:true)) != nil else { return }
        let path = socketURL.path
        var info = stat()
        if lstat(path,&info) == 0 {
            // Replace only our own stale socket, never another file.
            guard (info.st_mode & S_IFMT) == S_IFSOCK, info.st_uid == getuid() else { return }
            unlink(path)
        }
        let fd = socket(AF_UNIX, SOCK_STREAM, 0)
        guard fd >= 0 else { return }
        var address = sockaddr_un(); address.sun_family = sa_family_t(AF_UNIX)
        let bytes = Array(path.utf8)
        guard bytes.count < MemoryLayout.size(ofValue:address.sun_path) else { close(fd); return }
        withUnsafeMutableBytes(of:&address.sun_path) { raw in raw.copyBytes(from:bytes) }
        let previous = umask(0o077)
        let bound = withUnsafePointer(to:&address) { $0.withMemoryRebound(to:sockaddr.self, capacity:1) {
            bind(fd, $0, socklen_t(MemoryLayout<sockaddr_un>.size)) } }
        umask(previous)
        guard bound == 0, chmod(path, 0o600) == 0, listen(fd, 16) == 0 else { close(fd); return }
        listener = fd
        DispatchQueue.global(qos:.userInitiated).async { [weak self] in self?.acceptLoop(fd) }
    }

    private func stop() {
        let fd = listener; listener = -1
        if fd >= 0 { shutdown(fd, SHUT_RDWR); close(fd); unlink(socketURL.path) }
    }

    private func acceptLoop(_ fd: Int32) {
        while true {
            let client = accept(fd, nil, nil)
            if client < 0 { if errno == EINTR { continue }; return }
            var uid = uid_t(0), gid = gid_t(0)
            guard getpeereid(client,&uid,&gid) == 0, uid == getuid() else { close(client); continue }
            // A caller that leaves before the answer must not take this app down.
            var on: Int32 = 1
            setsockopt(client, SOL_SOCKET, SO_NOSIGPIPE, &on, socklen_t(MemoryLayout<Int32>.size))
            DispatchQueue.global(qos:.userInitiated).async { [weak self] in self?.serve(client) }
        }
    }

    private func serve(_ client: Int32) {
        defer { close(client) }
        var data = Data(); var buffer = [UInt8](repeating:0, count:65536)
        while !data.contains(10) {
            let n = read(client,&buffer,buffer.count)
            if n <= 0 { return }
            data.append(contentsOf:buffer.prefix(n))
            if data.count > 1 << 20 { return }
        }
        guard let line = data.split(separator:10).first,
              let message = try? JSONSerialization.jsonObject(with:Data(line)) as? [String:Any] else { return }
        // Only the signed helper may ask about native input; checked only for
        // that op, from the connection itself.
        let reply = handle(message, helperPeer: message["op"] as? String == "native_check" && Self.peerIsHelper(client),
                           callerGone: { Self.hungUp(client) })
        guard var out = try? JSONSerialization.data(withJSONObject:reply) else { return }
        out.append(10)
        out.withUnsafeBytes { raw in _ = write(client, raw.baseAddress, raw.count) }
    }

    // MARK: protocol

    func handle(_ message: [String:Any], helperPeer: Bool = false, callerGone: @escaping () -> Bool = { false }) -> [String:Any] {
        switch message["op"] as? String {
        case "native_check": return helperPeer ? nativeCheck(message, callerGone: callerGone) : ["status":"refused"]
        case "plan": return plan(message)
        case "resume": return resume(message)
        case "claim": return claim(message)
        case "consume": return consume(message)
        case "finish": return finish(message)
        case "runtime": return runtime(message)
        default: return ["status":"invalid"]
        }
    }

    static func key(_ request: [String:Any], _ item: [String:Any]) -> String {
        let effects = (item["effects"] as? [String] ?? []).sorted().joined(separator:",")
        return [request["target"] as? String ?? "", request["team"] as? String ?? "", effects,
                item["destination"] as? String ?? "", item["object_type"] as? String ?? ""].joined(separator:"\u{1f}")
    }
    /// Payments and credential entry are approved one at a time, never by a broader grant.
    static func sensitive(_ item: [String:Any]) -> Bool {
        let effects = item["effects"] as? [String] ?? []
        if ["financial", "credential"].contains(item["class"] as? String ?? "") { return true }
        return effects.contains("financial") || effects.contains("credential")
    }
    static func financial(_ item: [String:Any]) -> Bool { (item["effects"] as? [String] ?? []).contains("financial") }
    static func irreversibleDelete(_ item: [String:Any]) -> Bool {
        (item["effects"] as? [String] ?? []).contains("delete") && item["reversibility"] as? String == "irreversible"
    }
    static func taskHint(_ request: [String:Any]) -> String { request["task_hint"] as? String ?? "" }
    /// Which broader choices a card may offer for these items.
    static func choices(_ items: [[String:Any]], task: Bool = true, identified: Bool = true) -> [Choice] {
        guard identified else { return [.once, .deny] }
        var result: [Choice] = [.once]
        if task && !items.contains(where:sensitive) { result.append(.task) }
        if !items.contains(where:{ sensitive($0) || irreversibleDelete($0) }) { result.append(.always) }
        result.append(.deny)
        return result
    }
    static func canonical(_ value: Any) -> Data {
        (try? JSONSerialization.data(withJSONObject:value, options:[.sortedKeys])) ?? Data()
    }

    /// The signing team of the app a request targets, resolved here rather than taken from the
    /// caller. Running copies are what Haejo acts on, so they decide; with none running, the copy
    /// LaunchServices would open. nil means "cannot tell one app" (copies from different teams,
    /// a name rather than a bundle id): such a request gets no broader grant at all.
    var teamResolver: (String) -> String? = { bundle in
        func team(_ code: SecStaticCode) -> String? {
            var info: CFDictionary?
            guard SecCodeCopySigningInformation(code, SecCSFlags(rawValue:kSecCSSigningInformation), &info) == errSecSuccess,
                  let dict = info as? [String:Any] else { return nil }
            return dict[kSecCodeInfoTeamIdentifier as String] as? String ?? ""
        }
        guard bundle.contains("."), !bundle.contains(" ") else { return nil }
        let running = NSRunningApplication.runningApplications(withBundleIdentifier:bundle)
        if !running.isEmpty {
            var teams = Set<String>()
            for app in running {
                var guest: SecCode?, image: SecStaticCode?
                guard SecCodeCopyGuestWithAttributes(nil, [kSecGuestAttributePid: app.processIdentifier] as CFDictionary, [], &guest) == errSecSuccess,
                      let guest, SecCodeCopyStaticCode(guest, [], &image) == errSecSuccess, let image,
                      let value = team(image) else { return nil }
                teams.insert(value)
            }
            return teams.count == 1 ? teams.first : nil
        }
        guard let url = NSWorkspace.shared.urlForApplication(withBundleIdentifier:bundle) else { return nil }
        var code: SecStaticCode?
        guard SecStaticCodeCreateWithPath(url as CFURL, [], &code) == errSecSuccess, let code else { return nil }
        return team(code)
    }
    private func identified(_ request: [String:Any]) -> [String:Any] {
        var copy = request
        if let team = teamResolver(request["target"] as? String ?? "") { copy["team"] = team }
        else { copy["team"] = NSNull(); copy["unidentified"] = true }
        return copy
    }
    static func identifiable(_ request: [String:Any]) -> Bool { request["unidentified"] as? Bool != true }

    /// True when a grant the person already gave covers this item now. Call inside `state`.
    private func coveredLocked(_ request: [String:Any], _ item: [String:Any]) -> Bool {
        guard !Self.sensitive(item), Self.identifiable(request) else { return false }
        let key = Self.key(request,item), now = Date(), owner = Self.taskHint(request)
        if !owner.isEmpty && taskGrants.contains(where:{ $0.key == key && $0.owner == owner && $0.expires > now }) { return true }
        return !Self.irreversibleDelete(item) && loadAlways().contains(key)
    }
    func covered(_ request: [String:Any], _ item: [String:Any]) -> Bool { state.sync { coveredLocked(request,item) } }

    private func plan(_ message: [String:Any]) -> [String:Any] {
        guard let raw = message["request"] as? [String:Any], let items = raw["items"] as? [[String:Any]], !items.isEmpty
        else { return ["status":"invalid"] }
        let request = identified(raw)
        let id = "ap_" + UUID().uuidString.replacingOccurrences(of:"-", with:"").lowercased().prefix(16)
        let entry = Request(id:String(id), request:request, items:items)
        let immediate: Bool = state.sync {
            prune()
            requests[entry.id] = entry
            guard items.allSatisfy({ coveredLocked(request,$0) }) else { return false }
            entry.status = "allowed"; entry.scope = "grant"
            return true
        }
        if immediate { return ["status":"allowed", "approval_id":entry.id, "scope":"grant"] }
        present(entry, deadline:Self.pendingLifetime)
        let wait = min(max((message["wait"] as? NSNumber)?.doubleValue ?? 45, 1), 120)
        _ = entry.decided.wait(timeout:.now() + wait)
        return state.sync { ["status":entry.status, "approval_id":entry.id, "scope":entry.scope] }
    }

    private func resume(_ message: [String:Any]) -> [String:Any] {
        guard let id = message["approval_id"] as? String, let raw = message["request"] as? [String:Any]
        else { return ["status":"invalid"] }
        let request = identified(raw)
        return state.sync {
            prune()
            guard let entry = requests[id] else { return ["status":"expired", "approval_id":id] }
            // The whole approved request must be the same: steps, contracts, recipients, payloads and app.
            for field in ["flow_digest","params_digest","target","team","task_hint"] where
                Self.canonical([entry.request[field] ?? NSNull()]) != Self.canonical([request[field] ?? NSNull()]) {
                return ["status":"mismatch", "approval_id":id]
            }
            if (entry.request["window_id"] as? NSNumber) != (request["window_id"] as? NSNumber)
                || Self.canonical(entry.items) != Self.canonical(request["items"] ?? []) {
                return ["status":"mismatch", "approval_id":id]
            }
            return ["status":entry.status, "approval_id":id, "scope":entry.scope]
        }
    }

    private func claim(_ message: [String:Any]) -> [String:Any] {
        guard let id = message["approval_id"] as? String, let run = message["run_id"] as? String, !run.isEmpty
        else { return ["ok":false, "reason":"invalid"] }
        return state.sync {
            guard let entry = requests[id] else { return ["ok":false, "reason":"expired"] }
            guard entry.status == "allowed", entry.runID == nil else {
                return ["ok":false, "reason": entry.runID != nil ? "claimed" : entry.status]
            }
            entry.runID = run; entry.status = "claimed"
            return ["ok":true]
        }
    }

    /// Check and spend in one serial step: the run owns the request, the item and payload
    /// match, the step has not been spent, and a broader grant still stands.
    private func consume(_ message: [String:Any]) -> [String:Any] {
        guard let id = message["approval_id"] as? String, let run = message["run_id"] as? String,
              let step = (message["step"] as? NSNumber)?.intValue else { return ["ok":false, "reason":"invalid"] }
        let digest = message["payload_digest"] as? String
        return state.sync {
            guard let entry = requests[id], entry.status == "claimed", entry.runID == run,
                  let item = entry.items.first(where:{ ($0["step"] as? NSNumber)?.intValue == step }),
                  let expected = item["payload_digest"] as? String, expected == digest else { return ["ok":false, "reason":"mismatch"] }
            if entry.consumed.contains(step) { return ["ok":false, "reason":"consumed"] }
            if entry.scope != "once" && !coveredLocked(entry.request, item) { return ["ok":false, "reason":"revoked"] }
            entry.consumed.insert(step)
            return ["ok":true]
        }
    }

    private func finish(_ message: [String:Any]) -> [String:Any] {
        guard let id = message["approval_id"] as? String, let run = message["run_id"] as? String else { return ["ok":false] }
        return state.sync {
            guard let entry = requests[id], entry.runID == run else { return ["ok":false] }
            entry.status = message["outcome"] as? String == "completed" ? "completed" : "partial"
            return ["ok":true]
        }
    }

    private func runtime(_ message: [String:Any]) -> [String:Any] {
        let item = message["item"] as? [String:Any]
        let request = identified(["target": message["target"] as? String ?? "", "task_hint": message["task_hint"] ?? NSNull()])
        if let item, covered(request,item) { return ["status":"allowed", "scope":"grant"] }
        var described = item ?? [:]
        if described["describe"] == nil { described["describe"] = message["question"] as? String ?? "" }
        let entry = Request(id:"rt_" + UUID().uuidString.prefix(8), request:request, items:[described])
        let wait = min(max((message["wait"] as? NSNumber)?.doubleValue ?? 600, 1), 600)
        present(entry, deadline:wait, offerBroader:item != nil)
        if entry.decided.wait(timeout:.now() + wait) == .timedOut {
            state.sync { if entry.status == "pending" { entry.status = "timeout" } }
        }
        return state.sync { ["status": entry.status == "pending" ? "timeout" : entry.status, "scope":entry.scope] }
    }

    // MARK: native input (stage 2)

    var nativeWait: TimeInterval = 600     // internal for tests
    static let classWords = ["transmit":"전송", "financial":"결제·송금", "delete":"삭제", "credential":"자격 증명 입력"]

    /// The helper read this input and is holding it until the answer. The
    /// card is built from what the helper read. Until the helper also reads
    /// the recipient, an answer covers this one input only.
    /// The helper closed its end (Esc, or its own caller left).
    static func hungUp(_ fd: Int32) -> Bool {
        var channel = pollfd(fd:fd, events:Int16(POLLIN), revents:0)
        guard poll(&channel, 1, 0) > 0 else { return false }
        if channel.revents & Int16(POLLHUP|POLLERR|POLLNVAL) != 0 { return true }
        var byte: UInt8 = 0
        return recv(fd, &byte, 1, MSG_PEEK|MSG_DONTWAIT) == 0
    }

    private func nativeCheck(_ message: [String:Any], callerGone: @escaping () -> Bool) -> [String:Any] {
        guard let item = message["item"] as? [String:Any], let cls = item["class"] as? String,
              Self.classWords[cls] != nil else { return ["status":"invalid"] }
        var described = item
        described["describe"] = Self.nativeDescribe(item)
        let request: [String:Any] = ["target": item["target"] as? String ?? "", "team": item["team"] as? String ?? "",
                                     "window": item["window"] as? String ?? ""]
        let entry = Request(id:"nt_" + UUID().uuidString.replacingOccurrences(of:"-", with:"").prefix(12).lowercased(),
                            request:request, items:[described])
        state.sync { requests[entry.id] = entry }
        present(entry, deadline:nativeWait, offerBroader:false)
        // Wait in slices: a request the helper has dropped ends here and its
        // card closes, so a late "allow" cannot reach an input nobody waits for.
        let until = Date().addingTimeInterval(nativeWait)
        while entry.decided.wait(timeout:.now() + 0.25) == .timedOut {
            if callerGone() { state.sync { if entry.status == "pending" { entry.status = "cancelled" } }; break }
            if Date() >= until { state.sync { if entry.status == "pending" { entry.status = "timeout" } }; break }
        }
        return state.sync {
            let status = entry.status == "pending" ? "timeout" : entry.status
            requests[entry.id] = nil
            return ["status": status]
        }
    }

    static func nativeDescribe(_ item: [String:Any]) -> String {
        let word = classWords[item["class"] as? String ?? ""] ?? "확인이 필요한 입력"
        let label = (item["labels"] as? [String])?.first(where: { !$0.isEmpty })
            ?? (item["default_button"] as? [String])?.first(where: { !$0.isEmpty }) ?? ""
        let app = item["app_name"] as? String ?? ""
        var line = word + (label.isEmpty ? "" : ": '\(label)'")
        if !app.isEmpty { line += " (\(app))" }
        if let window = item["window"] as? String, !window.isEmpty { line += "\n창: \(window)" }
        return line
    }

    /// The connecting process is Haejo Helper signed by this app's own team.
    static func peerIsHelper(_ fd: Int32) -> Bool {
        guard let team = ownTeam() else { return false }
        var token = audit_token_t()
        var length = socklen_t(MemoryLayout<audit_token_t>.size)
        guard getsockopt(fd, SOL_LOCAL, LOCAL_PEERTOKEN, &token, &length) == 0 else { return false }
        let data = withUnsafeBytes(of:&token) { Data($0) } as CFData
        var code: SecCode?
        guard SecCodeCopyGuestWithAttributes(nil, [kSecGuestAttributeAudit: data] as CFDictionary, [], &code) == errSecSuccess,
              let code else { return false }
        var requirement: SecRequirement?
        let text = "identifier \"ai.callabo.haejo.helper\" and anchor apple generic and certificate leaf[subject.OU] = \"\(team)\""
        guard SecRequirementCreateWithString(text as CFString, [], &requirement) == errSecSuccess, let requirement else { return false }
        return SecCodeCheckValidity(code, [], requirement) == errSecSuccess
    }

    static func ownTeam() -> String? {
        var own: SecCode?
        guard SecCodeCopySelf([], &own) == errSecSuccess, let own else { return nil }
        var binary: SecStaticCode?
        guard SecCodeCopyStaticCode(own, [], &binary) == errSecSuccess, let binary else { return nil }
        var raw: CFDictionary?
        guard SecCodeCopySigningInformation(binary, SecCSFlags(rawValue:kSecCSSigningInformation), &raw) == errSecSuccess,
              let info = raw as? [String:Any], let team = info[kSecCodeInfoTeamIdentifier as String] as? String,
              team.range(of:"^[A-Z0-9]{10}$", options:.regularExpression) != nil else { return nil }
        return team
    }

    // MARK: decisions

    func decide(_ entry: Request, _ choice: Choice) {
        state.sync {
            guard entry.status == "pending" else { return }
            switch choice {
            case .deny: entry.status = "denied"
            case .once: entry.status = "allowed"; entry.scope = "once"
            case .task:
                // Bound to the task that asked; another task gets its own card.
                entry.status = "allowed"; entry.scope = "task"
                let owner = Self.taskHint(entry.request)
                for item in entry.items where !Self.sensitive(item) && !owner.isEmpty && Self.identifiable(entry.request) {
                    taskGrants.append(Grant(key:Self.key(entry.request,item), owner:owner,
                                            expires:Date().addingTimeInterval(Self.taskLifetime)))
                }
            case .always:
                entry.status = "allowed"; entry.scope = "always"
            }
        }
        if choice == .always {
            var keys = loadAlways()
            for item in entry.items where !Self.sensitive(item) && !Self.irreversibleDelete(item) && Self.identifiable(entry.request) {
                keys.insert(Self.key(entry.request,item))
            }
            saveAlways(keys)
        }
        entry.decided.signal()
    }

    private func prune() {
        let now = Date()
        taskGrants.removeAll { $0.expires <= now }
        for (id, entry) in requests where now.timeIntervalSince(entry.created) > Self.pendingLifetime {
            if entry.status == "pending" { entry.status = "expired"; entry.decided.signal() }
            if !["claimed"].contains(entry.status) { requests[id] = nil }
        }
    }

    // MARK: always grants (owned by this app)

    func loadAlways() -> Set<String> {
        guard let data = try? Data(contentsOf:alwaysURL),
              let list = try? JSONSerialization.jsonObject(with:data) as? [String] else { return [] }
        return Set(list)
    }
    func saveAlways(_ keys: Set<String>) {
        let folder = alwaysURL.deletingLastPathComponent()
        try? FileManager.default.createDirectory(at:folder, withIntermediateDirectories:true, attributes:[.posixPermissions:0o700])
        guard let data = try? JSONSerialization.data(withJSONObject:keys.sorted()) else { return }
        try? data.write(to:alwaysURL, options:.atomic)
        chmod(alwaysURL.path, 0o600)
    }

    // MARK: card

    private var queue: [(Request, TimeInterval, Bool)] = []
    private var showing = false

    private func present(_ entry: Request, deadline: TimeInterval, offerBroader: Bool = true) {
        DispatchQueue.main.async {
            self.queue.append((entry, deadline, offerBroader))
            self.showNext()
        }
    }

    private func showNext() {
        guard !showing, !queue.isEmpty else { return }
        let (entry, deadline, offerBroader) = queue.removeFirst()
        if state.sync(execute:{ entry.status != "pending" }) { showNext(); return }
        showing = true
        let alert = NSAlert()
        alert.alertStyle = .warning
        let target = entry.request["target"] as? String ?? ""
        alert.messageText = "Haejo 승인 요청" + (target.isEmpty ? "" : " — \(target)")
        alert.informativeText = Self.summary(entry)
        let choices = offerBroader ? Self.choices(entry.items, task:!Self.taskHint(entry.request).isEmpty,
                                                  identified:Self.identifiable(entry.request)) : [.once, .deny]
        let titles: [Choice:String] = [.once:"이번만 허용", .task:"이 작업 동안 허용(1시간)", .always:"항상 허용", .deny:"거절"]
        for choice in choices { alert.addButton(withTitle:titles[choice]!) }
        alert.buttons.last?.keyEquivalent = "\u{1b}"
        alert.buttons.first?.keyEquivalent = ""
        let timer = Timer(timeInterval:deadline, repeats:false) { _ in NSApp.abortModal() }
        RunLoop.main.add(timer, forMode:.modalPanel)
        // A request ended elsewhere (cancelled by its caller) closes its card.
        let watch = Timer(timeInterval:0.25, repeats:true) { [weak self] _ in
            if self?.state.sync(execute:{ entry.status != "pending" }) == true { NSApp.abortModal() }
        }
        RunLoop.main.add(watch, forMode:.modalPanel)
        NSApp.activate(ignoringOtherApps:true)
        let response = alert.runModal()
        timer.invalidate(); watch.invalidate()
        let index = response.rawValue - NSApplication.ModalResponse.alertFirstButtonReturn.rawValue
        if index >= 0 && index < choices.count { decide(entry, choices[index]) }
        else { state.sync { if entry.status == "pending" { entry.status = entry.id.hasPrefix("rt_") ? "timeout" : "expired" } }; entry.decided.signal() }
        showing = false
        showNext()
    }

    static func summary(_ entry: Request) -> String {
        var lines: [String] = []
        for item in entry.items {
            var line = "• " + (item["describe"] as? String ?? "확인이 필요한 단계")
            if let destination = item["destination"] as? String, !destination.isEmpty, !line.contains(destination) { line += " (받는 곳: \(destination))" }
            lines.append(line)
        }
        if let task = entry.request["task_hint"] as? String, !task.isEmpty { lines.append("작업: \(task)") }
        if let window = entry.request["window_id"] as? NSNumber { lines.append("창: \(window)") }
        if entry.items.contains(where:sensitive) { lines.append("결제·송금·자격 증명 입력은 매번 확인합니다.") }
        return lines.joined(separator:"\n")
    }
}
