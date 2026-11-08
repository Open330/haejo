// swift-tools-version: 6.0
import PackageDescription
import Foundation
let cachePath = URL(fileURLWithPath: #filePath).deletingLastPathComponent().appendingPathComponent("__pycache__").path
let cacheExcludes = FileManager.default.fileExists(atPath: cachePath) ? ["__pycache__"] : []
let package = Package(name: "TactoIOSAXSpike", platforms: [.macOS(.v14)], products: [
    .executable(name: "tacto-ios-ax-spike", targets: ["TactoIOSAXSpike"])
], targets: [
    .target(name: "CDTXBridge", path: "Vendor/CDTXBridge"),
    .target(name: "CMobileDevice", path: "Vendor/CMobileDevice"),
    .executableTarget(name: "TactoIOSAXSpike", dependencies: ["CDTXBridge", "CMobileDevice"], path: ".",
        exclude: ["Vendor/CDTXBridge", "Vendor/CMobileDevice", "Package.swift", "upstream.json", "THIRD_PARTY_LICENSE.txt",
                  "counter_fixture.py", "qualify_owned_counter.py", "README.md"] + cacheExcludes,
        sources: ["Sources", "Vendor/Transport"])
])
