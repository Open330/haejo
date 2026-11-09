import Foundation
import CoreGraphics
import CDTXBridge

// Development qualification only. No arbitrary labels, coordinates or actions.
final class OwnedCounter {
    let services: FixtureServices
    let rsd: RemoteServiceDiscovery
    let session: AXSession
    let walker: AXWalker
    let expectedPID: Int
    let heading: String
    private var measured: (item: AXWalker.Item, rect: CGRect, frame: CGImage)?
    private var attempted = false
    private(set) var lastPID: Int?

    init(udid: String, connection: IUDTXConnection, services: FixtureServices, pid: Int, heading: String) throws {
        guard pid > 0, heading.hasPrefix("Haejo test "), heading.count == 19,
              heading.suffix(8).allSatisfy({ $0.isASCII && ($0.isLetter || $0.isNumber || $0 == "-" || $0 == "_") }) else {
            throw ProbeError.invalidRequest
        }
        self.services = services; self.expectedPID = pid; self.heading = heading
        rsd = RemoteServiceDiscovery(udid: udid, client: services.client)
        session = AXSession(connection: connection)
        walker = try AXWalker(session: session)
    }
    deinit { walker.finish(); session.finish() }

    func portrait() throws -> (width: Double, height: Double) {
        stage = "owned_counter_orientation"
        let info = try rsd.connect(to: "com.apple.coredevice.deviceinfo")
        defer { info.close() }
        let raw = try CoreDeviceService(connection: info).invoke("com.apple.coredevice.feature.getdisplayinfo")
        guard let value = XPCObject.dictionary(raw).jsonReady as? [String: Any],
              let orientation = value["orientation"] as? [String: Any],
              orientation["currentDeviceOrientation"] as? String == "portrait",
              let displays = value["displays"] as? [[String: Any]], let first = displays.first,
              first["nativeOrientation"] as? String == "rot0",
              let bounds = first["bounds"] as? [[Double]], bounds.count == 2, bounds[1].count == 2,
              bounds[1][0] > 0, bounds[1][1] > bounds[1][0] else { throw ProbeError.invalidReply }
        return (bounds[1][0], bounds[1][1])
    }
    func stem(_ item: AXWalker.Item) -> String { item.caption.components(separatedBy: ", ").first ?? "" }

    func find(counter: Int, button: Bool) throws -> AXWalker.Item {
        // Every move has one wait; no re-submission after a missing/late event.
        stage = "owned_counter_focus_first"
        guard var item = try walker.move(.first) else { throw ProbeError.invalidReply }
        var headingSeen = false, countSeen = false
        var seen = Set<Data>()
        for _ in 0..<40 {
            lastPID = item.pid
            if item.pid != expectedPID { stage = "owned_counter_pid"; throw ProbeError.invalidReply }
            guard !seen.contains(item.token) else { throw ProbeError.invalidReply }
            seen.insert(item.token)
            let label = stem(item)
            headingSeen = headingSeen || label == heading
            countSeen = countSeen || label == "Counter \(counter)"
            stage = !headingSeen ? "owned_counter_find_heading" : !countSeen ? "owned_counter_find_counter" : "owned_counter_find_button"
            if headingSeen && countSeen && (!button || label == "Increment test counter") { return item }
            guard let next = try walker.move(.next) else { throw ProbeError.invalidReply }
            item = next
        }
        throw ProbeError.invalidReply
    }

    func prepare() throws -> [String: Any] {
        stage = "owned_counter_preflight"
        let dimensions = try portrait()
        let item = try find(counter: 0, button: true)
        stage = "owned_counter_measure"
        guard let measurement = try walker.measure(item.token, rsd: rsd),
              !ScreenCapture.isDark(measurement.frame),
              Double(measurement.frame.width) == dimensions.width,
              Double(measurement.frame.height) == dimensions.height,
              measurement.rect.width > 30, measurement.rect.height > 30,
              measurement.rect.minY > dimensions.height * 0.1,
              measurement.rect.maxY < dimensions.height * 0.85 else { throw ProbeError.invalidReply }
        measured = (item, measurement.rect, measurement.frame)
        walker.finish()
        return ["counter": 0, "fixture_heading_seen": true, "target_pid_verified": true,
                "current_orientation": "portrait", "button_measured": true]
    }

    func tap() throws -> [String: Any] {
        stage = "owned_counter_tap_preflight"
        guard !attempted, let measured else { throw ProbeError.invalidRequest }
        // Host prepares and submits once on this process; a second call is impossible.
        attempted = true
        let dimensions = try portrait()
        let rootReply = try session.invoke("deviceFetchSpecialElement:", [0])
        guard let root = AXWire.unwrap(rootReply) as? [String: Any],
              let token = root["PlatformElementValue_v1"] as? Data,
              AXWalker.Item.pid(of: token) == expectedPID else { throw ProbeError.invalidReply }
        let fresh = try ScreenCapture.image(rsd: rsd)
        guard !ScreenCapture.isDark(fresh),
              Double(fresh.width) == dimensions.width, Double(fresh.height) == dimensions.height,
              ScreenCapture.sameArea(measured.frame, fresh, in: measured.rect.insetBy(dx: -32, dy: -32)) else {
            throw ProbeError.invalidReply
        }
        stage = "owned_counter_dispatch"
        try services.tapOnce(x: Int((measured.rect.midX / dimensions.width * 65535).rounded()),
                             y: Int((measured.rect.midY / dimensions.height * 65535).rounded()))
        return ["sent": true, "transport_ping": true, "gesture_count": 1,
                "contact_reports": services.contactReports, "release_reports": services.releaseReports,
                "screen_change_verified": false]
    }
    func readback() throws -> [String: Any] {
        stage = "owned_counter_readback"
        guard attempted, services.touchAttempted else { throw ProbeError.invalidRequest }
        _ = try find(counter: 1, button: false)
        walker.finish()
        return ["counter": 1, "ax_transition_verified": true, "gesture_count": 1]
    }
}
