"""Actual TextEdit Edit > Select All on an owned document, TextEdit kept behind.

A command that opens no dialog: the helper's temporary preparation must run
it without the dialog wait, and the owned text view's own selection is the
oracle. Bootstrap opens the owned RTF with `open -g`; the task is one signed
`menu` act. The document is closed unmodified by its close button.
"""
import hashlib
from pathlib import Path
import secrets
import subprocess
import tempfile
import time

TARGET = 'com.apple.TextEdit'
SELECT_ALL = ['Edit', ['Select All', '전체 선택']]


def _owned(pid, title):
    from ApplicationServices import AXUIElementCreateApplication
    from haejo.driver import _attr
    app = AXUIElementCreateApplication(pid)
    hits = [w for w in (_attr(app, 'AXWindows') or []) if _attr(w, 'AXTitle') == title]
    window = hits[0] if len(hits) == 1 else None
    area = None
    if window is not None:
        stack = [window]
        while stack and area is None:
            node = stack.pop()
            if _attr(node, 'AXRole') == 'AXTextArea':
                area = node
            stack.extend(_attr(node, 'AXChildren') or [])
    return app, window, area


def _selection(area):
    from haejo.driver import _attr
    from ApplicationServices import AXValueGetValue, kAXValueCFRangeType
    raw = _attr(area, 'AXSelectedTextRange')
    ok, value = AXValueGetValue(raw, kAXValueCFRangeType, None)
    if not ok:
        return None
    if isinstance(value, tuple):
        return (int(value[0]), int(value[1]))
    return (int(value.location), int(value.length))


def run_probe(driver):
    from examples.probes.focus_witness import FocusWitness
    from haejo.driver import _attr
    report = {'passed': False, 'scope': 'owned_actual_TextEdit_background_Select_All', 'model_requests': 0}
    timeline = []

    def phase(name):
        timeline.append({'phase': name, 't': time.monotonic()})
    root = Path(__file__).resolve().parents[2]
    sources = [*root.glob('haejo/*.py'), *root.glob('helper/*.swift'), root / 'launcher/haejo',
               root / 'helper/Haejo Helper.app/Contents/MacOS/HaejoHelper', Path(__file__)]
    hashes = lambda: {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
                      for p in sources if p.is_file()}
    report['source_before'] = hashes()
    nonce = secrets.token_hex(8)
    body = 'Haejo owned select all ' + nonce
    directory = Path(tempfile.mkdtemp(prefix='haejo-select-all-')).resolve()
    source = directory / f'select-all-{nonce}.rtf'
    source.write_bytes(b'{\\rtf1\\ansi ' + body.encode('ascii') + b'}')
    window = None
    pid = None
    witness = None
    try:
        with FocusWitness() as witness:
            phase('bootstrap')
            subprocess.run(['open', '-g', '-a', 'TextEdit', str(source)], check=True, timeout=20)
            from AppKit import NSRunningApplication
            deadline = time.monotonic() + 10
            area = None
            while time.monotonic() < deadline:
                running = NSRunningApplication.runningApplicationsWithBundleIdentifier_(TARGET)
                if len(running) == 1:
                    pid = int(running[0].processIdentifier())
                    app, window, area = _owned(pid, source.name)
                    if window is not None and area is not None and _attr(window, 'AXMain') is True:
                        break
                time.sleep(0.1)
            if area is None:
                raise RuntimeError('owned_window_unavailable')
            time.sleep(1.0)        # the external witness takes the front back once
            phase('task')
            report['selection_before'] = _selection(area)
            report['textedit_ax_frontmost_before'] = _attr(app, 'AXFrontmost')
            observed = driver.observe(TARGET, 'tree_full')
            if observed.get('type') != 'observation':
                raise RuntimeError('task_observation_unavailable')
            began = time.monotonic()
            response = driver.act(observed['obs_id'], TARGET, {'name': 'menu', 'path': SELECT_ALL})
            report['menu_seconds'] = time.monotonic() - began
            report['menu_response'] = {k: response.get(k) for k in
                ('type', 'error', 'effect', 'reason_code', 'temporary_preparation', 'activated_target')
                if k in response}
            report['selection_after'] = _selection(area)
            report['text_length'] = len(_attr(area, 'AXValue') or '')
            report['textedit_ax_frontmost_after'] = _attr(app, 'AXFrontmost')
            report['edited_after'] = _attr(window, 'AXEdited')
            phase('cleanup')
    except Exception as error:
        report['failure_class'] = type(error).__name__
        report['failure'] = str(error)[:200]
    finally:
        if window is not None:
            from ApplicationServices import AXUIElementPerformAction
            if _attr(window, 'AXEdited') is not True:
                button = _attr(window, 'AXCloseButton')
                report['close_error'] = AXUIElementPerformAction(button, 'AXPress') if button is not None else None
                time.sleep(0.5)
            report['window_closed'] = _owned(pid, source.name)[1] is None
        if report.get('window_closed') or window is None:
            source.unlink(missing_ok=True)
            directory.rmdir()
        report['source_removed'] = not directory.exists()
        if witness is not None:
            report['activation_events'] = [{'bundle': a.get('bundle'), 't': a['t']} for a in witness.activations]
        report['operation_timeline'] = timeline
        report['source_unchanged'] = hashes() == report['source_before']
    task = next((p['t'] for p in timeline if p['phase'] == 'task'), None)
    report['task_activation_events'] = [a for a in report.get('activation_events', [])
                                        if task is not None and a['t'] >= task]
    tp = (report.get('menu_response') or {}).get('temporary_preparation') or {}
    report['passed'] = ((report.get('menu_response') or {}).get('type') == 'acted'
                        and report.get('selection_after') == (0, report.get('text_length'))
                        and report.get('selection_before') != report.get('selection_after')
                        and tp.get('restored') is True and tp.get('sheet_wait') == 'not_a_dialog_command'
                        and report.get('textedit_ax_frontmost_after') is False
                        and not report['task_activation_events'] and report.get('window_closed') is True
                        and report['source_removed'] and report['source_unchanged'])
    return report
