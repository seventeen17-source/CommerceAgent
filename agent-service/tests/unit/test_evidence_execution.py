"""T030 tests for guarded read-tool execution and evidence normalization."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.agent.evidence_execution import execute_read_evidence
from app.agent.evidence_routing import (
    EvidenceAction,
    EvidenceGuardDecision,
    EvidenceGuardStatus,
)
from app.clients.models import LogisticsSnapshot
from app.tools.models import ToolEnvelope


class _FakeEvidenceTools:
    def __init__(self, result: ToolEnvelope[LogisticsSnapshot]) -> None:
        self.result = result
        self.calls: list[str] = []

    async def get_logistics(self, order_id: str) -> ToolEnvelope[LogisticsSnapshot]:
        self.calls.append(order_id)
        return self.result


def _allowed() -> EvidenceGuardDecision:
    return EvidenceGuardDecision(
        status=EvidenceGuardStatus.ALLOWED,
        action=EvidenceAction.CALL_TOOL,
        tool="get_logistics",
        reason_code="SAFE_EVIDENCE_READ_ALLOWED",
    )


def _logistics() -> LogisticsSnapshot:
    return LogisticsSnapshot.model_validate(
        {
            "status": "IN_TRANSIT",
            "signed": False,
            "lastMeaningfulEventAt": datetime(2026, 9, 12, 8, 30, tzinfo=UTC),
            "stalledHours": 384,
        }
    )


@pytest.mark.asyncio
async def test_allowed_logistics_read_becomes_structured_authoritative_evidence() -> None:
    tools = _FakeEvidenceTools(
        ToolEnvelope(
            success=True,
            data=_logistics(),
            latencyMs=7,
            traceId="trace-logistics-001",
        )
    )

    result = await execute_read_evidence(
        _allowed(),
        resolved_order_id="order-001",
        step_index=3,
        tools=tools,
    )

    assert tools.calls == ["order-001"]
    assert result.evidence is not None
    assert result.evidence.evidence_type == "LOGISTICS"
    assert result.evidence.source == "get_logistics"
    assert result.evidence.data["status"] == "IN_TRANSIT"
    assert result.evidence.data["signed"] is False
    assert result.evidence.data["stalledHours"] == 384
    assert result.evidence.data["lastMeaningfulEventAt"] == "2026-09-12T08:30:00Z"
    assert result.history.step_index == 3
    assert result.history.tool_name == "get_logistics"
    assert result.history.success is True
    assert result.history.trace_id == "trace-logistics-001"


@pytest.mark.asyncio
async def test_failed_read_is_recorded_but_never_promoted_to_evidence() -> None:
    tools = _FakeEvidenceTools(
        ToolEnvelope[LogisticsSnapshot](
            success=False,
            errorCode="DEPENDENCY_UNAVAILABLE",
            retryable=True,
            latencyMs=20,
            traceId="trace-logistics-err",
        )
    )

    result = await execute_read_evidence(
        _allowed(),
        resolved_order_id="order-001",
        step_index=4,
        tools=tools,
    )

    assert result.evidence is None
    assert result.history.success is False
    assert result.history.error_code == "DEPENDENCY_UNAVAILABLE"
    assert result.history.retryable is True
    assert result.history.trace_id == "trace-logistics-err"


@pytest.mark.asyncio
async def test_denied_guard_cannot_execute_a_tool() -> None:
    tools = _FakeEvidenceTools(ToolEnvelope(success=True, data=_logistics(), latencyMs=1))
    denied = EvidenceGuardDecision(
        status=EvidenceGuardStatus.DENIED,
        action=EvidenceAction.CALL_TOOL,
        tool="get_logistics",
        reason_code="ORDER_NOT_RESOLVED",
    )

    with pytest.raises(ValueError, match="ALLOWED"):
        await execute_read_evidence(
            denied,
            resolved_order_id="order-001",
            step_index=1,
            tools=tools,
        )

    assert tools.calls == []


@pytest.mark.asyncio
async def test_allowed_but_wrong_tool_name_fails_closed_before_execution() -> None:
    tools = _FakeEvidenceTools(
        ToolEnvelope(success=True, data=_logistics(), latencyMs=1)
    )
    malformed = EvidenceGuardDecision(
        status=EvidenceGuardStatus.ALLOWED,
        action=EvidenceAction.CALL_TOOL,
        tool="get_order",
        reason_code="MALFORMED_TEST_INPUT",
    )

    with pytest.raises(ValueError, match="only get_logistics"):
        await execute_read_evidence(
            malformed,
            resolved_order_id="order-001",
            step_index=1,
            tools=tools,
        )

    assert tools.calls == []
