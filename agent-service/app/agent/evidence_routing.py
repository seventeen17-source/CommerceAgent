"""T030 next-evidence proposal contract and deterministic execution guard.

The LLM may propose what evidence would be useful next. It does not receive execution authority.
This module narrows the model-facing capability set and independently checks registry risk/state
before any Tool can run.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.agent.request_understanding import UnderstoodRequest
from app.agent.state import EvidenceItem
from app.clients.models import OrderSnapshot
from app.tools.models import ToolRisk
from app.tools.registry import ToolRegistry

__all__ = [
    "EvidenceAction",
    "EvidenceGuardDecision",
    "EvidenceDecisionModel",
    "EvidenceGuardStatus",
    "EvidenceReasonCode",
    "EvidenceRoutingContext",
    "NextEvidenceProposal",
    "build_evidence_routing_context",
    "decide_next_evidence",
    "guard_evidence_proposal",
    "guard_evidence_tool_name",
]


EvidenceToolName = Literal["get_logistics"]


class EvidenceAction(StrEnum):
    """What the model proposes doing next in the evidence stage."""

    CALL_TOOL = "CALL_TOOL"
    READY_FOR_ELIGIBILITY = "READY_FOR_ELIGIBILITY"


class EvidenceReasonCode(StrEnum):
    """Small model-owned explanation vocabulary for routing proposals."""

    NEED_LOGISTICS_STATE = "NEED_LOGISTICS_STATE"
    ENOUGH_EVIDENCE_FOR_ELIGIBILITY = "ENOUGH_EVIDENCE_FOR_ELIGIBILITY"


class NextEvidenceProposal(BaseModel):
    """Narrow model output for T030 evidence routing.

    The model-facing Tool set is intentionally smaller than the global T029 registry. Order
    resolution already happened before this stage, eligibility is a deterministic later node,
    after-sales status belongs to write recovery, and high-risk writes are never model-routed here.
    """

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    action: EvidenceAction
    tool: EvidenceToolName | None = None
    reason_code: EvidenceReasonCode = Field(alias="reasonCode")

    @model_validator(mode="after")
    def validate_action_shape(self) -> NextEvidenceProposal:
        if self.action is EvidenceAction.CALL_TOOL:
            if self.tool is None:
                raise ValueError("CALL_TOOL requires one evidence tool")
            if self.reason_code is not EvidenceReasonCode.NEED_LOGISTICS_STATE:
                raise ValueError("get_logistics requires NEED_LOGISTICS_STATE")
        else:
            if self.tool is not None:
                raise ValueError("READY_FOR_ELIGIBILITY cannot carry a tool")
            if self.reason_code is not EvidenceReasonCode.ENOUGH_EVIDENCE_FOR_ELIGIBILITY:
                raise ValueError("READY_FOR_ELIGIBILITY requires its matching reason code")
        return self




class EvidenceRoutingContext(BaseModel):
    """Minimal, non-sensitive facts the model may use to propose the next evidence step."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    intent: str = Field(min_length=1, max_length=100)
    mentions_logistics_problem: bool = Field(alias="mentionsLogisticsProblem")
    order_status: str = Field(alias="orderStatus", min_length=1, max_length=64)
    observed_evidence_types: list[str] = Field(alias="observedEvidenceTypes", max_length=32)


def build_evidence_routing_context(
    understood: UnderstoodRequest,
    *,
    order: OrderSnapshot,
    evidence: list[EvidenceItem],
) -> EvidenceRoutingContext:
    """Build the minimal second-round model context from authoritative observed facts."""
    observed = ["ORDER"]
    for item in evidence:
        if item.evidence_type not in observed:
            observed.append(item.evidence_type)

    return EvidenceRoutingContext(
        intent=understood.intent.value,
        mentions_logistics_problem=understood.mentions_logistics_problem,
        order_status=order.status,
        observed_evidence_types=observed,
    )

