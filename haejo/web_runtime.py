"""The web runtime: Playwright and Chromium, fetched on request and kept outside the app.

Haejo.app carries neither. `haejo web install` downloads both into the user's
Haejo folder, so each can move to a new version without a new Haejo release and
a Haejo update never replaces them:

    <Haejo data>/Web/site       Playwright and its Python dependencies
    <Haejo data>/Web/browsers   Chromium, as Playwright downloads it
    <Haejo data>/Web/runtime.json

Playwright imports one compiled module, greenlet. The app's signed Python loads
native code only with Haejo's signature, so the app ships greenlet (the
`web-bridge` extra) and everything else is fetched.

`activate()` makes that Playwright importable for this process. A checkout that
installed the `web` extra already has Playwright and is left alone.
"""
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

SCHEMA = 1
INSTALL_TIMEOUT = 1800


def directory():
    from .preferences import product_directory
    return product_directory()/'Web'


def python_tag():
    return f'{sys.version_info.major}.{sys.version_info.minor}'


def read_record(root=None):
    root = Path(root) if root is not None else directory()
    try:
        record = json.loads((root/'runtime.json').read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return None
    return record if type(record) is dict and record.get('schema') == SCHEMA else None


def status(root=None):
    """What is installed, without importing or starting any of it."""
    root = Path(root) if root is not None else directory()
    record = read_record(root)
    site = root/'site'
    browsers = root/'browsers'
    chromium = sorted(p.name for p in browsers.glob('chromium*')) if browsers.is_dir() else []
    installed = record is not None and (site/'playwright').is_dir()
    result = {'type': 'web_runtime', 'installed': installed, 'directory': str(root),
              'playwright': record.get('playwright') if installed else None,
              'python': record.get('python') if installed else None,
              'chromium': chromium, 'ready': False}
    if not installed:
        result['next'] = 'haejo web install'
    elif record.get('python') != python_tag():
        # Playwright's greenlet dependency is compiled for one Python version.
        result['next'] = 'haejo web install'
        result['reason'] = f'installed for Python {record.get("python")}, Haejo now runs Python {python_tag()}'
    elif not chromium:
        result['next'] = 'haejo web install'
        result['reason'] = 'Chromium is not downloaded'
    else:
        result['ready'] = True
    return result


def activate(root=None):
    """Make the fetched Playwright importable here; True when Playwright can be imported."""
    if importlib.util.find_spec('playwright') is not None:
        return True
    root = Path(root) if root is not None else directory()
    current = status(root)
    if not current['installed'] or current['python'] != python_tag():
        return False
    site = str(root/'site')
    if site not in sys.path:
        # After everything Haejo ships: a fetched package never shadows a bundled one.
        sys.path.append(site)
    os.environ['PLAYWRIGHT_BROWSERS_PATH'] = str(root/'browsers')
    importlib.invalidate_caches()
    return importlib.util.find_spec('playwright') is not None


def missing_message():
    return ('web runtime not installed: run `haejo web install` '
            '(downloads Playwright and Chromium into the Haejo data folder)')


def _pip_command():
    """pip as the running Python can start it: its own module, else the wheel Python ships."""
    if importlib.util.find_spec('pip') is not None:
        return [sys.executable, '-m', 'pip']
    import ensurepip
    wheels = sorted((Path(ensurepip.__file__).parent/'_bundled').glob('pip-*.whl'))
    if wheels:
        return [sys.executable, str(wheels[-1]/'pip')]
    uv = shutil.which('uv')
    if uv:
        return [uv, 'pip']
    return None


def _installed_version(site):
    for info in sorted(Path(site).glob('playwright-*.dist-info')):
        return info.name[len('playwright-'):-len('.dist-info')]
    return None


def install(version=None, root=None, run=subprocess.run, emit=print):
    """Download Playwright (latest, or `version`) and its Chromium. Replaces an earlier install."""
    root = Path(root) if root is not None else directory()
    pip = _pip_command()
    if pip is None:
        return {'type': 'error', 'error': 'web_runtime_installer_unavailable', 'effect': 'not_started',
                'detail': 'no pip for this Python and no uv on PATH'}
    if version is not None and not all(part.isdigit() for part in version.split('.')):
        return {'type': 'error', 'error': 'web_runtime_version_invalid', 'effect': 'not_started'}
    root.mkdir(parents=True, exist_ok=True)
    os.chmod(root, 0o700)
    staged = root/'site.new'
    shutil.rmtree(staged, ignore_errors=True)
    requirement = 'playwright' + (f'=={version}' if version else '')
    emit(f'Playwright 받는 중 ({requirement}) …')
    command = [*pip, 'install', '--target', str(staged), '--only-binary', ':all:', requirement]
    if Path(pip[0]).name == 'uv':
        command = [*pip, 'install', '--python', sys.executable, '--target', str(staged), '--only-binary', ':all:', requirement]
    else:
        command[len(pip)+1:len(pip)+1] = ['--disable-pip-version-check', '--no-warn-script-location', '--quiet']
    environment = {k: v for k, v in os.environ.items() if not k.startswith(('PIP_', 'PYTHON'))}
    try:
        fetched = run(command, env=environment, capture_output=True, text=True, timeout=INSTALL_TIMEOUT)
    except (OSError, subprocess.TimeoutExpired) as error:
        shutil.rmtree(staged, ignore_errors=True)
        return {'type': 'error', 'error': 'web_runtime_download_failed', 'effect': 'not_started', 'detail': type(error).__name__}
    found = _installed_version(staged) if fetched.returncode == 0 else None
    if found is None:
        shutil.rmtree(staged, ignore_errors=True)
        return {'type': 'error', 'error': 'web_runtime_download_failed', 'effect': 'not_started',
                'detail': (fetched.stderr or fetched.stdout or '').strip()[-600:]}
    if importlib.util.find_spec('greenlet') is not None:
        # Haejo.app's Python loads only the greenlet signed with the app; keep one copy.
        for extra in [*staged.glob('greenlet'), *staged.glob('greenlet-*.dist-info')]:
            shutil.rmtree(extra, ignore_errors=True)
    browsers = root/'browsers'
    emit(f'Chromium 받는 중 (Playwright {found}) …')
    # First on the path: this step downloads the browser of exactly the Playwright just fetched.
    driver = ('import sys; sys.path.insert(0, sys.argv.pop(1)); sys.argv[0] = "playwright"; '
              'from playwright.__main__ import main; main()')
    try:
        chromium = run([sys.executable, '-I', '-B', '-c', driver, str(staged), 'install', 'chromium'],
                       env=dict(environment, PLAYWRIGHT_BROWSERS_PATH=str(browsers)),
                       capture_output=True, text=True, timeout=INSTALL_TIMEOUT)
    except (OSError, subprocess.TimeoutExpired) as error:
        shutil.rmtree(staged, ignore_errors=True)
        return {'type': 'error', 'error': 'web_runtime_browser_download_failed', 'effect': 'not_started', 'detail': type(error).__name__}
    if chromium.returncode:
        shutil.rmtree(staged, ignore_errors=True)
        return {'type': 'error', 'error': 'web_runtime_browser_download_failed', 'effect': 'not_started',
                'detail': (chromium.stderr or chromium.stdout or '').strip()[-600:]}
    # The earlier Playwright stays usable until the new one and its browser are both on disk.
    site = root/'site'
    retired = root/'site.old'
    shutil.rmtree(retired, ignore_errors=True)
    if site.exists():
        site.rename(retired)
    staged.rename(site)
    shutil.rmtree(retired, ignore_errors=True)
    record = {'schema': SCHEMA, 'playwright': found, 'python': python_tag(),
              'installed_at': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}
    temporary = root/'runtime.json.new'
    temporary.write_text(json.dumps(record, indent=2)+'\n', encoding='utf-8')
    temporary.replace(root/'runtime.json')
    return status(root)


def remove(root=None):
    root = Path(root) if root is not None else directory()
    existed = root.is_dir() and not root.is_symlink()
    if existed:
        shutil.rmtree(root)
    return {'type': 'web_runtime', 'installed': False, 'removed': existed, 'directory': str(root)}


USAGE = '''usage: haejo web status [--json]                       what is installed and where
       haejo web install [--playwright X.Y.Z] [--json]  download Playwright (latest unless named) and its Chromium
       haejo web remove [--json]                        delete the downloaded web runtime
Playwright and Chromium are not part of Haejo.app; `haejo web-upload` uses the ones installed here.
Run install again to move to a newer Playwright.'''


def main(argv):
    args = list(argv)
    structured = '--json' in args
    args = [a for a in args if a != '--json']
    if not args or args[0] in ('--help', '-h', 'help'):
        print(USAGE)
        return 0 if args else 2
    action, rest = args[0], args[1:]
    if action == 'status' and not rest:
        result = status()
    elif action == 'install' and (not rest or (len(rest) == 2 and rest[0] == '--playwright')):
        result = install(rest[1] if rest else None,
                         emit=(lambda text: print(text, file=sys.stderr, flush=True)) if structured
                         else (lambda text: print(text, flush=True)))
    elif action == 'remove' and not rest:
        result = remove()
    else:
        print(USAGE)
        return 2
    if structured:
        print(json.dumps(result, ensure_ascii=False))
    elif result['type'] == 'error':
        print(f"{result['error']}: {result.get('detail', '')}".rstrip(': '))
    elif result.get('removed') is not None:
        print('웹 실행 환경을 지웠습니다.' if result['removed'] else '지울 웹 실행 환경이 없습니다.')
    elif result['ready']:
        print(f"웹 실행 환경 준비됨 — Playwright {result['playwright']}, {', '.join(result['chromium'])}\n  {result['directory']}")
    else:
        print('웹 실행 환경이 준비되지 않았습니다' + (f" ({result['reason']})" if result.get('reason') else '')
              + f". 다음: {result['next']}")
    return 1 if result['type'] == 'error' else 0
