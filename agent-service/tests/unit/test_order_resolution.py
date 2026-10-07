"""T030 tests for single-candidate order resolution."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from app.agent.order_resolution import OrderResolutionStatus, resolve_single_order
from app.agent.request_understanding import RequestIntent, UnderstoodRequest
from app.clients.models import OrderSnapshot, OrderSummary
from app.tools.models import ToolEnvelope


class _FakeOrderTools:
    def __init__(
        self,
        *,
        orders: list[OrderSummary] | None = None,
        details: dict[str, ToolEnvelope[OrderSnapshot]] | None = None,
        list_result: ToolEnvelope[list[OrderSummary]] | None = None,
    ) -> None:
        self.orders = [] if orders is None else orders
        self.details = {} if details is None else details
        self.list_result = list_result
        self.list_calls = 0
        self.get_calls: list[str] = []

    async def list_user_orders(self) -> ToolEnvelope[list[OrderSummary]]:
        self.list_calls += 1
        if self.list_result is not None:
            return self.list_result
        return ToolEnvelope(success=True, data=self.orders, latencyMs=1)

    async def get_order(self, order_id: str) -> ToolEnvelope[OrderSnapshot]:
        self.get_calls.append(order_id)
        return self.details[order_id]


def _understood(order_id: str | None) -> UnderstoodRequest:
    return UnderstoodRequest(
        intent=RequestIntent.REFUND_REQUEST,
        mentions_logistics_problem=True,
        mentioned_order_id=order_id,
    )


def _summary(order_id: str) -> OrderSummary:
    return OrderSummary.model_validate(
        {
            "orderId": order_id,
            "productSummary": "Synthetic item",
            "status": "SHIPPED",
            "createdAt": datetime(2026, 9, 1, tzinfo=UTC),
        }
    )


def _snapshot(order_id: str) -> OrderSnapshot:
    return OrderSnapshot.model_validate(
        {
            "orderId": order_id,
            "status": "SHIPPED",
            "totalAmount": Decimal("199.00"),
            "currency": "CNY",
            "items": [],
            "afterSalesStatus": None,
        }
    )


@pytest.mark.asyncio
async def test_mentioned_order_is_not_resolved_until_java_confirms_it() -> None:
    tools = _FakeOrderTools(
        details={
            "order-001": ToolEnvelope(
                success=True,
                data=_snapshot("order-001"),
                latencyMs=2,
                traceId="trace-order-001",
            )
        }
    )

    result = await resolve_single_order(_understood("order-001"), tools=tools)

    assert result.status is OrderResolutionStatus.RESOLVED
    assert result.resolved_order_id == "order-001"
    assert result.order is not None
    assert tools.list_calls == 0
    assert tools.get_calls == ["order-001"]


@pytest.mark.asyncio
async def test_cross_owner_or_missing_order_never_becomes_resolved() -> None:
    tools = _FakeOrderTools(
        details={
            "order-002": ToolEnvelope[OrderSnapshot](
                success=False,
                errorCode="ORDER_NOT_FOUND",
                retryable=False,
                latencyMs=2,
                traceId="trace-hidden",
            )
        }
    )

    result = await resolve_single_order(_understood("order-002"), tools=tools)

    assert result.status is OrderResolutionStatus.UNRESOLVED
    assert result.candidate_order_ids == ["order-002"]
    assert result.resolved_order_id is None
    assert result.order is None
    assert result.error_code == "ORDER_NOT_FOUND"


@pytest.mark.asyncio
async def test_one_visible_order_is_still_confirmed_through_get_order() -> None:
    tools = _FakeOrderTools(
        orders=[_summary("order-001")],
        details={
            "order-001": ToolEnvelope(
                success=True,
                data=_snapshot("order-001"),
                latencyMs=2,
            )
        },
    )

    result = await resolve_single_order(_understood(None), tools=tools)

    assert result.status is OrderResolutionStatus.RESOLVED
    assert tools.list_calls == 1
    assert tools.get_calls == ["order-001"]


@pytest.mark.asyncio
async def test_multiple_visible_orders_are_ambiguous_and_never_guessed() -> None:
    tools = _FakeOrderTools(orders=[_summary("order-001"), _summary("order-003")])

    result = await resolve_single_order(_understood(None), tools=tools)

    assert result.status is OrderResolutionStatus.AMBIGUOUS
    assert result.candidate_order_ids == ["order-001", "order-003"]
    assert result.resolved_order_id is None
    assert tools.get_calls == []


@pytest.mark.asyncio
async def test_empty_order_list_is_unresolved_without_fabricating_an_id() -> None:
    tools = _FakeOrderTools()

    result = await resolve_single_order(_understood(None), tools=tools)

    assert result.status is OrderResolutionStatus.UNRESOLVED
    assert result.candidate_order_ids == []
    assert result.resolved_order_id is None


@pytest.mark.asyncio
async def test_list_failure_is_not_misrepresented_as_no_orders() -> None:
    tools = _FakeOrderTools(
        list_result=ToolEnvelope[list[OrderSummary]](
            success=False,
            errorCode="DEPENDENCY_UNAVAILABLE",
            retryable=True,
            latencyMs=5,
        )
    )

    result = await resolve_single_order(_understood(None), tools=tools)

    assert result.status is OrderResolutionStatus.UNRESOLVED
    assert result.error_code == "DEPENDENCY_UNAVAILABLE"
    assert result.retryable is True


def _product_summary(order_id: str, product: str, day: int = 1) -> OrderSummary:
    return OrderSummary.model_validate(
        {
            "orderId": order_id,
            "productSummary": product,
            "status": "SHIPPED",
            "createdAt": datetime(2026, 9, day, tzinfo=UTC).isoformat(),
        }
    )


def _understood_with_hint(hint: str | None) -> UnderstoodRequest:
    return UnderstoodRequest(
        intent=RequestIntent.REFUND_REQUEST,
        mentions_logistics_problem=True,
        mentioned_order_id=None,
        mentioned_product_hint=hint,
    )


@pytest.mark.asyncio
async def test_a_product_clue_narrows_two_orders_to_one_it_still_confirms() -> None:
    """T044: the clue filters, and the authority still confirms ownership before it is resolved."""
    tools = _FakeOrderTools(
        orders=[
            _product_summary("order-001", "无线蓝牙耳机 Pro"),
            _product_summary("order-002", "运动水壶"),
        ],
        details={"order-001": ToolEnvelope(success=True, data=_snapshot("order-001"), latencyMs=1)},
    )

    result = await resolve_single_order(_understood_with_hint("耳机"), tools=tools)

    assert result.status is OrderResolutionStatus.RESOLVED
    assert result.resolved_order_id == "order-001"
    # The filtered order was read back from Java -- a clue is never treated as an answer.
    assert tools.get_calls == ["order-001"]


@pytest.mark.asyncio
async def test_a_clue_that_matches_nothing_still_asks_and_says_that_it_did() -> None:
    tools = _FakeOrderTools(
        orders=[
            _product_summary("order-001", "运动水壶", day=1),
            _product_summary("order-002", "登山杖", day=2),
        ]
    )

    result = await resolve_single_order(_understood_with_hint("耳机"), tools=tools)

    assert result.status is OrderResolutionStatus.AMBIGUOUS
    # The flag is what lets the caller ask a *broader* question instead of implying the clue worked.
    assert result.clue_matched_nothing is True
    assert result.candidate_order_ids == ["order-002", "order-001"]


@pytest.mark.asyncio
async def test_the_candidate_list_is_capped_so_the_question_stays_answerable() -> None:
    tools = _FakeOrderTools(
        orders=[_product_summary(f"order-{day:03d}", "耳机", day=day) for day in range(1, 9)]
    )

    result = await resolve_single_order(_understood_with_hint("耳机"), tools=tools)

    assert result.status is OrderResolutionStatus.AMBIGUOUS
    assert len(result.candidate_order_ids) == 5
    assert result.candidate_order_ids[0] == "order-008"
