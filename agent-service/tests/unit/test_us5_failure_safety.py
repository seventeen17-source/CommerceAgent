"""T057 executable safety contract for US5 failure handling.

T057 is intentionally test-first. Existing lower-level guarantees are active tests; the two
behaviours whose implementation belongs to T061 are strict xfails. This keeps the suite green while
making the missing US5 semantics executable instead of hiding them in prose.
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.agent.routing import (
    Decision,
    Node,
    SafeStopReason,
    route_after_execute,
    safe_stop_reason_for,
    terminal_decision_for,
)
from app.agent.state import (
    AgentState,
    EvidenceItem,
    RunStatus,
    ToolHistoryEntry,
    VerificationStatus,
    advance,
)
from app.clients.errors import CommerceApiError, CommerceTransportError


def make_state(**overrides: object) -> AgentState:
    values: dict[str, object] = {
        "run_id": uuid4(),
        "principal": {"user_id": "customer-001", "role": "CUSTOMER"},
        "user_request": "My after-sales request cannot be completed automatically.",
        "intent": "REFUND_REQUEST",
    }
    values.update(overrides)
    return AgentState.model_validate(values)


def test_retry_budget_cannot_be_spent_past_the_persisted_limit() -> None:
    """A resume does not grant a fresh retry budget."""

    state = make_state(retry_count=2, max_retries=2)

    with pytest.raises(ValidationError):
        advance(state, retry_count=state.retry_count + 1)


def test_retry_request_cannot_outrank_the_step_budget() -> None:
    """Even a retryable failure cannot start work after the run budget is spent."""

    state = make_state(step_count=12, max_steps=12)
    decision = Decision(retry_current_stage=True)

    assert route_after_execute(state, decision) is Node.SAFE_STOP
    assert safe_stop_reason_for(state, decision) is SafeStopReason.BUDGET_EXHAUSTED


def test_dependency_timeout_is_retryable_only_when_the_backend_answered_so() -> None:
    """A retryable error is permission to consider a retry, never an infinite loop."""

    timeout = CommerceApiError(
        error_code="DEPENDENCY_TIMEOUT",
        http_status=504,
        retryable=True,
    )

    assert timeout.blind_retry_allowed is True

    exhausted = make_state(retry_count=2, max_retries=2)
    with pytest.raises(ValidationError):
        advance(exhausted, retry_count=exhausted.retry_count + 1)


def test_unknown_transport_outcome_preserves_read_write_asymmetry() -> None:
    """Unknown read/evaluation results may retry; unknown writes may not blind retry."""

    side_effect_free_timeout = CommerceTransportError(
        reason="dependency timeout",
        request_was_safe=True,
    )
    state_changing_timeout = CommerceTransportError(
        reason="dependency timeout after write",
        request_was_safe=False,
    )

    assert side_effect_free_timeout.outcome_unknown is True
    assert side_effect_free_timeout.blind_retry_allowed is True
    assert state_changing_timeout.outcome_unknown is True
    assert state_changing_timeout.blind_retry_allowed is False


def test_safe_stop_is_terminal_and_carries_a_machine_readable_reason() -> None:
    """An unconfirmable business outcome must never be rendered as success."""

    state = make_state(verification={"status": VerificationStatus.UNKNOWN})

    terminal = terminal_decision_for(state)

    assert terminal.status is RunStatus.SAFE_STOP
    assert terminal.reason is SafeStopReason.VERIFICATION_UNKNOWN
    assert state.model_copy(update={"status": RunStatus.SAFE_STOP}).is_terminal is True


@pytest.mark.xfail(
    strict=True,
    reason="T061 must detect repeated no-new-evidence progress and route to safe stop/escalation",
)
def test_no_progress_loop_cannot_finish_as_a_clean_completion() -> None:
    """Repeated successful-looking work with no new evidence is not progress."""

    state = make_state(
        evidence=[
            EvidenceItem(
                evidence_type="LOGISTICS",
                source="get_logistics",
                data={"status": "IN_TRANSIT"},
            )
        ],
        tool_history=[
            ToolHistoryEntry(
                step_index=3,
                tool_name="get_logistics",
                success=False,
                error_code="DEPENDENCY_TIMEOUT",
                retryable=True,
            ),
            ToolHistoryEntry(
                step_index=4,
                tool_name="get_logistics",
                success=False,
                error_code="DEPENDENCY_TIMEOUT",
                retryable=True,
            ),
        ],
        retry_count=2,
        max_retries=2,
    )

    terminal = terminal_decision_for(state)

    assert terminal.status in {RunStatus.SAFE_STOP, RunStatus.ESCALATED}


@pytest.mark.xfail(
    strict=True,
    reason="T061 must route authoritative MANUAL_REVIEW to escalation instead of COMPLETED",
)
def test_manual_review_is_an_escalation_not_a_clean_completion() -> None:
    """Java saying MANUAL_REVIEW means automation is done, not the customer's case."""

    state = make_state(
        eligibility={
            "eligible": False,
            "allowed_action": "MANUAL_REVIEW",
            "max_refund_amount": None,
            "approval_required": False,
            "rule_code": None,
            "rule_version": None,
            "reason_codes": ["MANUAL_REVIEW_REQUIRED"],
        }
    )

    terminal = terminal_decision_for(state)

    assert terminal.status is RunStatus.ESCALATED
