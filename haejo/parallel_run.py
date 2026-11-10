"""Bounded window jobs, each on its own signed launcher/helper connection.

Window IDs belong to this invocation, never to a saved Flow. No shared Python
driver, automatic resend, app-wide fallback, or simulated mouse movement.
"""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import tempfile
import threading
import time

from .flow import Flow, every_step

MAX_JOBS = 4
MAX_MANIFEST_BYTES = 1024 * 1024
_ID = re.compile(r'[A-Za-z0-9][A-Za-z0-9_-]{0,39}\Z')
_TARGET = re.compile(r'[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+\Z')
_CODE = re.compile(r'[a-z][a-z0-9_]{0,80}\Z')


class ParallelRefused(ValueError):
    """The batch was refused before any worker started."""


class BatchControl:
    """Listen for the menu's stop-all signal, including workers still waiting.

    This notification can only stop a batch. It cannot start input, reset an
    abort, supply a Flow, or grant permissions. Individual run stops stay local.
    """
    name = 'ai.callabo.haejo.runtime.stop-all'

    def __init__(self, *, targets=()):
        self.targets = frozenset(target.lower() for target in targets)

    def __enter__(self):
        if threading.current_thread() is not threading.main_thread():
            raise ParallelRefused('parallel_requires_main_thread')
        try:
            from Foundation import NSDistributedNotificationCenter, NSRunLoop, NSDate
            self.center = NSDistributedNotificationCenter.defaultCenter()
            self.loop, self.date = NSRunLoop.currentRunLoop(), NSDate
            self.stopped = False
            def stop(note):
                info = note.userInfo()
                if info is None:
                    return
                schema, uid = info.get('schema'), info.get('uid')
                # A scoped sender (including the owned-fixture test) can stop
                # just matching batches. The menu omits targets to stop all.
                if 'targets' in info:
                    try:
                        scope = tuple(info['targets'])
                    except TypeError:
                        return
                    if (not 1 <= len(scope) <= MAX_JOBS or not all(isinstance(t, str) for t in scope)
                            or frozenset(t.lower() for t in scope) != self.targets):
                        return
                # Swift NSNumber integers bridge to an int subclass in PyObjC.
                if (isinstance(schema, int) and not isinstance(schema, bool) and schema == 1
                        and isinstance(uid, int) and not isinstance(uid, bool) and uid == os.getuid()):
                    self.stopped = True
            self.observer = self.center.addObserverForName_object_queue_usingBlock_(self.name, None, None, stop)
            if self.observer is None:
                raise RuntimeError('observer unavailable')
        except (ImportError, AttributeError, RuntimeError):
            raise ParallelRefused('parallel_control_unavailable') from None
        return self

    def pump(self):
        self.loop.runUntilDate_(self.date.dateWithTimeIntervalSinceNow_(0.05))

    def __exit__(self, *exc):
        self.center.removeObserver_(self.observer)


@dataclass(frozen=True)
class WindowJob:
    id: str
    target: str
    window_id: int
    flow_json: str


