"""Exercise the normal CLI session against an owned 240-control AppKit app.

The launcher may be a source build or an installed app. No runtime is patched.
This sends page requests before one deterministic Flow and checks the receiving
app independently. It never retries that Flow, including after a lost reply.
"""
from pathlib import Path
import argparse
import hashlib
import json
import os
import plistlib
import pty
import select
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
TARGET = 'open330.haejo.observation-pages-fixture'


def check(launcher):
    from AppKit import NSRunningApplication
    from haejo.contract import Envelope
    from haejo.flow import Flow, Step, Selector
    report = {'passed': False, 'flow_submissions': 0, 'model_calls_requested': 0,
              'launcher': str(launcher), 'launcher_sha256': hashlib.sha256(launcher.read_bytes()).hexdigest(),
              'scope': 'real signed CLI session; owned AppKit receiving oracle; no Save or external action',
              'observations': []}
    child = fixture = None
    master = slave = None
    buffer = b''
    transcript = bytearray()
    try:
        with tempfile.TemporaryDirectory(prefix='haejo-session-pages-') as folder:
            base = Path(folder)
            app = base/'ObservationPages.app'
            binary = app/'Contents/MacOS/ObservationPages'
            binary.parent.mkdir(parents=True)
            (app/'Contents/Info.plist').write_bytes(plistlib.dumps({
                'CFBundleIdentifier': TARGET, 'CFBundleExecutable': binary.name,
                'CFBundleName': 'Haejo Observation Pages Fixture', 'CFBundlePackageType': 'APPL',
                'LSUIElement': True}))
            subprocess.run(['xcrun', 'swiftc', '-parse-as-library',
                            str(ROOT/'tests/fixtures/NativeObservationPagesFixture.swift'), '-o', str(binary)],
                           check=True, capture_output=True, timeout=60)
            subprocess.run(['codesign', '--force', '--sign', '-', str(app)], check=True, capture_output=True, timeout=30)
            oracle = base/'receiving.json'
            fixture = subprocess.Popen([str(binary), str(oracle)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            try:
                deadline = time.monotonic()+15
                while True:
                    running = NSRunningApplication.runningApplicationWithProcessIdentifier_(fixture.pid)
                    if oracle.exists() and running and running.bundleIdentifier() == TARGET and running.isFinishedLaunching():
                        break
                    if time.monotonic() >= deadline:
                        raise RuntimeError('owned_fixture_not_ready')
                    time.sleep(.05)
                report['initial_oracle'] = json.loads(oracle.read_text())
                master, slave = pty.openpty()
                child = subprocess.Popen([str(launcher), 'session', TARGET, '--helper', '--guide', '--idle-timeout', '60'],
                                         stdin=slave, stdout=slave, stderr=slave, start_new_session=True)
                os.close(slave)
                slave = None

                def receive_ready():
                    nonlocal buffer
                    deadline = time.monotonic()+65
                    latest = None
                    while time.monotonic() < deadline:
                        if b'\n' not in buffer:
                            if not select.select([master], [], [], min(.5, deadline-time.monotonic()))[0]:
                                continue
                            chunk = os.read(master, 65536)
                            if not chunk:
                                raise RuntimeError('session_output_closed')
                            transcript.extend(chunk)
                            buffer += chunk
                            continue
                        line, buffer = buffer.split(b'\n', 1)
                        text = line.decode('utf-8', errors='replace').strip()
                        if text.startswith('{'):
                            value = json.loads(text)
                            if value.get('type') == 'observation':
                                if 'next_observation_cursor' in value:
                                    raise RuntimeError('live_cursor_exposed_to_author')
                                latest = value
                                report['observations'].append({
                                    'target_present': 'haejo-pages-Item239' in value['tree'],
                                    'has_more': value.get('has_more_observation', False)})
                        if text.startswith('session_invalid_flow:'):
                            raise RuntimeError('authoring_command_rejected')
                        if text.startswith('HAEJO_SESSION_READY'):
                            if latest is None:
                                raise RuntimeError('ready_without_new_observation')
                            return latest
                    raise TimeoutError('session_observation_timeout')

                page = receive_ready()
                report['initial_target_absent'] = 'haejo-pages-Item239' not in page['tree']
                for _ in range(8):
                    if 'haejo-pages-Item239' in page['tree']:
                        break
                    if not page.get('has_more_observation'):
                        raise RuntimeError('omitted_target_without_next_page')
                    os.write(master, b'{"observe_next":true}\n')
                    page = receive_ready()
                if 'haejo-pages-Item239' not in page['tree']:
                    raise RuntimeError('target_not_reached_within_page_limit')
                safety = Envelope.minimal().contract_for({'write_ephemeral'}, 'Click Item239 once in the owned fixture')
                flow = Flow('owned-page-click', TARGET,
                            [Step('click', selector=Selector(role='Button', title='Item239'), safety=safety)], schema=2)
                payload = (flow.to_json(compact=True)+'\n').encode()
                # One small record; no repeated writes after any unknown result.
                if len(payload) > 3000:
                    raise RuntimeError('probe_flow_unexpectedly_large')
                report['flow_submissions'] = 1
                written = os.write(master, payload)
                if written != len(payload):
                    raise RuntimeError('partial_flow_submission')
                deadline = time.monotonic()+65
                while child.poll() is None and time.monotonic() < deadline:
                    if select.select([master], [], [], .1)[0]:
                        try:
                            transcript.extend(os.read(master, 65536))
                        except OSError:
                            break
                report['exit_code'] = child.wait(timeout=max(.1, deadline-time.monotonic()))
                report['final_oracle'] = json.loads(oracle.read_text())
                report['guide_count'] = transcript.count(b'HAEJO_FLOW_GUIDE')
                report['passed'] = (report['exit_code'] == 0 and report['initial_target_absent']
                    and report['guide_count'] == 1 and len(report['observations']) >= 4
                    and report['initial_oracle'] == {'count': 0, 'selected': ''}
                    and report['final_oracle'] == {'count': 1, 'selected': 'Item239'})
            finally:
                if child and child.poll() is None:
                    child.terminate()
                    child.wait(timeout=10)
                fixture.terminate()
                fixture.wait(timeout=10)
                report['owned_fixture_exited'] = fixture.poll() is not None
    except Exception as error:
        report.update(passed=False, error_class=type(error).__name__)
    finally:
        for descriptor in (master, slave):
            if descriptor is not None:
                os.close(descriptor)
        report['transcript_sha256'] = hashlib.sha256(transcript).hexdigest()
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--launcher', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    with args.output.open('x') as stream:
        report = check(args.launcher.resolve())
        json.dump(report, stream, ensure_ascii=False, indent=2)
        stream.write('\n')
    print(json.dumps({'passed': report['passed'], 'report': str(args.output)}))
    raise SystemExit(0 if report['passed'] else 1)
