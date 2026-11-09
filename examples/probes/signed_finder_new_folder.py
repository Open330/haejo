"""Actual Finder File > New Folder in an owned folder, Finder kept behind.

Run only through the signed evaluator. An owned directory under
~/Library/Caches is opened with the helper's open_folder (LaunchServices,
activates=false); that is the bootstrap. The task is one signed `menu` act
on File > New Folder, which a background Finder reports disabled, so the
helper's temporary window preparation is what runs it. The filesystem is the
oracle: exactly one new directory with exactly the requested name, typed by the
same act (`text`) into the editor New Folder opens, inside the helper's
temporary preparation. The owned Finder window is closed by its close
button and the directory removed. No other Finder window is acted on.
"""
import hashlib
import os
from pathlib import Path
import secrets
import shutil
import tempfile
import time

TARGET = 'com.apple.finder'
NEW_FOLDER = ['File', ['New Folder', '새로운 폴더']]


def _window(pid, title):
    from ApplicationServices import AXUIElementCreateApplication
    from haejo.driver import _attr
    app = AXUIElementCreateApplication(pid)
    hits = [w for w in (_attr(app, 'AXWindows') or []) if _attr(w, 'AXTitle') == title]
    return app, (hits[0] if len(hits) == 1 else None)


def _name_fields(window, name):
    """Text fields in the owned window that show the new item's name."""
    from haejo.driver import _attr
    from ApplicationServices import AXUIElementIsAttributeSettable
    found = []

    def walk(node, depth):
        if depth > 16 or len(found) > 4:
            return
        if _attr(node, 'AXRole') == 'AXTextField' and _attr(node, 'AXValue') == name:
            err, settable = AXUIElementIsAttributeSettable(node, 'AXValue', None)
            found.append({'focused': _attr(node, 'AXFocused') is True, 'settable': err == 0 and bool(settable)})
            return
        for child in (_attr(node, 'AXChildren') or [])[:400]:
            walk(child, depth + 1)
    walk(window, 0)
    return found


def _subdirectories(folder):
    return sorted(p.name for p in folder.iterdir() if p.is_dir() and not p.is_symlink())


