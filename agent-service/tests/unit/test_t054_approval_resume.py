from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

import pytest
from fastapi import HTTPException

from app.agent.graph import GraphUpdate, build_graph, _entry_node
from app.agent.routing import Decision, Node, route_after_eligibility
from app.agent.state import AgentState, ApprovalSnapshot, RunStatus, advance
from app.api.runs import ResumeRunRequest, _verify_waiting_approval
from app.clients.auth import AuthContext
from app.clients.commerce_client import CommerceCall
from app.clients.models import ApprovalResult
from app.security.dependencies import AuthenticatedCall
from app.trace.checkpoint import RunRecord


RUN_ID = UUID("54000000-0000-4000-8000-000000000001")


def waiting_state() -> AgentState:
    return AgentState.model_validate(
        {
            "run_id": str(RUN_ID),
            "principal": {"user_id": "customer-001", "role": "CUSTOMER"},
            "user_request": "高风险退款",
            "intent": "REFUND_REQUEST",
            "resolved_order_id": "order-001",
            "eligibility": {
                "eligible": True,
                "allowed_action": "REFUND_ONLY",
                "max_refund_amount": "399.00",
                "approval_required": True,
                "rule_code": "HIGH_VALUE_REFUND",
                "rule_version": 1,
                "reason_codes": ["APPROVAL_REQUIRED_BY_AMOUNT"],
            },
            "approval": {"approval_request_id": "approval-001", "status": "PENDING"},
            "status": "WAITING_APPROVAL",
        }
    )


def waiting_record() -> RunRecord:
    state = waiting_state()
    return RunRecord(
        run_id=RUN_ID,
        user_id="customer-001",
        status=RunStatus.WAITING_APPROVAL,
        version=1,
        intent=state.intent,
        resolved_order_id=state.resolved_order_id,
        current_node=Node.WAITING_APPROVAL.value,
        next_action=None,
        step_count=state.step_count,
        retry_count=state.retry_count,
        state=state,
        model_name="test-model",
        prompt_version="t054-test",
        started_at=datetime(2026, 10, 8, tzinfo=UTC),
    )


def approval(**overrides: Any) -> ApprovalResult:
    payload: dict[str, Any] = {
        "approvalRequestId": "approval-001",
        "runId": str(RUN_ID),
        "orderId": "order-001",
        "actionType": "REFUND_ONLY",
        "amount": "399.00",
        "riskReason": "APPROVAL_REQUIRED_BY_AMOUNT",
        "status": "APPROVED",
        "decidedBy": "approver-001",
        "decidedAt": "2026-10-08T08:05:00Z",
        "requestedAt": "2026-10-08T08:00:00Z",
        "expiresAt": "2026-10-09T08:00:00Z",
    }
    payload.update(overrides)
    return ApprovalResult.model_validate(payload)


class ApprovalClient:
    def __init__(self, result: ApprovalResult) -> None:
        self.result = result
        self.calls: list[str] = []

    async def get_approval(self, auth: AuthContext, approval_request_id: str) -> CommerceCall[ApprovalResult]:
        self.calls.append(approval_request_id)
        return CommerceCall(value=self.result, trace_id="trace-approval-001", status_code=200)


class CheckpointStore:
    def __init__(self, record: RunRecord) -> None:
        self.record = record
        self.saved_state: AgentState | None = None

    def checkpoint_state(self, run_id: UUID, **kwargs: Any) -> RunRecord:
        self.saved_state = kwargs["state"]
        self.record = self.record.model_copy(
            update={
                "version": self.record.version + 1,
                "state": self.saved_state,
                "current_node": kwargs["current_node"],
                "next_action": kwargs["next_action"],
            }
        )
        return self.record


def authenticated_call() -> AuthenticatedCall:
    state = waiting_state()
    return AuthenticatedCall(
        auth=AuthContext(token="header.payload.signature"),  # noqa: S106 -- fixture only
        principal=state.principal,
    )


