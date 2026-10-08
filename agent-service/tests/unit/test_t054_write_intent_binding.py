from __future__ import annotations

from decimal import Decimal
from uuid import UUID

import pytest

from app.agent.execute_write import (
    WriteIntentConflictError,
    refund_write_intent,
    return_write_intent,
)
from app.agent.state import AgentState, ApprovalSnapshot, advance


RUN_ID = UUID("54000000-0000-4000-8000-000000000001")


def state() -> AgentState:
    return AgentState.model_validate(
        {
            "run_id": str(RUN_ID),
            "principal": {"user_id": "customer-001", "role": "CUSTOMER"},
            "user_request": "高风险售后",
            "resolved_order_id": "order-001",
            "approval": {
                "approval_request_id": "approval-001",
                "status": "APPROVED",
                "run_id": str(RUN_ID),
                "order_id": "order-001",
                "action_type": "REFUND_ONLY",
                "amount": "399.00",
                "binding_verified": True,
            },
        }
    )


def test_refund_durable_fingerprint_binds_the_approval_reference() -> None:
    base = state()
    first = refund_write_intent(
        base,
        order_id="order-001",
        reason_code="STALLED_LOGISTICS",
        requested_amount=Decimal("399.00"),
        approval_request_id="approval-001",
    )
    persisted = advance(base, write_intent=first.to_state_intent())

    replay = refund_write_intent(
        persisted,
        order_id="order-001",
        reason_code="STALLED_LOGISTICS",
        requested_amount=Decimal("399.00"),
        approval_request_id="approval-001",
    )
    assert replay.idempotency_key == first.idempotency_key

    with pytest.raises(WriteIntentConflictError):
        refund_write_intent(
            persisted,
            order_id="order-001",
            reason_code="STALLED_LOGISTICS",
            requested_amount=Decimal("399.00"),
            approval_request_id="approval-002",
        )


def test_return_durable_fingerprint_binds_the_approval_reference() -> None:
    base = advance(
        state(),
        approval=ApprovalSnapshot(
            approval_request_id="approval-return-001",
            status="APPROVED",
            run_id=RUN_ID,
            order_id="order-001",
            action_type="RETURN_REFUND",
            amount=Decimal("399.00"),
            binding_verified=True,
        ),
    )
    first = return_write_intent(
        base,
        order_id="order-001",
        reason_code="DELIVERED_RETURN",
        approval_request_id="approval-return-001",
    )
    persisted = advance(base, write_intent=first.to_state_intent())

    replay = return_write_intent(
        persisted,
        order_id="order-001",
        reason_code="DELIVERED_RETURN",
        approval_request_id="approval-return-001",
    )
    assert replay.idempotency_key == first.idempotency_key

    with pytest.raises(WriteIntentConflictError):
        return_write_intent(
            persisted,
            order_id="order-001",
            reason_code="DELIVERED_RETURN",
            approval_request_id="approval-return-002",
        )
