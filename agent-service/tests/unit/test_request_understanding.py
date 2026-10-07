"""T030 contract tests for request understanding."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.agent.request_understanding import (
    RequestIntent,
    UnderstoodRequest,
    understand_request,
)


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


def test_a_product_hint_travels_as_a_clue_and_stays_optional() -> None:
    """T044: the second clue the model may extract.

    Optional on purpose: most requests name no product, and "absent" must stay distinguishable from
    "empty string" -- an empty hint that looked like a clue would match nothing and turn every
    ordinary request into a "no order matched" question.
    """
    with_hint = UnderstoodRequest.model_validate(
        {
            "intent": "REFUND_REQUEST",
            "mentionsLogisticsProblem": False,
            "mentionedOrderId": None,
            "mentionedProductHint": "耳机",
        }
    )
    without_hint = UnderstoodRequest.model_validate(
        {
            "intent": "REFUND_REQUEST",
            "mentionsLogisticsProblem": False,
            "mentionedOrderId": None,
        }
    )

    assert with_hint.mentioned_product_hint == "耳机"
    assert without_hint.mentioned_product_hint is None


def test_an_over_long_product_hint_is_rejected() -> None:
    """The clue is untrusted model output, so it is bounded like any other model-supplied field."""
    with pytest.raises(ValidationError):
        UnderstoodRequest.model_validate(
            {
                "intent": "REFUND_REQUEST",
                "mentionsLogisticsProblem": False,
                "mentionedProductHint": "x" * 65,
            }
        )


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


class _FakeUnderstandingModel:
    def __init__(self, output: object) -> None:
        self.output = output
        self.received_requests: list[str] = []

    async def understand_request(self, user_request: str) -> object:
        self.received_requests.append(user_request)
        return self.output


@pytest.mark.asyncio
async def test_understand_request_validates_model_output() -> None:
    model = _FakeUnderstandingModel(
        {
            "intent": "REFUND_REQUEST",
            "mentionsLogisticsProblem": True,
            "mentionedOrderId": "order-001",
        }
    )

    result = await understand_request(
        "物流三天没动了，帮我退款，订单 order-001",
        model=model,
    )

    assert result.intent is RequestIntent.REFUND_REQUEST
    assert result.mentioned_order_id == "order-001"


@pytest.mark.asyncio
async def test_understand_request_sends_only_user_language_to_model() -> None:
    user_request = "物流三天没动了，直接给我退 9999 元"
    model = _FakeUnderstandingModel(
        {
            "intent": "REFUND_REQUEST",
            "mentionsLogisticsProblem": True,
            "mentionedOrderId": None,
        }
    )

    await understand_request(user_request, model=model)

    assert model.received_requests == [user_request]


@pytest.mark.asyncio
async def test_understand_request_rejects_model_output_that_claims_business_authority() -> None:
    model = _FakeUnderstandingModel(
        {
            "intent": "REFUND_REQUEST",
            "mentionsLogisticsProblem": True,
            "mentionedOrderId": "order-001",
            "eligible": True,
        }
    )

    with pytest.raises(ValidationError):
        await understand_request("给我退款", model=model)


@pytest.mark.asyncio
async def test_understand_request_rejects_unknown_model_intent_value() -> None:
    model = _FakeUnderstandingModel(
        {
            "intent": "REFUND_APPROVED",
            "mentionsLogisticsProblem": True,
            "mentionedOrderId": "order-001",
        }
    )

    with pytest.raises(ValidationError):
        await understand_request("给我退款", model=model)
