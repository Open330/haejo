#!/usr/bin/env python3
"""First-run check of a Haejo DMG on a fresh macOS VM, with no person involved.

A new account on a throwaway VM installs the DMG the way a person does: a
Safari-quarantined download, dragged to Applications, opened through the
Gatekeeper prompt, both permissions granted in System Settings, then one real
task. VNC input is real keyboard and mouse to the VM, so System Settings
accepts it; text on screen is found with Vision OCR, never fixed coordinates.
The VM runs without a window on the host and is deleted at the end.

  uv run --no-project --python 3.14 --with vncdotool==1.4.2 --with pillow==12.0.0 \\
      python setup/first_run_vm/check.py --dmg Haejo-1.0.0-rc.NN-arm64.dmg --out <dir>

Needs tart (https://github.com/cirruslabs/tart) and about 50 GB free disk.
Writes <dir>/first-run-vm.json and a screenshot per step.
"""
import argparse
import json
import re
import shutil
import subprocess
import tempfile
import time
import uuid
from pathlib import Path

IMAGE = 'ghcr.io/cirruslabs/macos-golden-gate-vanilla:27.2'
USER = PASSWORD = 'admin'   # the image's own throwaway account
HERE = Path(__file__).resolve().parent
# Partly covered prompts lose their first letters, so match fragments.
PASSWORD_PROMPT = r'odify Settings|ssword to continue|Enter your password'


class Failed(Exception):
    pass


def run(args, **kw):
    return subprocess.run(args, capture_output=True, text=True, **kw)


