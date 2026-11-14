"""Remove Haejo the way it was installed: its links, its app, and (on request) its data.

Moving Haejo.app to the Trash alone left four links pointing at nothing — the
`haejo` command and the Claude Code, Codex and shared skills — so an agent saw
a broken skill (june-mba, 2026-11-11). This removes exactly what Haejo made:
symlinks that resolve into this app, the app itself, and with `--remove-data`
the history, tasks, Flows and settings. Everything goes to the Trash, where it
can be put back; nothing is overwritten or deleted outright.

No Finder scripting is used: an Apple Event to Finder can raise a macOS
"allow control" prompt in front of the person. The bundle is moved within the
same volume instead.
"""
from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from pathlib import Path


def bundle_of(path) -> Path | None:
    """The .app this runtime lives in, or None for a source checkout."""
    for parent in Path(path).resolve().parents:
        if parent.suffix == '.app' and (parent/'Contents/Info.plist').is_file():
            return parent
    return None


def link_places(home: Path) -> list[Path]:
    """Every place install.sh and the app link into: the command and each skills folder."""
    places = [Path(os.environ.get('HAEJO_BIN_DIR') or home/'.local/bin')/'haejo']
    folders = [home/'.claude/skills', home/'.codex/skills', home/'.agents/skills']
    for key in ('CLAUDE_CONFIG_DIR', 'CODEX_HOME'):
        if os.environ.get(key):
            folders.append(Path(os.environ[key])/'skills')
    folders.extend((home/'Library/Application Support/asx/profiles').glob('*/skills'))
    places += [f/name for f in folders for name in ('haejo', '해줘')]
    seen, out = set(), []
    for p in places:
        if str(p) not in seen:
            seen.add(str(p)); out.append(p)
    return out


def owned_links(root: Path, home: Path) -> list[Path]:
    """Symlinks that point into `root` — this installation's own, nobody else's."""
    root = root.resolve()
    found = []
    for place in link_places(home):
        if not place.is_symlink():
            continue
        # realpath also for a link left dangling: /var vs /private/var and other
        # symlinked parents must not hide that the link points into this app.
        target = Path(os.path.realpath(os.path.join(place.parent, os.readlink(place))))
        if target == root or root in target.parents:
            found.append(place)
    return found


def to_trash(path: Path, home: Path, name: str | None = None) -> Path:
    trash = home/'.Trash'
    trash.mkdir(mode=0o700, exist_ok=True)
    dest = trash/(name or path.name)
    n = 1
    while dest.exists() or dest.is_symlink():
        n += 1
        base = Path(name or path.name)
        dest = trash/f'{base.stem} {n}{base.suffix}'
    os.rename(path, dest)
    return dest


# Named for the Trash: the two folders are both "Haejo"/"haejo", which collide
# on a case-insensitive volume and say nothing about what they hold.
DATA = (('Library/Application Support/Haejo', 'Haejo 실행 기록·설정'), ('.local/share/haejo', 'Haejo Flow'))


def data_places(home: Path) -> list[Path]:
    return [home/rel for rel, _ in DATA]


def ancestors(pid: int, parents: dict[int, int]) -> set[int]:
    chain = set()
    while pid > 1 and pid not in chain:
        chain.add(pid)
        pid = parents.get(pid, 0)
    return chain


def stop_processes(bundle: Path, keep: set[int]) -> list[int]:
    """End this app's own processes (setup app, helpers); never another app's,
    and never this command's own chain (the app may be the one that asked)."""
    out = subprocess.run(['/bin/ps', '-axo', 'pid=,ppid=,comm='], capture_output=True, text=True).stdout
    rows, parents = [], {}
    for line in out.splitlines():
        parts = line.strip().split(None, 2)
        if len(parts) == 3 and parts[0].isdigit() and parts[1].isdigit():
            parents[int(parts[0])] = int(parts[1])
            rows.append((int(parts[0]), parts[2]))
    for pid in list(keep):
        keep |= ancestors(pid, parents)
    stopped = []
    prefix = str(bundle.resolve()) + '/'
    for pid, command in rows:
        pid = str(pid)
        if int(pid) in keep:
            continue
        if command.strip().startswith(prefix) and '/runtime/.venv/' not in command:
            try:
                os.kill(int(pid), signal.SIGTERM)
                stopped.append(int(pid))
            except OSError:
                pass
    if stopped:
        time.sleep(0.5)
    return stopped


def plan(runtime: Path, home: Path, remove_data: bool) -> dict:
    bundle = bundle_of(runtime)
    root = bundle or runtime
    return {'bundle': bundle, 'links': owned_links(root, home),
            'data': [p for p in data_places(home) if p.exists()] if remove_data else []}


def main(argv) -> int:
    args = [a for a in argv if a not in ('--yes', '-y', '--remove-data', '--json')]
    if args:
        print('usage: haejo uninstall [--remove-data] [--yes] [--json]\n'
              'Removes the haejo command and skill links this installation made and moves Haejo.app\n'
              'to the Trash. --remove-data also moves run history, tasks, Flows and settings to the Trash.')
        return 2
    home = Path.home()
    runtime = Path(__file__).resolve().parents[1]
    p = plan(runtime, home, '--remove-data' in argv)
    lines = [f'  link: {l}' for l in p['links']]
    if p['bundle'] is not None:
        lines.append(f"  app:  {p['bundle']} → Trash")
    lines += [f'  data: {d} → Trash' for d in p['data']]
    if not lines:
        print('nothing_to_remove')
        return 0
    if '--yes' not in argv and '-y' not in argv:
        print('Haejo 제거:\n' + '\n'.join(lines))
        if not sys.stdin.isatty():
            print('approval_required: rerun with --yes')
            return 3
        if input('진행할까요? [y/N] ').strip().lower() not in ('y', 'yes', '네'):
            return 1
    result = {'links_removed': [], 'app_trashed': None, 'data_trashed': [], 'stopped': []}
    for link in p['links']:
        link.unlink(missing_ok=True)
        result['links_removed'].append(str(link))
    labels = {str(home/rel): label for rel, label in DATA}
    for folder in p['data']:
        result['data_trashed'].append(str(to_trash(folder, home, labels.get(str(folder)))))
    if p['bundle'] is not None:
        result['stopped'] = stop_processes(p['bundle'], {os.getpid(), os.getppid()})
        result['app_trashed'] = str(to_trash(p['bundle'], home))
    if '--json' in argv:
        import json
        print(json.dumps(result, ensure_ascii=False))
    else:
        for k in ('links_removed', 'data_trashed'):
            for v in result[k]:
                print(f'removed {v}' if k == 'links_removed' else f'trashed {v}')
        if result['app_trashed']:
            print(f"trashed {result['app_trashed']}")
        print('Haejo를 제거했습니다.' + ('' if p['data'] else ' 실행 기록·Flow는 남겨 두었습니다 (--remove-data로 함께 제거).'))
    return 0
