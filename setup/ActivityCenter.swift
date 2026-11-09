import AppKit
import Darwin

private func activityInteger(_ value: Any?) -> Int? {
    guard let n = value as? NSNumber, CFGetTypeID(n) != CFBooleanGetTypeID(),
          !["d","f"].contains(String(cString:n.objCType)), Double(n.intValue) == n.doubleValue else { return nil }
    return n.intValue
}

struct HaejoPreferences {
    var loggingEnabled = true
    var retentionDays = 30
    var showControlBanner = true
    var keepHelperWarm = false
    var helperIdleMinutes = 2
    var object: [String: Any] {
        ["schema": 1, "logging_enabled": loggingEnabled, "retention_days": retentionDays,
         "show_control_banner": showControlBanner, "keep_helper_warm": keepHelperWarm,
         "helper_idle_minutes": helperIdleMinutes]
    }
    init(_ object: [String: Any] = [:]) {
        func boolean(_ key: String, _ fallback: Bool) -> Bool {
            guard let n = object[key] as? NSNumber, CFGetTypeID(n) == CFBooleanGetTypeID() else { return fallback }
            return n.boolValue
        }
        loggingEnabled = boolean("logging_enabled", true)
        showControlBanner = boolean("show_control_banner", true)
        keepHelperWarm = boolean("keep_helper_warm", false)
        if let n = activityInteger(object["helper_idle_minutes"]), (1...10).contains(n) { helperIdleMinutes = n }
        if let n = activityInteger(object["retention_days"]), [7,30,90].contains(n) { retentionDays = n }
    }
}

struct ActivityStep: Equatable {
    var operation: String
    var action: String
    var target: String
    var elapsed: Double
    var outcome = "완료 확인 없음"
    var error = ""
    var ended = false
    var title: String {
        let names = ["observe":"앱 상태 확인", "capture":"앱 화면 확인", "ask":"모델에 판단 요청",
                     "credential_input":"위임된 로그인 필드 확인·입력", "credential_submit":"위임된 로그인 제출",
                     "list_targets":"실행 중인 앱 확인", "document_text":"문서 내용 확인", "menu_state":"메뉴 상태 확인"]
        if operation != "act" { return names[operation] ?? "앱 정보 확인" }
        return ["set_value":"텍스트 입력", "type_text":"텍스트 입력", "menu":"메뉴 실행", "click":"버튼 클릭",
                "double_click":"두 번 클릭", "drag":"드래그", "scroll":"스크롤", "press_key":"키 입력",
                "prepare_window":"작업 창 선택", "reopen_window":"창 다시 열기", "upload":"파일 첨부",
                "select_option":"항목 선택", "read":"결과 확인"][action] ?? "앱 동작 실행"
    }
}

struct ActivityRecord: Equatable {
    let url: URL
    var command = ""
    var target = ""
    var started = Date()
    var elapsed: Double = 0
    var exitCode: Int?
    var steps: [ActivityStep] = []
    var error = ""
    var truncated = false
    var damaged = false
    var foreground: Bool?
    var presentationSkipped = false
    var modelCalls: Int?
    var taskID: String?
    var invocationID: String?
    var complete: Bool { exitCode != nil && !command.isEmpty }
    var failed: Bool { exitCode.map { $0 != 0 } ?? false }
    var status: String { !complete ? "완료 확인 없음" : failed ? "실패" : "완료" }
    var title: String {
        ["first-run":"첫 작업", "observe":"앱 관찰", "run":"워크플로 실행", "replay":"워크플로 재사용",
         "do":"에이전트 작업", "session":"연속 작업", "batch":"반복 실행", "doctor":"상태 확인",
         "apps":"앱 목록 확인", "launch":"앱 열기", "capture":"화면 확인", "drag":"드래그",
         "web-upload":"파일 첨부", "auth":"Vault 위임 로그인", "windows":"창 목록 확인",
         "open-url":"웹 페이지 열기", "activate":"앱 앞으로 가져오기", "type":"텍스트 입력", "click":"클릭",
         "press":"키 입력", "read":"내용 읽기", "flows":"워크플로 관리", "show":"워크플로 보기"][command] ?? "Haejo 실행"
    }
    var appName: String {
        ["com.apple.TextEdit":"TextEdit", "com.apple.finder":"Finder", "com.apple.calculator":"계산기",
         "com.apple.Safari":"Safari", "com.google.Chrome":"Chrome"][target] ?? (target.isEmpty ? "이 Mac" : target)
    }
}

/// The task a group of calls was made for (`haejo task start`), from Tasks/<id>/task.json.
struct ActivityTask: Equatable {
    let id: String
    var goal = ""
    var detail = ""                       // agent-written description of the user's request
    var open = true
    var result: String?
    var notes: [ActivityNote] = []        // `haejo task note` / `task end --note`
    var reasons: [String: String] = [:]   // invocation id -> `--why`
}

struct ActivityNote: Equatable {
    let at: Date
    let text: String
}

/// One history row: every call made for one task, or a single call made outside any task.
struct ActivityGroup: Equatable {
    let key: String
    var records: [ActivityRecord]   // newest first
    var taskID: String?
    var task: ActivityTask?
    var isTask: Bool { taskID != nil }
    var started: Date { records.map { $0.started }.min() ?? Date() }
    var latest: Date { records.map { $0.started }.max() ?? Date() }
    var failed: Bool {
        if let task { return !task.open && task.result == "failed" }   // an open task is still in progress
        return records.contains { $0.failed }
    }
    var complete: Bool {
        if let task { return !task.open }
        return records.allSatisfy { $0.complete }
    }
    var title: String {
        guard let taskID else { return records.first?.title ?? "Haejo 실행" }
        if let goal = task?.goal, !goal.isEmpty { return goal }
        return "작업 \(taskID.prefix(10))"
    }
    var status: String {
        guard isTask else { return records.first?.status ?? "완료 확인 없음" }
        guard let task else { return records.contains { !$0.complete } ? "완료 확인 없음" : "기록만 있음" }
        if task.open { return "진행 중" }
        return ["done":"완료", "failed":"실패", "abandoned":"중단"][task.result ?? ""] ?? "종료"
    }
    var appNames: String {
        var seen: [String] = []
        for r in records.reversed() where !seen.contains(r.appName) { seen.append(r.appName) }
        return seen.prefix(3).joined(separator:", ") + (seen.count > 3 ? " 외 \(seen.count-3)" : "")
    }
}

final class ActivityStore {
    let root: URL
    var logs: URL { root.appendingPathComponent("Logs") }
    var preferencesURL: URL { root.appendingPathComponent("preferences.json") }
    private let pattern = try! NSRegularExpression(pattern: "^(haejo|tacto)-[0-9]{8}T[0-9]{12}Z-[0-9a-f]{32}\\.jsonl$")  // tacto-: pre-rename logs
    private var cache: [URL: (Date, Int, ActivityRecord)] = [:]
    let maximumBytes = 1_048_576 + 8192
    init(root: URL = FileManager.default.homeDirectoryForCurrentUser.appendingPathComponent("Library/Application Support/Haejo")) { self.root = root }
    func ownedDirectory(_ url: URL, create: Bool = false) throws {
        if create { try FileManager.default.createDirectory(at: url, withIntermediateDirectories: true, attributes: [.posixPermissions:0o700]) }
        let a = try FileManager.default.attributesOfItem(atPath: url.path)
        guard a[.type] as? FileAttributeType == .typeDirectory, (a[.ownerAccountID] as? NSNumber)?.uint32Value == getuid() else {
            throw NSError(domain:"HaejoActivity", code:1)
        }
    }
    func readPrivate(_ url: URL, limit: Int) throws -> Data {
        let fd = Darwin.open(url.path, O_RDONLY | O_NOFOLLOW | O_NONBLOCK)
        guard fd >= 0 else { throw NSError(domain:NSPOSIXErrorDomain, code:Int(errno)) }
        let handle = FileHandle(fileDescriptor:fd, closeOnDealloc:true)
        defer { try? handle.close() }
        var info = stat()
        guard fstat(fd, &info) == 0, info.st_mode & S_IFMT == S_IFREG, info.st_uid == getuid(), info.st_size <= limit else {
            throw NSError(domain:"HaejoActivity", code:2)
        }
        return try handle.read(upToCount:limit) ?? Data()
    }
    func preferences() throws -> HaejoPreferences {
        guard FileManager.default.fileExists(atPath: preferencesURL.path) else { return HaejoPreferences() }
        try ownedDirectory(root)
        guard let object = try JSONSerialization.jsonObject(with: readPrivate(preferencesURL, limit:16384)) as? [String:Any],
              (object["schema"] == nil || activityInteger(object["schema"]) == 1) else { throw NSError(domain:"HaejoActivity", code:3) }
        return HaejoPreferences(object)
    }
    func save(_ settings: HaejoPreferences) throws {
        try ownedDirectory(root, create:true)
        if let a = try? FileManager.default.attributesOfItem(atPath:preferencesURL.path) {
            guard a[.type] as? FileAttributeType == .typeRegular, (a[.ownerAccountID] as? NSNumber)?.uint32Value == getuid() else {
                throw NSError(domain:"HaejoActivity", code:4)
            }
        }
        let temporary = root.appendingPathComponent(".preferences-" + UUID().uuidString)
        defer { try? FileManager.default.removeItem(at:temporary) }
        let fd = Darwin.open(temporary.path, O_WRONLY | O_CREAT | O_EXCL | O_NOFOLLOW, 0o600)
        guard fd >= 0 else { throw NSError(domain:NSPOSIXErrorDomain, code:Int(errno)) }
        let handle = FileHandle(fileDescriptor:fd, closeOnDealloc:true)
        do {
            try handle.write(contentsOf:JSONSerialization.data(withJSONObject:settings.object, options:[.sortedKeys]))
            try handle.synchronize(); try handle.close()
        } catch { try? handle.close(); throw error }
        guard Darwin.rename(temporary.path, preferencesURL.path) == 0 else { throw NSError(domain:NSPOSIXErrorDomain, code:Int(errno)) }
    }
    func files() throws -> [(URL, Date, Int)] {
        guard FileManager.default.fileExists(atPath:logs.path) else { return [] }
        try ownedDirectory(root); try ownedDirectory(logs)
        return try FileManager.default.contentsOfDirectory(at:logs, includingPropertiesForKeys:nil).compactMap { url in
            let name = url.lastPathComponent
            guard pattern.firstMatch(in:name, range:NSRange(name.startIndex..., in:name)) != nil,
                  let a = try? FileManager.default.attributesOfItem(atPath:url.path),
                  a[.type] as? FileAttributeType == .typeRegular, (a[.ownerAccountID] as? NSNumber)?.uint32Value == getuid(),
                  let size = a[.size] as? Int, size <= maximumBytes else { return nil }
            return (url, a[.modificationDate] as? Date ?? .distantPast, size)
        }.sorted { $0.1 > $1.1 }
    }
    func records() throws -> [ActivityRecord] {
        let candidates = Array(try files().prefix(200))
        let keep = Set(candidates.map { $0.0 }); cache = cache.filter { keep.contains($0.key) }
        return candidates.compactMap { url, date, size in
            if let c = cache[url], c.0 == date && c.1 == size { return c.2 }
            guard let data = try? readPrivate(url, limit:maximumBytes) else { return nil }
            let record = parse(data, url:url, modified:date)
            cache[url] = (date, size, record); return record
        }
    }
    func parse(_ data: Data, url: URL, modified: Date) -> ActivityRecord {
        var record = ActivityRecord(url:url); record.started = modified
        guard let text = String(data:data, encoding:.utf8) else { record.damaged = true; return record }
        let lines = text.split(separator:"\n", omittingEmptySubsequences:true)
        let formatter = ISO8601DateFormatter(); formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        for (index, line) in lines.enumerated() {
            guard let row = try? JSONSerialization.jsonObject(with:Data(line.utf8)) as? [String:Any],
                  let event = row["event"] as? String, activityInteger(row["schema"]) == 1 else {
                if index < lines.count - 1 || text.hasSuffix("\n") { record.damaged = true }; continue
            }
            let elapsed = (row["elapsed_ms"] as? NSNumber)?.doubleValue ?? 0
            if elapsed.isFinite && elapsed >= 0 && elapsed < 1e12 { record.elapsed = max(record.elapsed, elapsed) }
            if let target = row["target"] as? String { record.target = String(target.prefix(255)) }
            switch event {
            case "command_start":
                record.command = row["command"] as? String ?? ""
                if let id = row["task_id"] as? String, id.utf8.count == 26, id.hasPrefix("t-"),
                   id.utf8.dropFirst(2).allSatisfy({ (0x30...0x39).contains($0) || (0x61...0x66).contains($0) }) { record.taskID = id }
                if let id = row["invocation_id"] as? String, id.utf8.count == 32,
                   id.utf8.allSatisfy({ (0x30...0x39).contains($0) || (0x61...0x66).contains($0) }) { record.invocationID = id }
                if let date = row["at"] as? String, let parsed = formatter.date(from:date) { record.started = parsed }
            case "command_end": record.exitCode = activityInteger(row["exit_code"])
            case "log_truncated": record.truncated = true
            case "task_result":
                record.error = row["error"] as? String ?? ""
                record.foreground = row["foreground_verified"] as? Bool
                record.presentationSkipped = row["presentation_skipped"] as? Bool ?? false
                record.modelCalls = activityInteger(row["model_calls"])
            case "access_start":
                record.steps.append(ActivityStep(operation:row["operation"] as? String ?? "", action:row["action"] as? String ?? "",
                                                 target:row["target"] as? String ?? "", elapsed:record.elapsed))
            case "access_end":
                if let i = record.steps.firstIndex(where: { !$0.ended && $0.operation == row["operation"] as? String && $0.action == (row["action"] as? String ?? "") }) {
                    record.steps[i].ended = true
                    record.steps[i].error = row["error"] as? String ?? ""
                    record.steps[i].outcome = row["type"] as? String == "error" || row["outcome"] as? String == "exception" ? "실패" : "응답 확인"
                }
            default: break
            }
        }
        // activate and other waits re-read a window that is still opening; in a
        // run that succeeded those reads are retries, not failures to show in red.
        if record.complete && !record.failed {
            for i in record.steps.indices where record.steps[i].outcome == "실패" && record.steps[i].operation != "act" {
                record.steps[i].outcome = "다시 확인"
            }
        }
        return record
    }
    var tasks: URL { root.appendingPathComponent("Tasks") }
    func task(_ id: String) -> ActivityTask? {
        let directory = tasks.appendingPathComponent(id)
        guard (try? ownedDirectory(tasks)) != nil, (try? ownedDirectory(directory)) != nil,
              let data = try? readPrivate(directory.appendingPathComponent("task.json"), limit:65536),
              let object = try? JSONSerialization.jsonObject(with:data) as? [String:Any],
              activityInteger(object["schema"]) == 1, object["id"] as? String == id else { return nil }
        var task = ActivityTask(id:id)
        task.goal = String((object["goal"] as? String ?? "").prefix(1000))
        task.detail = String((object["detail"] as? String ?? "").prefix(4000))
        task.open = object["state"] as? String != "closed"
        task.result = object["result"] as? String
        (task.notes, task.reasons) = taskEvents(directory.appendingPathComponent("events.jsonl"))
        return task
    }
    private var eventCache: [URL: (Date, Int, [ActivityNote], [String: String])] = [:]
    /// Decision notes and per-call reasons from a task's events.jsonl, re-read only when it changes.
    func taskEvents(_ url: URL) -> ([ActivityNote], [String: String]) {
        guard let a = try? FileManager.default.attributesOfItem(atPath:url.path),
              let size = a[.size] as? Int, let modified = a[.modificationDate] as? Date else { return ([], [:]) }
        if let c = eventCache[url], c.0 == modified, c.1 == size { return (c.2, c.3) }
        guard let data = try? readPrivate(url, limit:8*1024*1024), let text = String(data:data, encoding:.utf8) else { return ([], [:]) }
        let formatter = ISO8601DateFormatter(); formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        var notes: [ActivityNote] = [], reasons: [String: String] = [:]
        for line in text.split(separator:"\n") where line.contains("\"note\"") || line.contains("\"why\"") {
            guard let row = try? JSONSerialization.jsonObject(with:Data(line.utf8)) as? [String:Any] else { continue }
            if row["event"] as? String == "note", let note = row["text"] as? String,
               let at = (row["at"] as? String).flatMap(formatter.date) {
                notes.append(ActivityNote(at:at, text:String(note.prefix(1000))))
            } else if row["event"] as? String == "invocation_start", let id = row["invocation"] as? String, let why = row["why"] as? String {
                reasons[id] = String(why.prefix(500))
            }
        }
        eventCache[url] = (modified, size, notes, reasons)
        return (notes, reasons)
    }
    /// Calls grouped by the task they were made for, newest activity first.
    func groups() throws -> [ActivityGroup] {
        var byTask: [String: Int] = [:]
        var groups: [ActivityGroup] = []
        for record in try records() {
            if let id = record.taskID {
                if let i = byTask[id] { groups[i].records.append(record); continue }
                byTask[id] = groups.count
                groups.append(ActivityGroup(key:id, records:[record], taskID:id, task:task(id)))
            } else {
                groups.append(ActivityGroup(key:record.url.path, records:[record]))
            }
        }
        for i in groups.indices { groups[i].records.sort { $0.started > $1.started } }
        return groups.sorted { $0.latest > $1.latest }
    }
    func deleteRecords() throws {
        for (url, _, _) in try files() { try FileManager.default.removeItem(at:url) }
        cache.removeAll()
    }
}