def run_probe(driver):
    from examples.probes.focus_witness import FocusWitness
    from haejo.driver import _attr
    report = {'passed': False, 'scope': 'owned_actual_Finder_background_New_Folder',
              'model_requests': 0, 'cleanup': 'not_started'}
    timeline = []

    def phase(name, **extra):
        timeline.append({'phase': name, 't': time.monotonic(), **extra})
    root = Path(__file__).resolve().parents[2]
    sources = [*root.glob('haejo/*.py'), *root.glob('helper/*.swift'), root / 'launcher/haejo',
               root / 'helper/Haejo Helper.app/Contents/MacOS/HaejoHelper', Path(__file__)]
    hashes = lambda: {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
                      for p in sources if p.is_file()}
    report['source_before'] = hashes()
    created = Path(tempfile.mkdtemp(prefix='haejo-finder-new-folder-', dir=Path.home() / 'Library/Caches'))
    folder = created.parent.resolve() / created.name
    report['owned_directory'] = str(folder)
    wanted = 'haejo-renamed-' + secrets.token_hex(6)
    window = None
    pid = None
    witness = None
    try:
        with FocusWitness() as witness:
            phase('bootstrap')
            observed = driver.observe(TARGET, 'tree_full', require_window=False)
            if observed.get('type') != 'observation':
                raise RuntimeError('finder_observation_unavailable')
            opened = driver.act(observed['obs_id'], TARGET, {'name': 'open_folder', 'path': str(folder)})
            report['open_folder'] = {k: opened.get(k) for k in ('type', 'error', 'effect', 'activated_target')}
            if opened.get('type') != 'acted':
                raise RuntimeError('open_folder_failed')
            from AppKit import NSRunningApplication
            running = NSRunningApplication.runningApplicationsWithBundleIdentifier_(TARGET)
            pid = int(running[0].processIdentifier())
            deadline = time.monotonic() + 10
            while time.monotonic() < deadline:
                app, window = _window(pid, folder.name)
                if window is not None and _attr(window, 'AXMain') is True:
                    break
                time.sleep(0.1)
            if window is None:
                raise RuntimeError('owned_window_unavailable')
            report['window_main'] = _attr(window, 'AXMain')
            report['finder_ax_frontmost_before'] = _attr(app, 'AXFrontmost')
            time.sleep(0.5)
            phase('task')
            before = _subdirectories(folder)
            observed = driver.observe(TARGET, 'tree_full')
            if observed.get('type') != 'observation':
                raise RuntimeError('task_observation_unavailable')
            began = time.monotonic()
            response = driver.act(observed['obs_id'], TARGET, {'name': 'menu', 'path': NEW_FOLDER, 'text': wanted})
            report['menu_seconds'] = time.monotonic() - began
            report['menu_response'] = {k: response.get(k) for k in
                ('type', 'error', 'effect', 'reason_code', 'needs_foreground', 'temporary_preparation',
                 'activated_target', 'menu_path') if k in response}
            if response.get('type') != 'acted':
                raise RuntimeError('menu_not_acted')
            # Filesystem oracle: exactly one new entry, a directory, with the
            # exact requested name (bounded wait for Finder's own rename).
            names = []
            deadline = time.monotonic() + 3
            while time.monotonic() < deadline:
                names = [n for n in sorted(p.name for p in folder.iterdir() if not p.name.startswith('.'))
                         if n not in before]
                if names == [wanted]:
                    break
                time.sleep(0.05)
            report['new_entries'] = len(names)
            report['renamed_on_disk'] = names == [wanted] and (folder / wanted).is_dir() and not (folder / wanted).is_symlink()
            report['created_directories'] = len([n for n in names if (folder / n).is_dir()])
            report['final_new_directories'] = report['created_directories']
            report['finder_ax_frontmost_after'] = _attr(app, 'AXFrontmost')
            phase('cleanup')
    except Exception as error:
        report['failure_class'] = type(error).__name__
        report['failure'] = str(error)[:200]
    finally:
        if pid is not None and window is not None:
            from ApplicationServices import AXUIElementPerformAction
            button = _attr(window, 'AXCloseButton')
            report['window_close_error'] = AXUIElementPerformAction(button, 'AXPress') if button is not None else None
            time.sleep(0.5)
            # The column-view title follows the selection; the held element decides.
            report['window_closed'] = _attr(window, 'AXRole') is None
        if report.get('window_closed') or window is None:
            shutil.rmtree(folder, ignore_errors=True)
        report['directory_removed'] = not folder.exists()
        report['cleanup'] = 'removed' if report['directory_removed'] else 'left'
        if witness is not None:
            report['activation_events'] = [{'bundle': a.get('bundle'), 't': a['t']} for a in witness.activations]
            report['focus'] = witness.summary()
        report['operation_timeline'] = timeline
        report['source_after'] = hashes()
        report['source_unchanged'] = report['source_after'] == report['source_before']
    task = next((p['t'] for p in timeline if p['phase'] == 'task'), None)
    during = [a for a in report.get('activation_events', []) if task is not None and a['t'] >= task]
    report['task_activation_events'] = during
    tp = (report.get('menu_response') or {}).get('temporary_preparation') or {}
    report['rename_verified'] = report.get('renamed_on_disk') is True
    text = tp.get('text') or {}
    report['passed'] = (report.get('created_directories') == 1 and report.get('new_entries') == 1
                        and report['rename_verified'] and text.get('entered') is True
                        and tp.get('restored') is True
                        and report.get('finder_ax_frontmost_after') is False and not during
                        and report['directory_removed'] and report['source_unchanged'])
    return report
