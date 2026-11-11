"""Run the helper's clipboard snapshot on items with unreadable types."""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(sys.platform == 'darwin', 'AppKit pasteboard items')
class ClipboardSnapshotSwift(unittest.TestCase):
    def test_unreadable_types_are_left_out_and_empty_items_refused(self):
        source = (ROOT / 'helper/HaejoHelper.swift').read_text()
        snapshot = source[source.index('func clipboardSnapshot('):source.index('// Swift String == uses canonical')]
        code = 'import AppKit\n' + snapshot + r'''
// Provides nothing, like a system conversion type or a quit app's promise.
final class Empty:NSObject,NSPasteboardItemDataProvider {
    func pasteboard(_ p:NSPasteboard?,item:NSPasteboardItem,provideDataForType t:NSPasteboard.PasteboardType) {}
}
let empty=Empty()
let utf16=NSPasteboard.PasteboardType("public.utf16-external-plain-text")
func webkitCopy()->NSPasteboardItem {
    let item=NSPasteboardItem()
    item.setString("copied text",forType:.string)
    item.setData(Data("<b>copied</b>".utf8),forType:.html)
    item.setDataProvider(empty,forTypes:[utf16])
    return item
}
let onlyEmpty=NSPasteboardItem();onlyEmpty.setDataProvider(empty,forTypes:[utf16])
let big=NSPasteboardItem();big.setData(Data(count:8*1024*1024+1),forType:.tiff)
var out:[String:Any]=[:]
if let saved=clipboardSnapshot([webkitCopy(),webkitCopy()]) {
    out["web"]=saved.map {["types":$0.types.map {$0.rawValue},"text":$0.string(forType:.string) ?? ""]}
}
out["only_unreadable"]=clipboardSnapshot([onlyEmpty]) == nil
out["too_large"]=clipboardSnapshot([big]) == nil
out["empty_list"]=clipboardSnapshot([])?.count ?? -1
print(String(data:try! JSONSerialization.data(withJSONObject:out),encoding:.utf8)!)
'''
        with tempfile.TemporaryDirectory() as directory:
            script = Path(directory) / 'snapshot.swift'
            script.write_text(code)
            run = subprocess.run(['swift', str(script)], capture_output=True, text=True, timeout=90)
        self.assertEqual(0, run.returncode, run.stderr)
        result = json.loads(run.stdout)
        self.assertEqual(2, len(result['web']))
        for item in result['web']:
            self.assertEqual(['public.utf8-plain-text', 'public.html'], item['types'])
            self.assertEqual('copied text', item['text'])
        self.assertTrue(result['only_unreadable'])
        self.assertTrue(result['too_large'])
        self.assertEqual(0, result['empty_list'])


if __name__ == '__main__':
    unittest.main()
