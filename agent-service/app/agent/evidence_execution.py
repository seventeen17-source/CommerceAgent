"""Execute one guard-approved T030 read Tool and normalize it into Agent evidence."""

from __future__ import annotations

from typing import Protocol

from pydantic import BaseModel, ConfigDict

from app.agent.evidence_routing import EvidenceGuardDecision, EvidenceGuardStatus
from app.agent.state import EvidenceItem, ToolHistoryEntry
from app.clients.models import LogisticsSnapshot
from app.tools.models import ToolEnvelope

__all__ = ["EvidenceExecutionResult", "EvidenceReadTools", "execute_read_evidence"]


class EvidenceReadTools(Protocol):
    """The only read capability T030 currently executes after evidence routing."""

    async def get_logistics(self, order_id: str) -> ToolEnvelope[LogisticsSnapshot]:
        """Read authoritative logistics facts for an already-resolved order."""
        ...


class EvidenceExecutionResult(BaseModel):
    """One observable Tool execution plus optional authoritative evidence."""

    model_config = ConfigDict(extra="forbid")

    evidence: EvidenceItem | None = None
    history: ToolHistoryEntry


async def execute_read_evidence(
    decision: EvidenceGuardDecision,
    *,
    resolved_order_id: str,
    step_index: int,
    tools: EvidenceReadTools,
) -> EvidenceExecutionResult:
    """Execute exactly one guard-approved read and preserve success/failure trace facts."""
    if decision.status is not EvidenceGuardStatus.ALLOWED:
        raise ValueError("evidence execution requires an ALLOWED guard decision")
    if decision.tool != "get_logistics":
        raise ValueError("only get_logistics is executable in the T030 evidence stage")

    result = await tools.get_logistics(resolved_order_id)
    history = ToolHistoryEntry(
        step_index=step_index,
        tool_name="get_logistics",
        success=result.success,
        error_code=result.error_code,
        retryable=result.retryable,
        trace_id=result.trace_id,
    )

    if not result.success:
        return EvidenceExecutionResult(history=history)

    logistics = result.data
    if logistics is None:
        raise ValueError("successful logistics Tool result is missing data")
    evidence = EvidenceItem(
        evidence_type="LOGISTICS",
        source="get_logistics",
        data=logistics.model_dump(by_alias=True, mode="json"),
    )
    return EvidenceExecutionResult(evidence=evidence, history=history)
