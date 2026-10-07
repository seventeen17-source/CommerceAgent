"""T044 (presentation layer): a clue that matches no order is a question, never a resolution.

Why this file exists as its own suite: every other ambiguity test in the repo ends with *several*
candidates, so "one candidate left" has up to now always meant "Java confirmed it". The dangerous
case this file pins is the one where a single visible order does **not** back the clue the customer
gave -- resolving that order would answer a question the clue never answered, and it would look
exactly like a success downstream.

The two halves are deliberate: the resolution half asserts what the node returns *and* that it never
asked Java about that fallback order; the routing/wire half asserts what the customer is told.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.agent.order_resolution import (
    OrderResolution,
    OrderResolutionStatus,
    resolve_single_order,
)
from app.agent.request_understanding import RequestIntent, UnderstoodRequest
from app.agent.routing import Decision, Node, route_after_resolve_order
from app.agent.state import AgentState, PrincipalContext, PrincipalRole, RunStatus
from app.api.runs import _clarification_for
from app.clients.models import OrderSummary
from app.tools.models import ToolEnvelope


class _ClueOrderTools:
    """The two reads resolution may use, with ``get_order`` recorded and never answered.

    Raising rather than returning keeps the assertion honest: "we did not read a candidate" is
    checked by the recorded calls below, and a fallback that *did* reach for one fails loudly here
    instead of quietly depending on what the double happens to return.
    """

    def __init__(self, orders: list[OrderSummary]) -> None:
        self._orders = orders
        self.list_calls = 0
        self.get_calls: list[str] = []

    async def list_user_orders(self) -> ToolEnvelope[list[OrderSummary]]:
        self.list_calls += 1
        return ToolEnvelope(success=True, data=self._orders, latency_ms=1)

    async def get_order(self, order_id: str) -> ToolEnvelope[object]:
        self.get_calls.append(order_id)
        raise AssertionError("a clue that matched nothing must not be confirmed as the answer")


def _understood(hint: str) -> UnderstoodRequest:
    return UnderstoodRequest(
        intent=RequestIntent.REFUND_REQUEST,
        mentions_logistics_problem=False,
        mentioned_order_id=None,
        mentioned_product_hint=hint,
    )


def _summary(order_id: str, product: str, day: int) -> OrderSummary:
    return OrderSummary.model_validate(
        {
            "orderId": order_id,
            "productSummary": product,
            "status": "DELIVERED",
            "createdAt": datetime(2026, 9, day, tzinfo=UTC).isoformat(),
        }
    )


def _state(**overrides: Any) -> AgentState:
    values: dict[str, Any] = {
        "run_id": uuid4(),
        "principal": PrincipalContext(user_id="customer-001", role=PrincipalRole.CUSTOMER),
        "user_request": "把上次买的耳机退掉",
        "intent": "REFUND_REQUEST",
    }
    values.update(overrides)
    return AgentState.model_validate(values)


@pytest.mark.asyncio
async def test_one_order_that_the_clue_does_not_match_is_asked_about_not_resolved() -> None:
    """The single most dangerous shape: one visible order, and a clue that does not describe it."""
    tools = _ClueOrderTools([_summary("order-001", "运动水壶", day=1)])

    result = await resolve_single_order(_understood("耳机"), tools=tools)

    assert result.status is OrderResolutionStatus.NO_MATCH
    # The fallback candidate is still listed, because that is what the customer gets asked about.
    assert result.candidate_order_ids == ["order-001"]
    assert result.clue_matched_nothing is True
    assert result.resolved_order_id is None
    assert result.order is None
    # And the fallback was never confirmed: the clue, not the count, decides if it is an answer.
    assert tools.get_calls == []


@pytest.mark.asyncio
async def test_two_orders_that_the_clue_does_not_match_fall_back_to_both() -> None:
    tools = _ClueOrderTools(
        [_summary("order-001", "运动水壶", day=1), _summary("order-002", "登山杖", day=2)]
    )

    result = await resolve_single_order(_understood("耳机"), tools=tools)

    assert result.status is OrderResolutionStatus.NO_MATCH
    assert result.candidate_order_ids == ["order-002", "order-001"]
    assert result.clue_matched_nothing is True
    assert tools.get_calls == []


def test_no_match_without_the_flag_is_not_constructible() -> None:
    """The invariant is what makes the state readable: NO_MATCH means the clue matched nothing."""
    with pytest.raises(ValidationError):
        OrderResolution(
            status=OrderResolutionStatus.NO_MATCH,
            candidate_order_ids=["order-001"],
            clue_matched_nothing=False,
        )


def test_ambiguous_keeps_its_own_invariant() -> None:
    """The new state must not have loosened the old one: AMBIGUOUS still needs two candidates."""
    with pytest.raises(ValidationError):
        OrderResolution(
            status=OrderResolutionStatus.AMBIGUOUS,
            candidate_order_ids=["order-001"],
        )


def test_a_zero_match_with_one_fallback_routes_to_waiting_user_not_to_a_safe_stop() -> None:
    """Zero match is a question, not a refusal: it must not be read as ORDER_UNRESOLVED."""
    state = _state(clue_matched_nothing=True, candidate_order_ids=["order-001"])

    assert (
        route_after_resolve_order(state, Decision(resolution_attempted=True)) is Node.WAITING_USER
    )


def test_a_zero_match_with_several_fallbacks_is_reported_as_no_match() -> None:
    """The clue matched *nothing*, so "several orders look plausible" would misdescribe it."""
    state = _state(
        clue_matched_nothing=True,
        candidate_order_ids=["demo-order-001", "demo-order-002"],
    )

    clarification = _clarification_for(RunStatus.WAITING_USER, state)

    assert clarification is not None
    assert clarification.kind == "ORDER_NO_MATCH"
    assert clarification.candidate_order_ids == ["demo-order-001", "demo-order-002"]
