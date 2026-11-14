// Optional benchmark transports. Default launches remain unchanged.
import Foundation
import Darwin
import CryptoKit

enum HaejoMode {
    static let limit = 8 * 1024 * 1024
    static let workerCount = 4
    static func workerKey(_ build: String, slot: Int) -> String {
        SHA256.hash(data: Data("\(build):worker:\(slot)".utf8))
            .map { String(format:"%02x", $0) }.joined()
    }
    // Retry acquisition only. No application frame exists until this returns.
    static func waitForLease<T>(seconds: Double, attempt: () -> T,
                                busy: (T) -> Bool, cancelled: () -> Bool) -> T? {
        let deadline = ProcessInfo.processInfo.systemUptime + seconds
        var result = attempt()
        while busy(result) {
            if cancelled() { return nil }
            if ProcessInfo.processInfo.systemUptime >= deadline { return result }
            usleep(50_000)
            if cancelled() { return nil }
            result = attempt()
        }
        return result
    }
    static func buildKey(_ binary: URL) -> String? {
        guard let bytes = try? Data(contentsOf: binary) else { return nil }
        return SHA256.hash(data: bytes).map { String(format:"%02x", $0) }.joined()
    }
    static func directory(_ key: String) -> String? {
        let count = confstr(_CS_DARWIN_USER_TEMP_DIR,nil,0)
        guard count > 1, count <= 4096 else { return nil }
        var bytes = [CChar](repeating:0,count:count)
        guard confstr(_CS_DARWIN_USER_TEMP_DIR,&bytes,bytes.count) == count else { return nil }
        let parent = String(cString:bytes)
        var parentInfo = stat()
        guard lstat(parent,&parentInfo) == 0, parentInfo.st_uid == getuid(),
              parentInfo.st_mode & S_IFMT == S_IFDIR, parentInfo.st_mode & 0o777 == 0o700 else { return nil }
        let path = parent + (parent.hasSuffix("/") ? "" : "/") + "haejo-warm-\(key.prefix(20))"
        guard address(path+"/helper.sock") != nil else { return nil }
        if mkdir(path, 0o700) != 0 && errno != EEXIST { return nil }
        var info = stat()
        guard lstat(path, &info) == 0, info.st_uid == getuid(),
              info.st_mode & S_IFMT == S_IFDIR, info.st_mode & 0o777 == 0o700 else { return nil }
        return path
    }
    static func address(_ path: String) -> sockaddr_un? {
        var addr = sockaddr_un(); addr.sun_family = sa_family_t(AF_UNIX)
        guard path.utf8.count < MemoryLayout.size(ofValue:addr.sun_path) else { return nil }
        withUnsafeMutableBytes(of:&addr.sun_path) { dst in
            Array(path.utf8CString).withUnsafeBytes { src in dst.copyBytes(from:src) }
        }
        return addr
    }
    static func connect(_ path: String) -> Int32? {
        let fd = socket(AF_UNIX,SOCK_STREAM,0)
        guard fd >= 0, var addr = address(path) else { return nil }
        let ok = withUnsafePointer(to:&addr) { p in p.withMemoryRebound(to:sockaddr.self,capacity:1) {
            Darwin.connect(fd,$0,socklen_t(MemoryLayout<sockaddr_un>.size)) == 0
        }}
        guard ok else { close(fd); return nil }; return fd
    }
    static func send(_ fd: Int32, _ object: [String:Any]) -> Bool {
        guard var data = try? JSONSerialization.data(withJSONObject:object) else { return false }
        data.append(10); var position = 0
        return data.withUnsafeBytes { bytes in
            while position < data.count {
                let n = write(fd, bytes.baseAddress!.advanced(by:position), data.count-position)
                if n < 0 && errno == EINTR { continue }
                if n <= 0 { return false }; position += n
            }
            return true
        }
    }
    // Used only for the tiny pre-request handshake; read exactly through LF,
    // never consume a following application frame.
    static func receive(_ fd: Int32, seconds: Double = 3) -> [String:Any]? {
        var bytes = Data(); let deadline = ProcessInfo.processInfo.systemUptime + seconds
        while bytes.count < 4096 {
            let left = deadline - ProcessInfo.processInfo.systemUptime
            if left <= 0 { return nil }
            var p = pollfd(fd:fd,events:Int16(POLLIN),revents:0)
            let result = poll(&p,1,Int32(max(1,left*1000)))
            if result < 0 && errno == EINTR { continue }
            guard result > 0 else { return nil }
            var byte: UInt8 = 0
            let n = read(fd,&byte,1)
            if n < 0 && errno == EINTR { continue }
            guard n == 1 else { return nil }
            if byte == 10 { return (try? JSONSerialization.jsonObject(with:bytes)) as? [String:Any] }
            bytes.append(byte)
        }
        return nil
    }
}

