"""Host-selected window for a session or replay.

A live window ID (`--window-id`) is never persisted inside a Flow: a popup
opened per run gets a new ID every time. A *selector* (`--window-match`, or a
Flow's `window` field) is persisted instead and resolved to the one live
window it names when the run starts.

`tab=` names one tab of a browser window by its title (or, for the tab that is
showing, its address). The window is chosen as usual, the tab is selected in
it, and the pin then covers the page that tab shows.
"""
import time
from urllib.parse import urlsplit

SELECTOR_KEYS = ('url', 'title', 'tab', 'route', 'newest')
TAB_ROUTES = ('ax_press', 'window_pointer', 'front_pointer')
TAB_SETTLE_POLLS = 8
MATCH_WAIT_SECONDS = 10.0
MATCH_POLL_SECONDS = 0.5
# Listing states that mean "not available now", not "not there". A Flow that
# starts with wait_until keeps waiting through them (as the step itself would).
PAUSE_REASONS = frozenset(('screen_locked', 'display_asleep', 'session_not_on_console'))
PAUSE_POLL_SECONDS = 10.0
MAX_PAUSE_SECONDS = 6 * 3600
OTHER_SPACE_PAUSE_SECONDS = 30 * 60


def selector_problem(value):
    """None when `value` is a usable window selector, else a short reason."""
    if not isinstance(value, dict) or not value:
        return 'window selector must be a non-empty object'
    if set(value) - set(SELECTOR_KEYS):
        return 'window selector keys: url, title, tab, route, newest'
    for key in ('url', 'title', 'tab'):
        if key in value and (not isinstance(value[key], str) or not value[key].strip()
                             or len(value[key]) > 512 or '{{' in value[key]):
            return f'window.{key} must be a non-empty literal substring'
    if 'url' in value:
        try:
            host = _url_parts(value['url'])[1]   # also validates the port
        except ValueError:
            host = ''
        if not host or '.' not in host and host != 'localhost':
            return 'window.url must name a host, e.g. player.example.com or https://player.example.com/play'
    if 'route' in value and ('tab' not in value or value['route'] not in TAB_ROUTES):
        return 'window.route goes with tab and is one of ' + ', '.join(TAB_ROUTES)
    if 'newest' in value and value['newest'] is not True:
        return 'window.newest must be true when given'
    return None


def parse_match(specs):
    """`url=host/path`, `title=text`, `tab=text`, `route=name`, `newest` -> selector dict."""
    selector = {}
    for spec in specs:
        if spec == 'newest':
            key, text = 'newest', True
        elif '=' in spec and spec.split('=', 1)[0] in ('url', 'title', 'tab', 'route'):
            key, text = spec.split('=', 1)
        else:
            raise ValueError('--window-match takes url=SUBSTRING, title=SUBSTRING, tab=SUBSTRING or newest')
        if key in selector:
            raise ValueError(f'--window-match {key} given twice')
        selector[key] = text
    problem = selector_problem(selector)
    if problem:
        raise ValueError('--window-match: ' + problem)
    return selector


def take_window_arg(args):
    """Remove `--window-id N` or `--window-match SPEC...` from args.

    Returns (args, value) where value is an int window ID, a selector dict, or
    None.
    """
    args = list(args)
    has_id, has_match = '--window-id' in args, '--window-match' in args
    if has_id and has_match:
        raise ValueError('use either --window-id or --window-match')
    if has_match:
        if '--document' in args:
            raise ValueError('--window-match cannot be combined with --document')
        specs = []
        while '--window-match' in args:
            at = args.index('--window-match')
            if at + 1 >= len(args) or args[at + 1].startswith('-'):
                raise ValueError('--window-match takes url=SUBSTRING, title=SUBSTRING, tab=SUBSTRING or newest')
            specs.append(args[at + 1])
            del args[at:at + 2]
        return args, parse_match(specs)
    if not has_id:
        return args, None
    at = args.index('--window-id')
    if (args.count('--window-id') != 1 or at + 1 >= len(args) or not args[at + 1].isascii()
            or not args[at + 1].isdigit() or not 0 < int(args[at + 1]) <= 0xffffffff
            or '--document' in args):
        raise ValueError('--window-id needs one current positive window ID; choose it from `haejo windows <bundle-id> --helper`, or use --window-match url=... to choose it by page')
    value = int(args[at + 1])
    del args[at:at + 2]
    return args, value


DEFAULT_PORTS = {'http': 80, 'https': 443}


def _url_parts(text):
    """(scheme or None, host, port or None, path) for `https://host:port/path`,
    `host/path` or `host`. Raises ValueError for a malformed port."""
    text = text.strip()
    parts = urlsplit(text if '://' in text else '//' + text)
    return (parts.scheme.lower() or None), (parts.hostname or '').lower(), parts.port, parts.path


