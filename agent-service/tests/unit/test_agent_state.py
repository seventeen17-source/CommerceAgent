from decimal import Decimal
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.agent.state import (
    AgentState,
    ApprovalSnapshot,
    EligibilitySnapshot,
    EvidenceItem,
    PrincipalContext,
    PrincipalRole,
    RunStatus,
    ToolHistoryEntry,
    VerificationOutcome,
    VerificationStatus,
    WriteOutcome,
    WriteStatus,
)


def build_state(**overrides: object) -> AgentState:
    values: dict[str, object] = {
        "run_id": uuid4(),
        "principal": PrincipalContext(user_id="customer-001", role=PrincipalRole.CUSTOMER),
        "user_request": "My shipment has not moved for days. Can I get a refund?",
    }
    values.update(overrides)
    return AgentState.model_validate(values)


def test_agent_state_captures_explicit_run_progress() -> None:
    state = build_state(
        intent="LOGISTICS_REFUND",
        candidate_order_ids=["order-001"],
        resolved_order_id="order-001",
        evidence=[
            EvidenceItem(
                evidence_type="LOGISTICS",
                source="get_logistics",
                data={"status": "IN_TRANSIT", "stalledHours": 72},
            )
        ],
        eligibility=EligibilitySnapshot(
            eligible=True,
            allowed_action="REFUND_ONLY",
            max_refund_amount=Decimal("199.00"),
            approval_required=False,
            rule_code="LOGISTICS_STALLED_REFUND",
            rule_version=1,
            reason_codes=["LOGISTICS_STALLED"],
        ),
        approval=ApprovalSnapshot(),
        tool_history=[
            ToolHistoryEntry(
                step_index=0,
                tool_name="get_logistics",
                success=True,
                trace_id="trace-001",
            )
        ],
        step_count=1,
        retry_count=0,
        write=WriteOutcome(
            status=WriteStatus.SUCCEEDED,
            action="CREATE_REFUND_REQUEST",
            resource_id="refund-001",
        ),
        verification=VerificationOutcome(
            status=VerificationStatus.VERIFIED_SUCCESS,
            resource_id="refund-001",
        ),
        status=RunStatus.COMPLETED,
    )

    restored = AgentState.model_validate(state.model_dump())

    assert restored.resolved_order_id == "order-001"
    assert restored.eligibility is not None
    assert restored.eligibility.allowed_action == "REFUND_ONLY"
    assert restored.tool_history[0].trace_id == "trace-001"
    assert restored.verification.status is VerificationStatus.VERIFIED_SUCCESS
    assert restored.is_terminal is True


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("step_count", 13),
        ("retry_count", 3),
    ],
)
def test_agent_state_rejects_exceeded_safety_budget(field: str, value: int) -> None:
    values: dict[str, object] = {
        "max_steps": 12,
        "max_retries": 2,
        field: value,
    }

    with pytest.raises(ValidationError):
        build_state(**values)


def test_agent_state_rejects_raw_credentials_as_extra_fields() -> None:
    with pytest.raises(ValidationError):
        AgentState.model_validate(
            {
                "run_id": uuid4(),
                "principal": {
                    "user_id": "customer-001",
                    "role": "CUSTOMER",
                    "raw_jwt": "header.payload.signature",
                },
                "user_request": "Check my order",
            }
        )


@pytest.mark.parametrize(
    ("status", "expected_terminal"),
    [
        (RunStatus.RUNNING, False),
        (RunStatus.WAITING_USER, False),
        (RunStatus.WAITING_APPROVAL, False),
        (RunStatus.COMPLETED, True),
        (RunStatus.ESCALATED, True),
        (RunStatus.FAILED, True),
        (RunStatus.SAFE_STOP, True),
    ],
)
def test_terminal_status_is_explicit(status: RunStatus, expected_terminal: bool) -> None:
    state = build_state(status=status)

    assert state.is_terminal is expected_terminal


@pytest.mark.parametrize(
    "payload",
    [
        {"authorization": "Bearer secret-token"},
        {"nested": {"chainOfThought": "private reasoning"}},
        {"note": "request used Bearer secret-token before denial"},
        {
            "note": (
                "auth used eyJhbGciOiJIUzI1NiJ9."
                "eyJzdWIiOiJjdXN0b21lci0wMDEifQ."
                "abcdefghijklmnopqrstuvwxyz123456"
            )
        },
    ],
)
def test_evidence_rejects_sensitive_persisted_values(payload: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        EvidenceItem(evidence_type="TEST", source="unit-test", data=payload)


def test_verification_details_reject_sensitive_persisted_values() -> None:
    with pytest.raises(ValidationError):
        VerificationOutcome(details={"nested": {"access_token": "should-never-persist"}})


def test_java_owned_allowed_action_remains_forward_compatible() -> None:
    snapshot = EligibilitySnapshot(
        eligible=True,
        allowed_action="EXCHANGE",
        approval_required=False,
        rule_code="FUTURE-RULE",
        rule_version=2,
    )

    assert snapshot.allowed_action == "EXCHANGE"