// Cross-process ownership also covers per-command helpers and different builds.
// Never unlink lock files: existing waiters must keep the same inode.
//
// Task claims (docs/parallel-execution.md): an exclusive hold taken for a task
// leaves `task` and `claim_until` in the note, so the scope stays with that
// task between its commands. A request that acts for another open task reads
// the note after its own flock succeeds and treats a live claim as busy; a
// read, and every command without a task, passes and leaves the claim as it is.
final class HaejoScopeLease {
    /// How long a claim outlives the last call its task made on the scope.
    nonisolated(unsafe) static var claimSeconds = 90
    /// The scope of the screen front, claimed where a task brings an app forward.
    nonisolated(unsafe) static var frontScope = "front"
    private struct Held {
        let fd: Int32, shared: Bool, since: Int
        /// The note as it was when this lease got the lock.
        let prior: [String:Any]?
        var extra: [String:Any] = [:]
    }
    private var descriptors: [String:Held] = [:]
    /// The client process this lease works for, written next to an exclusive
    /// hold so a refused waiter can say who has the app and for how long.
    var holderPID: Int32 = 0
    /// The task the current request belongs to; nil for a command without one.
    var task: String?
    /// The current request changes its target (an action, taking the front).
    var acting = false
    /// Claims other tasks hold on parts of a scope this lease takes whole
    /// (windows of an app, TaskClaims.swift). A live one counts as a claim on
    /// the scope itself: an acting request waits, and a read passes without
    /// leaving this task's claim on the whole.
    var partClaim: (() -> (task: String, left: Int)?)?
    /// Another task's live claim that covers `scope`, given the scope's note.
    private func foreignClaim(_ note: [String:Any]?) -> (task: String, left: Int)? {
        if let claim = HaejoScopeLease.liveClaim(note), claim.task != task { return claim }
        return task == nil ? nil : partClaim?()
    }
    static func isTask(_ value: String) -> Bool {
        value.range(of: "^t-[0-9a-f]{24}$", options: .regularExpression) != nil
    }
    /// Whether a task is still open, asked of the task store `haejo task`
    /// keeps (docs/tasks.md): `state` in its task.json. An ended, unknown or
    /// unreadable task holds no claim, so ending a task frees its scopes at once.
    nonisolated(unsafe) static var taskOpen: (String) -> Bool = { task in
        let file = NSHomeDirectory()+"/Library/Application Support/Haejo/Tasks/"+task+"/task.json"
        guard let data = FileManager.default.contents(atPath: file), data.count <= 64 * 1024,
              let meta = (try? JSONSerialization.jsonObject(with: data)) as? [String:Any] else { return false }
        return meta["state"] as? String == "open"
    }
    /// The claim a note still carries: its task and the seconds left.
    static func liveClaim(_ note: [String:Any]?) -> (task: String, left: Int)? {
        guard let task = note?["task"] as? String, isTask(task),
              let until = note?["claim_until"] as? Int else { return nil }
        let left = until - Int(Date().timeIntervalSince1970)
        guard left > 0, left <= claimSeconds, taskOpen(task) else { return nil }
        return (task, left)
    }
    fileprivate static func path(_ scope: String) -> String? {
        let namespace = HaejoMode.workerKey("tacto-resource-leases-v1", slot:0)
        guard let directory = HaejoMode.directory(namespace) else { return nil }
        let key = SHA256.hash(data:Data(scope.utf8)).map { String(format:"%02x",$0) }.joined()
        return directory+"/"+key+".lock"
    }
    private static func read(_ fd: Int32) -> [String:Any]? {
        var bytes = [UInt8](repeating: 0, count: 256)
        let count = pread(fd, &bytes, bytes.count, 0)
        guard count > 0, count < 256 else { return nil }
        return (try? JSONSerialization.jsonObject(with: Data(bytes[0..<count]))) as? [String:Any]
    }
    /// Numbers and a task ID only; never a command line or window text. One
    /// write of a fixed length, so a reader sees the old note or the new one.
    private static func write(_ fd: Int32, _ note: [String:Any]) {
        guard var data = try? JSONSerialization.data(withJSONObject: note, options: [.sortedKeys]),
              data.count < 256 else { return }
        if data.count < 240 { data.append(Data(repeating: 0x20, count: 240 - data.count)) }
        _ = data.withUnsafeBytes { pwrite(fd, $0.baseAddress, data.count, 0) }
        _ = ftruncate(fd, off_t(data.count))
    }
    /// Admit the current request on a lock this lease has, and keep the note:
    /// its own claim renewed, or another task's claim carried over untouched.
    private func settle(_ held: Held, fresh: Bool) -> Bool {
        let foreign = foreignClaim(held.prior)
        if foreign != nil, acting, task != nil { return false }
        guard !held.shared, fresh || (task != nil && foreign == nil) else { return true }
        var note: [String:Any] = ["pid": Int(holderPID > 0 ? holderPID : getpid()),
                                  "helper_pid": Int(getpid()), "since": held.since]
        if foreign != nil {
            for key in ["task","claim_until","previous_front","previous_start","raised"] { note[key] = held.prior?[key] }
        } else if let task {
            note.merge(held.extra) { current, _ in current }
            note["task"] = task
            note["claim_until"] = Int(Date().timeIntervalSince1970) + HaejoScopeLease.claimSeconds
        }
        HaejoScopeLease.write(held.fd, note)
        return true
    }
    func take(_ scope: String, shared: Bool = false) -> Bool {
        if let held = descriptors[scope] {
            guard !held.shared || shared else { return false }
            if settle(held, fresh: false) { return true }
            // This connection got the lock for a read; another task's claim is
            // still live, so the lock goes back and that task's next command
            // gets it while this request waits its turn.
            _ = flock(held.fd,LOCK_UN); close(held.fd); descriptors[scope] = nil
            return false
        }
        guard let file = HaejoScopeLease.path(scope) else { return false }
        let fd = open(file,O_CREAT|O_RDWR|O_NOFOLLOW|O_CLOEXEC,0o600)
        guard fd >= 0 else { return false }
        var info = stat()
        guard fstat(fd,&info) == 0, info.st_uid == getuid(),
              info.st_mode & S_IFMT == S_IFREG, info.st_mode & 0o777 == 0o600,
              flock(fd,(shared ? LOCK_SH : LOCK_EX)|LOCK_NB) == 0 else { close(fd); return false }
        let held = Held(fd: fd, shared: shared, since: Int(Date().timeIntervalSince1970),
                        prior: HaejoScopeLease.read(fd))
        // Another task's claim is live: give the lock back, so that task's
        // next command gets it, and let the caller's wait loop come round.
        guard settle(held, fresh: true) else { _ = flock(fd,LOCK_UN); close(fd); return false }
        descriptors[scope] = held; return true
    }
    /// Take `scope`, waiting in turn until `until` (system uptime). A scope
    /// nobody waits for is taken at once: the only cost is one `stat`. Once a
    /// take fails this request gets a waiter ticket, and the oldest live
    /// waiter is the one that tries next (HaejoWaitQueue).
    func wait(_ scope: String, shared: Bool = false, until: Double, cancelled: () -> Bool) -> Bool {
        if cancelled() { return false }
        if descriptors[scope] != nil || !HaejoWaitQueue.waiting(scope) {
            if take(scope, shared: shared) { return true }
            if ProcessInfo.processInfo.systemUptime >= until { return false }
        }
        let ticket = HaejoWaitQueue.Ticket(scope, shared: shared)
        defer { ticket.leave() }
        while true {
            if cancelled() { return false }
            // Another task's claim that this request cannot pass: its ticket
            // says so, and requests the claim lets through go past it.
            let claim = acting && task != nil ? foreignClaim(HaejoScopeLease.note(scope))?.task : nil
            if ticket.turn(task: task, acting: acting, claim: claim), take(scope, shared: shared) { return true }
            if ProcessInfo.processInfo.systemUptime >= until { return false }
            usleep(20_000)
        }
    }
    /// Give `scope` back before this lease ends.
    func release(_ scope: String) {
        guard let held = descriptors.removeValue(forKey: scope) else { return }
        _ = flock(held.fd,LOCK_UN); close(held.fd)
    }
    /// The note `scope` carried when this lease took it.
    func prior(_ scope: String) -> [String:Any]? { descriptors[scope]?.prior }
    /// Extra numbers kept in this task's claim on `scope` (the front token).
    func annotate(_ scope: String, _ extra: [String:Any]) {
        guard var held = descriptors[scope] else { return }
        held.extra = extra; descriptors[scope] = held
        _ = settle(held, fresh: false)
    }
    /// Extend `task`'s claim on a scope no connection holds now, when its note
    /// still names that task and `matches` agrees.
    static func renew(_ scope: String, task: String, where matches: ([String:Any]) -> Bool) {
        guard let file = path(scope) else { return }
        let fd = open(file,O_RDWR|O_NOFOLLOW|O_CLOEXEC)
        guard fd >= 0 else { return }
        defer { close(fd) }
        guard flock(fd,LOCK_EX|LOCK_NB) == 0 else { return }
        defer { _ = flock(fd,LOCK_UN) }
        guard var note = read(fd), note["task"] as? String == task, matches(note) else { return }
        note["claim_until"] = Int(Date().timeIntervalSince1970) + claimSeconds
        write(fd, note)
    }
    /// Rewrite the note of a scope that is locked only for the moment of the
    /// edit (an index, not a resource). False when it could not be done now.
    @discardableResult
    static func edit(_ scope: String, _ change: ([String:Any]) -> [String:Any]?) -> Bool {
        guard let file = path(scope) else { return false }
        let fd = open(file,O_CREAT|O_RDWR|O_NOFOLLOW|O_CLOEXEC,0o600)
        guard fd >= 0 else { return false }
        defer { close(fd) }
        var info = stat()
        guard fstat(fd,&info) == 0, info.st_uid == getuid(),
              info.st_mode & S_IFMT == S_IFREG, info.st_mode & 0o777 == 0o600 else { return false }
        var locked = false
        for _ in 0..<25 { if flock(fd,LOCK_EX|LOCK_NB) == 0 { locked = true; break }; usleep(200) }
        guard locked else { return false }
        defer { _ = flock(fd,LOCK_UN) }
        if let note = change(read(fd) ?? [:]) { write(fd, note) }
        return true
    }
    static func note(_ scope: String) -> [String:Any]? {
        guard let file = path(scope),
              let data = FileManager.default.contents(atPath: file), !data.isEmpty, data.count < 256 else { return nil }
        return (try? JSONSerialization.jsonObject(with: data)) as? [String:Any]
    }
    /// Who holds `scope`: the live process named in its note, and the task
    /// whose claim on it is still running; nil when neither is known.
    static func holder(_ scope: String) -> [String:Any]? {
        guard let note = note(scope) else { return nil }
        var info: [String:Any] = [:]
        if let pid = note["pid"] as? Int, pid > 0, let since = note["since"] as? Int,
           kill(pid_t(pid), 0) == 0 || errno == EPERM {
            info["holder_pid"] = pid
            info["held_seconds"] = max(0, Int(Date().timeIntervalSince1970) - since)
            var name = [CChar](repeating: 0, count: 256)
            if proc_name(pid_t(pid), &name, UInt32(name.count)) > 0 {
                info["holder_process"] = String(cString: name)
            }
        }
        if let claim = liveClaim(note) {
            info["holder_task"] = claim.task
            info["claim_expires_in"] = claim.left
        }
        return info.isEmpty ? nil : info
    }
    deinit {
        for entry in descriptors.values { _ = flock(entry.fd,LOCK_UN); close(entry.fd) }
    }
}

