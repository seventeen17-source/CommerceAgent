from __future__ import annotations

from decimal import Decimal
from typing import Any
from uuid import UUID

import pytest

from app.agent.nodes import GraphDeps, build_approval_nodes, build_lifecycle_nodes
from app.agent.routing import Node, SafeStopReason, route_after_request_approval
from app.agent.state import AgentState, RunStatus, WriteIntent, WriteOutcome
from app.clients.models import ApprovalResult
from app.tools.models import ToolEnvelope
from app.tools.registry import ToolRegistry

RUN_ID = UUID("52000000-0000-4000-8000-000000000001")


def high_risk_state() -> AgentState:
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
        }
    )


def approval_result(**overrides: Any) -> ApprovalResult:
    payload: dict[str, Any] = {
        "approvalRequestId": "approval-001",
        "runId": str(RUN_ID),
        "orderId": "order-001",
        "actionType": "REFUND_ONLY",
        "amount": "399.00",
        "riskReason": "APPROVAL_REQUIRED_BY_AMOUNT",
        "status": "PENDING",
        "decidedBy": None,
        "decidedAt": None,
        "requestedAt": "2026-10-08T08:00:00Z",
        "expiresAt": "2026-10-09T08:00:00Z",
    }
    payload.update(overrides)
    return ApprovalResult.model_validate(payload)


class ApprovalTools:
    def __init__(self, envelope: ToolEnvelope[ApprovalResult]) -> None:
        self.envelope = envelope

    async def request_human_approval(self, **kwargs: Any) -> ToolEnvelope[ApprovalResult]:
        return self.envelope


class Unused:
    async def __getattr__(self, name: str) -> Any:  # pragma: no cover - never reached
        raise AssertionError(name)


async def unused_persist(
    state: AgentState, intent: WriteIntent, outcome: WriteOutcome
) -> AgentState:
    raise AssertionError("write persistence must not run while requesting approval")


def deps(approval_tools: Any) -> GraphDeps:
    unused = Unused()
    return GraphDeps(
        understanding=unused,
        orders=unused,
        evidence_model=unused,
        evidence=unused,
        registry=ToolRegistry(),
        eligibility=unused,
        approvals=approval_tools,
        writes=unused,
        after_sales=unused,
        persist_intent=unused_persist,
    )


@pytest.mark.asyncio
async def test_request_node_stores_only_java_pending_reference_then_routes_to_wait() -> None:
    tools = ApprovalTools(
        ToolEnvelope[ApprovalResult](
            success=True,
            data=approval_result(),
            latencyMs=2,
            traceId="java-trace-approval1",
        )
    )
    node = build_approval_nodes(deps(tools))[Node.REQUEST_APPROVAL]

    update = await node({"state": high_risk_state()})

    state = update["state"]
    assert state.approval is not None
    assert state.approval.approval_request_id == "approval-001"
    assert state.approval.status == "PENDING"
    assert route_after_request_approval(state, update["decision"]) is Node.WAITING_APPROVAL

    waiting = await build_lifecycle_nodes()[Node.WAITING_APPROVAL]({"state": state})
    terminal = waiting["decision"].terminal
    assert terminal is not None
    assert terminal.status is RunStatus.WAITING_APPROVAL


@pytest.mark.asyncio
async def test_request_node_safe_stops_when_java_did_not_confirm_creation() -> None:
    tools = ApprovalTools(
        ToolEnvelope[ApprovalResult](
            success=False,
            errorCode="WRITE_TIMEOUT_UNKNOWN",
            retryable=False,
            latencyMs=2,
        )
    )
    node = build_approval_nodes(deps(tools))[Node.REQUEST_APPROVAL]

    update = await node({"state": high_risk_state()})

    assert update["state"].approval is None
    assert update["decision"].safe_stop_reason is SafeStopReason.APPROVAL_REQUEST_FAILED
    assert route_after_request_approval(update["state"], update["decision"]) is Node.SAFE_STOP


@pytest.mark.asyncio
async def test_request_node_rejects_a_mismatched_authoritative_success_response() -> None:
    tools = ApprovalTools(
        ToolEnvelope[ApprovalResult](
            success=True,
            data=approval_result(amount=Decimal("400.00")),
            latencyMs=2,
            traceId="java-trace-approval2",
        )
    )
    node = build_approval_nodes(deps(tools))[Node.REQUEST_APPROVAL]

    update = await node({"state": high_risk_state()})

    assert update["state"].approval is None
    assert update["decision"].safe_stop_reason is SafeStopReason.APPROVAL_RESPONSE_INCONSISTENT