@pytest.mark.asyncio
async def test_exact_approved_binding_is_checkpointed_as_verified_before_resume() -> None:
    record = waiting_record()
    store = CheckpointStore(record)
    client = ApprovalClient(approval())

    refreshed = await _verify_waiting_approval(
        store=store,  # type: ignore[arg-type]
        record=record,
        client=client,  # type: ignore[arg-type]
        call=authenticated_call(),
        body=ResumeRunRequest(approvalRequestId="approval-001"),
    )

    state = refreshed.to_state()
    assert state is not None
    assert state.approval is not None
    assert state.approval.binding_verified is True
    assert state.approval.status == "APPROVED"
    assert state.approval.run_id == RUN_ID
    assert state.approval.amount == Decimal("399.00")
    assert client.calls == ["approval-001"]

    # A fresh Java eligibility snapshot still has to match the verified approval before a write.
    assert route_after_eligibility(state) is Node.REFUND_WRITE


@pytest.mark.asyncio
async def test_caller_cannot_swap_the_checkpointed_approval_id() -> None:
    record = waiting_record()
    store = CheckpointStore(record)
    client = ApprovalClient(approval())

    with pytest.raises(HTTPException) as caught:
        await _verify_waiting_approval(
            store=store,  # type: ignore[arg-type]
            record=record,
            client=client,  # type: ignore[arg-type]
            call=authenticated_call(),
            body=ResumeRunRequest(approvalRequestId="approval-from-another-run"),
        )

    assert caught.value.status_code == 409
    assert caught.value.detail == "APPROVAL_REFERENCE_MISMATCH"
    assert client.calls == []


@pytest.mark.asyncio
async def test_cross_run_authoritative_approval_is_rejected() -> None:
    record = waiting_record()
    store = CheckpointStore(record)
    client = ApprovalClient(approval(runId="54000000-0000-4000-8000-000000000099"))

    with pytest.raises(HTTPException) as caught:
        await _verify_waiting_approval(
            store=store,  # type: ignore[arg-type]
            record=record,
            client=client,  # type: ignore[arg-type]
            call=authenticated_call(),
            body=None,
        )

    assert caught.value.status_code == 409
    assert caught.value.detail == "APPROVAL_BINDING_MISMATCH"
    assert store.saved_state is None


@pytest.mark.asyncio
async def test_pending_approval_does_not_claim_or_advance_the_run() -> None:
    record = waiting_record()
    store = CheckpointStore(record)
    client = ApprovalClient(approval(status="PENDING", decidedBy=None, decidedAt=None))

    with pytest.raises(HTTPException) as caught:
        await _verify_waiting_approval(
            store=store,  # type: ignore[arg-type]
            record=record,
            client=client,  # type: ignore[arg-type]
            call=authenticated_call(),
            body=None,
        )

    assert caught.value.status_code == 409
    assert caught.value.detail == "APPROVAL_PENDING"
    assert store.saved_state is None


def test_verified_approval_resume_enters_fresh_eligibility_without_reinterpreting() -> None:
    """Only a restored Java-verified binding chooses the short HITL path."""
    state = waiting_state()
    initial = {"state": state}
    assert _entry_node(initial) is Node.UNDERSTAND

    verified = advance(
        state,
        status=RunStatus.RUNNING,
        step_count=7,
        approval=ApprovalSnapshot(
            approval_request_id="approval-001",
            status="APPROVED",
            run_id=RUN_ID,
            order_id="order-001",
            action_type="REFUND_ONLY",
            amount=Decimal("399.00"),
            binding_verified=True,
        ),
    )
    assert _entry_node({"state": verified}) is Node.CHECK_ELIGIBILITY
    assert _entry_node({"state": advance(verified, step_count=12)}) is Node.SAFE_STOP


