"""Shared memory persistence, conflict protection and native editor integration."""
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout, redirect_stderr
from concurrent.futures import ThreadPoolExecutor

from haejo.memory import MemoryStore, main, MAX_BYTES

ROOT = Path(__file__).resolve().parents[1]


class MemoryTests(unittest.TestCase):
    def test_read_does_not_create_and_writes_are_private(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = MemoryStore(Path(tmp) / 'Memory')
            empty = store.read()
            self.assertFalse(store.root.exists())
            saved = store.replace('다운로드: ~/Downloads\n한국어로 답변', empty['revision'])
            self.assertEqual(saved, MemoryStore(store.root).read())
            if os.name != 'nt':
                self.assertEqual(0o600, store.path.stat().st_mode & 0o777)
                self.assertEqual(0o700, store.root.stat().st_mode & 0o777)
            with self.assertRaises(ValueError):
                store.replace('stale', empty['revision'])
            self.assertEqual('', store.replace('', saved['revision'])['text'])

    def test_parallel_writers_only_one_wins(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = MemoryStore(Path(tmp) / 'Memory')
            revision = store.read()['revision']
            def write(text):
                try:
                    store.replace(text, revision)
                    return True
                except ValueError:
                    return False
            with ThreadPoolExecutor(2) as pool:
                self.assertEqual([False, True], sorted(pool.map(write, ['one', 'two'])))
            self.assertIn(store.read()['text'], ['one', 'two'])

    def test_bad_storage_and_oversize_preserve_content(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = MemoryStore(Path(tmp) / 'Memory')
            saved = store.replace('valid', store.read()['revision'])
            for bad in ['가' * MAX_BYTES, 'bad\0text']:
                with self.assertRaises(ValueError):
                    store.replace(bad, saved['revision'])
            self.assertEqual('valid', store.read()['text'])
            store.path.unlink()
            other = Path(tmp) / 'other'; other.write_text('private')
            store.path.symlink_to(other)
            with self.assertRaises(OSError):
                store.replace('overwrite', saved['revision'])
            self.assertEqual('private', other.read_text())

    def test_cli_round_trip_and_conflict(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = MemoryStore(Path(tmp) / 'Memory')
            revision = store.read()['revision']
            source = Path(tmp) / 'in.txt'; source.write_text('앱 사용 팁')
            out = io.StringIO()
            with redirect_stdout(out):
                self.assertEqual(0, main(['set', '--file', str(source), '--revision', revision, '--json'], store=store))
            value = json.loads(out.getvalue()); self.assertEqual('앱 사용 팁', value['text'])
            with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                self.assertEqual(2, main(['clear', '--revision', revision, '--json'], store=store))
                self.assertEqual(0, main(['clear', '--revision', value['revision'], '--json'], store=store))


@unittest.skipUnless(sys.platform == 'darwin' and shutil.which('swiftc'), 'AppKit required')
class MemoryPageTests(unittest.TestCase):
    def test_editor_uses_shared_cli_and_preserves_conflicting_draft(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            (folder/'run.py').write_text('import sys\nsys.path.insert(0, %r)\nfrom haejo.memory import main, MemoryStore\nsys.exit(main(sys.argv[1:], store=MemoryStore(%r)))\n' % (str(ROOT), str(folder/'Memory')))
            (folder/'ActivityCenter.swift').write_text((ROOT/'setup/ActivityCenter.swift').read_text().replace('private ', ''))
            (folder/'main.swift').write_text(r'''
import AppKit
let app = NSApplication.shared; app.setActivationPolicy(.prohibited)
let folder = CommandLine.arguments[1], python = CommandLine.arguments[2]
let runner: FlowLibraryPage.Runner = { args in
    let p = Process(); p.executableURL = URL(fileURLWithPath:python)
    p.arguments = ["-I",folder+"/run.py"] + Array(args.dropFirst())
    let pipe = Pipe(); p.standardOutput = pipe; p.standardError = pipe
    try p.run(); let data = pipe.fileHandleForReading.readDataToEndOfFile(); p.waitUntilExit()
    return (p.terminationStatus,data)
}
let page = MemoryPage(runner:runner)
let center = ActivityCenter(store:ActivityStore(root:URL(fileURLWithPath:folder+"/product")),refreshAutomatically:true,memoryPage:page)
func pump() { let end=Date().addingTimeInterval(15); while page.busy && Date()<end { RunLoop.main.run(until:Date().addingTimeInterval(0.02)) }; assert(!page.busy) }
center.presentMemory(); pump()
assert(page.editor.string.isEmpty && page.editor.isEditable)
page.editor.string = "매번 한국어로 답변"; page.saveMemory(); pump()
assert(page.status.stringValue.contains("저장했어요"))
let raw = try! runner(["memory","read","--json"])
let current = try! JSONSerialization.jsonObject(with:raw.1) as! [String:Any]
assert(current["text"] as! String == "매번 한국어로 답변")
let source = folder + "/external.txt"
try! "CLI에서 수정한 메모리".write(toFile:source, atomically:true, encoding:.utf8)
let changed = try! runner(["memory","set","--file",source,"--revision",current["revision"] as! String,"--json"])
assert(changed.0 == 0)
let external = try! JSONSerialization.jsonObject(with:changed.1) as! [String:Any]
center.present(settings:true); center.presentMemory(); pump()
assert(page.editor.string == "CLI에서 수정한 메모리")
assert(try! runner(["memory","clear","--revision",external["revision"] as! String,"--json"]).0 == 0)
page.editor.string = "보존할 초안"; page.saveMemory(); pump()
assert(page.status.stringValue.contains("다른 곳에서 변경"))
assert(page.editor.string == "보존할 초안" && page.dirty)
center.present(settings:true); center.presentMemory(); pump()
assert(page.editor.string == "보존할 초안")
page.editor.string = "CLI에서 수정한 메모리"; page.reload(); pump()
assert(page.editor.string.isEmpty)
page.editor.string = "# 선호\n\n한국어로 답변해 주세요.\n저장할 파일은 ~/Downloads에 둡니다."
try! center.snapshot(to:URL(fileURLWithPath:folder+"/snapshot"), memoryPage:true)
print("memory-page-pass")
''')
            result = subprocess.run(['swiftc', 'ActivityCenter.swift', 'main.swift', '-o', 'check'], cwd=folder, capture_output=True, text=True, timeout=180)
            self.assertEqual(0, result.returncode, result.stderr)
            result = subprocess.run([str(folder/'check'), str(folder), sys.executable], capture_output=True, text=True, timeout=90)
            self.assertEqual(0, result.returncode, result.stderr + result.stdout)
            self.assertIn('memory-page-pass', result.stdout)
            self.assertTrue((folder/'snapshot/app.png').is_file())
