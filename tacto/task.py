"""Goal-scoped tasks: group every Tacto invocation made for one user goal.

A task is file-backed metadata, not a daemon, lease or authorization. It
never holds the helper, KeepAwake or a foreground scope between invocations;
each bound invocation still acquires and releases those itself. Records are
content-free (command, target bundle IDs, closed result codes, timing), except
the caller-supplied goal sentence, which stays in the owner-only task.json.

`task end --result` is the caller's declaration, not verified goal success.
"""
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timezone
from pathlib import Path
import json
import os
import re
import stat
import sys
import time
import uuid

TASK_ID = re.compile(r'^t-[0-9a-f]{24}$')
_INVOCATION = re.compile(r'^[0-9a-f]{32}$')
_CODE = re.compile(r'^[a-z][a-z0-9_]{0,80}$')
_BUNDLE = re.compile(r'^[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+$')
RESULTS = ('done', 'failed', 'abandoned')
MAX_GOAL = 1000
MAX_EVENTS_BYTES = 8 * 1024 * 1024
MAX_TASK_JSON = 64 * 1024

current = ContextVar('tacto_task_binding', default=None)


class TaskRefused(Exception):
    def __init__(self, code, detail):
        super().__init__(code)
        self.code, self.detail = code, detail


def tasks_root(root=None):
    if root is not None:
        return Path(root)
    from .preferences import product_directory
    return product_directory()/'Tasks'


def _private_dir(path, *, create):
    path = Path(path)
    if create:
        for folder in (path.parent, path):
            try:
                folder.mkdir(mode=0o700, exist_ok=True)
            except FileNotFoundError:
                folder.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
                folder.mkdir(mode=0o700, exist_ok=True)
    for folder in (path.parent, path):
        info = folder.lstat()
        if not stat.S_ISDIR(info.st_mode) or (hasattr(os, 'getuid') and info.st_uid != os.getuid()):
            raise OSError('unsafe_task_directory')
        if create and os.name != 'nt':
            folder.chmod(0o700)
    return path


def _task_dir(task_id, root=None):
    if not isinstance(task_id, str) or not TASK_ID.fullmatch(task_id):
        raise TaskRefused('task_invalid', 'A task ID looks like t- followed by 24 hex digits; use the ID that `tacto task start` printed.')
    return tasks_root(root)/task_id


def _now():
    return datetime.now(timezone.utc).isoformat()


def _read_regular(path, limit):
    fd = os.open(path, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0))
    with os.fdopen(fd, 'rb') as stream:
        info = os.fstat(stream.fileno())
        if (not stat.S_ISREG(info.st_mode) or info.st_size > limit
                or hasattr(os, 'getuid') and info.st_uid != os.getuid()):
            raise OSError('unsafe_task_file')
        return stream.read(limit + 1)


def _write_meta(directory, meta):
    from .storage import write_private
    write_private(str(directory/'task.json'), json.dumps(meta, ensure_ascii=False, separators=(',', ':')))
    if os.name != 'nt':
        os.chmod(directory/'task.json', 0o600)


def _load_meta(directory):
    try:
        raw = json.loads(_read_regular(directory/'task.json', MAX_TASK_JSON))
    except FileNotFoundError:
        raise TaskRefused('task_unknown', 'No such task on this computer. Start one with `tacto task start "<goal>"`.') from None
    except (OSError, ValueError, UnicodeError):
        raise TaskRefused('task_unreadable', 'The task record is damaged or not owned by this user.') from None
    if (type(raw) is not dict or raw.get('schema') != 1 or raw.get('id') != directory.name
            or raw.get('state') not in ('open', 'closed')):
        raise TaskRefused('task_unreadable', 'The task record is damaged.')
    return raw


