"""Experimental iPhone L2 contract; a live no-WDA AX bridge is not shipped.

The host supplies one already-open, explicitly device/app-bound IOSSession.
HID writes have no device ACK. Keep that session through receiving-state
verification; a lost reply never permits another tap or automatic reconnect.
"""
from dataclasses import dataclass, asdict
import hashlib
import json
import math
import re
import time
from typing import Protocol
import uuid

from .document_label import quote_value

UPSTREAM_REVISION = '89702099f4d7552f704f93b4526756abda319ceb'
IOS_TAP_CAPABILITY = 'ios.tap_once.v1'
_TARGET = re.compile(r'ios://([A-Za-z0-9-]{8,80})/([A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+)\Z')
_ROLES = {'Button', 'StaticText', 'TextField', 'TextArea', 'Switch', 'Link', 'Group', 'Cell'}
_SNAPSHOT_ERRORS = {'ios_session_stopped','ios_target_changed','ios_connection_identity_unavailable',
                    'ios_connection_changed','ios_orientation_or_lock_unsupported','ios_snapshot_invalid','ios_screen_stalled'}


def parse_target(target):
    match = _TARGET.fullmatch(target) if isinstance(target, str) else None
    if not match:
        raise ValueError('ios_target_requires_explicit_device_and_bundle_id')
    return match.groups()


@dataclass(frozen=True)
class IOSNode:
    handle: str
    role: str
    identifier: str
    label: str
    value: str
    frame: tuple[float, float, float, float]
    enabled: bool = True
    hittable: bool = False


@dataclass(frozen=True)
class IOSSnapshot:
    device_id: str
    bundle_id: str
    connection_id: str
    orientation: str
    viewport: tuple[float, float]
    nodes: tuple[IOSNode, ...]
    locked: bool = False
    input_ready: bool = False
    modal_present: bool | None = None


class IOSSession(Protocol):
    """Trusted host transport. AX reads and taps share this connection lifetime.

    read_snapshot must read the *foreground* app and actual device orientation,
    lock and readiness, not echo requested values. tap_once returns True only
    for a completed host write (not a device ACK), False only before any write,
    and None for an uncertain/partial write. It must never reconnect or resend.
    Pairing, Developer Mode, DDI and UI Automation are human-owned setup.
    """
    def read_snapshot(self) -> IOSSnapshot: ...
    def tap_once(self, x: int, y: int) -> bool | None: ...
    def close(self) -> None: ...


class ScreenProgressClock:
    """A repeated model call/observation is not progress on the same screen."""
    def __init__(self, clock=time.monotonic):
        self.clock, self.fingerprint, self.changed_at, self.previous = clock, None, None, None

    def read(self):
        value = self.clock()
        if type(value) not in (int, float) or not math.isfinite(value) or self.previous is not None and value < self.previous:
            raise ValueError('invalid_ios_clock')
        self.previous = value
        return value

    def observe(self, fingerprint):
        now = self.read()
        if fingerprint != self.fingerprint:
            self.fingerprint, self.changed_at = fingerprint, now
        return now - self.changed_at


@dataclass
class TapReceipt:
    operation_id: str
    sent: bool | None = None
    screen_changed: bool | None = None
    screen_change_verified: bool = False


def _number(value):
    try:
        return type(value) in (int, float) and math.isfinite(value)
    except OverflowError:
        return False


