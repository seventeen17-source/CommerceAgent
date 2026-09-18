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

The second one is the important one: it does **not** mean the action failed, it means the outcome
is **unknown**. The backend may or may not have committed.

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
``POST`` timed out      Unknown: may have           No -- re-read authoritative state
                        committed                   first
======================  ==========================  ===================================

"Answered" means the outcome is known. "No answer" means it is not. Every bit of trouble caused by
a timeout comes from the second row of that distinction.

Blind retry is therefore never an unconditional right. See ``contracts/tool-contracts.md`` (no
blind retry; after an unknown timeout, read the authoritative state first) and
``contracts/error-contracts.md`` (``retryable=true`` does not mean unlimited retries -- each Tool
owns a finite retry budget).
"""

from __future__ import annotations

__all__ = ["CommerceApiError", "CommerceError", "CommerceTransportError"]


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

    The outcome is **unknown**, not failed. ``request_was_safe`` records whether the HTTP method
    had side effects; it is the only thing that makes an unknown outcome safe to repeat blindly.
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
