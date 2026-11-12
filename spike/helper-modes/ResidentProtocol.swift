import Foundation

@objc(HaejoModeRPC) protocol HaejoModeRPC {
    func acquire(_ build: String, reply: @escaping (NSDictionary) -> Void)
    func request(_ frame: Data, reply: @escaping (Data) -> Void)
}

enum HaejoResident {
    static let service = "open330.haejo.prototype.resident"
    static let agent = "open330.haejo.prototype.agent"
}
