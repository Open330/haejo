import Foundation

extension XPCObject {
    var largestData: Data? {
        switch self {
        case .data(let value): return value.count <= 32 * 1024 * 1024 ? value : nil
        case .dictionary(let values): return values.values.compactMap { $0.largestData }.max { $0.count < $1.count }
        case .array(let values): return values.compactMap { $0.largestData }.max { $0.count < $1.count }
        default: return nil
        }
    }
    // Never include payloads in screenshot error details.
    var jsonSummary: String { "payload omitted" }
}

// Explicit host-owned CoreDevice lease. This does not handshake a second RSD peer.
final class RemoteServiceDiscovery {
    let client: CoreDeviceClient
    let udid: String
    init(udid: String?) throws {
        guard let udid, (24...80).contains(udid.count),
              udid.allSatisfy({ $0.isHexDigit || $0 == "-" }) else { throw ProbeError.invalidRequest }
        self.udid = udid
        client = try CoreDeviceClient(udid: udid)
    }
    init(udid: String, client: CoreDeviceClient) { self.udid = udid; self.client = client }
    func close() { client.close() }
    func connect(to name: String) throws -> RemoteXPCConnection {
        try RemoteXPCConnection(socket: openSocket(to: name))
    }
    func openSocket(to name: String) throws -> TCPSocket {
        TCPSocket(adopting: try client.serviceSocket(name))
    }
}

// Service availability is not touch authorization. Keep HID open for the session.
final class FixtureServices {
    let client: CoreDeviceClient
    let hid: RemoteXPCConnection
    let display: [String: Any]
    private let gesture: OneGesture
    var touchAttempted: Bool { gesture.attempted }
    var contactReports: Int { gesture.contactReports }
    var releaseReports: Int { gesture.releaseReports }
    init(udid: String) throws {
        try verifyAppleFramework("/Library/Developer/PrivateFrameworks/CoreDevice.framework")
        client = try CoreDeviceClient(udid: udid)
        stage = "fixture_display"
        let info = try RemoteXPCConnection(socket: TCPSocket(adopting:
            try client.serviceSocket("com.apple.coredevice.deviceinfo")))
        defer { info.close() }
        let value = try CoreDeviceService(connection: info).invoke("com.apple.coredevice.feature.getdisplayinfo")
        guard let display = XPCObject.dictionary(value).jsonReady as? [String: Any] else { throw ProbeError.invalidReply }
        self.display = display
        stage = "fixture_hid"
        let socket = TCPSocket(adopting: try client.serviceSocket("com.apple.coredevice.hid.universalhidservice"))
        hid = try RemoteXPCConnection(socket: socket)
        let retainedHID = hid
        gesture = OneGesture(send: { report in
            try retainedHID.sendRequest(["featureIdentifier": .string("com.apple.coredevice.feature.remote.universalhidservice"),
                "messageType": .string("Request"), "payload": .dictionary([
                    "send": .dictionary(["_0": .data(report), "_1": .uint64(257)])])])
        }, ping: { try retainedHID.ping() })
    }
    deinit { hid.close(); client.close() }
    func readiness() throws -> [String: Any] {
        stage = "fixture_ping"
        try hid.ping()
        return ["hid_transport_ping": true, "display_info": display]
    }
    // One gesture only. A partial write can never authorize another contact.
    func tapOnce(x: Int, y: Int) throws {
        try gesture.tapOnce(x: x, y: y)
    }
}
