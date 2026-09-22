"""Write execution with unknown-outcome recovery -- the refund write path.

Why this module exists (and why it is not in the client)
-------------------------------------------------------
``CommerceClient.create_refund`` deliberately refuses to retry (T016 rule 4). It cannot: "no answer
arrived" means the outcome is **unknown**, and the client has no budget, no intent, and no authority
to decide what an unknown outcome means for the user's money. Java cannot decide either -- it cannot
see that this is attempt two of one logical request. That decision belongs here, with two facts only
this layer has:

1. **the idempotency key**, which identifies the logical write across attempts and across process
   restarts; and
2. **the retry budget**, which makes "at least once" delivery stop being "at least one duplicate".

The rule T022 pins down is short: *never let a lost response become a second refund, and never let
an unknown outcome become a success or a failure claim.*

```
persist intent (key durable)         <-- before anything is sent
        |
        v
POST /refunds (request_is_safe=False)
        |
        +-- answered ok .................. SUCCEEDED (resource_id from the response)
        +-- answered 4xx/5xx ............. FAILED with that error_code (retry only if retryable)
        +-- no answer (timeout/reset) .... outcome UNKNOWN -> read authoritative state:
                 |                            |- refund exists  -> SUCCEEDED, recovered=True
                 |                            |- no refund      -> retry the SAME key (budget)
                 |                            '- cannot confirm -> UNKNOWN, no retry
                 '-- budget exhausted ...... UNKNOWN (never FAILED: see below)
```

The last line is the subtle one. Reading "no refund exists yet" is **not** proof that none ever
will: a client-side timeout does not stop the server from finishing the request afterwards. So an
exhausted budget must end as ``WriteStatus.UNKNOWN`` and be escalated, never as a failure -- a
failure claim would tell the user "you were not refunded" about a refund that may still commit.
"""

from __future__ import annotations

import hashlib
import json
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from decimal import Decimal
from uuid import uuid4

from app.agent.state import AgentState, WriteIntent, WriteOutcome, WriteStatus
from app.clients.auth import AuthContext
from app.clients.commerce_client import CommerceClient
from app.clients.errors import CommerceApiError, CommerceError, CommerceTransportError
from app.clients.models import CreateRefundRequest, RefundResult

__all__ = [
    "CREATE_REFUND_ACTION",
    "DEFAULT_MAX_ATTEMPTS",
    "INTENT_NOT_DURABLE_ERROR_CODE",
    "UNKNOWN_OUTCOME_ERROR_CODE",
    "WriteIntentConflictError",
    "RefundWriteIntent",
    "RefundWriteOutcome",
    "create_refund",
    "refund_write_intent",
    "write_may_already_have_committed",
]

logger = logging.getLogger(__name__)

#: Action name recorded in the write intent and in ``WriteOutcome.action``.
CREATE_REFUND_ACTION = "CREATE_REFUND_REQUEST"

#: One attempt plus one same-key retry. A budget, not a loop: every extra attempt is another chance
#: to be wrong about what already happened.
DEFAULT_MAX_ATTEMPTS = 2

#: Upper bound on a caller-supplied budget. A configuration mistake must not be able to turn this
#: into an unbounded retry loop (FR-007 / US5).
MAX_ATTEMPTS_LIMIT = 5

#: Terminal "we do not know whether the refund exists" code. Reuses the shared taxonomy entry whose
#: documented handling is exactly ours: do not retry blindly, read authoritative state first.
UNKNOWN_OUTCOME_ERROR_CODE = "WRITE_TIMEOUT_UNKNOWN"

#: Local failure code for "the idempotency intent could not be made durable". Reuses
#: ``INTERNAL_ERROR``: it is our infrastructure failing, and the correct response is to send nothing
#: rather than a write whose key we may be unable to reproduce.
INTENT_NOT_DURABLE_ERROR_CODE = "INTERNAL_ERROR"


class WriteIntentConflictError(ValueError):
    """A resumed write no longer matches the durable logical request.

    Reusing the old key with a changed payload would become IDEMPOTENCY_CONFLICT at Java, while
    minting a new key would create a different logical write. Neither is valid recovery, so stop
    locally before any network call.
    """


def _canonical_amount(value: Decimal | None) -> str | None:
    """Stable decimal spelling for a fingerprint; never use binary float text for money."""
    if value is None:
        return None
    return format(value.normalize(), "f")


def _refund_request_fingerprint(
    *,
    order_id: str,
    reason_code: str,
    requested_amount: Decimal | None,
) -> str:
    """SHA-256 of the V1 logical refund payload, excluding run id and idempotency key."""
    payload = {
        "action": CREATE_REFUND_ACTION,
        "orderId": order_id,
        "reasonCode": reason_code,
        "requestedAmount": _canonical_amount(requested_amount),
    }
    encoded = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True)
