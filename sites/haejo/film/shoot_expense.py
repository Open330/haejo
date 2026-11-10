#!/usr/bin/env python3
"""Shoot the film's plates: card expenses entered into a demo groupware page.

Everything runs through the installed Haejo; window captures come from its
signed helper. The groupware page (demo-expense/) is a local demo marked DEMO
on screen; the card rows in data/ are made up.

  1. Other work of the day, each its own task: kickoff notes saved in TextEdit,
     the owned workshop folder sorted in Finder.
  2. Direct use, as an agent calls it: read November's statement in TextEdit,
     then enter its 8 rows (the first field by field, the rest one Flow run
     each), one task with a goal and a reason per call.
  3. The Haejo activity window over those tasks.
  4. expense-entry saved to the library, then December's 6 rows replayed with
     `haejo replay expense-entry -p …`, no model calls.

  python3 sites/haejo/film/shoot_expense.py --out DIR [--folder OWNED_FINDER_FOLDER]
  .venv/bin/python sites/haejo/film/render.py --plates DIR/plates --out FILM --lang ko
"""
import argparse, json, re, shutil, subprocess, time
from pathlib import Path

HERE = Path(__file__).resolve().parent
H = '/Applications/Haejo.app/Contents/Resources/runtime/launcher/haejo'
PAGE = '법인카드 경비 등록 - 데모상사 그룹웨어'
LOGS = Path.home()/'Library/Application Support/Haejo'


def sh(*args, check=True):
    r = subprocess.run([str(a) for a in args], capture_output=True, text=True, timeout=300)
    if check and r.returncode: raise RuntimeError(f'{args[:3]} → {(r.stdout+r.stderr)[-500:]}')
    return r


def safari_run(*args):
    """Run a Safari step; if focus moved and the paste did not start, bring the page back once."""
    r = sh(*args, check=False)
    if r.returncode and "'effect': 'not_started'" in r.stdout+r.stderr and 'paste_target' in r.stdout+r.stderr:
        sh(H, 'activate', 'com.apple.Safari', '--window', '법인카드 경비 등록', '--helper'); r = sh(*args, check=False)
    if r.returncode: raise RuntimeError(f'{args[:3]} → {(r.stdout+r.stderr)[-500:]}')
    return r


def osa(*lines): sh('osascript', *[x for l in lines for x in ('-e', l)])
def task_of(r): return re.search(r't-[0-9a-f]+', r.stdout+r.stderr).group(0)
def params(row): return [x for k, v in row.items() for x in ('-p', f'{k}={v}')]


def statement(rows, month):
    lines = [f'법인카드 사용내역 — 2026년 {month}월 (카드 끝자리 4821)', '', f"{'사용일':<12}{'가맹점':<14}{'금액':>9}   분류 / 프로젝트 / 사용 내용", '-'*64]
    lines += [f"{r['date']:<12}{r['merchant']:<14}{int(r['amount']):>9,}원   {r['category']} / {r['project']} / {r['memo']}" for r in rows]
    return '\n'.join(lines + ['-'*64, f"합계 {sum(int(r['amount']) for r in rows):,}원 ({len(rows)}건)", ''])


