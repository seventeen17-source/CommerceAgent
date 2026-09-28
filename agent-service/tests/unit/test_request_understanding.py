"""T030 contract tests for request understanding."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.agent.request_understanding import RequestIntent, UnderstoodRequest


def test_understood_request_keeps_only_non_authoritative_language_facts() -> None:
    result = UnderstoodRequest.model_validate(
        {
            "intent": "REFUND_REQUEST",
            "mentionsLogisticsProblem": True,
            "mentionedOrderId": "order-001",
        }
    )

    assert result.intent is RequestIntent.REFUND_REQUEST
    assert result.mentions_logistics_problem is True
    assert result.mentioned_order_id == "order-001"


@pytest.mark.parametrize(
    "forbidden_field",
    [
        "requestedRefundAmount",
        "eligible",
        "approvalRequired",
        "endpoint",
        "url",
        "userId",
    ],
)
def test_understood_request_rejects_business_authority_fields(forbidden_field: str) -> None:
    payload: dict[str, object] = {
        "intent": "REFUND_REQUEST",
        "mentionsLogisticsProblem": True,
        "mentionedOrderId": "order-001",
        forbidden_field: "model-supplied-value",
    }

    with pytest.raises(ValidationError):
        UnderstoodRequest.model_validate(payload)


def test_mentioned_order_id_is_only_a_bounded_identifier_shaped_clue() -> None:
    with pytest.raises(ValidationError):
        UnderstoodRequest.model_validate(
            {
                "intent": "REFUND_REQUEST",
                "mentionsLogisticsProblem": False,
                "mentionedOrderId": "order-001\nforged-trace-line",
            }
        )


def test_unknown_intent_does_not_need_an_order_reference() -> None:
    result = UnderstoodRequest.model_validate(
        {
            "intent": "UNKNOWN",
            "mentionsLogisticsProblem": False,
            "mentionedOrderId": None,
        }
    )

    assert result.intent is RequestIntent.UNKNOWN
    assert result.mentioned_order_id is None