class EvidenceDecisionModel(Protocol):
    """Provider-independent model boundary for deciding what evidence is useful next."""

    async def decide_next_evidence(self, context: EvidenceRoutingContext) -> object:
        """Return one JSON-like routing proposal without executing any Tool."""
        ...


async def decide_next_evidence(
    context: EvidenceRoutingContext,
    *,
    model: EvidenceDecisionModel,
) -> NextEvidenceProposal:
    """Ask the model for a proposal, then enforce the narrow proposal schema."""
    raw_output = await model.decide_next_evidence(context)
    return NextEvidenceProposal.model_validate(raw_output)


class EvidenceGuardStatus(StrEnum):
    """Deterministic decision about whether a proposed action may execute now."""

    ALLOWED = "ALLOWED"
    DENIED = "DENIED"


class EvidenceGuardDecision(BaseModel):
    """Guard result suitable for trace/debug output without hidden reasoning."""

    model_config = ConfigDict(extra="forbid")

    status: EvidenceGuardStatus
    action: EvidenceAction
    tool: str | None = Field(default=None, max_length=100)
    reason_code: str = Field(min_length=1, max_length=100)

    @property
    def allowed(self) -> bool:
        return self.status is EvidenceGuardStatus.ALLOWED


def guard_evidence_proposal(
    proposal: NextEvidenceProposal,
    *,
    resolved_order_id: str | None,
    observed_evidence_types: set[str],
    registry: ToolRegistry,
) -> EvidenceGuardDecision:
    """Authorize only the current evidence-stage action, never business eligibility itself."""
    if resolved_order_id is None:
        return _denied(proposal.action, proposal.tool, "ORDER_NOT_RESOLVED")

    if proposal.action is EvidenceAction.READY_FOR_ELIGIBILITY:
        return EvidenceGuardDecision(
            status=EvidenceGuardStatus.ALLOWED,
            action=proposal.action,
            reason_code="READY_FOR_DETERMINISTIC_ELIGIBILITY",
        )

    assert proposal.tool is not None
    raw_guard = guard_evidence_tool_name(
        proposal.tool,
        observed_evidence_types=observed_evidence_types,
        registry=registry,
    )
    return EvidenceGuardDecision(
        status=raw_guard.status,
        action=proposal.action,
        tool=raw_guard.tool,
        reason_code=raw_guard.reason_code,
    )


def guard_evidence_tool_name(
    tool_name: str,
    *,
    observed_evidence_types: set[str],
    registry: ToolRegistry,
) -> EvidenceGuardDecision:
    """Defense-in-depth guard for even malformed or bypassed model output."""
    try:
        registration = registry.get(tool_name)
    except ValueError:
        return _denied(EvidenceAction.CALL_TOOL, tool_name, "UNREGISTERED_TOOL")

    if registration.risk is not ToolRisk.READ_PRIVACY_MEDIUM:
        return _denied(EvidenceAction.CALL_TOOL, tool_name, "HIGH_RISK_TOOL_NOT_ALLOWED")

    if tool_name != "get_logistics":
        return _denied(EvidenceAction.CALL_TOOL, tool_name, "TOOL_NOT_ALLOWED_IN_EVIDENCE_STAGE")

    if "LOGISTICS" in observed_evidence_types:
        return _denied(EvidenceAction.CALL_TOOL, tool_name, "EVIDENCE_ALREADY_PRESENT")

    return EvidenceGuardDecision(
        status=EvidenceGuardStatus.ALLOWED,
        action=EvidenceAction.CALL_TOOL,
        tool=tool_name,
        reason_code="SAFE_EVIDENCE_READ_ALLOWED",
    )


def _denied(action: EvidenceAction, tool: str | None, reason_code: str) -> EvidenceGuardDecision:
    return EvidenceGuardDecision(
        status=EvidenceGuardStatus.DENIED,
        action=action,
        tool=tool,
        reason_code=reason_code,
    )
