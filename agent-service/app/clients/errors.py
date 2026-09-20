"""Typed failures raised by :class:`~app.clients.commerce_client.CommerceClient`.

Why this module exists
----------------------
``httpx`` raises a different exception per failure mode, and an HTTP status on its own does not
say whether the Agent is allowed to try again. Tool code (T029) must branch on *stable facts* --
an error code, a retryability decision -- not on exception types or message text. So every
failure that crosses this boundary is normalised into exactly one of two shapes:

- :class:`CommerceApiError` -- the backend answered with the structured error envelope.
- :class:`CommerceTransportError` -- no authoritative answer arrived (timeout, connection reset,
  unparseable body).

Two more failures are raised *around* a call rather than by one. They share the same base class, so
a single ``except CommerceError`` still means "this call did not succeed":

- :class:`UnsafeRequestParameterError` -- a caller-supplied value could not be sent safely, so
  nothing was sent at all.
- :class:`UnknownPrincipalRoleError` -- the call succeeded, but the identity it returned cannot be
  authorized.

Both are *known* failures with nothing to retry: the first never left the process, the second got a
clear answer it is refusing to act on.

"Answered" and "did not answer" are not interchangeable
-------------------------------------------------------
The distinction that carries the real risk is between the two *first* shapes: a
:class:`CommerceTransportError` does **not** mean the action failed, it means the outcome is
**unknown** -- the backend may or may not have committed.

The read/write asymmetry
------------------------
Knowing which of the two happened is what makes retry safe or unsafe, and it is not a property of
the HTTP method alone:

======================  ==========================  ===================================
Situation               Outcome                     Blind retry
======================  ==========================  ===================================
``GET`` answered 403    Known: it did not happen    No -- ``retryable`` is false
``GET`` timed out       Unknown, but side-effect    Yes -- worst case is a wasted call
                        free
``POST`` answered 503   Known: it did not commit    Yes -- ``retryable`` is true
state-changing ``POST`` Unknown: may have           No -- re-read authoritative state
                        committed                   first
side-effect free        Unknown, nothing committed  Yes -- worst case is a wasted call
``POST`` timed out
======================  ==========================  ===================================

"Answered" means the outcome is known; "no answer" means it is not. The last two rows are why
:class:`CommerceTransportError` takes an explicit ``request_was_safe`` argument instead of
deriving the answer from the HTTP method -- ``POST /after-sales/eligibility`` is a
deterministic evaluation that commits nothing, so it belongs in the fifth row, not the
fourth.

Blind retry is therefore never an unconditional right. See ``contracts/tool-contracts.md`` (no
blind retry; after an unknown timeout, read the authoritative state first) and
``contracts/error-contracts.md`` (``retryable=true`` does not mean unlimited retries -- each Tool
owns a finite retry budget).
"""

from __future__ import annotations

__all__ = [
    "CommerceApiError",
    "CommerceError",
    "CommerceTransportError",
    "UnknownPrincipalRoleError",
    "UnsafeRequestParameterError",
]


def _loggable(value: str) -> str:
    """Strip whitespace and control characters before a remote value reaches a message.

    Both new classes below interpolate a value that originated outside this process. A reflected
    string containing CR/LF can forge log lines, so it is rendered printable first. The raw value is
    still available on the exception for *structured* audit fields, where it cannot break a line.
    """
    printable = "".join(char for char in value if char.isprintable() and not char.isspace())
    return printable[:32] or "<empty>"


class CommerceError(Exception):
    """Base class for every failure raised by the typed Java API client.

    Catch this to handle "the call did not succeed" without distinguishing the two shapes; catch a
    subclass when the difference matters, which at the write boundary it usually does.
    """

    #: Whether the backend's state after this failure is genuinely unknown.
    outcome_unknown: bool = False


class CommerceApiError(CommerceError):
    """The backend answered with the structured error envelope.

    All payload fields come from the response body rather than local guessing, so callers can
    branch on them without parsing ``message``. ``message`` is kept for humans only.
    """

    outcome_unknown = False

    def __init__(
        self,
        *,
        error_code: str,
        http_status: int,
        retryable: bool,
        trace_id: str | None = None,
        message: str = "",
    ) -> None:
        super().__init__(f"{error_code} (HTTP {http_status})")
        self.error_code = error_code
        self.http_status = http_status
        self.retryable = retryable
        self.trace_id = trace_id
        self.message = message

    @property
    def blind_retry_allowed(self) -> bool:
        """Whether the same request may be repeated without checking state first.

        A backend that answered has *not* committed: the outcome is known to be "not done". So a
        retry is safe exactly when the envelope says the failure was transient.
        """
        return self.retryable


class CommerceTransportError(CommerceError):
    """No authoritative answer arrived: timeout, connection failure, or unparseable body.

    The outcome is **unknown**, not failed. ``request_was_safe`` records whether the *operation* had
    side effects -- decided by its semantics, not by its HTTP method, because
    ``POST /after-sales/eligibility`` is a deterministic evaluation and must stay safely retryable.
    It is the only thing that makes an unknown outcome safe to repeat blindly.
    """

    outcome_unknown = True

    def __init__(self, *, reason: str, request_was_safe: bool) -> None:
        super().__init__(reason)
        self.reason = reason
        self.request_was_safe = request_was_safe

    @property
    def blind_retry_allowed(self) -> bool:
        """Whether the same request may be repeated without checking state first.

        Only safe (side-effect free) requests qualify. A state-changing request must first re-read
        authoritative state, because this error cannot tell whether it already committed.
        """
        return self.request_was_safe


class UnsafeRequestParameterError(CommerceError):
    """A caller-supplied value could not be sent safely, so nothing was sent.

    ``order_id`` reaches the client from model output. Interpolated into a URL path unchecked,
    ``../``, ``?`` or ``#`` would send the call to a different endpoint -- the URL equivalent of SQL
    injection, and exactly what ``contracts/tool-contracts.md`` forbids ("Tool 不接受模型输出的
    任意 URL"). This failure is local and known: no request left the process, so there is nothing to
    retry and nothing whose outcome could be unknown.

    ``error_code`` reuses the shared ``INVALID_PARAMETER`` taxonomy entry so Eval attributes the
    failure to parameter validation instead of to the backend.
    """

    outcome_unknown = False
    error_code = "INVALID_PARAMETER"

    def __init__(self, *, field: str, reason: str) -> None:
        # The offending value is deliberately not interpolated: it is untrusted input, and this text
        # can reach a log line.
        super().__init__(f"{field}: {reason}")
        self.field = field
        self.reason = reason


class UnknownPrincipalRoleError(CommerceError):
    """Java returned a principal role this service cannot authorize.

    The call *succeeded*; the identity it returned is the problem. ``role`` stays open on the wire
    because Java owns the value set, so "unrecognized" has to be decided by the identity layer
    rather than by a parser. Failing closed here means the run ends as ``SAFE_STOP``/``ESCALATED``
    with a stable code and an audit record; the two alternatives are worse -- defaulting to
    ``CUSTOMER`` is a privilege guess, and raising a generic 500 loses the reason.

    ``error_code`` reuses ``ACCESS_DENIED`` from the shared taxonomy: "已认证，但当前角色/权限
    不允许访问该能力". ``wire_role`` keeps the raw value for structured audit only -- use
    ``str(error)`` for anything human-readable, since that form is sanitized.
    """

    outcome_unknown = False
    error_code = "ACCESS_DENIED"

    def __init__(self, *, user_id: str, wire_role: str) -> None:
        super().__init__(f"principal role {_loggable(wire_role)!r} is not authorizable")
        self.user_id = user_id
        self.wire_role = wire_role
