"""T053 handoff from Java eligibility to the authoritative human-approval API.

The Agent does not decide whether approval is required and does not mint approval facts. This module
takes the already-persistable Java eligibility snapshot, asks Java to create the exact proposal, and
copies back only the authoritative approval reference/status needed to park the run.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Protocol
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.agent.state import ApprovalSnapshot, EligibilitySnapshot, ToolHistoryEntry
from app.agent.tool_tracing import TraceSink, report_tool_call
from app.clients.models import ApprovalResult
from app.tools.models import ToolEnvelope

__all__ = [
    "ApprovalExecutionResult",
    "ApprovalTools",
    "request_human_approval",
]


class ApprovalTools(Protocol):
    """The one T053 capability needed to create an authoritative approval request."""

    async def request_human_approval(
        self,
        *,
        run_id: str,
        order_id: str,
        action_type: str,
        amount: Decimal | None,
        risk_reason: str,
    ) -> ToolEnvelope[ApprovalResult]:
        """Ask Java to create/replay one PENDING ApprovalRequest."""
        ...


class ApprovalExecutionResult(BaseModel):
    """One approval Tool call plus the optional authoritative snapshot."""

    model_config = ConfigDict(extra="forbid")

    approval: ApprovalSnapshot | None = None
    history: ToolHistoryEntry
    response_matches_proposal: bool = False


def _risk_reason(eligibility: EligibilitySnapshot) -> str:
    """Return the authoritative reason that made this decision approval-requiring."""
    reasons = [reason for reason in eligibility.reason_codes if reason.startswith("APPROVAL_")]
    if len(reasons) != 1:
        raise ValueError("approval-required eligibility must carry exactly one APPROVAL_* reason")
    return reasons[0]


def _same_amount(left: Decimal | None, right: Decimal | None) -> bool:
    if left is None or right is None:
        return left is None and right is None
    return left == right


async def request_human_approval(
    *,
    run_id: UUID,
    resolved_order_id: str,
    eligibility: EligibilitySnapshot,
    step_index: int,
    tools: ApprovalTools,
    record_trace: TraceSink | None = None,
) -> ApprovalExecutionResult:
    """Create/replay one PENDING approval and reject a mismatched success response.

    A 2xx response is not enough by itself: the returned row must describe the exact proposal we
    asked Java to persist. That check is cheap here and prevents a proxy/backend regression from
    attaching another run/order/action/amount to this Agent checkpoint.
    """
    if not eligibility.eligible or not eligibility.approval_required:
        raise ValueError("request_human_approval requires eligible + approval_required")
    risk_reason = _risk_reason(eligibility)

    result = await tools.request_human_approval(
        run_id=str(run_id),
        order_id=resolved_order_id,
        action_type=eligibility.allowed_action,
        amount=eligibility.max_refund_amount,
        risk_reason=risk_reason,
    )
    history = ToolHistoryEntry(
        step_index=step_index,
        tool_name="request_human_approval",
        success=result.success,
        error_code=result.error_code,
        retryable=result.retryable,
        trace_id=result.trace_id,
    )
    report_tool_call(
        record_trace,
        step_index=step_index,
        tool_name="request_human_approval",
        envelope=result,
        input_summary={
            "runId": str(run_id),
            "orderId": resolved_order_id,
            "actionType": eligibility.allowed_action,
            "amount": (
                None
                if eligibility.max_refund_amount is None
                else str(eligibility.max_refund_amount)
            ),
            "riskReason": risk_reason,
        },
    )

    if not result.success:
        return ApprovalExecutionResult(history=history)

    authoritative = result.data
    if authoritative is None:
        raise ValueError("successful approval Tool result is missing data")

    matches = (
        authoritative.run_id == run_id
        and authoritative.order_id == resolved_order_id
        and authoritative.action_type == eligibility.allowed_action
        and _same_amount(authoritative.amount, eligibility.max_refund_amount)
        and authoritative.risk_reason == risk_reason
        and authoritative.status == "PENDING"
    )
    if not matches:
        return ApprovalExecutionResult(history=history, response_matches_proposal=False)

    return ApprovalExecutionResult(
        approval=ApprovalSnapshot(
            approval_request_id=authoritative.approval_request_id,
            status=authoritative.status,
        ),
        history=history,
        response_matches_proposal=True,
    )
