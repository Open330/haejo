// Disposable, nonactivating AppKit window for observation-continuation tests.
// The last of 240 real buttons must not be reachable in the first 60-child walk.
import AppKit

@MainActor
final class PagesDelegate: NSObject, NSApplicationDelegate {
    let output: URL
    var window: NSWindow?
    var count = 0
    let result = NSTextField(labelWithString: "Nothing picked")

    init(output: URL) { self.output = output }

    func write(_ selected: String) {
        let data = try! JSONSerialization.data(withJSONObject: ["count": count, "selected": selected])
        try! data.write(to: output, options: .atomic)
    }

    func applicationDidFinishLaunching(_ note: Notification) {
        let window = NSWindow(contentRect: NSRect(x: 160, y: 140, width: 960, height: 610),
                              styleMask: [.titled, .closable], backing: .buffered, defer: false)
        window.title = "Tacto Observation Pages Fixture"
        window.isReleasedWhenClosed = false
        self.window = window
        for index in 0..<240 {
            let title = String(format: "Item%03d", index)
            let button = NSButton(title: title, target: self, action: #selector(pick(_:)))
            button.frame = NSRect(x: 8 + (index % 16) * 59,
                                  y: 46 + (14 - index / 16) * 36, width: 59, height: 30)
            button.setAccessibilityIdentifier("tacto-pages-\(title)")
            window.contentView!.addSubview(button)
        }
        result.frame = NSRect(x: 16, y: 12, width: 650, height: 24)
        result.setAccessibilityIdentifier("tacto-pages-result")
        window.contentView!.addSubview(result)
        window.orderFront(nil)
        write("")
        Timer.scheduledTimer(withTimeInterval: 240, repeats: false) { _ in NSApplication.shared.terminate(nil) }
    }

    @objc func pick(_ sender: NSButton) {
        count += 1
        result.stringValue = "Picked \(sender.title) count \(count)"
        write(sender.title)
    }
}

@main
enum ObservationPagesFixture {
    @MainActor static func main() {
        guard CommandLine.arguments.count == 2 else { exit(2) }
        let app = NSApplication.shared
        app.setActivationPolicy(.accessory)
        let delegate = PagesDelegate(output: URL(fileURLWithPath: CommandLine.arguments[1]))
        app.delegate = delegate
        withExtendedLifetime(delegate) { app.run() }
    }
}
