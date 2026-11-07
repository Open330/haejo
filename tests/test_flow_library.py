"""Saved-flow library: `tacto flows` data layer and the app's Flow page."""
from pathlib import Path
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout

from tacto import flow_library as L
from tacto.store import FlowStore

ROOT = Path(__file__).resolve().parents[1]
KOREAN = '계산기로_곱하기_테스트'


def seed(folder, names=None):
    """Write built-in recipes as saved flows (flows/*.json is not tracked)."""
    from tacto.library import builders
    folder = Path(folder); folder.mkdir(parents=True, exist_ok=True)
    built = builders()
    for name in names or sorted(built):
        (folder / f'{name}.json').write_text(built[name]().to_json())
    return built


class FlowLibraryTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.mkdtemp()
        self.store = FlowStore(os.path.join(self.folder, 'lib'))
        seed(self.store.path, ['calc_arith', 'textedit_save_as'])
        raw = json.loads(Path(self.store.path, 'calc_arith.json').read_text()); raw['name'] = KOREAN
        Path(self.store.path, f'{KOREAN}.json').write_text(json.dumps(raw, ensure_ascii=False))

    def tearDown(self):
        shutil.rmtree(self.folder)

    def test_lists_every_builtin_recipe_and_reports_damage(self):
        source = Path(self.folder, 'built')
        built = seed(source)
        for f in source.glob('*.json'):
            L.import_file(str(f), store=self.store, force=True)
        Path(self.store.path, 'broken.json').write_text('{"x":')
        flows = {e['name']: e for e in L.list_flows(self.store)['flows']}
        self.assertEqual(set(built) | {KOREAN, 'broken'}, set(flows))
        self.assertEqual('corrupt_flow', flows['broken']['error'])
        self.assertTrue(all(e['ok'] for n, e in flows.items() if n != 'broken'))
        self.assertTrue(flows['calc_arith']['shadowed_by_builtin'])
        self.assertFalse(flows[KOREAN]['shadowed_by_builtin'])

    def test_lasting_steps_follow_the_run_policy(self):
        save_as = L.detail('textedit_save_as', self.store)['flow']
        self.assertEqual(1, save_as['consequential_steps'])
        self.assertEqual(['confirm'], [s['policy'] for s in save_as['steps'] if s['consequential']])
        # Calculator AC is a reversible ephemeral delete: the run does not stop for it.
        calc = L.detail('calc_arith', self.store)['flow']
        self.assertEqual(0, calc['consequential_steps'])
        self.assertEqual('계산기를 지웁니다', calc['steps'][0]['label'])

    def test_set_keeps_unmodelled_fields_and_types(self):
        path = Path(self.store.path, 'calc_arith.json')
        raw = json.loads(path.read_text()); raw['x_note'] = 'kept'; raw['params']['n'] = 3
        path.write_text(json.dumps(raw))
        result = L.set_fields('calc_arith', params={'a': '99', 'n': '7', 'b': ''},
                              intents=['계산기로 {{a}} 곱하기 {{b}}', '계산기로 {{a}} 곱하기 {{b}}'], store=self.store)
        saved = json.loads(path.read_text())
        self.assertEqual('kept', saved['x_note'])
        self.assertEqual(('99', 7, None), (saved['params']['a'], saved['params']['n'], saved['params']['b']))
        self.assertEqual(['계산기로 {{a}} 곱하기 {{b}}'], result['flow']['intents'])

    def test_edits_that_name_nothing_are_refused_unchanged(self):
        before = Path(self.store.path, 'calc_arith.json').read_text()
        for kwargs, code in (({'params': {'zz': '1'}}, 'unknown_parameter'),
                             ({'intents': ['{{nope}} 해줘']}, 'invalid_intents')):
            with self.assertRaises(L.LibraryError) as caught:
                L.set_fields('calc_arith', store=self.store, **kwargs)
            self.assertEqual(code, caught.exception.code)
        self.assertEqual(before, Path(self.store.path, 'calc_arith.json').read_text())

    def test_rename_remove_and_names(self):
        L.rename('calc_arith', 'calc_mul2', self.store)
        self.assertEqual('calc_mul2', json.loads(Path(self.store.path, 'calc_mul2.json').read_text())['name'])
        self.assertFalse(Path(self.store.path, 'calc_arith.json').exists())
        for bad in ('bad/name', '../x', '', 'a' * 81, 'a.b'):
            with self.assertRaises(L.LibraryError):
                L.rename('calc_mul2', bad, self.store)
        with self.assertRaises(L.LibraryError) as caught:
            L.rename('calc_mul2', 'textedit_save_as', self.store)
        self.assertEqual('flow_exists', caught.exception.code)
        L.remove('calc_mul2', self.store)
        self.assertFalse(Path(self.store.path, 'calc_mul2.json').exists())

    def test_bundled_flows_are_read_only(self):
        bundled = os.path.join(self.folder, 'bundled')
        seed(bundled, ['calendar_today'])
        store = FlowStore(self.store.path, builtin_path=bundled)
        entry = L.detail('calendar_today', store)['flow']
        self.assertEqual(('builtin', False), (entry['source'], entry['editable']))
        for call in (lambda: L.remove('calendar_today', store),
                     lambda: L.rename('calendar_today', 'x', store),
                     lambda: L.set_fields('calendar_today', intents=[], store=store)):
            with self.assertRaises(L.LibraryError) as caught:
                call()
            self.assertEqual('flow_read_only', caught.exception.code)

    def test_save_refuses_overwrite_and_invalid_files(self):
        source = Path(self.folder, 'mine.json')
        seed(self.folder, ['finder_open_folder'])
        raw = json.loads(Path(self.folder, 'finder_open_folder.json').read_text()); raw['name'] = 'mine'
        source.write_text(json.dumps(raw))
        self.assertEqual('mine', L.import_file(str(source), store=self.store)['flow']['name'])
        with self.assertRaises(L.LibraryError) as caught:
            L.import_file(str(source), store=self.store)
        self.assertEqual('flow_exists', caught.exception.code)
        L.import_file(str(source), name='other', store=self.store)
        Path(self.folder, 'bad.json').write_text('{"name": "bad", "steps": "no"}')
        with self.assertRaises(L.LibraryError) as caught:
            L.import_file(str(Path(self.folder, 'bad.json')), store=self.store)
        self.assertEqual('invalid_flow', caught.exception.code)
        self.assertFalse(Path(self.store.path, 'bad.json').exists())

    def test_json_cli_reports_errors_as_codes(self):
        import tacto.store as store_module
        original = store_module.default_directory
        store_module.default_directory = lambda: self.store.path
        try:
            out = io.StringIO()
            with redirect_stdout(out):
                code = L.main(['show', 'missing', '--json'])
            self.assertEqual((1, 'flow_not_found'), (code, json.loads(out.getvalue())['error']))
            out = io.StringIO()
            with redirect_stdout(out):
                self.assertEqual(0, L.main(['--json']))
            self.assertEqual(3, len(json.loads(out.getvalue())['flows']))
        finally:
            store_module.default_directory = original


