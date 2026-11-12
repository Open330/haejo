"""Which means delivered an input, and when to move to the next one.

Three levels, quietest first (docs/safari-capability-matrix.md):

  L1  an accessibility action or attribute write, the app behind
  L2  pointer/key events addressed to the app's window, the app behind
  L3  the same input with the app brought in front, given back afterwards
      (or the person's real pointer, as `hover` uses)

The signed helper names the route it used in its reply (`input_route`,
`route_level`); older replies name only the route, so the level is read from
that. A reply with no route is a plain accessibility action.
"""
import re

POINTER_ROUTE_CAPABILITY = 'click.route_pointer'
WEB_ROUTES_CAPABILITY = 'web.input_routes'

LEVELS = ('L1', 'L2', 'L3')

_L3_ROUTES = frozenset({'global_pointer', 'native_paste', 'native_unicode', 'foreground_keys',
                        'foreground_popup_menu', 'foreground_element_click'})
_L2_ROUTES = frozenset({'window_keys', 'window_key', 'window_submit_key', 'window_bound_submit_key',
                        'window_bound_mouse', 'window_bound_element_click', 'window_bound_double_click',
                        'window_bound_drag', 'window_input', 'window_prepare', 'window_resize_drag',
                        'combo_popup_bound_click'})

# What a reply may say about its route; anything else stays out of the record.
_FIELDS = ('focus_route', 'fallback_from', 'routed_from', 'foreground_taken', 'front_restored',
           'previous_front', 'pointer_moved', 'pointer_restored', 'pressed_again')


def level_of(route):
    """The level of a named route; a route this runtime does not know is L1
    only when it says so itself (`ax_*`), otherwise unknown (None)."""
    if route is None or route == '':
        return 'L1'
    if not isinstance(route, str):
        return None
    if route in _L3_ROUTES:
        return 'L3'
    if route in _L2_ROUTES:
        return 'L2'
    if route.startswith(('ax_', 'uia_')) or route in ('web_popup_menu', 'row_selection', 'safari_address_confirm'):
        return 'L1'
    return None


def route_of(response):
    """The route a driver reply reports, as a small record for the run log.

    None for a reply that dispatched nothing (a refusal before any input)."""
    if not isinstance(response, dict):
        return None
    dispatched = response.get('type') == 'acted' or (
        response.get('type') == 'error' and response.get('effect', 'unknown') != 'not_started')
    if not dispatched:
        return None
    name = response.get('input_route')
    if name is not None and not isinstance(name, str):
        name = None
    level = response.get('route_level')
    if level not in LEVELS:
        level = level_of(name)
    record = {'input_route': name or 'ax_action', 'route_level': level}
    for field in _FIELDS:
        value = response.get(field)
        if isinstance(value, (bool, str)) and value != '':
            record[field] = value
    return record


def under_web_area(tree, element_index):
    """True when the observed element sits inside a WebArea (page content)."""
    if not isinstance(tree, str) or type(element_index) is not int:
        return False
    lines = tree.splitlines()
    at = next((n for n, line in enumerate(lines) if re.match(rf'\s*{element_index}\s', line)), None)
    if at is None:
        return False
    depth = len(lines[at]) - len(lines[at].lstrip())
    for line in reversed(lines[:at]):
        indent = len(line) - len(line.lstrip())
        if indent >= depth:
            continue
        depth = indent
        parts = line.split()
        if len(parts) >= 2 and parts[0].isdigit() and parts[1] == 'WebArea':
            return True
    return False


def pointer_fallback_applies(step, action, response, tree, capabilities):
    """Should a click whose result never showed be sent once more as pointer events?

    Only where the accessibility press is known to be answered with success and
    nothing else: page content, whose controls may listen for pointer events
    the press does not produce. The step must be a plain reversible click with
    an explicit result check (that check is what said the press did nothing),
    and the first reply must be the plain press — a click that already went as
    pointer events is never repeated."""
    safety = getattr(step, 'safety', None)
    return (getattr(step, 'action', None) == 'click'
            and isinstance(action, dict) and 'route' not in action
            and type(action.get('element_index')) is int
            and getattr(step, 'postcondition', None) is not None
            and getattr(step, 'selector', None) is not None
            and getattr(step, 'binding', None) is None
            and safety is not None and set(safety.effects) <= {'read', 'write_ephemeral'}
            and POINTER_ROUTE_CAPABILITY in (capabilities or ())
            and isinstance(response, dict) and response.get('type') == 'acted'
            and not response.get('input_route') and not response.get('unverified')
            and under_web_area(tree, action['element_index']))


def describe(record):
    """One line for a person: which route, and what happened to the front."""
    if not isinstance(record, dict):
        return ''
    text = f"{record.get('input_route')} ({record.get('route_level') or 'level unknown'})"
    if record.get('fallback_from'):
        text += f", after {record['fallback_from']}"
    if record.get('foreground_taken'):
        back = record.get('previous_front') or 'the previous app'
        text += (f"; took the front and returned it to {back}" if record.get('front_restored')
                 else '; took the front and could not return it')
    return text