def parse_jobs(manifest):
    """Validate the entire batch and freeze bound flows before starting a job."""
    if (not isinstance(manifest, dict) or set(manifest) != {'schema', 'jobs'}
            or type(manifest['schema']) is not int or manifest['schema'] != 1
            or not isinstance(manifest['jobs'], list) or not 1 <= len(manifest['jobs']) <= MAX_JOBS):
        raise ParallelRefused('parallel_requires_schema_1_and_1_to_4_jobs')
    jobs, ids, scopes = [], set(), set()
    for raw in manifest['jobs']:
        if (not isinstance(raw, dict) or set(raw) != {'id', 'window_id', 'flow'}
                or not isinstance(raw['id'], str) or not _ID.fullmatch(raw['id'])
                or raw['id'] in ids or type(raw['window_id']) is not int
                or not 0 < raw['window_id'] <= 0xffffffff or not isinstance(raw['flow'], dict)):
            raise ParallelRefused('parallel_invalid_job_or_duplicate_id')
        try:
            template = Flow.from_json(json.dumps(raw['flow'], allow_nan=False), strict_checks=True)
            if any(step.for_each is not None for step in every_step(template.steps)):
                raise ValueError('expand repetitions before submitting parallel jobs')
            flow = template.bind()
        except (ValueError, TypeError, KeyError, ArithmeticError, RecursionError):
            raise ParallelRefused('parallel_invalid_flow') from None
        if not _TARGET.fullmatch(flow.target) or len(flow.target) > 255:
            raise ParallelRefused('parallel_requires_bundle_id')
        scope = (flow.target.lower(), raw['window_id'])
        if scope in scopes:
            raise ParallelRefused('parallel_duplicate_window')
        steps = every_step(flow.steps)
        if not steps or len(steps) > 100:
            raise ParallelRefused('parallel_requires_1_to_100_steps')
        for step in steps:
            if (step.action not in ('read', 'click', 'set_value', 'type_text')
                    or step.selector is None or step.postcondition is None
                    or step.unverified_ok or step.on_uncertain
                    or step.safety is None or step.safety.reversibility != 'reversible'
                    or not set(step.safety.effects) <= {'read', 'write_ephemeral'}
                    or (step.action == 'set_value' and set(step.params) != {'value'})):
                raise ParallelRefused('parallel_requires_checked_reversible_ax_steps')
        from .contract import policy
        if any(policy(step.safety).risk != 'none' for step in steps):
            raise ParallelRefused('parallel_requires_unattended_contracts')
        snapshot = json.dumps(json.loads(flow.to_json(compact=True)), ensure_ascii=False, separators=(',', ':'))
        if len(snapshot.encode('utf-8')) > MAX_MANIFEST_BYTES:
            raise ParallelRefused('parallel_flow_over_budget')
        jobs.append(WindowJob(raw['id'], flow.target, raw['window_id'], snapshot))
        ids.add(raw['id']); scopes.add(scope)
    return tuple(jobs)


class SessionReceipt:
    """Metadata from real replay/driver replies; never includes observed values."""
    def __init__(self):
        self.replayed = None
        self.may_have_acted = False
        self.error = None
        self.coordination_ms = 0
        self.helper_pid = None

    def note(self, reply):
        if not isinstance(reply, dict):
            return
        elapsed = reply.get('coordination_elapsed_ms')
        if type(elapsed) is int and 0 <= elapsed <= 600000:
            self.coordination_ms += elapsed
        error = reply.get('error')
        if reply.get('type') == 'error' and isinstance(error, str) and _CODE.fullmatch(error):
            self.error = error

    def wrap(self, inner):
        owner = self
        identity = getattr(inner, 'helper_process_identity', None)
        pid = getattr(identity, 'pid', None)
        if type(pid) is int and 0 < pid <= 0x7fffffff:
            self.helper_pid = pid
        class ReceiptDriver:
            # This is a method/read-only-attribute proxy. Replay/session code
            # must not assign driver state here instead of on the inner driver.
            def __getattr__(self, name):
                method = getattr(inner, name)
                if name not in ('observe', 'act', 'probe', 'wait_until', 'scope_window'):
                    return method
                def traced(*args, **kwargs):
                    previous = owner.may_have_acted
                    if name == 'act':
                        owner.may_have_acted = True
                    reply = method(*args, **kwargs)
                    if name == 'act' and isinstance(reply, dict) and reply.get('effect') == 'not_started':
                        owner.may_have_acted = previous
                    owner.note(reply)
                    return reply
                return traced
        return ReceiptDriver()

    def summary(self, code):
        verified = code == 0 and self.replayed is not None and self.replayed.ok is True
        if not verified and self.replayed is not None:
            for entry in self.replayed.log:
                if entry.get('status') in ('error', 'gated', 'unverified'):
                    detail = entry.get('detail')
                    error = entry.get('error') or (detail.get('error') if isinstance(detail, dict) else None)
                    if self.error is None and isinstance(error, str) and _CODE.fullmatch(error):
                        self.error = error
        effect = 'observed' if verified else ('unknown' if self.may_have_acted else 'not_started')
        return {'schema': 1, 'ok': verified, 'effect': effect,
                'error': None if verified else (self.error or 'session_result_unavailable'),
                'coordination_elapsed_ms': self.coordination_ms, 'helper_pid': self.helper_pid}


