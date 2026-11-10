"""Read-only, low-frequency Flow waits with a paused availability clock."""
import math
import re
import sys
import time

DEFAULT_POLL_S = 10
MAX_TIMEOUT_S = 7200


def _check_problem(check, depth=0):
    from .flow import Postcondition, Selector
    if not isinstance(check, Postcondition) or depth > 8:
        return 'until requires a check object (depth at most 8)'
    if check.field is not None and not isinstance(check.field, Selector):
        return 'until.field requires a selector'
    for key in ('equals', 'contains', 'absent', 'absent_role', 'attribute'):
        value = getattr(check, key)
        if value is not None and not isinstance(value, str):
            return 'until predicates require text'
    if check.exists is not None and (check.exists is not True or check.field is None):
        return 'until.exists requires true and a field selector'
    if not isinstance(check.all_of, list) or len(check.all_of) > 32:
        return 'until.all_of requires at most 32 checks'
    if (all(getattr(check, key) is None for key in ('equals', 'contains', 'absent', 'absent_role', 'exists'))
            and not check.all_of):
        return 'until requires equals, contains, absent, absent_role, exists or all_of'
    if check.absent_role is not None and not check.absent_role.strip():
        return 'until.absent_role requires a role'
    for child in check.all_of:
        problem = _check_problem(child, depth + 1)
        if problem:
            return problem
    return None


def step_problem(step):
    problem = _check_problem(step.until)
    if problem:
        return problem
    if (type(step.timeout_s) not in (int, float) or not 0 < step.timeout_s <= MAX_TIMEOUT_S
            or not math.isfinite(step.timeout_s)):
        return 'wait_until.timeout_s must be finite, positive and at most 7200'
    if step.poll_s is not None and (type(step.poll_s) not in (int, float)
            or not 1 <= step.poll_s <= 60 or not math.isfinite(step.poll_s)):
        return 'wait_until.poll_s must be finite and from 1 to 60'
    if (step.selector is not None or step.params or step.binding is not None
            or step.postcondition is not None or step.expect is not None
            or step.skip_if is not None or step.captures):
        return 'wait_until uses until instead of input parameters, captures or other checks'
    if step.safety is not None and set(step.safety.effects) != {'read'}:
        return 'wait_until has only read effects'
    return None


# A pause is not counted against timeout_s, but it is not unbounded either: an
# off-screen diagnosis can also mean the window was ordered out for good.
MAX_PAUSED_S = 6 * 3600


def platform_pause_reason(target):
    """Cheap local availability check before an AX tree read on macOS.

    Remote/browser backends do not inherit the local machine's lock state.
    Unknown platform state leaves the driver's own observation authoritative.
    """
    if sys.platform != 'darwin' or not re.fullmatch(r'[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+', target):
        return None
    try:
        from .session import lock_state
        if lock_state().get('locked') is True:
            return 'screen_locked'
        import Quartz
        error, displays, count = Quartz.CGGetOnlineDisplayList(32, None, None)
        if error == 0 and count and all(Quartz.CGDisplayIsAsleep(display) for display in displays):
            return 'display_asleep'
    except Exception:
        pass
    return None


def observation_pause_reason(reply):
    """Use explicit backend diagnoses, never infer a pause from any failure."""
    lock = reply.get('lock')
    if isinstance(lock, dict) and lock.get('locked') is True:
        return 'screen_locked'
    reason = reply.get('reason')
    if reason in ('screen_locked', 'display_asleep', 'display_sleeping', 'window_offscreen',
                  'window_not_on_active_space', 'not_on_active_space'):
        return reason
    if reply.get('error') in ('screen_locked', 'display_asleep'):
        return reply['error']
    return None


def run_step(driver, target, step, index, result):
    """Return the matching fresh observation, or record a structured failure.

    Each interval is attributed to the last observed availability state. Pauses
    start on detection and finish on the first readable poll. A stable helper
    connection polls at most once per poll_s; it is not an idle stdin reader.
    """
    from .flow import _replay_observation
    from .observation_state import retryable_observation_error
    poll = DEFAULT_POLL_S if step.poll_s is None else step.poll_s
    started = checkpoint = time.monotonic()
    active = paused = 0.0
    previous_reason = None
    pauses = {}
    polls = 0

    def account(now, reason):
        nonlocal checkpoint, active, paused
        delta = max(0, now - checkpoint)
        checkpoint = now
        if reason:
            paused += delta
            pauses[reason] = pauses.get(reason, 0) + delta
        else:
            active += delta

    def record(**fields):
        result.record(step=index, action='wait_until', effect='none', polls=polls,
                      active_seconds=round(active, 6), paused_seconds=round(paused, 6),
                      elapsed_seconds=round(time.monotonic() - started, 6),
                      pauses=[{'reason': reason, 'seconds': round(seconds, 6)}
                              for reason, seconds in pauses.items()], **fields)

    while True:
        reason = platform_pause_reason(target)
        # Time asleep in the host is charged to the availability state last
        # observed, not to an independently expiring wall-clock deadline.
        account(time.monotonic(), previous_reason)
        observation = None
        if reason is None:
            observation = _replay_observation(driver.observe, target, 'tree_full')
            polls += 1
            reason = observation_pause_reason(observation)
        account(time.monotonic(), reason)
        previous_reason = reason
        if reason and paused >= MAX_PAUSED_S:
            record(status='error', error='wait_paused_too_long', reason=reason)
            return None
        if reason is None:
            if observation.get('type') == 'observation':
                if active <= step.timeout_s and step.until.check(observation['tree']):
                    record(status='ok')
                    return observation
            elif not retryable_observation_error(observation):
                record(status='error', error='wait_observation_failed', detail=observation)
                return None
            if active >= step.timeout_s:
                record(status='error', error='wait_timeout')
                return None
        # The connection and window/document scope stay open during replay.
        # Session/batch input idle timers run only at the next stdin read.
        time.sleep(poll if reason else min(poll, max(0, step.timeout_s - active)))
