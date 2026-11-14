"""Build a relocatable developer preview from the trusted local runtime.

No install, GUI launch, permission request, download or notarization. This copies
local dependencies; their release licensing/platform compatibility needs a
separate audit. Output is reserved before work and never replaces an existing app.
"""
import argparse
import configparser
from email.parser import Parser
import hashlib
import time
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parent.parent
MAGICS = {bytes.fromhex(x) for x in ('feedface','cefaedfe','feedfacf','cffaedfe','cafebabe','bebafeca')}



def shipped_docs(directory, names):
    """Docs the app carries: everything but the demo recordings.

    The recordings under docs/assets/demos are for the README; copied into the
    app (twice, through skill/docs) they added 14 MB to the 1.0.2 download.
    """
    skipped = ignored(directory, names)
    if Path(directory).name == 'assets' and Path(directory).parent.name == 'docs':
        skipped += [name for name in names if name == 'demos']
    return skipped


def deployment_target():
    """The macOS floor shared with helper/build.sh and launcher/build.sh."""
    match = re.search(r'^HAEJO_MACOS_TARGET=(\d+\.\d+)$', (ROOT/'signing.sh').read_text(), re.M)
    if not match:
        raise RuntimeError('signing.sh does not state HAEJO_MACOS_TARGET')
    return match.group(1)


def swift_target():
    return f'{platform.machine()}-apple-macos{deployment_target()}'


def require_deployment_target(paths, run=subprocess.run):
    """Every Swift binary Haejo compiles starts on the stated macOS floor."""
    expected = deployment_target()
    for path in paths:
        listing = run(['vtool', '-show-build', str(path)], check=True, capture_output=True, text=True).stdout
        found = re.findall(r'^\s*minos (\S+)$', listing, re.M)
        if not found or any(value != expected for value in found):
            raise RuntimeError(f'{Path(path).name} targets macOS {found or "unknown"}, not {expected}')
    return expected


def ignored(directory, names):
    return [n for n in names if n == '__pycache__' or n.endswith(('.pyc','.pyo','.pth'))
            or n.startswith('__editable__') or n == 'direct_url.json']


def native_files(directory):
    for path in sorted(directory.rglob('*')):
        if path.is_symlink() or not path.is_file():continue
        with path.open('rb') as stream:magic=stream.read(4)
        if magic in MAGICS:yield path


def normalize_python_metadata(runtime, original_prefix):
    """Remove the build machine prefix from copied build-time metadata only."""
    changed = 0
    for path in (runtime/'.venv/lib').glob('python*/_sysconfigdata*.py'):
        before = path.read_text()
        after = before.replace(str(original_prefix), '/opt/haejo-runtime')
        if after != before:
            path.write_text(after)
            changed += 1
    return changed


def require_private_paths_absent(directory, prefixes):
    needles = [str(path).encode() for path in prefixes if str(path) not in ('', '/')]
    scanned = 0
    for path in directory.rglob('*'):
        if path.is_file() and not path.is_symlink():
            scanned += 1
            data = path.read_bytes()
            if any(needle in data for needle in needles):
                raise RuntimeError('private_build_path_in_bundle')
    return scanned


def compile_setup(executable, folder):
    # Swift's prefix-map does not rewrite every #filePath string literal.
    # Relative input names keep those literals independent of the build host.
    sources = folder/'setup-source'
    sources.mkdir()
    for name in ('main.swift', 'PermissionState.swift', 'ActivityCenter.swift', 'ApprovalCenter.swift'):
        shutil.copy2(ROOT/'setup'/name, sources/name)
    shutil.copy2(ROOT/'RuntimeStatus.swift', sources/'RuntimeStatus.swift')
    run(['swiftc', '-target', swift_target(), '-file-prefix-map', str(ROOT)+'=/haejo-source',
         'main.swift', 'PermissionState.swift', 'ActivityCenter.swift', 'ApprovalCenter.swift', 'RuntimeStatus.swift', '-o', str(executable)], cwd=sources)


