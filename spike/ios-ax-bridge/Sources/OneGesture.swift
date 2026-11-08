import Foundation

enum GestureError: Error { case invalidOrAlreadyAttempted }

/// One touchscreen gesture. A failed/partial send never permits a new contact.
/// Wire layout follows the pinned MIT iphone-use HIDService; notice retained.
final class OneGesture {
    private let send: (Data) throws -> Void
    private let ping: () throws -> Void
    private let pause: (TimeInterval) -> Void
    private(set) var attempted = false
    private(set) var contactReports = 0
    private(set) var releaseReports = 0
    private(set) var cleanupReleaseAttempts = 0
    init(send: @escaping (Data) throws -> Void, ping: @escaping () throws -> Void,
         pause: @escaping (TimeInterval) -> Void = Thread.sleep(forTimeInterval:)) {
        self.send = send; self.ping = ping; self.pause = pause
    }
    func tapOnce(x: Int, y: Int) throws {
        guard !attempted, (0...65535).contains(x), (0...65535).contains(y) else {
            throw GestureError.invalidOrAlreadyAttempted
        }
        attempted = true
        var releaseComplete = false
        func write(_ state: UInt8) throws {
            var report = Data([0x09, 0x01, 0x05, state, UInt8(x & 255), UInt8(x >> 8), UInt8(y & 255), UInt8(y >> 8)])
            report.append(Data(repeating: 0, count: 32)); report.append(Data([2, 0, 0, 0]))
            let stamp = DispatchTime.now().uptimeNanoseconds & ((1 << 48) - 1)
            for shift in stride(from: 0, to: 48, by: 8) { report.append(UInt8((stamp >> UInt64(shift)) & 255)) }
            report.append(Data(repeating: 0, count: 8))
            try send(report)
            if state == 0xC2 { contactReports += 1 } else { releaseReports += 1 }
        }
        do {
            try write(0xC2); pause(0.04)
            try write(0xC2); pause(0.04)
            try write(0x02); releaseComplete = true
            try ping()  // HTTP/2 progress, not a delivered-touch/application ACK.
        } catch {
            if !releaseComplete {
                cleanupReleaseAttempts += 1
                try? write(0x02)  // One release only, same connection, no new down.
            }
            throw error
        }
    }
}
