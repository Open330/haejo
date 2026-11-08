import Foundation
import CDTXBridge

enum ScanError: Error { case noFocusEvents }
enum ScreenshotError: Error { case noImage(String), decodeFailed }

// Minimal focus adapter for the owned fixture. A focus walk changes UI state.
// It shares Probe's existing DTX connection and never reconnects on timeout.
final class AXSession {
    let connection: IUDTXConnection
    private let lock = NSLock()
    private var events = [[String: Any]]()
    init(connection: IUDTXConnection) { self.connection = connection }
    @discardableResult
    func invoke(_ selector: String, _ arguments: [Any] = [], expectsReply: Bool = true) throws -> Any? {
        try connection.invokeSelector(selector, arguments: arguments, expectsReply: expectsReply, timeout: 3)
    }
    func beginFocusWalk() throws {
        connection.eventHandler = { [weak self] selector, arguments in
            guard selector == "hostInspectorCurrentElementChanged:", let self else { return }
            var value = AXWire.unwrap(arguments.first)
            if let list = value as? [Any] { value = list.first }
            guard let focus = value as? [String: Any] else { return }
            self.lock.lock(); defer { self.lock.unlock() }
            // Overflow makes the session unusable, not a reason to submit more moves.
            if self.events.count < 64 { self.events.append(focus) }
        }
        for selector in ["deviceSetAuditTargetPid:", "deviceSetAuditUIPid:"] {
            try invoke(selector, [0], expectsReply: false)
        }
        try invoke("deviceInspectorShowVisuals:", [false], expectsReply: false)
        try invoke("deviceSetAppMonitoringEnabled:", [true], expectsReply: false)
        try invoke("deviceInspectorSetMonitoredEventType:", [0], expectsReply: false)
    }
    func moveFocus(_ direction: AXWire.Direction) throws {
        try invoke("deviceInspectorMoveWithOptions:", [AXWire.moveOptions(direction)], expectsReply: false)
    }
    func nextFocus(timeout: TimeInterval) -> [String: Any]? {
        let deadline = Date().addingTimeInterval(timeout)
        repeat {
            lock.lock()
            let value = events.isEmpty ? nil : events.removeFirst()
            lock.unlock()
            if let value { return value }
            RunLoop.current.run(mode: .default, before: Date().addingTimeInterval(0.02))
        } while Date() < deadline
        return nil
    }
    static func token(of focus: [String: Any]) -> Data? {
        (focus["ElementValue_v1"] as? [String: Any])?["PlatformElementValue_v1"] as? Data
    }
    func finish() {
        _ = try? invoke("deviceInspectorShowVisuals:", [false], expectsReply: false)
        for selector in ["deviceSetAuditTargetPid:", "deviceSetAuditUIPid:"] {
            _ = try? invoke(selector, [0], expectsReply: false)
        }
        connection.eventHandler = nil
    }
}