class IOSDriver:
    """Portable spike adapter for explicit, host-authorized reversible taps.

    No text/clipboard, OCR click fallback, app launch, landscape, auto-pairing,
    or consequential commit capability. A transport fixture is not live iOS.
    """
    capabilities = frozenset({IOS_TAP_CAPABILITY, 'observe.labels_v1'})
    platform = 'ios-spike'

    def __init__(self, target, session: IOSSession, *, authorize_tap=None,
                 cancelled=None, clock=time.monotonic, sleep=time.sleep, screen_timeout_seconds=10):
        if not _number(screen_timeout_seconds) or not 0 < screen_timeout_seconds <= 120:
            raise ValueError('invalid_ios_screen_timeout')
        self.target, self.session = target, session
        self.device_id, self.bundle_id = parse_target(target)
        self.authorize_tap = authorize_tap or (lambda target, node: False)
        self.cancelled = cancelled or (lambda: False)
        self.progress = ScreenProgressClock(clock)
        self.screen_timeout_seconds = screen_timeout_seconds
        self.sleep = sleep
        self.connection_id = None
        self.current = None
        self.obs_id = None
        self.before = None
        self.pending = None
        self.receipts = []
        self.closed = False

    def identity(self, target):
        if target != self.target:
            raise ValueError('ios_target_changed')
        return self.target

    def _refuse(self, error, *, effect='not_started'):
        return {'type':'error', 'error':error, 'effect':effect}

    def _snapshot(self):
        if self.closed or self.cancelled():
            raise ValueError('ios_session_stopped')
        snap = self.session.read_snapshot()
        if self.closed or self.cancelled():
            raise ValueError('ios_session_stopped')
        if type(snap) is not IOSSnapshot or snap.device_id != self.device_id or snap.bundle_id != self.bundle_id:
            raise ValueError('ios_target_changed')
        if not isinstance(snap.connection_id, str) or not snap.connection_id or len(snap.connection_id) > 128:
            raise ValueError('ios_connection_identity_unavailable')
        if self.connection_id is not None and snap.connection_id != self.connection_id:
            raise ValueError('ios_connection_changed')
        if snap.orientation != 'portrait' or type(snap.locked) is not bool or snap.locked:
            raise ValueError('ios_orientation_or_lock_unsupported')
        if (type(snap.viewport) is not tuple or len(snap.viewport) != 2
                or not all(_number(n) and 0 < n <= 10000 for n in snap.viewport)
                or type(snap.nodes) is not tuple or not 1 <= len(snap.nodes) <= 5000
                    or type(snap.input_ready) is not bool or snap.modal_present is not None and type(snap.modal_present) is not bool):
            raise ValueError('ios_snapshot_invalid')
        handles = set()
        text_size = 0
        for node in snap.nodes:
            if (type(node) is not IOSNode or node.role not in _ROLES
                    or not isinstance(node.handle, str) or not node.handle or node.handle in handles
                    or any(not isinstance(s, str) or len(s) > 4096 for s in (node.handle, node.identifier, node.label, node.value))
                    or type(node.enabled) is not bool or type(node.hittable) is not bool
                    or type(node.frame) is not tuple or len(node.frame) != 4
                    or not all(_number(n) for n in node.frame) or any(n < 0 for n in node.frame[2:])):
                raise ValueError('ios_snapshot_invalid')
            handles.add(node.handle)
            text_size += sum(len(s) for s in (node.handle,node.identifier,node.label,node.value))
            if text_size > 1_000_000:
                raise ValueError('ios_snapshot_invalid')
        self.connection_id = snap.connection_id
        # Device/connection epochs and AX handles bind input identity, but are
        # not visual progress. AX enumeration order may also change at rest.
        nodes=[]
        for node in snap.nodes:
            visible=asdict(node)
            for key in ('handle','identifier','hittable'):
                visible.pop(key)
            nodes.append(json.dumps(visible,sort_keys=True,ensure_ascii=True,allow_nan=False))
        encoded = json.dumps({'orientation':snap.orientation,'viewport':snap.viewport,
                              'nodes':sorted(nodes),'locked':snap.locked,'modal_present':snap.modal_present},
                             sort_keys=True,ensure_ascii=True,allow_nan=False)
        fingerprint = hashlib.sha256(encoded.encode()).hexdigest()
        if self.progress.observe(fingerprint) >= self.screen_timeout_seconds:
            raise ValueError('ios_screen_stalled')
        return snap, fingerprint

    @staticmethod
    def _tree(snap):
        lines = ['0 Window Title: '+quote_value(snap.bundle_id)]
        for i, node in enumerate(snap.nodes, 1):
            fields = ', '.join(key+': '+quote_value(value) for key, value in (
                ('Identifier',node.identifier), ('Title',node.label), ('Value',node.value)))
            lines.append(f'  {i} {node.role} LabelsV1: {fields}'+(' [disabled]' if not node.enabled else ''))
        return '\n'.join(lines)

    def observe(self, target, mode='tree_full', require_window=True):
        # A failed observation must never leave an old index usable as a read
        # acknowledgement or input address. Pending dispatch evidence is kept.
        self.current, self.obs_id = None, None
        if target != self.target or mode != 'tree_full':
            return self._refuse('ios_target_or_mode_unsupported')
        try:
            snap, fingerprint = self._snapshot()
            tree = self._tree(snap)
        except ValueError as error:
            code = str(error) if str(error) in _SNAPSHOT_ERRORS else 'ios_snapshot_unavailable'
            return self._refuse(code)
        except Exception:
            return self._refuse('ios_snapshot_unavailable')
        self.current, self.obs_id = (snap, fingerprint, tree), 'ios-'+uuid.uuid4().hex
        if self.pending is not None:
            self.pending.screen_changed = fingerprint != self.before[1]
        return {'type':'observation','target':target,'obs_id':self.obs_id,'tree':tree,
                'screen_fingerprint':fingerprint,'element_count':len(snap.nodes)+1}

    def probe(self, obs_id, target, element_index):
        try:
            if self.closed or self.cancelled():
                return self._refuse('ios_session_stopped')
        except Exception:
            return self._refuse('ios_session_stopped')
        if self.current is None or obs_id != self.obs_id or target != self.target:
            return self._refuse('stale_observation')
        if type(element_index) is not int or not 1 <= element_index <= len(self.current[0].nodes):
            return self._refuse('ios_element_unavailable')
        node = self.current[0].nodes[element_index-1]
        return {'type':'probe','enabled':node.enabled,'actions':['AXPress'] if node.hittable else []}

    def act(self, obs_id, target, action, expect=None, risk_class='none', intent_text='', approved=False):
        if (not isinstance(action, dict) or set(action) != {'name','element_index'}
                or action.get('name') not in ('read','click')):
            return self._refuse('ios_action_unsupported')
        problem = self.probe(obs_id, target, action['element_index'])
        if problem['type'] == 'error':
            return problem
        if action['name'] == 'read':
            return {'type':'acted','action':'read'}
        if self.pending is not None:
            return self._refuse('ios_input_unresolved')
        bound = self.current
        node = bound[0].nodes[action['element_index']-1]
        if (not node.enabled or not node.hittable or not bound[0].input_ready
                or bound[0].modal_present is not False or risk_class != 'none'):
            return self._refuse('ios_input_not_ready')
        if expect:
            if not isinstance(expect, dict) or set(expect) - {'role','attribute','label','enabled','value','no_modal'}:
                return self._refuse('ios_expectation_unsupported')
            if (any(key in expect and not isinstance(expect[key],str) for key in ('role','attribute','label','value'))
                    or any(key in expect and type(expect[key]) is not bool for key in ('enabled','no_modal'))):
                return self._refuse('ios_expectation_unsupported')
            attributes = {'Title':node.label, 'Description':node.label, 'Identifier':node.identifier, 'Value':node.value}
            if (expect.get('role',node.role).removeprefix('AX') != node.role
                    or expect.get('enabled',node.enabled) is not node.enabled
                    or expect.get('value',node.value) != node.value
                    or expect.get('no_modal',True) is not True
                    or 'label' in expect and attributes.get(expect.get('attribute','Title')) != expect['label']):
                return self._refuse('ios_expectation_changed')
        try:
            if not self.authorize_tap(target, node):
                return self._refuse('ios_tap_not_authorized')
            fresh, fingerprint = self._snapshot()
        except Exception:
            return self._refuse('ios_preflight_unavailable')
        if obs_id != self.obs_id or self.current is None:
            return self._refuse('stale_observation')
        if fingerprint != bound[1]:
            return self._refuse('ios_screen_changed_before_tap')
        if fresh != bound[0]:
            return self._refuse('ios_input_identity_changed')
        x,y,w,h = node.frame
        width,height = fresh.viewport
        if not (w > 0 and h > 0 and x >= 0 and y >= 0 and x+w <= width and y+h <= height):
            return self._refuse('ios_element_outside_viewport')
        self.before = bound
        self.pending = TapReceipt(uuid.uuid4().hex)
        self.receipts.append(self.pending)
        try:
            self.pending.sent = self.session.tap_once(round((x+w/2)/width*65535), round((y+h/2)/height*65535))
        except Exception:
            return self._refuse('ios_dispatch_unknown', effect='unknown')
        if self.pending.sent is False:
            self.pending = None
            return self._refuse('ios_dispatch_not_started')
        if self.pending.sent is not True:
            self.pending.sent = None
            return self._refuse('ios_dispatch_unknown', effect='unknown')
        return {'type':'acted','action':'click','input_route':'ios_universal_hid',
                'sent':True,'screen_changed':None,'screen_change_verified':False,
                'unverified':'observe_effect','reobserve_required':True}

    def wait_until(self, target, predicate, timeout_ms=4000, poll_ms=100):
        if (type(timeout_ms) is not int or not 0 < timeout_ms <= 30000
                or type(poll_ms) is not int or not 1 <= poll_ms <= 1000):
            return self._refuse('ios_wait_invalid')
        if self.pending is not None and self.pending.sent is not True:
            return self._refuse('ios_dispatch_unknown',effect='unknown')
        deadline = self.progress.read() + timeout_ms/1000
        preexisting = self.pending is not None and predicate(self.before[2])
        while True:
            observed = self.observe(target)
            if observed['type'] != 'observation':
                return observed
            if predicate(observed['tree']):
                if self.pending is not None:
                    if preexisting or self.pending.screen_changed is not True:
                        return self._refuse('ios_transition_not_verified', effect='unknown')
                    self.pending.screen_change_verified = True
                    self.pending = None
                return observed
            now = self.progress.read()
            if now >= deadline:
                return {'type':'timeout','last_obs':observed}
            self.sleep(min(poll_ms/1000, deadline-now))

    def close(self):
        if not self.closed:
            self.closed = True
            self.current, self.obs_id = None, None
            try:
                self.session.close()
            except Exception:
                raise ValueError('ios_session_close_failed') from None


