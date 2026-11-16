#!/usr/bin/env python3
"""Shoot "two tasks, one Calculator": the second task is told the first is at work, and goes on when it ends.

Everything runs through the installed Haejo. Task A presses 7 + 8 = in a
Calculator that stays behind the app in use. Task B asks for a key of the same
Calculator while A is at work: the reply is target_busy with A's task id and
nothing is pressed. When A's task ends, B asks again and does 3 × 9 =.

Each capture is the Calculator window, taken by the signed helper after a
call. evidence.json keeps, for every call, the app in front on both sides, the
exit code and what B was told; it holds no screen contents, and
an app outside com.apple.* appears as other-app-1.

Calculator is started behind the app in front and quit at the end (the shoot
ends at once when Calculator is already running, so a person's own Calculator
is never used).

  python3 sites/haejo/film/shoot_turns.py --out DIR
  .venv/bin/python sites/haejo/film/render_turns.py --shoot DIR --out CLIP
"""
import argparse, json, re, subprocess, time
from pathlib import Path

H = '/Applications/Haejo.app/Contents/Resources/runtime/launcher/haejo'
CALC = 'com.apple.calculator'
SAFETY = {'effects': ['write_ephemeral'], 'reversibility': 'reversible', 'resource': {'object_type': 'calculator entry', 'scope': 'entry'}}
DISPLAY = {'role': 'ScrollArea', 'identifier': 'StandardInputView', 'in_focused_window': False}
OTHERS = {}


def sh(*args, check=True, env=None):
    r = subprocess.run([str(a) for a in args], capture_output=True, text=True, timeout=300, env=env)
    if check and r.returncode: raise RuntimeError(f'{args[:3]} → {(r.stdout+r.stderr)[-500:]}')
    return r


def front():
    asn = sh('lsappinfo', 'front').stdout.strip()
    bundle = re.search(r'"([^"]*)"', sh('lsappinfo', 'info', '-only', 'bundleid', asn).stdout).group(1)
    return bundle if bundle.startswith('com.apple.') else OTHERS.setdefault(bundle, f'other-app-{len(OTHERS)+1}')


def flow(out, key, shows=None):
    step = {'action': 'click', 'selector': {'role': 'Button', 'identifier': key, 'in_focused_window': False}}
    step.update({'postcondition': {'field': DISPLAY, 'attribute': 'Value', 'equals': shows}} if shows else {'unverified_ok': True})
    one = out/f'key-{key}.json'
    one.write_text(json.dumps({'schema': 2, 'name': f'turns-{key}', 'target': CALC, 'safety_defaults': SAFETY, 'steps': [step]}))
    return one


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--out', type=Path, required=True)
    a = ap.parse_args(); out = a.out.resolve(); P = out/'plates'; P.mkdir(parents=True)
    if sh('pgrep', '-x', 'Calculator', check=False).returncode == 0: raise SystemExit('Calculator is already running. Quit it, then shoot.')
    began = front(); frames = []; tasks = {}

    def frame(name, who, did, a_state, b_state, **more):
        sh(H, 'capture', CALC, '--helper', '--output', P/f'{len(frames):02d}-{name}.png')
        frames.append({'frame': name, 'task': who, 'did': did, 'a': a_state, 'b': b_state, 'front': front(), **more})

    def press(who, key, shows=None):
        before = front(); r = sh(H, 'run', flow(out, key, shows), '--helper', '--yes', '--task', tasks[who], check=False); after = front()
        if r.returncode or before != after or CALC in (before, after): raise RuntimeError(f'{who} {key}: exit {r.returncode}, front {before} → {after} {(r.stdout+r.stderr)[-400:]}')
        return {'exit': r.returncode, 'front_before': before, 'front_after': after}

    try:
        sh('open', '-g', '-b', CALC)
        for _ in range(40):
            if sh(H, 'capture', CALC, '--helper', '--output', P/'probe.png', check=False).returncode == 0: break
            time.sleep(0.5)
        (P/'probe.png').unlink(missing_ok=True)
        for who, goal in (('A', '7 + 8 on Calculator'), ('B', '3 × 9 on Calculator')):
            tasks[who] = json.loads(sh(H, 'task', 'start', f'turns clip: {goal}', '--json').stdout)['task_id']
        frame('start', None, None, 'starts: 7 + 8', 'starts: 3 × 9')
        frame('a-7', 'A', '7', 'pressed 7', 'starts: 3 × 9', **press('A', 'Seven'))
        frame('a-plus', 'A', '+', 'pressed 7 +', 'starts: 3 × 9', **press('A', 'Add'))
        # B asks for a key of the same Calculator while A's task holds it: the reply names A's task and nothing is pressed.
        asked = time.monotonic(); before = front()
        r = sh(H, 'run', flow(out, 'Three'), '--helper', '--yes', '--task', tasks['B'], '--json', check=False); log = r.stdout+r.stderr
        told = {'exit': r.returncode, 'error': 'target_busy' if 'target_busy' in log else 'input_busy' if 'input_busy' in log else None,
                'names_task_a': tasks['A'] in log, 'has_hint': '다른 작업' in log, 'seconds': round(time.monotonic()-asked, 1),
                'front_before': before, 'front_after': front()}
        if not (r.returncode and told['error'] and told['names_task_a']): raise RuntimeError(f'B was not told to wait: {log[-500:]}')
        frame('b-told', 'B', 'asks for 3', 'pressed 7 +', 'told: task A is using Calculator', **told)
        frame('a-8', 'A', '8', 'pressed 7 + 8', 'told: task A is using Calculator', **press('A', 'Eight'))
        frame('a-equals', 'A', '=', '7 + 8 = 15', 'told: task A is using Calculator', **press('A', 'Equals', '15'))
        ended = time.monotonic(); sh(H, 'task', 'end', tasks.pop('A'), '--result', 'done', '--json')
        again = press('B', 'Three')
        frame('b-3', 'B', '3', 'done', 'pressed 3', **again, b_seconds_after_a_ended=round(time.monotonic()-ended, 1))
        frame('b-times', 'B', '×', 'done', 'pressed 3 ×', **press('B', 'Multiply'))
        frame('b-9', 'B', '9', 'done', 'pressed 3 × 9', **press('B', 'Nine'))
        frame('b-equals', 'B', '=', 'done', '3 × 9 = 27', **press('B', 'Equals', '27'))
        sh(H, 'task', 'end', tasks.pop('B'), '--result', 'done', '--json')
        frame('end', None, None, 'done', 'done')
    finally:
        for task in tasks.values(): sh(H, 'task', 'end', task, '--result', 'abandoned', '--json', check=False)
        sh('osascript', '-e', 'tell application id "com.apple.calculator" to quit', check=False)
        for f in out.glob('key-*.json'): f.unlink()
        summary = {'shot': time.strftime('%Y-%m-%d'), 'haejo': sh(H, '--version').stdout.strip(), 'macos': sh('sw_vers', '-productVersion').stdout.strip(),
                   'front_at_start': began, 'front_at_end': front(), 'front_unchanged': all(f['front'] == began for f in frames) and front() == began,
                   'calculator_ever_in_front': any(f['front'] == CALC for f in frames),
                   'frames': frames}
        (out/'evidence.json').write_text(json.dumps(summary, ensure_ascii=False, indent=1)+'\n')
        print(json.dumps({k: summary[k] for k in ('front_at_start', 'front_at_end', 'front_unchanged', 'calculator_ever_in_front')} | {'frames': len(frames)}))


if __name__ == '__main__':
    main()