@contextmanager
def _locked(directory):
    """Short metadata lock; never held across a GUI action."""
    flags = os.O_RDWR | os.O_CREAT | getattr(os, 'O_NOFOLLOW', 0)
    fd = os.open(directory/'.lock', flags, 0o600)
    try:
        if os.name == 'nt':
            import msvcrt
            os.lseek(fd, 0, 0)
            msvcrt.locking(fd, msvcrt.LK_LOCK, 1)
        else:
            import fcntl
            fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        try:
            if os.name == 'nt':
                import msvcrt
                os.lseek(fd, 0, 0)
                msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
        finally:
            os.close(fd)


def _append(directory, row):
    data = (json.dumps(dict(schema=1, at=_now(), **row), ensure_ascii=False, allow_nan=False,
                       separators=(',', ':')) + '\n').encode()
    path = directory/'events.jsonl'
    flags = os.O_RDWR | os.O_CREAT | os.O_APPEND | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(path, flags, 0o600)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or (hasattr(os, 'getuid') and info.st_uid != os.getuid()):
            raise OSError('unsafe_task_file')
        if info.st_size + len(data) + 1 > MAX_EVENTS_BYTES:
            raise OSError('task_events_full')
        if info.st_size:
            # A crash can leave a torn final record. Terminate it so it stays
            # visible as one damaged record instead of swallowing this one.
            # Callers hold the task lock, so no writer is mid-record here.
            tail = os.pread(fd, 1, info.st_size - 1) if hasattr(os, 'pread') else _tail_byte(path)
            if tail != b'\n':
                data = b'\n' + data
        view = memoryview(data)
        while view:
            size = os.write(fd, view)
            if size <= 0:
                raise OSError('task_write_failed')
            view = view[size:]
        os.fsync(fd)
    finally:
        os.close(fd)


def _tail_byte(path):
    with open(path, 'rb') as stream:
        stream.seek(-1, os.SEEK_END)
        return stream.read(1)


# ---------------------------------------------------------------- lifecycle

def start(goal, *, root=None):
    if not isinstance(goal, str) or not goal.strip():
        raise TaskRefused('task_goal_required', 'Describe the user\'s final goal in one sentence: tacto task start "<goal>".')
    goal = goal.strip()
    if len(goal) > MAX_GOAL or any(ord(c) < 32 and c not in '\t' for c in goal):
        raise TaskRefused('task_goal_invalid', f'Use one line of at most {MAX_GOAL} characters.')
    base = _private_dir(tasks_root(root), create=True)
    for _ in range(4):
        task_id = 't-' + uuid.uuid4().hex[:24]
        directory = base/task_id
        try:
            directory.mkdir(mode=0o700)
        except FileExistsError:
            continue
        _private_dir(directory, create=True)
        meta = {'schema': 1, 'id': task_id, 'goal': goal, 'state': 'open',
                'created_at': _now(), 'closed_at': None, 'result': None}
        with _locked(directory):
            _write_meta(directory, meta)
            _append(directory, {'event': 'task_start', 'pid': os.getpid()})
        return meta
    raise OSError('task_id_exhausted')


def end(task_id, result, *, root=None):
    if result not in RESULTS:
        raise TaskRefused('task_result_invalid', 'Use --result done, failed or abandoned.')
    directory = _task_dir(task_id, root)
    if not directory.exists():
        raise TaskRefused('task_unknown', 'No such task on this computer.')
    with _locked(_private_dir(directory, create=False)):
        meta = _load_meta(directory)
        if meta['state'] == 'closed':
            raise TaskRefused('task_closed', f"Task already ended ({meta.get('result')}).")
        meta.update(state='closed', closed_at=_now(), result=result)
        _write_meta(directory, meta)
        _append(directory, {'event': 'task_end', 'result': result, 'pid': os.getpid()})
    return meta