// Waiter tickets: who has been waiting for a scope, oldest first.
//
// A request whose first take fails writes a ticket into the scope's queue
// file (next to its lock file, kept for good like the lock file) and, on every
// poll, tries the lock only when no older live ticket stands before it. A
// ticket leaves the file when its request gets the scope, gives up or is
// cancelled. No process tends the queue: a ticket whose process is gone, or
// whose `seen` second is older than `staleSeconds`, is dropped by whichever
// waiter reads the file next, so a crashed or stopped waiter holds nobody up.
//
// Who stands before whom:
// - two shared waiters go together; anything else goes in ticket order, so an
//   exclusive waiter is not overtaken by later shared ones;
// - a ticket that waits for another task's claim to end (not for the lock)
//   stands only before requests that claim can also turn away. A read, a
//   command without a task and the claim's own task pass it.
enum HaejoWaitQueue {
    static let limit = 32
    /// A ticket not refreshed for this long belongs to a waiter that stopped.
    nonisolated(unsafe) static var staleSeconds = 3
    nonisolated(unsafe) private static var counter = 0
    private struct Entry {
        var number: Int, pid: Int, id: Int, seen: Int, shared: Bool, claim: String
        var row: [Any] { [number, pid, id, seen, shared ? 1 : 0, claim] }
        init?(_ raw: Any) {
            guard let row = raw as? [Any], row.count == 6, let number = row[0] as? Int, let pid = row[1] as? Int,
                  let id = row[2] as? Int, let seen = row[3] as? Int, let shared = row[4] as? Int,
                  let claim = row[5] as? String else { return nil }
            self.init(number: number, pid: pid, id: id, seen: seen, shared: shared == 1, claim: claim)
        }
        init(number: Int, pid: Int, id: Int, seen: Int, shared: Bool, claim: String) {
            self.number = number; self.pid = pid; self.id = id; self.seen = seen; self.shared = shared; self.claim = claim
        }
    }
    private static func file(_ scope: String) -> String? {
        HaejoScopeLease.path(scope).map { String($0.dropLast(5)) + ".queue" }
    }
    /// Whether any ticket is in the scope's queue: one `stat`, no lock.
    static func waiting(_ scope: String) -> Bool {
        var info = stat()
        guard let file = file(scope), lstat(file, &info) == 0 else { return false }
        return info.st_size > 0
    }
    /// The live tickets of `scope`, oldest first: `[number, pid, shared]`.
    static func tickets(_ scope: String) -> [[Int]] {
        var rows: [[Int]] = []
        _ = edit(scope) { entries in rows = entries.map { [$0.number, $0.pid, $0.shared ? 1 : 0] }; return false }
        return rows
    }
    /// Read the queue under its own short lock, drop tickets of waiters that
    /// are gone, let `change` edit it, and write it back when anything changed.
    /// False when the queue cannot be read now; the caller then acts as a
    /// request without a ticket.
    private static func edit(_ scope: String, _ change: (inout [Entry]) -> Bool) -> Bool {
        guard let file = file(scope) else { return false }
        let fd = open(file, O_CREAT|O_RDWR|O_NOFOLLOW|O_CLOEXEC, 0o600)
        guard fd >= 0 else { return false }
        defer { close(fd) }
        var info = stat()
        guard fstat(fd, &info) == 0, info.st_uid == getuid(), info.st_mode & S_IFMT == S_IFREG,
              info.st_mode & 0o777 == 0o600 else { return false }
        // Held for microseconds by anyone; a holder that stopped is waited out briefly.
        var locked = false
        for _ in 0..<25 { if flock(fd, LOCK_EX|LOCK_NB) == 0 { locked = true; break }; usleep(200) }
        guard locked else { return false }
        defer { _ = flock(fd, LOCK_UN) }
        var bytes = [UInt8](repeating: 0, count: 4096)
        let count = pread(fd, &bytes, bytes.count, 0)
        let rows = count > 0 ? (try? JSONSerialization.jsonObject(with: Data(bytes[0..<count]))) as? [Any] ?? [] : []
        let now = Int(Date().timeIntervalSince1970)
        var entries = rows.compactMap { Entry($0) }.filter {
            now - $0.seen <= staleSeconds && $0.seen <= now + staleSeconds && (kill(pid_t($0.pid), 0) == 0 || errno == EPERM)
        }
        let dropped = entries.count != rows.count
        guard change(&entries) || dropped else { return true }
        entries.sort { $0.number < $1.number }
        guard !entries.isEmpty, let data = try? JSONSerialization.data(withJSONObject: entries.map { $0.row }),
              data.count <= 4096 else { _ = ftruncate(fd, 0); return true }
        _ = data.withUnsafeBytes { pwrite(fd, $0.baseAddress, data.count, 0) }
        _ = ftruncate(fd, off_t(data.count))
        return true
    }
    final class Ticket {
        private let scope: String, shared: Bool, id: Int
        private var joined = false
        init(_ scope: String, shared: Bool) {
            self.scope = scope; self.shared = shared
            HaejoWaitQueue.counter += 1; id = HaejoWaitQueue.counter
        }
        /// Whether this waiter is the one to try the lock now. `claim` is the
        /// task whose claim this request is waiting out, if one is.
        func turn(task: String?, acting: Bool, claim: String?) -> Bool {
            var mine = true
            let pid = Int(getpid()), now = Int(Date().timeIntervalSince1970)
            let read = HaejoWaitQueue.edit(scope) { entries in
                var changed = false
                var index = entries.firstIndex { $0.pid == pid && $0.id == self.id }
                if index == nil {
                    // A full queue leaves this request polling without a ticket.
                    guard entries.count < HaejoWaitQueue.limit else { return false }
                    entries.append(Entry(number: (entries.map { $0.number }.max() ?? 0) + 1, pid: pid, id: self.id,
                                         seen: now, shared: self.shared, claim: claim ?? ""))
                    index = entries.count - 1; changed = true; self.joined = true
                }
                var own = entries[index!]
                if own.seen != now || own.claim != claim ?? "" {
                    own.seen = now; own.claim = claim ?? ""; entries[index!] = own; changed = true
                }
                mine = !entries.contains { other in
                    other.number < own.number && !(self.shared && other.shared)
                        && (other.claim.isEmpty || (acting && task != nil && task != other.claim))
                }
                return changed
            }
            return !read || mine
        }
        func leave() {
            guard joined else { return }
            let pid = Int(getpid())
            _ = HaejoWaitQueue.edit(scope) { entries in
                let before = entries.count
                entries.removeAll { $0.pid == pid && $0.id == self.id }
                return entries.count != before
            }
            joined = false
        }
    }
}
