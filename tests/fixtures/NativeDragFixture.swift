// Receiving-side witness: all state is updated by AppKit mouse handlers.
import AppKit
final class NonKeyDragPanel:NSPanel {
    override var canBecomeKey:Bool {false}
    override var canBecomeMain:Bool {false}
}
@MainActor final class ResizeRoot:NSView {
    let receipt:URL
    init(frame:NSRect,receipt:URL) {self.receipt=receipt;super.init(frame:frame)}
    required init?(coder:NSCoder) {fatalError()}
    override func acceptsFirstMouse(for event:NSEvent?)->Bool {true}
    override func mouseDown(with event:NSEvent) {
        guard let window else {return}
        let start=window.frame,mouse=window.convertPoint(toScreen:event.locationInWindow)
        var drags=0,ups=0
        while let next=window.nextEvent(matching:[.leftMouseDragged,.leftMouseUp]) {
            if next.type == .leftMouseUp {ups+=1;break}
            let now=window.convertPoint(toScreen:next.locationInWindow)
            let width=max(100,start.width+now.x-mouse.x),height=max(100,start.height+mouse.y-now.y)
            window.setFrame(NSRect(x:start.minX,y:start.maxY-height,width:width,height:height),display:true)
            drags+=1
        }
        if let data=try? JSONSerialization.data(withJSONObject:["downs":1,"drags":drags,"ups":ups]) {
            try? data.write(to:receipt,options:.atomic)
        }
    }
}
@MainActor final class DragCanvas:NSView {
    var events:[[String:Any]]=[]
    let receipt:URL
    init(frame:NSRect,receipt:URL) { self.receipt=receipt;super.init(frame:frame) }
    required init?(coder:NSCoder) { fatalError() }
    override var isFlipped:Bool {true}
    override var acceptsFirstResponder:Bool {true}
    override func acceptsFirstMouse(for event:NSEvent?)->Bool {true}
    override func draw(_ dirty:NSRect) {NSColor.systemBlue.setFill();bounds.fill()}
    func record(_ event:NSEvent,_ kind:String) {
        let point=convert(event.locationInWindow,from:nil)
        events.append(["kind":kind,"x":point.x,"y":point.y,"window":event.windowNumber,
                       "number":event.eventNumber,"pressure":event.pressure,"timestamp":event.timestamp])
        if let data=try? JSONSerialization.data(withJSONObject:events) {try? data.write(to:receipt,options:.atomic)}
    }
    override func mouseDown(with event:NSEvent) {record(event,"down")}
    override func mouseDragged(with event:NSEvent) {record(event,"drag")}
    override func mouseUp(with event:NSEvent) {record(event,"up")}
}
@MainActor final class DragDelegate:NSObject,NSApplicationDelegate {
    var window:NSWindow!
    var slider:NSSlider!
    let root:URL
    init(_ root:URL) {self.root=root}
    func applicationDidFinishLaunching(_ notification:Notification) {
        if CommandLine.arguments.contains("--borderless") {
            window=NonKeyDragPanel(contentRect:NSRect(x:200,y:200,width:480,height:300),
                styleMask:[.borderless,.nonactivatingPanel,.fullSizeContentView],backing:.buffered,defer:false)
            window.hidesOnDeactivate=false
        } else if CommandLine.arguments.contains("--floating") {
            window=NSPanel(contentRect:NSRect(x:200,y:200,width:480,height:300),
                styleMask:[.titled,.closable,.resizable,.utilityWindow,.nonactivatingPanel],backing:.buffered,defer:false)
        } else {
            window=NSWindow(contentRect:NSRect(x:200,y:200,width:480,height:300),styleMask:[.titled,.closable,.resizable],backing:.buffered,defer:false)
        }
        window.title="Haejo Drag Fixture"
        if CommandLine.arguments.contains("--floating") {window.level = .floating}
        window.isReleasedWhenClosed=false
        if CommandLine.arguments.contains("--borderless") {
            window.contentView=ResizeRoot(frame:window.contentView!.frame,receipt:root.appendingPathComponent("resize-events.json"))
        }
        let canvas=DragCanvas(frame:NSRect(x:20,y:100,width:440,height:180),receipt:root.appendingPathComponent("events.json"))
        window.contentView?.addSubview(canvas)
        slider=NSSlider(value:20,minValue:0,maxValue:100,target:self,action:#selector(changed))
        slider.frame=NSRect(x:30,y:30,width:400,height:30);slider.isContinuous=true
        slider.setAccessibilityIdentifier("drag-slider")
        window.contentView?.addSubview(slider)
        if CommandLine.arguments.contains("--interactive-grip") {
            let button=NSButton(title:"Owned action",target:self,action:#selector(gripClicked))
            button.frame=NSRect(x:430,y:0,width:50,height:22)
            window.contentView?.addSubview(button)
        }
        window.orderBack(nil);changed()
        Timer.scheduledTimer(withTimeInterval:0.05,repeats:true) { [weak self] _ in
            MainActor.assumeIsolated {
                guard let self else {return}
                let frame=self.window.frame
                let geometry:[String:Double]=["width":frame.width,"height":frame.height,"x":frame.minX,"y":frame.minY]
                if let data=try? JSONSerialization.data(withJSONObject:geometry) {
                    try? data.write(to:self.root.appendingPathComponent("geometry.json"),options:.atomic)
                }
            }
        }
        Timer.scheduledTimer(withTimeInterval:300,repeats:false) {_ in NSApplication.shared.terminate(nil)}
    }
    @objc func changed() {try? String(slider.doubleValue).write(to:root.appendingPathComponent("slider.txt"),atomically:true,encoding:.utf8)}
    @objc func gripClicked() {try? "clicked".write(to:root.appendingPathComponent("grip-clicked"),atomically:true,encoding:.utf8)}
}
@main enum DragFixture {
    @MainActor static func main() {
        let app=NSApplication.shared;app.setActivationPolicy(.accessory)
        let delegate=DragDelegate(URL(fileURLWithPath:CommandLine.arguments[1]));app.delegate=delegate
        app.run();withExtendedLifetime(delegate) {}
    }
}
