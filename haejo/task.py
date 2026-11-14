"""Goal-scoped tasks: group every Haejo invocation made for one user goal.

A task is file-backed metadata, not a daemon, lease or authorization. It
never holds the helper or KeepAwake between invocations; each bound invocation
still acquires and releases those itself. What an open task keeps between its
invocations is a short claim on the apps it works in and on the screen front
it took (docs/parallel-execution.md); the helper reads `state` in task.json to
know the task is still open, so ending the task frees them at once. Records are
content-free (command, target bundle IDs, closed result codes, timing, and
the names of the flows an invocation ran), except the caller-supplied goal
sentence, which stays in the owner-only task.json.

`task end --result` is the caller's declaration, not verified goal success.
"""
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timezone
from pathlib import Path
from .private_fs import mkdir_private
import hashlib
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
# Agent-written prose: the task's description, a one-line reason on a call
# (`--why`) and decision notes (`task note`). They stay in this private task
# directory; access receipts remain content-free.
MAX_DETAIL = 4000
MAX_WHY = 500
MAX_NOTE = 1000
MAX_EVENTS_BYTES = 8 * 1024 * 1024
MAX_TASK_JSON = 64 * 1024
# Only names of kept recipes (built-in or saved in the library) are copied: a
# name a model gave a learned/compiled flow, or one inside a file, can echo the
# request ("send_1234_to_kim"). Those are recorded as a short one-way ref so
# repeats still line up. `base:recovery` names a recovery of a kept recipe.
_FLOW_NAME = re.compile(r'^[A-Za-z0-9_.\-]{1,80}(?::[A-Za-z0-9_.\-]{1,80})?$')
_FLOW_REF = re.compile(r'^[0-9a-f]{12}$')
FLOW_SOURCES = ('builtin', 'library', 'file', 'inline')
MAX_FLOWS = 16
MAX_STEP_LOG_BYTES = 4 * 1024 * 1024

current = ContextVar('haejo_task_binding', default=None)


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
                mkdir_private(folder, exist_ok=True)
            except FileNotFoundError:
                mkdir_private(folder.parent, parents=True, exist_ok=True)
                mkdir_private(folder, exist_ok=True)
    for folder in (path.parent, path):
        info = folder.lstat()
        if not stat.S_ISDIR(info.st_mode) or (hasattr(os, 'getuid') and info.st_uid != os.getuid()):
            raise OSError('unsafe_task_directory')
        if create and os.name != 'nt':
            folder.chmod(0o700)
    return path


def _task_dir(task_id, root=None):
    if not isinstance(task_id, str) or not TASK_ID.fullmatch(task_id):
        raise TaskRefused('task_invalid', 'A task ID looks like t- followed by 24 hex digits; use the ID that `haejo task start` printed.')
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
        raise TaskRefused('task_unknown', 'No such task on this computer. Start one with `haejo task start "<goal>"`.') from None
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

def _prose(text, limit, code, *, multiline):
    """Validate agent-written prose. Returns the stripped text or None when absent."""
    if text is None:
        return None
    if not isinstance(text, str) or not text.strip():
        raise TaskRefused(code, 'Give non-empty text.')
    text = text.strip()
    allowed = '\t\n' if multiline else '\t'
    if len(text) > limit or any((ord(c) < 32 and c not in allowed) or ord(c) == 127 for c in text):
        raise TaskRefused(code, f"Use {'text' if multiline else 'one line'} of at most {limit} characters.")
    return text


