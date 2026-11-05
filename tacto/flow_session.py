"""One signed connection: observe, accept one bounded flow, replay, exit."""
import json
import os
import select
import sys
import time
from contextlib import contextmanager

from .access_log import record_failure
from .flow import Flow, every_step


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


def read_session_flow(fd, timeout, emit, *, prepare=None, observe_next=None, find_observation=None):
    """Repair interactive schema errors before dispatch on the same connection."""
    deadline = time.monotonic() + timeout
    reader = _windows_reader(fd) if sys.platform == 'win32' else None
    while True:
        # Framing, EOF and budget errors are terminal; only a complete JSON line
        # rejected by Flow parsing can be corrected without starting over.
        raw = read_flow_line(fd, max(0, deadline - time.monotonic()), reader=reader)
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
            flow = Flow.from_json(raw, strict_checks=True)
            return prepare(flow) if prepare is not None else flow
        except (ValueError, TypeError, KeyError, RecursionError) as exc:
            if not os.isatty(fd):
                raise
            from .flow_errors import feedback
            record_failure('session_invalid_flow', 'load')
            emit('session_invalid_flow: ' + feedback(exc))
            emit('TACTO_SESSION_READY correct the JSON on this same session; no UI input was sent. The original input deadline still applies.')


def prepare_session_flow(flow, target):
    from .flow_errors import FlowFieldError
    if flow.target != target:
        raise FlowFieldError('session_target_mismatch', 'target', 'Match the target of this session.')
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
    args = list(args)
    # Windows has no signed helper: the session drives UI Automation in this
    # process, so --helper is refused there and required on macOS.
    windows = sys.platform == "win32"
    helper = [] if windows else ['--helper']
    usage = ('usage: session <app.exe | pid:N> [--guide] [--timings] [--idle-timeout 1..600]' if windows
             else 'usage: session <bundle-id> --helper [--document /absolute/path] [--guide] [--timings] [--idle-timeout 1..600]')
    from .window_scope import take_window_arg, bind_window
    try:args,window_id=take_window_arg(args)
    except ValueError as error:emit(str(error));return 2
    if windows and window_id is not None:emit('window_scope_unavailable');return 2
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
    started = time.monotonic()
    timing = {}
    try:
        driver = make_driver(list(helper))
        if window_id is not None:
            problem=bind_window(driver,target,window_id)
            if problem is not None:emit(json.dumps(problem));return 1
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
            visible = {key: value for key, value in observation.items()
                       if key != 'next_observation_cursor'}
            more = bool(observation.get('next_observation_cursor'))
            if more:
                visible['has_more_observation'] = True
            emit(json.dumps(visible, ensure_ascii=False))
            if more:
                lookup = (' If the exact name is known, send {"find_in_observation":"exact label"} instead.'
                          if 'observe.reveal' in getattr(driver, 'capabilities', ()) else '')
                emit('TACTO_OBSERVATION_MORE send {"observe_next":true} to inspect omitted candidates on this session; no UI input is sent.' + lookup)
            emit('TACTO_SESSION_READY send one compact Flow JSON line, then newline; target=' + target)

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
                    emit(session_guide(target, reusable='--reuse-guide' in args, document=document))
                if window_id is not None:
                    emit(f'TACTO_WINDOW_SCOPE {window_id}: read/set_value/type_text and supported AXPress only; menus/keys/pointer require a separate app-wide session. Do not save the live window ID in the Flow.')
                show_observation()
                timing['input_ready_seconds'] = time.monotonic() - started
                flow, template = read_session_flow(stdin.fileno(), timeout, emit,
                                                   prepare=lambda parsed: prepare_session_flow(parsed, target),
                                                   observe_next=additional_observation,
                                                   find_observation=additional_observation)
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
            from .document_readback import failure_readback, MARKER
            def observe_result(replayed):
                readback = failure_readback(driver, flow, replayed)
                if readback is not None:
                    observed_state.append(readback)
            # Unlike _on_result this callback retains no resume authority.
            result_options['_result_observer'] = observe_result
        result = run_flow(flow, flags, _driver=driver, _confirm=lambda description: False,
                          **result_options)
        for readback in observed_state:
            emit(MARKER + json.dumps(readback, separators=(',', ':')))
        timing['replay_done_seconds'] = time.monotonic() - started
        if result == 0 and save_path is not None:
            from .storage import write_private
            try:
                write_private(save_path, template, overwrite=False)
            except OSError:
                record_failure('session_save_failed', 'save')
                emit('session_save_failed: UI task completed; file not saved. Do not replay the task.');return 1
            emit('TACTO_FLOW_SAVED ' + save_path)
            if document is not None:
                emit('TACTO_FLOW_SCOPE ' + json.dumps({
                    'document':document, 'scope_stored_in_flow':False,
                    'replay_argv':['tacto','run',save_path,'--helper','--document',document],
                }, ensure_ascii=False))
        return result
    finally:
        if driver is not None:
            driver.close()
        if '--timings' in args:
            timing['session_done_seconds'] = time.monotonic() - started
            emit('TACTO_SESSION_TIMINGS ' + json.dumps(timing, sort_keys=True))
