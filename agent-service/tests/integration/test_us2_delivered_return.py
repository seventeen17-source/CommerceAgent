"""T037: delivered evidence replaces the refund path with the return path.

US2's claim is a *branching* claim, not a capability claim: the same customer request ("give me a
refund"), landing on an order that is already delivered and still inside its return window, must not
be executed as a refund.

The orchestration below is the honest stand-in for the T041 nodes: eligibility -> the router's
branch -> the return executor -> verification. The assertions that matter are on the **fake Java's
call log**, because "the refund endpoint was never called" is a fact only the server side can
witness, and a test that only checked "a return row was written" would stay green even if the Agent
had also tried to pay.
"""

from __future__ import annotations

from collections import deque
from typing import Any

import httpx
import pytest

from app.agent.execute_write import (
    CREATE_RETURN_ACTION,
    DEFAULT_MAX_ATTEMPTS,
    ReturnWriteOutcome,
    execute_return_write,
    return_write_intent,
    write_may_already_have_committed,
)
from app.agent.routing import Node, route_after_eligibility
from app.agent.state import (
    AgentState,
    EligibilitySnapshot,
    PrincipalContext,
    PrincipalRole,
    VerificationOutcome,
    VerificationStatus,
    WriteIntent,
    WriteOutcome,
    WriteStatus,
)
from app.agent.verify_business_state import verify_return_business_state
from app.clients.auth import AuthContext
from app.clients.commerce_client import CommerceClient
from app.clients.models import EligibilityRequest
from app.tools.commerce_tools import CommerceTools

_AUTH = AuthContext(token="header.payload.signature")  # noqa: S106 - a fake, not a credential
_REASON_CODE = "DELIVERED_RETURN"