def start(goal, *, detail=None, root=None):
    if not isinstance(goal, str) or not goal.strip():
        raise TaskRefused('task_goal_required', 'Describe the user\'s final goal in one sentence: haejo task start "<goal>".')
    goal = goal.strip()
    if len(goal) > MAX_GOAL or any(ord(c) < 32 and c not in '\t' for c in goal):
        raise TaskRefused('task_goal_invalid', f'Use one line of at most {MAX_GOAL} characters.')
    detail = _prose(detail, MAX_DETAIL, 'task_detail_invalid', multiline=True)
    base = _private_dir(tasks_root(root), create=True)
    for _ in range(4):
        task_id = 't-' + uuid.uuid4().hex[:24]
        directory = base/task_id
        try:
            mkdir_private(directory)
        except FileExistsError:
            continue
        _private_dir(directory, create=True)
        meta = {'schema': 1, 'id': task_id, 'goal': goal, 'state': 'open',
                'created_at': _now(), 'closed_at': None, 'result': None}
        if detail:
            meta['detail'] = detail
        with _locked(directory):
            _write_meta(directory, meta)
            _append(directory, {'event': 'task_start', 'pid': os.getpid()})
        return meta
    raise OSError('task_id_exhausted')


def describe(task_id, text, *, root=None):
    """Set or replace the description of an open task (the user's request in prose)."""
    text = _prose(text, MAX_DETAIL, 'task_detail_invalid', multiline=True)
    if text is None:
        raise TaskRefused('task_detail_invalid', 'Give the description: haejo task describe <id> "<the user\'s request>".')
    directory = _task_dir(task_id, root)
    if not directory.exists():
        raise TaskRefused('task_unknown', 'No such task on this computer.')
    with _locked(_private_dir(directory, create=False)):
        meta = _load_meta(directory)
        if meta['state'] != 'open':
            raise TaskRefused('task_closed', f"Task already ended ({meta.get('result')}).")
        meta['detail'] = text
        _write_meta(directory, meta)
    return meta


def prose_hint(task_id, *, at_end=False, root=None):
    """One line naming the prose commands for whatever this task still lacks, or None."""
    try:
        report = status(task_id, root=root)
    except (OSError, TaskRefused):
        return None
    parts = []
    if not at_end and not report.get('detail'):
        parts.append(f'요청 설명: haejo task describe {task_id} "<사용자 요청>"')
    if not report.get('notes'):
        parts.append(f'결과 요약: haejo task note {task_id} "<무엇을 확인했고 왜 끝냈는지>"' if at_end
                     else f'판단 기록: haejo task note {task_id} "<판단과 근거>"')
    return 'HAEJO_TASK_HINT ' + ' · '.join(parts) if parts else None


def note(task_id, text, *, root=None):
    """Record one agent decision or the closing summary (accepted after the task ends too)."""
    text = _prose(text, MAX_NOTE, 'task_note_invalid', multiline=True)
    if text is None:
        raise TaskRefused('task_note_invalid', 'Give the decision text: haejo task note "<decision>".')
    directory = _task_dir(task_id, root)
    if not directory.exists():
        raise TaskRefused('task_unknown', 'No such task on this computer.')
    with _locked(_private_dir(directory, create=False)):
        meta = _load_meta(directory)
        _append(directory, {'event': 'note', 'text': text, 'pid': os.getpid()})
    return meta


def end(task_id, result, *, root=None, completion_scope=None, summary=None):
    if result not in RESULTS:
        raise TaskRefused('task_result_invalid', 'Use --result done, failed or abandoned.')
    summary = _prose(summary, MAX_NOTE, 'task_note_invalid', multiline=True)
    directory = _task_dir(task_id, root)
    if not directory.exists():
        raise TaskRefused('task_unknown', 'No such task on this computer.')
    with _locked(_private_dir(directory, create=False)):
        meta = _load_meta(directory)
        if meta['state'] == 'closed':
            raise TaskRefused('task_closed', f"Task already ended ({meta.get('result')}).")
        meta.update(state='closed', closed_at=_now(), result=result)
        if completion_scope in ('command', 'visible_document_text', 'failed_invocation'):
            meta['completion_scope'] = completion_scope
        if summary:
            _append(directory, {'event': 'note', 'text': summary, 'pid': os.getpid()})
        _write_meta(directory, meta)
        _append(directory, {'event': 'task_end', 'result': result, 'completion_scope': meta.get('completion_scope'), 'pid': os.getpid()})
    return meta


