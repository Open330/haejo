import Foundation
import CoreFoundation

/// Ephemeral UI metadata only. Notifications never authorize input or reset an abort.
enum HaejoRuntimeStatus {
    static let status = Notification.Name("open330.haejo.runtime.status")
    static let query = Notification.Name("open330.haejo.runtime.query")
    static let stop = Notification.Name("open330.haejo.runtime.stop")
    /// Batch coordinators hear this even before a worker acquires a helper.
    static let stopAll = Notification.Name("open330.haejo.runtime.stop-all")

    struct Run {
        let id: String
        let pid: Int32
        let target: String
        let stopped: Bool
        let active: Bool
        /// Optional schema-1 extensions. Older helpers omit them and older
        /// consumers ignore them; a malformed value is dropped, never guessed.
        /// `windowID` is only the helper-accepted window scope. `outcome` is
        /// what the helper itself returned — postconditions are verified by the
        /// caller, so nothing here claims an effect was verified.
        let windowID: UInt32?
        let phase: String?
        let action: String?
        let outcome: String?
        static let phases: Set<String> = ["running","waiting"]
        static let outcomes: Set<String> = ["observed","dispatched","not_started","unknown","error"]
        static func token(_ raw: Any?) -> String? {
            guard let text = raw as? String, (1...32).contains(text.utf8.count),
                  text.utf8.allSatisfy({ (0x61...0x7a).contains($0) || $0 == 0x5f }) else { return nil }
            return text
        }
        init?(_ info: [AnyHashable: Any]) {
            guard let schema = info["schema"] as? NSNumber,
                  CFGetTypeID(schema) != CFBooleanGetTypeID(), schema.doubleValue == 1,
                  let uid = info["uid"] as? NSNumber, CFGetTypeID(uid) != CFBooleanGetTypeID(), uid.doubleValue == Double(getuid()),
                  let id = info["id"] as? String, UUID(uuidString:id) != nil,
                  let pid = info["pid"] as? NSNumber, CFGetTypeID(pid) != CFBooleanGetTypeID(), pid.doubleValue > 0, pid.doubleValue <= Double(Int32.max), pid.doubleValue == Double(pid.int32Value),
                  let target = info["target"] as? String, !target.isEmpty, target.utf8.count <= 256, target.rangeOfCharacter(from:.controlCharacters) == nil,
                  let stopped = info["stopped"] as? NSNumber, CFGetTypeID(stopped) == CFBooleanGetTypeID(),
                  let active = info["active"] as? NSNumber, CFGetTypeID(active) == CFBooleanGetTypeID()
            else { return nil }
            self.id=id; self.pid=pid.int32Value; self.target=target
            self.stopped=stopped.boolValue; self.active=active.boolValue
            if let n = info["window_id"] as? NSNumber, CFGetTypeID(n) != CFBooleanGetTypeID(),
               n.doubleValue > 0, n.doubleValue <= Double(UInt32.max), n.doubleValue == Double(n.uint32Value) {
                windowID = n.uint32Value
            } else { windowID = nil }
            phase = Run.token(info["phase"]).flatMap { Run.phases.contains($0) ? $0 : nil }
            action = Run.token(info["action"])
            outcome = Run.token(info["outcome"]).flatMap { Run.outcomes.contains($0) ? $0 : nil }
        }
        /// Human words for known helper steps; unknown tokens stay as sent.
        static let actionLabels: [String:String] = [
            "observe":"관측", "read":"읽기", "click":"클릭", "set_value":"값 입력", "type_text":"텍스트 입력",
            "press_key":"키 입력", "resize_window":"창 크기 조절", "probe":"상태 확인", "capture":"화면 캡처",
            "menu_state":"메뉴 확인", "menu_items":"메뉴 확인", "selection":"선택 읽기", "document_text":"문서 읽기",
            "foreground_begin":"앞으로 가져오기", "foreground_end":"앞으로 가져오기 해제",
            "release_targets":"대상 해제", "window_list":"창 목록"]
        var actionLabel: String? { action.map { Run.actionLabels[$0] ?? $0 } }
        /// One menu line: app, window and the helper's own current state.
        var summary: String {
            var parts = [target]
            if let windowID { parts.append("창 \(windowID)") }
            if stopped { parts.append("중단됨") }
            else if phase == "running" { parts.append(actionLabel.map { "\($0) 중" } ?? "실행 중") }
            else if phase == "waiting" {
                switch (actionLabel, outcome) {
                case let (a?, "dispatched"?): parts.append("대기 · \(a) 전달됨(검증 전)")
                case let (a?, "not_started"?): parts.append("대기 · \(a) 시작 안 됨")
                case let (a?, "unknown"?): parts.append("대기 · \(a) 결과 불명")
                case let (a?, "error"?): parts.append("대기 · \(a) 오류")
                case (_, "observed"?): parts.append("대기 · 관측 완료")
                default: parts.append("대기")
                }
            }
            return parts.joined(separator:" · ")
        }
    }

