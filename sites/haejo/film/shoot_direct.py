#!/usr/bin/env python3
"""Shoot the landing's "direct control" clip: a form filled in a Safari window that stays behind.

Everything runs through the installed Haejo, one call per step, on the
accessibility route. The expense page (demo-expense/) is a local demo marked
DEMO on screen; the row comes from data/2026-11.json and is made up. The
window in front of it in the clip is a TextEdit note this script writes in a
new folder (a made-up quarterly summary), opened behind the app in use.

Each capture is one window, taken by the signed helper after the call that
changed it. Around every call the script records which app is in front and the
route Haejo named; evidence.json keeps that, with no screen contents. A step
that would change the app in front ends the shoot.

Safari is running before the shoot starts (a cold start can show Safari's own
session alert in front). The script leaves Safari and the app in front as they
were: it closes the demo tab by its address and the note through TextEdit's own
menu, and quits TextEdit when the shoot started it.

  python3 sites/haejo/film/shoot_direct.py --out DIR
  .venv/bin/python sites/haejo/film/render_direct.py --plates DIR/plates --out CLIP
"""
import argparse, json, re, shutil, subprocess, tempfile, time
from pathlib import Path

HERE = Path(__file__).resolve().parent
H = '/Applications/Haejo.app/Contents/Resources/runtime/launcher/haejo'
SAFARI, TEXTEDIT = 'com.apple.Safari', 'com.apple.TextEdit'
PAGE = '법인카드 경비 등록 - 데모상사 그룹웨어'
URL = 'http://127.0.0.1:8742/?month=11'
MATCH = ['--window-match', 'url=127.0.0.1']
NOTE = '3분기 보고서.rtf'
NOTE_HTML = '''<html><head><meta charset="utf-8"></head><body style="font-family:'Apple SD Gothic Neo';font-size:14pt">
<p style="font-size:22pt"><b>3분기 실적 요약</b></p>
<p>신규 고객사 온보딩이 끝나면서 매출이 전 분기보다 12% 늘었습니다. 물류 개선 프로젝트는 일정대로 진행 중이고, 사내 교육은 두 차례 열었습니다.</p>
<p><b>다음 분기 계획</b></p>
<p>1. 온보딩 자료를 고객사별로 정리합니다.<br>2. 물류센터 시범 운영 결과를 공유합니다.<br>3. 교육 과정을 한 번 더 엽니다.</p>
<p>이 문서는 촬영용으로 지어낸 예시입니다.</p>
</body></html>'''
SAFETY = {'effects': ['write_ephemeral'], 'reversibility': 'reversible', 'resource': {'object_type': 'demo expense form', 'scope': 'entry'}}


def sh(*args, check=True):
    r = subprocess.run([str(a) for a in args], capture_output=True, text=True, timeout=300)
    if check and r.returncode: raise RuntimeError(f'{args[:3]} → {(r.stdout+r.stderr)[-500:]}')
    return r


def again(*args):
    """A resize or capture: while the window list is unavailable (the person is on another Space), ask again."""
    for n in range(40):
        r = sh(*args, check=False)
        if r.returncode == 0: return r
        time.sleep(3)
    raise RuntimeError(f'{args[:3]} → {(r.stdout+r.stderr)[-500:]}')


OTHERS = {}


def front():
    """The app in front: its bundle id for Apple's apps, a neutral label for any other (the summary names no app the person uses)."""
    asn = sh('lsappinfo', 'front').stdout.strip()
    bundle = re.search(r'"([^"]*)"', sh('lsappinfo', 'info', '-only', 'bundleid', asn).stdout).group(1)
    return bundle if bundle.startswith('com.apple.') else OTHERS.setdefault(bundle, f'other-app-{len(OTHERS)+1}')


def running(name): return sh('pgrep', '-x', name, check=False).returncode == 0
def text(field, value): return {'action': 'set_value', 'selector': {'role': 'TextField', 'title': field}, 'params': {'value': value},
                                'postcondition': {'field': {'role': 'TextField', 'title': field}, 'attribute': 'Value', 'equals': value}}


