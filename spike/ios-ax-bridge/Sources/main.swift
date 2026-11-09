// Development-only no-WDA AX probe. No input or arbitrary selector endpoint.
import Foundation
import CDTXBridge
import CMobileDevice
import Security
import Darwin

enum ProbeError: Error { case invalidRequest, socketIO, invalidReply, frameTooLarge }
// Accessed only by the synchronous stdin loop and its synchronous Probe calls.
nonisolated(unsafe) var stage = "request"

final class ServiceSocket {
    private var descriptor: Int32
    init(_ descriptor: Int32) {
        self.descriptor = descriptor
        let flags = fcntl(descriptor, F_GETFL)
        if flags >= 0 { _ = fcntl(descriptor, F_SETFL, flags & ~O_NONBLOCK) }
        var noSignal: Int32 = 1
        setsockopt(descriptor, SOL_SOCKET, SO_NOSIGPIPE, &noSignal, socklen_t(MemoryLayout<Int32>.size))
        var timeout = timeval(tv_sec: 5, tv_usec: 0)
        setsockopt(descriptor, SOL_SOCKET, SO_RCVTIMEO, &timeout, socklen_t(MemoryLayout<timeval>.size))
        setsockopt(descriptor, SOL_SOCKET, SO_SNDTIMEO, &timeout, socklen_t(MemoryLayout<timeval>.size))
    }
    deinit { if descriptor >= 0 { Darwin.close(descriptor) } }
    func write(_ data: Data) throws {
        try data.withUnsafeBytes { bytes in
            var offset = 0
            while offset < bytes.count {
                let count = Darwin.send(descriptor, bytes.baseAddress!.advanced(by: offset), bytes.count - offset, 0)
                if count < 0 && errno == EINTR { continue }
                guard count > 0 else { throw ProbeError.socketIO }
                offset += count
            }
        }
    }
    func read(_ size: Int) throws -> Data {
        guard size > 0 && size <= 4 * 1024 * 1024 else { throw ProbeError.frameTooLarge }
        var data = Data(count: size)
        try data.withUnsafeMutableBytes { bytes in
            var offset = 0
            while offset < size {
                let count = recv(descriptor, bytes.baseAddress!.advanced(by: offset), size - offset, 0)
                if count < 0 && errno == EINTR { continue }
                guard count > 0 else { throw ProbeError.socketIO }
                offset += count
            }
        }
        return data
    }
    func checkIn() throws {
        let body = try PropertyListSerialization.data(fromPropertyList:
            ["Label": "haejo-ios-ax-spike", "ProtocolVersion": "2", "Request": "RSDCheckin"],
            format: .xml, options: 0)
        var length = UInt32(body.count).bigEndian
        try write(Data(bytes: &length, count: 4) + body)
        for expected in ["RSDCheckin", "StartService"] {
            let header = [UInt8](try read(4))
            let size = header.reduce(0) { ($0 << 8) | Int($1) }
            let reply = try PropertyListSerialization.propertyList(from: read(size), format: nil)
            guard let dictionary = reply as? [String: Any], dictionary["Error"] == nil,
                  dictionary["Request"] as? String == expected else { throw ProbeError.invalidReply }
        }
    }
    func detach() -> Int32 {
        var timeout = timeval(tv_sec: 0, tv_usec: 0)
        setsockopt(descriptor, SOL_SOCKET, SO_RCVTIMEO, &timeout, socklen_t(MemoryLayout<timeval>.size))
        let value = descriptor; descriptor = -1; return value
    }
}

final class USBServiceOwner {
    let service: AMDServiceConnectionRef
    init(udid: String) throws {
        let device = try DeviceDiscovery.device(matching: udid)
        service = try device.startService("com.apple.accessibility.axAuditDaemon.remoteserver")
    }
    deinit { _ = cmd_service_connection_invalidate(service) }
}

func verifyAppleFramework(_ path: String) throws {
    var code: SecStaticCode?
    var requirement: SecRequirement?
    guard SecStaticCodeCreateWithPath(URL(fileURLWithPath: path) as CFURL, [], &code) == errSecSuccess,
          SecRequirementCreateWithString("anchor apple" as CFString, [], &requirement) == errSecSuccess,
          let code, let requirement,
          SecStaticCodeCheckValidity(code, SecCSFlags(rawValue: kSecCSStrictValidate), requirement) == errSecSuccess else {
        throw ProbeError.invalidReply
    }
}

