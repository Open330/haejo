// The helper's side of the stage-2 channel: ask the menu app about one input.
//
// The menu app is authenticated as the SERVER of this socket, by its code
// signature (same team as this helper, menu app identifier), before anything
// is sent. A squatted socket or an unsigned listener reads as unavailable,
// never as an answer. What is sent is what the helper read (`item`), so the
// card the person sees describes the input the helper is about to post.

import Foundation
import AppKit
import Security

enum NativeApprovalClient {
    /// The shipped menu app only; a dev preview build is not an approver.
    static let menuIdentifiers = ["ai.callabo.haejo.setup.standalone.preview"]
    /// Longer than the card's own wait, so the menu app's "timeout" arrives.
    static let replyWait: TimeInterval = 630

    static var socketPath: String {
        FileManager.default.homeDirectoryForCurrentUser
            .appendingPathComponent("Library/Application Support/Haejo/approval.sock").path
    }

    static func serverRequirement(team: String) -> String? {
        guard team.range(of: "^[A-Z0-9]{10}$", options: .regularExpression) != nil else { return nil }
        let ids = menuIdentifiers.map { "identifier \"\($0)\"" }.joined(separator: " or ")
        return "(\(ids)) and anchor apple generic and certificate leaf[subject.OU] = \"\(team)\""
    }

    /// The signing team of a running process, from its code signature.
    static func team(of pid: pid_t) -> String? {
        let attrs = [kSecGuestAttributePid: NSNumber(value: pid)] as CFDictionary
        var code: SecCode?
        guard SecCodeCopyGuestWithAttributes(nil, attrs, [], &code) == errSecSuccess, let code else { return nil }
        var binary: SecStaticCode?
        guard SecCodeCopyStaticCode(code, [], &binary) == errSecSuccess, let binary else { return nil }
        var raw: CFDictionary?
        guard SecCodeCopySigningInformation(binary, SecCSFlags(rawValue: kSecCSSigningInformation), &raw) == errSecSuccess,
              let info = raw as? [String: Any] else { return nil }
        return info[kSecCodeInfoTeamIdentifier as String] as? String
    }


    /// What the card shows and what a later re-check compares.
    static func item(_ input: ObservedInput, _ cls: ApprovalClass, pid: pid_t, commit: CommitView = CommitView()) -> [String: Any] {
        let app = NSRunningApplication(processIdentifier: pid)
        return ["class": cls.rawValue, "kind": input.kind, "role": input.role, "subrole": input.subrole,
                "labels": input.labels, "default_button": input.defaultButtonLabels,
                "target": app?.bundleIdentifier ?? "", "app_name": app?.localizedName ?? "",
                "team": team(of: pid) ?? "", "pid": Int(pid),
                "process_start": app?.launchDate?.timeIntervalSince1970 ?? 0,
                "window": NativeApproval.windowTitle(fromIdentity: input.window),
                "commit": commit.summary, "unreadable": commit.unreadable, "destination": commit.destination]
    }

    /// What must not change between the card and the input: the process
    /// and its signer. (The element and its window are in the input itself.)
    static func context(_ pid: pid_t) -> String {
        let app = NSRunningApplication(processIdentifier: pid)
        return [app?.bundleIdentifier ?? "", team(of: pid) ?? "",
                String(app?.launchDate?.timeIntervalSince1970 ?? 0)].joined(separator: "\u{1f}")
    }

    static func check(_ input: ObservedInput, _ cls: ApprovalClass, _ pid: pid_t, _ commit: CommitView) -> NativeDecision {
        guard let team = HaejoSigning.ownTeam(), let requirement = serverRequirement(team: team) else { return .unavailable }
        guard let reply = ask(["op": "native_check", "item": item(input, cls, pid: pid, commit: commit)], requirement: requirement) else {
            return NativeApproval.callerGone() ? .cancelled : .unavailable
        }
        switch reply["status"] as? String {
        case "allowed": return .allowed
        case "denied": return .denied
        case "timeout", "expired": return .timeout
        default: return .unavailable
        }
    }

    static func ask(_ message: [String: Any], requirement: String) -> [String: Any]? {
        let fd = socket(AF_UNIX, SOCK_STREAM, 0)
        guard fd >= 0 else { return nil }
        defer { close(fd) }
        var on: Int32 = 1
        setsockopt(fd, SOL_SOCKET, SO_NOSIGPIPE, &on, socklen_t(MemoryLayout<Int32>.size))
        var address = sockaddr_un(); address.sun_family = sa_family_t(AF_UNIX)
        let bytes = Array(socketPath.utf8)
        guard bytes.count < MemoryLayout.size(ofValue: address.sun_path) else { return nil }
        withUnsafeMutableBytes(of: &address.sun_path) { $0.copyBytes(from: bytes) }
        let connected = withUnsafePointer(to: &address) { $0.withMemoryRebound(to: sockaddr.self, capacity: 1) {
            connect(fd, $0, socklen_t(MemoryLayout<sockaddr_un>.size)) } }
        guard connected == 0 else { return nil }
        // The listener must be the signed menu app, checked before sending.
        guard PeerAuth.satisfies(fd: fd, requirement: requirement).0 else { return nil }
        // Read in one-second slices so Esc (the all-run stop) ends the wait.
        var timeout = timeval(tv_sec: 1, tv_usec: 0)
        setsockopt(fd, SOL_SOCKET, SO_RCVTIMEO, &timeout, socklen_t(MemoryLayout<timeval>.size))
        let deadline = Date().addingTimeInterval(replyWait)
        guard var out = try? JSONSerialization.data(withJSONObject: message) else { return nil }
        out.append(10)
        let sent = out.withUnsafeBytes { write(fd, $0.baseAddress, $0.count) }
        guard sent == out.count else { return nil }
        var data = Data(); var buffer = [UInt8](repeating: 0, count: 65536)
        while !data.contains(10) {
            // Esc, or the caller of this request gone: closing the socket
            // tells the menu app to drop the card.
            if NativeApproval.callerGone() || Date() > deadline { return nil }
            let n = read(fd, &buffer, buffer.count)
            if n < 0 && (errno == EAGAIN || errno == EWOULDBLOCK || errno == EINTR) { continue }
            if n <= 0 { return nil }
            data.append(contentsOf: buffer.prefix(n))
            if data.count > 1 << 20 { return nil }
        }
        guard let line = data.split(separator: 10).first else { return nil }
        return try? JSONSerialization.jsonObject(with: Data(line)) as? [String: Any]
    }
}