def _stop(process):
    """Stop the launcher AND its inherited-channel child, then reap the launcher."""
    if process.poll() is None:
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        except PermissionError:
            if process.poll() is None:
                raise
        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            pass
    # The launcher may have exited before its Python child; the group is still
    # ours until every member has gone. Do not leave delayed input behind.
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    except PermissionError:
        # Darwin can report EPERM for a group whose last live member exited
        # after TERM. A still-running launcher is a real cleanup failure.
        if process.poll() is None:
            raise
    process.wait()


def run_parallel_jobs(manifest, *, timeout=60, on_event=None):
    """Run at most four checked AX window jobs; return results in input order.

    The fixed sibling launcher creates a new authenticated channel for each
    process. Never duplicate or pass this process's inherited helper descriptor.
    A timeout or missing receipt is unknown; this function never retries a job.
    """
    jobs = parse_jobs(manifest)
    if sys.platform != 'darwin':
        raise ParallelRefused('parallel_requires_macos')
    if type(timeout) is not int or not 1 <= timeout <= 600:
        raise ParallelRefused('parallel_timeout_requires_1_to_600_seconds')
    launcher = Path(__file__).resolve().parents[1] / 'launcher' / 'haejo'
    # Read on the caller's thread: pool workers do not inherit ContextVars.
    # Only the parent's already-validated task, never an inherited raw value.
    from .task import current as task_binding
    bound = task_binding.get()
    task_env = dict(bound.child_env()) if bound is not None else {}
    if not launcher.is_file() or not os.access(launcher, os.X_OK):
        raise ParallelRefused('parallel_signed_launcher_unavailable')
    emit = on_event or (lambda event: None)
    active, lock, cancelled = set(), threading.Lock(), threading.Event()
    def cancel_active():
        cancelled.set()
        with lock:
            processes = tuple(active)
            active.clear()
        for process in processes:
            _stop(process)
    def event(job, state):
        with lock:
            emit({'type':'parallel_job', 'id':job.id, 'target':job.target,
                  'window_id':job.window_id, 'state':state})
    def one(job):
        started = time.monotonic()
        result = {'id':job.id, 'target':job.target, 'window_id':job.window_id,
                  'ok':False, 'effect':'not_started', 'error':'parallel_cancelled',
                  'coordination_elapsed_ms':0, 'helper_pid':None}
        if cancelled.is_set():
            return result
        with tempfile.TemporaryDirectory(prefix='haejo-parallel-') as directory:
            receipt = Path(directory) / 'receipt.json'
            command = [str(launcher), 'session', job.target, '--helper', '--window-id', str(job.window_id),
                       '--receipt', str(receipt)]
            env = {k:v for k,v in os.environ.items() if not k.startswith('HAEJO_')}
            env.update(task_env)
            env['HAEJO_HELPER_MODE'] = 'warm'
            process = None
            try:
                with lock:
                    if cancelled.is_set():
                        return result
                    process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
                                               stderr=subprocess.DEVNULL, text=True, env=env,
                                               start_new_session=True, close_fds=True)
                    active.add(process)
                event(job, 'running')
                process.communicate(job.flow_json + '\n', timeout=timeout)
                if receipt.is_file() and receipt.stat().st_size <= 4096:
                    raw = json.loads(receipt.read_text(encoding='utf-8'))
                    if (type(raw) is dict and set(raw) == {'schema','ok','effect','error','coordination_elapsed_ms','helper_pid'}
                            and type(raw['schema']) is int and raw['schema'] == 1
                            and type(raw['ok']) is bool and raw['ok'] == (process.returncode == 0)
                            and raw['effect'] in ('observed','not_started','unknown')
                            and (raw['error'] is None if raw['ok'] else
                                 isinstance(raw['error'], str) and _CODE.fullmatch(raw['error']))
                            and type(raw['coordination_elapsed_ms']) is int and raw['coordination_elapsed_ms'] >= 0
                            and (raw['helper_pid'] is None or type(raw['helper_pid']) is int and 0 < raw['helper_pid'] <= 0x7fffffff)
                            and (raw['effect'] == 'observed') == raw['ok']):
                        result.update({k:v for k,v in raw.items() if k != 'schema'})
                    else:
                        result.update(effect='unknown', error='parallel_invalid_receipt')
                else:
                    result.update(effect='unknown', error='parallel_cancelled' if cancelled.is_set() else 'parallel_receipt_unavailable')
            except subprocess.TimeoutExpired:
                result.update(effect='unknown', error='parallel_timeout')
            except (OSError, ValueError):
                result.update(effect='unknown' if process is not None else 'not_started', error='parallel_worker_unavailable')
            finally:
                if process is not None:
                    with lock:
                        owns_cleanup = process in active
                        active.discard(process)
                    if owns_cleanup and process.poll() is None:
                        _stop(process)
                    if process.stdin is not None:
                        try:
                            process.stdin.close()
                        except (OSError, ValueError):
                            pass  # A stopped child may have closed its read end.
            result['elapsed_ms'] = round((time.monotonic() - started)*1000)
            event(job, 'verified' if result['ok'] else ('unknown' if result['effect']=='unknown' else 'failed'))
            return result
    with BatchControl(targets=(job.target for job in jobs)) as control:
        pool = ThreadPoolExecutor(max_workers=len(jobs))
        try:
            for job in jobs:
                event(job, 'queued')
            futures = [pool.submit(one, job) for job in jobs]
            while not all(future.done() for future in futures):
                control.pump()
                if control.stopped and not cancelled.is_set():
                    cancel_active()
            results = [future.result() for future in futures]
        except BaseException:
            cancel_active()
            raise
        finally:
            pool.shutdown(wait=True, cancel_futures=True)
    return {'type':'parallel_result', 'ok':all(r['ok'] for r in results),
            'cancelled':cancelled.is_set(), 'jobs':results}


