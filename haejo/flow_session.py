"""One signed connection: observe, accept one bounded flow, replay, exit."""
import json
import shlex
import os
import select
import sys
import time
from contextlib import contextmanager

from .access_log import record_failure
from .flow import Flow, Step, every_step, literal_step


MAX_FLOW_BYTES = 1024 * 1024
MAX_OBSERVATION_PAGES = 8


@contextmanager
def flow_input_mode(fd):
    original = None
    # Windows consoles have no termios; their line mode already delivers
    # one whole line, which is all a session reads.
    if os.isatty(fd) and sys.platform != "win32":
        import termios
        original = termios.tcgetattr(fd)
        settings = list(original)
        settings[6] = list(original[6])
        settings[3] &= ~(termios.ICANON | termios.ECHO)
        settings[6][termios.VMIN] = 1
        settings[6][termios.VTIME] = 0
        termios.tcsetattr(fd, termios.TCSANOW, settings)
    try:
        yield
    finally:
        if original is not None:
            termios.tcsetattr(fd, termios.TCSANOW, original)


def _windows_reader(fd, *, depth=2):
    """select() takes only sockets on Windows, so one thread reads the pipe.

    The queue holds at most `depth` chunks: while a long batch job runs, the
    thread waits instead of reading the rest of stdin into memory.
    """
    import queue
    import threading
    chunks = queue.Queue(maxsize=depth)

    def pump():
        while True:
            try:
                chunk = os.read(fd, 65536)
            except OSError:
                chunk = b''
            chunks.put(chunk)
            if not chunk:
                return
    threading.Thread(target=pump, daemon=True).start()

    def read(remaining):
        try:
            return chunks.get(timeout=remaining)
        except queue.Empty:
            raise TimeoutError('session_idle_timeout') from None
    read.queue = chunks   # for tests: bounded backlog
    return read


def read_flow_line(fd, timeout, *, platform=None, reader=None):
    deadline = time.monotonic() + timeout
    data = bytearray()
    windows = (platform or sys.platform) == "win32"
    if windows and reader is None:
        reader = _windows_reader(fd)
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError('session_idle_timeout')
        if windows:
            chunk = reader(remaining)
            if len(data) + len(chunk) > MAX_FLOW_BYTES + 1:
                chunk = chunk[:MAX_FLOW_BYTES + 1 - len(data)]
        elif not select.select([fd], [], [], remaining)[0]:
            raise TimeoutError('session_idle_timeout')
        else:
            chunk = os.read(fd, min(65536, MAX_FLOW_BYTES + 1 - len(data)))
        if not chunk:
            raise ValueError('session_input_closed')
        data.extend(chunk)
        if len(data) > MAX_FLOW_BYTES:
            raise ValueError('session_flow_over_budget')
        if b'\n' in data:
            line, tail = data.split(b'\n', 1)
            if tail.strip():
                raise ValueError('session_accepts_one_flow')
            return line.decode('utf-8')


def decode_session_flow(raw, target, document=None, *, steps=False):
    """Expand optional bound steps; keep full Flow and pinned-edit semantics."""
    payload = json.loads(raw)
    if steps and isinstance(payload, dict) and set(payload) == {'steps'}:
        from .command_help import session_defaults
        payload = {**session_defaults(target, document), **payload}
        raw = json.dumps(payload, ensure_ascii=False)
    single_edit = isinstance(payload, dict) and ('set_value' in payload or 'check_value' in payload)
    if single_edit:
        from .flow_errors import FlowFieldError
        if document is None:
            raise FlowFieldError('edit requires document session', 'set_value',
                                 'Use a full Flow, or a session with --document for a single edit step.')
        allowed = (set(Step.__dataclass_fields__) - {'action', 'params'}) | {'set_value', 'check_value'}
        if set(payload) - allowed:
            raise FlowFieldError('mixed edit and Flow header', 'set_value',
                                 'Send one edit step without Flow header fields, or a full Flow.')
        payload = {'schema': 2, 'name': 'document-edit', 'target': target,
                   'selector_defaults': {'role': 'TextArea', 'identifier': 'First Text View',
                                         'ancestor': document},
                   'safety_defaults': {'effects': ['read'], 'reversibility': 'reversible',
                                       'resource': {'object_type': 'document', 'scope': 'item'}},
                   'steps': [payload]}
        raw = json.dumps(payload, ensure_ascii=False)
    flow = Flow.from_json(raw, strict_checks=True)
    if single_edit:
        # A step-only message has no parameter namespace. Its supplied text,
        # selectors and evidence are literal data, including {{template}} text.
        flow.steps = [literal_step(step) for step in flow.steps]
    return flow


