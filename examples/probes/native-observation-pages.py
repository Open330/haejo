"""Owned AppKit continuation probe; fixed and live-model evidence stay separate.

Creates/terminates only its own disposable app. A receiving-side JSON oracle
counts actual button callbacks independently of the planner and AX tree.
"""
from pathlib import Path
import argparse
import hashlib
import json
import os
import plistlib
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
TARGET = 'ai.callabo.tacto.observation-pages-fixture'


def run_probe(driver, *, provider='fixed', budget=4000):
    from unittest.mock import patch
    from AppKit import NSRunningApplication
    from tacto.ask import ask_here_paged
    import tacto.ask as ask_module
    from tacto.general import run
    from tacto.input_audit_process import ProcessInputAudit
    from tacto.provider_observation import summarize_provider_calls
    import tiktoken

    counter = tiktoken.get_encoding('o200k_base').encode_ordinary
    sources = [*ROOT.glob('tacto/*.py'), *ROOT.glob('helper/*.swift'),
               Path(__file__), ROOT/'tests/fixtures/NativeObservationPagesFixture.swift',
               ROOT/'helper/Tacto Helper.app/Contents/MacOS/TactoHelper']
    hashes = lambda: {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                       for p in sources if p.is_file()}
    report = {'passed': False, 'evaluation_kind': 'fixed_owned_appkit' if provider == 'fixed' else 'live_model_owned_appkit',
              'provider_requested': provider, 'transport': type(driver).__name__,
              'prompt_budget': budget, 'serving_tokenizer_verified': False,
              'comparison_eligible': False, 'physical_typing_preservation_verified': False,
              'plans': [], 'prompt_tokens': [], 'native_actions': []}
    original_ask = ask_module.ask
    def measured_ask(question, *args, **kwargs):
        guard = kwargs['_request_guard']
        def measured_guard(prompt, attempt):
            guard(prompt, attempt)
            report['prompt_tokens'].append(len(counter(prompt)))
        kwargs['_request_guard'] = measured_guard
        return original_ask(question, *args, **kwargs)

    original_observe, original_act = driver.observe, driver.act
    def observe(*args, **kwargs):
        value = original_observe(*args, **kwargs)
        report.setdefault('observations', []).append({
            'type': value.get('type'), 'error': value.get('error'),
            'continued': kwargs.get('continuation') is not None,
            'has_next': bool(value.get('next_observation_cursor')),
            'target_present': 'tacto-pages-Item239' in value.get('tree', ''),
            'truncated': value.get('truncated')})
        return value
    def act(*args, **kwargs):
        entry = {'action': dict(args[2]), 'status': 'attempted'}
        report['native_actions'].append(entry)
        value = original_act(*args, **kwargs)
        entry.update(status='returned', result=value)
        return value
    driver.observe, driver.act = observe, act
    process = None
    audit = None
    started = time.monotonic()
    report['source_before'] = hashes()
    try:
        with tempfile.TemporaryDirectory(prefix='tacto-observation-pages-') as folder:
            base = Path(folder)
            app = base/'ObservationPages.app'
            binary = app/'Contents/MacOS/ObservationPages'
            binary.parent.mkdir(parents=True)
            (app/'Contents/Info.plist').write_bytes(plistlib.dumps({
                'CFBundleIdentifier': TARGET, 'CFBundleExecutable': binary.name,
                'CFBundleName': 'Tacto Observation Pages Fixture', 'CFBundlePackageType': 'APPL',
                'LSUIElement': True}))
            subprocess.run(['xcrun', 'swiftc', '-parse-as-library',
                            str(ROOT/'tests/fixtures/NativeObservationPagesFixture.swift'),
                            '-o', str(binary)], check=True, capture_output=True, timeout=60)
            subprocess.run(['codesign', '--force', '--sign', '-', str(app)],
                           check=True, capture_output=True, timeout=30)
            oracle = base/'receiving.json'
            process = subprocess.Popen([str(binary), str(oracle)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            try:
                deadline = time.monotonic()+15
                while True:
                    running = NSRunningApplication.runningApplicationWithProcessIdentifier_(process.pid)
                    if (oracle.exists() and running and running.bundleIdentifier() == TARGET
                            and running.isFinishedLaunching()):
                        break
                    if time.monotonic() >= deadline:
                        raise RuntimeError('owned_fixture_not_ready')
                    time.sleep(.05)
                report['initial_oracle'] = json.loads(oracle.read_text())
                def plan(goal, cands, history):
                    if provider == 'fixed':
                        selected = json.loads(oracle.read_text())
                        desired = 'tacto-pages-result' if selected['count'] else 'tacto-pages-Item239'
                        found = next((c for c in cands if c.get('match') == desired or desired in c.get('line', '')), None)
                        if found:
                            answer = {'actions': [{'candidate': found, 'do': 'read' if selected['count'] else 'click'}],
                                      'finishes': bool(selected['count'])}
                        else:
                            more = next((c for c in cands if c.get('_observation_page')), None)
                            if more is None:
                                raise RuntimeError('omitted_target_without_continuation')
                            answer = {'actions': [{'candidate': more, 'do': 'read'}]}
                    else:
                        answer = ask_here_paged(goal, cands, history, provider=provider,
                                                budget=budget, max_pages=8,
                                                token_counter=lambda text: len(counter(text)))
                    report['plans'].append({'labels': [c['label'] for c in cands],
                        'actions': [{'do': a['do'], 'label': a['candidate']['label']} for a in (answer or {}).get('actions', [])],
                        'stop_reason': (answer or {}).get('stop_reason')})
                    return answer
                audit = ProcessInputAudit(interval=.01, startup_timeout=10, stop_timeout=3, max_samples=25000)
                with audit, patch.object(ask_module, 'ask', side_effect=measured_ask):
                    result = run(driver, TARGET,
                        'Click the button Item239 exactly once, then read the result display. '
                        'Do not click any other button. If the target is absent, inspect the omitted observation candidates.',
                        plan, max_screens=12, timeout_seconds=160)
                report.update(loop_ok=result.ok, verified=result.verified, why=result.why,
                              stop_reason=result.stop_reason, observation_pages=result.observation_pages,
                              said=result.said, provider_calls=result.provider_calls,
                              provider_summary=summarize_provider_calls(result.provider_calls),
                              audit=audit.report(), final_oracle=json.loads(oracle.read_text()))
                report['passed'] = (result.ok and result.verified and result.observation_pages >= 3
                    and report['initial_oracle'] == {'count': 0, 'selected': ''}
                    and report['final_oracle'] == {'count': 1, 'selected': 'Item239'}
                    and 'Picked Item239 count 1' in result.said
                    and report['audit']['status'] == 'UNCHANGED_SAMPLED'
                    and all(n <= budget for n in report['prompt_tokens'])
                    and report['observations'][0]['target_present'] is False)
            finally:
                process.terminate()
                process.wait(timeout=10)
                report['owned_fixture_exited'] = process.poll() is not None
    except Exception as error:
        report.update(passed=False, error_class=type(error).__name__)
    finally:
        driver.observe, driver.act = original_observe, original_act
        report['source_after'] = hashes()
        report['source_unchanged'] = report['source_before'] == report['source_after']
        report['passed'] = report['passed'] and report['source_unchanged'] and report.get('owned_fixture_exited', False)
        report['seconds'] = time.monotonic()-started
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--transport', choices=('direct', 'helper'), default='helper')
    parser.add_argument('--provider', choices=('fixed', 'codex', 'claude'), default='fixed')
    parser.add_argument('--budget', type=int, default=4000)
    args = parser.parse_args()
    descriptor = os.open(args.output, os.O_WRONLY|os.O_CREAT|os.O_EXCL, 0o600)
    with os.fdopen(descriptor, 'w') as stream:
        try:
            from tacto.driver import Driver
            from tacto.helper import InheritedHelperDriver
            if args.transport == 'helper' and not InheritedHelperDriver.available():
                raise RuntimeError('Use launcher/tacto eval native_observation_pages_fixed for the signed path')
            driver = Driver() if args.transport == 'direct' else InheritedHelperDriver()
            try:
                report = run_probe(driver, provider=args.provider, budget=args.budget)
            finally:
                driver.close()
        except Exception as error:
            report = {'passed': False, 'error_class': type(error).__name__}
        json.dump(report, stream, ensure_ascii=False, indent=2)
        stream.write('\n')
    print(json.dumps({'passed': report['passed'], 'output': str(args.output)}))
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