def _alive(pid):
    if type(pid) is not int or pid <= 0:
        return False
    if os.name == 'nt':
        return None
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def status(task_id, *, root=None):
    directory = _task_dir(task_id, root)
    if not directory.exists():
        raise TaskRefused('task_unknown', 'No such task on this computer.')
    _private_dir(directory, create=False)
    meta = _load_meta(directory)
    invocations, order, damaged = {}, [], 0
    try:
        raw = _read_regular(directory/'events.jsonl', MAX_EVENTS_BYTES)
    except FileNotFoundError:
        raw = b''
    for line in raw.split(b'\n'):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except (ValueError, UnicodeError):
            damaged += 1          # e.g. a partial final record after a crash
            continue
        if type(row) is not dict:
            damaged += 1
            continue
        inv = row.get('invocation')
        if row.get('event') == 'invocation_start' and isinstance(inv, str) and inv not in invocations:
            invocations[inv] = {k: row.get(k) for k in ('invocation', 'command', 'pid', 'parent', 'access_log')}
            invocations[inv].update(started_at=row.get('at'), ended_at=None, exit_code=None, elapsed_ms=None,
                                    targets=[], error=None, stage=None, state=None)
            order.append(inv)
        elif row.get('event') == 'invocation_end' and inv in invocations:
            item = invocations[inv]
            item.update(ended_at=row.get('at'), exit_code=row.get('exit_code'), elapsed_ms=row.get('elapsed_ms'),
                        targets=row.get('targets') or [], error=row.get('error'), stage=row.get('stage'))
    counts = {'ok': 0, 'failed': 0, 'in_flight': 0, 'uncertain': 0}
    for inv in order:
        item = invocations[inv]
        if item['ended_at'] is not None:
            item['state'] = 'ok' if item['exit_code'] == 0 else 'failed'
        else:
            # A missing end is never success and never permission to resend input.
            item['state'] = 'in_flight' if _alive(item['pid']) else 'uncertain'
        counts[item['state']] += 1
    return {'type': 'task', 'task_id': meta['id'], 'goal': meta['goal'], 'state': meta['state'],
            'result': meta.get('result'), 'created_at': meta.get('created_at'), 'closed_at': meta.get('closed_at'),
            'counts': counts, 'damaged_records': damaged,
            'invocations': [invocations[i] for i in order]}


def list_tasks(*, include_closed=False, limit=50, root=None):
    base = tasks_root(root)
    if not base.exists():
        return []
    _private_dir(base, create=False)
    rows = []
    for entry in base.iterdir():
        if not TASK_ID.fullmatch(entry.name) or entry.is_symlink() or not entry.is_dir():
            continue
        try:
            meta = _load_meta(entry)
        except TaskRefused:
            continue
        if meta['state'] == 'open' or include_closed:
            rows.append({k: meta.get(k) for k in ('id', 'goal', 'state', 'result', 'created_at', 'closed_at')})
    rows.sort(key=lambda r: r.get('created_at') or '', reverse=True)
    return rows[:limit]


# ---------------------------------------------------------------- binding

class Binding:
    """One admitted invocation of one task."""
    def __init__(self, task_id, directory, command, parent):
        self.task_id, self.directory, self.command, self.parent = task_id, directory, command, parent
        self.invocation = uuid.uuid4().hex
        self.started = time.monotonic()
        self.ended = False

    def admit(self, access_log_name=None):
        _private_dir(self.directory, create=False)
        with _locked(self.directory):
            meta = _load_meta(self.directory)
            if meta['state'] != 'open':
                raise TaskRefused('task_closed', f"Task {self.task_id} already ended ({meta.get('result')}); start a new task for new work.")
            row = {'event': 'invocation_start', 'invocation': self.invocation, 'command': self.command,
                   'pid': os.getpid()}
            if self.parent:
                row['parent'] = self.parent
            if access_log_name:
                row['access_log'] = access_log_name
            _append(self.directory, row)

    def finish(self, exit_code, access_log=None):
        if self.ended:
            return
        self.ended = True
        row = {'event': 'invocation_end', 'invocation': self.invocation,
               'exit_code': exit_code if type(exit_code) is int else None,
               'elapsed_ms': round((time.monotonic() - self.started) * 1000)}
        if access_log is not None:
            targets = sorted(t for t in getattr(access_log, 'targets', ()) if _BUNDLE.fullmatch(t))[:16]
            if targets:
                row['targets'] = targets
            last = getattr(access_log, 'last_failure', None) or {}
            for key in ('error', 'stage'):
                if isinstance(last.get(key), str) and _CODE.fullmatch(last[key]):
                    row[key] = last[key]
        try:
            # Ending is allowed after task end: the invocation was admitted while open.
            with _locked(self.directory):
                _append(self.directory, row)
        except OSError:
            print('tacto: 작업(task) 종료 기록을 남기지 못했습니다 — 이 실행은 status 에서 uncertain 으로 보입니다.', file=sys.stderr)

    def child_env(self):
        return {'TACTO_TASK': self.task_id, 'TACTO_TASK_PARENT': self.invocation}