def main(args):
    if sys.platform != 'darwin':
        print('parallel is macOS-only'); return 2
    args = list(args)
    timeout = 60
    if '--timeout' in args:
        i = args.index('--timeout')
        if args.count('--timeout') != 1 or i+1 >= len(args) or not args[i+1].isascii() or not args[i+1].isdigit():
            print('parallel_timeout_requires_1_to_600_seconds'); return 2
        timeout = int(args[i+1]); del args[i:i+2]
    files = [v for v in args if v not in ('--helper','--json')]
    if len(files) != 1 or files[0].startswith('-') or args.count('--helper') != 1 or args.count('--json') > 1:
        print('usage: haejo parallel <manifest.json> --helper [--timeout 1..600] [--json]'); return 2
    try:
        with open(files[0], 'rb') as stream:
            data = stream.read(MAX_MANIFEST_BYTES + 1)
        if len(data) > MAX_MANIFEST_BYTES:
            raise ParallelRefused('parallel_manifest_over_budget')
        manifest = json.loads(data)
    except (OSError, ValueError, TypeError, RecursionError):
        print(json.dumps({'type':'error','error':'parallel_invalid_manifest','effect':'not_started'})); return 2
    try:
        events = None if '--json' in args else lambda row: print(json.dumps(row), flush=True)
        result = run_parallel_jobs(manifest, timeout=timeout, on_event=events)
    except ParallelRefused as exc:
        print(json.dumps({'type':'error','error':str(exc),'effect':'not_started'})); return 2
    except (OSError, ValueError, TypeError, RecursionError):
        print(json.dumps({'type':'error','error':'parallel_coordinator_failed','effect':'unknown'})); return 1
    print(json.dumps(result)); return 0 if result['ok'] else 1
