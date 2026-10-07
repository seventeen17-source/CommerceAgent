"""T030 deterministic handoff from evidence collection to Java eligibility authority.

The Agent never computes refund eligibility or amount here. Once evidence routing says the run is
ready, this module calls the already-authenticated T029 Tool and copies the Java decision into the
Agent state shape. The request reason code is descriptive only; Java deliberately ignores it when
selecting rules or computing amounts.
"""

from __future__ import annotations

from typing import Final, Protocol

from pydantic import BaseModel, ConfigDict

from app.agent.evidence_routing import EvidenceAction, EvidenceGuardDecision, EvidenceGuardStatus
from app.agent.state import EligibilitySnapshot, ToolHistoryEntry
from app.agent.tool_tracing import TraceSink, report_tool_call
from app.clients.models import EligibilityDecision
from app.tools.models import ToolEnvelope

__all__ = [
    "US1_ELIGIBILITY_REASON_CODE",
    "EligibilityExecutionResult",
    "EligibilityTools",
    "check_eligibility",
]


US1_ELIGIBILITY_REASON_CODE: Final[str] = "LOGISTICS_DELAY"


class EligibilityTools(Protocol):
    """The T029 read capability used by the T030 eligibility handoff."""

    async def check_after_sales_eligibility(
        self, order_id: str, reason_code: str
    ) -> ToolEnvelope[EligibilityDecision]:
        """Ask Java for the authoritative deterministic eligibility decision."""
        ...


class EligibilityExecutionResult(BaseModel):
    """One eligibility Tool call plus the optional authoritative decision snapshot."""

    model_config = ConfigDict(extra="forbid")

    eligibility: EligibilitySnapshot | None = None
    history: ToolHistoryEntry


async def check_eligibility(
    decision: EvidenceGuardDecision,
    *,
    resolved_order_id: str,
    step_index: int,
    tools: EligibilityTools,
    record_trace: TraceSink | None = None,
) -> EligibilityExecutionResult:
    """Call Java only after the evidence stage explicitly hands off to eligibility."""
    if decision.status is not EvidenceGuardStatus.ALLOWED:
        raise ValueError("eligibility execution requires an ALLOWED guard decision")
    if decision.action is not EvidenceAction.READY_FOR_ELIGIBILITY:
        raise ValueError("eligibility execution requires READY_FOR_ELIGIBILITY")
    if decision.tool is not None:
        raise ValueError("eligibility handoff must not carry a Tool name")

    result = await tools.check_after_sales_eligibility(
        resolved_order_id,
        US1_ELIGIBILITY_REASON_CODE,
    )
    history = ToolHistoryEntry(
        step_index=step_index,
        tool_name="check_after_sales_eligibility",
        success=result.success,
        error_code=result.error_code,
        retryable=result.retryable,
        trace_id=result.trace_id,
    )
    report_tool_call(
        record_trace,
        step_index=step_index,
        tool_name="check_after_sales_eligibility",
        envelope=result,
        input_summary={"orderId": resolved_order_id, "reasonCode": US1_ELIGIBILITY_REASON_CODE},
    )

    if not result.success:
        return EligibilityExecutionResult(history=history)

    authoritative = result.data
    if authoritative is None:
        raise ValueError("successful eligibility Tool result is missing data")
    snapshot = EligibilitySnapshot(
        eligible=authoritative.eligible,
        allowed_action=authoritative.allowed_action,
        max_refund_amount=authoritative.max_refund_amount,
        approval_required=authoritative.approval_required,
        rule_code=authoritative.rule_code,
        rule_version=authoritative.rule_version,
        reason_codes=authoritative.reason_codes,
    )
    return EligibilityExecutionResult(eligibility=snapshot, history=history)
