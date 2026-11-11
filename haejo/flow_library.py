"""Saved-flow library: list, inspect and maintain the recipes in FlowStore.

`haejo flows` is what the app's Flow page calls (with `--json`) and what a
person or agent uses from a shell. Edits change only the fields a person can
change without re-authoring — parameter defaults, the request sentences
(`intents`) and the name. Steps, selectors and safety contracts stay as the
author recorded them; a step change is a re-authoring (`haejo compile`).

Every edit works on the stored JSON text, not a re-serialised Flow, so fields
this runtime does not model survive, and the edited text must still parse as a
Flow before it replaces the file.
"""
from __future__ import annotations

import json
import os
import re
import sys
from datetime import datetime, timezone

from .flow import Flow, every_step
from .storage import write_private
from .store import FlowStore

# Windows has no signed helper and refuses --helper; never suggest it there.
_HELPER = '' if sys.platform == 'win32' else ' --helper'

# The policy levels at which a run stops for the person (or `--yes`).
ASKS = frozenset({'confirm', 'handoff', 'blocked'})
MAX_INTENTS = 20
MAX_TEXT = 500
MAX_FILE = 4 * 1024 * 1024


class LibraryError(Exception):
    def __init__(self, code: str, detail: str):
        super().__init__(code)
        self.code, self.detail = code, detail


def valid_name(name) -> bool:
    """FlowStore keeps only alphanumerics (any script), _ and - in a file
    name; a name that sanitising would change would address another file."""
    return (isinstance(name, str) and 1 <= len(name) <= 80
            and all(c.isalnum() or c in '_-' for c in name))


def _builtin_names() -> set[str]:
    try:
        from .library import builders
        return set(builders())
    except Exception:
        return set()


def _user_path(store: FlowStore, name: str) -> str:
    if not valid_name(name):
        raise LibraryError('invalid_name', 'use letters, digits, _ or - (at most 80)')
    return os.path.join(store.path, name + '.json')


def _read_text(path: str) -> str:
    with open(path, encoding='utf-8') as source:
        text = source.read(MAX_FILE + 1)
    if len(text) > MAX_FILE:
        raise LibraryError('flow_too_large', 'flow files are limited to 4 MiB')
    return text


def _locate(store: FlowStore, name: str) -> tuple[str, str]:
    """(path, source) for a listed flow; user files win over bundled ones."""
    path = _user_path(store, name)
    if os.path.lexists(path):
        return path, 'user'
    if store.builtin_path:
        bundled = os.path.join(store.builtin_path, name + '.json')
        if os.path.isfile(bundled):
            return bundled, 'builtin'
    raise LibraryError('flow_not_found', f'no saved flow named {name}')


def _label(step) -> str:
    if step.intent_text:
        return step.intent_text[:MAX_TEXT]
    sel = step.selector
    if sel is not None:
        for key in ('title', 'desc', 'identifier', 'value', 'placeholder'):
            value = getattr(sel, key, None)
            if isinstance(value, list):
                value = ' / '.join(str(v) for v in value)
            if value:
                return str(value)[:MAX_TEXT]
        if getattr(sel, 'role', None):
            return str(sel.role)
    params = step.params or {}
    if step.action == 'menu' and isinstance(params.get('path'), list):
        return ' > '.join(str(p) for p in params['path'])[:MAX_TEXT]
    for key in ('key', 'text', 'value', 'url', 'name'):
        if isinstance(params.get(key), (str, int, float)) and str(params[key]):
            return str(params[key])[:MAX_TEXT]
    return ''


def _steps(flow: Flow) -> list[dict]:
    from .contract import policy
    out = []
    for index, step in enumerate(every_step(flow.steps), 1):
        effects, level, reason = [], None, ''
        if step.safety is not None:
            effects = list(step.safety.effects)
            decision = policy(step.safety)
            level, reason = decision.risk, decision.reason
        out.append({'index': index, 'action': step.action, 'label': _label(step),
                    'effects': effects, 'policy': level, 'policy_reason': reason[:MAX_TEXT],
                    'consequential': level in ASKS,
                    'reads_value': bool(step.captures)})
    return out