def _release_claims(task_id, root=None):
    """An ended task holds nothing: its claims on apps are void once task.json
    says closed, and the helper gives back the screen front it took."""
    if root is None or Path(root) == tasks_root():
        from .helper import release_task_claims
        release_task_claims(task_id)


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
    invocations, order, damaged, notes = {}, [], 0, []
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
                                    targets=[], error=None, stage=None, state=None, flows=[],
                                    why=row['why'][:MAX_WHY] if isinstance(row.get('why'), str) else None)
            order.append(inv)
        elif row.get('event') == 'note' and isinstance(row.get('text'), str):
            notes.append({'at': row.get('at') if isinstance(row.get('at'), str) else None, 'text': row['text'][:MAX_NOTE]})
        elif row.get('event') == 'invocation_flow' and isinstance(inv, str) and inv in invocations:
            flows = invocations[inv]['flows']
            name = row.get('name') if isinstance(row.get('name'), str) and _FLOW_NAME.fullmatch(row['name']) else None
            ref = row.get('ref') if isinstance(row.get('ref'), str) and _FLOW_REF.fullmatch(row['ref']) else None
            source = row.get('source') if row.get('source') in FLOW_SOURCES else 'inline'
            if len(flows) < MAX_FLOWS:
                flows.append({'name': name, 'ref': ref, 'source': source})
        elif row.get('event') == 'invocation_end' and isinstance(inv, str) and inv in invocations:
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
    detail = meta.get('detail') if isinstance(meta.get('detail'), str) else None
    return {'type': 'task', 'task_id': meta['id'], 'goal': meta['goal'], 'detail': detail, 'state': meta['state'],
            'result': meta.get('result'), 'completion_scope': meta.get('completion_scope'),
            'created_at': meta.get('created_at'), 'closed_at': meta.get('closed_at'),
            'counts': counts, 'damaged_records': damaged,
            'invocations': [invocations[i] for i in order], 'notes': notes}


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
        self.admitted = False
        self.flows = set()
        self.finish_requested = False
        self.finish_recorded = False
        self.created_inline = False
        self.json_output = False
        self.visible_document_verified = False
        self.why = None

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
            if self.why:
                row['why'] = self.why
            _append(self.directory, row)
            self.admitted = True

    def note_flow(self, name, source=None):
        """Record that this invocation ran a flow. First note per name wins."""
        if not self.admitted or self.ended:
            return
        if not isinstance(name, str) or not name or len(name) > 400:
            name = None
        key = name or '-'
        if key in self.flows or len(self.flows) >= MAX_FLOWS:
            return
        self.flows.add(key)
        if source not in FLOW_SOURCES:
            source = _flow_source(name)
        row = {'event': 'invocation_flow', 'invocation': self.invocation, 'source': source}
        if name and source in ('builtin', 'library') and _FLOW_NAME.fullmatch(name):
            row['name'] = name
        elif name:
            row['ref'] = hashlib.sha256(name.encode('utf-8', 'surrogatepass')).hexdigest()[:12]
        try:
            with _locked(self.directory):
                _append(self.directory, row)
        except OSError:
            pass       # a missing flow note never fails the run

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
                self.finish_recorded = True
        except OSError:
            print('haejo: 작업(task) 종료 기록을 남기지 못했습니다 — 이 실행은 status 에서 uncertain 으로 보입니다.', file=sys.stderr)

    def close_if_requested(self, exit_code):
        if not self.finish_requested:
            return
        if not self.finish_recorded:
            print('HAEJO_TASK_FINISH_UNCERTAIN task remains open; invocation end was not recorded.', file=sys.stderr)
            return
        visible = exit_code == 1 and self.visible_document_verified
        done = exit_code == 0 or visible
        scope = 'visible_document_text' if visible else 'command' if done else 'failed_invocation'
        try:
            meta = end(self.task_id, 'done' if done else 'failed', root=self.directory.parent,
                       completion_scope=scope)
            _release_claims(self.task_id, self.directory.parent)
            stream = sys.stderr if self.json_output else sys.stdout
            print('HAEJO_TASK_FINISHED ' + json.dumps({'id':self.task_id,'result':meta['result'],
                  'completion_scope':scope},separators=(',',':')), file=stream)
            hint = prose_hint(self.task_id, at_end=True, root=self.directory.parent)
            if hint:
                print(hint, file=stream)
        except (OSError, TaskRefused):
            print('HAEJO_TASK_FINISH_UNCERTAIN task closure could not be recorded; inspect task status.', file=sys.stderr)

    def close_unadmitted_inline(self):
        if self.created_inline and not self.admitted:
            try:
                end(self.task_id, 'failed', root=self.directory.parent,
                    completion_scope='failed_invocation')
            except (OSError, TaskRefused):
                print('HAEJO_TASK_FINISH_UNCERTAIN task admission failed; inspect task status.', file=sys.stderr)

    def child_env(self):
        return {'HAEJO_TASK': self.task_id, 'HAEJO_TASK_PARENT': self.invocation}


