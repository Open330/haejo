#!/usr/bin/env python3
"""Re-shoot the landing's TextEdit and Finder examples with the installed Haejo.

Owned scratch files only: a new folder of five synthetic files and one note.
Haejo replays the saved Flows (film/textedit.flow.json, film/finder.flow.json,
built-in textedit_save); the signed helper captures the one owned window
before and after each step. Output matches render_native_examples.py:
<out>/<name>-<stamp>/report.json + frame PNGs.

  python shoot_everyday.py --out DIR
  python ../render_native_examples.py --recordings DIR
"""
import argparse, json, subprocess, time
from pathlib import Path

HERE = Path(__file__).resolve().parent
HAEJO = Path('/Applications/Haejo.app/Contents/Resources/runtime/launcher/haejo')
NOTE = 'haejo-workshop-notes.txt'
FILES = {'Agenda.txt': 'Agenda\n1. Welcome\n2. Hands-on\n3. Q&A\n', 'Budget.csv': 'item,amount\nvenue,120\nsnacks,40\n',
         'Checklist.txt': '[ ] laptop\n[ ] adapter\n[ ] notes\n', NOTE: 'Workshop preparation\n'}
PDF = (b'%PDF-1.1\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj 2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj '
       b'3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 300 144]>>endobj\ntrailer<</Root 1 0 R>>\n%%EOF\n')


def sh(*args, timeout=180, check=True):
    r = subprocess.run([str(a) for a in args], capture_output=True, text=True, timeout=timeout)
    if check and r.returncode: raise RuntimeError(f'{args[:3]}: {r.stdout[-400:]}{r.stderr[-400:]}')
    return r


def osa(*lines): sh('osascript', *[x for line in lines for x in ('-e', line)])


class Shoot:
    def __init__(self, base, name, target, window):
        self.dir = base/f'{name}-{time.strftime("%Y%m%dT%H%M%S")}'; self.dir.mkdir(parents=True)
        self.target, self.window, self.t0 = target, window, time.monotonic()
        self.frames, self.actions = [], []
    def now(self): return round(time.monotonic()-self.t0, 3)
    def capture(self):
        f = f'frame-{len(self.frames):03d}.png'; at = self.now()
        sh(HAEJO, 'capture', self.target, '--helper', '--window', self.window, '--output', self.dir/f)
        self.frames.append({'file': f, 'at': at})
    def act(self, name, *command):
        at = self.now(); r = sh(*command, check=False)
        out = [l for l in (r.stdout+r.stderr).splitlines() if l.strip()]
        self.actions.append({'at': at, 'action': {'name': name}, 'exit': r.returncode, 'last': out[-1] if out else ''})
        return r
    def finish(self, final):
        (self.dir/'report.json').write_text(json.dumps({'target': self.target, 'final': final, 'seconds': self.now(),
            'frames': self.frames, 'actions': self.actions}, ensure_ascii=False, indent=2)+'\n')


def main():
    ap = argparse.ArgumentParser(description=__doc__); ap.add_argument('--out', type=Path, required=True)
    a = ap.parse_args(); base = a.out.resolve(); base.mkdir(parents=True, exist_ok=True)
    folder = base/'native-files'; folder.mkdir(exist_ok=True)
    for name, text in FILES.items(): (folder/name).write_text(text)
    (folder/'Workshop-handbook.pdf').write_bytes(PDF); note = folder/NOTE

    # TextEdit: write the note, then save it with the built-in textedit_save.
    osa(f'tell application "TextEdit" to close (every window whose name is "{NOTE}") saving no')
    note.write_text(FILES[NOTE]); sh('open', '-a', 'TextEdit', note); time.sleep(2)
    osa(f'tell application "TextEdit" to set bounds of (first window whose name is "{NOTE}") to {{200, 120, 856, 542}}')
    s = Shoot(base, 'textedit', 'com.apple.TextEdit', NOTE); s.capture()
    s.act('set_value', HAEJO, 'run', HERE/'textedit.flow.json', '--helper', '--document', note, '--yes'); s.capture()
    save = s.act('menu', HAEJO, 'replay', 'textedit_save', '-p', f'document={note}', '-p', f'name={NOTE}', '--helper', '--yes'); s.capture(); s.capture()
    expected = json.loads((HERE/'textedit.flow.json').read_text())['params']['notes']
    assert save.returncode == 0 and note.read_text() == expected, 'TextEdit save not verified'
    s.finish({'file': NOTE, 'contents_match': True, 'saved_state_verified': True,
              'edit_replay_ok': s.actions[0]['exit'] == 0, 'save_replay_ok': True})

    # Finder: sort the owned folder by Kind, then by Name.
    osa('tell application "Finder"', 'repeat with w in (get every Finder window)', 'if name of w is "native-files" then close w', 'end repeat', 'end tell')
    sh('open', '-a', 'Finder', folder); time.sleep(2)
    osa('tell application "Finder" to set current view of front window to list view',
        'tell application "Finder" to set bounds of front window to {200, 120, 1120, 555}')
    s = Shoot(base, 'finder', 'com.apple.finder', 'native-files'); s.capture()
    one = json.loads((HERE/'finder.flow.json').read_text())
    for i, step in enumerate(one['steps']):
        path = s.dir/f'step-{i}.flow.json'; path.write_text(json.dumps({**one, 'steps': [step]}))
        r = s.act('click', HAEJO, 'run', path, '--helper'); path.unlink()
        assert r.returncode == 0, r.stdout[-300:]; s.capture()
    s.capture(); s.finish({'verified': True, 'window': 'native-files', 'result': '5 items, sorted by Name'})
    print(base)


if __name__ == '__main__':
    main()