def split_binding(argv, environ=None):
    """Remove `--task ID` from argv. Returns (task_id or None, explicit, argv)."""
    environ = os.environ if environ is None else environ
    out, explicit = [], None
    i = 0
    args = list(argv)
    while i < len(args):
        token = args[i]
        if token == '--task':
            if explicit is not None or i + 1 >= len(args):
                raise TaskRefused('task_invalid', '--task takes one task ID, once.')
            explicit = args[i + 1]
            i += 2
            continue
        if token.startswith('--task='):
            if explicit is not None:
                raise TaskRefused('task_invalid', '--task takes one task ID, once.')
            explicit = token.split('=', 1)[1]
            i += 1
            continue
        out.append(token)
        i += 1
    if explicit is not None:
        return explicit, True, out
    value = environ.get('TACTO_TASK')
    if value:
        return value, False, out
    return None, False, out


def bind(task_id, command, *, root=None, environ=None):
    environ = os.environ if environ is None else environ
    directory = _task_dir(task_id, root)
    if not directory.exists():
        raise TaskRefused('task_unknown', f'No task {task_id} on this computer. Start one with `tacto task start "<goal>"`.')
    _private_dir(directory, create=False)
    meta = _load_meta(directory)
    if meta['state'] != 'open':
        # Checked again under the lock at admission; this refuses before any log or UI work.
        raise TaskRefused('task_closed', f"Task {task_id} already ended ({meta.get('result')}); start a new task for new work.")
    parent = environ.get('TACTO_TASK_PARENT')
    if parent is not None and not _INVOCATION.fullmatch(parent):
        parent = None
    return Binding(task_id, directory, command, parent)


# ---------------------------------------------------------------- CLI

USAGE = ('usage: tacto task start "<goal>" [--json]\n'
         '       tacto task status [<task-id>] [--json]\n'
         '       tacto task list [--all] [--json]\n'
         '       tacto task end [<task-id>] --result done|failed|abandoned [--json]')


def _emit_refusal(exc, as_json):
    if as_json:
        print(json.dumps({'type': 'error', 'error': exc.code, 'detail': exc.detail}, ensure_ascii=False))
    else:
        print(f'{exc.code}: {exc.detail}')


def _resolve_id(args):
    ids = [a for a in args if not a.startswith('--')]
    if len(ids) > 1:
        raise TaskRefused('task_invalid', 'Give one task ID.')
    if ids:
        return ids[0]
    value = os.environ.get('TACTO_TASK')
    if value:
        return value
    raise TaskRefused('task_invalid', 'Give the task ID (or set TACTO_TASK); Tacto never guesses a latest task.')