def _flow_source(name):
    """builtin / library / inline, judged the way `haejo replay` resolves a name."""
    if name is None or not _FLOW_NAME.fullmatch(name):
        return 'inline'
    name = name.split(':', 1)[0]          # a recovery belongs to its recipe
    try:
        from .library import builders
        if name in builders():
            return 'builtin'
    except Exception:
        pass
    try:
        from .store import default_directory
        safe = ''.join(c for c in name if c.isalnum() or c in '_-')
        if safe and os.path.lexists(os.path.join(default_directory(), safe + '.json')):
            return 'library'
    except Exception:
        pass
    return 'inline'


def note_visible_document_result(report):
    """A visible-body witness, never a Save/dispatch receipt or permission."""
    binding = current.get()
    if (binding is not None and type(report) is dict
            and report.get('scope') == 'visible_document_text'
            and report.get('matches_requested_text') is True
            and type(report.get('remaining_steps')) is int and report['remaining_steps'] == 0
            and report.get('save_verified') is False and report.get('dispatch_confirmed') is False):
        binding.visible_document_verified = True


def inline_prose(args):
    """Strip `--detail` and `--why` (agent prose for the task record)."""
    rest, found = [], {}
    i = 0
    while i < len(args):
        value = args[i]
        if value == '--':
            rest.extend(args[i:])
            break
        name = next((n for n in ('detail', 'why') if value == '--' + n or value.startswith(f'--{n}=')), None)
        if name is None:
            rest.append(value); i += 1
            continue
        if name in found:
            raise TaskRefused(f'task_{name}_invalid', f'Use --{name} once.')
        if value == '--' + name:
            if i + 1 >= len(args) or args[i + 1].startswith('--'):
                raise TaskRefused(f'task_{name}_invalid', f'--{name} takes one text argument.')
            found[name] = args[i + 1]; i += 2
        else:
            found[name] = value.split('=', 1)[1]; i += 1
    detail = _prose(found.get('detail'), MAX_DETAIL, 'task_detail_invalid', multiline=True)
    why = _prose(found.get('why'), MAX_WHY, 'task_why_invalid', multiline=False)
    return rest, detail, why


def inline_options(args):
    """Strip local lifecycle options before command parsing or any UI work."""
    rest, goal, finish = [], None, False
    i = 0
    while i < len(args):
        value = args[i]
        if value == '--':
            rest.extend(args[i:])
            break
        if value == '--goal' or value.startswith('--goal='):
            if goal is not None:
                raise TaskRefused('task_goal_invalid', 'Use --goal once with --task new.')
            if value == '--goal':
                if i+1 >= len(args) or args[i+1].startswith('--'):
                    raise TaskRefused('task_goal_required', '--goal takes one goal sentence.')
                goal = args[i + 1]
                i += 2
            else:
                goal = value.split('=', 1)[1]
                i += 1
        elif value == '--finish-task':
            if finish:
                raise TaskRefused('task_invalid', 'Use --finish-task once.')
            finish = True
            i += 1
        else:
            rest.append(value)
            i += 1
    return rest, goal, finish


