"""Context-local model deadline and host cancellation for planner/witness calls.

Cancellation is local: it stops new attempts and the owned local provider
process group. It never proves that remote generation or billing stopped.
"""
from contextlib import contextmanager
from contextvars import ContextVar
import math
import time

_DEADLINE = ContextVar('tacto_model_deadline', default=None)
_CANCEL = ContextVar('tacto_model_cancel', default=())


class ModelCancelled(Exception):
    """The host cancelled this model request before an answer was accepted.

    ``output``/``stderr`` hold bounded raw bytes captured before the local
    process group was stopped, for telemetry parsing only, never as answers.
    """

    def __init__(self, message='model request cancelled by host', *, output=None, stderr=None):
        super().__init__(message)
        self.output = output
        self.stderr = stderr


@contextmanager
def model_cancellation(predicate):
    """Scope a host cancellation predicate over nested model requests.

    Nested scopes combine: any true predicate cancels. A predicate that raises
    counts as cancelled, because the request can no longer prove it may run.
    """
    if predicate is None:
        yield
        return
    if not callable(predicate):
        raise TypeError('model cancellation predicate must be callable')
    token = _CANCEL.set((*_CANCEL.get(), predicate))
    try:
        yield
    finally:
        _CANCEL.reset(token)


def model_cancellation_active():
    return bool(_CANCEL.get())


def model_cancelled():
    for predicate in _CANCEL.get():
        try:
            if predicate():
                return True
        except Exception:
            return True
    return False


def raise_if_model_cancelled():
    if model_cancelled():
        raise ModelCancelled()


@contextmanager
def model_deadline(deadline):
    if deadline is not None and (type(deadline) not in (int, float) or not math.isfinite(deadline)):
        raise ValueError("model deadline must be finite")
    previous = _DEADLINE.get()
    effective = previous if deadline is None else deadline if previous is None else min(previous, deadline)
    token = _DEADLINE.set(effective)
    try:
        yield
    finally:
        _DEADLINE.reset(token)


def remaining_model_seconds(timeout_seconds=420):
    if (type(timeout_seconds) not in (int, float) or not math.isfinite(timeout_seconds)
            or timeout_seconds <= 0):
        raise ValueError('model timeout must be finite and positive')
    # Every attempt asks for its remaining budget first; a cancelled scope has
    # none, so no new route or validation retry can start after cancellation.
    raise_if_model_cancelled()
    remaining = min(timeout_seconds, 420)
    deadline = _DEADLINE.get()
    if deadline is not None:
        remaining = min(remaining, deadline - time.monotonic())
    if remaining <= 0:
        raise TimeoutError('model request deadline exceeded')
    return remaining