def _entry(store: FlowStore, name: str, *, steps: bool = False, builtins=None) -> dict:
    path, source = _locate(store, name)
    entry = {'name': name, 'source': source, 'path': path, 'editable': source == 'user',
             'shadowed_by_builtin': name in (_builtin_names() if builtins is None else builtins)}
    try:
        info = os.stat(path)
        entry['modified'] = datetime.fromtimestamp(info.st_mtime, timezone.utc).isoformat()
    except OSError:
        entry['modified'] = None
    try:
        text = _read_text(path)
        raw = json.loads(text)
        if isinstance(raw, dict) and raw.get('schema') == 1:
            raise LibraryError('legacy_schema', 'schema 1 flow; migrate it before use')
        flow = Flow.from_json(text)
    except LibraryError as exc:
        entry.update(ok=False, error=exc.code, detail=exc.detail)
        return entry
    except (OSError, ValueError, TypeError, KeyError, AttributeError) as exc:
        entry.update(ok=False, error='corrupt_flow', detail=str(exc)[:MAX_TEXT])
        return entry
    walked = _steps(flow)
    entry.update(ok=True, target=flow.target, schema=flow.schema,
                 params={k: v for k, v in flow.params.items()},
                 literal_params=sorted(flow.literal_params),
                 runtime_values=sorted(flow.runtime_names()),
                 intents=list(flow.intents),
                 step_count=len(walked),
                 consequential_steps=sum(s['consequential'] for s in walked),
                 decisions=sum(s['action'] == 'decide' for s in walked))
    if steps:
        entry['steps'] = walked
    return entry


def list_flows(store: FlowStore | None = None) -> dict:
    store = store or FlowStore()
    builtins = _builtin_names()
    flows = []
    for name in store.list():
        if not valid_name(name):
            continue
        try:
            flows.append(_entry(store, name, builtins=builtins))
        except LibraryError:
            continue
    return {'ok': True, 'store': store.path, 'flows': flows}


def detail(name: str, store: FlowStore | None = None) -> dict:
    return {'ok': True, 'flow': _entry(store or FlowStore(), name, steps=True)}


def _editable(store: FlowStore, name: str) -> tuple[str, dict]:
    path, source = _locate(store, name)
    if source != 'user':
        raise LibraryError('flow_read_only', 'bundled flows cannot be changed; import a copy under a new name')
    if os.path.islink(path):
        raise LibraryError('flow_read_only', 'the saved flow is a symbolic link; edit its target directly')
    raw = json.loads(_read_text(path))
    if not isinstance(raw, dict) or raw.get('schema') == 1:
        raise LibraryError('legacy_schema', 'schema 1 flow; migrate it before editing')
    return path, raw


def _commit(path: str, raw: dict, *, overwrite: bool = True) -> Flow:
    text = json.dumps(raw, ensure_ascii=False, indent=2) + '\n'
    try:
        flow = Flow.from_json(text)
    except (ValueError, TypeError, KeyError, AttributeError) as exc:
        raise LibraryError('invalid_flow', str(exc)[:MAX_TEXT]) from None
    try:
        write_private(path, text, overwrite=overwrite)
    except FileExistsError:
        raise LibraryError('flow_exists', f'{os.path.basename(path)[:-5]} already exists') from None
    return flow


def _coerce(old, new: str):
    """Keep a default's type when the new text reads as that type."""
    if new == '':
        return None                       # required at run time
    if isinstance(old, bool):
        if new.lower() in ('true', 'false'):
            return new.lower() == 'true'
        raise LibraryError('invalid_parameter_value', 'use true or false')
    if isinstance(old, int):
        try:
            return int(new)
        except ValueError:
            pass
    if isinstance(old, float):
        try:
            return float(new)
        except ValueError:
            pass
    return new


