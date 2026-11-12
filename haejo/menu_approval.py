"""Menu approval: the Haejo menu app answers consequential confirm steps.

Opt-in (`require_menu_approval` in preferences, default off). When off nothing
here runs and the CLI keeps its existing `--yes`/terminal behaviour. When on,
every confirm step on the CLI paths is decided in the Haejo menu app, whatever
flags or terminal the caller has; a grant the person already gave there
(this run, for a task, or always) passes at once.

Scope: this replaces the CLI's yes for confirm steps. Steps the policy marks
`preapproved` keep passing as before, and a caller that edits Haejo itself or
drives the screen without Haejo is outside what this part covers.
"""
from __future__ import annotations

import hashlib
import json
import os
import socket
import time
import uuid
from dataclasses import dataclass

from .contract import ApprovalToken

PENDING_EXIT = 4
PLAN_WAIT_SECONDS = 45.0
RUNTIME_WAIT_SECONDS = 600.0
_GRANT_TTL = 24 * 3600.0   # the menu app owns validity; this only stops a stale token in memory


def enabled(prefs=None) -> bool:
    if prefs is None:
        from .preferences import load_preferences
        prefs = load_preferences()
    return prefs.get('require_menu_approval') is True


def socket_path():
    from .preferences import product_directory
    return product_directory()/'approval.sock'


class MenuUnavailable(Exception):
    pass


def call(message: dict, timeout: float) -> dict:
    """One JSON request and one JSON reply over the menu app's private socket."""
    path = str(socket_path())
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as conn:
            conn.settimeout(timeout + 5.0)
            conn.connect(path)
            conn.sendall(json.dumps(message, ensure_ascii=False, separators=(',', ':')).encode() + b'\n')
            data = b''
            while not data.endswith(b'\n'):
                chunk = conn.recv(65536)
                if not chunk:
                    break
                data += chunk
                if len(data) > 1 << 20:
                    raise MenuUnavailable('reply too large')
        reply = json.loads(data.decode())
    except (OSError, ValueError, UnicodeError) as exc:
        raise MenuUnavailable(str(exc)) from None
    if not isinstance(reply, dict):
        raise MenuUnavailable('malformed reply')
    return reply


def _digest(value) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                     separators=(',', ':'), default=str).encode()).hexdigest()


def item_for(index: int, step, describe_text: str, effects=None) -> dict:
    c = step.safety
    return {
        'step': index,
        # A live field can add effects the step did not declare (a password
        # field adds `credential`); the card and any grant use what is real.
        'effects': sorted(set(effects) if effects is not None else set(c.effects)),
        'destination': c.destination.identity,
        'object_type': c.resource.object_type,
        'selection_count': c.resource.selection_count,
        'reversibility': c.reversibility,
        'describe': describe_text,
        # The binding digest covers the action, target and payload, so it is
        # the payload digest every item carries (financial included).
        'payload_digest': step.binding.digest() if step.binding is not None else None,
    }


def _plain(value):
    import dataclasses
    if value is None:
        return None
    if dataclasses.is_dataclass(value):
        return dataclasses.asdict(value)
    return getattr(value, '__dict__', str(value))


def request_for(flow, items: list[dict], window_id=None) -> dict:
    params = getattr(flow, 'params', None)
    return {
        'flow_name': flow.name,
        # Every step's action, selector, params, contract and binding: a changed
        # meaning (effects, recipient, payload) is a different request.
        'flow_digest': _digest([[s.action, s.selector and s.selector.__dict__, s.params,
                                 _plain(s.safety), s.binding.digest() if s.binding is not None else None]
                                for s in flow.steps]),
        'params_digest': _digest(params if isinstance(params, dict) else {}),
        'target': flow.target,
        'window_id': window_id,
        'task_hint': os.environ.get('HAEJO_TASK') or None,
        'items': items,
    }


@dataclass
class MenuApprovalToken(ApprovalToken):
    """An ApprovalToken that the menu app must also consume right before use.

    The local binding check runs first; then the menu app spends the item for
    this run, atomically, so one approval runs one command and a grant revoked
    in the menu stops the next step."""
    approval_id: str = ''
    run_id: str = ''
    step_index: int = -1
    payload_digest: str | None = None
    last_reason: str = ''

    def authorizes(self, binding, contract, now=None):
        ok, why = super().authorizes(binding, contract, now)
        if not ok:
            return ok, why
        try:
            reply = call({'op': 'consume', 'approval_id': self.approval_id, 'run_id': self.run_id,
                          'step': self.step_index, 'payload_digest': binding.digest()}, 10.0)
        except MenuUnavailable:
            self.last_reason = 'approval_unavailable'
            return False, 'approval_unavailable'
        if reply.get('ok') is True:
            return True, 'approved'
        self.last_reason = 'approval_' + str(reply.get('reason') or 'denied')
        return False, self.last_reason


def menu_token(base: ApprovalToken, approval_id: str, run_id: str, index: int, payload_digest) -> MenuApprovalToken:
    return MenuApprovalToken(binding_digest=base.binding_digest, effects=list(base.effects),
                             destination_identity=base.destination_identity, issued_at=base.issued_at,
                             expires_at=time.time() + _GRANT_TTL, approval_id=approval_id, run_id=run_id,
                             step_index=index, payload_digest=payload_digest)


