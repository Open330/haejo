"""Host-selected window for a session or replay.

A live window ID (`--window-id`) is never persisted inside a Flow: a popup
opened per run gets a new ID every time. A *selector* (`--window-match`, or a
Flow's `window` field) is persisted instead and resolved to the one live
window it names when the run starts.
"""
import time

SELECTOR_KEYS = ('url', 'title', 'newest')
MATCH_WAIT_SECONDS = 10.0
MATCH_POLL_SECONDS = 0.5


def selector_problem(value):
    """None when `value` is a usable window selector, else a short reason."""
    if not isinstance(value, dict) or not value:
        return 'window selector must be a non-empty object'
    if set(value) - set(SELECTOR_KEYS):
        return 'window selector keys: url, title, newest'
    for key in ('url', 'title'):
        if key in value and (not isinstance(value[key], str) or not value[key].strip()
                             or len(value[key]) > 512 or '{{' in value[key]):
            return f'window.{key} must be a non-empty literal substring'
    if 'newest' in value and value['newest'] is not True:
        return 'window.newest must be true when given'
    return None


def parse_match(specs):
    """`url=host/path`, `title=text`, `newest` -> selector dict."""
    selector = {}
    for spec in specs:
        if spec == 'newest':
            key, text = 'newest', True
        elif '=' in spec and spec.split('=', 1)[0] in ('url', 'title'):
            key, text = spec.split('=', 1)
        else:
            raise ValueError('--window-match takes url=SUBSTRING, title=SUBSTRING or newest')
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
                raise ValueError('--window-match takes url=SUBSTRING, title=SUBSTRING or newest')
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


def _matches(row, selector):
    for key in ('url', 'title'):
        if key in selector:
            have = row.get(key)
            if not isinstance(have, str) or selector[key].casefold() not in have.casefold():
                return False
    return True


def _candidate(row):
    return {k: row[k] for k in ('window_id', 'title', 'url') if k in row}


def resolve_window(driver, target, selector, *, wait=MATCH_WAIT_SECONDS, sleep=time.sleep, clock=time.monotonic):
    """Return (window_id, None) or (None, error reply).

    Waits briefly when nothing matches yet: the popup a previous step opened
    can take a moment to appear.
    """
    listing = getattr(driver, 'windows', None)
    if listing is None or 'observe.window_list' not in getattr(driver, 'capabilities', ()):
        return None, {'type': 'error', 'error': 'window_list_unavailable', 'effect': 'not_started'}
    deadline = clock() + wait
    while True:
        reply = listing(target)
        if not isinstance(reply, dict) or reply.get('type') != 'windows':
            return None, reply if isinstance(reply, dict) else {
                'type': 'error', 'error': 'window_list_unavailable', 'effect': 'not_started'}
        rows = [r for r in reply.get('windows', []) if isinstance(r, dict) and type(r.get('window_id')) is int]
        found = [r for r in rows if _matches(r, selector)]
        if found and (len(found) == 1 or selector.get('newest')):
            return max(r['window_id'] for r in found), None
        if found:
            return None, {'type': 'error', 'error': 'window_match_ambiguous', 'effect': 'not_started',
                          'selector': selector, 'candidates': [_candidate(r) for r in found][:16],
                          'hint': 'add url=/title= text that only one window has, or newest to take the most recently opened'}
        if clock() >= deadline:
            error = {'type': 'error', 'error': 'window_match_none', 'effect': 'not_started',
                     'selector': selector, 'listed': [_candidate(r) for r in rows][:16]}
            for key in ('reason', 'unlisted', 'screen'):
                if key in reply:
                    error[key] = reply[key]
            return None, error
        sleep(MATCH_POLL_SECONDS)


def bind_window(driver, target, window):
    """Pin `driver` to one window. `window` is an ID or a selector dict.

    Returns None on success, else the error reply to print.
    """
    if isinstance(window, dict):
        window_id, problem = resolve_window(driver, target, window)
        if problem is not None:
            return problem
    else:
        window_id = window
    bind = getattr(driver, 'scope_window', None)
    if bind is None:
        return {'type': 'error', 'error': 'window_scope_unavailable', 'effect': 'not_started'}
    result = bind(target, window_id)
    return None if result.get('type') == 'window_scope' else result