def steps(row):
    return [('date', text('사용일자', row['date'])), ('merchant', text('가맹점명', row['merchant'])),
            ('category', {'action': 'click', 'selector': {'role': 'RadioButton', 'title': row['category']},
                          'postcondition': {'field': {'role': 'RadioButton', 'title': row['category']}, 'attribute': 'Value', 'equals': '1'}}),
            ('amount', text('금액', row['amount'])), ('project', text('프로젝트 코드', row['project'])), ('memo', text('사용 내용', row['memo'])),
            ('register', {'action': 'click', 'selector': {'role': 'Button', 'title': '등록'},
                          'postcondition': {'contains': f"번째 경비를 등록했습니다: {row['merchant']}"}})]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--out', type=Path, required=True); ap.add_argument('--row', type=int, default=3, help='which row of data/2026-11.json (1-8)')
    a = ap.parse_args(); out = a.out.resolve(); P = out/'plates'; P.mkdir(parents=True)
    if not running('Safari'): raise SystemExit('Open Safari first, then run the shoot: it works in the Safari that is already running.')
    row = json.loads((HERE/'data/2026-11.json').read_text())[a.row-1]
    began, textedit_was_running = front(), running('TextEdit')
    if began == SAFARI: raise SystemExit('Safari is in front. Shoot while another app is in front.')
    folder = Path(tempfile.mkdtemp(prefix='haejo-direct-')); note = folder/NOTE
    server = subprocess.Popen(['python3', '-m', 'http.server', '8742', '--bind', '127.0.0.1'], cwd=HERE/'demo-expense',
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    evidence = []

    def record(name, action, call):
        """Run one call, note the app in front on both sides and the routes it named, then capture the Safari window."""
        before = front(); r = call(); after = front(); log = r.stdout+r.stderr
        routes = [json.loads(l.split(' ', 1)[1]) for l in log.splitlines() if l.startswith('HAEJO_ROUTE ')]
        entry = {'step': name, 'action': action, 'front_before': before, 'front_after': after, 'front_unchanged': before == after,
                 'safari_in_front': SAFARI in (before, after), 'exit': r.returncode,
                 'routes': [{k: x[k] for k in ('input_route', 'route_level', 'status', 'foreground_taken') if k in x} for x in routes]}
        evidence.append(entry)
        if r.returncode or not entry['front_unchanged'] or entry['safari_in_front'] or any(x.get('route_level') == 'L3' for x in routes):
            raise RuntimeError(f'{name}: {json.dumps(entry, ensure_ascii=False)} {log[-400:]}')
        again(H, 'capture', SAFARI, '--helper', '--window', PAGE, '--output', P/f'{len(evidence)-1:02d}-{name}.png')
        entry['capture_front'] = front()

    def menu(app, path, check):
        one = out/'menu.json'
        one.write_text(json.dumps({'schema': 2, 'name': 'direct-cleanup', 'target': app, 'safety_defaults': SAFETY,
                                   'steps': [{'action': 'menu', 'params': {'path': path}, **check}]}, ensure_ascii=False))
        return sh(H, 'run', one, '--helper', '--yes', check=False).returncode == 0

    try:
        time.sleep(1)
        # The page, opened behind (before TextEdit starts: an app starting at the same moment left the page unconfirmed).
        def open_page():
            r = sh(H, 'open-url', URL, '--helper', check=False)
            for _ in range(10):  # page_not_shown: look for the page before anything else (a first window can take a while)
                if r.returncode == 0 or '127.0.0.1:8742' in sh(H, 'windows', SAFARI, '--helper', check=False).stdout: r.returncode = 0; break
                time.sleep(2)
            if r.returncode == 0: again(H, 'resize', SAFARI, '--helper', '--window', PAGE, '--width', 800, '--height', 570)
            return r
        record('open', 'open-url', open_page)
        # The window "in use": a made-up note, opened behind the app in front.
        (folder/'note.html').write_text(NOTE_HTML); sh('textutil', '-convert', 'rtf', folder/'note.html', '-output', note); (folder/'note.html').unlink()
        sh('open', '-g', '-a', 'TextEdit', note); time.sleep(3)
        again(H, 'resize', TEXTEDIT, '--helper', '--window', NOTE, '--width', 470, '--height', 350)
        again(H, 'capture', TEXTEDIT, '--helper', '--window', NOTE, '--output', P/'front.png')
        # One call per field.
        for name, step in steps(row):
            one = out/'one.json'; one.write_text(json.dumps({'schema': 2, 'name': f'direct-{name}', 'target': SAFARI, 'safety_defaults': SAFETY, 'steps': [step]}, ensure_ascii=False))
            def run():
                for _ in range(40):  # a reply with effect not_started sent nothing to the page, so the same call is made again
                    r = sh(H, 'run', one, '--helper', '--yes', *MATCH, check=False)
                    if r.returncode == 0 or '"effect": "not_started"' not in r.stdout+r.stderr: break
                    time.sleep(3)
                return r
            record(name, step['action'], run)
    finally:
        server.terminate()
        # Close what the shoot opened, behind the app in front: the demo tab by its address, the note by TextEdit's own menu.
        sh('osascript', '-e', 'tell application "Safari" to close (every tab of every window whose URL starts with "http://127.0.0.1:8742")', check=False)
        closed = {'safari_tab': '127.0.0.1:8742' not in sh(H, 'windows', SAFARI, '--helper', check=False).stdout,
                  'textedit_note': menu(TEXTEDIT, ['File', 'Close'], {'postcondition': {'absent_role': 'Window'}} if not textedit_was_running else {'unverified_ok': True})}
        if not textedit_was_running: closed['textedit_quit'] = menu(TEXTEDIT, ['TextEdit', 'Quit TextEdit'], {'unverified_ok': True})
        shutil.rmtree(folder, ignore_errors=True)
        for f in ('one.json', 'menu.json'): (out/f).unlink(missing_ok=True)
        ended = front()
        summary = {'shot': time.strftime('%Y-%m-%d'), 'haejo': sh(H, '--version').stdout.strip(),
                   'macos': sh('sw_vers', '-productVersion').stdout.strip(),
                   'safari': sh('defaults', 'read', '/Applications/Safari.app/Contents/Info', 'CFBundleShortVersionString', check=False).stdout.strip(),
                   'front_at_start': began, 'front_at_end': ended, 'front_unchanged': began == ended and all(e['front_unchanged'] for e in evidence),
                   'safari_ever_in_front': any(e['safari_in_front'] for e in evidence) or ended == SAFARI,
                   'front_window_source': 'TextEdit note written by this script (made-up text), opened with open -g, captured by window',
                   'page': 'sites/haejo/film/demo-expense (local demo)',
                   'routes_note': 'set_value steps print HAEJO_ROUTE; a click is an accessibility press (AXPress) and prints a route line only when it moves up to another route', 'row': row, 'steps': evidence, 'closed': closed}
        (out/'evidence.json').write_text(json.dumps(summary, ensure_ascii=False, indent=1)+'\n')
        print(json.dumps({k: summary[k] for k in ('front_at_start', 'front_at_end', 'front_unchanged', 'safari_ever_in_front', 'closed')}))


if __name__ == '__main__':
    main()