def bundled_import_valid(data, runtime):
    try:
        root=runtime.resolve(strict=True)
        if type(data) is not dict or not all(isinstance(data.get(key),str)
                and Path(data[key]).resolve(strict=True).is_relative_to(root) for key in ('haejo','prefix','helper')):
            return False
        helper = root/'helper/Haejo Helper.app/Contents/MacOS/HaejoHelper'
        return helper.is_file() and Path(data['helper']).resolve(strict=True) == helper.resolve(strict=True)
    except (OSError,RuntimeError,ValueError):return False


def requirement(identifier, signed_reference=None):
    reference = signed_reference or ROOT/'helper/Haejo Helper.app'
    result = subprocess.run(['codesign','-dv','--verbose=4',str(reference)],
                            capture_output=True,text=True,check=True)
    match = re.search(r'^TeamIdentifier=([A-Z0-9]{10})$', result.stderr, re.M)
    if not match or not re.fullmatch(r'[A-Za-z0-9.-]+',identifier):
        raise RuntimeError('valid Apple signing team/identifier unavailable')
    return f'identifier "{identifier}" and anchor apple generic and certificate leaf[subject.OU] = "{match[1]}"'


def run(argv, **kwargs):
    return subprocess.run(argv,check=True,capture_output=True,text=True,timeout=120,**kwargs)