class RefundWriteIntent:
    """One logical refund, identified by a key that survives retries and process restarts."""

    run_id: str
    order_id: str
    reason_code: str
    idempotency_key: str
    requested_amount: Decimal | None = None

    def to_state_intent(self) -> WriteIntent:
        """The persistable form. Written *before* the request is sent."""
        return WriteIntent(
            action=CREATE_REFUND_ACTION,
            target_id=self.order_id,
            idempotency_key=self.idempotency_key,
            request_fingerprint=_refund_request_fingerprint(
                order_id=self.order_id,
                reason_code=self.reason_code,
                requested_amount=self.requested_amount,
            ),
        )


@dataclass(frozen=True)
class RefundWriteOutcome:
    """What the write attempt(s) established -- and what they did not.

    ``recovered`` separates "the backend's answer told us" from "authoritative state told us". Both
    are successes, but Eval and the trace must be able to tell them apart: a recovery means at least
    one response was lost, which is an infrastructure fact worth counting.
    """

    write_status: WriteStatus
    attempts: int
    idempotency_key: str
    resource_id: str | None = None
    error_code: str | None = None
    recovered: bool = False
    trace_ids: tuple[str, ...] = field(default_factory=tuple)

    @property
    def succeeded(self) -> bool:
        return self.write_status is WriteStatus.SUCCEEDED

    def to_state_outcome(self) -> WriteOutcome:
        """The persistable outcome; written after the attempt settles."""
        return WriteOutcome(
            status=self.write_status,
            action=CREATE_REFUND_ACTION,
            resource_id=self.resource_id,
            error_code=self.error_code,
        )


def refund_write_intent(
    state: AgentState,
    *,
    order_id: str,
    reason_code: str,
    requested_amount: Decimal | None = None,
) -> RefundWriteIntent:
    """Build this run's refund intent, **reusing a persisted key** for the same target.

    Reuse is keyed on (action, target): the same run refunding a *different* order is a different
    logical write and must get its own key, while a resumed attempt at the same order must keep the
    original one. That is the whole point of persisting the intent -- a fresh ``uuid4`` here would
    turn every resume into a second refund.
    """
    persisted = state.write_intent
    proposed_fingerprint = _refund_request_fingerprint(
        order_id=order_id,
        reason_code=reason_code,
        requested_amount=requested_amount,
    )
    if (
        persisted is not None
        and persisted.action == CREATE_REFUND_ACTION
        and persisted.target_id == order_id
    ):
        if persisted.request_fingerprint != proposed_fingerprint:
            raise WriteIntentConflictError(
                "the resumed refund payload does not match the durable write intent"
            )
        return RefundWriteIntent(
            run_id=str(state.run_id),
            order_id=order_id,
            reason_code=reason_code,
            idempotency_key=persisted.idempotency_key,
            requested_amount=requested_amount,
        )
    return RefundWriteIntent(
        run_id=str(state.run_id),
        order_id=order_id,
        reason_code=reason_code,
        idempotency_key=uuid4().hex,
        requested_amount=requested_amount,
    )


def write_may_already_have_committed(state: AgentState) -> bool:
    """Whether persisted state says an attempt was made whose outcome is not settled.

    ``PENDING``/``UNKNOWN`` both mean "a request may have reached Java". ``NOT_ATTEMPTED`` and
    ``FAILED`` mean it did not commit *as far as we know* -- and since a settled outcome is only
    ever written after authoritative confirmation, those may be trusted. ``SUCCEEDED`` needs no
    recovery either: the write is done.
    """
    return state.write_intent is not None and state.write.status in {
        WriteStatus.PENDING,
        WriteStatus.UNKNOWN,
    }


