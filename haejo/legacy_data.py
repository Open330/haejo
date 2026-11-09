"""Move per-user data left under the product's previous name (Tacto) to the Haejo paths.

The product was renamed from Tacto to Haejo on 2026-11-09. Activity history, preferences,
task records and saved Flows are user data, so the first Haejo run moves them instead of
starting empty. A directory moves only when the Haejo path does not exist yet; nothing is
merged, overwritten or deleted. Symlinks are left alone.
"""
import os
from pathlib import Path
import sys

LEGACY_PRODUCT = 'Tacto'     # product directory name before the rename
LEGACY_SLUG = 'tacto'        # lowercase data directory name before the rename


def legacy_pairs(home=None, environ=None, platform=None):
    """(old, new) directory pairs for this platform. Pure; touches nothing."""
    home = Path(home) if home is not None else Path.home()
    environ = os.environ if environ is None else environ
    platform = platform or sys.platform
    pairs = []
    if platform == 'darwin':
        support = home/'Library/Application Support'
        pairs.append((support/LEGACY_PRODUCT, support/'Haejo'))
    elif platform == 'win32':
        local = Path(environ.get('LOCALAPPDATA') or home/'AppData/Local')
        pairs.append((local/LEGACY_PRODUCT, local/'Haejo'))
    else:
        pairs.append((home/'.local/state'/LEGACY_SLUG, home/'.local/state/haejo'))
    data = environ.get('XDG_DATA_HOME', '')
    if not data or not os.path.isabs(data):
        data = home/'.local/share'
    pairs.append((Path(data)/LEGACY_SLUG, Path(data)/'haejo'))
    return pairs


def migrate_legacy_data(home=None, environ=None, platform=None):
    """Rename each legacy directory to its Haejo path when that path is free.

    Returns the (old, new) pairs that moved. Failures are ignored: the runtime then
    simply starts with an empty Haejo directory, as a fresh install would.
    """
    moved = []
    for old, new in legacy_pairs(home, environ, platform):
        try:
            if old.is_symlink() or not old.is_dir() or new.exists() or new.is_symlink():
                continue
            new.parent.mkdir(parents=True, exist_ok=True)
            os.rename(old, new)
            moved.append((old, new))
        except OSError:
            continue
    return moved
