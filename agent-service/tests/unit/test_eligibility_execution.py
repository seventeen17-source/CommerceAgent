"""T030 tests for the deterministic Java eligibility handoff."""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.agent.eligibility_execution import US1_ELIGIBILITY_REASON_CODE, check_eligibility
from app.agent.evidence_routing import (
    EvidenceAction,
    EvidenceGuardDecision,
    EvidenceGuardStatus,
)
from app.clients.models import EligibilityDecision
from app.tools.models import ToolEnvelope


class _FakeEligibilityTools:
    def __init__(self, result: ToolEnvelope[EligibilityDecision]) -> None:
        self.result = result
        self.calls: list[tuple[str, str]] = []

    async def check_after_sales_eligibility(
        self, order_id: str, reason_code: str
    ) -> ToolEnvelope[EligibilityDecision]:
        self.calls.append((order_id, reason_code))
        return self.result


def _ready() -> EvidenceGuardDecision:
    return EvidenceGuardDecision(
        status=EvidenceGuardStatus.ALLOWED,
        action=EvidenceAction.READY_FOR_ELIGIBILITY,
        reason_code="READY_FOR_DETERMINISTIC_ELIGIBILITY",
    )


def _java_decision() -> EligibilityDecision:
    return EligibilityDecision.model_validate(
        {
            "eligible": True,
            "allowedAction": "REFUND_ONLY",
            "maxRefundAmount": Decimal("199.00"),
            "approvalRequired": False,
            "ruleCode": "LOGISTICS_STALLED_REFUND",
            "ruleVersion": 1,
            "reasonCodes": ["STALL_THRESHOLD_MET"],
        }
    )


@pytest.mark.asyncio
async def test_ready_handoff_calls_java_with_controlled_descriptive_reason() -> None:
    tools = _FakeEligibilityTools(
        ToolEnvelope(
            success=True,
            data=_java_decision(),
            latencyMs=3,
            traceId="java-trace-eligibility",
        )
    )

    result = await check_eligibility(
        _ready(),
        resolved_order_id="order-001",
        step_index=4,
        tools=tools,
    )

    assert tools.calls == [("order-001", US1_ELIGIBILITY_REASON_CODE)]
    assert US1_ELIGIBILITY_REASON_CODE == "LOGISTICS_DELAY"
    assert result.eligibility is not None


@pytest.mark.asyncio
async def test_java_decision_is_copied_without_agent_recomputing_amount() -> None:
    tools = _FakeEligibilityTools(ToolEnvelope(success=True, data=_java_decision(), latencyMs=2))

    result = await check_eligibility(
        _ready(),
        resolved_order_id="order-001",
        step_index=4,
        tools=tools,
    )

    assert result.eligibility is not None
    assert result.eligibility.eligible is True
    assert result.eligibility.allowed_action == "REFUND_ONLY"
    assert result.eligibility.max_refund_amount == Decimal("199.00")
    assert result.eligibility.approval_required is False
    assert result.eligibility.rule_code == "LOGISTICS_STALLED_REFUND"
    assert result.eligibility.rule_version == 1
    assert result.eligibility.reason_codes == ["STALL_THRESHOLD_MET"]


@pytest.mark.asyncio
async def test_failed_java_evaluation_creates_no_eligibility_snapshot() -> None:
    tools = _FakeEligibilityTools(
        ToolEnvelope[EligibilityDecision](
            success=False,
            errorCode="DEPENDENCY_UNAVAILABLE",
            retryable=True,
            latencyMs=5,
            traceId="java-trace-failure",
        )
    )

    result = await check_eligibility(
        _ready(),
        resolved_order_id="order-001",
        step_index=4,
        tools=tools,
    )

    assert result.eligibility is None
    assert result.history.success is False
    assert result.history.error_code == "DEPENDENCY_UNAVAILABLE"
    assert result.history.retryable is True
    assert result.history.trace_id == "java-trace-failure"


@pytest.mark.asyncio
async def test_denied_guard_cannot_call_java_eligibility() -> None:
    tools = _FakeEligibilityTools(ToolEnvelope(success=True, data=_java_decision(), latencyMs=1))
    denied = EvidenceGuardDecision(
        status=EvidenceGuardStatus.DENIED,
        action=EvidenceAction.READY_FOR_ELIGIBILITY,
        reason_code="ORDER_NOT_RESOLVED",
    )

    with pytest.raises(ValueError, match="ALLOWED"):
        await check_eligibility(
            denied,
            resolved_order_id="order-001",
            step_index=4,
            tools=tools,
        )

    assert tools.calls == []


@pytest.mark.asyncio
async def test_logistics_tool_decision_cannot_skip_into_eligibility() -> None:
    tools = _FakeEligibilityTools(
        ToolEnvelope(success=True, data=_java_decision(), latencyMs=1)
    )
    still_collecting = EvidenceGuardDecision(
        status=EvidenceGuardStatus.ALLOWED,
        action=EvidenceAction.CALL_TOOL,
        tool="get_logistics",
        reason_code="SAFE_EVIDENCE_READ_ALLOWED",
    )

    with pytest.raises(ValueError, match="READY_FOR_ELIGIBILITY"):
        await check_eligibility(
            still_collecting,
            resolved_order_id="order-001",
            step_index=4,
            tools=tools,
        )

    assert tools.calls == []