async def create_refund(
    *,
    client: CommerceClient,
    auth: AuthContext,
    intent: RefundWriteIntent,
    persist_intent: Callable[[WriteIntent, WriteOutcome], Awaitable[None]],
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    may_already_have_committed: bool = False,
) -> RefundWriteOutcome:
    """Create exactly one refund, or report that the outcome could not be established.

    ``persist_intent`` is required, and it is called *before* the first request with both the
    durable intent and a ``PENDING`` outcome. The callback must persist those two values atomically:
    a checkpoint that contains the key but still says ``NOT_ATTEMPTED`` is ambiguous on resume.
    If that persistence fails, nothing is sent.
    """
    if not 1 <= max_attempts <= MAX_ATTEMPTS_LIMIT:
        raise ValueError(f"max_attempts must be between 1 and {MAX_ATTEMPTS_LIMIT}")

    pending = WriteOutcome(status=WriteStatus.PENDING, action=CREATE_REFUND_ACTION)
    try:
        await persist_intent(intent.to_state_intent(), pending)
    except Exception as exc:
        logger.error(
            "refusing to send a refund whose idempotency intent could not be persisted: %s",
            type(exc).__name__,
        )
        return RefundWriteOutcome(
            write_status=WriteStatus.FAILED,
            attempts=0,
            idempotency_key=intent.idempotency_key,
            error_code=INTENT_NOT_DURABLE_ERROR_CODE,
        )

    trace_ids: list[str] = []

    if may_already_have_committed:
        # Resuming: read before writing. If a previous attempt did commit, this is where we find out
        # -- without sending anything.
        confirmed = await _confirmed_refunds(
            client, auth, intent.order_id, intent.idempotency_key
        )
        if confirmed is None:
            return _unknown(attempts=0, intent=intent, trace_ids=trace_ids)
        if confirmed:
            return _recovered(confirmed[0], attempts=0, intent=intent, trace_ids=trace_ids)

    attempts = 0
    while attempts < max_attempts:
        attempts += 1
        try:
            call = await client.create_refund(
                auth, idempotency_key=intent.idempotency_key, request=_request_body(intent)
            )
        except CommerceApiError as exc:
            # "Answered" means Java did not commit, so this failure is known rather than unknown.
            if exc.trace_id is not None:
                trace_ids.append(exc.trace_id)
            if exc.blind_retry_allowed and attempts < max_attempts:
                continue
            return RefundWriteOutcome(
                write_status=WriteStatus.FAILED,
                attempts=attempts,
                idempotency_key=intent.idempotency_key,
                error_code=exc.error_code,
                trace_ids=tuple(trace_ids),
            )
        except CommerceTransportError as exc:
            logger.warning("refund write outcome unknown for order: %s", exc.reason)
            confirmed = await _confirmed_refunds(
                client, auth, intent.order_id, intent.idempotency_key
            )
            if confirmed is None:
                # We cannot even read the state we would need to decide. Retrying would be a guess.
                return _unknown(attempts=attempts, intent=intent, trace_ids=trace_ids)
            if confirmed:
                return _recovered(
                    confirmed[0], attempts=attempts, intent=intent, trace_ids=trace_ids
                )
            # The authoritative read says nothing was committed *yet*. That is not the same as
            # "nothing ever will be" (the timed-out request may still finish), which is why the only
            # safe next step is the same key -- never a new one.
            continue
        else:
            trace_ids.append(call.trace_id)
            return RefundWriteOutcome(
                write_status=WriteStatus.SUCCEEDED,
                attempts=attempts,
                idempotency_key=intent.idempotency_key,
                resource_id=call.value.refund_request_id,
                trace_ids=tuple(trace_ids),
            )

    return _unknown(attempts=attempts, intent=intent, trace_ids=trace_ids)


def _request_body(intent: RefundWriteIntent) -> CreateRefundRequest:
    """The wire body.

    Built from the contract's own field names (``model_validate`` with camelCase keys) rather than
    from Python kwargs: the alias is what actually travels, and mypy -- without the pydantic
    plugin -- only knows the aliased signature. Validation still happens, and ``extra="forbid"``
    still applies.

    ``approval_request_id`` is deliberately absent: V1 has no authoritative approval record, and the
    Java side refuses a reference it cannot validate rather than storing it as if it were proof
    (US4/T049 adds the real binding).
    """
    return CreateRefundRequest.model_validate(
        {
            "orderId": intent.order_id,
            "reasonCode": intent.reason_code,
            "requestedAmount": intent.requested_amount,
            "runId": intent.run_id,
        }
    )


async def _confirmed_refunds(
    client: CommerceClient,
    auth: AuthContext,
    order_id: str,
    idempotency_key: str,
) -> list[RefundResult] | None:
    """The authoritative refund list for an order, or ``None`` when it could not be established.

    ``None`` and ``[]`` are different answers and must never be merged: ``[]`` means "the backend
    answered, and no refund exists", which is what makes a same-key retry safe. ``None`` means
    "we do not know", which makes any retry a guess.

    Recovery is bound to the durable idempotency key. A different refund on the same order is an
    important business fact, but it is not proof that *this* logical write committed. Without the
    key filter we could incorrectly report another concurrent refund as our own success.
    """
    try:
        call = await client.get_after_sales_status(
            auth, order_id, idempotency_key=idempotency_key
        )
    except CommerceError as exc:
        logger.warning("could not confirm refund state for the order: %s", type(exc).__name__)
        return None
    return call.value.refunds


def _unknown(
    *, attempts: int, intent: RefundWriteIntent, trace_ids: list[str]
) -> RefundWriteOutcome:
    return RefundWriteOutcome(
        write_status=WriteStatus.UNKNOWN,
        attempts=attempts,
        idempotency_key=intent.idempotency_key,
        error_code=UNKNOWN_OUTCOME_ERROR_CODE,
        trace_ids=tuple(trace_ids),
    )


def _recovered(
    refund: RefundResult,
    *,
    attempts: int,
    intent: RefundWriteIntent,
    trace_ids: list[str],
) -> RefundWriteOutcome:
    return RefundWriteOutcome(
        write_status=WriteStatus.SUCCEEDED,
        attempts=attempts,
        idempotency_key=intent.idempotency_key,
        resource_id=refund.refund_request_id,
        recovered=True,
        trace_ids=tuple(trace_ids),
    )
