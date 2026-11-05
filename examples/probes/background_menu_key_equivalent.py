"""Can a background TextEdit open Save As from its observed key equivalent?

background-menu-refusal.py settled that a responder-chain menu command is
disabled in a background app and that pressing it is refused. This asks the
remaining question: the same command's OWN key equivalent, read from the menu
item (AXMenuItemCmdChar / AXMenuItemCmdModifiers — never guessed from a title),
posted to TextEdit's pid and bound to the owned document window, the way the
helper's window-bound key path already delivers navigation keys.

Only an owned document is used: a fresh RTF in a temporary folder, opened with
`open -g`, and an owned foreground window that takes the front back once after
that open (macOS 27 brought TextEdit forward on `open -g`, measured
2026-11-05). Every activation is recorded by focus_witness. Nothing is saved:
a sheet that appears is cancelled by AXPress on its own Cancel button, and the
owned document is closed unmodified.

Success is a save sheet on THE OWNED WINDOW with no activation — not the post
returning. A navigation key (Right) is sent first as the delivery control: if
it does not move the owned caret, a missing sheet says nothing.

`--foreground-control` additionally repeats the same event with TextEdit in
front (it activates TextEdit; the owned window must be its focused window) to
show the event itself is well-formed. It is off by default.

    python3 examples/probes/background_menu_key_equivalent.py [--repeat N] [--foreground-control]
"""
import argparse
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[2]
TARGET = 'com.apple.TextEdit'