class FakeDeliveredJava:
    """The Java API as US2 consumes it: delivered, inside the window, return-only.

    Faithful about the two facts this path depends on:

    * a return row is committed **before** its answer can be lost (``timeout_after_commit``), which
      is exactly the case the Agent cannot distinguish from "nothing was written"; and
    * the refund endpoint exists and is recorded, so "it was never called" is an observable claim
      rather than an assumption.
    """

    ORDER_ID = "order-t037-delivered"
    RETURN_ID = "7c2e4f60-9a1b-4d3e-8f2a-1b2c3d4e5f60"
    RETURN_DEADLINE = "2026-10-13T08:00:00Z"

    def __init__(self) -> None:
        self.allowed_action = "RETURN_REFUND"
        self.calls: list[str] = []
        #: Every idempotency key the return endpoint saw, in order.
        self.return_keys: list[str] = []
        self.returns: dict[str, dict[str, Any]] = {}
        #: Scripted behaviour for the next attempt(s): "ok" or "timeout_after_commit".
        self.return_faults: deque[str] = deque()

    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self._handle)

    def _eligibility_payload(self) -> dict[str, Any]:
        return {
            "eligible": True,
            "allowedAction": self.allowed_action,
            "maxRefundAmount": "199.00",
            "approvalRequired": False,
            "ruleCode": "T037-DELIVERED-RETURN",
            "ruleVersion": 1,
            "reasonCodes": [],
            "evaluatedAt": "2026-10-06T08:00:00Z",
        }

    def _commit(self, key: str) -> None:
        self.returns[key] = {
            "returnRequestId": self.RETURN_ID,
            "status": "CREATED",
            "returnDeadline": self.RETURN_DEADLINE,
        }

    def _handle(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        self.calls.append(f"{request.method} {path}")

        if path == "/api/v1/after-sales/eligibility":
            return httpx.Response(200, json=self._eligibility_payload())

        if path == "/api/v1/returns":
            key = request.headers.get("Idempotency-Key", "")
            self.return_keys.append(key)
            fault = self.return_faults.popleft() if self.return_faults else "ok"
            self._commit(key)
            if fault == "timeout_after_commit":
                # Committed, then the answer was lost -- the case that must never become a second
                # write and must never be reported as "nothing happened".
                raise httpx.ReadTimeout("scripted timeout after commit", request=request)
            return httpx.Response(200, json=self.returns[key])

        if path == "/api/v1/refunds":
            # Reaching this line at all is the failure this test exists to catch.
            return httpx.Response(500, json={"errorCode": "MUST_NOT_BE_CALLED"})

        if path.endswith("/after-sales"):
            key = request.url.params.get("idempotencyKey")
            rows = [self.returns[key]] if key in self.returns else []
            return httpx.Response(200, json={"refunds": [], "returns": rows})

        raise AssertionError(f"unexpected path {path}")

    def wrote_refund(self) -> bool:
        return any(call == "POST /api/v1/refunds" for call in self.calls)


def _client(java: FakeDeliveredJava) -> CommerceClient:
    return CommerceClient(
        base_url="http://commerce.test/api/v1",
        timeout_seconds=5.0,
        transport=java.transport(),
    )


def _state(**overrides: Any) -> AgentState:
    values: dict[str, Any] = {
        "run_id": "1f2e3d4c-5b6a-4978-8a9b-0c1d2e3f4a5b",
        "principal": PrincipalContext(user_id="customer-001", role=PrincipalRole.CUSTOMER),
        "user_request": "This arrived last week and I want my money back.",
    }
    values.update(overrides)
    return AgentState.model_validate(values)


class Persister:
    """The durability seam, as the graph node supplies it."""

    def __init__(self, state: AgentState) -> None:
        self.state = state
        self.saved: list[WriteIntent] = []

    async def __call__(self, intent: WriteIntent, pending: WriteOutcome) -> None:
        assert pending.status is WriteStatus.PENDING
        assert pending.action == CREATE_RETURN_ACTION
        self.saved.append(intent)
        self.state = self.state.model_copy(update={"write_intent": intent, "write": pending})

    def record_outcome(self, outcome: ReturnWriteOutcome) -> None:
        self.state = self.state.model_copy(update={"write": outcome.to_state_outcome()})

    def record_verification(self, verification: VerificationOutcome) -> None:
        self.state = self.state.model_copy(update={"verification": verification})


async def _us2_return_flow(
    *,
    client: CommerceClient,
    java: FakeDeliveredJava,
    persister: Persister,
) -> tuple[Node, ReturnWriteOutcome | None]:
    """Eligibility -> the router's branch -> the return executor -> verification.

    The branch is not decoration: the executor is called only *because* the router chose the return
    node. A regression that sent ``RETURN_REFUND`` back to the refund write would therefore show up
    as "the refund endpoint was called" rather than as a quietly passing assertion.
    """
    decision = (
        await client.check_eligibility(
            _AUTH, EligibilityRequest(order_id=java.ORDER_ID, reason_code=_REASON_CODE)
        )
    ).value
    snapshot = EligibilitySnapshot(
        eligible=decision.eligible,
        allowed_action=decision.allowed_action,
        max_refund_amount=decision.max_refund_amount,
        approval_required=decision.approval_required,
        rule_code=decision.rule_code,
        rule_version=decision.rule_version,
        reason_codes=decision.reason_codes,
    )
    state = persister.state.model_copy(
        update={"resolved_order_id": java.ORDER_ID, "eligibility": snapshot}
    )

    branch = route_after_eligibility(state)
    if branch is not Node.RETURN_WRITE:
        return branch, None

    tools = CommerceTools(client=client, auth=_AUTH)
    intent = return_write_intent(state, order_id=java.ORDER_ID, reason_code=_REASON_CODE)
    execution = await execute_return_write(
        tools=tools,
        intent=intent,
        persist_intent=persister,
        max_attempts=DEFAULT_MAX_ATTEMPTS,
        may_already_have_committed=write_may_already_have_committed(state),
    )
    outcome = execution.outcome
    persister.record_outcome(outcome)

    if not outcome.succeeded:
        return branch, outcome

    verification = await verify_return_business_state(
        tools=tools,
        order_id=java.ORDER_ID,
        idempotency_key=outcome.idempotency_key,
        expected_return_request_id=outcome.resource_id,
    )
    persister.record_verification(verification)
    return branch, outcome


@pytest.mark.asyncio
async def test_delivered_evidence_writes_a_return_and_never_touches_the_refund_endpoint() -> None:
    java = FakeDeliveredJava()
    persister = Persister(_state())

    branch, outcome = await _us2_return_flow(client=_client(java), java=java, persister=persister)

    assert branch is Node.RETURN_WRITE
    assert outcome is not None
    assert outcome.succeeded
    assert not java.wrote_refund(), "a delivered order must not be executed as a refund"
    assert java.return_keys == [outcome.idempotency_key]
    assert len(java.returns) == 1, "exactly one logical return"

    verification = persister.state.verification
    assert verification is not None
    assert verification.status is VerificationStatus.VERIFIED_SUCCESS
    assert verification.resource_id == FakeDeliveredJava.RETURN_ID


@pytest.mark.asyncio
async def test_a_lost_return_answer_is_recovered_from_authority_without_a_second_write() -> None:
    java = FakeDeliveredJava()
    java.return_faults.append("timeout_after_commit")
    persister = Persister(_state())

    branch, outcome = await _us2_return_flow(client=_client(java), java=java, persister=persister)

    assert branch is Node.RETURN_WRITE
    assert outcome is not None
    assert outcome.succeeded and outcome.recovered
    assert len(java.return_keys) == 1, "an unknown outcome must not become a second return"
    assert not java.wrote_refund()
    verification = persister.state.verification
    assert verification is not None
    assert verification.status is VerificationStatus.VERIFIED_SUCCESS


@pytest.mark.asyncio
@pytest.mark.parametrize("action", ["REFUND_ONLY", "MANUAL_REVIEW", "DENY"])
async def test_the_branch_follows_the_decision_and_not_the_agent(action: str) -> None:
    """The router is what differentiates: only a return-granting action reaches the return write."""
    java = FakeDeliveredJava()
    java.allowed_action = action
    persister = Persister(_state())

    branch, outcome = await _us2_return_flow(client=_client(java), java=java, persister=persister)

    assert branch is not Node.RETURN_WRITE
    assert outcome is None
    assert java.return_keys == []
    assert not java.wrote_refund()
