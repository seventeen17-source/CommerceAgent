"""T050: the Agent must never manufacture the authority that unlocks a high-risk write.

These tests pin the negative half of HITL across T050-T054: a caller may name an approval reference,
but cannot assert status/role/binding through the resume transport, and an APPROVED-looking snapshot
without T054's explicit authoritative binding verification must still fail closed. T054 adds the
positive path by owner-scoped re-reading Java; it does not weaken these negative guarantees.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.agent.routing import (
    Node,
    SafeStopReason,
    route_after_eligibility,
    safe_stop_reason_for,
)
from app.agent.state import AgentState
from app.api.runs import ResumeRunRequest


def make_state(**overrides: Any) -> AgentState:
    base: dict[str, Any] = {
        "run_id": uuid4(),
        "principal": {"user_id": "customer-001", "role": "CUSTOMER"},
        "user_request": "这个退款如果需要审批就帮我处理",
        "intent": "REFUND_REQUEST",
        "resolved_order_id": "order-001",
        "eligibility": {
            "eligible": True,
            "allowed_action": "REFUND_ONLY",
            "max_refund_amount": Decimal("500.00"),
            "approval_required": True,
            "rule_code": "HIGH_VALUE_REFUND",
            "rule_version": 1,
            "reason_codes": ["APPROVAL_REQUIRED_BY_AMOUNT"],
        },
    }
    base.update(overrides)
    return AgentState.model_validate(base)


def test_agent_cannot_self_approve_by_putting_approved_in_its_state() -> None:
    """An approval-shaped snapshot is not authority and cannot unlock the refund node."""
    state = make_state(
        approval={
            "approval_request_id": "approval-invented-by-agent",
            "status": "APPROVED",
        }
    )

    assert safe_stop_reason_for(state) is SafeStopReason.APPROVAL_STATE_UNVERIFIED
    assert route_after_eligibility(state) is Node.SAFE_STOP


def test_an_approval_id_from_another_run_cannot_unlock_this_run() -> None:
    """Without an authoritative re-read + binding check, an opaque id is only a claim."""
    run_a = uuid4()
    state = make_state(
        run_id=run_a,
        approval={
            "approval_request_id": "approval-owned-by-run-b",
            "status": "APPROVED",
        },
    )

    assert str(state.run_id) == str(run_a)
    assert route_after_eligibility(state) is Node.SAFE_STOP


def test_resume_request_cannot_forge_approval_status_or_role() -> None:
    """The resume transport accepts a reference, never caller-authored approval facts."""
    with pytest.raises(ValidationError):
        ResumeRunRequest.model_validate(
            {
                "approvalRequestId": "approval-001",
                "approval_status": "APPROVED",
            }
        )

    with pytest.raises(ValidationError):
        ResumeRunRequest.model_validate(
            {
                "approval_request_id": "approval-001",
                "role": "APPROVER",
            }
        )


def test_verified_binding_marker_requires_a_complete_approved_snapshot() -> None:
    """T054's internal marker cannot be set on a partial or merely PENDING snapshot."""
    with pytest.raises(ValidationError):
        make_state(
            approval={
                "approval_request_id": "approval-001",
                "status": "APPROVED",
                "binding_verified": True,
            }
        )

    with pytest.raises(ValidationError):
        make_state(
            approval={
                "approval_request_id": "approval-001",
                "status": "PENDING",
                "run_id": uuid4(),
                "order_id": "order-001",
                "action_type": "REFUND_ONLY",
                "amount": "500.00",
                "binding_verified": True,
            }
        )