private let activityCanvas = NSColor(name:nil) { a in
    a.bestMatch(from:[.aqua,.darkAqua]) == .darkAqua ? NSColor(srgbRed:0.10,green:0.11,blue:0.105,alpha:1) : NSColor(srgbRed:0.975,green:0.973,blue:0.96,alpha:1)
}
private let activitySidebar = NSColor(name:nil) { a in
    a.bestMatch(from:[.aqua,.darkAqua]) == .darkAqua ? NSColor(srgbRed:0.13,green:0.14,blue:0.13,alpha:1) : NSColor(srgbRed:0.94,green:0.94,blue:0.925,alpha:1)
}

private final class ActivityBackground: NSView {
    var fill: NSColor = activityCanvas
    override var wantsUpdateLayer: Bool { true }
    override func updateLayer() { effectiveAppearance.performAsCurrentDrawingAppearance { layer?.backgroundColor = fill.cgColor } }
    override func viewDidChangeEffectiveAppearance() { super.viewDidChangeEffectiveAppearance(); needsDisplay = true }
}
private final class ActivityCard: NSStackView {
    override var wantsUpdateLayer: Bool { true }
    override func updateLayer() { effectiveAppearance.performAsCurrentDrawingAppearance { layer?.backgroundColor = NSColor.controlBackgroundColor.cgColor } }
    override func viewDidChangeEffectiveAppearance() { super.viewDidChangeEffectiveAppearance(); needsDisplay = true }
}
private final class ActivityNavigationButton: NSButton {
    override func draw(_ dirtyRect: NSRect) {
        let color: NSColor = state == .on ? .controlAccentColor : .labelColor
        if state == .on || isHighlighted {
            NSColor.controlAccentColor.withAlphaComponent(state == .on ? 0.12 : 0.06).setFill()
            NSBezierPath(roundedRect:bounds,xRadius:8,yRadius:8).fill()
        }
        let symbol = image?.withSymbolConfiguration(NSImage.SymbolConfiguration(paletteColors:[color])) ?? image
        symbol?.draw(in:NSRect(x:12,y:(bounds.height-16)/2,width:16,height:16),from:.zero,operation:.sourceOver,fraction:1,respectFlipped:true,hints:nil)
        let paragraph = NSMutableParagraphStyle(); paragraph.lineBreakMode = .byTruncatingTail
        (title as NSString).draw(in:NSRect(x:36,y:(bounds.height-17)/2,width:bounds.width-48,height:18),withAttributes:[.font:NSFont.systemFont(ofSize:13,weight:.medium),.foregroundColor:color,.paragraphStyle:paragraph])
    }
}

final class ActivityDocumentStack: NSStackView { override var isFlipped: Bool { true } }

private func activityErrorMessage(_ code: String) -> String {
    ["credential_plan_changed":"검토한 뒤 파일 내용이 바뀌었어요. 파일을 다시 선택해 검토하세요.",
     "credential_plan_invalid":"위임 파일 형식을 확인하세요. 에이전트가 만든 Haejo 위임 파일을 선택하세요.",
     "credential_configuration_invalid":"설정을 읽지 못했어요. 파일과 입력 내용을 확인하세요.",
     "credential_name_invalid":"이름에는 영문·숫자·점·밑줄·하이픈을 사용하세요.",
     "credential_file_unavailable":"등록한 세션 파일을 읽지 못했어요. 파일 위치를 확인하세요.",
     "credential_account_mismatch":"현재 로그인된 계정이 위임한 계정과 달라요.",
     "credential_arguments_invalid":"설정에 필요한 항목을 확인하세요.",
     "vault_provider_invalid":"Vault 서버 주소와 실행·세션 파일의 절대 경로를 확인하세요.",
     "new_window_not_unique":"새 문서 창을 하나로 확인하지 못했어요.",
     "helper_unavailable":"앱 조작 연결을 사용할 수 없어요. Mac 권한·에이전트 설정을 확인하세요.",
     "target_not_found":"대상 앱을 찾지 못했어요.", "no_window_content":"아직 열린 창이 없어요.",
     "observation_unavailable":"앱 상태를 읽지 못했어요.", "aborted_by_user":"사용자가 작업을 중단했어요.",
     "new_document_not_empty":"새 문서가 비어 있지 않아 입력을 멈췄어요.",
     "application_identity_changed":"대상 앱이 바뀌어 작업을 멈췄어요.",
     "text_not_verified":"입력 결과를 확인하지 못했어요.",
     "action_failed":"요청한 동작을 완료하지 못했어요.",
     "step_not_authorized":"승인되지 않은 단계가 있어 실행하지 않았어요.",
     "invalid_flow":"작업 내용(flow)을 읽지 못해 실행하지 않았어요.",
     "invalid_parameters":"작업에 필요한 값이 빠져 실행하지 않았어요.",
     "session_invalid_flow":"받은 작업 내용(flow)이 올바르지 않아 실행하지 않았어요.",
     "session_input_timeout":"작업 내용을 기다리다 시간이 지나 끝냈어요.",
     "session_target_mismatch":"작업 대상 앱이 연결한 앱과 달라 실행하지 않았어요.",
     "window_missing_or_ambiguous":"캡처할 창을 하나로 정하지 못했어요.",
     "window_capture_failed":"창을 캡처하지 못했어요.",
     "output_exists":"저장할 파일이 이미 있어 덮어쓰지 않았어요.",
     "unknown_failure":"작업이 실패했어요. 원인 코드는 기록되지 않았어요."][code] ?? ("오류 코드: " + String(code.prefix(120)))
}

private func activityLabel(_ text: String, _ size: CGFloat = 13, _ weight: NSFont.Weight = .regular, secondary: Bool = false) -> NSTextField {
    let field = NSTextField(wrappingLabelWithString:text)
    field.font = .systemFont(ofSize:size, weight:weight)
    field.textColor = secondary ? .secondaryLabelColor : .labelColor
    field.setContentCompressionResistancePriority(.required, for:.vertical)
    field.setContentCompressionResistancePriority(.defaultLow, for:.horizontal)
    return field
}

final class ActivityCenter: NSWindowController, NSWindowDelegate, NSTableViewDataSource, NSTableViewDelegate, NSSearchFieldDelegate, NSSplitViewDelegate {
    let store: ActivityStore
    var onSetup: (() -> Void)?
    private let queue = DispatchQueue(label:"ai.callabo.haejo.activity-reader", qos:.userInitiated)
    private let table = NSTableView()
    private let search = NSSearchField()
    private let filter = NSSegmentedControl(labels:["전체", "실패", "완료 확인 없음"], trackingMode:.selectOne, target:nil, action:nil)
    private let heading = activityLabel("실행 기록", 24, .semibold)
    private let summary = activityLabel("불러오는 중…", 12, secondary:true)
    private let detail = ActivityDocumentStack()
    private let history = NSStackView()
    private let settings = ActivityDocumentStack()
    private let content = NSView()
    private let split = NSSplitView()
    private let status = activityLabel("상태 확인 중", 11, secondary:true)
    private let saveStatus = activityLabel("변경 사항은 다음 작업부터 적용됩니다.", 12, secondary:true)
    private let logToggle = NSButton(checkboxWithTitle:"실행 기록 자동 저장", target:nil, action:nil)
    private let bannerToggle = NSButton(checkboxWithTitle:"작업 중 배너 표시", target:nil, action:nil)
    private let warmToggle = NSButton(checkboxWithTitle:"빠른 실행(helper 유지)", target:nil, action:nil)
    private let helperIdle = NSPopUpButton(frame:.zero,pullsDown:false)
    private let retention = NSPopUpButton(frame:.zero,pullsDown:false)
    private let historyButton = ActivityNavigationButton()
    private let settingsButton = ActivityNavigationButton()
    private let flowsButton = ActivityNavigationButton()
    let flowPage: FlowLibraryPage
    private enum Page { case history, flows, settings }
    private var page = Page.history
    private var credentialCenter: CredentialCenter?
    private var allRecords: [ActivityGroup] = []
    private var filtered: [ActivityGroup] = []
    private var selected: String?
    private var timer: Timer?
    private var loading = false
    private let refreshAutomatically: Bool
    private var isSettings = false
    private var currentSettings = HaejoPreferences()
    private var rendered: ActivityGroup?
    private let dateFormatter: DateFormatter = { let f = DateFormatter(); f.dateStyle = .medium; f.timeStyle = .short; return f }()