TOOL = r'''
import AppKit
import ApplicationServices
import Carbon
setvbuf(stdout, nil, _IOLBF, 0)
let args = CommandLine.arguments
let mode = args[1]
func emit(_ value: [String: Any]) {
    print(String(data: try! JSONSerialization.data(withJSONObject: value), encoding: .utf8)!) }
if mode == "foreground" {
    // An owned window that takes the front once, then only waits.
    let app = NSApplication.shared
    app.setActivationPolicy(.regular)
    let window = NSWindow(contentRect: NSRect(x: 40, y: 40, width: 280, height: 60), styleMask: [.titled],
                          backing: .buffered, defer: false)
    window.title = args[2]
    window.makeKeyAndOrderFront(nil)
    DispatchQueue.main.asyncAfter(deadline: .now() + 0.2) {
        app.activate(ignoringOtherApps: true); emit(["ready": Int(getpid())]) }
    app.run()
}
let pid = pid_t(args[2])!, title = args[3]
func attr(_ e: AXUIElement, _ n: String) -> AnyObject? {
    var v: AnyObject?; return AXUIElementCopyAttributeValue(e, n as CFString, &v) == .success ? v : nil }
let app = AXUIElementCreateApplication(pid)
typealias GetWindow = @convention(c) (AXUIElement, UnsafeMutablePointer<CGWindowID>) -> AXError
let hi = dlopen("/System/Library/Frameworks/ApplicationServices.framework/Frameworks/HIServices.framework/HIServices", RTLD_LAZY)
let getWindow = unsafeBitCast(dlsym(hi, "_AXUIElementGetWindow")!, to: GetWindow.self)
let matches = ((attr(app, "AXWindows") as? [AXUIElement]) ?? []).filter { attr($0, "AXTitle") as? String == title }
guard matches.count == 1 else { emit(["ok": false, "reason": "owned_window_count", "count": matches.count]); exit(0) }
let window = matches[0]
var windowID: CGWindowID = 0
guard getWindow(window, &windowID) == .success, windowID > 0 else { emit(["ok": false, "reason": "window_id"]); exit(0) }
func ownedFocused() -> Bool { attr(app, "AXFocusedWindow").map { CFEqual($0, window) } ?? false }
func sheets() -> [AXUIElement] {
    ((attr(window, "AXChildren") as? [AXUIElement]) ?? []).filter { attr($0, "AXRole") as? String == "AXSheet" } }
func textArea(_ e: AXUIElement, _ depth: Int) -> AXUIElement? {
    if attr(e, "AXRole") as? String == "AXTextArea" { return e }
    if depth < 8 { for child in (attr(e, "AXChildren") as? [AXUIElement]) ?? [] {
        if let hit = textArea(child, depth + 1) { return hit } } }
    return nil }
func caret() -> Int? {
    guard let area = textArea(window, 0), let raw = attr(area, "AXSelectedTextRange") else { return nil }
    var range = CFRange(); guard AXValueGetValue(raw as! AXValue, .cfRange, &range) else { return nil }
    return range.location }
func menuItem(_ path: [[String]]) -> [AXUIElement] {
    guard let bar = attr(app, "AXMenuBar") else { return [] }
    var nodes = [bar as! AXUIElement]
    for wants in path {
        var next: [AXUIElement] = []
        for node in nodes {
            var kids = (attr(node, "AXChildren") as? [AXUIElement]) ?? []
            if let menu = kids.first(where: { attr($0, "AXRole") as? String == "AXMenu" }) {
                kids = (attr(menu, "AXChildren") as? [AXUIElement]) ?? [] }
            next += kids.filter { wants.contains(attr($0, "AXTitle") as? String ?? "\u{0}") }
        }
        nodes = next
    }
    return nodes }
let item = menuItem([["File", "파일"], ["Save As…", "다른 이름으로 저장…"]])
guard item.count == 1 else { emit(["ok": false, "reason": "menu_item_count", "count": item.count]); exit(0) }
let observedChar = attr(item[0], "AXMenuItemCmdChar") as? String
let observedModifiers = (attr(item[0], "AXMenuItemCmdModifiers") as? NSNumber)?.intValue
let state: [String: Any] = ["window_id": Int(windowID), "owned_focused": ownedFocused(),
    "owned_main": attr(window, "AXMain") as? Bool as Any, "app_frontmost": attr(app, "AXFrontmost") as? Bool as Any,
    "sheets": sheets().count, "caret": caret() as Any, "item_enabled": attr(item[0], "AXEnabled") as? Bool as Any,
    "cmd_char": observedChar as Any, "cmd_modifiers": observedModifiers as Any]
func post(code: UInt16, chars: String, plain: String, flags: NSEvent.ModifierFlags) -> Bool {
    let stamp = ProcessInfo.processInfo.systemUptime
    var events: [CGEvent] = []
    for kind in [NSEvent.EventType.keyDown, .keyUp] {
        guard let owner = NSEvent.keyEvent(with: kind, location: .zero, modifierFlags: flags, timestamp: stamp,
                windowNumber: Int(windowID), context: nil, characters: chars, charactersIgnoringModifiers: plain,
                isARepeat: false, keyCode: code), let event = owner.cgEvent else { return false }
        events.append(event)
    }
    // The helper's window-bound key path re-checks this before each event.
    for event in events { guard ownedFocused() else { return false }; event.postToPid(pid) }
    return true }
func keyCode(for character: String) -> UInt16? {
    // From the current layout, never from a table of guesses.
    guard let source = TISCopyCurrentKeyboardLayoutInputSource()?.takeRetainedValue(),
          let raw = TISGetInputSourceProperty(source, kTISPropertyUnicodeKeyLayoutData) else { return nil }
    let data = Unmanaged<CFData>.fromOpaque(raw).takeUnretainedValue()
    let layout = unsafeBitCast(CFDataGetBytePtr(data), to: UnsafePointer<UCKeyboardLayout>.self)
    var found: [UInt16] = []
    for code in 0..<128 {
        var dead: UInt32 = 0, length = 0, buffer = [UniChar](repeating: 0, count: 4)
        guard UCKeyTranslate(layout, UInt16(code), UInt16(kUCKeyActionDown), 0, UInt32(LMGetKbdType()),
                             OptionBits(kUCKeyTranslateNoDeadKeysBit), &dead, 4, &length, &buffer) == noErr,
              length == 1 else { continue }
        if String(utf16CodeUnits: buffer, count: 1).lowercased() == character.lowercased() { found.append(UInt16(code)) }
    }
    return found.count == 1 ? found[0] : nil }
switch mode {
case "state":
    emit(state.merging(["ok": true]) { a, _ in a })
case "navigation":
    let before = caret()
    let posted = post(code: 124, chars: "\u{F703}", plain: "\u{F703}", flags: .function)
    Thread.sleep(forTimeInterval: 0.5)
    emit(["ok": posted, "caret_before": before as Any, "caret_after": caret() as Any])
case "key_equivalent":
    guard let char = observedChar, char.count == 1, let modifiers = observedModifiers,
          modifiers & ~0xF == 0, let code = keyCode(for: char) else {
        emit(["ok": false, "reason": "key_equivalent_not_observed", "state": state]); exit(0) }
    var flags: NSEvent.ModifierFlags = []
    if modifiers & 8 == 0 { flags.insert(.command) }
    if modifiers & 1 != 0 { flags.insert(.shift) }
    if modifiers & 2 != 0 { flags.insert(.option) }
    if modifiers & 4 != 0 { flags.insert(.control) }
    let plain = flags.contains(.shift) ? char.uppercased() : char.lowercased()
    guard sheets().isEmpty else { emit(["ok": false, "reason": "sheet_already_open"]); exit(0) }
    let posted = post(code: code, chars: char.lowercased(), plain: plain, flags: flags)
    var appeared: Double? = nil
    let start = ProcessInfo.processInfo.systemUptime
    while ProcessInfo.processInfo.systemUptime - start < 3 {
        if !sheets().isEmpty { appeared = ProcessInfo.processInfo.systemUptime - start; break }
        Thread.sleep(forTimeInterval: 0.05)
    }
    emit(["ok": posted, "state_before": state, "key_code": Int(code), "flags": Int(flags.rawValue),
          "sheet_on_owned_window": appeared != nil, "sheet_seconds": appeared as Any,
          "app_frontmost_after": attr(app, "AXFrontmost") as? Bool as Any])
case "cancel":
    var pressed: [Int32] = []
    for sheet in sheets() {
        func walk(_ e: AXUIElement, _ depth: Int) {
            if attr(e, "AXRole") as? String == "AXButton", ["Cancel", "취소"].contains(attr(e, "AXTitle") as? String ?? "") {
                pressed.append(AXUIElementPerformAction(e, kAXPressAction as CFString).rawValue); return }
            if depth < 12 { for child in (attr(e, "AXChildren") as? [AXUIElement]) ?? [] { walk(child, depth + 1) } }
        }
        walk(sheet, 0)
    }
    Thread.sleep(forTimeInterval: 0.5)
    emit(["ok": pressed == [0] && sheets().isEmpty, "pressed": pressed, "sheets_after": sheets().count])
case "close":
    guard sheets().isEmpty, attr(window, "AXDocument") != nil else { emit(["ok": false, "reason": "not_closable"]); exit(0) }
    guard (attr(window, "AXEdited") as? Bool) != true else { emit(["ok": false, "reason": "owned_document_edited"]); exit(0) }
    guard let button = attr(window, "AXCloseButton") else { emit(["ok": false, "reason": "close_button"]); exit(0) }
    let error = AXUIElementPerformAction(button as! AXUIElement, kAXPressAction as CFString)
    Thread.sleep(forTimeInterval: 0.5)
    let left = ((attr(app, "AXWindows") as? [AXUIElement]) ?? []).filter { attr($0, "AXTitle") as? String == title }.count
    emit(["ok": error == .success && left == 0, "windows_left": left])
default:
    emit(["ok": false, "reason": "mode"])
}
'''


