from __future__ import annotations

from decimal import Decimal
from uuid import UUID

import pytest

from app.agent.approval_execution import request_human_approval
from app.agent.state import EligibilitySnapshot
from app.clients.models import ApprovalResult
from app.tools.models import ToolEnvelope

RUN_ID = UUID("52000000-0000-4000-8000-000000000001")


def approval_result(**overrides: object) -> ApprovalResult:
    base: dict[str, object] = {
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
    base.update(overrides)
    return ApprovalResult.model_validate(base)


class FakeApprovalTools:
    def __init__(self, result: ToolEnvelope[ApprovalResult]) -> None:
        self.result = result
        self.calls: list[dict[str, object]] = []

    async def request_human_approval(self, **kwargs: object) -> ToolEnvelope[ApprovalResult]:
        self.calls.append(dict(kwargs))
        return self.result


def eligibility() -> EligibilitySnapshot:
    return EligibilitySnapshot(
        eligible=True,
        allowed_action="REFUND_ONLY",
        max_refund_amount=Decimal("399.00"),
        approval_required=True,
        rule_code="HIGH_VALUE_REFUND",
        rule_version=1,
        reason_codes=["STALL_THRESHOLD_MET", "APPROVAL_REQUIRED_BY_AMOUNT"],
    )


@pytest.mark.asyncio
async def test_success_copies_only_authoritative_pending_reference_into_agent_state_shape() -> None:
    tools = FakeApprovalTools(
        ToolEnvelope[ApprovalResult](
            success=True,
            data=approval_result(),
            latencyMs=3,
            traceId="java-trace-approval1",
        )
    )

    result = await request_human_approval(
        run_id=RUN_ID,
        resolved_order_id="order-001",
        eligibility=eligibility(),
        step_index=5,
        tools=tools,
    )

    assert result.response_matches_proposal is True
    assert result.approval is not None
    assert result.approval.approval_request_id == "approval-001"
    assert result.approval.status == "PENDING"
    assert tools.calls == [
        {
            "run_id": str(RUN_ID),
            "order_id": "order-001",
            "action_type": "REFUND_ONLY",
            "amount": Decimal("399.00"),
            "risk_reason": "APPROVAL_REQUIRED_BY_AMOUNT",
        }
    ]


@pytest.mark.asyncio
async def test_success_response_with_cross_run_binding_is_not_accepted() -> None:
    tools = FakeApprovalTools(
        ToolEnvelope[ApprovalResult](
            success=True,
            data=approval_result(runId="52000000-0000-4000-8000-000000000099"),
            latencyMs=3,
            traceId="java-trace-approval2",
        )
    )

    result = await request_human_approval(
        run_id=RUN_ID,
        resolved_order_id="order-001",
        eligibility=eligibility(),
        step_index=5,
        tools=tools,
    )

    assert result.response_matches_proposal is False
    assert result.approval is None


@pytest.mark.asyncio
async def test_failed_tool_call_never_creates_an_agent_approval_snapshot() -> None:
    tools = FakeApprovalTools(
        ToolEnvelope[ApprovalResult](
            success=False,
            errorCode="WRITE_TIMEOUT_UNKNOWN",
            retryable=False,
            latencyMs=3,
        )
    )

    result = await request_human_approval(
        run_id=RUN_ID,
        resolved_order_id="order-001",
        eligibility=eligibility(),
        step_index=5,
        tools=tools,
    )

    assert result.approval is None
    assert result.history.success is False
    assert result.history.error_code == "WRITE_TIMEOUT_UNKNOWN"


@pytest.mark.asyncio
async def test_approval_required_without_one_authoritative_approval_reason_fails_closed() -> None:
    broken = eligibility().model_copy(update={"reason_codes": ["STALL_THRESHOLD_MET"]})
    tools = FakeApprovalTools(
        ToolEnvelope[ApprovalResult](
            success=True,
            data=approval_result(),
            latencyMs=3,
        )
    )

    with pytest.raises(ValueError, match="exactly one APPROVAL_"):
        await request_human_approval(
            run_id=RUN_ID,
            resolved_order_id="order-001",
            eligibility=broken,
            step_index=5,
            tools=tools,
        )

    assert tools.calls == []
