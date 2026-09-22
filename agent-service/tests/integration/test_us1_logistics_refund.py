"""T022: the US1 stalled-logistics refund path as the Agent actually walks it.

Two scenarios are pinned here, and both are about money that must not be created twice:

1. **Stalled-logistics happy path** -- one order, 120 h without a logistics event, eligibility says
   ``REFUND_ONLY``; the write produces exactly one refund and the result is verified against
   authoritative state rather than against the write response.
2. **Unknown-write recovery** -- a write whose answer never arrived. The outcome is *unknown*, not
   failed: Java may have committed. The Agent must read authoritative state before repeating
   anything, must reuse the same idempotency key if it does repeat, and must escalate (never claim
   success or failure) when it cannot establish the truth.

Why the Java side is scripted rather than real
----------------------------------------------
Java is an external authority; its *contract* is what this layer consumes, and
``httpx.MockTransport`` lets a test do something a real server cannot be asked to do on demand:
commit the refund and then throw the answer away. That is the only way to test unknown-outcome
recovery at all. Per the T018/T016 precedent: the store is the thing under test and gets a real
database; Java is simulated against its published contract. Nothing here needs PostgreSQL, so this
suite runs anywhere.

The ``_us1_refund_flow`` helper below stands in for the T030/T032 graph nodes: it spells out the
intended order of business steps (order -> logistics -> eligibility -> guarded write -> verify) so
the refund path is exercised end to end before LangGraph is wired up. It is deliberately not a
graph.
"""

from __future__ import annotations

import json
from collections import deque
from typing import Any

import httpx
import pytest

from app.agent.execute_write import (
    CREATE_REFUND_ACTION,
    DEFAULT_MAX_ATTEMPTS,
    INTENT_NOT_DURABLE_ERROR_CODE,
    UNKNOWN_OUTCOME_ERROR_CODE,
    RefundWriteIntent,
    RefundWriteOutcome,
    WriteIntentConflictError,
    create_refund,
    refund_write_intent,
    write_may_already_have_committed,
)
from app.agent.state import (
    AgentState,
    PrincipalContext,
    PrincipalRole,
    WriteIntent,
    WriteOutcome,
    WriteStatus,
)
from app.clients.auth import AuthContext
from app.clients.commerce_client import CommerceClient
from app.clients.models import EligibilityRequest

#: A placeholder, not a credential -- same convention as the other client tests: the name avoids a
#: "token"/"password" root so ruff's hardcoded-secret rule (S105/S106) stays enabled for real code.
_FAKE_JWT = "header.payload.signature"
_AUTH = AuthContext(token=_FAKE_JWT)

_REASON_CODE = "STALLED_LOGISTICS"


# ---------------------------------------------------------------------------------------------
# A stateful, scriptable stand-in for the Java business API
# ---------------------------------------------------------------------------------------------