    init(store: ActivityStore = ActivityStore(), refreshAutomatically: Bool = true, flowPage: FlowLibraryPage? = nil) {
        self.store = store
        self.flowPage = flowPage ?? FlowLibraryPage()
        self.refreshAutomatically = refreshAutomatically
        let window = NSWindow(contentRect:NSRect(x:0,y:0,width:1060,height:700), styleMask:[.titled,.closable,.miniaturizable,.resizable], backing:.buffered, defer:false)
        super.init(window:window)
        window.title = "Haejo"; window.titlebarAppearsTransparent = true; window.isReleasedWhenClosed = false
        window.contentMinSize = NSSize(width:900,height:600); window.delegate = self
        window.backgroundColor = .windowBackgroundColor
        let background = ActivityBackground(frame:window.contentView!.bounds); background.wantsLayer = true; window.contentView = background
        if let visible = NSScreen.main?.visibleFrame { window.setContentSize(NSSize(width:max(900,min(1060,visible.width-32)),height:max(600,min(700,visible.height-48)))) }
        build(); window.contentView?.layoutSubtreeIfNeeded(); split.setPosition(300,ofDividerAt:0); window.center()
    }
    required init?(coder:NSCoder) { nil }
    private func column(_ views: [NSView], spacing: CGFloat = 12) -> NSStackView {
        let stack = NSStackView(views:views); stack.orientation = .vertical; stack.alignment = .leading; stack.spacing = spacing
        return stack
    }
    private func button(_ title: String, _ icon: String, _ selector: Selector) -> NSButton {
        let b = NSButton(title:title, image:NSImage(systemSymbolName:icon, accessibilityDescription:title) ?? NSImage(), target:self, action:selector)
        b.bezelStyle = .rounded; b.imagePosition = .imageLeading; b.alignment = .left
        return b
    }
    private func build() {
        guard let root = window?.contentView else { return }
        let sidebar = ActivityBackground(); sidebar.fill = activitySidebar; sidebar.wantsLayer = true
        let brand = activityLabel("Haejo", 23, .bold)
        let logo = NSImageView(); logo.image = NSImage(contentsOf:Bundle.main.url(forResource:"haejo-app", withExtension:"icns") ?? URL(fileURLWithPath:"/nonexistent"))
        logo.imageScaling = .scaleProportionallyUpOrDown; logo.widthAnchor.constraint(equalToConstant:32).isActive = true; logo.heightAnchor.constraint(equalToConstant:32).isActive = true
        let brandRow = NSStackView(views:[logo,brand]); brandRow.spacing = 8
        historyButton.title = "실행 기록"; historyButton.image = NSImage(systemSymbolName:"clock.arrow.circlepath", accessibilityDescription:nil)
        settingsButton.title = "설정"; settingsButton.image = NSImage(systemSymbolName:"slider.horizontal.3", accessibilityDescription:nil)
        flowsButton.title = "저장된 Flow"; flowsButton.image = NSImage(systemSymbolName:"square.stack.3d.up", accessibilityDescription:nil)
        flowsButton.setAccessibilityIdentifier("haejo.activity.flows")
        for b in [historyButton,flowsButton,settingsButton] { b.font = .systemFont(ofSize:13,weight:.medium); b.target = self; b.action = #selector(navigate(_:)); b.bezelStyle = .rounded; b.isBordered = false; b.setButtonType(.pushOnPushOff); b.wantsLayer = true; b.layer?.cornerRadius = 8; b.imagePosition = .imageLeading; b.alignment = .left; b.widthAnchor.constraint(equalToConstant:176).isActive = true; b.heightAnchor.constraint(equalToConstant:38).isActive = true }
        historyButton.setAccessibilityIdentifier("haejo.activity.history"); settingsButton.setAccessibilityIdentifier("haejo.activity.settings")
        let setup = button("Mac 권한·에이전트", "arrow.up.forward.app", #selector(openSetup))
        let tagline = activityLabel("에이전트의 작업 공간",11,secondary:true)
        let spacer = NSView(); spacer.setContentHuggingPriority(.init(1),for:.vertical)
        let side = column([brandRow,tagline,historyButton,flowsButton,settingsButton,spacer,status,setup])
        side.spacing = 8; side.setCustomSpacing(24,after:tagline)
        status.preferredMaxLayoutWidth = 176
        status.widthAnchor.constraint(lessThanOrEqualToConstant:176).isActive = true
        sidebar.addSubview(side); side.translatesAutoresizingMaskIntoConstraints = false
        NSLayoutConstraint.activate([side.topAnchor.constraint(equalTo:sidebar.topAnchor,constant:26),side.leadingAnchor.constraint(equalTo:sidebar.leadingAnchor,constant:16),side.trailingAnchor.constraint(equalTo:sidebar.trailingAnchor,constant:-16),side.bottomAnchor.constraint(equalTo:sidebar.bottomAnchor,constant:-20)])
        root.addSubview(sidebar); root.addSubview(content)
        for v in [sidebar,content] { v.translatesAutoresizingMaskIntoConstraints = false }
        NSLayoutConstraint.activate([sidebar.leadingAnchor.constraint(equalTo:root.leadingAnchor),sidebar.topAnchor.constraint(equalTo:root.topAnchor),sidebar.bottomAnchor.constraint(equalTo:root.bottomAnchor),sidebar.widthAnchor.constraint(equalToConstant:208),content.leadingAnchor.constraint(equalTo:sidebar.trailingAnchor),content.trailingAnchor.constraint(equalTo:root.trailingAnchor),content.topAnchor.constraint(equalTo:root.topAnchor),content.bottomAnchor.constraint(equalTo:root.bottomAnchor)])
        buildHistory(); buildSettings()
        flowPage.window = window; pin(flowPage.view,into:content); flowPage.view.isHidden = true
        navigate(historyButton)
    }
    private func pin(_ view: NSView, into container: NSView, inset: CGFloat = 24) {
        container.addSubview(view); view.translatesAutoresizingMaskIntoConstraints = false
        NSLayoutConstraint.activate([view.leadingAnchor.constraint(equalTo:container.leadingAnchor,constant:inset),view.trailingAnchor.constraint(equalTo:container.trailingAnchor,constant:-inset),view.topAnchor.constraint(equalTo:container.topAnchor,constant:inset),view.bottomAnchor.constraint(equalTo:container.bottomAnchor,constant:-inset)])
    }
    private func buildHistory() {
        history.orientation = .vertical; history.alignment = .leading; history.spacing = 16
        let refresh = button("새로고침", "arrow.clockwise", #selector(refresh))
        let top = NSStackView(views:[heading,NSView(),refresh]); top.alignment = .centerY
        search.placeholderString = "앱 또는 작업 검색"; search.delegate = self; search.setAccessibilityIdentifier("haejo.activity.search")
        search.widthAnchor.constraint(greaterThanOrEqualToConstant:160).isActive = true
        search.heightAnchor.constraint(greaterThanOrEqualToConstant:28).isActive = true
        filter.target = self; filter.action = #selector(applyFilter); filter.selectedSegment = 0
        let tools = NSStackView(views:[search,filter]); tools.spacing = 12
        let list = NSScrollView(); list.hasVerticalScroller = true; list.autohidesScrollers = true
        let col = NSTableColumn(identifier:NSUserInterfaceItemIdentifier("session")); table.addTableColumn(col)
        table.headerView = nil; table.rowHeight = 64; table.intercellSpacing = .zero
        table.style = .fullWidth; table.delegate = self; table.dataSource = self; table.columnAutoresizingStyle = .lastColumnOnlyAutoresizingStyle
        table.setAccessibilityIdentifier("haejo.activity.sessions"); list.documentView = table
        let details = NSScrollView(); details.hasVerticalScroller = true; details.autohidesScrollers = true
        detail.orientation = .vertical; detail.alignment = .leading; detail.spacing = 10
        detail.edgeInsets = NSEdgeInsets(top:24,left:24,bottom:24,right:24); detail.translatesAutoresizingMaskIntoConstraints = false
        details.documentView = detail
        detail.widthAnchor.constraint(equalTo:details.contentView.widthAnchor).isActive = true
        split.isVertical = true; split.dividerStyle = .thin; split.delegate = self
        split.wantsLayer = true; split.layer?.cornerRadius = 10; split.layer?.masksToBounds = true
        split.addArrangedSubview(list); split.addArrangedSubview(details)
        split.setHoldingPriority(.defaultHigh,forSubviewAt:0)
        split.setHoldingPriority(.defaultLow,forSubviewAt:1)
        list.widthAnchor.constraint(greaterThanOrEqualToConstant:240).isActive = true
        details.widthAnchor.constraint(greaterThanOrEqualToConstant:300).isActive = true
        for view in [top,summary,tools,split] { history.addArrangedSubview(view) }
        for v in [top,tools,split] { v.widthAnchor.constraint(equalTo:history.widthAnchor).isActive = true }
        split.heightAnchor.constraint(greaterThanOrEqualToConstant:360).isActive = true
        pin(history,into:content)
    }
    private func settingsCard(_ title: String, _ explanation: String, _ control: NSView) -> NSView {
        let stack = ActivityCard(views:[activityLabel(title,16,.semibold),activityLabel(explanation,12,secondary:true),control]); stack.orientation = .vertical; stack.alignment = .leading; stack.spacing = 12
        stack.edgeInsets = NSEdgeInsets(top:20,left:20,bottom:20,right:20)
        for view in stack.arrangedSubviews where view is NSTextField {
            view.widthAnchor.constraint(equalTo:stack.widthAnchor,constant:-40).isActive = true
        }
        stack.wantsLayer = true; stack.layer?.cornerRadius = 12
        return stack
    }
    private func buildSettings() {
        settings.orientation = .vertical; settings.alignment = .leading; settings.spacing = 14
        logToggle.target = self; logToggle.action = #selector(saveSettings)
        bannerToggle.target = self; bannerToggle.action = #selector(saveSettings)
        bannerToggle.setAccessibilityIdentifier("haejo.settings.control-banner")
        logToggle.setAccessibilityIdentifier("haejo.settings.logging")
        retention.addItems(withTitles:["7일", "30일", "90일"]); retention.target = self; retention.action = #selector(saveSettings)
        retention.setAccessibilityIdentifier("haejo.settings.retention")
        warmToggle.target = self; warmToggle.action = #selector(saveSettings)
        warmToggle.setAccessibilityIdentifier("haejo.settings.keep-helper-warm")
        helperIdle.addItems(withTitles:(1...10).map { "\($0)분" })
        helperIdle.target = self; helperIdle.action = #selector(saveSettings)
        helperIdle.setAccessibilityIdentifier("haejo.settings.helper-idle")
        let warmControls = NSStackView(views:[warmToggle,activityLabel("사용하지 않을 때 종료",12,secondary:true),helperIdle])
        warmControls.orientation = .vertical; warmControls.alignment = .leading; warmControls.spacing = 10
        let remove = button("저장된 기록 모두 삭제…", "trash", #selector(confirmDelete))
        let credentials = button("Vault·로그인 위임 관리", "key", #selector(openCredentials))
        let cards = [settingsCard("로그인 위임", "Vault 연결과 앱·사이트별 위임을 관리합니다. 에이전트가 만든 위임 파일을 끌어놓고 허용 수준을 검토하세요.",credentials),
                     settingsCard("빠른 실행", "도우미를 잠시 유지해 다음 작업을 더 빠르게 시작합니다. 기본은 꺼짐입니다. 유휴 시간이 지나면 자동 종료하며, 환경변수로 지정한 실행 방식이 우선합니다.",warmControls),
                     settingsCard("실행 기록", "접근한 앱·동작·결과·시간을 이 Mac에 저장합니다. 화면 내용·입력값·프롬프트는 기록하지 않습니다.",logToggle),
                     settingsCard("기록 보관 기간", "선택한 기간과 최대 200개·20MB 제한 안에서 다음 작업 시작 시 정리합니다.",retention),
                     settingsCard("작업 표시", "끄면 우상단 배너를 숨깁니다. 기존 Haejo 메뉴에서 작업 상태를 확인하거나 중단할 수 있고, Esc로도 중단할 수 있습니다.",bannerToggle)]
        settings.addArrangedSubview(activityLabel("설정",24,.semibold))
        for card in cards { settings.addArrangedSubview(card); card.widthAnchor.constraint(equalTo:settings.widthAnchor).isActive = true }
        for v in [saveStatus,remove,activityLabel("기록은 Haejo를 통한 접근 내역입니다. 에이전트의 내부 추론이나 전체 대화는 포함하지 않습니다.",12,secondary:true)] { settings.addArrangedSubview(v) }
        settings.addArrangedSubview(activityLabel("Haejo · " + (Bundle.main.object(forInfoDictionaryKey:"HaejoReleaseTag") as? String ?? "개발 버전"),11,secondary:true))
        let scroll = NSScrollView(); scroll.hasVerticalScroller = true; scroll.autohidesScrollers = true; scroll.drawsBackground = false; scroll.contentView.drawsBackground = false
        settings.translatesAutoresizingMaskIntoConstraints = false; scroll.documentView = settings
        settings.widthAnchor.constraint(equalTo:scroll.contentView.widthAnchor).isActive = true
        pin(scroll,into:content); scroll.isHidden = true; scroll.identifier = NSUserInterfaceItemIdentifier("settings-page")
    }
    @objc private func navigate(_ sender: NSButton) {
        page = sender === settingsButton ? .settings : sender === flowsButton ? .flows : .history
        isSettings = page == .settings
        history.isHidden = page != .history
        flowPage.view.isHidden = page != .flows
        content.subviews.first(where: { $0.identifier?.rawValue == "settings-page" })?.isHidden = !isSettings
        historyButton.state = page == .history ? .on : .off; settingsButton.state = isSettings ? .on : .off
        flowsButton.state = page == .flows ? .on : .off
        for b in [historyButton,flowsButton,settingsButton] { b.contentTintColor = b.state == .on ? .controlAccentColor : .labelColor; b.needsDisplay = true }
        switch page {
        case .settings: loadSettings()
        case .flows:
            window?.contentView?.layoutSubtreeIfNeeded()
            if flowPage.split.subviews[0].frame.width < 240 { flowPage.split.setPosition(300,ofDividerAt:0) }
            if refreshAutomatically { flowPage.reload() }
        case .history: if refreshAutomatically { refresh() }
        }
    }
    func presentFlows() {
        navigate(flowsButton)
        showWindow(nil); window?.makeKeyAndOrderFront(nil); NSApp.activate(ignoringOtherApps:true)
    }
    func present(settings: Bool = false) {
        navigate(settings ? settingsButton : historyButton)
        showWindow(nil); window?.makeKeyAndOrderFront(nil); NSApp.activate(ignoringOtherApps:true)
        if timer == nil { timer = Timer.scheduledTimer(withTimeInterval:2,repeats:true) { [weak self] _ in if self?.window?.isVisible == true && self?.window?.isMiniaturized == false && NSApp.isActive && self?.page == .history { self?.refresh() } } }
    }
    func presentCurrent() { if page == .flows { presentFlows() } else { present(settings:isSettings) } }
    func updateStatus(_ text: String) { status.stringValue = text }
    @objc private func openSetup() { onSetup?() }
    @objc func refresh() {
        guard !loading else { return }; loading = true
        queue.async { [weak self] in
            guard let self else { return }
            let result = Result { (try self.store.groups(), (try? self.store.preferences()) ?? HaejoPreferences()) }
            DispatchQueue.main.async {
                self.loading = false
                switch result {
                case .success(let value): self.allRecords = value.0; self.currentSettings = value.1; self.applyFilter()
                case .failure: self.summary.stringValue = "실행 기록을 읽지 못했어요. 잠시 후 새로고침해 주세요."
                }
            }
        }
    }
    @objc private func applyFilter() {
        let query = search.stringValue.trimmingCharacters(in:.whitespacesAndNewlines)
        filtered = allRecords.filter { r in
            (filter.selectedSegment != 1 || r.failed) && (filter.selectedSegment != 2 || !r.complete)
            && (query.isEmpty || ([r.title, r.status, r.task?.detail ?? ""] + r.records.flatMap { [$0.title, $0.appName] }).joined(separator:" ").localizedCaseInsensitiveContains(query))
        }
        let failed = allRecords.filter { $0.failed }.count
        let calls = allRecords.reduce(0) { $0 + $1.records.count }
        let tasks = allRecords.filter { $0.isTask }.count
        summary.stringValue = "최근 \(calls)개 실행" + (tasks > 0 ? " · 작업 \(tasks)개" : "") + " · 실패 \(failed)개 · \(filtered.count)개 표시" + (currentSettings.loggingEnabled ? "" : " · 새 기록 저장 꺼짐")
        table.reloadData()
        if let id = selected, let i = filtered.firstIndex(where: { $0.key == id }) { table.selectRowIndexes(IndexSet(integer:i),byExtendingSelection:false); showDetail(filtered[i]) }
        else if let first = filtered.first { selected = first.key; table.selectRowIndexes(IndexSet(integer:0),byExtendingSelection:false); showDetail(first) }
        else { selected = nil; showDetail(nil) }
    }
    func controlTextDidChange(_ obj: Notification) { applyFilter() }
    func numberOfRows(in tableView: NSTableView) -> Int { filtered.count }
    func tableView(_ tableView: NSTableView, viewFor tableColumn: NSTableColumn?, row: Int) -> NSView? {
        guard filtered.indices.contains(row) else { return nil }
        let r = filtered[row]
        let cell = NSTableCellView()
        let title = activityLabel(r.title,13,.semibold)
        let subtitle = activityLabel(r.isTask ? "작업 · 호출 \(r.records.count)회 · \(r.appNames) · \(dateFormatter.string(from:r.latest))" : "\(r.appNames) · \(dateFormatter.string(from:r.latest))",11,secondary:true)
        let mark = activityLabel(r.status,11,.semibold)
        mark.textColor = r.failed ? .systemRed : r.status == "진행 중" ? .controlAccentColor : r.status == "기록만 있음" ? .secondaryLabelColor : r.complete ? .systemGreen : .secondaryLabelColor
        title.maximumNumberOfLines = 1; subtitle.maximumNumberOfLines = 1
        title.lineBreakMode = .byTruncatingTail; subtitle.lineBreakMode = .byTruncatingTail
        for v in [title,subtitle,mark] { cell.addSubview(v); v.translatesAutoresizingMaskIntoConstraints = false }
        cell.textField = title
        NSLayoutConstraint.activate([title.leadingAnchor.constraint(equalTo:cell.leadingAnchor,constant:12),title.topAnchor.constraint(equalTo:cell.topAnchor,constant:13),title.trailingAnchor.constraint(lessThanOrEqualTo:mark.leadingAnchor,constant:-8),mark.trailingAnchor.constraint(equalTo:cell.trailingAnchor,constant:-12),mark.topAnchor.constraint(equalTo:title.topAnchor),subtitle.leadingAnchor.constraint(equalTo:title.leadingAnchor),subtitle.trailingAnchor.constraint(equalTo:cell.trailingAnchor,constant:-12),subtitle.topAnchor.constraint(equalTo:title.bottomAnchor,constant:5)])

        return cell
    }
    func tableViewSelectionDidChange(_ notification: Notification) {
        guard filtered.indices.contains(table.selectedRow) else { return }
        let group = filtered[table.selectedRow]; selected = group.key; showDetail(group)
    }
    private func showDetail(_ g: ActivityGroup?) {
        if let g, rendered == g { return }
        rendered = g
        for v in detail.arrangedSubviews { detail.removeArrangedSubview(v); v.removeFromSuperview() }
        guard let g else {
            detail.addArrangedSubview(activityLabel(allRecords.isEmpty ? (currentSettings.loggingEnabled ? "아직 실행 기록이 없어요" : "실행 기록 저장이 꺼져 있어요") : "조건에 맞는 기록이 없어요",20,.semibold))
            detail.addArrangedSubview(activityLabel(currentSettings.loggingEnabled ? "Haejo로 작업하면 접근 내역과 결과가 여기에 표시됩니다." : "설정에서 켜면 다음 작업부터 기록을 남깁니다.",13,secondary:true)); layoutDetail(); return
        }
        if g.isTask { showTask(g); layoutDetail(); return }
        let r = g.records[0]
        detail.addArrangedSubview(activityLabel(r.title,20,.semibold))
        detail.addArrangedSubview(activityLabel("\(r.appName) · \(r.status)",13,.medium))
        detail.addArrangedSubview(activityLabel(dateFormatter.string(from:r.started),12,secondary:true))
        var metrics = String(format:"%.2f초 · 동작 %d회",r.elapsed/1000,r.steps.filter { $0.operation == "act" }.count)
        if let calls = r.modelCalls { metrics += " · 모델 호출 \(calls)회" }
        detail.addArrangedSubview(activityLabel(metrics,12,secondary:true))
        if r.foreground == true { detail.addArrangedSubview(activityLabel("결과 문서를 앞으로 표시했어요.",12,.medium)) }
        if r.foreground == false { detail.addArrangedSubview(activityLabel(r.presentationSkipped ? "설정에 따라 백그라운드로 완료했어요." : "결과 화면 표시를 확인하지 못했어요.",12,secondary:true)) }
        if !r.error.isEmpty { detail.addArrangedSubview(activityLabel(activityErrorMessage(r.error),12)) }
        if r.truncated || r.damaged { detail.addArrangedSubview(activityLabel(r.truncated ? "용량 제한으로 일부 접근 기록이 생략됐습니다." : "일부 기록이 손상되어 읽을 수 없습니다.",12,secondary:true)) }
        let divider = NSBox(); divider.boxType = .separator; detail.addArrangedSubview(divider)
        if r.steps.isEmpty { detail.addArrangedSubview(activityLabel("세부 접근 내역이 없는 실행입니다.",12,secondary:true)) }
        addSteps(r)
        layoutDetail()
    }
    /// A task: its goal and state, then every call made for it in order, each with its steps.
    private func showTask(_ g: ActivityGroup) {
        detail.addArrangedSubview(activityLabel(g.title,20,.semibold))
        let failures = g.records.filter { $0.failed }.count
        detail.addArrangedSubview(activityLabel("작업 · \(g.status) · 호출 \(g.records.count)회" + (failures > 0 ? " (실패 \(failures))" : ""),13,.medium))
        detail.addArrangedSubview(activityLabel("\(dateFormatter.string(from:g.started)) – \(dateFormatter.string(from:g.latest)) · \(g.appNames)",12,secondary:true))
        if let id = g.taskID { detail.addArrangedSubview(activityLabel(id,11,secondary:true)) }
        if let task = g.task, !task.detail.isEmpty {
            detail.addArrangedSubview(activityLabel("요청 설명",12,.semibold))
            detail.addArrangedSubview(activityLabel(task.detail,13))
        }
        // Newest first and bounded, so a long task stays readable and the 2-second refresh stays cheap.
        let shown = g.records.prefix(ActivityCenter.taskCallLimit)
        if g.records.count > shown.count { detail.addArrangedSubview(activityLabel("최근 \(shown.count)회를 최신순으로 표시합니다 (전체 \(g.records.count)회).",12,secondary:true)) }
        else if g.records.count > 1 { detail.addArrangedSubview(activityLabel("최신순으로 표시합니다.",12,secondary:true)) }
        // Decision notes interleave by time with the calls shown; older notes past the window are omitted with them.
        let oldestShown = shown.last?.started ?? .distantPast
        var notes = (g.task?.notes ?? []).filter { g.records.count <= shown.count || $0.at >= oldestShown }.sorted { $0.at > $1.at }
        func addNotes(after date: Date?) {
            while let note = notes.first, date.map({ note.at >= $0 }) ?? true {
                notes.removeFirst()
                let icon = NSImageView(image:NSImage(systemSymbolName:"text.bubble",accessibilityDescription:"판단") ?? NSImage())
                icon.contentTintColor = .controlAccentColor
                icon.widthAnchor.constraint(equalToConstant:18).isActive = true
                icon.heightAnchor.constraint(equalToConstant:18).isActive = true
                let texts = column([activityLabel("판단 · " + note.text,13,.medium),activityLabel(dateFormatter.string(from:note.at),11,secondary:true)],spacing:4)
                let divider = NSBox(); divider.boxType = .separator; detail.addArrangedSubview(divider)
                let row = NSStackView(views:[icon,texts]); row.alignment = .top; row.spacing = 12
                detail.addArrangedSubview(row)
            }
        }
        for (offset, r) in shown.enumerated() {
            addNotes(after:r.started)
            let index = g.records.count - 1 - offset
            let divider = NSBox(); divider.boxType = .separator; detail.addArrangedSubview(divider)
            let head = activityLabel("\(index+1). \(r.title) · \(r.appName) · \(r.status)",14,.semibold)
            if r.failed { head.textColor = .systemRed }
            detail.addArrangedSubview(head)
            if let id = r.invocationID, let why = g.task?.reasons[id] { detail.addArrangedSubview(activityLabel("이유 · " + why,12,.medium)) }
            var metrics = dateFormatter.string(from:r.started) + String(format:" · %.2f초 · 동작 %d회",r.elapsed/1000,r.steps.filter { $0.operation == "act" }.count)
            if let calls = r.modelCalls { metrics += " · 모델 호출 \(calls)회" }
            detail.addArrangedSubview(activityLabel(metrics,11,secondary:true))
            if !r.error.isEmpty { detail.addArrangedSubview(activityLabel(activityErrorMessage(r.error),12)) }
            if r.truncated || r.damaged { detail.addArrangedSubview(activityLabel(r.truncated ? "용량 제한으로 일부 접근 기록이 생략됐습니다." : "일부 기록이 손상되어 읽을 수 없습니다.",12,secondary:true)) }
            addSteps(r, limit:ActivityCenter.taskStepLimit)
        }
        addNotes(after:nil)
    }
    static let taskCallLimit = 30
    static let taskStepLimit = 6
    private func addSteps(_ r: ActivityRecord, limit: Int = .max) {
        if r.steps.count > limit { detail.addArrangedSubview(activityLabel("단계 \(r.steps.count)개 중 처음 \(limit)개",11,secondary:true)) }
        for step in r.steps.prefix(limit) {
            let icon = NSImageView(image:NSImage(systemSymbolName:step.outcome == "실패" ? "exclamationmark.circle" : step.operation == "observe" ? "eye" : "cursorarrow",accessibilityDescription:nil) ?? NSImage())
            icon.contentTintColor = step.outcome == "실패" ? .systemRed : .secondaryLabelColor
            icon.widthAnchor.constraint(equalToConstant:18).isActive = true
            icon.heightAnchor.constraint(equalToConstant:18).isActive = true
            let texts = column([activityLabel(step.title,13,.medium),activityLabel(String(format:"%.2f초 · %@",step.elapsed/1000,step.outcome),11,secondary:true)],spacing:4)
            if !step.error.isEmpty { texts.addArrangedSubview(activityLabel(activityErrorMessage(step.error),11,secondary:true)) }
            let row = NSStackView(views:[icon,texts]); row.alignment = .top; row.spacing = 12
            detail.addArrangedSubview(row)
        }
    }
    private func layoutDetail() {
        for v in detail.arrangedSubviews { v.widthAnchor.constraint(equalTo:detail.widthAnchor,constant:-48).isActive = true; if let f = v as? NSTextField { f.preferredMaxLayoutWidth = max(200,detail.frame.width-48) } }
        detail.layoutSubtreeIfNeeded(); detail.setFrameSize(NSSize(width:detail.frame.width,height:detail.fittingSize.height))
    }
    private func loadSettings() {
        do { currentSettings = try store.preferences(); saveStatus.stringValue = "변경 사항은 다음 작업부터 적용됩니다." }
        catch { saveStatus.stringValue = "설정을 읽지 못했어요. 기본값을 표시합니다."; currentSettings = HaejoPreferences() }
        logToggle.state = currentSettings.loggingEnabled ? .on : .off
        bannerToggle.state = currentSettings.showControlBanner ? .on : .off
        warmToggle.state = currentSettings.keepHelperWarm ? .on : .off
        helperIdle.selectItem(at:currentSettings.helperIdleMinutes-1)
        helperIdle.isEnabled = currentSettings.keepHelperWarm
        retention.selectItem(at:[7,30,90].firstIndex(of:currentSettings.retentionDays) ?? 1)
    }
    @objc private func openCredentials() {
        if credentialCenter == nil {credentialCenter=CredentialCenter()}
        credentialCenter?.present()
    }
    @objc private func saveSettings() {
        var desired = currentSettings; desired.showControlBanner = bannerToggle.state == .on
        desired.loggingEnabled = logToggle.state == .on
        desired.keepHelperWarm = warmToggle.state == .on
        desired.helperIdleMinutes = max(1,helperIdle.indexOfSelectedItem+1)
        desired.retentionDays = [7,30,90][max(0,retention.indexOfSelectedItem)]
        do { try store.save(desired); currentSettings = desired; helperIdle.isEnabled = desired.keepHelperWarm; saveStatus.stringValue = "저장했어요. 다음 작업부터 적용됩니다." }
        catch { loadSettings(); saveStatus.stringValue = "설정을 저장하지 못했어요. 이전 설정을 유지합니다." }
    }
    @objc private func confirmDelete() {
        guard let window else { return }
        let alert = NSAlert(); alert.messageText = "저장된 실행 기록을 모두 삭제할까요?"
        alert.informativeText = "이 Mac의 접근 기록이 삭제됩니다. 작업과 저장된 워크플로는 유지됩니다."
        alert.addButton(withTitle:"삭제"); alert.addButton(withTitle:"취소")
        alert.buttons.first?.hasDestructiveAction = true
        alert.beginSheetModal(for:window) { [weak self] response in
            guard response == .alertFirstButtonReturn, let self else { return }
            self.queue.async {
                let result = Result { try self.store.deleteRecords() }
                DispatchQueue.main.async {
                    switch result { case .success: self.saveStatus.stringValue = "저장된 기록을 삭제했어요."
                    case .failure: self.saveStatus.stringValue = "일부 기록을 삭제하지 못했어요." }
                    self.refresh()
                }
            }
        }
    }
    func snapshot(to directory: URL, settingsPage: Bool = false, flowsPage: Bool = false, size: NSSize = NSSize(width:1060,height:700)) throws {
        try FileManager.default.createDirectory(at:directory,withIntermediateDirectories:true)
        allRecords = try store.groups(); currentSettings = (try? store.preferences()) ?? HaejoPreferences(); applyFilter()
        navigate(settingsPage ? settingsButton : flowsPage ? flowsButton : historyButton)
        window?.setContentSize(size)
        guard let view = window?.contentView else { return }
        view.layoutSubtreeIfNeeded()
        table.reloadData(); view.layoutSubtreeIfNeeded()
        if !settingsPage && !flowsPage { showDetail(filtered.first) }
        if flowsPage { flowPage.layoutDetail() }
        view.layoutSubtreeIfNeeded()
        func redraw(_ v: NSView) { v.needsDisplay = true; v.displayIfNeeded(); for child in v.subviews { redraw(child) } }
        redraw(view)
        if let bitmap = view.bitmapImageRepForCachingDisplay(in:view.bounds) {
            view.cacheDisplay(in:view.bounds,to:bitmap)
            try bitmap.representation(using:.png,properties:[:])?.write(to:directory.appendingPathComponent("app.png"))
        }
        let report: [String:Any] = ["record_count":allRecords.count,"visible_count":filtered.count,"settings_page":settingsPage,"width":view.bounds.width,"height":view.bounds.height]
        try JSONSerialization.data(withJSONObject:report,options:[.sortedKeys]).write(to:directory.appendingPathComponent("layout.json"))
    }
    func splitView(_ splitView: NSSplitView, shouldAdjustSizeOfSubview view: NSView) -> Bool {
        view === splitView.subviews.last
    }
    func splitView(_ splitView: NSSplitView, constrainMinCoordinate proposedMinimumPosition: CGFloat, ofSubviewAt dividerIndex: Int) -> CGFloat { 240 }
    func splitView(_ splitView: NSSplitView, constrainMaxCoordinate proposedMaximumPosition: CGFloat, ofSubviewAt dividerIndex: Int) -> CGFloat { min(380,splitView.bounds.width-300) }
    func windowDidResize(_ notification: Notification) { let record = rendered; rendered = nil; showDetail(record); if page == .flows { flowPage.layoutDetail() } }
    func windowWillClose(_ notification: Notification) { timer?.invalidate(); timer = nil }
}

// Loaded only when the person opens credential management. No credential
// values enter command arguments, metadata previews or activity receipts.
final class CredentialPlanDrop: NSView {
    var receive: ((URL) -> Void)?
    override init(frame:NSRect) { super.init(frame:frame); registerForDraggedTypes([.fileURL]) }
    required init?(coder:NSCoder) { nil }
    override func draggingEntered(_ sender:NSDraggingInfo) -> NSDragOperation { .copy }
    override func performDragOperation(_ sender:NSDraggingInfo) -> Bool {
        guard let urls=sender.draggingPasteboard.readObjects(forClasses:[NSURL.self],options:[.urlReadingFileURLsOnly:true]) as? [URL],urls.count==1 else {return false}
        receive?(urls[0]);return true
    }
}

final class CredentialCenter: NSWindowController, NSWindowDelegate {
    typealias Runner = ([String],Data?) throws -> [String:Any]
    private let runner:Runner
    private let queue=DispatchQueue(label:"ai.callabo.haejo.credential-settings",qos:.userInitiated)
    private let providerName=NSTextField(string:"")
    private let provider=NSPopUpButton(frame:.zero,pullsDown:false)
    private let providers=NSPopUpButton(frame:.zero,pullsDown:false)
    private var vaults:[String:[String:Any]]=[:]
    private let server=NSTextField(string:"")
    private let executable=NSTextField(string:"")
    private let sessionFile=NSTextField(string:"")
    private let grants=NSPopUpButton(frame:.zero,pullsDown:false)
    private let grantName=NSTextField(string:"")
    private let level=NSPopUpButton(frame:.zero,pullsDown:false)
    private let preview=activityLabel("에이전트가 만든 위임 파일을 선택하거나 아래로 끌어놓으세요.",13,secondary:true)
    private let grantDetails=activityLabel("등록된 위임을 선택하면 앱·사이트·수준을 확인할 수 있습니다.",12,secondary:true)
    private let itemName=NSTextField(string:"")
    private let secret=NSSecureTextField(string:"")
    private let status=activityLabel("비밀값은 표시하지 않으며 이 Mac의 Keychain 또는 연결한 Vault에 보관합니다.",12,secondary:true)
    private var buttons:[NSButton]=[]
    private var scopes:[String:[String:Any]]=[:]
    private var planURL:URL?
    private var reviewDigest:String?
    private var busy=false
    private var savePlan:NSButton!
    private let tabs=NSTabView()
    private var tabButtons:[NSButton]=[]

    init(runner:Runner?=nil) {
        let launcher=Bundle.main.resourceURL?.appendingPathComponent("runtime/launcher/haejo")
        self.runner=runner ?? { args,input in
            guard let launcher,FileManager.default.isExecutableFile(atPath:launcher.path) else {throw NSError(domain:"HaejoCredentials",code:1)}
            let process=Process();process.executableURL=launcher;process.arguments=["auth"]+args
            let output=Pipe();process.standardOutput=output;process.standardError=FileHandle.nullDevice
            let pipe=input == nil ? nil : Pipe();process.standardInput=pipe ?? FileHandle.nullDevice as Any
            try process.run()
            if let input,let pipe {try pipe.fileHandleForWriting.write(contentsOf:input);try pipe.fileHandleForWriting.close()}
            let data=output.fileHandleForReading.readDataToEndOfFile();process.waitUntilExit()
            guard data.count<=1_048_576,let result=try JSONSerialization.jsonObject(with:data) as? [String:Any] else {throw NSError(domain:"HaejoCredentials",code:2)}
            return result
        }
        let window=NSWindow(contentRect:NSRect(x:0,y:0,width:780,height:620),styleMask:[.titled,.closable,.resizable],backing:.buffered,defer:false)
        super.init(window:window);window.title="Vault · 로그인 위임";window.isReleasedWhenClosed=false
        window.delegate=self
        window.contentView=ActivityBackground(frame:window.contentView!.bounds)
        window.backgroundColor = .windowBackgroundColor
        window.contentMinSize=NSSize(width:740,height:600);window.center();build()
    }
    required init?(coder:NSCoder) { nil }
    private func column(_ views:[NSView])->NSStackView {
        let stack=NSStackView(views:views);stack.orientation = .vertical;stack.alignment = .leading;stack.spacing=14
        return stack
    }
    private func row(_ title:String,_ field:NSView)->NSView {
        let label=activityLabel(title,12,.medium);label.widthAnchor.constraint(equalToConstant:130).isActive=true
        let stack=NSStackView(views:[label,field]);stack.spacing=12
        field.widthAnchor.constraint(greaterThanOrEqualToConstant:430).isActive=true
        return stack
    }
    private func action(_ title:String,_ selector:Selector)->NSButton {
        let button=NSButton(title:title,target:self,action:selector);button.bezelStyle = .rounded;buttons.append(button);return button
    }
    private func tab(_ title:String,_ views:[NSView],_ tabs:NSTabView) {
        let stack=column(views);stack.edgeInsets=NSEdgeInsets(top:24,left:20,bottom:20,right:20)
        let item=NSTabViewItem(identifier:title);item.label=title;item.view=stack;tabs.addTabViewItem(item)
        for v in views where v is NSTextField {v.widthAnchor.constraint(lessThanOrEqualTo:stack.widthAnchor,constant:-40).isActive=true}
    }
    private func build() {
        provider.addItems(withTitles:["macOS Keychain","Bitwarden / Vaultwarden"])
        provider.target=self;provider.action=#selector(providerChanged)
        providers.target=self;providers.action=#selector(selectProvider)
        providerName.placeholderString="예: work";server.placeholderString="https://vault.example.com"
        executable.placeholderString="선택 사항 · bw 실행 파일의 절대 경로"
        sessionFile.placeholderString="선택 사항 · 기존 인증 세션 파일의 절대 경로"
        grantName.placeholderString="예: work-login";itemName.placeholderString="예: work-password"
        level.addItems(withTitles:["파일에 지정된 수준", "입력만 허용 (제출 안 함)"])
        tabs.tabViewType = .noTabsNoBorder;tabs.translatesAutoresizingMaskIntoConstraints=false
        for (index,title) in ["Vault 연결","로그인 위임","로컬 인증 정보"].enumerated() {
            let button=NSButton(title:title,target:self,action:#selector(selectTab(_:)))
            button.tag=index;button.bezelStyle = .rounded;button.setButtonType(.pushOnPushOff)
            button.widthAnchor.constraint(equalToConstant:180).isActive=true;button.heightAnchor.constraint(equalToConstant:32).isActive=true
            button.state=index==0 ? .on : .off;tabButtons.append(button)
        }
        let navigation=NSStackView(views:tabButtons);navigation.spacing=8
        tab("Vault 연결",[
            activityLabel("인증 정보를 보관할 곳을 연결하세요",20,.semibold),
            activityLabel("Vault의 잠금·로그인 상태는 유지합니다. 연결 이름은 에이전트가 위임을 만들 때 사용합니다.",12,secondary:true),
            row("등록된 연결",providers),row("연결 이름",providerName),row("보관 방식",provider),row("Vault 서버",server),
            row("실행 파일",NSStackView(views:[executable,action("선택…",#selector(chooseExecutable))])),
            row("세션 파일",NSStackView(views:[sessionFile,action("선택…",#selector(chooseSession))])),action("연결 등록·수정",#selector(registerProvider))],tabs)
        let drop=CredentialPlanDrop(frame:.zero);drop.heightAnchor.constraint(equalToConstant:62).isActive=true
        drop.widthAnchor.constraint(equalToConstant:640).isActive=true;drop.wantsLayer=true;drop.layer?.cornerRadius=10
        drop.layer?.borderWidth=1;drop.layer?.borderColor=NSColor.separatorColor.cgColor
        let dropLabel=activityLabel("위임 JSON 파일을 여기에 끌어놓기",13,secondary:true)
        drop.addSubview(dropLabel);dropLabel.translatesAutoresizingMaskIntoConstraints=false
        NSLayoutConstraint.activate([dropLabel.centerXAnchor.constraint(equalTo:drop.centerXAnchor),dropLabel.centerYAnchor.constraint(equalTo:drop.centerYAnchor)])
        drop.receive={ [weak self] url in self?.review(url) }
        grants.target=self;grants.action=#selector(grantChanged)
        let manage=NSStackView(views:[grants,action("새로고침",#selector(reload)),action("선택한 위임 취소",#selector(revoke))]);manage.spacing=10
        savePlan=action("검토한 위임 저장",#selector(registerGrant));savePlan.isEnabled=false
        preview.preferredMaxLayoutWidth=640;preview.maximumNumberOfLines=4
        grantDetails.preferredMaxLayoutWidth=640;grantDetails.maximumNumberOfLines=3
        tab("로그인 위임",[activityLabel("앱·사이트별 로그인 위임",20,.semibold),manage,grantDetails,
            action("에이전트가 만든 위임 파일 선택…",#selector(choosePlan)),drop,preview,
            row("위임 이름",grantName),row("허용 수준",level),savePlan],tabs)
        tab("로컬 인증 정보",[activityLabel("이 Mac의 Keychain에 저장",20,.semibold),
            activityLabel("에이전트에게 비밀번호를 보내지 않고 직접 저장합니다. 위임에서 이 항목 이름을 참조합니다.",12,secondary:true),
            row("항목 이름",itemName),row("비밀값",secret),action("Keychain에 저장",#selector(storeSecret))],tabs)
        status.maximumNumberOfLines=3;status.preferredMaxLayoutWidth=720
        let content=window!.contentView!;content.addSubview(tabs);content.addSubview(status);content.addSubview(navigation);status.translatesAutoresizingMaskIntoConstraints=false;navigation.translatesAutoresizingMaskIntoConstraints=false
        NSLayoutConstraint.activate([navigation.topAnchor.constraint(equalTo:content.topAnchor,constant:20),navigation.leadingAnchor.constraint(equalTo:content.leadingAnchor,constant:28),
            tabs.topAnchor.constraint(equalTo:navigation.bottomAnchor,constant:12),tabs.leadingAnchor.constraint(equalTo:content.leadingAnchor,constant:20),tabs.trailingAnchor.constraint(equalTo:content.trailingAnchor,constant:-20),
            tabs.bottomAnchor.constraint(equalTo:status.topAnchor,constant:-16),status.leadingAnchor.constraint(equalTo:content.leadingAnchor,constant:28),status.trailingAnchor.constraint(equalTo:content.trailingAnchor,constant:-28),status.bottomAnchor.constraint(equalTo:content.bottomAnchor,constant:-20),status.heightAnchor.constraint(equalToConstant:48)])
        providerChanged()
    }
    @objc private func selectTab(_ sender:NSButton) {
        tabs.selectTabViewItem(at:sender.tag)
        for button in tabButtons {button.state=button===sender ? .on : .off}
    }
    func present() {showWindow(nil);window?.makeKeyAndOrderFront(nil);reload()}
    func windowWillClose(_ notification:Notification) {secret.stringValue=""}
    private func call(_ args:[String],input:Data?=nil,done:@escaping([String:Any])->Void) {
        guard !busy else {return};busy=true;buttons.forEach{$0.isEnabled=false};status.stringValue="처리 중…"
        queue.async { [weak self] in
            guard let self else {return}
            let result=(try? self.runner(args,input)) ?? ["ok":false,"error":"credential_configuration_invalid"]
            DispatchQueue.main.async {
                self.busy=false;self.buttons.forEach{$0.isEnabled=true};self.savePlan.isEnabled=self.reviewDigest != nil
                if let code=result["error"] as? String {self.status.stringValue=activityErrorMessage(code);return}
                self.status.stringValue="완료했습니다.";done(result)
            }
        }
    }
    @objc private func providerChanged() {for field in [server,executable,sessionFile] {field.isEnabled=provider.indexOfSelectedItem==1}}
    @objc private func selectProvider() {
        guard let name=providers.titleOfSelectedItem,let config=vaults[name] else {providerName.stringValue="";return}
        providerName.stringValue=name;provider.selectItem(at:config["kind"] as? String == "bitwarden" ? 1 : 0)
        server.stringValue=config["server"] as? String ?? "";executable.stringValue=config["executable"] as? String ?? "";sessionFile.stringValue=config["session_file"] as? String ?? "";providerChanged()
    }
    private func choosePath(_ field:NSTextField) {
        let picker=NSOpenPanel();picker.canChooseDirectories=false;picker.allowsMultipleSelection=false
        picker.beginSheetModal(for:window!) {response in if response == .OK,let url=picker.url {field.stringValue=url.path}}
    }
    @objc private func chooseExecutable() {choosePath(executable)}
    @objc private func chooseSession() {choosePath(sessionFile)}
    @objc private func registerProvider() {
        var args=["vault",providerName.stringValue]
        if provider.indexOfSelectedItem==0 {args.append("--keychain")}
        else {
            args += ["--bitwarden",server.stringValue]
            if !executable.stringValue.isEmpty {args += ["--executable",executable.stringValue]}
            if !sessionFile.stringValue.isEmpty {args += ["--session-file",sessionFile.stringValue]}
        }
        call(args) { [weak self] _ in self?.status.stringValue="연결을 등록했습니다. 위임 파일에서 이 연결 이름을 사용할 수 있습니다." }
    }
    @objc private func choosePlan() {
        let picker=NSOpenPanel();picker.canChooseDirectories=false;picker.allowsMultipleSelection=false;picker.allowedFileTypes=["json"]
        picker.beginSheetModal(for:window!) { [weak self] response in if response == .OK,let url=picker.url {self?.review(url)} }
    }
    private func review(_ url:URL) {
        guard !busy else {return}
        planURL=nil;reviewDigest=nil;savePlan.isEnabled=false
        preview.stringValue="위임 파일을 검토하는 중입니다…"
        call(["inspect",url.path]) { [weak self] info in
            guard let self else {return};self.planURL=url;self.reviewDigest=info["review_digest"] as? String
            self.preview.stringValue="앱: \(info["target"] as? String ?? "")\n사이트: \(info["origin"] as? String ?? "이 앱의 기본 화면") · 수준: \(info["level"] as? String ?? "") · \(info["stages"] as? Int ?? 1)단계\n계정 확인: \((info["account_check"] as? Bool)==true ? "설정됨" : "미설정")"
            if self.grantName.stringValue.isEmpty {self.grantName.stringValue=url.deletingPathExtension().lastPathComponent}
            self.savePlan.isEnabled=self.reviewDigest != nil
        }
    }
    @objc private func registerGrant() {
        guard let url=planURL,let digest=reviewDigest else {return}
        var args=["grant",grantName.stringValue,url.path,"--yes","--review-digest",digest]
        if level.indexOfSelectedItem==1 {args.append("--fill-only")}
        call(args) { [weak self] _ in self?.reload() }
    }
    @objc private func reload() {
        call(["list","--vaults"]) { [weak self] info in
            guard let self else {return};self.scopes=info["scopes"] as? [String:[String:Any]] ?? [:]
            self.vaults=info["vaults"] as? [String:[String:Any]] ?? [:]
            self.providers.removeAllItems();self.providers.addItems(withTitles:["새 연결"]+self.vaults.keys.sorted())
            self.grants.removeAllItems();self.grants.addItems(withTitles:(info["grants"] as? [String] ?? []).sorted());self.grantChanged()
        }
    }
    @objc private func grantChanged() {
        guard let name=grants.titleOfSelectedItem,let info=scopes[name] else {grantDetails.stringValue="등록된 위임이 없습니다.";return}
        if let code=info["error"] as? String {grantDetails.stringValue=activityErrorMessage(code);return}
        grantDetails.stringValue="\(info["target"] as? String ?? "") · \(info["origin"] as? String ?? "기본 앱 화면")\n\(info["level"] as? String ?? "사용 불가") · 계정 확인 \((info["account_check"] as? Bool)==true ? "설정됨" : "미설정")"
    }
    @objc private func revoke() {guard let name=grants.titleOfSelectedItem else {return};call(["revoke",name]) { [weak self] _ in self?.reload() }}
    @objc private func storeSecret() {
        guard !busy else {return}
        guard !secret.stringValue.isEmpty else {status.stringValue="저장할 비밀값을 입력하세요.";return}
        let data=(secret.stringValue+"\n").data(using:.utf8);secret.stringValue=""
        call(["put",itemName.stringValue],input:data) { [weak self] _ in self?.status.stringValue="Keychain에 저장했습니다. 비밀값은 에이전트에게 전달되지 않았습니다." }
    }
}

// MARK: - Saved flows

/// One saved flow as `haejo flows --json` / `haejo flows show --json` report it.
struct FlowStepSummary: Equatable {
    var index = 0, action = "", label = "", policy = "", reason = ""
    var consequential = false
    var actionTitle: String {
        ["click":"클릭","double_click":"두 번 클릭","set_value":"입력","type_text":"입력","press_key":"키 입력",
         "menu":"메뉴","secondary_action":"보조 동작","scroll":"스크롤","select_option":"항목 선택","read":"읽기",
         "decide":"판단","close_menu":"메뉴 닫기","status_item":"메뉴바 아이콘","reopen_window":"창 다시 열기",
         "prepare_window":"작업 창 선택","drag":"드래그","upload":"파일 첨부","wait":"기다리기"][action] ?? action
    }
}

struct FlowSummary: Equatable {
    var name = "", target = "", source = "user", path = ""
    var editable = false, ok = false, shadowed = false
    var error = "", detail = ""
    var params: [(String, String?)] = []
    var intents: [String] = []
    var stepCount = 0, consequential = 0, decisions = 0
    var steps: [FlowStepSummary] = []
    static func == (a: FlowSummary, b: FlowSummary) -> Bool {
        a.name == b.name && a.path == b.path && a.ok == b.ok && a.target == b.target && a.intents == b.intents
            && a.params.map { $0.0 } == b.params.map { $0.0 } && a.params.map { $0.1 } == b.params.map { $0.1 }
            && a.steps == b.steps && a.editable == b.editable && a.error == b.error
    }
    init(name: String) { self.name = name }
    init?(_ o: [String: Any]) {
        guard let name = o["name"] as? String, !name.isEmpty else { return nil }
        self.name = name
        target = o["target"] as? String ?? ""; source = o["source"] as? String ?? "user"; path = o["path"] as? String ?? ""
        editable = (o["editable"] as? Bool) == true; ok = (o["ok"] as? Bool) == true
        shadowed = (o["shadowed_by_builtin"] as? Bool) == true
        error = o["error"] as? String ?? ""; detail = o["detail"] as? String ?? ""
        if let p = o["params"] as? [String: Any] {
            params = p.keys.sorted().map { key in
                let v = p[key]
                if v == nil || v is NSNull { return (key, nil) }
                if let n = v as? NSNumber, CFGetTypeID(n) == CFBooleanGetTypeID() { return (key, n.boolValue ? "true" : "false") }
                return (key, "\(v!)")
            }
        }
        intents = o["intents"] as? [String] ?? []
        stepCount = activityInteger(o["step_count"]) ?? 0
        consequential = activityInteger(o["consequential_steps"]) ?? 0
        decisions = activityInteger(o["decisions"]) ?? 0
        steps = (o["steps"] as? [[String: Any]] ?? []).map { s in
            FlowStepSummary(index: activityInteger(s["index"]) ?? 0, action: s["action"] as? String ?? "",
                            label: s["label"] as? String ?? "", policy: s["policy"] as? String ?? "",
                            reason: s["policy_reason"] as? String ?? "", consequential: (s["consequential"] as? Bool) == true)
        }
    }
    var appName: String {
        ["com.apple.TextEdit":"TextEdit", "com.apple.finder":"Finder", "com.apple.calculator":"계산기",
         "com.apple.Safari":"Safari", "com.google.Chrome":"Chrome", "com.apple.mail":"Mail", "com.apple.iCal":"캘린더"][target] ?? target
    }
}

private func flowErrorMessage(_ code: String, _ detail: String = "") -> String {
    let known = ["flow_not_found":"저장된 Flow를 찾지 못했어요. 새로고침해 주세요.",
     "flow_read_only":"앱에 포함된 Flow는 바꿀 수 없어요.",
     "flow_exists":"같은 이름의 Flow가 이미 있어요.",
     "invalid_name":"이름에는 글자·숫자·밑줄(_)·하이픈(-)만 쓸 수 있어요(최대 80자).",
     "unknown_parameter":"이 Flow에 없는 입력값이에요.",
     "invalid_parameter_value":"입력값 형식을 확인하세요.",
     "invalid_intents":"요청 문장의 {{이름}}은 이 Flow의 입력값이어야 해요.",
     "invalid_flow":"저장하면 Flow를 읽을 수 없게 되어 바꾸지 않았어요.",
     "legacy_schema":"이전 형식(schema 1)의 Flow예요. 변환한 뒤 사용할 수 있어요.",
     "corrupt_flow":"Flow 파일이 손상되어 읽을 수 없어요.",
     "library_unavailable":"Flow 보관함을 읽지 못했어요.",
     "runtime_unavailable":"Haejo 실행 파일을 찾지 못했어요. 앱을 다시 설치해 주세요."][code]
    return known ?? ("오류 코드: " + String(code.prefix(80)) + (detail.isEmpty ? "" : " · " + String(detail.prefix(160))))
}

/// The Flow page inside the Haejo window: list, inspect, run, edit defaults
/// and request sentences, rename, delete. Steps are shown, not edited — a step
/// change is a re-authoring, and the CLI refuses edits that would not parse.
final class FlowLibraryPage: NSObject, NSTableViewDataSource, NSTableViewDelegate, NSSearchFieldDelegate, NSSplitViewDelegate {
    typealias Runner = ([String]) throws -> (Int32, Data)
    let view = NSStackView()
    let table = NSTableView()
    let search = NSSearchField()
    let summary = activityLabel("불러오는 중…", 12, secondary:true)
    let status = activityLabel("", 12, secondary:true)
    let detail = ActivityDocumentStack()
    let split = NSSplitView()
    weak var window: NSWindow?
    private let runner: Runner
    private let queue = DispatchQueue(label:"ai.callabo.haejo.flow-library", qos:.userInitiated)
    private(set) var flows: [FlowSummary] = []
    private(set) var filtered: [FlowSummary] = []
    private(set) var current: FlowSummary?
    private(set) var storePath = ""
    var paramFields: [String: NSTextField] = [:]
    let intentsView = NSTextView()
    private var actionButtons: [NSButton] = []
    private var pending = 0
    var busy: Bool { pending > 0 }
    private(set) var running = false

    /// `launcher` is the runtime the app resolved (installed bundle or a
    /// checkout preview); without one, the installed bundle's own copy.
    static func launcherRunner(_ launcher: URL? = nil) -> Runner {
        let launcher = launcher ?? Bundle.main.resourceURL?.appendingPathComponent("runtime/launcher/haejo")
        return { args in
            guard let launcher, FileManager.default.isExecutableFile(atPath:launcher.path) else {
                throw NSError(domain:"HaejoFlows", code:1)
            }
            let process = Process(); process.executableURL = launcher; process.arguments = args
            let output = Pipe(); process.standardOutput = output; process.standardError = output
            process.standardInput = FileHandle.nullDevice
            try process.run()
            let data = output.fileHandleForReading.readDataToEndOfFile(); process.waitUntilExit()
            return (process.terminationStatus, data)
        }
    }

    init(runner: Runner? = nil) {
        self.runner = runner ?? FlowLibraryPage.launcherRunner()
        super.init()
        build()
    }

    private func build() {
        view.orientation = .vertical; view.alignment = .leading; view.spacing = 16
        let heading = activityLabel("저장된 Flow", 24, .semibold)
        let refresh = NSButton(title:"새로고침", image:NSImage(systemSymbolName:"arrow.clockwise", accessibilityDescription:nil) ?? NSImage(), target:self, action:#selector(reload))
        refresh.bezelStyle = .rounded; refresh.imagePosition = .imageLeading
        let top = NSStackView(views:[heading,NSView(),refresh]); top.alignment = .centerY
        search.placeholderString = "이름·앱·요청 문장 검색"; search.delegate = self
        search.setAccessibilityIdentifier("haejo.flows.search")
        let list = NSScrollView(); list.hasVerticalScroller = true; list.autohidesScrollers = true
        table.addTableColumn(NSTableColumn(identifier:NSUserInterfaceItemIdentifier("flow")))
        table.headerView = nil; table.rowHeight = 58; table.intercellSpacing = .zero; table.style = .fullWidth
        table.delegate = self; table.dataSource = self; table.columnAutoresizingStyle = .lastColumnOnlyAutoresizingStyle
        table.setAccessibilityIdentifier("haejo.flows.list"); list.documentView = table
        let details = NSScrollView(); details.hasVerticalScroller = true; details.autohidesScrollers = true
        detail.orientation = .vertical; detail.alignment = .leading; detail.spacing = 10
        detail.edgeInsets = NSEdgeInsets(top:24,left:24,bottom:24,right:24); detail.translatesAutoresizingMaskIntoConstraints = false
        details.documentView = detail
        detail.widthAnchor.constraint(equalTo:details.contentView.widthAnchor).isActive = true
        split.isVertical = true; split.dividerStyle = .thin; split.delegate = self
        split.wantsLayer = true; split.layer?.cornerRadius = 10; split.layer?.masksToBounds = true
        split.addArrangedSubview(list); split.addArrangedSubview(details)
        split.setHoldingPriority(.defaultHigh,forSubviewAt:0); split.setHoldingPriority(.defaultLow,forSubviewAt:1)
        list.widthAnchor.constraint(greaterThanOrEqualToConstant:240).isActive = true
        details.widthAnchor.constraint(greaterThanOrEqualToConstant:300).isActive = true
        status.maximumNumberOfLines = 4
        for v in [top,summary,search,split,status] as [NSView] { view.addArrangedSubview(v) }
        for v in [top,search,split,status] as [NSView] { v.widthAnchor.constraint(equalTo:view.widthAnchor).isActive = true }
        split.heightAnchor.constraint(greaterThanOrEqualToConstant:340).isActive = true
        intentsView.isRichText = false; intentsView.font = .systemFont(ofSize:12)
        intentsView.isAutomaticQuoteSubstitutionEnabled = false; intentsView.isAutomaticTextReplacementEnabled = false
        intentsView.setAccessibilityIdentifier("haejo.flows.intents")
        showDetail(nil)
    }

    // MARK: data

    private func call(_ args: [String]) -> (Int32, [String: Any]) {
        do {
            let (code, data) = try runner(["flows"] + args + ["--json"])
            guard data.count <= 8_388_608, let object = try? JSONSerialization.jsonObject(with:data) as? [String: Any] else {
                return (code, ["ok": false, "error": "library_unavailable"])
            }
            return (code, object)
        } catch { return (1, ["ok": false, "error": "runtime_unavailable"]) }
    }

    /// Requests run one at a time, in order, on a serial queue; none is
    /// dropped because another is still running.
    private func perform(_ args: [String], _ done: @escaping ([String: Any]) -> Void) {
        pending += 1; updateButtons()
        queue.async { [weak self] in
            guard let self else { return }
            let (_, result) = self.call(args)
            DispatchQueue.main.async {
                self.pending -= 1; self.updateButtons()
                if (result["ok"] as? Bool) != true {
                    self.status.stringValue = flowErrorMessage(result["error"] as? String ?? "library_unavailable", result["detail"] as? String ?? "")
                    return
                }
                done(result)
            }
        }
    }

    @objc func reload() {
        perform([]) { [weak self] result in self?.apply(list:result) }
    }

    func apply(list result: [String: Any]) {
        storePath = result["store"] as? String ?? ""
        flows = FlowLibraryPage.ordered(result)
        applyFilter()
    }

    /// Readable flows first, by name; damaged files after them.
    static func ordered(_ result: [String: Any]) -> [FlowSummary] {
        (result["flows"] as? [[String: Any]] ?? []).compactMap(FlowSummary.init)
            .sorted { ($0.ok ? 0 : 1, $0.name) < ($1.ok ? 0 : 1, $1.name) }
    }

    func applyFilter() {
        let query = search.stringValue.trimmingCharacters(in:.whitespacesAndNewlines)
        filtered = flows.filter { f in
            query.isEmpty || ([f.name, f.appName, f.target] + f.intents).joined(separator:" ").localizedCaseInsensitiveContains(query)
        }
        summary.stringValue = flows.isEmpty ? "저장된 Flow가 없어요" : "Flow \(flows.count)개 · \(filtered.count)개 표시" + (storePath.isEmpty ? "" : " · " + (storePath as NSString).abbreviatingWithTildeInPath)
        table.reloadData()
        let keep = current?.name
        if let keep, let i = filtered.firstIndex(where: { $0.name == keep }) {
            table.selectRowIndexes(IndexSet(integer:i), byExtendingSelection:false); load(filtered[i].name)
        } else if let first = filtered.first {
            table.selectRowIndexes(IndexSet(integer:0), byExtendingSelection:false); load(first.name)
        } else { current = nil; showDetail(nil) }
    }

    func load(_ name: String) {
        perform(["show", name]) { [weak self] result in
            guard let self, let object = result["flow"] as? [String: Any], let flow = FlowSummary(object) else { return }
            self.apply(detail:flow)
        }
    }

    func apply(detail flow: FlowSummary) {
        if current == flow { return }
        current = flow; showDetail(flow)
    }

    func controlTextDidChange(_ obj: Notification) { if (obj.object as? NSSearchField) === search { applyFilter() } }

    // MARK: table

    func numberOfRows(in tableView: NSTableView) -> Int { filtered.count }
    func tableView(_ tableView: NSTableView, viewFor tableColumn: NSTableColumn?, row: Int) -> NSView? {
        guard filtered.indices.contains(row) else { return nil }
        let f = filtered[row], cell = NSTableCellView()
        let title = activityLabel(f.name, 13, .semibold)
        let subtitle = activityLabel(f.ok ? "\(f.appName) · \(f.stepCount)단계" + (f.source == "user" ? "" : " · 기본 제공") : flowErrorMessage(f.error), 11, secondary:true)
        let mark = activityLabel(!f.ok ? "읽을 수 없음" : f.consequential > 0 ? "확인 \(f.consequential)" : "", 11, .semibold)
        mark.textColor = f.ok ? .systemOrange : .systemRed
        for v in [title,subtitle] { v.maximumNumberOfLines = 1; v.lineBreakMode = .byTruncatingTail }
        for v in [title,subtitle,mark] { cell.addSubview(v); v.translatesAutoresizingMaskIntoConstraints = false }
        cell.textField = title
        NSLayoutConstraint.activate([title.leadingAnchor.constraint(equalTo:cell.leadingAnchor,constant:12),title.topAnchor.constraint(equalTo:cell.topAnchor,constant:11),
            title.trailingAnchor.constraint(lessThanOrEqualTo:mark.leadingAnchor,constant:-8),mark.trailingAnchor.constraint(equalTo:cell.trailingAnchor,constant:-12),
            mark.topAnchor.constraint(equalTo:title.topAnchor),subtitle.leadingAnchor.constraint(equalTo:title.leadingAnchor),
            subtitle.trailingAnchor.constraint(equalTo:cell.trailingAnchor,constant:-12),subtitle.topAnchor.constraint(equalTo:title.bottomAnchor,constant:4)])
        return cell
    }
    func tableViewSelectionDidChange(_ notification: Notification) {
        guard filtered.indices.contains(table.selectedRow) else { return }
        let name = filtered[table.selectedRow].name
        if current?.name != name { status.stringValue = ""; load(name) }
    }

    // MARK: detail

    private func button(_ title: String, _ icon: String, _ selector: Selector, _ id: String) -> NSButton {
        let b = NSButton(title:title, image:NSImage(systemSymbolName:icon, accessibilityDescription:nil) ?? NSImage(), target:self, action:selector)
        b.bezelStyle = .rounded; b.imagePosition = .imageLeading; b.setAccessibilityIdentifier(id)
        return b
    }

    private func section(_ title: String) -> NSTextField { activityLabel(title, 13, .semibold) }

    func showDetail(_ flow: FlowSummary?) {
        for v in detail.arrangedSubviews { detail.removeArrangedSubview(v); v.removeFromSuperview() }
        paramFields = [:]; actionButtons = []
        guard let f = flow else {
            detail.addArrangedSubview(activityLabel(flows.isEmpty ? "아직 저장된 Flow가 없어요" : "Flow를 선택하세요", 20, .semibold))
            detail.addArrangedSubview(activityLabel("에이전트가 만든 Flow를 보관함에 저장하면 여기에서 확인하고 다시 실행할 수 있어요. 터미널에서는 haejo flows save <flow.json> 으로 저장합니다.", 13, secondary:true))
            layoutDetail(); return
        }
        detail.addArrangedSubview(activityLabel(f.name, 20, .semibold))
        guard f.ok else {
            detail.addArrangedSubview(activityLabel(flowErrorMessage(f.error, f.detail), 13))
            detail.addArrangedSubview(activityLabel(f.path, 11, secondary:true))
            let row = NSStackView(views:[button("Finder에서 보기","folder",#selector(reveal),"haejo.flows.reveal")])
            if f.editable { row.addArrangedSubview(button("삭제…","trash",#selector(confirmRemove),"haejo.flows.remove")) }
            actionButtons = row.arrangedSubviews.compactMap { $0 as? NSButton }
            detail.addArrangedSubview(row); layoutDetail(); return
        }
        var facts = "\(f.appName) · \(f.stepCount)단계"
        if f.decisions > 0 { facts += " · 판단 지점 \(f.decisions)곳(모델 호출)" }
        facts += f.source == "user" ? "" : " · 앱에 포함된 Flow(읽기 전용)"
        detail.addArrangedSubview(activityLabel(facts, 13, .medium))
        if f.shadowed {
            detail.addArrangedSubview(activityLabel("같은 이름의 기본 Flow가 있어 실행하면 기본 버전이 쓰여요. 이 파일을 쓰려면 이름을 바꾸세요.", 12, secondary:true))
        }
        let run = button("실행", "play.fill", #selector(runFlow), "haejo.flows.run")
        run.keyEquivalent = "\r"
        let row = NSStackView(views:[run, button("Finder에서 보기","folder",#selector(reveal),"haejo.flows.reveal")]); row.spacing = 8
        if f.editable {
            row.addArrangedSubview(button("이름 변경…","pencil",#selector(promptRename),"haejo.flows.rename"))
            row.addArrangedSubview(button("삭제…","trash",#selector(confirmRemove),"haejo.flows.remove"))
        }
        actionButtons = row.arrangedSubviews.compactMap { $0 as? NSButton }
        detail.addArrangedSubview(row)

        detail.addArrangedSubview(divider())
        detail.addArrangedSubview(section("입력값"))
        if f.params.isEmpty {
            detail.addArrangedSubview(activityLabel("입력값 없이 항상 같은 작업을 합니다.", 12, secondary:true))
        } else {
            detail.addArrangedSubview(activityLabel("실행할 때 이 값을 씁니다. 비워 두면 실행마다 직접 넣어야 해요." + (f.editable ? " 기본값으로 남기려면 저장을 누르세요." : ""), 12, secondary:true))
            for (name, value) in f.params {
                let label = activityLabel(name, 12, .medium); label.widthAnchor.constraint(equalToConstant:120).isActive = true
                let field = NSTextField(string:value ?? ""); field.placeholderString = "실행할 때 입력"
                field.setAccessibilityIdentifier("haejo.flows.param." + name)
                field.widthAnchor.constraint(greaterThanOrEqualToConstant:180).isActive = true
                paramFields[name] = field
                let line = NSStackView(views:[label, field]); line.spacing = 12
                detail.addArrangedSubview(line)
            }
        }
        detail.addArrangedSubview(section("요청 문장"))
        detail.addArrangedSubview(activityLabel("에이전트가 이 Flow를 찾을 때 맞춰 보는 문장이에요. 한 줄에 하나, 입력값은 {{이름}}으로 씁니다.", 12, secondary:true))
        intentsView.string = f.intents.joined(separator:"\n"); intentsView.isEditable = f.editable
        let box = NSScrollView(); box.documentView = intentsView; box.hasVerticalScroller = true; box.borderType = .bezelBorder
        intentsView.minSize = NSSize(width:0,height:64); intentsView.isVerticallyResizable = true
        intentsView.autoresizingMask = [.width]; intentsView.textContainer?.widthTracksTextView = true
        box.heightAnchor.constraint(equalToConstant:72).isActive = true
        detail.addArrangedSubview(box)
        if f.editable {
            let save = button("입력값·문장 저장", "square.and.arrow.down", #selector(saveFields), "haejo.flows.save")
            actionButtons.append(save); detail.addArrangedSubview(NSStackView(views:[save]))
        }

        detail.addArrangedSubview(divider())
        detail.addArrangedSubview(section("단계"))
        for step in f.steps {
            let icon = NSImageView(image:NSImage(systemSymbolName:step.consequential ? "exclamationmark.triangle" : step.action == "decide" ? "sparkles" : "circle", accessibilityDescription:nil) ?? NSImage())
            icon.contentTintColor = step.consequential ? .systemOrange : .tertiaryLabelColor
            icon.widthAnchor.constraint(equalToConstant:16).isActive = true; icon.heightAnchor.constraint(equalToConstant:16).isActive = true
            let title = activityLabel("\(step.index). \(step.actionTitle)" + (step.label.isEmpty ? "" : " · " + step.label), 12, .medium)
            let texts = column([title])
            if step.consequential { texts.addArrangedSubview(activityLabel("실행 전에 확인 · " + step.reason, 11, secondary:true)) }
            let line = NSStackView(views:[icon, texts]); line.alignment = .top; line.spacing = 10
            detail.addArrangedSubview(line)
        }
        detail.addArrangedSubview(activityLabel(f.path, 11, secondary:true))
        updateButtons(); layoutDetail()
    }

    private func column(_ views: [NSView]) -> NSStackView {
        let s = NSStackView(views:views); s.orientation = .vertical; s.alignment = .leading; s.spacing = 3; return s
    }
    private func divider() -> NSView { let d = NSBox(); d.boxType = .separator; return d }

    func layoutDetail() {
        for v in detail.arrangedSubviews {
            v.widthAnchor.constraint(equalTo:detail.widthAnchor,constant:-48).isActive = true
            if let f = v as? NSTextField { f.preferredMaxLayoutWidth = max(200,detail.frame.width-48) }
        }
        detail.layoutSubtreeIfNeeded(); detail.setFrameSize(NSSize(width:detail.frame.width,height:detail.fittingSize.height))
    }

    private func updateButtons() {
        for b in actionButtons { b.isEnabled = b.accessibilityIdentifier() == "haejo.flows.reveal" || (!busy && !running) }
    }

    // MARK: actions

    func parameterArguments() -> [String] {
        paramFields.keys.sorted().compactMap { key in
            let value = paramFields[key]!.stringValue
            return value.isEmpty ? nil : key + "=" + value
        }.flatMap { ["-p", $0] }
    }

    func runArguments(confirmed: Bool) -> [String] {
        guard let f = current else { return [] }
        return ["replay", f.name] + parameterArguments() + ["--helper"] + (confirmed ? ["--yes"] : [])
    }

    @objc func runFlow() {
        guard let f = current, f.ok, !running else { return }
        let missing = f.params.filter { (paramFields[$0.0]?.stringValue ?? "").isEmpty }.map { $0.0 }
        if !missing.isEmpty { status.stringValue = "입력값을 넣어 주세요: " + missing.joined(separator:", "); return }
        let lasting = f.steps.filter { $0.consequential }
        guard !lasting.isEmpty, let window else { start(runArguments(confirmed:false)); return }
        let alert = NSAlert(); alert.messageText = "\(f.name)을(를) 실행할까요?"
        alert.informativeText = "이 Flow에는 결과가 남는 단계가 있어요:\n" + lasting.prefix(5).map { "· \($0.index). \($0.actionTitle) \($0.label) — \($0.reason)" }.joined(separator:"\n")
        alert.addButton(withTitle:"실행"); alert.addButton(withTitle:"취소")
        alert.beginSheetModal(for:window) { [weak self] response in
            guard response == .alertFirstButtonReturn, let self else { return }
            self.start(self.runArguments(confirmed:true))
        }
    }

    private func start(_ args: [String]) {
        guard let name = current?.name else { return }
        running = true; updateButtons(); status.stringValue = "\(name) 실행 중… 메뉴바의 Haejo에서 중단할 수 있어요."
        queue.async { [weak self] in
            guard let self else { return }
            let outcome = Result { try self.runner(args) }
            DispatchQueue.main.async {
                self.running = false; self.updateButtons()
                switch outcome {
                case .failure: self.status.stringValue = flowErrorMessage("runtime_unavailable")
                case .success(let (code, data)):
                    let text = String(decoding:data.prefix(65536), as:UTF8.self)
                    let tail = text.split(separator:"\n").map { $0.trimmingCharacters(in:.whitespaces) }.filter { !$0.isEmpty }.suffix(3).joined(separator:"\n")
                    self.status.stringValue = (code == 0 ? "\(name) 완료" : "\(name) 실패 (종료 코드 \(code))") + (tail.isEmpty ? "" : "\n" + String(tail.prefix(600)))
                }
            }
        }
    }

    func saveArguments() -> [String] {
        guard let f = current else { return [] }
        var args = ["set", f.name]
        for (name, _) in f.params { args += ["-p", name + "=" + (paramFields[name]?.stringValue ?? "")] }
        let lines = intentsView.string.split(separator:"\n").map { $0.trimmingCharacters(in:.whitespaces) }.filter { !$0.isEmpty }
        if lines != f.intents { args.append("--clear-intents"); for line in lines { args += ["--intent", line] } }
        return args
    }

    @objc func saveFields() {
        guard let f = current, f.editable else { return }
        perform(saveArguments()) { [weak self] result in
            guard let self, let object = result["flow"] as? [String: Any], let flow = FlowSummary(object) else { return }
            self.status.stringValue = "\(flow.name)의 입력값과 문장을 저장했어요."
            self.current = nil; self.apply(detail:flow); self.reloadListOnly()
        }
    }

    private func reloadListOnly() {
        perform([]) { [weak self] result in
            guard let self else { return }
            self.storePath = result["store"] as? String ?? ""
            self.flows = FlowLibraryPage.ordered(result)
            self.applyFilter()
        }
    }

    @objc func promptRename() {
        guard let f = current, f.editable, let window else { return }
        let alert = NSAlert(); alert.messageText = "Flow 이름 변경"
        alert.informativeText = "글자·숫자·밑줄(_)·하이픈(-)을 쓸 수 있어요. 에이전트는 새 이름으로 다시 실행합니다."
        let field = NSTextField(string:f.name); field.frame = NSRect(x:0,y:0,width:280,height:24)
        alert.accessoryView = field; alert.addButton(withTitle:"변경"); alert.addButton(withTitle:"취소")
        alert.window.initialFirstResponder = field
        alert.beginSheetModal(for:window) { [weak self] response in
            guard response == .alertFirstButtonReturn, let self else { return }
            self.rename(f.name, to:field.stringValue.trimmingCharacters(in:.whitespaces))
        }
    }

    func rename(_ old: String, to new: String) {
        guard !new.isEmpty, new != old else { return }
        perform(["rename", old, new]) { [weak self] result in
            guard let self, let object = result["flow"] as? [String: Any], let flow = FlowSummary(object) else { return }
            self.status.stringValue = "이름을 \(flow.name)(으)로 바꿨어요."
            self.current = flow; self.showDetail(flow); self.reloadListOnly()
        }
    }

    @objc func confirmRemove() {
        guard let f = current, f.editable, let window else { return }
        let alert = NSAlert(); alert.messageText = "\(f.name)을(를) 삭제할까요?"
        alert.informativeText = "보관함에서 Flow 파일을 지웁니다. 실행 기록은 남아요."
        alert.addButton(withTitle:"삭제"); alert.addButton(withTitle:"취소"); alert.buttons.first?.hasDestructiveAction = true
        alert.beginSheetModal(for:window) { [weak self] response in
            guard response == .alertFirstButtonReturn, let self else { return }
            self.remove(f.name)
        }
    }

    func remove(_ name: String) {
        perform(["rm", name]) { [weak self] _ in
            guard let self else { return }
            self.status.stringValue = "\(name)을(를) 삭제했어요."
            self.current = nil; self.reloadListOnly()
        }
    }

    @objc func reveal() {
        guard let f = current, !f.path.isEmpty else { return }
        NSWorkspace.shared.activateFileViewerSelecting([URL(fileURLWithPath:f.path)])
    }

    func splitView(_ splitView: NSSplitView, shouldAdjustSizeOfSubview view: NSView) -> Bool { view === splitView.subviews.last }
    func splitView(_ splitView: NSSplitView, constrainMinCoordinate proposedMinimumPosition: CGFloat, ofSubviewAt dividerIndex: Int) -> CGFloat { 240 }
    func splitView(_ splitView: NSSplitView, constrainMaxCoordinate proposedMaximumPosition: CGFloat, ofSubviewAt dividerIndex: Int) -> CGFloat { min(380,splitView.bounds.width-300) }
}