def outcome(kind: str, **extra) -> dict:
    return {'type': 'approval_' + kind, 'effect': 'not_started', **extra}


def take_approval_arg(argv):
    """Remove `--approval <id>` from argv; returns (argv, id|None). ValueError on misuse."""
    if '--approval' not in argv:
        return list(argv), None
    k = argv.index('--approval')
    if argv.count('--approval') != 1 or k + 1 >= len(argv) or not argv[k + 1].startswith('ap_'):
        raise ValueError('--approval requires one approval id (ap_…)')
    return argv[:k] + argv[k + 2:], argv[k + 1]


def plan(flow, agent, window_id=None, approval_id=None):
    """Authorize a flow with the menu app.

    Returns (approvals, blocked, result): `result` is None when the run may
    start (then the approvals hold menu tokens for every confirm step, claimed
    for one run), or a typed outcome dict to print with PENDING_EXIT/1.
    Preapproved steps keep their ordinary tokens and never reach the menu.
    """
    from .contract import describe, policy
    asked: dict[int, str] = {}

    def collect(what: str) -> bool:
        return True
    approvals, blocked = agent.authorize(flow, ask=collect)
    if blocked:
        return approvals, blocked, None
    items = []
    for i, st in enumerate(flow.steps):
        if i in approvals and st.safety is not None and policy(st.safety).risk == 'confirm':
            items.append(item_for(i, st, describe(st.safety, policy(st.safety))))
            asked[i] = items[-1]['payload_digest']
    if not items:
        return approvals, [], None
    request = request_for(flow, items, window_id)
    message = ({'op': 'resume', 'approval_id': approval_id, 'request': request} if approval_id
               else {'op': 'plan', 'request': request, 'wait': PLAN_WAIT_SECONDS})
    try:
        reply = call(message, PLAN_WAIT_SECONDS)
    except MenuUnavailable:
        return approvals, [], outcome('unavailable', hint='Haejo 앱을 열어 두면 메뉴에서 승인할 수 있습니다')
    status = reply.get('status')
    ident = reply.get('approval_id') or approval_id
    if status == 'native':
        # Enforced in the helper: each risky input is decided there, on what
        # it reads, with one card. Nothing to ask before the run.
        return approvals, [], None
    if status == 'pending':
        return approvals, [], outcome('pending', approval_id=ident, resume=f'--approval {ident}')
    if status != 'allowed' or not isinstance(ident, str):
        return approvals, [], outcome(str(status or 'denied'), approval_id=ident)
    run_id = uuid.uuid4().hex
    try:
        claim = call({'op': 'claim', 'approval_id': ident, 'run_id': run_id}, 10.0)
    except MenuUnavailable:
        return approvals, [], outcome('unavailable', approval_id=ident)
    if claim.get('ok') is not True:
        return approvals, [], outcome(str(claim.get('reason') or 'claimed'), approval_id=ident)
    for i, digest in asked.items():
        approvals[i] = menu_token(approvals[i], ident, run_id, i, digest)
    return approvals, [], None


def finish(approvals, ok: bool):
    """Tell the menu app the run ended (completed or partial); best effort."""
    token = next((t for t in (approvals or {}).values() if isinstance(t, MenuApprovalToken)), None)
    if token is None:
        return
    try:
        call({'op': 'finish', 'approval_id': token.approval_id, 'run_id': token.run_id,
              'outcome': 'completed' if ok else 'partial'}, 5.0)
    except MenuUnavailable:
        pass


class RuntimeConfirm:
    """The CLI confirm callback when menu approval is on.

    Used for values settled during a run and for `haejo do` turns. It never
    raises: a menu that is gone, a card that times out or a refusal all answer
    no, and `last_outcome` says which so the result can name it."""
    menu_approval = True

    def __init__(self, target: str = '', wait: float = RUNTIME_WAIT_SECONDS):
        self.target = target
        self.wait = wait
        self.last_outcome = ''

    def request(self, step, question: str, index: int | None = None, effects=None) -> bool:
        item = None
        if step is not None and getattr(step, 'safety', None) is not None:
            try:
                item = item_for(index if index is not None else -1, step, question, effects)
            except Exception:
                item = None
        return self._ask(question, item)

    def __call__(self, question: str) -> bool:
        return self._ask(question, None)

    def _ask(self, question, item) -> bool:
        self.last_outcome = ''
        try:
            reply = call({'op': 'runtime', 'target': self.target, 'question': str(question)[:4000],
                          'item': item, 'task_hint': os.environ.get('HAEJO_TASK') or None,
                          'wait': self.wait}, self.wait)
        except MenuUnavailable:
            self.last_outcome = 'approval_unavailable'
            return False
        except Exception:
            self.last_outcome = 'approval_unavailable'
            return False
        if reply.get('status') == 'allowed':
            return True
        if reply.get('status') == 'native' and item is not None:
            # The helper decides this input when it is entered.
            return True
        self.last_outcome = 'approval_' + str(reply.get('status') or 'denied')
        return False