    /// Read once without creating files. Invalid/foreign/symlinked files use defaults.
    static func preferences(in directory: URL = FileManager.default.homeDirectoryForCurrentUser
        .appendingPathComponent("Library/Application Support/Haejo")) -> [String:Any] {
        guard (try? directory.resourceValues(forKeys:[.isSymbolicLinkKey]).isSymbolicLink) != true else { return [:] }
        let fd = open(directory.appendingPathComponent("preferences.json").path, O_RDONLY | O_NOFOLLOW | O_NONBLOCK)
        guard fd >= 0 else { return [:] }
        defer { close(fd) }
        var info = stat()
        guard fstat(fd,&info) == 0, (info.st_mode & S_IFMT) == S_IFREG,
              info.st_uid == getuid(), info.st_size <= 16384 else { return [:] }
        var bytes = [UInt8](repeating:0,count:16385)
        let count = read(fd,&bytes,bytes.count)
        guard count >= 0, count <= 16384,
              let object = try? JSONSerialization.jsonObject(with:Data(bytes.prefix(count))) as? [String:Any],
              let schema = object["schema"] as? NSNumber,
              CFGetTypeID(schema) != CFBooleanGetTypeID(), schema.doubleValue == 1 else { return [:] }
        return object
    }
    static func showBanner(in directory: URL = FileManager.default.homeDirectoryForCurrentUser
        .appendingPathComponent("Library/Application Support/Haejo")) -> Bool {
        guard let value = preferences(in:directory)["show_control_banner"] as? NSNumber,
              CFGetTypeID(value) == CFBooleanGetTypeID() else { return true }
        return value.boolValue
    }
    struct HelperSettings: Equatable {
        let mode: String
        let idleSeconds: Int
    }
    static func helperSettings(_ object: [String:Any], environment: [String:String]) -> HelperSettings {
        let enabled = (object["keep_helper_warm"] as? NSNumber).flatMap {
            CFGetTypeID($0) == CFBooleanGetTypeID() ? $0.boolValue : nil
        } ?? false
        var minutes = 2
        if let n = object["helper_idle_minutes"] as? NSNumber,
           CFGetTypeID(n) != CFBooleanGetTypeID(), !["d","f"].contains(String(cString:n.objCType)),
           (1...10).contains(n.intValue) { minutes = n.intValue }
        // An explicit per_command disables the GUI option. No resident route ships.
        let mode = environment["HAEJO_HELPER_MODE"].map { $0 == "warm" ? "warm" : "per_command" }
            ?? (enabled ? "warm" : "per_command")
        var seconds = minutes * 60
        // Development/automation override; GUI range remains 1–10 minutes.
        if let raw = environment["HAEJO_HELPER_IDLE_SECONDS"], let n = Int(raw), (1...600).contains(n) { seconds = n }
        return HelperSettings(mode:mode,idleSeconds:seconds)
    }
}
