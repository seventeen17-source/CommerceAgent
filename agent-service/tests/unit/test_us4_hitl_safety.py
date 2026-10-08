"""T050: the Agent must never manufacture the authority that unlocks a high-risk write.

These tests intentionally stop one layer before T052-T054. At this point Python has no authority
API to re-read, so the only safe behaviour is fail-closed: an approval-shaped value already present
in AgentState, or an approval id supplied by a caller, must not turn approval_required into a
write permission.

T054 may later replace the safe-stop with an authoritative Java re-read + exact binding check. What
must remain true after that change is the negative half pinned here: model/caller supplied state is
never sufficient by itself.
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

    assert safe_stop_reason_for(state) is SafeStopReason.ELIGIBILITY_APPROVAL_REQUIRED
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
                "approval_request_id": "approval-001",
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


def test_agent_state_rejects_caller_invented_approval_binding_fields() -> None:
    """Until Java supplies a typed authoritative binding, the Agent cannot smuggle one into state."""
    with pytest.raises(ValidationError):
        make_state(
            approval={
                "approval_request_id": "approval-001",
                "status": "APPROVED",
                "run_id": "some-run",
                "order_id": "order-001",
                "action": "REFUND_ONLY",
                "amount": "500.00",
            }
        )
