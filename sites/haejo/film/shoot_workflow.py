#!/usr/bin/env python3
"""Re-shoot the landing's repeated-workflow clip on the owned AppKit test form.

Builds the test fixture from tests/fixtures/NativeComplexBenchmark.swift with
the window title "Haejo Workflow Demo", then for five input sets replays the
saved 11-step Flow with the installed Haejo, one step at a time, capturing
the window after each step. The fixture's own record must show one completion
per job with the expected result. Writes workflow-replay.mp4,
workflow-result.png and updated workflow marker times in pointer-guide.json;
run ../annotate_recordings.py afterwards for the guided edition.
"""
import argparse, json, os, plistlib, subprocess, sys, tempfile, time, uuid
from pathlib import Path

HERE = Path(__file__).resolve().parent; ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT))
from examples.benchmark_complex_scenarios import recipe, job, params  # noqa: E402

HAEJO = Path('/Applications/Haejo.app/Contents/Resources/runtime/launcher/haejo')
ASSETS = HERE.parent/'dist/assets/demos'
STEP_HOLD, JOB_HOLD, END_HOLD = .25, .9, 2.0


def sh(*args, timeout=180):
    r = subprocess.run([str(a) for a in args], capture_output=True, text=True, timeout=timeout)
    if r.returncode: raise RuntimeError(f'{args[:3]}: {(r.stdout+r.stderr)[-500:]}')
    return r


def main():
    ap = argparse.ArgumentParser(description=__doc__); ap.add_argument('--out', type=Path, required=True)
    a = ap.parse_args(); base = a.out.resolve(); base.mkdir(parents=True)
    target = 'open330.haejo.workflowdemo.'+uuid.uuid4().hex[:8]
    app = base/'Haejo Workflow Demo.app'; binary = app/'Contents/MacOS'; binary.mkdir(parents=True)
    plistlib.dump({'CFBundleIdentifier': target, 'CFBundleName': 'Haejo Workflow Demo', 'CFBundleExecutable': 'WorkflowDemo',
                   'CFBundlePackageType': 'APPL', 'LSUIElement': True}, (app/'Contents/Info.plist').open('wb'))
    source = (ROOT/'tests/fixtures/NativeComplexBenchmark.swift').read_text().replace('"HAEJO Complex Benchmark"', '"Haejo Workflow Demo"')
    swift = base/'WorkflowDemo.swift'; swift.write_text(source)
    sh('swiftc', '-parse-as-library', swift, '-o', binary/'WorkflowDemo'); sh('codesign', '--force', '--sign', '-', app)
    state_dir = base/'fixture'; state_dir.mkdir()
    proc = subprocess.Popen([str(binary/'WorkflowDemo'), str(state_dir)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    flow = json.loads(recipe(target).to_json()); frames = base/'frames'; frames.mkdir(); shots = []; results = []
    try:
        time.sleep(2)
        def capture(hold):
            f = frames/f'{len(shots):03d}.png'; sh(HAEJO, 'capture', target, '--helper', '--output', f); shots.append((f, hold))
        for n in range(1, 6):
            values = job(n, f'job-{n}'); seq = n
            (state_dir/'control.json').write_text(json.dumps({'sequence': seq, 'job': values['job'], 'mode': 'normal', 'version': 1}))
            for _ in range(200):
                try:
                    st = json.loads((state_dir/'oracle.json').read_text())
                    if st['sequence'] == seq and st['phase'] == 'entry': break
                except (OSError, ValueError): pass
                time.sleep(.05)
            if n == 1: capture(JOB_HOLD)
            p = [x for k, v in params(values).items() for x in ('-p', f'{k}={v}')]
            for i, step in enumerate(flow['steps']):
                one = base/'step.flow.json'; one.write_text(json.dumps({**flow, 'steps': [step]}, ensure_ascii=False))
                sh(HAEJO, 'run', one, '--helper', *p); capture(STEP_HOLD if i < len(flow['steps'])-1 else JOB_HOLD)
            st = json.loads((state_dir/'oracle.json').read_text())
            commits = [c for c in st['commits'] if c['sequence'] == seq]
            assert st['phase'] == 'done' and len(commits) == 1 and int(st['result']) == values['result'], st
            results.append(values['result'])
    finally:
        proc.terminate()
    shots[-1] = (shots[-1][0], END_HOLD)
    manifest = base/'concat.txt'
    manifest.write_text(''.join(f"file '{f}'\nduration {h}\n" for f, h in shots)+f"file '{shots[-1][0]}'\n")
    sh('ffmpeg', '-hide_banner', '-loglevel', 'error', '-y', '-f', 'concat', '-safe', '0', '-i', manifest, '-vf', 'fps=24,scale=1220:1004',
       '-c:v', 'libx264', '-crf', '22', '-pix_fmt', 'yuv420p', '-movflags', '+faststart', '-an', ASSETS/'workflow-replay.mp4')
    sh('ffmpeg', '-hide_banner', '-loglevel', 'error', '-y', '-i', shots[-1][0], '-vf', 'scale=1220:1004', ASSETS/'workflow-result.png')
    # Marker n (after the READY marker) belongs to the frame captured after step n.
    guide = json.loads((ASSETS/'pointer-guide.json').read_text()); w = guide['scenarios']['workflow']
    starts, t = [], 0.0
    for _, h in shots: starts.append(round(t, 3)); t += h
    for m, at in zip(w['markers'][1:], starts[1:]): m['time'] = at
    w['seconds'] = round(t, 3); w['poster_marker']['time'] = w['markers'][-1]['time']
    (ASSETS/'pointer-guide.json').write_text(json.dumps(guide, ensure_ascii=False, indent=2)+'\n')
    print(json.dumps({'results': results, 'frames': len(shots), 'seconds': w['seconds']}))


if __name__ == '__main__':
    main()
