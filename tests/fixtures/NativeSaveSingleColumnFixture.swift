// Owned background NSSavePanel sheet for directory witnesses; never saves.
import AppKit
import Foundation

final class SingleColumnDelegate: NSObject, NSApplicationDelegate {
    var window: NSWindow?
    var panel: NSSavePanel?
    let directory: String
    init(directory: String) { self.directory = directory }
    func applicationDidFinishLaunching(_ notification: Notification) {
        let window = NSWindow(contentRect: NSRect(x: 120, y: 120, width: 640, height: 220),
                              styleMask: [.titled, .closable], backing: .buffered, defer: false)
        window.title = "HAEJO Owned Save Single Column Fixture"
        window.isReleasedWhenClosed = false
        self.window = window
        window.orderBack(nil)
        let panel = NSSavePanel()
        self.panel = panel
        panel.directoryURL = URL(fileURLWithPath: directory, isDirectory: true)
        panel.nameFieldStringValue = "never-saved.rtf"
        // The completion handler never writes; the evaluator cancels by exiting.
        panel.beginSheetModal(for: window) { _ in }
        // The panel's in-process directory is the independent truth the AX
        // witness must match. Only its path is printed, never folder contents.
        Timer.scheduledTimer(withTimeInterval: 0.25, repeats: true) { _ in
            let state: [String: Any] = ["pid": Int(getpid()), "directory": panel.directoryURL?.path ?? "",
                                        "expanded": panel.isExpanded]
            if let data = try? JSONSerialization.data(withJSONObject: state) {
                print(String(decoding: data, as: UTF8.self)); fflush(stdout)
            }
        }
    }
}

let app = NSApplication.shared
app.setActivationPolicy(.accessory)
let delegate = SingleColumnDelegate(directory: CommandLine.arguments[1])
app.delegate = delegate
app.run()