class FakeJava:
    """The Java API as this layer consumes it, with scriptable per-attempt failures.

    It is faithful about the two facts the recovery policy depends on:

    * a refund is committed **before** its answer can be lost (``timeout_after_commit``), which is
      exactly the case an Agent cannot distinguish from "nothing happened";
    * a second key for an already-refunded order is refused with ``DUPLICATE_AFTER_SALES``, so a
      "retry" that switched keys cannot quietly succeed.
    """

    ORDER_ID = "order-t022"
    REFUND_ID = "3f1a9d10-4c2b-4a6e-9c3d-6f0b1a2c3d4e"
    TOTAL = "199.00"

    def __init__(self) -> None:
        self.order_status = "SHIPPED"
        self.after_sales_status: str | None = None
        self.stalled_hours: int | None = 120
        self.eligible = True
        self.allowed_action = "REFUND_ONLY"
        self.approval_required = False
        #: Scripted behaviour for the next write attempt(s): "ok", "timeout_before_commit",
        #: "timeout_after_commit", "duplicate", "unavailable".
        self.write_faults: deque[str] = deque()
        self.after_sales_read_fails = False
        self.after_sales_omit_refunds = False
        #: Every idempotency key the endpoint saw, in order -- proof that a retry reused it.
        self.write_keys: list[str] = []
        self.calls: list[str] = []
        #: Shared with the test's persister so ordering (persist before write) can be asserted.
        self.events: list[str] = []
        self.refunds: dict[str, dict[str, Any]] = {}

    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self._handle)

    def write_attempts(self) -> int:
        return len(self.write_keys)

    def commit_out_of_band(self, key: str, amount: str | None = None) -> None:
        """Commit a refund as if a previous process had done it (no HTTP involved)."""
        self.refunds[key] = {
            "refundRequestId": self.REFUND_ID,
            "status": "CREATED",
            "acceptedAmount": amount or self.TOTAL,
        }
        self.after_sales_status = "REFUND_REQUESTED"

    # ---- routing ---------------------------------------------------------------------------

    def _handle(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        self.calls.append(f"{request.method} {path}")
        order_path = f"/api/v1/orders/{self.ORDER_ID}"
        if request.method == "GET" and path == order_path:
            return httpx.Response(200, json=self._order())
        if request.method == "GET" and path == f"{order_path}/logistics":
            return httpx.Response(200, json=self._logistics())
        if request.method == "POST" and path == "/api/v1/after-sales/eligibility":
            return httpx.Response(200, json=self._decision())
        if request.method == "GET" and path == f"{order_path}/after-sales":
            if self.after_sales_read_fails:
                # A dependency failure on the *read* half: the outcome stays unknown.
                return self._error(503, "DEPENDENCY_UNAVAILABLE", retryable=True)
            return httpx.Response(200, json=self._after_sales(request))
        if request.method == "POST" and path == "/api/v1/refunds":
            return self._write(request)
        return self._error(404, "ORDER_NOT_FOUND")

    def _write(self, request: httpx.Request) -> httpx.Response:
        key = request.headers.get("Idempotency-Key")
        if key is None:
            # The contract makes this header required: a write without it is not idempotent.
            return self._error(400, "INVALID_PARAMETER")
        self.write_keys.append(key)
        self.events.append(f"write:{key}")

        fault = self.write_faults.popleft() if self.write_faults else "ok"
        if fault == "timeout_before_commit":
            raise httpx.ReadTimeout("no answer arrived", request=request)
        if fault == "timeout_after_commit":
            if self._commit(request, key) is None:
                return self._error(409, "DUPLICATE_AFTER_SALES")
            raise httpx.ReadTimeout("no answer arrived", request=request)
        if fault == "duplicate":
            return self._error(409, "DUPLICATE_AFTER_SALES")
        if fault == "unavailable":
            return self._error(503, "LOGISTICS_UNAVAILABLE", retryable=True)

        replay = self.refunds.get(key)
        if replay is not None:
            return httpx.Response(200, json=replay)
        committed = self._commit(request, key)
        if committed is None:
            return self._error(409, "DUPLICATE_AFTER_SALES")
        return httpx.Response(200, json=committed)

    # ---- business state --------------------------------------------------------------------

    def _commit(self, request: httpx.Request, key: str) -> dict[str, Any] | None:
        """Commit the refund, or return ``None`` when the order already has a live one.

        A live refund under a *different* key is the duplicate case Java refuses: that is what makes
        "retry with a new key" observably wrong rather than silently expensive.
        """
        if self.refunds:
            return None
        payload = json.loads(request.content)
        refund = {
            "refundRequestId": self.REFUND_ID,
            "status": "CREATED",
            "acceptedAmount": payload.get("requestedAmount") or self.TOTAL,
        }
        self.refunds[key] = refund
        self.after_sales_status = "REFUND_REQUESTED"
        return refund

    def _order(self) -> dict[str, Any]:
        return {
            "orderId": self.ORDER_ID,
            "status": self.order_status,
            "totalAmount": self.TOTAL,
            "currency": "USD",
            "afterSalesStatus": self.after_sales_status,
            "items": [
                {
                    "productId": "product-t022",
                    "productName": "Wireless Headphones",
                    "productCategory": "ELECTRONICS",
                    "quantity": 1,
                }
            ],
        }

    def _logistics(self) -> dict[str, Any]:
        return {
            "status": "IN_TRANSIT",
            "signed": False,
            "lastMeaningfulEventAt": "2026-09-17T08:00:00Z",
            "stalledHours": self.stalled_hours,
        }

    def _decision(self) -> dict[str, Any]:
        return {
            "eligible": self.eligible,
            "allowedAction": self.allowed_action,
            "maxRefundAmount": self.TOTAL if self.eligible else None,
            "approvalRequired": self.approval_required,
            "ruleCode": "T022-STALLED-REFUND",
            "ruleVersion": 1,
            "reasonCodes": ["STALL_THRESHOLD_MET"],
        }

    def _after_sales(self, request: httpx.Request) -> dict[str, Any]:
        key = request.url.params.get("idempotencyKey")
        if key is None:
            refunds = list(self.refunds.values())
        else:
            matched = self.refunds.get(key)
            refunds = [] if matched is None else [matched]
        payload: dict[str, Any] = {"refunds": refunds, "returns": []}
        if self.after_sales_omit_refunds:
            payload.pop("refunds")
        return payload

    @staticmethod
    def _error(code: int, error_code: str, *, retryable: bool = False) -> httpx.Response:
        return httpx.Response(
            code,
            json={
                "errorCode": error_code,
                "message": error_code,
                "retryable": retryable,
                "traceId": "trace-from-java-0001",
            },
            headers={"X-Trace-Id": "trace-from-java-0001"},
        )


# ---------------------------------------------------------------------------------------------
# Fixtures and helpers
# ---------------------------------------------------------------------------------------------


def _client(java: FakeJava) -> CommerceClient:
    return CommerceClient(
        base_url="http://commerce.test/api/v1",
        timeout_seconds=5.0,
        transport=java.transport(),
    )


def _state(**overrides: Any) -> AgentState:
    values: dict[str, Any] = {
        "run_id": "9c2f5b6e-1a2b-4c3d-8e4f-5a6b7c8d9e0f",
        "principal": PrincipalContext(user_id="customer-001", role=PrincipalRole.CUSTOMER),
        "user_request": "My parcel has not moved for days. I want a refund.",
    }
    values.update(overrides)
    return AgentState.model_validate(values)


def _persisted_refund_intent(
    key: str,
    *,
    reason_code: str = _REASON_CODE,
) -> WriteIntent:
    """Build a durable intent with the same fingerprint logic production uses."""
    generated = refund_write_intent(
        _state(),
        order_id=FakeJava.ORDER_ID,
        reason_code=reason_code,
        requested_amount=None,
    ).to_state_intent()
    return generated.model_copy(update={"idempotency_key": key})


class Persister:
    """The durability seam, as the graph node will supply it.

    It records the write intent into the run's state (in production that state is checkpointed in
    the same step) and appends to a shared event log, which is how the test proves the key was
    durable *before* the request left the process.

    It also **owns** the state: the persister is the only object that sees both the intent (written
    before the attempt) and the outcome (written after it). A helper keeping a private copy of the
    state would assert against a state the write path never touched.
    """

    def __init__(self, state: AgentState, events: list[str] | None = None) -> None:
        self.state = state
        self.events = events if events is not None else []
        self.saved: list[WriteIntent] = []

    async def __call__(self, intent: WriteIntent, pending: WriteOutcome) -> None:
        assert pending.status is WriteStatus.PENDING
        self.events.append(f"persist:{intent.idempotency_key}")
        self.saved.append(intent)
        self.state = self.state.model_copy(
            update={"write_intent": intent, "write": pending}
        )

    def record_outcome(self, outcome: RefundWriteOutcome) -> None:
        self.state = self.state.model_copy(update={"write": outcome.to_state_outcome()})


async def _us1_refund_flow(
    *,
    client: CommerceClient,
    java: FakeJava,
    persister: Persister,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
) -> RefundWriteOutcome | None:
    """Order -> logistics -> eligibility -> guarded write -> verify, in the intended order.

    Stands in for the T030/T032 nodes. The guard matters: a decision that does not grant
    ``REFUND_ONLY`` must never reach the write, which is why the write lives inside the branch
    rather than after it.
    """
    await client.get_order(_AUTH, java.ORDER_ID)
    await client.get_logistics(_AUTH, java.ORDER_ID)
    decision = (
        await client.check_eligibility(
            _AUTH, EligibilityRequest(order_id=java.ORDER_ID, reason_code=_REASON_CODE)
        )
    ).value

    if (
        not decision.eligible
        or decision.allowed_action != "REFUND_ONLY"
        or decision.approval_required
    ):
        return None

    intent = refund_write_intent(
        persister.state, order_id=java.ORDER_ID, reason_code=_REASON_CODE, requested_amount=None
    )
    outcome = await create_refund(
        client=client,
        auth=_AUTH,
        intent=intent,
        persist_intent=persister,
        max_attempts=max_attempts,
        may_already_have_committed=write_may_already_have_committed(persister.state),
    )
    persister.record_outcome(outcome)

    if not outcome.succeeded:
        return outcome

    # Post-write verification: the authoritative read, not the write response, is the evidence.
    verified = (await client.get_after_sales_status(_AUTH, java.ORDER_ID)).value.refunds
    assert [refund.refund_request_id for refund in verified] == [outcome.resource_id]
    return outcome


# ---------------------------------------------------------------------------------------------
# Scenario 1: the stalled-logistics happy path
# ---------------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_stalled_logistics_produces_exactly_one_verified_refund() -> None:
    java = FakeJava()
    persister = Persister(_state())

    outcome = await _us1_refund_flow(client=_client(java), java=java, persister=persister)

    assert outcome is not None
    assert outcome.succeeded
    assert outcome.recovered is False, "the answer arrived, so this is not a recovery"
    assert outcome.attempts == 1
    assert outcome.resource_id == FakeJava.REFUND_ID
    assert java.write_attempts() == 1, "one logical refund means one write attempt, not two"
    assert java.after_sales_status == "REFUND_REQUESTED"

    # The durable state carries the key that actually identified the write.
    state = persister.state
    assert state.write_intent is not None
    assert state.write_intent.target_id == FakeJava.ORDER_ID
    assert state.write_intent.idempotency_key == java.write_keys[0]
    assert state.write.status is WriteStatus.SUCCEEDED
    assert state.write.resource_id == FakeJava.REFUND_ID


@pytest.mark.asyncio
async def test_the_idempotency_key_is_durable_before_the_request_is_sent() -> None:
    """The ordering *is* the safety property.

    A key that is only remembered after the request leaves is worthless: if the process dies in
    between, the retry is a new logical write and Java creates a second refund.
    """
    java = FakeJava()
    persister = Persister(_state(), events=java.events)

    await _us1_refund_flow(client=_client(java), java=java, persister=persister)

    assert len(java.events) == 2, java.events
    persist_event, write_event = java.events
    assert persist_event.startswith("persist:")
    assert write_event.startswith("write:")
    assert persist_event.split(":", 1)[1] == write_event.split(":", 1)[1], (
        "the key that was persisted must be the key that was sent"
    )


@pytest.mark.asyncio
async def test_a_non_eligible_decision_never_reaches_the_write() -> None:
    java = FakeJava()
    java.eligible = False
    java.allowed_action = "DENY"
    persister = Persister(_state())

    outcome = await _us1_refund_flow(client=_client(java), java=java, persister=persister)

    assert outcome is None
    assert java.write_attempts() == 0, "no eligibility, no money"
    assert persister.state.write_intent is None, (
        "nothing was sent, so there is no intent to recover"
    )


# ---------------------------------------------------------------------------------------------
# Scenario 2: unknown-write recovery
# ---------------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_lost_response_is_recovered_from_authoritative_state_without_rewriting() -> None:
    """Java committed; the answer never arrived.

    The only truthful conclusion is "it is there", and it must be reached **without** sending a
    second write -- that retry would have been refused as a duplicate, and reporting a failure
    would have told the user they were not refunded while the order says otherwise.
    """
    java = FakeJava()
    java.write_faults.append("timeout_after_commit")
    persister = Persister(_state())

    outcome = await _us1_refund_flow(client=_client(java), java=java, persister=persister)

    assert outcome is not None
    assert outcome.succeeded
    assert outcome.recovered is True, "authoritative state, not a response, established the outcome"
    assert outcome.resource_id == FakeJava.REFUND_ID
    assert java.write_attempts() == 1, "a recovery must not send another write"
    assert any(call.endswith("/after-sales") for call in java.calls)


@pytest.mark.asyncio
async def test_a_timeout_before_commit_retries_with_the_same_key() -> None:
    """The first attempt really did not commit, so a retry is safe -- with the *same* key.

    A new key would be a second logical write and Java would refuse it as a duplicate, so the test
    asserts the key stayed identical rather than merely that a retry happened.
    """
    java = FakeJava()
    java.write_faults.append("timeout_before_commit")
    persister = Persister(_state())

    outcome = await _us1_refund_flow(client=_client(java), java=java, persister=persister)

    assert outcome is not None
    assert outcome.succeeded
    assert outcome.attempts == 2
    assert outcome.recovered is False, "the retry got a real answer"
    assert java.write_attempts() == 2
    assert len(set(java.write_keys)) == 1, f"the retry switched keys: {java.write_keys}"
    assert len(java.refunds) == 1


@pytest.mark.asyncio
async def test_a_resumed_run_reuses_the_persisted_key_and_checks_state_first() -> None:
    """Resume after a crash: the persisted intent is what makes this safe.

    The run is reconstructed from persisted state (intent + an unresolved outcome) while the refund
    is already committed in Java. A correct resume sends **nothing** and reuses the stored key.
    """
    java = FakeJava()
    java.commit_out_of_band("key-from-the-previous-process")
    persister = Persister(
        _state(
            write=WriteOutcome(status=WriteStatus.UNKNOWN, action=CREATE_REFUND_ACTION),
            write_intent=_persisted_refund_intent("key-from-the-previous-process"),
        )
    )
    assert write_may_already_have_committed(persister.state) is True

    outcome = await _us1_refund_flow(client=_client(java), java=java, persister=persister)

    assert outcome is not None and outcome.succeeded and outcome.recovered is True
    assert outcome.idempotency_key == "key-from-the-previous-process"
    assert java.write_attempts() == 0, (
        "a resumed run must not re-send a write it cannot account for"
    )


@pytest.mark.asyncio
async def test_a_resumed_run_with_nothing_committed_writes_with_the_persisted_key() -> None:
    """The other half of resume: Java has no refund, so the original attempt truly did not land."""
    java = FakeJava()
    persister = Persister(
        _state(
            write=WriteOutcome(status=WriteStatus.UNKNOWN, action=CREATE_REFUND_ACTION),
            write_intent=_persisted_refund_intent("key-from-the-previous-process"),
        )
    )

    outcome = await _us1_refund_flow(client=_client(java), java=java, persister=persister)

    assert outcome is not None and outcome.succeeded and outcome.recovered is False
    assert java.write_keys == ["key-from-the-previous-process"]


@pytest.mark.asyncio
async def test_an_unconfirmed_state_read_stops_instead_of_guessing() -> None:
    """Write outcome unknown, and the read that settles it also fails: escalate, do not retry."""
    java = FakeJava()
    java.write_faults.append("timeout_before_commit")
    java.after_sales_read_fails = True
    persister = Persister(_state())

    outcome = await _us1_refund_flow(client=_client(java), java=java, persister=persister)

    assert outcome is not None
    assert outcome.write_status is WriteStatus.UNKNOWN
    assert outcome.error_code == UNKNOWN_OUTCOME_ERROR_CODE
    assert outcome.succeeded is False
    assert java.write_attempts() == 1, (
        "retrying without knowing the outcome is a guess, not a policy"
    )


@pytest.mark.asyncio
async def test_the_retry_budget_is_finite_and_never_switches_keys() -> None:
    """Every attempt loses its answer; the authoritative read keeps saying "no refund yet".

    "Not committed yet" is not "never will be" -- the timed-out request may still finish. So the
    terminal state is UNKNOWN (escalate), never FAILED, and the budget is what stops the loop.
    """
    java = FakeJava()
    java.write_faults.extend(["timeout_before_commit", "timeout_before_commit"])
    persister = Persister(_state())

    outcome = await _us1_refund_flow(
        client=_client(java), java=java, persister=persister, max_attempts=2
    )

    assert outcome is not None
    assert outcome.write_status is WriteStatus.UNKNOWN
    assert outcome.error_code == UNKNOWN_OUTCOME_ERROR_CODE
    assert outcome.attempts == 2
    assert java.write_attempts() == 2, "the budget must be finite"
    assert len(set(java.write_keys)) == 1, (
        f"budget exhaustion must not mint keys: {java.write_keys}"
    )


@pytest.mark.asyncio
async def test_a_different_refund_on_the_same_order_is_not_misattributed_to_this_key() -> None:
    """Another logical refund is not proof that this timed-out key committed."""
    java = FakeJava()
    java.commit_out_of_band("some-other-logical-write")
    persister = Persister(
        _state(
            write=WriteOutcome(status=WriteStatus.UNKNOWN, action=CREATE_REFUND_ACTION),
            write_intent=_persisted_refund_intent("key-from-the-previous-process"),
        )
    )

    outcome = await _us1_refund_flow(client=_client(java), java=java, persister=persister)

    assert outcome is not None
    assert outcome.write_status is WriteStatus.FAILED
    assert outcome.error_code == "DUPLICATE_AFTER_SALES"
    assert outcome.recovered is False
    assert java.write_keys == ["key-from-the-previous-process"]


@pytest.mark.asyncio
async def test_missing_refunds_field_keeps_the_write_unknown_instead_of_licensing_retry() -> None:
    """Missing evidence is not an authoritative empty list."""
    java = FakeJava()
    java.write_faults.append("timeout_before_commit")
    java.after_sales_omit_refunds = True
    persister = Persister(_state())

    outcome = await _us1_refund_flow(client=_client(java), java=java, persister=persister)

    assert outcome is not None
    assert outcome.write_status is WriteStatus.UNKNOWN
    assert outcome.error_code == UNKNOWN_OUTCOME_ERROR_CODE
    assert java.write_attempts() == 1


def test_a_resumed_key_cannot_be_rebound_to_a_changed_payload() -> None:
    """The durable key and the durable logical request are one identity."""
    state = _state(
        write=WriteOutcome(status=WriteStatus.UNKNOWN, action=CREATE_REFUND_ACTION),
        write_intent=_persisted_refund_intent("key-from-the-previous-process"),
    )

    with pytest.raises(WriteIntentConflictError):
        refund_write_intent(
            state,
            order_id=FakeJava.ORDER_ID,
            reason_code="A_DIFFERENT_REASON",
            requested_amount=None,
        )


@pytest.mark.asyncio
async def test_a_duplicate_answer_is_terminal_and_never_retried() -> None:
    java = FakeJava()
    java.write_faults.append("duplicate")
    persister = Persister(_state())

    outcome = await _us1_refund_flow(client=_client(java), java=java, persister=persister)

    assert outcome is not None
    assert outcome.write_status is WriteStatus.FAILED
    assert outcome.error_code == "DUPLICATE_AFTER_SALES"
    assert outcome.recovered is False
    assert java.write_attempts() == 1, "an authoritative refusal is not a transient failure"


@pytest.mark.asyncio
async def test_a_retryable_backend_error_is_retried_with_the_same_key() -> None:
    java = FakeJava()
    java.write_faults.append("unavailable")
    persister = Persister(_state())

    outcome = await _us1_refund_flow(client=_client(java), java=java, persister=persister)

    assert outcome is not None and outcome.succeeded
    assert java.write_attempts() == 2
    assert len(set(java.write_keys)) == 1


@pytest.mark.asyncio
async def test_a_write_without_a_durable_intent_is_never_sent() -> None:
    """If the key cannot be made durable, the money never moves.

    The alternative -- send first and hope the key survives -- trades a local persistence failure
    for a possible duplicate refund, which is the wrong way round.
    """
    java = FakeJava()
    state = _state()

    async def failing_persister(intent: WriteIntent, pending: WriteOutcome) -> None:
        raise RuntimeError("checkpoint store unavailable")

    outcome = await create_refund(
        client=_client(java),
        auth=_AUTH,
        intent=refund_write_intent(state, order_id=FakeJava.ORDER_ID, reason_code=_REASON_CODE),
        persist_intent=failing_persister,
    )

    assert outcome.write_status is WriteStatus.FAILED
    assert outcome.error_code == INTENT_NOT_DURABLE_ERROR_CODE
    assert outcome.attempts == 0
    assert java.write_attempts() == 0, "no durable key, no write"


@pytest.mark.asyncio
async def test_the_retry_budget_cannot_be_configured_without_a_bound() -> None:
    """A configuration mistake must not turn the write path into an unbounded loop (FR-007)."""
    intent = RefundWriteIntent(
        run_id="9c2f5b6e-1a2b-4c3d-8e4f-5a6b7c8d9e0f",
        order_id=FakeJava.ORDER_ID,
        reason_code=_REASON_CODE,
        idempotency_key="0123456789abcdef0123456789abcdef",
    )

    async def persister(value: WriteIntent, pending: WriteOutcome) -> None:
        return None

    with pytest.raises(ValueError, match="max_attempts"):
        await create_refund(
            client=_client(FakeJava()),
            auth=_AUTH,
            intent=intent,
            persist_intent=persister,
            max_attempts=99,
        )
