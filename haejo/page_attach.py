"""Registered files for a page's file control in the person's own browser.

`haejo attach <name> /absolute/file ...` pins each file's size and SHA-256
under a name. A Flow step `attach_files` names that registration, never a
path; at dispatch the bytes are hashed again, here and once more in the
signed helper just before it chooses, so what reaches the page is what was
registered. The helper opens the control's own open panel and reports the
route it used (helper/OpenPanelUpload.swift).
"""
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import time

REGISTRY_NAME = 'attachments.json'
MAX_FILES = 16
MAX_SCOPES = 64
ROUTES = ('ax_background', 'ax_brief_front', 'go_to_folder_front')
_SCOPE = re.compile(r'[A-Za-z_][A-Za-z0-9_]{0,39}')
_DIGEST = re.compile(r'[0-9a-f]{64}')


class AttachmentRefused(ValueError):
    """A registration that cannot be made; the code names why."""


def _registry_path(root=None):
    if root is None:
        from .preferences import product_directory
        root = product_directory()
    return Path(root) / REGISTRY_NAME


def _fingerprint(path):
    """(size, sha256) of an existing regular file, or None."""
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK)
    except OSError:
        return None
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode):
            return None
        with os.fdopen(os.dup(fd), 'rb') as stream:
            digest = hashlib.file_digest(stream, 'sha256').hexdigest()
        after = os.fstat(fd)
        if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
            return None
        return before.st_size, digest
    except OSError:
        return None
    finally:
        os.close(fd)


def manifest_digest(files):
    """One digest for the registered names, sizes and bytes, in order."""
    value = [{'filename': f['filename'], 'size_bytes': f['size_bytes'], 'sha256': f['sha256']} for f in files]
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                     separators=(',', ':')).encode()).hexdigest()


def _read(root=None):
    path = _registry_path(root)
    try:
        fd = os.open(path, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0))
    except OSError:
        return {}
    with os.fdopen(fd, 'rb') as stream:
        info = os.fstat(stream.fileno())
        if (not stat.S_ISREG(info.st_mode) or info.st_size > 1024 * 1024
                or hasattr(os, 'getuid') and info.st_uid != os.getuid()):
            return {}
        try:
            value = json.loads(stream.read())
        except ValueError:
            return {}
    scopes = value.get('scopes') if isinstance(value, dict) and value.get('version') == 1 else None
    return {name: entry for name, entry in scopes.items() if _entry_valid(name, entry)} if isinstance(scopes, dict) else {}


def _entry_valid(name, entry):
    if not (type(name) is str and _SCOPE.fullmatch(name) and type(entry) is dict
            and set(entry) == {'files', 'attachment_digest', 'registered_at'}
            and type(entry['files']) is list and 1 <= len(entry['files']) <= MAX_FILES):
        return False
    for item in entry['files']:
        if not (type(item) is dict and set(item) == {'path', 'filename', 'size_bytes', 'sha256'}
                and type(item['path']) is str and os.path.isabs(item['path'])
                and item['filename'] == os.path.basename(item['path'])
                and type(item['size_bytes']) is int and item['size_bytes'] >= 0
                and type(item['sha256']) is str and _DIGEST.fullmatch(item['sha256'])):
            return False
    return entry['attachment_digest'] == manifest_digest(entry['files'])


def _write(scopes, root=None):
    from .private_fs import mkdir_private
    from .storage import write_private
    path = _registry_path(root)
    mkdir_private(path.parent, parents=True, exist_ok=True)
    write_private(str(path), json.dumps({'version': 1, 'scopes': scopes}, ensure_ascii=False, indent=2))


def register(name, paths, root=None):
    """Pin these files under `name`; returns the registration."""
    if type(name) is not str or not _SCOPE.fullmatch(name):
        raise AttachmentRefused('invalid_scope')
    if not isinstance(paths, (list, tuple)) or not 1 <= len(paths) <= MAX_FILES:
        raise AttachmentRefused('one_to_sixteen_files')
    files = []
    for raw in paths:
        if type(raw) is not str or not os.path.isabs(raw) or len(raw.encode()) > 1024 \
                or any(ord(c) < 32 or ord(c) == 127 for c in raw):
            raise AttachmentRefused('absolute_path_required')
        path = os.path.realpath(raw)
        pinned = _fingerprint(path)
        if pinned is None:
            raise AttachmentRefused('readable_file_required')
        files.append({'path': path, 'filename': os.path.basename(path),
                      'size_bytes': pinned[0], 'sha256': pinned[1]})
    if len({os.path.dirname(f['path']) for f in files}) != 1:
        # One open panel shows one folder; files of several folders go in several steps.
        raise AttachmentRefused('files_share_one_folder')
    if len({f['path'] for f in files}) != len(files):
        raise AttachmentRefused('file_listed_twice')
    entry = {'files': files, 'attachment_digest': manifest_digest(files), 'registered_at': int(time.time())}
    scopes = _read(root)
    scopes[name] = entry
    if len(scopes) > MAX_SCOPES:
        for stale in sorted(scopes, key=lambda key: scopes[key]['registered_at'])[:len(scopes) - MAX_SCOPES]:
            if stale != name:
                del scopes[stale]
    _write(scopes, root)
    return entry