def page(month):
    osa('tell application "Safari"', 'close (every window whose name contains "법인카드")',
        f'make new document with properties {{URL:"http://127.0.0.1:8742/?month={month}"}}', 'delay 2',
        'set bounds of front window to {60, 60, 1240, 900}', 'end tell')


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--out', type=Path, required=True); ap.add_argument('--folder', type=Path)
    ap.add_argument('--include-task', action='append', default=[], help='an earlier task of the day to show in the activity frame')
    a = ap.parse_args(); out = a.out.resolve(); F = out/'frames'; P = out/'plates'; F.mkdir(parents=True); P.mkdir()
    nov = json.loads((HERE/'data/2026-11.json').read_text()); dec = json.loads((HERE/'data/2026-12.json').read_text())
    server = subprocess.Popen(['python3', '-m', 'http.server', '8742', '--bind', '127.0.0.1'], cwd=HERE/'demo-expense',
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    def cap(name, app='com.apple.Safari', window=PAGE):
        sh(H, 'capture', app, '--helper', '--window', window, '--output', F/f'{name}.png', check=False)
    tasks = list(a.include_task)
    try:
        time.sleep(1)
        # Close earlier copies of the notes this run creates, so window names stay unique.
        for name in ('고객사-킥오프-회의록.txt', '11월-법인카드-사용내역.txt'):
            osa(f'tell application "TextEdit" to close (every window whose name is "{name}") saving no')
        # 1. Other work of the day.
        note = out/'고객사-킥오프-회의록.txt'; note.write_text(''); sh('open', '-a', 'TextEdit', note); time.sleep(2)
        r = sh(H, 'run', HERE/'data/kickoff-notes.flow.json', '--helper', '--document', note, '--yes', '--task', 'new',
               '--goal', '킥오프 회의록 정리', '--detail', '오늘 고객사 킥오프 회의 내용을 회의록으로 정리해서 저장해줘', '--why', '회의록 본문 작성', check=False)  # TextEdit edits end commit_unverified; the save below verifies
        t = task_of(r); tasks.append(t)
        sh(H, 'activate', 'com.apple.TextEdit', '--window', note.name, '--helper', '--task', t, '--why', '저장하려고 회의록 창을 앞으로')
        sh(H, 'replay', 'textedit_save', '-p', f'document={note}', '-p', f'name={note.name}', '--helper', '--yes', '--task', t,
           '--why', '회의록 저장', '--finish-task')
        if a.folder:
            osa(f'tell application "Finder" to open POSIX file "{a.folder.resolve()}"', 'tell application "Finder" to set current view of front window to list view')
            time.sleep(2)
            r = sh(H, 'run', HERE/'finder.flow.json', '--helper', '--task', 'new', '--goal', '워크숍 자료 폴더 정리',
                   '--detail', '워크숍 자료 폴더를 종류별로 보고 이름순으로 정리해줘', '--why', '종류별, 이름순 정렬', '--finish-task')
            tasks.append(task_of(r))

        # 2. Direct use: the statement, then 8 entries.
        st = out/'11월-법인카드-사용내역.txt'; st.write_text(statement(nov, 11))
        page(11); sh('open', '-a', 'TextEdit', st); time.sleep(2)
        osa(f'tell application "TextEdit" to set bounds of (first window whose name is "{st.name}") to {{1250, 60, 1900, 620}}')
        cap('statement', 'com.apple.TextEdit', st.name); cap('s00')
        r = sh(H, 'observe', 'com.apple.TextEdit', '--helper', '--document', st, '--task', 'new', '--goal', '11월 법인카드 경비 등록',
               '--detail', '11월 법인카드 사용내역 8건을 사내 경비 시스템에 등록해줘', '--why', '카드 사용내역 8건 읽기')
        t = task_of(r); tasks.append(t)
        sh(H, 'activate', 'com.apple.Safari', '--window', '법인카드 경비 등록', '--helper', '--task', t, '--why', '경비 시스템 창을 앞으로')
        flow = json.loads((HERE/'expense-entry.json').read_text())
        labels = ['사용일자 입력', '가맹점명 입력', '비용 분류 선택', '금액 입력', '프로젝트 코드 입력', '사용 내용 입력', '등록']
        for i, step in enumerate(flow['steps']):
            one = out/'one.json'; one.write_text(json.dumps({**flow, 'steps': [step]}, ensure_ascii=False))
            safari_run(H, 'run', one, '--helper', '--yes', '--task', t, '--why', f"1/8 {nov[0]['merchant']} · {labels[i]}", *params(nov[0]))
            cap(f's01-{i+1}')
        for n, row in enumerate(nov[1:], start=2):
            safari_run(H, 'run', HERE/'expense-entry.json', '--helper', '--yes', '--task', t, *params(row),
               '--why', f"{n}/8 {row['merchant']} {int(row['amount']):,}원 등록", *(['--finish-task'] if n == 8 else []))
            cap(f's{n:02d}')

        # 3. Activity window over the day's tasks.
        fx = out/'activity'; (fx/'Logs').mkdir(parents=True); (fx/'Tasks').mkdir()
        for task in tasks:
            for log in (LOGS/'Logs').glob('*.jsonl'):
                try:  # log retention may prune old receipts meanwhile
                    if task in log.read_text(errors='ignore'): shutil.copy2(log, fx/'Logs'/log.name)
                except FileNotFoundError:
                    pass
            shutil.copytree(LOGS/'Tasks'/task, fx/'Tasks'/task)
        sh('/Applications/Haejo.app/Contents/MacOS/HaejoSetup', '--activity-snapshot', out/'act', '--activity-fixture', fx)

        # 4. Save and replay next month.
        sh(H, 'flows', 'save', HERE/'expense-entry.json', '--force')
        page(12); cap('d00'); sh(H, 'activate', 'com.apple.Safari', '--window', '법인카드 경비 등록', '--helper')
        seconds, t = [], None
        for n, row in enumerate(dec, start=1):
            bind = ['--task', 'new', '--goal', '12월 법인카드 경비 등록', '--detail', '저장한 expense-entry Flow로 12월 법인카드 6건 등록'] if t is None else ['--task', t]
            r = safari_run(H, 'replay', 'expense-entry', '--helper', '--yes', '--timings', *params(row), *bind,
                   '--why', f"{n}/6 {row['merchant']} {int(row['amount']):,}원", *(['--finish-task'] if n == len(dec) else []))
            t = t or task_of(r); assert 'PROVIDER' not in r.stdout+r.stderr
            (out/f'replay-{n}.out').write_text(r.stdout+r.stderr)
            seconds.append(next(json.loads(l.split(' ', 1)[1]) for l in (r.stdout+r.stderr).splitlines() if l.startswith('HAEJO_TIMINGS '))['replay_seconds'])
            cap(f'd{n:02d}')
    finally:
        server.terminate()

    # Plates: Safari without its toolbar (the address shows the local demo host).
    for f in [*F.glob('s0*.png'), *F.glob('d0*.png')]:
        sh('ffmpeg', '-v', 'error', '-y', '-i', f, '-vf', 'crop=2360:1575:0:105', P/f.name)
    sh('ffmpeg', '-v', 'error', '-y', '-i', F/'statement.png', '-vf', 'crop=iw:min(ih\\,560):0:0', P/'statement.png')
    shutil.copy2(out/'act/app.png', P/'activity.png')
    (P/'facts.json').write_text(json.dumps({'replay_seconds': round(sum(seconds), 1), 'rows': [round(s, 1) for s in seconds], 'model_calls': 0}))
    print((P/'facts.json').read_text())


if __name__ == '__main__':
    main()
