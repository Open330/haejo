"""Package the already signed dev helper in a temporary SMAppService host.

Build only. Registration is explicit and must be undone after measurements.
Never installs over /Applications/Haejo.app or the normal command/skills.
"""
import argparse, os, plistlib, shutil, subprocess, tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
AGENT = 'ai.callabo.haejo.prototype.agent'
SERVICE = 'ai.callabo.haejo.prototype.resident'


def build(output, identity, idle_seconds=120):
    if '--resident-agent' not in (ROOT / 'helper/HaejoHelper.swift').read_text():
        raise SystemExit('Resident is spike-only. Build the spike/helper-modes branch in a separate checkout.')
    app = Path(output).absolute() / 'HaejoModes.app'
    if app.exists():
        raise SystemExit('Output exists; unregister the previous host before replacing it')
    helper = ROOT / 'helper/Haejo Helper.app'
    subprocess.run(['codesign', '--verify', '--deep', '--strict', str(helper)], check=True)
    resources = app / 'Contents/Resources'; resources.mkdir(parents=True)
    shutil.copytree(helper, resources / 'Haejo Helper.app', symlinks=True)
    macos = app / 'Contents/MacOS'; macos.mkdir()
    agents = app / 'Contents/Library/LaunchAgents'; agents.mkdir(parents=True)
    with tempfile.TemporaryDirectory(prefix='haejo-mode-host-') as folder:
        source = Path(folder) / 'main.swift'
        shutil.copy2(ROOT / 'spike/helper-modes/Host.swift', source)
        subprocess.run(['xcrun', 'swiftc', '-O', str(source), str(ROOT / 'spike/helper-modes/ResidentProtocol.swift'),
                        '-o', str(macos / 'HaejoModes')], check=True)
    (app / 'Contents/Info.plist').write_bytes(plistlib.dumps({
        'CFBundleIdentifier': 'ai.callabo.haejo.prototype.host', 'CFBundleExecutable': 'HaejoModes',
        'CFBundlePackageType': 'APPL', 'CFBundleVersion': '1', 'LSUIElement': True}))
    (agents / (AGENT + '.plist')).write_bytes(plistlib.dumps({
        'Label': AGENT, 'BundleProgram': 'Contents/Resources/Haejo Helper.app/Contents/MacOS/HaejoHelper',
        'ProgramArguments': ['HaejoHelper', '--resident-agent', '--mode-idle', str(idle_seconds)],
        'MachServices': {SERVICE: True}, 'ProcessType': 'Interactive',
        'AssociatedBundleIdentifiers': ['ai.callabo.haejo.prototype.host']}))
    subprocess.run(['codesign', '--force', '--sign', identity, '--options', 'runtime', '--timestamp=none',
                    '--identifier', 'ai.callabo.haejo.prototype.host', str(app)], check=True)
    subprocess.run(['codesign', '--verify', '--deep', '--strict', str(app)], check=True)
    print(app / 'Contents/MacOS/HaejoModes')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True)
    parser.add_argument('--identity', default=os.environ.get('HAEJO_SIGN_IDENTITY'))
    parser.add_argument('--idle-seconds', type=int, default=120, choices=range(1, 601), metavar='1..600')
    args = parser.parse_args()
    if not args.identity:
        parser.error('--identity or HAEJO_SIGN_IDENTITY is required')
    build(args.output, args.identity, args.idle_seconds)