class VM:
    def __init__(self, out: Path, dmg: Path, image: str, keep: bool):
        self.out, self.dmg, self.image, self.keep = out, dmg, image, keep
        self.name = 'haejo-first-run-' + uuid.uuid4().hex[:8]
        self.work = Path(tempfile.mkdtemp(prefix='haejo-first-run-'))
        self.shot = 0
        self.steps = []
        self.vnc = None
        self.ocr = self.work / 'ocr'
        built = run(['swiftc', '-O', str(HERE / 'ocr.swift'), '-o', str(self.ocr)])
        if built.returncode:
            raise Failed('ocr build failed: ' + built.stderr[-400:])

    # ---- VM lifecycle -------------------------------------------------
    def start(self):
        if run(['tart', 'clone', self.image, self.name]).returncode:
            raise Failed('tart clone failed')
        run(['tart', 'set', self.name, '--memory', '6144', '--cpu', '4'])
        share = self.work / 'share'
        share.mkdir()
        shutil.copy2(self.dmg, share / self.dmg.name)
        log = (self.work / 'tart-run.log').open('w')
        self.proc = subprocess.Popen(['tart', 'run', self.name, '--no-graphics', '--vnc-experimental',
                                      f'--dir=share:{share}'], stdout=log, stderr=subprocess.STDOUT)
        deadline = time.monotonic() + 240
        url = None
        while time.monotonic() < deadline and not url:
            time.sleep(2)
            url = re.search(r'vnc://:([^@]+)@127\.0\.0\.1:(\d+)', (self.work / 'tart-run.log').read_text())
        if not url:
            raise Failed('VM did not start a VNC server')
        self.vnc_password, self.vnc_port = url.group(1), int(url.group(2))
        while time.monotonic() < deadline:
            ip = run(['tart', 'ip', self.name])
            if ip.returncode == 0 and ip.stdout.strip():
                self.ip = ip.stdout.strip()
                break
            time.sleep(3)
        else:
            raise Failed('VM has no IP address')
        self.install_key()
        if self.keep:   # enough to reach the VM by hand afterwards
            (self.out / 'vm.json').write_text(json.dumps({'name': self.name, 'ip': self.ip, 'work': str(self.work),
                                                          'vnc_port': self.vnc_port}) + '\n')
        self.vnc = self   # every VNC call below opens its own short connection
        self.mouseMove(400, 400)   # wake the display

    # Each VNC call is one vncdo run: tart's VNC answers one full-screen
    # request per connection, and vncdo's own pacing makes Finder see a drag.
    def _vncdo(self, *commands, timeout=60):
        import sys
        vncdo = Path(sys.executable).parent / 'vncdo'
        result = run([str(vncdo), '-s', f'127.0.0.1::{self.vnc_port}', '-p', self.vnc_password,
                      *map(str, commands)], timeout=timeout)
        if result.returncode:
            raise Failed('vncdo failed: ' + result.stderr[-300:])

    def captureScreen(self, path):
        self._vncdo('capture', path)

    def mouseMove(self, x, y):
        self._vncdo('move', int(x), int(y))

    def keyPress(self, key):
        self._vncdo('key', key)

    def install_key(self):
        key = self.work / 'key'
        run(['ssh-keygen', '-q', '-t', 'ed25519', '-N', '', '-f', str(key)])
        self.ssh_base = ['ssh', '-i', str(key), '-o', f'UserKnownHostsFile={self.work}/known',
                         '-o', 'StrictHostKeyChecking=accept-new', '-o', 'BatchMode=yes', f'{USER}@{self.ip}']
        script = f'''set timeout 20
spawn ssh -o StrictHostKeyChecking=accept-new -o UserKnownHostsFile={self.work}/known -o PubkeyAuthentication=no {USER}@{self.ip} "mkdir -p ~/.ssh && chmod 700 ~/.ssh && cat >> ~/.ssh/authorized_keys && chmod 600 ~/.ssh/authorized_keys"
expect "assword:" {{ send "{PASSWORD}\\r" }}
send "{(key.with_suffix('.pub')).read_text().strip()}\\r"
send "\\004"
expect eof
'''
        for _ in range(30):
            run(['expect', '-c', script], timeout=60)
            if self.sh('true', check=False).returncode == 0:
                return
            time.sleep(5)
        raise Failed('ssh into the VM failed')

    def sh(self, command, check=True, timeout=120):
        result = run(self.ssh_base + [command], timeout=timeout)
        if check and result.returncode:
            raise Failed(f'{command!r} failed: {result.stdout[-300:]}{result.stderr[-300:]}')
        return result

    def stop(self):
        if self.keep:
            return
        run(['tart', 'stop', self.name])
        run(['tart', 'delete', self.name])
        shutil.rmtree(self.work, ignore_errors=True)

    # ---- screen -------------------------------------------------------
    def screen(self, label):
        self.shot += 1
        path = self.out / f'{self.shot:02d}-{label}.png'
        self.vnc.captureScreen(str(path))
        read = run([str(self.ocr), str(path)])
        lines = json.loads(read.stdout or '[]')
        for line in lines:
            line['cx'] = line['x'] + line['w'] // 2
            line['cy'] = line['y'] + line['h'] // 2
        return lines, path

    @staticmethod
    def find(lines, pattern, exact=False):
        rx = re.compile(pattern)
        return [l for l in lines if (rx.fullmatch(l['text'].strip()) if exact else rx.search(l['text']))]

    def wait_for(self, pattern, label, timeout=40, exact=False):
        deadline = time.monotonic() + timeout
        while True:
            lines, path = self.screen(label)
            if self.find(lines, PASSWORD_PROMPT) and not re.search(pattern, 'odify Settings'):
                self.answer_password(label)   # a password prompt can come late in any step
                continue
            hits = self.find(lines, pattern, exact)
            if hits:
                return hits, lines, path
            if time.monotonic() > deadline:
                raise Failed(f'{pattern!r} not on screen ({path.name})')
            self.vnc.mouseMove(410, 410)
            time.sleep(2)

    def click(self, x, y):
        self._vncdo('move', int(x), int(y), 'pause', '0.2', 'click', 1)

    def drag(self, start, end):
        # Small first moves start the drag the way a hand does, then a few steps.
        sx, sy = int(start[0]), int(start[1])
        dx = 1 if end[0] >= start[0] else -1
        steps = ['move', sx + 4 * dx, sy + 2, 'pause', '0.15', 'move', sx + 12 * dx, sy + 4, 'pause', '0.15']
        for f in (0.3, 0.6, 0.95, 1.0):
            steps += ['move', int(sx + (end[0] - sx) * f), int(sy + (end[1] - sy) * f), 'pause', '0.2']
        self._vncdo('move', sx, sy, 'pause', '0.6', 'mousedown', 1, 'pause', '0.9',
                    *steps, 'pause', '0.8', 'mouseup', 1)

    def type(self, text):
        self._vncdo('type', text, 'key', 'enter')

    def authenticate_if_asked(self, label, timeout=6):
        """Answer a password prompt for the VM account when one appears."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            lines, _ = self.screen(label)
            if self.find(lines, PASSWORD_PROMPT):
                self.answer_password(label)
                return True
            time.sleep(1)
        return False

    def answer_password(self, label):
        # Typing while the prompt is still fading in is lost, so wait, type,
        # and type again while the prompt stays.
        for _ in range(3):
            time.sleep(1.5)
            # Typed with no prompt, the letters would jump the Settings sidebar.
            if not self.find(self.screen(f'{label}-ready')[0], PASSWORD_PROMPT):
                return
            self.type(PASSWORD)
            time.sleep(2)
            if not self.find(self.screen(f'{label}-after')[0], PASSWORD_PROMPT):
                return
        raise Failed('the password prompt did not accept the VM password')

    def toggle_in_row(self, path, row, pane_right):
        """Center of the switch at the right end of a list row (pixels, not text)."""
        from PIL import Image
        image = Image.open(path).convert('RGB')
        y = row['cy']
        background = image.getpixel((row['x'] + row['w'] + 40, y))
        # An off switch is a faint track (only ~12-30 levels from the row) with a
        # white knob, so look at a band of rows and a low threshold.
        columns = {x for x in range(row['x'] + row['w'] + 40, min(pane_right, image.width - 1))
                   if any(sum(abs(a - b) for a, b in zip(image.getpixel((x, y + dy)), background)) > 12
                          for dy in (-6, 0, 6))}
        runs, start = [], None
        for x in range(row['x'] + row['w'] + 40, min(pane_right, image.width - 1) + 1):
            if x in columns and start is None:
                start = x
            elif x not in columns and start is not None:
                runs.append((start, x - 1)); start = None
        # A switch is 40-160 pixels wide; card edges and shadows are narrower.
        switches = [r for r in runs if 40 <= r[1] - r[0] <= 160]
        if not switches:
            raise Failed(f'no switch found in the row ({path.name})')
        left, right = switches[-1]
        return (left + right) // 2, y

    # ---- steps --------------------------------------------------------
    def step(self, name, fn):
        started = time.monotonic()
        try:
            detail = fn() or {}
            self.steps.append({'step': name, 'passed': True, 'seconds': round(time.monotonic() - started, 1), **detail})
        except Exception as error:
            self.steps.append({'step': name, 'passed': False, 'seconds': round(time.monotonic() - started, 1),
                               'error': str(error)[:500]})
            raise

    def gatekeeper_default(self):
        """The image ships with Gatekeeper off; a Mac ships with App Store and
        identified developers. Turning it on from the CLI leaves App Store only."""
        self.sh(f'echo {PASSWORD} | sudo -S spctl --global-enable')
        # The ?Security anchor scrolls the pane to "Allow applications from".
        self.sh('open "x-apple.systempreferences:com.apple.settings.PrivacySecurity.extension?Security"')
        allow, lines, path = self.wait_for(r'Allow applications from', 'privacy-security', timeout=90)
        if self.find(lines, r'App Store (&|and) Known Developers'):
            return {'already': True}
        value = [l for l in self.find(lines, r'^App Store$', exact=True) if abs(l['cy'] - allow[0]['cy']) < 30]
        if not value:
            raise Failed(f'policy value not found ({path.name})')
        def row_value(lines):
            row = self.find(lines, r'Allow applications from')
            return [l['text'] for l in lines if row and abs(l['cy'] - row[0]['cy']) < 30 and l is not row[0]]
        for attempt in range(3):
            self.click(value[0]['cx'], value[0]['cy'])
            hits, _, _ = self.wait_for(r'App Store (&|and) Known Developers', f'policy-menu-{attempt}')
            time.sleep(0.8)   # let the menu finish opening before choosing
            self.click(hits[0]['cx'], hits[0]['cy'])
            self.authenticate_if_asked(f'policy-password-{attempt}', timeout=20)
            lines, path = self.screen(f'policy-set-{attempt}')
            if any(l['text'].startswith('✓') for l in lines):   # the menu is still open
                self.keyPress('esc')
                time.sleep(1)
            # Read the setting back from a freshly opened Security section.
            self.sh('open "x-apple.systempreferences:com.apple.settings.PrivacySecurity.extension?Security"')
            _, lines, path = self.wait_for(r'Allow applications from', f'policy-check-{attempt}', timeout=30)
            if any(re.search(r'Known Developers', t) for t in row_value(lines)):
                break
            allow = self.find(lines, r'Allow applications from')
            value = [l for l in self.find(lines, r'^App Store$', exact=True) if abs(l['cy'] - allow[0]['cy']) < 30] or value
        else:
            raise Failed(f'policy did not change ({path.name})')
        self.sh('osascript -e \'quit app "System Settings"\'', check=False)
        return {}

    def install(self):
        q = f'0083;{int(time.time()):x};Safari;{str(uuid.uuid4()).upper()}'
        self.sh(f'cp "/Volumes/My Shared Files/share/{self.dmg.name}" ~/Downloads/ && '
                f'xattr -w com.apple.quarantine "{q}" ~/Downloads/{self.dmg.name}')
        # The policy change can take a few seconds to reach the assessment daemon.
        for _ in range(20):
            image = self.sh(f'spctl -a -vv -t open --context context:primary-signature ~/Downloads/{self.dmg.name} 2>&1',
                            check=False).stdout
            if ': accepted' in image:
                break
            time.sleep(3)
        else:
            raise Failed('Gatekeeper rejected the downloaded DMG: ' + image[-200:])
        self.sh(f'hdiutil attach -nobrowse ~/Downloads/{self.dmg.name} >/dev/null && open /Volumes/Haejo')
        for attempt in range(5):   # a drag the window server drops leaves nothing copied
            # The DMG window shows both captions on one row; the Finder sidebar's
            # "Applications" alone is not it, so wait for the pair.
            deadline = time.monotonic() + 60
            while True:
                lines, path = self.screen(f'dmg-window-{attempt}')
                pairs = [(a, h) for a in self.find(lines, r'^Applications$', exact=True)
                         for h in self.find(lines, r'^Haejo$', exact=True)
                         if abs(a['cy'] - h['cy']) < 30 and h['cx'] > a['cx']]
                if pairs:
                    apps, haejo = pairs[0][0], [pairs[0][1]]
                    break
                if time.monotonic() > deadline:
                    raise Failed(f'Haejo icon not found in the DMG window ({path.name})')
                time.sleep(2)
            lift = int(apps['h'] * 2.5)   # the icon's middle; its top edge is transparent margin
            # Bring the DMG window forward first: on an inactive window the
            # first mouse-down may only activate it and never start a drag.
            self.click(apps['cx'], apps['cy'] + apps['h'] * 8)
            time.sleep(1)
            self.drag((haejo[0]['cx'], haejo[0]['cy'] - lift), (apps['cx'], apps['cy'] - lift))
            for _ in range(5):
                time.sleep(2)
                if self.sh('test -e /Applications/Haejo.app', check=False).returncode == 0:
                    break
            else:
                continue
            break
        else:
            raise Failed(f'dragging Haejo to Applications copied nothing ({path.name})')
        # Done copying: the size stops growing at or above the original (extended
        # attributes can make the copy larger) and the signature verifies.
        source = int(self.sh('du -sk /Volumes/Haejo/Haejo.app | cut -f1').stdout.strip())
        deadline = time.monotonic() + 180
        previous, size = -1, 0
        while time.monotonic() < deadline:
            size = int(self.sh('du -sk /Applications/Haejo.app 2>/dev/null | cut -f1', check=False).stdout.strip() or 0)
            if size >= source and size == previous and \
                    self.sh('codesign --verify --deep --strict /Applications/Haejo.app', check=False).returncode == 0:
                break
            previous = size
            time.sleep(3)
        else:
            raise Failed(f'Haejo.app did not finish copying ({size} of {source} KB)')
        previous = size
        app = self.sh('spctl -a -vv /Applications/Haejo.app 2>&1 | head -2', check=False).stdout
        if 'accepted' not in app or 'Notarized Developer ID' not in app:
            raise Failed('Gatekeeper did not accept the installed app: ' + app)
        # Eject as a person does after installing; its window would cover setup.
        self.sh('hdiutil detach -quiet /Volumes/Haejo', check=False)
        return {'installed_kb': int(previous)}

    def first_open(self):
        self.sh('open /Applications/Haejo.app')
        hits, lines, _ = self.wait_for(r'app downloaded|want to open it', 'gatekeeper-prompt', timeout=60)
        button = [l for l in self.find(lines, r'^Open$', exact=True) if l['cy'] > hits[0]['cy']]
        self.click(button[0]['cx'], button[0]['cy'])
        _, lines, path = self.wait_for(r'Mac 권한', 'haejo-window', timeout=60)
        connected = bool(self.find(lines, r'연결 완료|연결했어요'))
        return {'agents_connected': connected, 'screenshot': path.name}

    def layout(self, lines, path, pane_title):
        """Where the guide and the visible part of the Settings pane are.

        The guide is a 300-point panel (about 620 pixels here) titled
        "Haejo 권한 도우미"; it sits beside Settings, or over its sidebar when
        there is no room, so the list can be partly under it on the left."""
        guide = self.find(lines, r'Haejo 권한 도우미')
        title = self.find(lines, pane_title)
        if not guide or not title:
            raise Failed(f'guide or Settings pane not on screen ({path.name})')
        g_left, g_right = guide[0]['cx'] - 320, guide[0]['cx'] + 320
        title = title[0]
        if title['cx'] > g_right:   # Settings content to the right of the guide
            left = g_right + 10
            pane = [l for l in lines if l['x'] >= left - 30 and l['cy'] > title['cy']]
        else:                        # guide beside Settings, on its right
            left = 0
            pane = [l for l in lines if l['x'] + l['w'] < g_left and l['cy'] > title['cy']]
        # The pane's right edge comes from its own description lines (which share
        # a left edge under the title); another app's window beside Settings
        # must not stretch it.
        band = [l for l in pane if title['cy'] < l['cy'] < title['cy'] + 260]
        start = min((l['x'] for l in band), default=title['x'])
        right = max([l['x'] + l['w'] for l in band if abs(l['x'] - start) < 60] or [title['x'] + title['w']]) + 40
        return {'g_left': g_left, 'g_right': g_right, 'left': left, 'right': right, 'title': title, 'pane': pane}

    def list_row(self, lay, app_name):
        last = re.escape(app_name.split()[-1])
        rows = [l for l in lay['pane'] if re.search(rf'(^|\s){last}$', l['text'].strip())
                and not (lay['g_left'] <= l['cx'] <= lay['g_right'])]
        return rows[0] if rows else None

    def grant(self, label, which, app_name, drag_icon):
        # Start each grant from the setup window alone (Haejo returns in front of
        # Settings after a grant; an earlier build stayed behind it).
        self.sh('osascript -e \'quit app "System Settings"\'', check=False)
        time.sleep(2)
        heading = r'앱 조작 권한 켜기' if which == 0 else r'화면 캡처.*권한 켜기'
        pane_title = r'Device Control and Data Access|Accessibility$' if which == 0 else r'Screen & System Audio Recording'
        for attempt in range(3):   # a first click may only bring the window forward
            lines, path = self.screen(f'{label}-uncover')
            if not self.find(lines, r'^설정 (다시 )?열기$', exact=True):
                # Another window covers the button: click what shows of setup, as a person would.
                visible = self.find(lines, r'에이전트 연결|첫 작업|Mac 권한|연결 완료')
                if visible:
                    self.click(visible[0]['cx'], visible[0]['cy'])
                    time.sleep(1.5)
            hits, lines, _ = self.wait_for(r'^설정 (다시 )?열기$', f'{label}-before', exact=True)
            target = sorted(hits, key=lambda l: l['cy'])[0 if which == 0 else -1]   # a granted card has no button
            self.click(target['cx'], target['cy'])
            try:
                self.wait_for(heading, f'{label}-guide', timeout=15)
                break
            except Failed:
                if attempt == 2:
                    raise
        time.sleep(1)
        lines, path = self.screen(f'{label}-settings')
        lay = self.layout(lines, path, pane_title)
        row = self.list_row(lay, app_name)
        if not row and drag_icon:
            name = [l for l in self.find(lines, rf'^{re.escape(app_name)}$', exact=True)
                    if lay['g_left'] <= l['cx'] <= lay['g_right']]
            if not name:
                raise Failed(f'guide icon not found ({path.name})')
            icon = (name[0]['cx'], name[0]['cy'] - int(name[0]['h'] * 4))
            empty = sorted(self.find(lay['pane'], r'^No Items$', exact=True), key=lambda l: l['cy'])
            if empty:   # an empty list shows "No Items" inside its own box
                drop = (empty[0]['cx'], empty[0]['cy'])
            else:       # under the description, inside the first list
                text = [l for l in lay['pane'] if l['cy'] < lay['title']['cy'] + 200] or [lay['title']]
                drop = ((max(lay['left'], min(l['x'] for l in text)) + lay['right']) // 2,
                        max(l['y'] + l['h'] for l in text) + 50)
            for _ in range(3):   # a drag the window server drops adds nothing
                self.drag(icon, drop)
                self.authenticate_if_asked(f'{label}-drop-password', timeout=10)
                if self.granted(which):   # added switched on; the guide closes itself
                    break
                lines, path = self.screen(f'{label}-after-drop')
                try:
                    lay = self.layout(lines, path, pane_title)
                    row = self.list_row(lay, app_name)
                except Failed:
                    row = None
                if row or self.find(lines, r'^Quit (&|and) Reopen$', exact=True):
                    break
        if not row and not self.granted(which):
            raise Failed(f'{app_name} row not in the Settings list ({path.name})')
        for attempt in range(3):
            if self.granted(which):
                break
            if attempt:   # another window took the front and the prompt went with it
                self.sh('open -b com.apple.systempreferences')
                time.sleep(2)
                lines, path = self.screen(f'{label}-retry-{attempt}')
                lay = self.layout(lines, path, pane_title)
                row = self.list_row(lay, app_name) or row
            # The guide must leave the switch reachable: click it without closing the guide.
            self.click(*self.toggle_in_row(path, row, lay['right']))
            self.authenticate_if_asked(f'{label}-password-{attempt}', timeout=20)
            for _ in range(5):
                if self.granted(which):
                    break
                time.sleep(2)
        if not self.granted(which):
            raise Failed(f'{label} permission not granted ({self.screen(label + "-not-granted")[1].name})')
        lines, _ = self.screen(f'{label}-granted')
        reopen = self.find(lines, r'^Quit (&|and) Reopen$', exact=True)
        if reopen:
            self.click(reopen[0]['cx'], reopen[0]['cy'])
            time.sleep(8)
        return {'reopen_prompt': bool(reopen), 'guide_left_switch_visible': True}

    def granted(self, which):
        doctor = self.sh('~/.local/bin/haejo doctor 2>&1 | head -3', check=False).stdout.splitlines()
        return len(doctor) > which and doctor[which].startswith('✓')

    def first_task(self):
        self.sh('osascript -e \'quit app "System Settings"\'', check=False)
        if not (self.granted(0) and self.granted(1)):
            raise Failed('permissions not kept after reopening')
        flow = {'name': 'first-run-vm', 'target': 'com.apple.finder', 'schema': 2, 'steps': [{
            'action': 'menu', 'params': {'path': ['File', ['New Folder', '새로운 폴더']], 'text': 'first-run-check'},
            'unverified_ok': True, 'safety': {
                'effects': ['write_persistent'], 'data_classes': ['none'],
                'resource': {'object_type': 'folder', 'scope': 'item'}, 'destination': {'kind': 'same_app'},
                'reversibility': 'reversible', 'unknowns': [],
                'evidence': [{'source': 'user_intent', 'field': 'asked', 'value': 'first-run VM check',
                              'covers': ['write_persistent']}]}}]}
        self.sh(f"mkdir -p ~/first-run && cat > /tmp/first-run.json <<'EOF'\n{json.dumps(flow)}\nEOF")
        self.sh('open -g ~/first-run; sleep 2')
        # Quit & Reopen restarts Haejo (macOS, or Haejo's own relauncher); wait until it reports ready again.
        for _ in range(20):
            if '준비 끝' in self.sh('~/.local/bin/haejo doctor 2>&1', check=False).stdout:
                break
            time.sleep(3)
        task = self.sh('~/.local/bin/haejo task start "first-run VM check" 2>&1', check=False).stdout
        tid = re.search(r'HAEJO_TASK (\S+)', task)
        env = f'HAEJO_TASK={tid.group(1)} ' if tid else ''
        outputs = []
        for _ in range(2):   # again only when the first one certainly did nothing
            result = self.sh(f'{env}~/.local/bin/haejo run /tmp/first-run.json --helper --yes 2>&1',
                             check=False, timeout=120)
            outputs.append(result.stdout[-600:])
            if 'not_started' not in result.stdout:
                break
            time.sleep(5)
        if self.sh('test -d ~/first-run/first-run-check', check=False).returncode:
            raise Failed(f'first task did not create the folder ({self.screen("first-task")[1].name}): {outputs[-1]}')
        return {'runs': len(outputs)}


def main():
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('--dmg', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--image', default=IMAGE)
    parser.add_argument('--keep', action='store_true', help='leave the VM for inspection')
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    vm = VM(args.out, args.dmg.resolve(), args.image, args.keep)
    report = {'dmg': args.dmg.name, 'image': args.image, 'steps': vm.steps}
    try:
        vm.step('start', vm.start)
        vm.step('gatekeeper_default', vm.gatekeeper_default)
        vm.step('install_by_drag', vm.install)
        vm.step('first_open', vm.first_open)
        vm.step('grant_app_control', lambda: vm.grant('app-control', 0, 'Haejo Helper', False))
        vm.step('grant_screen_capture', lambda: vm.grant('screen-capture', 1, 'Haejo', True))
        vm.step('first_task', vm.first_task)
        report['passed'] = True
    except Exception as error:
        report['passed'] = False
        report['error'] = str(error)[:500]
    finally:
        vm.stop()
        (args.out / 'first-run-vm.json').write_text(json.dumps(report, indent=2, ensure_ascii=False) + '\n')
    print(json.dumps({k: report[k] for k in ('passed',)} | {'steps': [(s['step'], s['passed']) for s in vm.steps]},
                     ensure_ascii=False))
    raise SystemExit(0 if report['passed'] else 1)


if __name__ == '__main__':
    main()