REUSE_HINT_AT = 2


def flow_shape(flow):
    """What makes two one-off session Flows "the same procedure": target,
    name and each step's action and role. Values (titles, typed text) differ
    per item and are left out."""
    from .flow import every_step
    parts = [flow.target, flow.name]
    for step in every_step(flow.steps):
        role = getattr(getattr(step, 'selector', None), 'role', None)
        parts.append(f'{step.action}:{role or ""}')
    return hashlib.sha256('\x1f'.join(parts).encode('utf-8', 'surrogatepass')).hexdigest()[:16]


def note_session_success(flow):
    """Count a successful unsaved session Flow by shape; return a reuse hint
    the run it reaches REUSE_HINT_AT in this task, else None."""
    binding = current.get()
    if binding is None or not binding.admitted or binding.ended:
        return None
    try:
        shape = flow_shape(flow)
        with _locked(binding.directory):
            _append(binding.directory, {'event': 'invocation_shape', 'invocation': binding.invocation, 'shape': shape})
            seen = 0
            with open(binding.directory / 'events.jsonl', encoding='utf-8') as handle:
                for line in handle:
                    if shape in line:
                        try:
                            row = json.loads(line)
                        except ValueError:
                            continue
                        seen += row.get('event') == 'invocation_shape' and row.get('shape') == shape
    except (OSError, ValueError, TypeError, AttributeError):
        return None
    if seen != REUSE_HINT_AT:
        return None
    return ('HAEJO_HINT reuse: this task has now run the same Flow shape '
            f'{seen} times. Save it once with `haejo session {flow.target} --helper --reuse-guide --save /abs/flow.json` '
            '(item values as {{params}}; a per-item popup as "window": {"url": "..."}), then repeat it with '
            '`haejo batch /abs/flow.json --helper`, one {"params":{...}} line per item.')


def note_flow(name, source=None):
    """Tie a flow run to the current task invocation, if there is one."""
    binding = current.get()
    if binding is not None:
        binding.note_flow(name, source)


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
    value = environ.get('HAEJO_TASK')
    if value:
        return value, False, out
    return None, False, out


def bind(task_id, command, *, root=None, environ=None):
    environ = os.environ if environ is None else environ
    directory = _task_dir(task_id, root)
    if not directory.exists():
        raise TaskRefused('task_unknown', f'No task {task_id} on this computer. Start one with `haejo task start "<goal>"`.')
    _private_dir(directory, create=False)
    meta = _load_meta(directory)
    if meta['state'] != 'open':
        # Checked again under the lock at admission; this refuses before any log or UI work.
        raise TaskRefused('task_closed', f"Task {task_id} already ended ({meta.get('result')}); start a new task for new work.")
    parent = environ.get('HAEJO_TASK_PARENT')
    if parent is not None and not _INVOCATION.fullmatch(parent):
        parent = None
    return Binding(task_id, directory, command, parent)


# ---------------------------------------------------------------- CLI