def url_matches(pattern, url):
    """Host matches on a label boundary (`example.com` covers
    `player.example.com`, not `badexample.com` or a path containing it);
    scheme, when given, must be equal; path is a case-sensitive prefix."""
    if not isinstance(url, str):
        return False
    want_scheme, want_host, want_port, want_path = _url_parts(pattern)
    have = urlsplit(url)
    host = (have.hostname or '').lower()
    if not want_host or not (host == want_host or host.endswith('.' + want_host)):
        return False
    scheme = have.scheme.lower()
    if want_scheme and scheme != want_scheme:
        return False
    try:
        port = have.port or DEFAULT_PORTS.get(scheme)
    except ValueError:
        return False
    if want_port is not None and port != want_port:
        return False
    return not want_path or want_path == '/' or have.path.startswith(want_path)


def _matches(row, selector):
    if 'url' in selector and not url_matches(selector['url'], row.get('url')):
        return False
    if 'title' in selector:
        have = row.get('title')
        if not isinstance(have, str) or selector['title'].casefold() not in have.casefold():
            return False
    return True


def _candidate(row, tab=None):
    found = {k: row[k] for k in ('window_id', 'title', 'url') if k in row}
    if tab is not None:
        found['tab'] = {k: tab[k] for k in ('index', 'title', 'selected', 'url') if k in tab}
    elif isinstance(row.get('tabs'), list) and len(row['tabs']) > 1:
        found['tabs'] = [t.get('title') for t in row['tabs'] if isinstance(t, dict)][:32]
    return found


def tab_matches(tab, text):
    """`text` is part of the tab's title, or of its address when the listing
    knows it (the tab that is showing). Case-insensitive."""
    want = text.casefold()
    return any(isinstance(tab.get(key), str) and want in tab[key].casefold() for key in ('title', 'url'))


def _tabs(row):
    return [t for t in row.get('tabs') or () if isinstance(t, dict) and type(t.get('index')) is int
            and isinstance(t.get('title'), str)]


def _pairs(rows, selector):
    """(window row, tab row or None) for every match."""
    rows = [r for r in rows if _matches(r, selector)]
    if 'tab' not in selector:
        return [(r, None) for r in rows]
    return [(r, t) for r in rows for t in _tabs(r) if tab_matches(t, selector['tab'])]


def _newest(pairs):
    window_id = max(row['window_id'] for row, _ in pairs)
    tabs = [tab for row, tab in pairs if row['window_id'] == window_id]
    if tabs[0] is None:
        return window_id, None
    showing = [tab for tab in tabs if tab.get('selected') is True]
    return window_id, (showing or tabs)[-1]


def resolve_window(driver, target, selector, *, wait=None, sleep=time.sleep, clock=time.monotonic,
                   patient=False):
    """Return (window_id, None) or (None, error reply)."""
    window_id, _, problem = resolve_target(driver, target, selector, wait=wait, sleep=sleep, clock=clock,
                                           patient=patient)
    return window_id, problem


def resolve_target(driver, target, selector, *, wait=None, sleep=time.sleep, clock=time.monotonic,
                   patient=False):
    """Return (window_id, tab row or None, None) or (None, None, error reply).

    Waits briefly when nothing matches yet: the popup a previous step opened
    can take a moment to appear. `patient` also waits (up to
    MAX_PAUSE_SECONDS) while the screen is locked/asleep or the matching
    window is on another Space; that time does not use up `wait`.
    """
    paused = 0.0
    pause_started = pause_limit = None
    listing = getattr(driver, 'windows', None)
    if listing is None or 'observe.window_list' not in getattr(driver, 'capabilities', ()):
        return None, None, {'type': 'error', 'error': 'window_list_unavailable', 'effect': 'not_started'}
    deadline = clock() + (MATCH_WAIT_SECONDS if wait is None else wait)
    while True:
        polled = clock()
        reply = listing(target)
        if not isinstance(reply, dict):
            return None, None, {'type': 'error', 'error': 'window_list_unavailable', 'effect': 'not_started'}
        if reply.get('type') != 'windows' and not (patient and reply.get('reason') in PAUSE_REASONS):
            return None, None, reply
        # Settle the pause that ended with this poll (measured, so host sleep
        # or oversleep counts) before anything is accepted.
        if pause_started is not None:
            spent = polled - pause_started
            paused += spent
            deadline += spent
            pause_started = None
            if paused >= pause_limit:
                return None, None, {'type': 'error', 'error': 'window_match_paused_too_long', 'effect': 'not_started',
                              'selector': selector, 'paused_seconds': round(paused, 3)}
        rows = [r for r in reply.get('windows', []) if isinstance(r, dict) and type(r.get('window_id')) is int]
        found = _pairs(rows, selector)
        if found and (len(found) == 1 or selector.get('newest')):
            return (*_newest(found), None)
        if found:
            return None, None, {'type': 'error', 'error': 'window_match_ambiguous', 'effect': 'not_started',
                          'selector': selector, 'candidates': [_candidate(r, t) for r, t in found][:16],
                          'hint': 'add url=/title=/tab= text that only one window or tab has, or newest to take the most recently opened'}
        locked = reply.get('reason') in PAUSE_REASONS
        # An unlisted window has no title or URL, so it may not be the one
        # wanted: wait for another Space for a shorter time than for a lock.
        # Only when the app lists no window here at all: one unrelated window
        # on another Space must not hold a run for half an hour.
        elsewhere = not rows and any(isinstance(r, dict) and r.get('reason') == 'not_on_active_space'
                                     for r in reply.get('unlisted', ()))
        limit = MAX_PAUSE_SECONDS if locked else OTHER_SPACE_PAUSE_SECONDS if elsewhere else 0
        if patient and limit and paused < limit:
            pause_started, pause_limit = polled, limit
            sleep(PAUSE_POLL_SECONDS)
            continue
        if reply.get('type') != 'windows':
            return None, None, reply
        if clock() >= deadline:
            error = {'type': 'error', 'error': 'window_match_none', 'effect': 'not_started',
                     'selector': selector, 'listed': [_candidate(r) for r in rows][:16]}
            for key in ('reason', 'unlisted', 'screen'):
                if key in reply:
                    error[key] = reply[key]
            return None, None, error
        sleep(MATCH_POLL_SECONDS)


