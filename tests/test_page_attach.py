"""Registered files for a page's file control: registration, pinning, dispatch shape."""
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest import mock

from haejo import page_attach
from haejo.flow import Flow, replay

ROOT = Path(__file__).resolve().parents[1]


class RegistrationTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory(prefix='haejo-attach-')
        self.addCleanup(self.folder.cleanup)
        self.root = Path(self.folder.name) / 'state'
        self.files = Path(os.path.realpath(self.folder.name)) / 'files'
        self.files.mkdir()
        self.a = self.files / 'a.txt'
        self.b = self.files / 'b.bin'
        self.a.write_bytes(b'alpha')
        self.b.write_bytes(bytes(range(256)))

    def test_registration_pins_name_size_and_sha256(self):
        entry = page_attach.register('cv', [str(self.a), str(self.b)], self.root)
        self.assertEqual([f['filename'] for f in entry['files']], ['a.txt', 'b.bin'])
        self.assertEqual(entry['files'][0]['sha256'], hashlib.sha256(b'alpha').hexdigest())
        self.assertEqual(entry['files'][1]['size_bytes'], 256)
        self.assertEqual(entry['attachment_digest'], page_attach.manifest_digest(entry['files']))
        self.assertEqual(page_attach.registration('cv', self.root), entry)
        registry = self.root / page_attach.REGISTRY_NAME
        self.assertEqual(stat.S_IMODE(registry.stat().st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(self.root.stat().st_mode), 0o700)

    def test_the_same_bytes_under_another_name_keep_the_digest(self):
        first = page_attach.register('one', [str(self.a)], self.root)
        second = page_attach.register('two', [str(self.a)], self.root)
        self.assertEqual(first['attachment_digest'], second['attachment_digest'])
        self.a.write_bytes(b'beta!')
        third = page_attach.register('one', [str(self.a)], self.root)
        self.assertNotEqual(first['attachment_digest'], third['attachment_digest'])

    def test_registrations_that_cannot_be_made_name_why(self):
        other = Path(os.path.realpath(self.folder.name)) / 'other'
        other.mkdir()
        (other / 'c.txt').write_bytes(b'c')
        for name, paths, code in (
                ('bad name', [str(self.a)], 'invalid_scope'),
                ('cv', [], 'one_to_sixteen_files'),
                ('cv', ['relative.txt'], 'absolute_path_required'),
                ('cv', [str(self.files)], 'readable_file_required'),
                ('cv', [str(self.files / 'missing')], 'readable_file_required'),
                ('cv', [str(self.a), str(other / 'c.txt')], 'files_share_one_folder'),
                ('cv', [str(self.a), str(self.a)], 'file_listed_twice')):
            with self.subTest(code=code):
                with self.assertRaises(page_attach.AttachmentRefused) as refused:
                    page_attach.register(name, paths, self.root)
                self.assertEqual(str(refused.exception), code)
        self.assertIsNone(page_attach.registration('cv', self.root))

    def test_a_symlinked_path_is_registered_as_the_file_it_names(self):
        link = self.files / 'link.txt'
        link.symlink_to(self.a)
        entry = page_attach.register('cv', [str(link)], self.root)
        self.assertEqual(entry['files'][0]['path'], str(self.a))

    def test_helper_action_carries_the_pinned_paths_and_digests(self):
        entry = page_attach.register('cv', [str(self.a), str(self.b)], self.root)
        action, problem = page_attach.helper_action(
            {'name': 'attach_files', 'element_index': 7, 'scope': 'cv'}, self.root)
        self.assertIsNone(problem)
        self.assertEqual(action, {'name': 'choose_files', 'element_index': 7, 'files': [
            {'path': str(self.a), 'sha256': entry['files'][0]['sha256']},
            {'path': str(self.b), 'sha256': entry['files'][1]['sha256']}]})
        pinned, problem = page_attach.helper_action(
            {'name': 'attach_files', 'element_index': 7, 'scope': 'cv',
             'attachment_digest': entry['attachment_digest']}, self.root)
        self.assertIsNone(problem)
        self.assertEqual(pinned, action)

    def test_changed_bytes_are_refused_before_anything_is_pressed(self):
        page_attach.register('cv', [str(self.a)], self.root)
        self.a.write_bytes(b'ALPHA')   # same size, other bytes
        action, problem = page_attach.helper_action(
            {'name': 'attach_files', 'element_index': 0, 'scope': 'cv'}, self.root)
        self.assertIsNone(action)
        self.assertEqual((problem['error'], problem['effect'], problem['filename']),
                         ('attachment_changed', 'not_started', 'a.txt'))
        self.a.unlink()
        _, problem = page_attach.helper_action(
            {'name': 'attach_files', 'element_index': 0, 'scope': 'cv'}, self.root)
        self.assertEqual(problem['error'], 'attachment_changed')

    def test_missing_registration_other_digest_and_malformed_actions(self):
        page_attach.register('cv', [str(self.a)], self.root)
        cases = (
            ({'name': 'attach_files', 'element_index': 0, 'scope': 'none'}, 'attachment_not_registered'),
            ({'name': 'attach_files', 'element_index': 0, 'scope': 'cv', 'attachment_digest': '0' * 64},
             'attachment_digest_mismatch'),
            ({'name': 'attach_files', 'element_index': 0, 'scope': 'cv', 'path': str(self.a)}, 'invalid_action'),
            ({'name': 'attach_files', 'element_index': True, 'scope': 'cv'}, 'invalid_action'),
            ({'name': 'attach_files', 'element_index': 0}, 'invalid_action'),
            ({'name': 'attach_files', 'element_index': 0, 'scope': '../cv'}, 'invalid_action'),
            ({'name': 'click', 'element_index': 0, 'scope': 'cv'}, 'invalid_action'))
        for action, code in cases:
            with self.subTest(code=code, action=action):
                translated, problem = page_attach.helper_action(action, self.root)
                self.assertIsNone(translated)
                self.assertEqual((problem['error'], problem['effect']), (code, 'not_started'))

    def test_a_registry_edited_by_hand_is_not_trusted(self):
        entry = page_attach.register('cv', [str(self.a)], self.root)
        registry = self.root / page_attach.REGISTRY_NAME
        value = json.loads(registry.read_text())
        value['scopes']['cv']['files'][0]['sha256'] = hashlib.sha256(b'other').hexdigest()
        registry.write_text(json.dumps(value))
        self.assertIsNone(page_attach.registration('cv', self.root))
        value['scopes']['cv'] = entry
        registry.write_text(json.dumps(value))
        self.assertEqual(page_attach.registration('cv', self.root), entry)

    def test_forget_and_command_line(self):
        def run(*argv):
            out = io.StringIO()
            with redirect_stdout(out):
                code = page_attach.main(list(argv), root=self.root)
            return code, out.getvalue()
        code, text = run('cv', str(self.a), str(self.b))
        reply = json.loads(text)
        self.assertEqual(code, 0)
        self.assertEqual(reply['step'], {'action': 'attach_files', 'params': {'scope': 'cv'}})
        self.assertEqual([f['filename'] for f in reply['files']], ['a.txt', 'b.bin'])
        self.assertNotIn(str(self.files), text)   # the listing names files, not folders
        code, text = run('--list')
        self.assertEqual([r['scope'] for r in json.loads(text)['registrations']], ['cv'])
        code, text = run('other', str(self.files / 'missing'))
        self.assertEqual((code, json.loads(text)), (1, {'ok': False, 'error': 'readable_file_required'}))
        self.assertEqual(run('--forget', 'cv')[0], 0)
        self.assertEqual(run('--forget', 'cv')[0], 1)
        self.assertEqual(run('--list')[1].strip(), json.dumps({'ok': True, 'registrations': []}))
        self.assertEqual(run('--help')[0], 0)
        self.assertEqual(run('cv')[0], 2)

    def test_params_shape(self):
        ok = page_attach.params_valid
        self.assertTrue(ok({'scope': 'cv'}))
        self.assertTrue(ok({'scope': 'cv', 'attachment_digest': 'a' * 64}))
        for bad in ({}, {'scope': ''}, {'scope': 'cv', 'path': '/x'}, {'scope': 'cv', 'attachment_digest': 'A' * 64},
                    {'scope': 3}, {'attachment_digest': 'a' * 64}, None):
            self.assertFalse(ok(bad), bad)


class DriverTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory(prefix='haejo-attach-')
        self.addCleanup(self.folder.cleanup)
        self.root = Path(self.folder.name) / 'state'
        self.file = Path(os.path.realpath(self.folder.name)) / 'cv.pdf'
        self.file.write_bytes(b'%PDF-owned')
        patch = mock.patch('haejo.preferences.product_directory', return_value=self.root)
        patch.start()
        self.addCleanup(patch.stop)
        self.entry = page_attach.register('cv', [str(self.file)])

    def driver(self, capabilities):
        from haejo.helper import HelperDriver
        driver = HelperDriver.__new__(HelperDriver)
        driver.capabilities = set(capabilities)
        driver._last_action_at = 0.0
        driver.sent = []
        def send(message):
            driver.sent.append(message)
            return {'type': 'acted', 'action': 'choose_files', 'route': 'ax_brief_front'}
        driver._send = send
        return driver

    def test_the_helper_receives_choose_files_with_the_registered_bytes(self):
        driver = self.driver({'action.choose_files'})
        reply = driver.act('o1', 'com.apple.Safari', {'name': 'attach_files', 'element_index': 4, 'scope': 'cv'})
        self.assertEqual(reply['route'], 'ax_brief_front')
        self.assertEqual(driver.sent, [{'type': 'act', 'obs_id': 'o1', 'target': 'com.apple.Safari', 'action': {
            'name': 'choose_files', 'element_index': 4,
            'files': [{'path': str(self.file), 'sha256': hashlib.sha256(b'%PDF-owned').hexdigest()}]}}])

    def test_nothing_is_sent_for_changed_bytes_or_an_older_helper(self):
        old = self.driver(set())
        reply = old.act('o1', 'com.apple.Safari', {'name': 'attach_files', 'element_index': 4, 'scope': 'cv'})
        self.assertEqual((reply['error'], reply['effect'], old.sent), ('attach_unavailable', 'not_started', []))
        driver = self.driver({'action.choose_files'})
        self.file.write_bytes(b'%PDF-other')
        reply = driver.act('o1', 'com.apple.Safari', {'name': 'attach_files', 'element_index': 4, 'scope': 'cv'})
        self.assertEqual((reply['error'], reply['effect'], driver.sent), ('attachment_changed', 'not_started', []))


class FakeDriver:
    def __init__(self, capabilities=('action.choose_files',), reply=None):
        self.capabilities = frozenset(capabilities)
        self.acts = []
        self.reply = reply or {'type': 'acted', 'action': 'choose_files', 'route': 'ax_brief_front',
                               'took_front': True, 'front_seconds': 0.9, 'front_restored': True, 'real_keys': 0,
                               'control_label': 'cv.pdf', 'control_names_files': True,
                               'files': [{'filename': 'cv.pdf', 'sha256': 'a' * 64}], 'steps': []}

    def identity(self, target):
        return target

    def observe(self, target, mode='tree_full', **kwargs):
        label = 'cv.pdf' if self.acts and self.reply.get('type') == 'acted' else 'no file selected'
        return {'type': 'observation', 'obs_id': f'o{len(self.acts)}', 'target': target,
                'tree': f'0 Window  Title: "Form"\n  1 WebArea  Description: "Form"\n    2 Button  Title: {label}'}

    def wait_until(self, target, predicate, **kwargs):
        seen = self.observe(target)
        return seen if predicate(seen['tree']) else {'type': 'timeout', 'last_obs': seen}

    def act(self, obs_id, target, action, **kwargs):
        self.acts.append(action)
        return dict(self.reply)


def attach_flow(params):
    return Flow.from_json(json.dumps({
        'schema': 2, 'name': 'attach', 'target': 'com.apple.Safari',
        'safety_defaults': {'effects': ['write_ephemeral'], 'reversibility': 'reversible',
                            'resource': {'object_type': 'web form', 'scope': 'entry'}},
        'steps': [{'action': 'attach_files', 'selector': {'role': 'Button', 'title': 'no file selected'},
                   'params': params,
                   'postcondition': {'field': {'role': 'Button', 'title': 'cv.pdf'},
                                     'attribute': 'Title', 'equals': 'cv.pdf'}}]}))


class FlowTests(unittest.TestCase):
    def test_a_step_names_a_registration_and_the_event_reports_the_route(self):
        driver = FakeDriver()
        result = replay(driver, attach_flow({'scope': 'cv'}))
        self.assertTrue(result.ok, result.log)
        self.assertEqual(driver.acts, [{'name': 'attach_files', 'element_index': 2, 'scope': 'cv'}])
        self.assertEqual([e['attach'] for e in result.events if 'attach' in e], [{
            'route': 'ax_brief_front', 'took_front': True, 'front_seconds': 0.9, 'front_restored': True,
            'real_keys': 0, 'control_label': 'cv.pdf', 'control_names_files': True, 'steps': []}])

    def test_the_page_decides_success_not_the_reply(self):
        # The helper says acted but the page still shows no file: the step fails.
        class Unchanged(FakeDriver):
            def observe(self, target, mode='tree_full', **kwargs):
                return {'type': 'observation', 'obs_id': 'o', 'target': target,
                        'tree': '0 Window  Title: "Form"\n  1 Button  Title: no file selected'}
        result = replay(Unchanged(), attach_flow({'scope': 'cv'}))
        self.assertFalse(result.ok)

    def test_a_driver_without_the_route_or_a_step_with_paths_is_refused_before_input(self):
        driver = FakeDriver(capabilities=())
        result = replay(driver, attach_flow({'scope': 'cv'}))
        self.assertFalse(result.ok)
        self.assertEqual((result.log[-1]['error'], result.log[-1]['effect'], driver.acts),
                         ('attach_contract_required', 'not_started', []))
        with self.assertRaises(Exception):
            attach_flow({'scope': 'cv', 'path': '/etc/hosts'})

    def test_a_refusal_from_the_helper_stops_the_flow_with_its_steps(self):
        driver = FakeDriver(reply={'type': 'error', 'error': 'files_not_selectable', 'effect': 'not_started',
                                   'panel_closed': True, 'files_attached': False, 'steps': []})
        result = replay(driver, attach_flow({'scope': 'cv'}))
        self.assertFalse(result.ok)
        self.assertIn('files_not_selectable', json.dumps(result.log[-1], ensure_ascii=False, default=str))

    def test_attaching_is_a_form_edit(self):
        from haejo.safety import classify, effects_of
        action = {'name': 'attach_files', 'scope': 'cv'}
        self.assertEqual(effects_of(action, '2 Button  Title: Upload resume')[0], {'write_ephemeral'})
        self.assertEqual(classify(action, '2 Button  Title: Upload resume')[0], 'none')

    def test_help_does_not_register_anything(self):
        from haejo.command_help import command_help
        self.assertIsNone(command_help('attach', ['--help']))   # the command prints its own usage


@unittest.skipUnless(sys.platform == 'darwin' and shutil.which('xcrun'), 'macOS Swift required')
class SwiftTests(unittest.TestCase):
    def build(self, source, name):
        folder = tempfile.TemporaryDirectory(prefix='haejo-swift-attach-')
        self.addCleanup(folder.cleanup)
        main = Path(folder.name) / 'main.swift'
        binary = Path(folder.name) / 'check'
        main.write_text(source)
        built = subprocess.run(['xcrun', 'swiftc', str(main), '-o', str(binary)],
                               capture_output=True, text=True, timeout=180)
        self.assertEqual(built.returncode, 0, built.stderr)
        ran = subprocess.run([str(binary), folder.name], capture_output=True, text=True, timeout=20)
        self.assertEqual(ran.returncode, 0, ran.stderr)
        self.assertEqual(ran.stdout.strip(), name)

    def test_launcher_forwards_only_well_formed_registered_files(self):
        source = (ROOT / 'launcher/haejo.swift').read_text()
        protocol = source[source.index('let allowedTypes:'):source.index('// MARK: - Socket plumbing')]
        protocol += source[source.index('@Sendable func modelTimeout('):source.index('enum ModelProcessError:')]
        harness = '''
let digest = String(repeating: "a", count: 64)
func request(_ files: Any, extra: [String: Any] = [:]) -> [String: Any] {
    var action: [String: Any] = ["name": "choose_files", "element_index": 3, "files": files]
    for (key, value) in extra { action[key] = value }
    return ["type": "act", "target": "com.apple.Safari", "obs_id": "o1", "action": action]
}
precondition(vetted(request([["path": "/Users/me/cv.pdf", "sha256": digest]])) == nil)
precondition(vetted(request(Array(repeating: ["path": "/Users/me/cv.pdf", "sha256": digest], count: 16))) == nil)
let refused: [Any] = [
    [] as [[String: Any]],
    Array(repeating: ["path": "/Users/me/cv.pdf", "sha256": digest], count: 17),
    [["path": "cv.pdf", "sha256": digest]],
    [["path": "/Users/me/cv.pdf", "sha256": String(repeating: "A", count: 64)]],
    [["path": "/Users/me/cv.pdf", "sha256": "abc"]],
    [["path": "/Users/me/cv.pdf"]],
    [["path": "/Users/me/cv.pdf", "sha256": digest, "name": "other"]],
    [["path": "/Users/me/a\\u{0}b", "sha256": digest]],
    "/Users/me/cv.pdf",
]
for files in refused { precondition(vetted(request(files)) != nil, "accepted \\(files)") }
precondition(vetted(request([["path": "/Users/me/cv.pdf", "sha256": digest]], extra: ["path": ["File"]])) != nil)
var missing = request([["path": "/Users/me/cv.pdf", "sha256": digest]])
missing["action"] = ["name": "choose_files", "files": [["path": "/Users/me/cv.pdf", "sha256": digest]]]
precondition(vetted(missing) != nil)
var other = request([["path": "/Users/me/cv.pdf", "sha256": digest]])
other["action"] = ["name": "click", "element_index": 3, "files": [["path": "/Users/me/cv.pdf", "sha256": digest]]]
precondition(vetted(other) != nil)
print("SWIFT_CHOOSE_FILES_PROTOCOL_PASS")
'''
        self.build('import Foundation\nimport CoreFoundation\n' + protocol + harness,
                   'SWIFT_CHOOSE_FILES_PROTOCOL_PASS')

    def test_helper_pins_the_registered_bytes_and_one_folder(self):
        source = (ROOT / 'helper/OpenPanelUpload.swift').read_text()
        stubs = '''
final class AbortState { var isStopped = false }
let abortState = AbortState()
func attr(_ el: AXUIElement, _ name: String) -> CFTypeRef? { nil }
func str(_ el: AXUIElement, _ name: String) -> String? { nil }
func isFrontmost(pid p: pid_t) -> Bool { false }
func nativeFrontmostProcessPID() -> pid_t? { nil }
func returnScreen(to previous: pid_t) -> Bool { false }
'''
        harness = '''
let folder = URL(fileURLWithPath: CommandLine.arguments[1]).resolvingSymlinksInPath()
let a = folder.appendingPathComponent("a.txt"), b = folder.appendingPathComponent("b.txt")
try! Data("alpha".utf8).write(to: a)
try! Data().write(to: b)
let alpha = "8ed3f6ad685b959ead7022518e1af76cd816f8e8ec7ccdda1ed4018e8f2223f8"
let empty = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
precondition(openPanelFileDigest(a.path) == alpha)
precondition(openPanelFileDigest(b.path) == empty)
precondition(openPanelFileDigest(folder.appendingPathComponent("missing").path) == nil)
let good = openPanelParseFiles([["path": a.path, "sha256": alpha], ["path": b.path, "sha256": empty]])
precondition(good.problem == nil && good.files.map { $0.name } == ["a.txt", "b.txt"])
precondition(good.files[0].directory == folder.path && good.files[0].path == a.path)
let sub = folder.appendingPathComponent("sub")
try! FileManager.default.createDirectory(at: sub, withIntermediateDirectories: true)
let c = sub.appendingPathComponent("c.txt")
try! Data("c".utf8).write(to: c)
let refused: [Any?] = [
    nil, [] as [[String: Any]], [["path": a.path]], [["path": "a.txt", "sha256": alpha]],
    [["path": a.path, "sha256": alpha.uppercased()]], [["path": sub.path, "sha256": alpha]],
    [["path": folder.appendingPathComponent("missing").path, "sha256": alpha]],
    [["path": a.path, "sha256": alpha], ["path": c.path, "sha256": alpha]],
    [["path": a.path, "sha256": alpha], ["path": a.path, "sha256": alpha]],
]
for files in refused { precondition(openPanelParseFiles(files).problem != nil, "accepted \\(String(describing: files))") }
// A registered digest that the bytes no longer have is what chooseFiles refuses on.
try! Data("ALPHA".utf8).write(to: a)
precondition(openPanelFileDigest(a.path) != alpha)
print("SWIFT_OPEN_PANEL_FILES_PASS")
'''
        self.build(source + stubs + harness, 'SWIFT_OPEN_PANEL_FILES_PASS')

    def test_the_helper_build_and_capability_include_the_route(self):
        self.assertIn('"OpenPanelUpload.swift"', (ROOT / 'helper/build.sh').read_text())
        helper = (ROOT / 'helper/HaejoHelper.swift').read_text()
        self.assertIn('"action.choose_files"', helper)
        self.assertIn('case "choose_files":', helper)


if __name__ == '__main__':
    unittest.main()