def registration(name, root=None):
    return _read(root).get(name) if type(name) is str else None


def forget(name, root=None):
    scopes = _read(root)
    if name not in scopes:
        return False
    del scopes[name]
    _write(scopes, root)
    return True


def params_valid(params):
    return (type(params) is dict and 'scope' in params and set(params) <= {'scope', 'attachment_digest'}
            and type(params['scope']) is str and _SCOPE.fullmatch(params['scope']) is not None
            and ('attachment_digest' not in params or (
                type(params['attachment_digest']) is str
                and _DIGEST.fullmatch(params['attachment_digest']) is not None)))


def helper_action(action, root=None):
    """(`choose_files` action for the helper, None) or (None, refusal).

    Nothing has been pressed when this refuses: the registration is missing,
    names other bytes than the step pinned, or a file changed since.
    """
    def refused(code, **extra):
        return None, {'type': 'error', 'error': code, 'effect': 'not_started', **extra}
    if (type(action) is not dict or action.get('name') != 'attach_files'
            or type(action.get('element_index')) is not int or action['element_index'] < 0
            or set(action) - {'name', 'element_index', 'scope', 'attachment_digest'}
            or not params_valid({k: v for k, v in action.items() if k in ('scope', 'attachment_digest')})):
        return refused('invalid_action')
    entry = registration(action['scope'], root)
    if entry is None:
        return refused('attachment_not_registered', scope=action['scope'],
                       next=f"haejo attach {action['scope']} /absolute/file")
    if action.get('attachment_digest', entry['attachment_digest']) != entry['attachment_digest']:
        return refused('attachment_digest_mismatch', scope=action['scope'])
    for item in entry['files']:
        if _fingerprint(item['path']) != (item['size_bytes'], item['sha256']):
            return refused('attachment_changed', scope=action['scope'], filename=item['filename'],
                           next=f"haejo attach {action['scope']} <files>   # register the current bytes")
    return {'name': 'choose_files', 'element_index': action['element_index'],
            'files': [{'path': item['path'], 'sha256': item['sha256']} for item in entry['files']]}, None


def route_report(response):
    """What an `attach_files` reply says about the way it went."""
    keys = ('route', 'took_front', 'front_seconds', 'front_restored', 'real_keys',
            'control_label', 'control_names_files', 'steps')
    return {key: response[key] for key in keys if key in response}


def public(name, entry):
    """A registration as it is shown: names, sizes and digests."""
    return {'scope': name, 'attachment_digest': entry['attachment_digest'],
            'files': [{k: item[k] for k in ('filename', 'size_bytes', 'sha256')} for item in entry['files']]}


USAGE = '''usage: haejo attach <name> /absolute/file [/absolute/file ...]
       haejo attach --list
       haejo attach --forget <name>
Registers files for a web page's file control and pins their size and SHA-256.
Use the name in a Flow step on the page's file control (Safari, `--helper`):
  {"action":"attach_files","selector":{"role":"Button","title":"<the control's label>"},"params":{"scope":"<name>"},"postcondition":{...the page naming the file...}}
The reply's `route` says how the open panel was driven.'''


def main(argv, *, root=None, emit=print):
    if not argv or argv[0] in ('--help', '-h', 'help'):
        emit(USAGE)
        return 0 if argv else 2
    if argv[0] == '--list':
        if len(argv) != 1:
            emit(USAGE)
            return 2
        emit(json.dumps({'ok': True, 'registrations': [public(n, e) for n, e in sorted(_read(root).items())]},
                        ensure_ascii=False))
        return 0
    if argv[0] == '--forget':
        if len(argv) != 2:
            emit(USAGE)
            return 2
        gone = forget(argv[1], root)
        emit(json.dumps({'ok': gone, 'scope': argv[1], **({} if gone else {'error': 'attachment_not_registered'})}))
        return 0 if gone else 1
    if len(argv) < 2 or argv[0].startswith('-'):
        emit(USAGE)
        return 2
    try:
        entry = register(argv[0], argv[1:], root)
    except AttachmentRefused as error:
        emit(json.dumps({'ok': False, 'error': str(error)}))
        return 1
    emit(json.dumps({'ok': True, **public(argv[0], entry),
                     'step': {'action': 'attach_files', 'params': {'scope': argv[0]}}}, ensure_ascii=False))
    return 0
