import Foundation
import AppKit
import ApplicationServices

// The one place a real button click is posted: the last route for selecting a
// browser tab, used after AXPress and the window-bound click both left the
// tab unselected (ParallelWindows.swift, parallelTabSelect).

/// The last route: the browser comes to the front, the real pointer presses
/// the tab, the pointer returns to where it was and the app that was in front
/// is put back.
func frontPointerPress(_ tab:AXUIElement,window:AXUIElement,pid:pid_t,windowID:CGWindowID,
                       done:() -> Bool,report:inout [String:Any]) -> String? {
    guard let previous=nativeFrontmostProcessPID(),let app=NSRunningApplication(processIdentifier:pid),
          let cursor=CGEvent(source:nil)?.location else { return "front_state_unavailable" }
    report["front_taken"]=previous != pid
    defer {
        CGWarpMouseCursorPosition(cursor)
        if previous != pid { report["front_restored"]=returnScreen(to:previous) }
    }
    _ = AXUIElementPerformAction(window,kAXRaiseAction as CFString)
    if previous != pid { _ = app.activate(options:[]) }
    let until=ProcessInfo.processInfo.systemUptime+2
    while nativeFrontmostProcessPID() != pid && ProcessInfo.processInfo.systemUptime<until { usleep(20_000) }
    guard nativeFrontmostProcessPID()==pid else { return "browser_not_in_front" }
    _ = AXUIElementPerformAction(tab,"AXScrollToVisible" as CFString)
    usleep(150_000)
    var raw:CFTypeRef?
    var origin=CGPoint.zero,size=CGSize.zero
    guard AXUIElementCopyAttributeValue(tab,kAXPositionAttribute as CFString,&raw) == .success,
          AXValueGetValue(raw as! AXValue,.cgPoint,&origin),
          AXUIElementCopyAttributeValue(tab,kAXSizeAttribute as CFString,&raw) == .success,
          AXValueGetValue(raw as! AXValue,.cgSize,&size),size.width>4,size.height>4 else { return "tab_frame_unavailable" }
    let point=CGPoint(x:origin.x+size.width/2,y:origin.y+size.height/2)
    // The pointer lands on whatever window is on top at that point: it must
    // be this browser window and this tab.
    let above=CGWindowListCopyWindowInfo([.optionOnScreenOnly,.excludeDesktopElements],kCGNullWindowID) as? [[String:Any]] ?? []
    let top=above.first { entry in
        guard (entry[kCGWindowLayer as String] as? Int)==0,
              let bounds=entry[kCGWindowBounds as String] as? [String:Any],
              let rect=CGRect(dictionaryRepresentation:bounds as CFDictionary) else { return false }
        return rect.contains(point)
    }
    guard (top?[kCGWindowNumber as String] as? NSNumber)?.uint32Value==windowID else { return "tab_covered" }
    var hit=elementAtPoint(point,pid:pid)
    var onTab=false
    for _ in 0..<8 {
        guard let node=hit else { break }
        if CFEqual(node,tab) { onTab=true;break }
        hit=attr(node,kAXParentAttribute as String).flatMap { CFGetTypeID($0)==AXUIElementGetTypeID() ? ($0 as! AXUIElement) : nil }
    }
    guard onTab,let source=CGEventSource(stateID:.hidSystemState),
          let down=CGEvent(mouseEventSource:source,mouseType:.leftMouseDown,mouseCursorPosition:point,mouseButton:.left),
          let up=CGEvent(mouseEventSource:source,mouseType:.leftMouseUp,mouseCursorPosition:point,mouseButton:.left)
    else { return "tab_not_under_pointer" }
    down.post(tap:.cghidEventTap);usleep(60_000);up.post(tap:.cghidEventTap)
    _ = done()
    return nil
}
