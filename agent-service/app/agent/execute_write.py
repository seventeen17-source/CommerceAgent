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
from typing import Protocol
from uuid import uuid4

from app.agent.state import AgentState, ToolHistoryEntry, WriteIntent, WriteOutcome, WriteStatus
from app.agent.tool_tracing import TraceSink, report_tool_call
from app.clients.auth import AuthContext
from app.clients.commerce_client import CommerceClient
from app.clients.models import AfterSalesStatus, RefundResult
from app.tools.commerce_tools import CommerceTools
from app.tools.models import ToolEnvelope

__all__ = [
    "CREATE_REFUND_ACTION",
    "DEFAULT_MAX_ATTEMPTS",
    "INTENT_NOT_DURABLE_ERROR_CODE",
    "UNKNOWN_OUTCOME_ERROR_CODE",
    "RefundWriteExecutionResult",
    "RefundWriteIntent",
    "RefundWriteOutcome",
    "RefundWriteTools",
    "WriteIntentConflictError",
    "create_refund",
    "execute_refund_write",
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
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode(
        "utf-8"
    )
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


class RefundWriteTools(Protocol):
    """T029 Tool capabilities required by the T031 write executor."""

    async def create_refund_request(
        self,
        *,
        order_id: str,
        reason_code: str,
        requested_amount: Decimal | None,
        idempotency_key: str,
        run_id: str,
        approval_request_id: str | None = None,
    ) -> ToolEnvelope[RefundResult]:
        """Attempt one protected refund write without blind retry."""
        ...

    async def get_after_sales_status(
        self,
        order_id: str,
        *,
        idempotency_key: str | None = None,
    ) -> ToolEnvelope[AfterSalesStatus]:
        """Read authoritative after-sales state for recovery."""
        ...


@dataclass(frozen=True)
class RefundWriteExecutionResult:
    """One T031 write execution plus every Tool call needed to establish its outcome."""

    outcome: RefundWriteOutcome
    history: tuple[ToolHistoryEntry, ...] = field(default_factory=tuple)


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
    """Compatibility entrypoint retained for the T022 client-level tests.

    T031 moves orchestration to the T029 Tool boundary. Keeping this function avoids rewriting older
    callers while ensuring both old and new paths share exactly one recovery policy.
    """
    execution = await execute_refund_write(
        tools=CommerceTools(client=client, auth=auth),
        intent=intent,
        persist_intent=persist_intent,
        max_attempts=max_attempts,
        may_already_have_committed=may_already_have_committed,
    )
    return execution.outcome


async def execute_refund_write(
    *,
    tools: RefundWriteTools,
    intent: RefundWriteIntent,
    persist_intent: Callable[[WriteIntent, WriteOutcome], Awaitable[None]],
    record_trace: TraceSink | None = None,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    may_already_have_committed: bool = False,
    start_step_index: int = 1,
) -> RefundWriteExecutionResult:
    """Execute one logical refund through T029 Tools with bounded unknown-result recovery.

    The durable intent is persisted before the first Tool call. A WRITE_TIMEOUT_UNKNOWN never
    licenses a blind retry: the executor first calls get_after_sales_status with the same
    idempotency key. Only an authoritative empty result may lead to another attempt, and every
    attempt reuses the original key.

    ``record_trace`` receives each finished call, which is why it is a parameter rather than
    something the caller reconstructs later: the envelope stops existing when this function returns,
    and the evidence row needs the latency and correlation id that only exist inside it.
    """
    if not 1 <= max_attempts <= MAX_ATTEMPTS_LIMIT:
        raise ValueError(f"max_attempts must be between 1 and {MAX_ATTEMPTS_LIMIT}")
    if start_step_index < 0:
        raise ValueError("start_step_index must be non-negative")

    pending = WriteOutcome(status=WriteStatus.PENDING, action=CREATE_REFUND_ACTION)
    try:
        await persist_intent(intent.to_state_intent(), pending)
    except Exception as exc:
        logger.error(
            "refusing to send a refund whose idempotency intent could not be persisted: %s",
            type(exc).__name__,
        )
        return RefundWriteExecutionResult(
            outcome=RefundWriteOutcome(
                write_status=WriteStatus.FAILED,
                attempts=0,
                idempotency_key=intent.idempotency_key,
                error_code=INTENT_NOT_DURABLE_ERROR_CODE,
            )
        )

    history: list[ToolHistoryEntry] = []
    trace_ids: list[str] = []
    next_step_index = start_step_index

    if may_already_have_committed:
        confirmed, entry = await _tool_confirmed_refunds(
            tools,
            order_id=intent.order_id,
            idempotency_key=intent.idempotency_key,
            step_index=next_step_index,
        )
        history.append(entry)
        next_step_index += 1
        if confirmed is None or len(confirmed) > 1:
            return RefundWriteExecutionResult(
                outcome=_unknown(attempts=0, intent=intent, trace_ids=trace_ids),
                history=tuple(history),
            )
        if confirmed:
            return RefundWriteExecutionResult(
                outcome=_recovered(confirmed[0], attempts=0, intent=intent, trace_ids=trace_ids),
                history=tuple(history),
            )

    attempts = 0
    while attempts < max_attempts:
        attempts += 1
        result = await tools.create_refund_request(
            order_id=intent.order_id,
            reason_code=intent.reason_code,
            requested_amount=intent.requested_amount,
            idempotency_key=intent.idempotency_key,
            run_id=intent.run_id,
        )
        history.append(
            _history_entry(
                step_index=next_step_index,
                tool_name="create_refund_request",
                result=result,
            )
        )
        report_tool_call(
            record_trace,
            step_index=next_step_index,
            tool_name="create_refund_request",
            envelope=result,
            input_summary={"orderId": intent.order_id, "reasonCode": intent.reason_code},
        )
        next_step_index += 1

        if result.trace_id is not None:
            trace_ids.append(result.trace_id)

        if result.success:
            authoritative_write = result.data
            if authoritative_write is None:
                raise ValueError("successful refund Tool result is missing data")
            return RefundWriteExecutionResult(
                outcome=RefundWriteOutcome(
                    write_status=WriteStatus.SUCCEEDED,
                    attempts=attempts,
                    idempotency_key=intent.idempotency_key,
                    resource_id=authoritative_write.refund_request_id,
                    trace_ids=tuple(trace_ids),
                ),
                history=tuple(history),
            )

        if result.error_code == UNKNOWN_OUTCOME_ERROR_CODE:
            confirmed, entry = await _tool_confirmed_refunds(
                tools,
                order_id=intent.order_id,
                idempotency_key=intent.idempotency_key,
                step_index=next_step_index,
                record_trace=record_trace,
            )
            history.append(entry)
            next_step_index += 1

            if confirmed is None or len(confirmed) > 1:
                return RefundWriteExecutionResult(
                    outcome=_unknown(attempts=attempts, intent=intent, trace_ids=trace_ids),
                    history=tuple(history),
                )
            if confirmed:
                return RefundWriteExecutionResult(
                    outcome=_recovered(
                        confirmed[0],
                        attempts=attempts,
                        intent=intent,
                        trace_ids=trace_ids,
                    ),
                    history=tuple(history),
                )

            # The authority answered and found no refund for this key *yet*. The same key is the
            # safe retry identity; exhausting the budget remains UNKNOWN because the timed-out
            # request may still finish later.
            continue

        if result.retryable and attempts < max_attempts:
            continue

        return RefundWriteExecutionResult(
            outcome=RefundWriteOutcome(
                write_status=WriteStatus.FAILED,
                attempts=attempts,
                idempotency_key=intent.idempotency_key,
                error_code=result.error_code,
                trace_ids=tuple(trace_ids),
            ),
            history=tuple(history),
        )

    return RefundWriteExecutionResult(
        outcome=_unknown(attempts=attempts, intent=intent, trace_ids=trace_ids),
        history=tuple(history),
    )


async def _tool_confirmed_refunds(
    tools: RefundWriteTools,
    *,
    order_id: str,
    idempotency_key: str,
    step_index: int,
    record_trace: TraceSink | None = None,
) -> tuple[list[RefundResult] | None, ToolHistoryEntry]:
    """Return key-scoped refunds, preserving failed-read versus authoritative-empty semantics."""
    result = await tools.get_after_sales_status(
        order_id,
        idempotency_key=idempotency_key,
    )
    history = _history_entry(
        step_index=step_index,
        tool_name="get_after_sales_status",
        result=result,
    )
    report_tool_call(
        record_trace,
        step_index=step_index,
        tool_name="get_after_sales_status",
        envelope=result,
        input_summary={"orderId": order_id},
    )
    if not result.success:
        return None, history

    authoritative = result.data
    if authoritative is None:
        raise ValueError("successful after-sales Tool result is missing data")
    return authoritative.refunds, history


def _history_entry[T](
    *,
    step_index: int,
    tool_name: str,
    result: ToolEnvelope[T],
) -> ToolHistoryEntry:
    return ToolHistoryEntry(
        step_index=step_index,
        tool_name=tool_name,
        success=result.success,
        error_code=result.error_code,
        retryable=result.retryable,
        trace_id=result.trace_id,
    )


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