def test_unverified_or_unresolved_approval_cannot_select_short_resume() -> None:
    state = waiting_state()
    approval = ApprovalSnapshot(
        approval_request_id="approval-001",
        status="APPROVED",
        run_id=RUN_ID,
        order_id="order-001",
        action_type="REFUND_ONLY",
        amount=Decimal("399.00"),
        binding_verified=False,
    )
    assert _entry_node({"state": advance(state, status=RunStatus.RUNNING, approval=approval)}) is Node.UNDERSTAND
    assert _entry_node({
        "state": advance(
            state,
            status=RunStatus.RUNNING,
            resolved_order_id=None,
            approval=approval.model_copy(update={"binding_verified": True}),
        )
    }) is Node.UNDERSTAND


@pytest.mark.asyncio
async def test_compiled_resume_graph_rechecks_eligibility_before_write() -> None:
    """The real LangGraph START edge must not call model/order/evidence on HITL resume."""
    trace: list[Node] = []

    async def unexpected(graph: Any) -> GraphUpdate:
        raise AssertionError("verified resume must not re-run model/order/evidence")

    async def check_eligibility(graph: Any) -> GraphUpdate:
        trace.append(Node.CHECK_ELIGIBILITY)
        state = advance(graph["state"], step_count=graph["state"].step_count + 1)
        return {"state": state, "decision": Decision()}

    async def refund_write(graph: Any) -> GraphUpdate:
        trace.append(Node.REFUND_WRITE)
        state = advance(
            graph["state"],
            step_count=graph["state"].step_count + 1,
            write_intent={
                "action": "CREATE_REFUND_REQUEST",
                "target_id": "order-001",
                "idempotency_key": "37087fe4af524f36b0ba02dd4e4d55ef",
                "request_fingerprint": "a" * 64,
            },
            write={"status": "SUCCEEDED", "resource_id": "refund-001"},
        )
        return {"state": state, "decision": Decision()}

    async def verify(graph: Any) -> GraphUpdate:
        trace.append(Node.VERIFY)
        state = advance(
            graph["state"],
            step_count=graph["state"].step_count + 1,
            verification={"status": "VERIFIED_SUCCESS", "resource_id": "refund-001"},
        )
        return {"state": state, "decision": Decision()}

    async def finalize(graph: Any) -> GraphUpdate:
        trace.append(Node.FINALIZE)
        return {"state": graph["state"], "decision": Decision()}

    nodes = {node: unexpected for node in Node}
    nodes[Node.CHECK_ELIGIBILITY] = check_eligibility
    nodes[Node.REFUND_WRITE] = refund_write
    nodes[Node.VERIFY] = verify
    nodes[Node.FINALIZE] = finalize

    base = waiting_state()
    verified = advance(
        base,
        status=RunStatus.RUNNING,
        step_count=7,
        approval=ApprovalSnapshot(
            approval_request_id="approval-001",
            status="APPROVED",
            run_id=RUN_ID,
            order_id="order-001",
            action_type="REFUND_ONLY",
            amount=Decimal("399.00"),
            binding_verified=True,
        ),
    )
    finished = await build_graph(nodes).ainvoke({
        "state": verified, "decision": Decision(), "understood": None, "resolution": None
    })
    assert trace == [
        Node.CHECK_ELIGIBILITY, Node.REFUND_WRITE, Node.VERIFY, Node.FINALIZE
    ]
    assert finished["state"].verification.status.value == "VERIFIED_SUCCESS"
    assert finished["state"].step_count == 10


def test_fresh_eligibility_drift_after_resume_safe_stops_instead_of_writing() -> None:
    base = waiting_state()
    eligibility = base.eligibility
    assert eligibility is not None
    checked = advance(
        base,
        approval=ApprovalSnapshot(
            approval_request_id="approval-001",
            status="APPROVED",
            run_id=RUN_ID,
            order_id="order-001",
            action_type="REFUND_ONLY",
            amount=Decimal("399.00"),
            binding_verified=True,
        ),
        eligibility=eligibility.model_copy(update={"max_refund_amount": Decimal("400.00")}),
        status=RunStatus.RUNNING,
    )
    assert route_after_eligibility(checked) is Node.SAFE_STOP