def bind_window(driver, target, window, *, patient=False):
    """Pin `driver` to one window. `window` is an ID or a selector dict.

    Returns None on success, else the error reply to print.
    """
    tab = None
    if isinstance(window, dict):
        window_id, tab, problem = resolve_target(driver, target, window, patient=patient)
        if problem is not None:
            return problem
    else:
        window_id = window
    bind = getattr(driver, 'scope_window', None)
    if bind is None:
        return {'type': 'error', 'error': 'window_scope_unavailable', 'effect': 'not_started'}
    result = bind(target, window_id)
    if result.get('type') != 'window_scope':
        return result
    if tab is not None:
        problem = _select_tab(driver, target, window['tab'], tab, window.get('route'))
        if problem is not None:
            return problem
    # What chose this pin: a later Flow may reuse it only for the same selector.
    try:
        driver._window_selector = (target, dict(window)) if isinstance(window, dict) else None
    except AttributeError:
        pass
    return None


def _select_tab(driver, target, text, tab, route=None):
    """Show `tab` in the pinned window and check the page it shows.

    The route is the helper's: AXPress on the tab button, then a click bound
    to the window, then the real pointer with the browser in front (the app
    that was in front is restored). `route` names the one route to use.
    """
    select = getattr(driver, 'select_tab', None)
    if select is None or 'session.tab_select' not in getattr(driver, 'capabilities', ()):
        return {'type': 'error', 'error': 'tab_select_unavailable', 'effect': 'not_started'}
    for _ in range(3):
        reply = select(target, tab['index'], tab['title'], route=route)
        if not isinstance(reply, dict):
            return {'type': 'error', 'error': 'tab_select_unavailable', 'effect': 'not_started'}
        if reply.get('error') != 'tab_changed':
            break
        # A tab that finished loading got its page title, or tabs moved: take
        # the one the same text names in the list the helper just read.
        again = [t for t in _tabs(reply) if tab_matches(t, text)]
        if len(again) != 1:
            return reply
        tab = again[0]
    if reply.get('type') != 'tab_selected':
        return reply
    # A page still loading shows "Untitled" and no address for a moment.
    for _ in range(TAB_SETTLE_POLLS):
        if tab_matches(reply, text):
            break
        time.sleep(MATCH_POLL_SECONDS)
        fresh = select(target, reply['index'], None, route=route)
        if not isinstance(fresh, dict) or fresh.get('type') != 'tab_selected':
            break
        reply = dict(fresh, **{k: reply[k] for k in ('route', 'attempts', 'front_taken', 'front_restored')
                               if k in reply})
    chosen = {k: reply[k] for k in ('window_id', 'index', 'title', 'url', 'route', 'attempts',
                                     'front_taken', 'front_restored') if k in reply}
    if not tab_matches(reply, text):
        return {'type': 'error', 'error': 'tab_select_unverified', 'effect': 'unknown', 'selected': chosen,
                'hint': 'the selected tab shows another page; list tabs with `haejo windows` and choose again'}
    try:
        driver._tab_selection = chosen
    except AttributeError:
        pass
    return None


def tab_note(driver):
    """One line that says which tab was selected and by which route."""
    chosen = getattr(driver, '_tab_selection', None)
    if not isinstance(chosen, dict):
        return None
    import json
    return 'HAEJO_TAB_SELECTED ' + json.dumps(chosen, ensure_ascii=False)


def pin_for_flow(driver, flow, *, patient=False):
    """Pin `driver` to the window `flow.window` names, or keep a pin that the
    same selector made. None on success, else the refusal."""
    if not flow.window:
        return None
    pinned = getattr(driver, '_window_scope', None)
    if pinned is not None:
        if getattr(driver, '_window_selector', None) == (flow.target, flow.window):
            return None
        return {'type': 'error', 'error': 'window_scope_conflict', 'effect': 'not_started',
                'detail': 'this connection is pinned to a window chosen for a different selector; start a new command for this Flow'}
    return bind_window(driver, flow.target, flow.window, patient=patient)