def _frontmost():
    from AppKit import NSWorkspace
    app = NSWorkspace.sharedWorkspace().frontmostApplication()
    return None if app is None else (app.bundleIdentifier() or f'{app.localizedName()}#{app.processIdentifier()}')


def _textedit_pid():
    from AppKit import NSRunningApplication
    running = NSRunningApplication.runningApplicationsWithBundleIdentifier_(TARGET)
    return int(running[0].processIdentifier()) if len(running) == 1 else None


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('--repeat', type=int, default=3)
    parser.add_argument('--foreground-control', action='store_true')
    parser.add_argument('--output', type=Path)
    options = parser.parse_args(argv)
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from focus_witness import FocusWitness

    nonce = secrets.token_hex(8)
    work = Path(tempfile.mkdtemp(prefix='tacto-bg-keyeq-')).resolve()
    tool = work / 'tool'
    (work / 'tool.swift').write_text(TOOL)
    subprocess.run(['xcrun', 'swiftc', str(work / 'tool.swift'), '-o', str(tool)],
                   check=True, capture_output=True, timeout=240)
    document = work / f'tacto-bg-keyeq-{nonce}.rtf'
    document.write_bytes(b'{\\rtf1\\ansi owned background key equivalent fixture ' + nonce.encode() + b'}')
    report = {'scope': 'owned_TextEdit_document_background_key_equivalent', 'passed': False,
              'nonce': nonce, 'model_requests': 0, 'saves_committed': 0, 'runs': [],
              'what_this_measures': 'whether the observed Save As key equivalent, posted to the pid and '
                                    'bound to the owned window, opens a sheet while TextEdit stays behind'}
    front = None

    def call(*args):
        out = subprocess.run([str(tool), *map(str, args)], capture_output=True, text=True, timeout=30)
        lines = [line for line in out.stdout.splitlines() if line.startswith('{')]
        return json.loads(lines[-1]) if lines else {'ok': False, 'stderr': out.stderr[-400:]}

    pid = None
    try:
        report['frontmost_before_open'] = _frontmost()
        subprocess.run(['open', '-g', '-a', 'TextEdit', str(document)], check=True, timeout=20)
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            pid = _textedit_pid()
            if pid and call('state', pid, document.name).get('ok'):
                break
            time.sleep(0.2)
        report['frontmost_after_open'] = _frontmost()
        front = subprocess.Popen([str(tool), 'foreground', f'tacto-bg-keyeq-front-{nonce}'],
                                 stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
        front.stdout.readline()
        time.sleep(0.5)
        with FocusWitness() as witness:
            report['witness_initial'] = witness.initial
            for index in range(options.repeat):
                run = {'index': index, 'background_state': call('state', pid, document.name)}
                run['navigation_control'] = call('navigation', pid, document.name)
                run['key_equivalent'] = call('key_equivalent', pid, document.name)
                if run['key_equivalent'].get('sheet_on_owned_window'):
                    run['cancel'] = call('cancel', pid, document.name)
                report['runs'].append(run)
        report['background_activations'] = [a.get('bundle') for a in witness.activations]
        report['background_windows'] = witness.summary()['windows']
        if options.foreground_control:
            # Measurement only: this takes the front for TextEdit.
            subprocess.run(['osascript', '-e', 'tell application "System Events" to set frontmost of '
                            f'(first process whose unix id is {pid}) to true'], timeout=10)
            time.sleep(0.8)
            control = {'state': call('state', pid, document.name)}
            if control['state'].get('owned_focused') is True:
                control['key_equivalent'] = call('key_equivalent', pid, document.name)
                if control['key_equivalent'].get('sheet_on_owned_window'):
                    control['cancel'] = call('cancel', pid, document.name)
            report['foreground_control'] = control
        runs = report['runs']
        delivered = all(r['navigation_control'].get('caret_after') not in (None, r['navigation_control'].get('caret_before'))
                        for r in runs)
        opened = [bool(r['key_equivalent'].get('sheet_on_owned_window')) for r in runs]
        report['navigation_delivered_every_run'] = delivered
        report['background_sheet_opened'] = opened
        report['background_activation_free'] = report['background_activations'] == []
        report['passed'] = bool(runs) and delivered and all(opened) and report['background_activation_free']
        report['conclusion'] = ('background_key_equivalent_opens_save_as' if report['passed'] else
                                'background_key_equivalent_does_not_open_save_as' if delivered and not any(opened)
                                and report['background_activation_free'] else 'inconclusive')
    finally:
        if pid:
            report['cleanup_close'] = call('close', pid, document.name)
        if front is not None:
            front.terminate()
            try:
                front.wait(timeout=5)
            except subprocess.TimeoutExpired:
                front.kill()
        for path in (document, work / 'tool', work / 'tool.swift'):
            try:
                path.unlink()
            except OSError:
                pass
        try:
            work.rmdir()
        except OSError:
            pass
        report['frontmost_end'] = _frontmost()
    output = options.output or ROOT / 'reviews' / time.strftime('%Y-%m-%d') / f'background-menu-key-equivalent-{time.time_ns()}.json'
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=1))
    print(json.dumps({'output': str(output), 'passed': report['passed'], 'conclusion': report.get('conclusion')}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