final class Probe {
    // Keep both the CoreDevice assertion and DTX connection through the session.
    let client: CoreDeviceClient?
    let usbOwner: USBServiceOwner?
    let connection: IUDTXConnection
    let epoch = UUID().uuidString
    let xcode: [String: String]
    let udid: String
    var services: FixtureServices?
    init(udid: String, transport: String) throws {
        self.udid = udid
        stage = "xcode_framework"
        let process = Process()
        process.executableURL = URL(fileURLWithPath: "/usr/bin/xcode-select")
        process.arguments = ["-p"]
        process.environment = ["PATH": "/usr/bin:/bin"]
        let output = Pipe(); process.standardOutput = output
        try process.run(); process.waitUntilExit()
        let developer = String(decoding: output.fileHandleForReading.readDataToEndOfFile(), as: UTF8.self)
            .trimmingCharacters(in: .whitespacesAndNewlines)
        guard process.terminationStatus == 0, developer.hasSuffix("/Developer") else { throw ProbeError.invalidReply }
        let contents = (developer as NSString).deletingLastPathComponent
        let plist = NSDictionary(contentsOfFile: contents + "/Info.plist")
        let version = NSDictionary(contentsOfFile: contents + "/version.plist")
        xcode = ["developer_path": developer, "build": version?["ProductBuildVersion"] as? String ?? "unknown",
                 "version": plist?["CFBundleShortVersionString"] as? String ?? "unknown"]
        let framework = contents + "/SharedFrameworks/DTXConnectionServices.framework"
        try verifyAppleFramework(framework)
        try IUDTXConnection.loadFramework(atPath: framework)
        let socket: ServiceSocket
        if transport == "mobiledevice-lockdown" {
            stage = "usb_lockdown_service"
            client = nil
            let owner = try USBServiceOwner(udid: udid)
            usbOwner = owner
            let descriptor = cmd_service_connection_duplicate_socket(owner.service)
            guard descriptor >= 0 else { throw ProbeError.socketIO }
            socket = ServiceSocket(descriptor)
        } else {
            usbOwner = nil
            stage = "coredevice_usage_assertion"
            try verifyAppleFramework("/Library/Developer/PrivateFrameworks/CoreDevice.framework")
            let coreClient = try CoreDeviceClient(udid: udid)
            client = coreClient
            stage = "ax_service_socket"
            socket = ServiceSocket(try coreClient.serviceSocket("com.apple.accessibility.axAuditDaemon.remoteserver.shim.remote"))
            stage = "lockdown_shim_checkin"
            try socket.checkIn()
        }
        stage = "dtx_connection"
        connection = try IUDTXConnection(socket: socket.detach())
    }
    deinit { connection.cancel(); client?.close() }
    func capabilities() throws -> [String] {
        stage = "ax_capabilities"
        let value = try connection.invokeSelector("deviceCapabilities", arguments: [], expectsReply: true, timeout: 5)
        guard let list = AXWire.unwrap(value) as? [String] else { throw ProbeError.invalidReply }
        return list.sorted()
    }
    func readRoot() throws -> [String: Any] {
        stage = "ax_root"
        let reply = try connection.invokeSelector("deviceFetchSpecialElement:", arguments: [0], expectsReply: true, timeout: 5)
        guard let root = AXWire.unwrap(reply) as? [String: Any],
              let token = root["PlatformElementValue_v1"] as? Data, !token.isEmpty else {
            throw ProbeError.invalidReply
        }
        var attributes = [String: Any]()
        for name in ["Label", "Value", "Role", "Identifier"] {
            let value = try connection.invokeSelector("deviceElement:valueForAttribute:",
                arguments: [AXWire.element(token), AXWire.attribute(named: name)], expectsReply: true, timeout: 3)
            attributes[name] = AXWire.jsonReady(AXWire.unwrap(value))
        }
        return ["root": AXWire.jsonReady(root), "attributes": attributes]
    }
    func serviceReadiness() throws -> [String: Any] {
        guard services == nil else { throw ProbeError.invalidRequest }
        stage = "fixture_services"
        services = try FixtureServices(udid: udid)
        return try services!.readiness()
    }
}

func emit(_ value: [String: Any]) {
    if let data = try? JSONSerialization.data(withJSONObject: value, options: [.sortedKeys]) {
        FileHandle.standardOutput.write(data + Data([10]))
    }
}

func requestLine() throws -> String? {
    var bytes = [UInt8]()
    var byte: UInt8 = 0
    while true {
        let count = Darwin.read(STDIN_FILENO, &byte, 1)
        if count < 0 && errno == EINTR { continue }
        if count == 0 {
            guard bytes.isEmpty else { throw ProbeError.invalidRequest }
            return nil
        }
        guard count == 1 else { throw ProbeError.socketIO }
        if byte == 10 {
            guard let line = String(bytes: bytes, encoding: .utf8) else { throw ProbeError.invalidRequest }
            return line
        }
        guard bytes.count < 4096 else { throw ProbeError.frameTooLarge }
        bytes.append(byte)
    }
}

