"""T030 tests for model proposal versus deterministic evidence execution authority."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.agent.evidence_routing import (
    EvidenceAction,
    EvidenceGuardStatus,
    EvidenceReasonCode,
    NextEvidenceProposal,
    guard_evidence_proposal,
    guard_evidence_tool_name,
)
from app.tools.registry import ToolRegistry


def _logistics_proposal() -> NextEvidenceProposal:
    return NextEvidenceProposal.model_validate(
        {
            "action": "CALL_TOOL",
            "tool": "get_logistics",
            "reasonCode": "NEED_LOGISTICS_STATE",
        }
    )


def test_model_contract_does_not_expose_high_risk_write_tool() -> None:
    with pytest.raises(ValidationError):
        NextEvidenceProposal.model_validate(
            {
                "action": "CALL_TOOL",
                "tool": "create_refund_request",
                "reasonCode": "NEED_LOGISTICS_STATE",
            }
        )


def test_guard_independently_denies_high_risk_write_even_if_contract_is_bypassed() -> None:
    decision = guard_evidence_tool_name(
        "create_refund_request",
        observed_evidence_types=set(),
        registry=ToolRegistry(),
    )

    assert decision.status is EvidenceGuardStatus.DENIED
    assert decision.reason_code == "HIGH_RISK_TOOL_NOT_ALLOWED"


def test_guard_rejects_arbitrary_unregistered_tool_name() -> None:
    decision = guard_evidence_tool_name(
        "call_any_url",
        observed_evidence_types=set(),
        registry=ToolRegistry(),
    )

    assert decision.status is EvidenceGuardStatus.DENIED
    assert decision.reason_code == "UNREGISTERED_TOOL"


def test_guard_requires_resolved_order_before_logistics_read() -> None:
    decision = guard_evidence_proposal(
        _logistics_proposal(),
        resolved_order_id=None,
        observed_evidence_types=set(),
        registry=ToolRegistry(),
    )

    assert decision.status is EvidenceGuardStatus.DENIED
    assert decision.reason_code == "ORDER_NOT_RESOLVED"


def test_guard_allows_logistics_after_order_resolution() -> None:
    decision = guard_evidence_proposal(
        _logistics_proposal(),
        resolved_order_id="order-001",
        observed_evidence_types={"ORDER"},
        registry=ToolRegistry(),
    )

    assert decision.status is EvidenceGuardStatus.ALLOWED
    assert decision.tool == "get_logistics"
    assert decision.reason_code == "SAFE_EVIDENCE_READ_ALLOWED"


def test_guard_blocks_duplicate_logistics_read_to_prevent_no_progress_loop() -> None:
    decision = guard_evidence_proposal(
        _logistics_proposal(),
        resolved_order_id="order-001",
        observed_evidence_types={"ORDER", "LOGISTICS"},
        registry=ToolRegistry(),
    )

    assert decision.status is EvidenceGuardStatus.DENIED
    assert decision.reason_code == "EVIDENCE_ALREADY_PRESENT"


def test_ready_for_eligibility_does_not_mean_eligible() -> None:
    proposal = NextEvidenceProposal.model_validate(
        {
            "action": "READY_FOR_ELIGIBILITY",
            "tool": None,
            "reasonCode": "ENOUGH_EVIDENCE_FOR_ELIGIBILITY",
        }
    )

    decision = guard_evidence_proposal(
        proposal,
        resolved_order_id="order-001",
        observed_evidence_types={"ORDER", "LOGISTICS"},
        registry=ToolRegistry(),
    )

    assert proposal.reason_code is EvidenceReasonCode.ENOUGH_EVIDENCE_FOR_ELIGIBILITY
    assert decision.status is EvidenceGuardStatus.ALLOWED
    assert decision.action is EvidenceAction.READY_FOR_ELIGIBILITY
    assert decision.tool is None
    assert decision.reason_code == "READY_FOR_DETERMINISTIC_ELIGIBILITY"