USAGE = ('usage: haejo task start "<goal>" [--detail "<description>"] [--json]\n'
         '       haejo task describe [<task-id>] "<the user\'s request>" [--json]\n'
         '       haejo task note [<task-id>] "<decision>" [--json]\n'
         '       haejo task status [<task-id>] [--steps] [--json]\n'
         '       haejo task list [--all] [--json]\n'
         '       haejo task end [<task-id>] --result done|failed|abandoned [--note "<summary>"] [--json]')


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
    value = os.environ.get('HAEJO_TASK')
    if value:
        return value
    raise TaskRefused('task_invalid', 'Give the task ID (or set HAEJO_TASK); Haejo never guesses a latest task.')


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
            rest, detail, why = inline_prose(rest)
            if len(rest) != 1 or rest[0].startswith('--') or why is not None:
                print(USAGE); return 2
            meta = start(rest[0], detail=detail, root=root)
            if as_json:
                print(json.dumps({'type': 'task', 'task_id': meta['id'], 'state': 'open'}, ensure_ascii=False))
            else:
                print(f"HAEJO_TASK {meta['id']}")
                print(f"Prefix every haejo command for this goal: HAEJO_TASK={meta['id']} haejo …  "
                      f"(or add --task {meta['id']}). Finish with: haejo task end {meta['id']} --result done|failed|abandoned")
                hint = prose_hint(meta['id'], root=root)
                if hint:
                    print(hint)
            return 0
        if sub == 'describe':
            if not rest or any(a.startswith('--') for a in rest) or len(rest) > 2:
                print(USAGE); return 2
            task_id = _resolve_id(rest[:-1])
            describe(task_id, rest[-1], root=root)
            print(json.dumps({'type': 'task_describe', 'task_id': task_id, 'recorded': True}) if as_json
                  else f'description recorded on {task_id}')
            return 0
        if sub == 'note':
            if not rest or any(a.startswith('--') for a in rest) or len(rest) > 2:
                print(USAGE); return 2
            task_id = _resolve_id(rest[:-1])
            note(task_id, rest[-1], root=root)
            print(json.dumps({'type': 'task_note', 'task_id': task_id, 'recorded': True}) if as_json
                  else f'note recorded on {task_id}')
            return 0
        if sub == 'status':
            steps = '--steps' in rest
            rest = [a for a in rest if a != '--steps']
            if any(a.startswith('--') for a in rest):
                print(USAGE); return 2
            report = status(_resolve_id(rest), root=root)
            if steps:
                for item in report['invocations']:
                    item['steps'] = invocation_steps(item)
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
            summary = None
            if '--note' in rest:
                k = rest.index('--note')
                if rest.count('--note') != 1 or k + 1 >= len(rest):
                    print(USAGE); return 2
                summary = rest[k + 1]
                rest = rest[:k] + rest[k + 2:]
            if '--result' not in rest:
                print(USAGE); return 2
            i = rest.index('--result')
            if i + 1 >= len(rest) or rest.count('--result') != 1:
                print(USAGE); return 2
            result = rest[i + 1]
            meta = end(_resolve_id(rest[:i] + rest[i + 2:]), result, root=root, summary=summary)
            _release_claims(meta['id'], root)
            report = status(meta['id'], root=root)
            if as_json:
                print(json.dumps({'type': 'task', 'task_id': meta['id'], 'state': 'closed', 'result': result,
                                  'counts': report['counts']}, ensure_ascii=False))
            else:
                print(f"task {meta['id']} ended: {result} (caller-declared; not a verification)")
                hint = prose_hint(meta['id'], at_end=True, root=root)
                if hint:
                    print(hint)
                c = report['counts']
                if c['in_flight'] or c['uncertain']:
                    print(f"  note: {c['in_flight']} in_flight, {c['uncertain']} uncertain — inspect the target state before any retry.")
            return 0
    except TaskRefused as exc:
        _emit_refusal(exc, as_json)
        return 2
    except OSError as exc:
        from .private_fs import access_repair_hint
        _emit_refusal(TaskRefused('task_storage_unavailable', 'The private task directory could not be used.'
                                  + access_repair_hint(exc)), as_json)
        return 2
    print(USAGE)
    return 2