def read_session_flow(fd, timeout, emit, *, prepare=None, observe_next=None, find_observation=None, metrics=None, decode=None):
    """Repair interactive schema errors before dispatch on the same connection."""
    deadline = time.monotonic() + timeout
    reader = (_CHAIN_READER.get(fd) or _windows_reader(fd)) if sys.platform == 'win32' else None
    while True:
        # Framing, EOF and budget errors are terminal; only a complete JSON line
        # rejected by Flow parsing can be corrected without starting over.
        raw = read_flow_line(fd, max(0, deadline - time.monotonic()), reader=reader)
        counted = False
        try:
            if observe_next is not None or find_observation is not None:
                command = json.loads(raw)
                if isinstance(command, dict) and 'observe_next' in command:
                    if (set(command) != {'observe_next'} or command['observe_next'] is not True
                            or observe_next is None):
                        from .flow_errors import FlowFieldError
                        raise FlowFieldError('invalid_observation_request', 'observe_next',
                                             'Send only {"observe_next":true}; send the Flow separately.')
                    observe_next()
                    continue
                if isinstance(command, dict) and 'find_in_observation' in command:
                    from .protocol import reveal_problem
                    from .flow_errors import FlowFieldError
                    label = command['find_in_observation']
                    if (set(command) != {'find_in_observation'} or not isinstance(label, str)
                            or reveal_problem([label]) or find_observation is None):
                        raise FlowFieldError('invalid_observation_lookup', 'find_in_observation',
                                             'Send one exact label as text, without a Flow or other commands.')
                    find_observation(label)
                    continue
            if metrics is not None:
                metrics['flow_input_attempts'] = metrics.get('flow_input_attempts', 0) + 1
                metrics['flow_input_utf8_bytes'] = metrics.get('flow_input_utf8_bytes', 0) + len(raw.encode('utf-8'))
                counted = True
            flow = decode(raw) if decode is not None else Flow.from_json(raw, strict_checks=True)
            return prepare(flow) if prepare is not None else flow
        except (ValueError, TypeError, KeyError, RecursionError) as exc:
            if metrics is not None and not counted:
                metrics['flow_input_attempts'] = metrics.get('flow_input_attempts', 0) + 1
                metrics['flow_input_utf8_bytes'] = metrics.get('flow_input_utf8_bytes', 0) + len(raw.encode('utf-8'))
            if not os.isatty(fd):
                raise
            from .flow_errors import feedback
            if metrics is not None:
                metrics['flow_input_corrections'] = metrics.get('flow_input_corrections', 0) + 1
            record_failure('session_invalid_flow', 'load')
            emit('session_invalid_flow: ' + feedback(exc))
            emit('HAEJO_SESSION_READY correct the JSON on this same session; no UI input was sent. The original input deadline still applies.')


def prepare_session_flow(flow, target, window=None):
    from .flow_errors import FlowFieldError
    if flow.target != target:
        raise FlowFieldError('session_target_mismatch', 'target', 'Match the target of this session.')
    # The session already chose its window; a saved Flow keeps the selector
    # (never the live ID) so a replay finds the same kind of window again.
    if isinstance(window, dict):
        if flow.window is None:
            flow.window = dict(window)
        elif flow.window != window:
            raise FlowFieldError('session_window_mismatch', 'window',
                                 'Use the same selector as this session\'s --window-match, or omit "window".')
    elif flow.window is not None:
        raise FlowFieldError('session_window_mismatch', 'window',
                             'Start this session with --window-match matching "window", or omit it.')
    if any(step.action in ('decide', 'visual') for step in every_step(flow.steps)):
        raise FlowFieldError('session_requires_deterministic_flow', 'steps', 'Use deterministic steps here; use run for model judgment.')
    template = flow.to_json(compact=True)
    if flow.params or flow.tables or flow.derived:
        try:
            flow = flow.bind()
        except (ValueError, TypeError, KeyError, ArithmeticError) as exc:
            raise FlowFieldError('session_invalid_parameters', 'params',
                                 'Provide defaults for every {{name}}; session accepts no -p flags.') from exc
    if flow.target != target:
        raise FlowFieldError('session_target_mismatch', 'target', 'Bound parameters must keep the session target.')
    from .flow_errors import contract_field_error
    for index, step in enumerate(every_step(flow.steps)):
        if step.safety is not None:
            problem = contract_field_error(step.safety, 'steps['+str(index)+'].safety')
            if problem is not None:
                raise problem
    return flow, template