def refresh_distribution_metadata(runtime, work):
    """Build current project metadata; never ship the build host's stale README or entry points."""
    source = work/'metadata-source'
    source.mkdir()
    for name in ('pyproject.toml', 'README.md', 'LICENSE'):
        if (ROOT/name).is_file():
            shutil.copy2(ROOT/name, source/name)
    shutil.copytree(ROOT/'haejo', source/'haejo', ignore=ignored)
    wheels = work/'metadata-wheel'
    run(['uv', 'build', '--wheel', '--offline', '--out-dir', str(wheels), str(source)])
    wheel, = wheels.glob('haejo_runtime-*.whl')
    sites = list((runtime/'.venv/lib').glob('python*/site-packages'))
    if len(sites) != 1:
        raise RuntimeError('runtime site-packages is ambiguous')
    site = sites[0]
    # Remove command wrappers advertised by the old *owned* distribution,
    # including retired command aliases. Only the signed launcher is shipped.
    for metadata in site.glob('*.dist-info'):
        metadata_file = metadata/'METADATA'
        if not metadata_file.is_file():
            continue
        name = Parser().parsestr(metadata_file.read_text()).get('Name', '')
        # Retired distribution removal is migration cleanup, never an alias.
        if name not in ('haejo-runtime', 'nlc'):
            continue
        entries = metadata/'entry_points.txt'
        parser = configparser.ConfigParser()
        if entries.is_file():
            parser.read(entries)
        if name == 'nlc' and parser.get('console_scripts', 'nlc', fallback='') != 'nlc.cli:main':
            raise RuntimeError('unrecognized retired project distribution')
        if entries.is_file():
            for name in parser['console_scripts'] if parser.has_section('console_scripts') else ():
                if Path(name).name != name or name in ('.', '..'):
                    raise RuntimeError('invalid owned console script')
                script = runtime/'.venv/bin'/name
                if script.is_file() or script.is_symlink():
                    script.unlink()
        shutil.rmtree(metadata)
    with zipfile.ZipFile(wheel) as archive:
        for member in archive.namelist():
            parts = Path(member).parts
            if not parts or not parts[0].startswith('haejo_runtime-') or not parts[0].endswith('.dist-info'):
                continue
            if '..' in parts or member.startswith('/'):
                raise RuntimeError('invalid wheel metadata path')
            target = site/member
            if member.endswith('/'):
                target.mkdir(parents=True, exist_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(archive.read(member))
    return wheel.name


def sign(path, identity, identifier=None, req=None):
    argv=['codesign','--force','--sign',identity,'--options','runtime','--timestamp=none']
    if identifier:argv+=['--identifier',identifier]
    if req:argv+=['-r=designated => '+req]
    run([*argv,str(path)])


# Present in the copied runtime but never used by Haejo: the base Python's own
# installer (the bundled runtime installs nothing) and pyobjc-core's test
# package. Together ~28 MB of every install.
UNSHIPPED = ('pip', 'PyObjCTest')


def remove_unshipped(venv):
    removed = []
    for site in Path(venv).glob('lib/python*/site-packages'):
        for path in sorted(site.iterdir()):
            name = path.name
            if name in UNSHIPPED or (name.startswith('pip-') and name.endswith('.dist-info')):
                shutil.rmtree(path) if path.is_dir() and not path.is_symlink() else path.unlink()
                removed.append(name)
    for script in sorted(Path(venv).glob('bin/pip*')):
        script.unlink(); removed.append('bin/' + script.name)
    return removed


def build(output, identity):
    if platform.system()!='Darwin':raise RuntimeError('macOS required')
    began=time.monotonic()
    def sources():
        paths=[ROOT/name for name in ('pyproject.toml','README.md','setup/build_standalone_preview.py','setup/main.swift',
            'setup/PermissionState.swift','setup/ActivityCenter.swift','setup/ApprovalCenter.swift','docs/assets/haejo-app.icns','docs/assets/haejo-logo.svg',
            'docs/assets/haejo-menu-template.svg','helper/bundle.sh',
            'launcher/haejo.swift','launcher/HelperModeClient.swift','HelperModeProtocol.swift','RuntimeStatus.swift','SigningPolicy.swift','signing.sh','skill/install.sh','skill/SKILL.md',
            'helper/Haejo Helper.app/Contents/MacOS/HaejoHelper','helper/Haejo Helper.app/Contents/Info.plist')]
        paths+=sorted((ROOT/'haejo').glob('*.py'))
        return {str(path.relative_to(ROOT)):hashlib.sha256(path.read_bytes()).hexdigest() for path in paths}
    output=Path(output).absolute()
    if output.suffix!='.app' or not output.parent.is_dir():raise ValueError('new .app in existing directory required')
    # mkdir is exclusive even for a dangling symlink; a partial failure remains
    # explicitly reserved, with no executable app copied into it.
    output.mkdir(mode=0o700)
    before=sources()
    report={'scope':'local_relocatable_developer_preview','architecture':platform.machine(),
            'notarized':False,'gui_launched':False,'installed':False,'macos_version':platform.mac_ver()[0]}
    with tempfile.TemporaryDirectory(prefix='haejo-standalone-build-',dir=output.parent) as folder:
        app=Path(folder)/output.name;contents=app/'Contents';resources=contents/'Resources'
        resources.mkdir(parents=True);(contents/'MacOS').mkdir()
        runtime=resources/'runtime';runtime.mkdir()
        info=json.loads(run([str(ROOT/'.venv/bin/python'),'-I','-B','-c',
            'import sys,json; print(json.dumps({"base":sys.base_prefix,"version":sys.version_info[:2]}))']).stdout)
        base=Path(info['base']).resolve();version='.'.join(map(str,info['version']))
        shutil.copytree(base,runtime/'.venv',symlinks=True,ignore=ignored)
        site=runtime/'.venv/lib'/('python'+version)/'site-packages'
        site.mkdir(parents=True,exist_ok=True)
        shutil.copytree(ROOT/'.venv/lib'/('python'+version)/'site-packages',site,
                        dirs_exist_ok=True,symlinks=True,ignore=ignored)
        if (site/'haejo').exists():shutil.rmtree(site/'haejo')
        shutil.copytree(ROOT/'haejo',site/'haejo',ignore=ignored)
        report['distribution_metadata_wheel'] = refresh_distribution_metadata(runtime, Path(folder))
        report['python_metadata_normalized'] = normalize_python_metadata(runtime, base)
        report['unshipped_removed'] = remove_unshipped(runtime/'.venv')
        # A dylib's install ID is build metadata too; preserve relocatable loads.
        for library in (runtime/'.venv/lib').glob('libpython*.dylib'):
            run(['install_name_tool', '-id', '@rpath/'+library.name, str(library)])
        # Ship deterministic checked-hash bytecode before sealing the bundle.
        # -B at every owned runtime entry reads these caches but never creates
        # new files inside the signed app on a user's first command.
        run([str(runtime/'.venv/bin/python'),'-I','-B','-m','compileall','-q',
             '--invalidation-mode','checked-hash','-s',str(runtime/'.venv'),
             '-p','haejo-runtime',str(runtime/'.venv')])
        report['precompiled_python_files']=sum(1 for _ in (runtime/'.venv').rglob('*.pyc'))
        # Only shipped skill/docs; never copy mutable local flows or reviews.
        shutil.copytree(ROOT/'skill',runtime/'skill',symlinks=False,ignore=shipped_docs)
        shutil.copytree(ROOT/'docs',runtime/'docs',symlinks=False,ignore=shipped_docs)
        (runtime/'helper').mkdir()
        shutil.copytree(ROOT/'helper/Haejo Helper.app',runtime/'helper/Haejo Helper.app',symlinks=True)
        run(['codesign','--verify','--deep','--strict','-R='+requirement('open330.haejo.helper'),str(runtime/'helper/Haejo Helper.app')])
        for path in runtime.rglob('*'):
            if path.is_symlink():
                try:path.resolve(strict=True).relative_to(runtime.resolve())
                except (ValueError,OSError):raise RuntimeError('runtime symlink escapes or is broken') from None
        (runtime/'launcher').mkdir()
        launcher=runtime/'launcher/haejo'
        launcher_source=Path(folder)/'launcher-source';launcher_source.mkdir()
        shutil.copy2(ROOT/'launcher/haejo.swift',launcher_source/'main.swift')
        run(['swiftc','-O','-target',swift_target(),'-file-prefix-map',str(ROOT)+'=/haejo-source',str(launcher_source/'main.swift'),str(ROOT/'SigningPolicy.swift'),str(ROOT/'HelperModeProtocol.swift'),str(ROOT/'RuntimeStatus.swift'),str(ROOT/'launcher/HelperModeClient.swift'),'-o',str(launcher)])
        sign(launcher,identity,'open330.haejo',requirement('open330.haejo'))
        run(['codesign','--verify','-R='+requirement('open330.haejo'),str(launcher)])
        native=list(native_files(runtime/'.venv'))
        # Native extensions/dylibs before the interpreter, all same identity.
        for path in sorted(native,key=lambda p:(p.parent.name=='bin',str(p))):sign(path,identity)
        report['native_runtime_files_signed']=len(native)
        executable=contents/'MacOS/HaejoSetup'
        for name in ('haejo-app.icns','haejo-logo.svg','haejo-menu-template.svg'):
            shutil.copy2(ROOT/'docs/assets'/name,resources/name)
        # The embedded permission holder keeps its identity and requirement,
        # but receives the same product icon instead of a generic application.
        import plistlib
        helper_app=runtime/'helper/Haejo Helper.app'
        helper_resources=helper_app/'Contents/Resources'
        helper_resources.mkdir(exist_ok=True)
        shutil.copy2(ROOT/'docs/assets/haejo-app.icns',helper_resources/'haejo-app.icns')
        helper_plist=helper_app/'Contents/Info.plist'
        helper_info=plistlib.loads(helper_plist.read_bytes())
        helper_info['CFBundleIconFile']='haejo-app.icns'
        helper_info['CFBundleName']='Haejo Helper'
        helper_info['CFBundleDisplayName']='Haejo Helper'
        helper_info['CFBundleDevelopmentRegion']='en'
        helper_info['LSHasLocalizedDisplayName']=True
        for language in ('en','ko'):
            localized=helper_resources/(language+'.lproj')
            localized.mkdir(exist_ok=True)
            (localized/'InfoPlist.strings').write_bytes(plistlib.dumps({
                'CFBundleName':'Haejo Helper','CFBundleDisplayName':'Haejo Helper'}))
        helper_plist.write_bytes(plistlib.dumps(helper_info))
        sign(helper_app,identity,'open330.haejo.helper',requirement('open330.haejo.helper'))
        run(['codesign','--verify','--deep','--strict','-R='+requirement('open330.haejo.helper'),str(helper_app)])
        compile_setup(executable, Path(folder))
        import plistlib
        (contents/'Info.plist').write_bytes(plistlib.dumps({
            'CFBundleDisplayName':'Haejo','CFBundleName':'Haejo',
            'CFBundleIconFile':'haejo-app.icns',
            'CFBundleExecutable':'HaejoSetup','CFBundleIdentifier':'open330.haejo.app',
            'CFBundlePackageType':'APPL','CFBundleShortVersionString':'1.0.3','CFBundleVersion':'1',
            'LSUIElement':True,
            'LSMinimumSystemVersion':deployment_target()}))
        (resources/'runtime.json').write_text(json.dumps({'bundledRoot':'runtime'}))
        owner_requirement=requirement('open330.haejo.app')
        sign(executable,identity,'open330.haejo.app',owner_requirement)
        sign(app,identity,'open330.haejo.app',owner_requirement)
        run(['codesign','--verify','--deep','--strict','-R='+owner_requirement,str(app)])
        shutil.copytree(app,output,dirs_exist_ok=True,symlinks=True)
    # Relocation happened after signing. Run no GUI command and write no caches.
    python=output/'Contents/Resources/runtime/.venv/bin/python'
    report['relocated_import']=json.loads(run([str(python),'-I','-B','-c',
        'import haejo,haejo.helper,Foundation,Quartz,ApplicationServices,json,sys; print(json.dumps({"haejo":haejo.__file__,"prefix":sys.prefix,"helper":haejo.helper.HELPER}))'],cwd='/').stdout)
    if not bundled_import_valid(report['relocated_import'],output/'Contents/Resources/runtime'):
        raise RuntimeError('runtime imported outside bundle')
    run([str(python),'-I','-B','-m','haejo.cli','--help'],cwd='/')
    # Exercise the actual signed launcher, not only a Python -B probe. A
    # missing -B here used to pass packaging then invalidate its own signature.
    for _ in range(2):
        run([str(output/'Contents/Resources/runtime/launcher/haejo'),'--help'],cwd='/')
        run(['codesign','--verify','--deep','--strict','-R='+owner_requirement,str(output)])
    report['signature_preserved_after_launcher_runs']=True
    run(['codesign','--verify','--deep','--strict','-R='+owner_requirement,str(output)])
    report['outer_permission_owner_requirement_verified']=True
    report['signature_verified_after_import']=True
    report['private_path_files_scanned'] = require_private_paths_absent(output, (Path.home(), ROOT))
    report['private_build_paths_absent'] = True
    report['source_before']=before;report['source_after']=sources()
    report['source_stable']=before==report['source_after'];report['elapsed_seconds']=time.monotonic()-began
    if not report['source_stable']:raise RuntimeError('build sources changed')
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--identity',required=True)
    parser.add_argument('--report',type=Path,required=True)
    args=parser.parse_args()
    fd=os.open(args.report,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
    with os.fdopen(fd,'w') as file:
        try:report=build(args.output,args.identity)
        except Exception as error:
            json.dump({'status':'failed','error_class':type(error).__name__,'scope':'standalone_preview_build','gui_launched':False},file);file.write('\n');raise
        json.dump({'status':'passed',**report},file);file.write('\n')
    print('Built developer preview; not launched, installed or notarized: '+str(args.output))