@unittest.skipUnless(sys.platform == 'darwin' and shutil.which('swiftc'), 'AppKit required')
class FlowPageTests(unittest.TestCase):
    def test_page_drives_the_real_cli(self):
        with tempfile.TemporaryDirectory() as folder:
            folder = Path(folder); lib = folder / 'lib'; (folder / 'product/Logs').mkdir(parents=True)
            seed(lib, ['calc_arith', 'textedit_save_as', 'finder_open_folder'])
            (lib / 'broken_one.json').write_text('{"broken": ')
            (folder / 'run.py').write_text(
                'import sys\nsys.path.insert(0, %r)\nimport tacto.store as s\n'
                's.default_directory = lambda: %r\ns.builtin_directory = lambda: None\n'
                'from tacto.flow_library import main\nsys.exit(main(sys.argv[1:]))\n' % (str(ROOT), str(lib)))
            (folder / 'ActivityCenter.swift').write_text((ROOT / 'setup/ActivityCenter.swift').read_text().replace('private ', ''))
            (folder / 'main.swift').write_text(r'''
import AppKit
let app=NSApplication.shared; app.setActivationPolicy(.prohibited)
let W=CommandLine.arguments[1], python=CommandLine.arguments[2]
var replays:[[String]]=[]
let page=FlowLibraryPage(runner:{ args in
  if args.first == "replay" { replays.append(args); return (0, Data("  done — 결과: 418\n".utf8)) }
  let p=Process(); p.executableURL=URL(fileURLWithPath:python); p.arguments=["-I",W+"/run.py"]+Array(args.dropFirst())
  let o=Pipe(); p.standardOutput=o; try p.run(); let d=o.fileHandleForReading.readDataToEndOfFile(); p.waitUntilExit(); return (p.terminationStatus,d)
})
func pump(_ until:()->Bool){ let end=Date().addingTimeInterval(30); while !until() && Date()<end { RunLoop.main.run(until:Date().addingTimeInterval(0.05)) } }
let center=ActivityCenter(store:ActivityStore(root:URL(fileURLWithPath:W+"/product")),refreshAutomatically:true,flowPage:page)
center.presentFlows()
pump { page.current != nil && !page.busy }
assert(page.flows.count==4 && page.flows.last!.name=="broken_one" && !page.flows.last!.ok)
assert(page.split.subviews[0].frame.width>=240)
page.search.stringValue="save_as"; page.applyFilter(); pump { page.current?.name=="textedit_save_as" && !page.busy }
assert(page.current!.consequential==1 && page.current!.shadowed)
page.search.stringValue="calc_arith"; page.applyFilter(); pump { page.current?.name=="calc_arith" && !page.busy }
page.paramFields["a"]!.stringValue="99"
assert(page.runArguments(confirmed:false)==["replay","calc_arith","-p","a=99","-p","b=34","-p","op=*","--helper"])
page.runFlow(); pump { !page.running && page.status.stringValue.contains("완료") }
assert(replays.count==1 && page.status.stringValue.contains("418"))
page.paramFields["b"]!.stringValue=""; page.runFlow(); assert(page.status.stringValue.contains("b") && replays.count==1)
page.paramFields["b"]!.stringValue="34"
page.intentsView.string="계산기로 {{a}} 곱하기 {{b}}\n"
page.saveFields(); pump { page.status.stringValue.contains("저장했어요") && !page.busy }
assert(page.current!.params.first{ $0.0=="a" }!.1=="99" && page.current!.intents==["계산기로 {{a}} 곱하기 {{b}}"])
page.intentsView.string="{{nope}} 해줘"; page.saveFields(); pump { page.status.stringValue.contains("입력값이어야") && !page.busy }
page.rename("calc_arith", to:"calc_mul2"); pump { page.current?.name=="calc_mul2" && !page.busy }
assert(FileManager.default.fileExists(atPath:W+"/lib/calc_mul2.json") && !FileManager.default.fileExists(atPath:W+"/lib/calc_arith.json"))
page.rename("calc_mul2", to:"bad/name"); pump { page.status.stringValue.contains("이름에는") && !page.busy }
center.presentFlows(); page.remove("calc_mul2"); pump { page.status.stringValue.contains("삭제했어요") && !page.busy && page.flows.count==3 }
assert(!FileManager.default.fileExists(atPath:W+"/lib/calc_mul2.json"))
try! center.snapshot(to:URL(fileURLWithPath:W+"/shot"),flowsPage:true)
print("flow-page-pass")
''')
            built = subprocess.run(['swiftc', 'ActivityCenter.swift', 'main.swift', '-o', 'check'], cwd=folder, capture_output=True, text=True, timeout=180)
            self.assertEqual(0, built.returncode, built.stderr)
            result = subprocess.run([str(folder / 'check'), str(folder), sys.executable], capture_output=True, text=True, timeout=120)
            self.assertEqual(0, result.returncode, result.stderr + result.stdout)
            self.assertIn('flow-page-pass', result.stdout)
            self.assertTrue((folder / 'shot/app.png').is_file())


if __name__ == '__main__':
    unittest.main()