def run_session(args, *, make_driver, run_flow, stdin, emit):
    """Optionally publish a private, content-free receipt for a coordinator."""
    args = list(args)
    if '--receipt' not in args:
        return _run_session(args, make_driver=make_driver, run_flow=run_flow, stdin=stdin, emit=emit)
    i = args.index('--receipt')
    if (args.count('--receipt') != 1 or i+1 >= len(args)
            or '\0' in args[i+1] or not os.path.isabs(args[i+1]) or os.path.lexists(args[i+1])
            or not os.path.isdir(os.path.dirname(args[i+1]))):
        emit('session_receipt: use one absolute new path in an existing directory'); return 2
    path = args[i+1]; del args[i:i+2]
    from .parallel_run import SessionReceipt
    from .storage import write_private
    receipt = SessionReceipt()
    def driver_factory(flags):
        return receipt.wrap(make_driver(flags))
    def replay_flow(*positional, **kwargs):
        previous = kwargs.get('_result_observer')
        def observed(result):
            receipt.replayed = result
            if previous is not None:
                previous(result)
        return run_flow(*positional, **dict(kwargs, _result_observer=observed))
    try:
        code = _run_session(args, make_driver=driver_factory, run_flow=replay_flow, stdin=stdin, emit=emit)
    except BaseException as exc:
        from .helper import HelperLeaseRefused, HelperUnavailable
        if isinstance(exc, HelperLeaseRefused):
            receipt.note(exc.result())
        elif isinstance(exc, HelperUnavailable):
            receipt.error = 'helper_unavailable'
        try:
            write_private(path, json.dumps(receipt.summary(1)), overwrite=False)
        except OSError:
            pass
        raise
    try:
        write_private(path, json.dumps(receipt.summary(code)), overwrite=False)
    except OSError:
        emit('session_receipt_write_failed: inspect the task before replaying'); return 1
    return code


MAX_CHAINED_APPS = 4
# Chained apps read their Flows from one stdin. On Windows a reader is a thread
# blocked on that pipe, so the chain owns one reader for every app; a second
# would race the first for the next app's line.
_CHAIN_READER = {}
_INHERITED = ('--helper', '--timings', '--guide', '--steps')


def _run_session(args, *, make_driver, run_flow, stdin, emit):
    """One app, or several in order with `--then <bundle-id> [its options]`.

    Each later app starts only after the previous one finished with a checked
    result; its guide and observation follow that result in the same output,
    so the author reads the value and writes the next Flow without another
    command. Each app is its own session: its own target, observation,
    replay and checks."""
    args = list(args)
    if '--then' not in args:
        return _run_one_session(args, make_driver=make_driver, run_flow=run_flow, stdin=stdin, emit=emit)
    segments, current = [], []
    for value in args:
        if value == '--then':
            segments.append(current); current = []
        else:
            current.append(value)
    segments.append(current)
    if len(segments) > MAX_CHAINED_APPS or any(not seg or seg[0].startswith('-') for seg in segments[1:]):
        emit('session_then: use --then <bundle-id> [--document /absolute/path] after the first app, up to '
             + str(MAX_CHAINED_APPS) + ' apps'); return 2
    inherited = [flag for flag in _INHERITED if flag in segments[0]]
    # The signed launcher hands this process one helper channel; every app in
    # the chain uses it, and it closes once at the end.
    shared = {}

    class _Kept:
        def __init__(self, inner):
            self._inner = inner
        def __getattr__(self, name):
            return getattr(self._inner, name)
        def close(self):
            pass

    def kept_driver(flags):
        key = tuple(flags)
        if key not in shared:
            shared[key] = make_driver(flags)
        return _Kept(shared[key])

    def end_app():
        # The next app starts unpinned: the previous app's window scope and
        # leases end with it, exactly as if its own command had ended.
        for driver in shared.values():
            if getattr(driver, '_window_scope', None) is None:
                continue
            release = getattr(driver, 'release_targets', None)
            try:
                if callable(release):
                    release()
            except Exception:
                pass
            if getattr(driver, '_window_scope', None) is not None:
                return False
        return True

    def stop(index, segment, completed):
        later = segments[index + 1:]
        emit('HAEJO_SESSION_STOPPED later apps not started: ' + ', '.join(seg[0] for seg in later))
        later = [later[0] + [flag for flag in inherited if flag not in later[0]]] + later[1:]
        if completed:
            emit('HAEJO_SESSION_RESUME ' + segment[0] + ' already finished its task; continue with the next app: '
                 'haejo session ' + ' --then '.join(shlex.join(seg) for seg in later))
        else:
            emit('HAEJO_SESSION_RESUME after handling the failure above, continue from this app: haejo session '
                 + ' --then '.join(shlex.join(seg) for seg in [segment] + segments[index + 1:]))

    fd = None
    try:
        fd = stdin.fileno()
    except Exception:
        pass
    if sys.platform == 'win32' and fd is not None:
        _CHAIN_READER[fd] = _windows_reader(fd)
    result = 0
    try:
        for index, segment in enumerate(segments):
            if index:
                if not end_app():
                    emit('session_then: the previous app\'s window pin could not be released')
                    stop(index - 1, segments[index - 1], True)
                    return 1
                segment = segment + [flag for flag in inherited if flag not in segment]
                emit('HAEJO_SESSION_NEXT ' + segment[0] + ' (' + str(index + 1) + '/' + str(len(segments)) + ')')
            saved = []

            def watch(line, saved=saved):
                # A save failure comes after the app's task already ran.
                if isinstance(line, str) and line.startswith('session_save_failed'):
                    saved.append(line)
                emit(line)
            result = _run_one_session(segment, make_driver=kept_driver, run_flow=run_flow, stdin=stdin, emit=watch)
            if result != 0:
                if index + 1 < len(segments):
                    stop(index, segment, bool(saved))
                return result
        return result
    finally:
        _CHAIN_READER.pop(fd, None)
        for driver in shared.values():
            driver.close()