def set_fields(name: str, *, params: dict | None = None, intents: list | None = None,
               store: FlowStore | None = None) -> dict:
    store = store or FlowStore()
    path, raw = _editable(store, name)
    if params:
        current = raw.get('params') or {}
        unknown = sorted(set(params) - set(current))
        if unknown:
            raise LibraryError('unknown_parameter',
                               f"{', '.join(unknown)} is not a parameter of {name}; parameters: {', '.join(sorted(current)) or 'none'}")
        for key, value in params.items():
            if not isinstance(value, str) or len(value) > MAX_TEXT:
                raise LibraryError('invalid_parameter_value', f'{key}: text of at most {MAX_TEXT} characters')
            current[key] = _coerce(current[key], value)
        raw['params'] = current
    if intents is not None:
        cleaned = [s.strip() for s in intents if isinstance(s, str) and s.strip()]
        if len(cleaned) > MAX_INTENTS or any(len(s) > MAX_TEXT for s in cleaned):
            raise LibraryError('invalid_intents', f'at most {MAX_INTENTS} sentences of {MAX_TEXT} characters')
        names = set(raw.get('params') or {})
        for sentence in cleaned:
            missing = sorted(set(re.findall(r'\{\{\s*([A-Za-z_][A-Za-z0-9_]*)\s*\}\}', sentence)) - names)
            if missing:
                raise LibraryError('invalid_intents', f"{{{{{missing[0]}}}}} is not a parameter of {name}")
        raw['intents'] = list(dict.fromkeys(cleaned))
    _commit(path, raw)
    return detail(name, store)


def rename(old: str, new: str, store: FlowStore | None = None) -> dict:
    store = store or FlowStore()
    path, raw = _editable(store, old)
    target = _user_path(store, new)
    if new == old:
        return detail(old, store)
    if os.path.lexists(target) or (store.builtin_path and os.path.exists(os.path.join(store.builtin_path, new + '.json'))):
        raise LibraryError('flow_exists', f'{new} already exists')
    raw['name'] = new
    _commit(target, raw, overwrite=False)
    os.unlink(path)
    return detail(new, store)


def remove(name: str, store: FlowStore | None = None) -> dict:
    store = store or FlowStore()
    path, source = _locate(store, name)
    if source != 'user':
        raise LibraryError('flow_read_only', 'bundled flows cannot be removed')
    os.unlink(path)
    return {'ok': True, 'removed': name}


def import_file(source: str, *, name: str | None = None, force: bool = False,
                store: FlowStore | None = None) -> dict:
    store = store or FlowStore()
    try:
        raw = json.loads(_read_text(source))
    except OSError as exc:
        raise LibraryError('file_unavailable', exc.strerror or str(exc)) from None
    except ValueError as exc:
        raise LibraryError('invalid_flow', f'not JSON ({exc})') from None
    if not isinstance(raw, dict):
        raise LibraryError('invalid_flow', 'a flow file holds one JSON object')
    if raw.get('schema') == 1:
        raise LibraryError('legacy_schema', 'schema 1 flow; migrate it before saving')
    name = name or raw.get('name') or os.path.splitext(os.path.basename(source))[0]
    target = _user_path(store, str(name))
    if os.path.abspath(source) == os.path.abspath(target):
        return detail(str(name), store)
    if os.path.islink(target):
        raise LibraryError('flow_read_only', 'the saved flow is a symbolic link; replace it directly')
    raw['name'] = name
    _commit(target, raw, overwrite=force)
    return detail(str(name), store)


USAGE = """usage: haejo flows [--json]                         saved flows
       haejo flows show <name> [--json]             parameters, sentences and steps
       haejo flows set <name> [-p k=v ...] [--intent "..." ...] [--json]
                                                    change parameter defaults (empty = asked at run) / sentences
       haejo flows rename <name> <new-name> [--json]
       haejo flows rm <name> [--json]
       haejo flows save <flow.json> [--name N] [--force] [--json]
                                                    keep a flow file in the library (then: haejo replay <name>)"""


def _print_entry(entry: dict) -> None:
    mark = '' if entry.get('ok') else f"  [{entry.get('error')}]"
    print(f"  {entry['name']}{mark}")
    if not entry.get('ok'):
        print(f"    {entry.get('detail', '')}")
        return
    bits = [entry['target'], f"{entry['step_count']} steps"]
    if entry['consequential_steps']:
        bits.append(f"{entry['consequential_steps']} lasting")
    if entry['source'] != 'user':
        bits.append('bundled')
    print('    ' + ' · '.join(bits))
    if entry['params']:
        print('    params: ' + ', '.join(f"{k}={'(asked)' if v is None else v}" for k, v in entry['params'].items()))