def _format_status(report):
    c = report['counts']
    head = [f"task {report['task_id']}  {report['state']}" + (f" ({report['result']})" if report['result'] else ''),
            f"goal: {report['goal']}"]
    if report.get('detail'):
        head.extend('detail: ' + line if k == 0 else '        ' + line
                    for k, line in enumerate(report['detail'].splitlines()))
    head.append(f"invocations: {len(report['invocations'])}  ok {c['ok']}  failed {c['failed']}  "
                f"in_flight {c['in_flight']}  uncertain {c['uncertain']}")
    pending = list(report.get('notes') or [])
    def flush_notes(before):
        while pending and (before is None or (pending[0]['at'] or '') <= (before or '')):
            item = pending.pop(0)
            lines = item['text'].splitlines() or ['']
            head.append(f"   note {item['at'] or '-'} {lines[0]}")
            head.extend('        ' + line for line in lines[1:])
    for n, item in enumerate(report['invocations'], 1):
        flush_notes(item['started_at'])
        targets = ','.join(item['targets']) if item['targets'] else '-'
        result = {'ok': 'ok', 'failed': f"exit {item['exit_code']}"}.get(item['state'], item['state'])
        reason = f" {item['error']}" + (f"/{item['stage']}" if item['stage'] else '') if item['error'] else ''
        ms = f" {item['elapsed_ms']}ms" if item['elapsed_ms'] is not None else ''
        child = ' (child)' if item.get('parent') else ''
        flows = ''.join(f" flow={f['name'] or ('#' + f['ref'] if f.get('ref') else '(unnamed)')}[{f['source']}]"
                        for f in item.get('flows') or [])
        head.append(f"  {n:>3} {item['started_at']} {item['command']}{child}{flows} {targets} {result}{reason}{ms}")
        if item.get('why'):
            head.append(f"        why: {item['why']}")
        steps = item.get('steps')
        if steps is not None:
            if not steps.get('available'):
                head.append(f"        steps: {steps.get('reason', 'unavailable')}")
            for k, step in enumerate(steps.get('steps') or [], 1):
                what = step.get('operation', step['event'])
                if step.get('action'):
                    what += ':' + step['action']
                tail = ' '.join(str(step[x]) for x in ('type', 'outcome', 'status', 'error', 'stage') if step.get(x))
                head.append(f"        {k:>3} +{step.get('elapsed_ms', '?')}ms {what} {step.get('target', '-')} {tail}".rstrip())
            if steps.get('truncated'):
                head.append('        (step receipt truncated)')
    flush_notes(None)
    if c['uncertain']:
        head.append('uncertain = no end record and the process is gone: inspect the target before retrying.')
    if report['damaged_records']:
        head.append(f"damaged records skipped: {report['damaged_records']}")
    return '\n'.join(head)


def invocation_steps(item):
    """The content-free step receipts of one invocation, from its access log.

    Only the access log named in the task record, only when it carries the
    same invocation ID, and only the already content-free receipt fields.
    """
    from .access_log import _NAMES, read_run
    name = item.get('access_log')
    if not isinstance(name, str) or not _NAMES.fullmatch(name):
        return {'available': False, 'reason': 'no_access_log', 'steps': []}
    try:
        raw = read_run(name, limit=MAX_STEP_LOG_BYTES)
    except FileNotFoundError:
        return {'available': False, 'reason': 'access_log_removed', 'steps': []}
    except (OSError, ValueError):
        return {'available': False, 'reason': 'access_log_unreadable', 'steps': []}
    keep = ('event', 'elapsed_ms', 'operation', 'target', 'action', 'type', 'outcome', 'status', 'error', 'stage')
    steps, owner, truncated = [], None, False
    for line in raw.split(b'\n'):
        try:
            row = json.loads(line)
        except (ValueError, UnicodeError):
            continue
        if type(row) is not dict:
            continue
        if row.get('event') == 'command_start':
            owner = row.get('invocation_id')
        elif row.get('event') == 'log_truncated':
            truncated = True
        elif row.get('event') in ('access_end', 'task_result'):
            steps.append({k: row[k] for k in keep if isinstance(row.get(k), (str, int)) and not isinstance(row.get(k), bool)})
    if owner != item.get('invocation'):
        return {'available': False, 'reason': 'access_log_mismatch', 'steps': []}
    return {'available': True, 'steps': steps, 'truncated': truncated}


GUIDE = ('A task groups every Haejo call made for one user goal. Start it first,\n'
         'run every haejo command for the goal with HAEJO_TASK=<id> (or --task <id>),\n'
         'then end it. It holds no helper, lease or approval between calls.\n'
         '--detail describes the task; --why "<reason>" on any bound command and\n'
         '`haejo task note "<decision>"` record the agent\'s decisions in the task.')