def _run_one_session(args, *, make_driver, run_flow, stdin, emit):
    args = list(args)
    # Windows has no signed helper: the session drives UI Automation in this
    # process, so --helper is refused there and required on macOS.
    windows = sys.platform == "win32"
    helper = [] if windows else ['--helper']
    usage = ('usage: session <app.exe | pid:N> [--guide] [--steps] [--timings] [--idle-timeout 1..600]' if windows
             else 'usage: session <bundle-id> --helper [--document /absolute/path] [--guide] [--steps] [--timings] [--idle-timeout 1..600] [--then <bundle-id> [--document /absolute/path]]')
    from .window_scope import take_window_arg, bind_window
    try:args,window_id=take_window_arg(args)
    except ValueError as error:emit(str(error));return 2
    if windows and window_id is not None:emit('window_scope_unavailable');return 2
    bound_steps = '--steps' in args
    if bound_steps:
        if args.count('--steps') != 1:
            emit('session_steps: use --steps once'); return 2
        args.remove('--steps')
    timeout = 90
    save_path = None
    document = None
    if '--document' in args:
        index = args.index('--document')
        if (windows or args.count('--document') != 1 or index+1 >= len(args)
                or not os.path.isabs(args[index+1]) or '\0' in args[index+1]):
            emit('session_document: --document needs one absolute TextEdit path');return 2
        document = args[index+1];del args[index:index+2]
    if '--save' in args:
        index = args.index('--save')
        if args.count('--save') != 1 or index+1 >= len(args) or args[index+1].startswith('-'):
            emit('session_save: --save needs one absolute new path');return 2
        save_path = args[index+1];del args[index:index+2]
        if not os.path.isabs(save_path) or os.path.lexists(save_path) or not os.path.isdir(os.path.dirname(save_path)):
            emit('session_save: use an absolute new path in an existing directory');return 2
    if '--idle-timeout' in args:
        index = args.index('--idle-timeout')
        if args.count('--idle-timeout') != 1 or index + 1 >= len(args):
            emit(usage)
            return 2
        value = args[index + 1]
        if not value.isdigit() or not 1 <= int(value) <= 600:
            emit('session_invalid_idle_timeout')
            return 2
        timeout = int(value)
        del args[index:index + 2]
    targets = [value for value in args if value not in ('--helper', '--timings', '--guide', '--reuse-guide')]
    if (len(targets) != 1 or targets[0].startswith('-') or args.count('--helper') != len(helper)
            or args.count('--timings') > 1 or args.count('--guide') > 1 or args.count('--reuse-guide') > 1):
        emit(usage)
        return 2
    target = targets[0]
    if document is not None and target != 'com.apple.TextEdit':
        emit('document_scope_unavailable: --document requires com.apple.TextEdit');return 2
    driver = None
    bound_window_id = None
    started = time.monotonic()
    timing = {}
    try:
        driver = make_driver(list(helper))
        if window_id is not None:
            problem=bind_window(driver,target,window_id)
            if problem is not None:emit(json.dumps(problem,ensure_ascii=False));return 1
            scope=getattr(driver,'_window_scope',None)
            bound_window_id=scope[1] if isinstance(scope,tuple) else None
        if document is not None:
            from .document_scope import DocumentScopedDriver, DocumentScopeUnavailable
            try:
                driver = DocumentScopedDriver(driver, target, document)
            except DocumentScopeUnavailable as exc:
                from .pin_diagnostic import format_pin_diagnostic
                diagnostic = format_pin_diagnostic(exc.pin_reason)
                if diagnostic is not None:emit(diagnostic)
                emit('document_scope_unavailable: ' + str(exc));return 1
        observation = driver.observe(target, 'tree_full')
        timing['observation_ready_seconds'] = time.monotonic() - started
        if observation.get('type') != 'observation':
            emit(json.dumps(observation, ensure_ascii=False))
            return 1
        continuation_pages = 0

        def show_observation():
            # The live cursor belongs to this connection; authors see only
            # whether there are more candidates, never a reusable native token.
            hidden = {'next_observation_cursor'}
            if '--timings' not in args:
                hidden.update(('observation_timing_ms', 'observation_metrics',
                               'window_listing_diagnostic', 'coordination_elapsed_ms'))
            visible = {key: value for key, value in observation.items() if key not in hidden}
            more = bool(observation.get('next_observation_cursor'))
            if more:
                visible['has_more_observation'] = True
            emit(json.dumps(visible, ensure_ascii=False, separators=(',', ':')))
            if more:
                lookup = (' If the exact name is known, send {"find_in_observation":"exact label"} instead.'
                          if 'observe.reveal' in getattr(driver, 'capabilities', ()) else '')
                emit('HAEJO_OBSERVATION_MORE send {"observe_next":true} to inspect omitted candidates on this session; no UI input is sent.' + lookup)
            if not more and window_id is None and document is None:
                # Waiting for the author's JSON can take a minute. Holding the
                # app meanwhile turned every other observe/capture on it into
                # a 10 s target_busy (2026-11-05/06). The replay observes again
                # on this connection, so nothing stale is acted on.
                release = getattr(driver, 'release_targets', None)
                if callable(release) and 'session.release_targets' in getattr(driver, 'capabilities', ()):
                    try:
                        release()
                    except Exception:
                        pass
            emit('HAEJO_SESSION_READY send one compact Flow JSON line, then newline; target=' + target)

        def additional_observation(label=None):
            nonlocal observation, continuation_pages
            from .flow_errors import FlowFieldError
            field = 'observe_next' if label is None else 'find_in_observation'
            if continuation_pages >= MAX_OBSERVATION_PAGES:
                raise FlowFieldError('observation_page_limit', field,
                                     'Eight additional observations were requested; narrow the window or task.')
            if label is not None and 'observe.reveal' not in getattr(driver, 'capabilities', ()):
                raise FlowFieldError('observation_lookup_unavailable', field,
                                     'This runtime cannot search omitted labels; use observe_next.')
            cursor = observation.pop('next_observation_cursor', None)
            if not isinstance(cursor, str) or not cursor:
                raise FlowFieldError('observation_continuation_unavailable', field,
                                     'No next observation is available on this session.')
            continuation_pages += 1
            try:
                options = {'continuation': cursor} if label is None else {'reveal': [label]}
                next_page = driver.observe(target, 'tree_full', **options)
            except Exception:
                next_page = None
            if (label is None and (not isinstance(next_page, dict) or next_page.get('type') != 'observation')):
                # A stale page used to end the whole session (continuation_stale,
                # AccessibilityInspector 2026-11-06). Look again from the top.
                try:
                    next_page = driver.observe(target, 'tree_full')
                except Exception:
                    next_page = None
                if isinstance(next_page, dict) and next_page.get('type') == 'observation':
                    emit('HAEJO_OBSERVATION_RESTARTED the previous page expired; this is a fresh first page.')
            if not isinstance(next_page, dict) or next_page.get('type') != 'observation':
                raise FlowFieldError('observation_continuation_failed', field,
                                     'The continuation expired or changed; start a fresh observation.')
            observation = next_page
            show_observation()
        try:
            # Avoid terminal canonical-line limits and echoing document text.
            # Restore this invocation's terminal flags even on cancellation.
            with flow_input_mode(stdin.fileno()):
                if '--guide' in args or '--reuse-guide' in args:
                    from .command_help import session_guide
                    emit(session_guide(target, reusable='--reuse-guide' in args,
                                       document=document, save=save_path is not None, steps=bound_steps))
                if window_id is not None:
                    chosen = bound_window_id if bound_window_id is not None else window_id
                    stored = (' --save stores the selector as the Flow\'s "window", so each replay picks the matching window again.'
                              if isinstance(window_id, dict) else
                              ' The live ID is not stored; for a reusable Flow start with --window-match url=... (or title=..., tab=..., newest).')
                    emit(f'HAEJO_WINDOW_SCOPE {chosen}: read/set_value/type_text and supported AXPress; in a web page also select_option, scroll, typed text and click with params {"route":"pointer"}. App menus, other keys and other pointer work use a separate app-wide session.' + stored)
                    from .window_scope import tab_note
                    note=tab_note(driver)
                    if note:emit(note)
                show_observation()
                timing['input_ready_seconds'] = time.monotonic() - started
                flow, template = read_session_flow(stdin.fileno(), timeout, emit,
                                                   prepare=lambda parsed: prepare_session_flow(parsed, target, window_id),
                                                   observe_next=additional_observation,
                                                   find_observation=additional_observation,
                                                   metrics=timing if '--timings' in args else None,
                                                   decode=lambda raw: decode_session_flow(raw, target, document, steps=bound_steps))
                timing['flow_received_seconds'] = time.monotonic() - started
        except (ValueError, TypeError, KeyError, TimeoutError, RecursionError) as exc:
            # A flow may contain personal text. Do not echo malformed input or
            # decoder excerpts; terminal framing/transport errors end the session.
            from .flow_errors import feedback
            record_failure('session_input_timeout' if isinstance(exc, TimeoutError) else 'session_invalid_flow', 'load')
            emit('session_invalid_flow: ' + feedback(exc))
            return 2
        # A session is one operation, not a daemon or a source of reusable
        # observation IDs. replay reobserves on this same authenticated channel.
        flags = [*helper, '--think', '0']
        if '--timings' in args:
            flags.append('--timings')
        observed_state = []
        result_options = {}
        if document is not None:
            from .document_readback import failure_readback, present_body_state, MARKER
            def observe_result(replayed):
                readback = failure_readback(driver, flow, replayed)
                if readback is not None:
                    observed_state.append(readback)
            # Unlike _on_result this callback retains no resume authority.
            result_options['_result_observer'] = observe_result
            def present_result(replayed):
                return present_body_state(observed_state[-1], emit) if observed_state else False
            result_options['_result_presenter'] = present_result
        def no_approver(description):
            return False
        no_approver.no_approver = True
        result = run_flow(flow, flags, _driver=driver, _confirm=no_approver,
                          **result_options)
        for readback in observed_state:
            emit(MARKER + json.dumps(readback, separators=(',', ':')))
            if save_path is None and len(flow.steps) == 1:
                from .task import note_visible_document_result
                note_visible_document_result(readback)
        timing['replay_done_seconds'] = time.monotonic() - started
        if result == 0 and save_path is None:
            from .task import note_session_success
            hint = note_session_success(flow)
            if hint:
                emit(hint)
        if result == 0 and save_path is not None:
            from .storage import write_private
            try:
                write_private(save_path, template, overwrite=False)
            except OSError:
                record_failure('session_save_failed', 'save')
                emit('session_save_failed: UI task completed; file not saved. Do not replay the task.');return 1
            emit('HAEJO_FLOW_SAVED ' + save_path)
            if document is not None:
                emit('HAEJO_FLOW_SCOPE ' + json.dumps({
                    'document':document, 'scope_stored_in_flow':False,
                    'replay_argv':['haejo','run',save_path,'--helper','--document',document],
                }, ensure_ascii=False))
        return result
    finally:
        if driver is not None:
            driver.close()
        if '--timings' in args:
            timing['session_done_seconds'] = time.monotonic() - started
            emit('HAEJO_SESSION_TIMINGS ' + json.dumps(timing, sort_keys=True))