def main(argv: list[str]) -> int:
    as_json = '--json' in argv
    args = [a for a in argv if a != '--json']

    def emit(result: dict) -> int:
        if as_json:
            print(json.dumps(result, ensure_ascii=False))
        return 0

    try:
        if not args:
            result = list_flows()
            if as_json:
                return emit(result)
            print(f"  library: {result['store']}")
            if not result['flows']:
                print('  (no saved flows — keep one with: haejo flows save <flow.json>)')
            for entry in result['flows']:
                _print_entry(entry)
            return 0
        verb, rest = args[0], args[1:]
        if verb in ('-h', '--help', 'help'):
            print(USAGE)
            return 0
        if verb == 'show' and len(rest) == 1:
            result = detail(rest[0])
            if as_json:
                return emit(result)
            entry = result['flow']
            _print_entry(entry)
            for sentence in entry.get('intents') or []:
                print(f'    "{sentence}"')
            for step in entry.get('steps') or []:
                tag = f"  [{', '.join(step['effects'])}]" if step['consequential'] else ''
                print(f"    {step['index']:>2}. {step['action']} {step['label']}{tag}")
            print(f"  run: haejo replay {entry['name']}{_HELPER}")
            return 0
        if verb == 'set' and rest:
            name, params, intents, i = rest[0], {}, None, 1
            while i < len(rest):
                if rest[i] == '-p' and i + 1 < len(rest) and '=' in rest[i + 1]:
                    key, value = rest[i + 1].split('=', 1)
                    params[key] = value
                elif rest[i] == '--intent' and i + 1 < len(rest):
                    intents = (intents or []) + [rest[i + 1]]
                elif rest[i] == '--clear-intents':
                    intents, i = [], i - 1
                else:
                    raise LibraryError('invalid_arguments', USAGE)
                i += 2
            if not params and intents is None:
                raise LibraryError('invalid_arguments', 'nothing to change; add -p name=value or --intent "..."')
            result = set_fields(name, params=params, intents=intents)
            if as_json:
                return emit(result)
            print(f'  updated {name}')
            _print_entry(result['flow'])
            return 0
        if verb == 'rename' and len(rest) == 2:
            result = rename(rest[0], rest[1])
            if as_json:
                return emit(result)
            print(f'  renamed {rest[0]} → {rest[1]}')
            return 0
        if verb in ('rm', 'remove', 'delete') and len(rest) == 1:
            result = remove(rest[0])
            if as_json:
                return emit(result)
            print(f'  removed {rest[0]}')
            return 0
        if verb in ('save', 'import') and rest:
            source, name, force, i = rest[0], None, False, 1
            while i < len(rest):
                if rest[i] == '--name' and i + 1 < len(rest):
                    name, i = rest[i + 1], i + 2
                elif rest[i] == '--force':
                    force, i = True, i + 1
                else:
                    raise LibraryError('invalid_arguments', USAGE)
            result = save_result = import_file(source, name=name, force=force)
            if as_json:
                return emit(result)
            print(f"  saved {save_result['flow']['name']} → {save_result['flow']['path']}")
            print(f"  run: haejo replay {save_result['flow']['name']}{_HELPER}")
            return 0
        raise LibraryError('invalid_arguments', USAGE)
    except LibraryError as exc:
        if as_json:
            print(json.dumps({'ok': False, 'error': exc.code, 'detail': exc.detail}, ensure_ascii=False))
        else:
            print(f'{exc.code}: {exc.detail}', file=sys.stderr if exc.code != 'invalid_arguments' else sys.stdout)
        return 2 if exc.code == 'invalid_arguments' else 1
    except OSError as exc:
        if as_json:
            print(json.dumps({'ok': False, 'error': 'library_unavailable', 'detail': str(exc)[:MAX_TEXT]}, ensure_ascii=False))
        else:
            print(f'library_unavailable: {exc}', file=sys.stderr)
        return 1