// One explicit device and transport. Never try another phone or fall back.
// Errors deliberately omit backend text, device identifiers and on-screen content.
var probe: Probe?
var stopped = false
let ownedFixtureMode = Array(CommandLine.arguments.dropFirst()) == ["--owned-fixture"]
if CommandLine.arguments.count > 1 && !ownedFixtureMode { emit(["ok": false, "error": "invalid_mode"]); exit(2) }
var ownedCounter: OwnedCounter?
while true {
    do {
        guard let line = try requestLine() else { break }
        stage = "request"
        guard let request = try JSONSerialization.jsonObject(with: Data(line.utf8)) as? [String: Any],
              let command = request["command"] as? String else { throw ProbeError.invalidRequest }
        let keys = Set(request.keys)
        if command == "close", keys == ["command"] { ownedCounter = nil; probe = nil; emit(["ok": true, "closed": true]); break }
        guard !stopped else { throw ProbeError.invalidRequest }
        switch command {
        case "open":
            guard keys == ["command", "device_id", "transport"], probe == nil,
                  let transport = request["transport"] as? String,
                  ["coredevice-tunnel", "mobiledevice-lockdown"].contains(transport),
                  let udid = request["device_id"] as? String,
                  (24...80).contains(udid.count), udid.allSatisfy({ $0.isHexDigit || $0 == "-" }) else {
                throw ProbeError.invalidRequest
            }
            probe = try Probe(udid: udid, transport: transport)
            emit(["ok": true, "connection_id": probe!.epoch, "transport": transport,
                  "xcode": probe!.xcode, "input_enabled": ownedFixtureMode])
        case "capabilities":
            guard keys == ["command"], let probe else { throw ProbeError.invalidRequest }
            emit(["ok": true, "selectors": try probe.capabilities(), "input_enabled": ownedFixtureMode])
        case "read_root":
            guard keys == ["command"], let probe else { throw ProbeError.invalidRequest }
            var result = try probe.readRoot()
            result["ok"] = true; result["input_enabled"] = ownedFixtureMode
            emit(result)
        case "service_readiness":
            guard keys == ["command"], let probe else { throw ProbeError.invalidRequest }
            var result = try probe.serviceReadiness()
            result["ok"] = true; result["input_enabled"] = ownedFixtureMode
            emit(result)
        case "prepare_owned_counter":
            guard ownedFixtureMode, ownedCounter == nil,
                  keys == ["command", "expected_pid", "fixture_heading"], let probe,
                  let pid = request["expected_pid"] as? Int, let heading = request["fixture_heading"] as? String,
                  let services = probe.services else { throw ProbeError.invalidRequest }
            ownedCounter = try OwnedCounter(udid: probe.udid, connection: probe.connection,
                services: services, pid: pid, heading: heading)
            var result = try ownedCounter!.prepare()
            result["ok"] = true; result["input_enabled"] = true; emit(result)
        case "tap_owned_counter_once":
            guard ownedFixtureMode, keys == ["command"], let ownedCounter else { throw ProbeError.invalidRequest }
            var result = try ownedCounter.tap()
            result["ok"] = true; result["input_enabled"] = true; emit(result)
        case "read_owned_counter":
            guard ownedFixtureMode, keys == ["command"], let ownedCounter else { throw ProbeError.invalidRequest }
            var result = try ownedCounter.readback()
            result["ok"] = true; result["input_enabled"] = true; emit(result)
        default: throw ProbeError.invalidRequest
        }
    } catch {
        // An exception invalidates this process session. There is no reconnect/retry path.
        let touchAttempted = probe?.services?.touchAttempted ?? false
        let focusPID = ownedCounter?.lastPID
        ownedCounter = nil; probe = nil; stopped = true
        let nativeError = error as NSError
        var details: [String: Any] = ["ok": false, "error": "ios_ax_probe_failed",
            "stage": stage, "input_enabled": false, "touch_attempted": touchAttempted]
        if touchAttempted { details["sent"] = NSNull(); details["effect"] = "unknown" }
        if let focusPID { details["observed_pid"] = focusPID }
        if nativeError.domain == "IUDTXErrorDomain" { details["dtx_error_code"] = nativeError.code }
        if case MobileDeviceError.callFailed(let call, let code) = error {
            details["mobiledevice_call"] = call
            details["mobiledevice_error_code"] = Int(code)
        }
        if case MobileDeviceError.noDeviceFound = error { details["reason"] = "mobiledevice_not_found" }
        if case MobileDeviceError.deviceNotFound = error { details["reason"] = "explicit_device_not_seen" }
        if case CoreDeviceClient.Failure.actionFailed(let action, let message) = error {
            details["coredevice_action"] = action
            // Diagnostic category only: never a lock/readiness attestation.
            let text = message.lowercased()
            details["reason"] = text.contains("could not be established") ? "device_connection_unavailable" :
                text.contains("not found") ? "service_not_found" :
                text.contains("not available") ? "service_not_available" :
                text.contains("locked") ? "device_locked" :
                text.contains("developer mode") ? "developer_mode" :
                text.contains("not connected") ? "device_not_connected" : "coredevice_rejected"
        }
        emit(details)
        // Framing errors are terminal; don't interpret a suffix as a new request.
        if case ProbeError.frameTooLarge = error { break }
    }
}
// Explicit cleanup also on EOF and malformed framing (top-level globals aren't RAII).
ownedCounter = nil; probe = nil
