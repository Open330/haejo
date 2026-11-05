"""A save panel showing only the current folder's column (sidebar place).

The helper's actual NativeSavePanelReader against a synthetic AX tree: the
folder comes from the entries' own native URLs, never a label or expected path.
"""
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]

HARNESS = r'''
import Foundation
import ApplicationServices
struct FixtureNode { let element: AXUIElement; var values: [String: AnyObject] }
var nodes: [FixtureNode] = []
func node(_ role: String, parent: AXUIElement? = nil, identifier: String? = nil) -> AXUIElement {
    let element = AXUIElementCreateApplication(pid_t(100000 + nodes.count))
    var values: [String: AnyObject] = ["AXRole": role as NSString, "AXChildren": [] as NSArray]
    if let parent { values["AXParent"] = parent }
    if let identifier { values["AXIdentifier"] = identifier as NSString }
    nodes.append(FixtureNode(element: element, values: values))
    if let parent {
        let index = nodes.firstIndex(where: { CFEqual($0.element, parent) })!
        let children = nodes[index].values["AXChildren"] as! [AXUIElement]
        nodes[index].values["AXChildren"] = (children + [element]) as NSArray
    }
    return element
}
func set(_ element: AXUIElement, _ key: String, _ value: AnyObject) {
    let index = nodes.firstIndex(where: { CFEqual($0.element, element) })!
    nodes[index].values[key] = value
}
let window = node("AXWindow")
let sheet = node("AXSheet", parent: window, identifier: "save-panel")
let group = node("AXGroup", parent: sheet)
let browser = node("AXBrowser", parent: group, identifier: "ColumnView")
let container = node("AXScrollArea", parent: browser)
let column = node("AXScrollArea", parent: container)
let list = node("AXList", parent: column)
set(list, "AXSelectedChildren", [] as NSArray)
var fields: [AXUIElement] = []
func entry(_ url: AnyObject?) {
    let row = node("AXGroup", parent: list)
    let field = node("AXTextField", parent: row)
    if let url { set(field, "AXURL", url) }
    fields.append(field)
}
for name in ["a.rtf", "b%20c.txt", "sub/"] { entry(NSURL(string: "file:///owned/folder/" + name)!) }
let name = node("AXTextField", parent: group, identifier: "saveAsNameTextField")
set(name, "AXValue", "owned.rtf" as NSString)
let format = node("AXPopUpButton", parent: group, identifier: "ContentTypesPopup")
set(format, "AXValue", "Rich Text Document" as NSString)
let commit = node("AXButton", parent: group, identifier: "OKButton")
set(commit, "AXEnabled", kCFBooleanTrue)
// The label must never be consulted for the folder.
let whereLabel = node("AXPopUpButton", parent: group, identifier: "where popup")
set(whereLabel, "AXValue", "Elsewhere" as NSString)
var asked: [String] = []
let read: NativeSavePanelReader.AttributeReader = { element, key in
    let value = nodes.first(where: { CFEqual($0.element, element) })!.values[key]
    return value == nil ? (.attributeUnsupported, nil) : (.success, value)
}
let resource: (AnyObject) throws -> NativeSaveDirectoryResource = { raw in
    guard let url = raw as? URL else { throw NativeSavePanelError.unavailable("not a URL") }
    asked.append(url.absoluteString)
    return NativeSaveDirectoryResource(path: url.path, device: 42, inode: 7)
}
let reader = try NativeSavePanelReader(readAttribute: read, directoryResource: resource)
func mustReject(_ label: String, _ operation: () throws -> Void) {
    do { try operation(); fatalError("accepted: " + label) }
    catch NativeSavePanelError.unavailable { }
    catch { fatalError("unexpected failure: " + label) }
}
let witness = try reader.read(window, requireFormat: true)
precondition(witness.directory.path == "/owned/folder", witness.directory.path)
precondition(!asked.isEmpty && Set(asked) == ["file:///owned/folder/"], "\(asked)")  // read() captures twice
precondition(witness.resources.count == 1 && witness.filename == "owned.rtf" && CFEqual(witness.commit, commit))
precondition(reader.budgetUsage["single_column_entries_witnessed"] == 3)
try reader.revalidate(window, witness: witness, requireFormat: true)
// Disagreeing parents, a missing or non-file URL, a textual URL: unavailable.
set(fields[1], "AXURL", NSURL(string: "file:///owned/other/b.txt")!)
mustReject("disagreeing folders") { _ = try reader.read(window) }
set(fields[1], "AXURL", NSURL(string: "https://example.com/b.txt")!)
mustReject("non-file URL") { _ = try reader.read(window) }
set(fields[1], "AXURL", "file:///owned/folder/b.txt" as NSString)
mustReject("textual URL") { _ = try reader.read(window) }
let index = nodes.firstIndex(where: { CFEqual($0.element, fields[1]) })!
nodes[index].values.removeValue(forKey: "AXURL")
mustReject("entry without URL") { _ = try reader.read(window) }
set(fields[1], "AXURL", NSURL(string: "file:///owned/folder/b.txt")!)
_ = try reader.read(window)
// A selected entry in the lone column is not this witness.
let rows = nodes.first(where: { CFEqual($0.element, list) })!.values["AXChildren"] as! [AXUIElement]
set(list, "AXSelectedChildren", [rows[0]] as NSArray)
mustReject("selection present") { _ = try reader.read(window) }
set(list, "AXSelectedChildren", [] as NSArray)
// Only the first 64 entries are read; a later disagreement is outside the sample.
for i in 0..<70 { entry(NSURL(string: "file:///owned/folder/f\(i).txt")!) }
set(fields[fields.count - 1], "AXURL", NSURL(string: "file:///owned/late/x.txt")!)
_ = try reader.read(window)
precondition(reader.budgetUsage["single_column_entries_witnessed"] == 64)
// An empty folder column cannot witness its folder.
set(list, "AXChildren", [] as NSArray)
mustReject("empty column") { _ = try reader.read(window) }
// No columns at all is still unavailable.
set(container, "AXChildren", [] as NSArray)
mustReject("no columns") { _ = try reader.read(window) }
print("SINGLE_COLUMN_PASS")
'''


@unittest.skipUnless(sys.platform == 'darwin' and shutil.which('xcrun'), 'macOS Swift required')
class SingleColumnSavePanelTests(unittest.TestCase):
    def test_single_column_folder_from_entry_urls(self):
        with tempfile.TemporaryDirectory(prefix='tacto-single-column-') as directory:
            source, binary = Path(directory) / 'main.swift', Path(directory) / 'check'
            source.write_text(HARNESS)
            built = subprocess.run(['xcrun', 'swiftc', '-warnings-as-errors', str(source),
                                    str(ROOT / 'helper/SavePanelObservation.swift'), '-o', str(binary)],
                                   capture_output=True, text=True, timeout=120)
            self.assertEqual(0, built.returncode, built.stderr)
            result = subprocess.run([str(binary)], capture_output=True, text=True, timeout=20)
            self.assertEqual(0, result.returncode, result.stderr)
            self.assertEqual('SINGLE_COLUMN_PASS', result.stdout.strip())


if __name__ == '__main__':
    unittest.main()
