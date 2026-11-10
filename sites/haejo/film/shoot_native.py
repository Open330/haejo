#!/usr/bin/env python3
"""Shoot the film's Calculator plates with the installed Haejo; no mouse or keyboard.

Every pixel comes from the real Calculator window, captured by the signed
helper. For each input set the saved Flow runs one step at a time and the
window is captured after each step, so the plate holds each real state. Then
the whole Flow runs once more as one ordinary replay, and once with a stale
selector under --auto-repair, to record the genuine terminal output and the
activity receipts the film shows. Inputs are 7+8 and 3+9 only.

Output: <out>/calc-<case>/NN.png, <out>/runs.json, <out>/activity/Logs/*.jsonl
"""
import argparse, copy, json, os, shutil, subprocess, time
from pathlib import Path

HERE = Path(__file__).resolve().parent
HAEJO = Path('/Applications/Haejo.app/Contents/Resources/runtime/launcher/haejo')
LOGS = Path.home()/'Library/Application Support/Haejo/Logs'
TARGET = 'com.apple.calculator'
CASES = {'first': {'left_key': 'Seven', 'right_key': 'Eight', 'left': '7', 'right': '8', 'result': '15'},
         'second': {'left_key': 'Three', 'right_key': 'Nine', 'left': '3', 'right': '9', 'result': '12'}}


def params(values):
    return [arg for k, v in values.items() for arg in ('-p', f'{k}={v}')]


def run(flow_path, values, *extra):
    started = time.monotonic()
    r = subprocess.run([str(HAEJO), 'run', str(flow_path), '--helper', *params(values), *extra],
                       capture_output=True, text=True, timeout=300)
    return {'exit': r.returncode, 'seconds': round(time.monotonic()-started, 2),
            'output': [line for line in (r.stdout+r.stderr).splitlines() if line.strip()]}


def capture(path):
    subprocess.run([str(HAEJO), 'capture', TARGET, '--helper', '--output', str(path)],
                   check=True, capture_output=True, timeout=60)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--out', type=Path, required=True)
    a = ap.parse_args(); out = a.out.resolve(); out.mkdir(parents=True, mode=0o700)
    flow = json.loads((HERE/'calculator.flow.json').read_text())
    subprocess.run(['open', '-g', '-a', 'Calculator'], check=True); time.sleep(2)
    for case, values in CASES.items():
        frames = out/f'calc-{case}'; frames.mkdir()
        capture(frames/'00.png')
        for i, step in enumerate(flow['steps']):
            one = copy.deepcopy(flow); one['steps'] = [step]
            path = frames/f'step-{i}.flow.json'; path.write_text(json.dumps(one))
            result = run(path, values); path.unlink()
            assert result['exit'] == 0, (case, i, result)
            capture(frames/f'{i+1:02d}.png')
    # Whole-Flow runs whose output and receipts the film shows.
    receipts_before = set(os.listdir(LOGS)) if LOGS.exists() else set()
    runs = {'first': run(HERE/'calculator.flow.json', CASES['first']),
            'second': run(HERE/'calculator.flow.json', CASES['second'], '--timings')}
    stale = copy.deepcopy(flow); stale['steps'][3]['selector']['identifier'] = 'Plus'
    stale_path = out/'calculator-stale.flow.json'; stale_path.write_text(json.dumps(stale, ensure_ascii=False, indent=1))
    runs['repair'] = run(stale_path, CASES['second'], '--auto-repair', 'claude', '--repair-packet', str(out/'repair-packet.json'))
    assert [r['exit'] for r in runs.values()] == [0, 0, 0], runs
    (out/'runs.json').write_text(json.dumps(runs, ensure_ascii=False, indent=2)+'\n')
    activity = out/'activity/Logs'; activity.mkdir(parents=True)
    for name in sorted(set(os.listdir(LOGS))-receipts_before):
        shutil.copy2(LOGS/name, activity/name)
    print(json.dumps({k: (v['exit'], v['output'][-1]) for k, v in runs.items()}, ensure_ascii=False))


if __name__ == '__main__':
    main()