def run_ios_spike(flow, session, *, authorize_tap=None, **driver_options):
    """Model-free reversible Flow replay through an explicit host transport.

    Receipt fields are returned separately from replay success. No resume
    authority, route promotion, or live bridge discovery is supplied here.
    """
    from .flow import replay, every_step
    from .contract import policy
    from .execution_summary import interruption_summary
    if not 1 <= len(flow.steps) <= 100 or any(s.for_each is not None for s in every_step(flow.steps)):
        raise ValueError('ios_spike_requires_1_to_100_explicit_steps')
    flow = flow.bind()
    parse_target(flow.target)
    for step in every_step(flow.steps):
        if (step.action not in ('click','read') or step.selector is None or step.postcondition is None
                or step.unverified_ok or step.on_uncertain or step.skip_if is not None
                or step.safety is None or not set(step.safety.effects) <= {'read','write_ephemeral'}
                or step.safety.reversibility != 'reversible' or policy(step.safety).risk != 'none'):
            raise ValueError('ios_spike_requires_checked_reversible_read_or_click')
    driver = IOSDriver(flow.target, session, authorize_tap=authorize_tap, **driver_options)
    cleanup_error = None
    try:
        result = replay(driver, flow)
        if result.ok and any(not receipt.screen_change_verified for receipt in driver.receipts):
            result.record(status='unverified',error='ios_transition_not_verified',effect='unknown')
    finally:
        try:
            driver.close()
        except ValueError:
            cleanup_error = 'ios_session_close_failed'
    if cleanup_error is not None:
        result.record(status='error',stage='cleanup',error=cleanup_error,effect='unknown')
    return {'ok':result.ok,'receipts':[asdict(r) for r in driver.receipts],
            'session_closed':cleanup_error is None,'cleanup_error':cleanup_error,
            **interruption_summary(result,len(flow.steps))}