def main(args, *, root=None):
    args = list(args)
    as_json = '--json' in args
    args = [a for a in args if a != '--json']
    if not args or args[0] in ('-h', '--help', 'help'):
        print(USAGE + '\n\n' + GUIDE)
        return 0
    sub, rest = args[0], args[1:]
    try:
        if sub == 'start':
            if len(rest) != 1:
                print(USAGE); return 2
            meta = start(rest[0], root=root)
            if as_json:
                print(json.dumps({'type': 'task', 'task_id': meta['id'], 'state': 'open'}, ensure_ascii=False))
            else:
                print(f"TACTO_TASK {meta['id']}")
                print(f"Prefix every tacto command for this goal: TACTO_TASK={meta['id']} tacto …  "
                      f"(or add --task {meta['id']}). Finish with: tacto task end {meta['id']} --result done|failed|abandoned")
            return 0
        if sub == 'status':
            if any(a.startswith('--') for a in rest):
                print(USAGE); return 2
            report = status(_resolve_id(rest), root=root)
            print(json.dumps(report, ensure_ascii=False) if as_json else _format_status(report))
            return 0
        if sub == 'list':
            if rest not in ([], ['--all']):
                print(USAGE); return 2
            rows = list_tasks(include_closed=rest == ['--all'], root=root)
            if as_json:
                print(json.dumps({'type': 'task_list', 'tasks': rows}, ensure_ascii=False))
            elif not rows:
                print('no open tasks' if rest != ['--all'] else 'no tasks')
            else:
                for row in rows:
                    tail = f" ({row['result']})" if row['result'] else ''
                    print(f"{row['id']}  {row['state']}{tail}  {row['created_at']}  {row['goal']}")
            return 0
        if sub == 'end':
            if '--result' not in rest:
                print(USAGE); return 2
            i = rest.index('--result')
            if i + 1 >= len(rest) or rest.count('--result') != 1:
                print(USAGE); return 2
            result = rest[i + 1]
            meta = end(_resolve_id(rest[:i] + rest[i + 2:]), result, root=root)
            report = status(meta['id'], root=root)
            if as_json:
                print(json.dumps({'type': 'task', 'task_id': meta['id'], 'state': 'closed', 'result': result,
                                  'counts': report['counts']}, ensure_ascii=False))
            else:
                print(f"task {meta['id']} ended: {result} (caller-declared; not a verification)")
                c = report['counts']
                if c['in_flight'] or c['uncertain']:
                    print(f"  note: {c['in_flight']} in_flight, {c['uncertain']} uncertain — inspect the target state before any retry.")
            return 0
    except TaskRefused as exc:
        _emit_refusal(exc, as_json)
        return 2
    except OSError:
        _emit_refusal(TaskRefused('task_storage_unavailable', 'The private task directory could not be used.'), as_json)
        return 2
    print(USAGE)
    return 2


def _format_status(report):
    c = report['counts']
    head = [f"task {report['task_id']}  {report['state']}" + (f" ({report['result']})" if report['result'] else ''),
            f"goal: {report['goal']}",
            f"invocations: {len(report['invocations'])}  ok {c['ok']}  failed {c['failed']}  "
            f"in_flight {c['in_flight']}  uncertain {c['uncertain']}"]
    for n, item in enumerate(report['invocations'], 1):
        targets = ','.join(item['targets']) if item['targets'] else '-'
        result = {'ok': 'ok', 'failed': f"exit {item['exit_code']}"}.get(item['state'], item['state'])
        reason = f" {item['error']}" + (f"/{item['stage']}" if item['stage'] else '') if item['error'] else ''
        ms = f" {item['elapsed_ms']}ms" if item['elapsed_ms'] is not None else ''
        child = ' (child)' if item.get('parent') else ''
        head.append(f"  {n:>3} {item['started_at']} {item['command']}{child} {targets} {result}{reason}{ms}")
    if c['uncertain']:
        head.append('uncertain = no end record and the process is gone: inspect the target before retrying.')
    if report['damaged_records']:
        head.append(f"damaged records skipped: {report['damaged_records']}")
    return '\n'.join(head)


GUIDE = ('A task groups every Tacto call made for one user goal. Start it first,\n'
         'run every tacto command for the goal with TACTO_TASK=<id> (or --task <id>),\n'
         'then end it. It holds no helper, lease or approval between calls.')
