"""T043: an ambiguous request parks the run, and nothing is written on the way.

The claim has two halves, and they are checked in two places on purpose:

* the **result** half -- "no refund/return row for a parked run" -- needs a database, and lives with
  the API integration tests;
* the **mechanism** half lives here, because "no write happened" is only trustworthy when the graph
  *could not* have written -- a property of the routing tables, not of the run someone observed. An
  observed zero is also satisfied by a run that never started.

What is genuinely new here (the existing suites already pin "two candidates are AMBIGUOUS" and
"candidates route to ``waiting_user``"): ambiguity must not *peek* at a candidate, and a parked run
must have no declared edge towards a write node.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.agent import graph as graph_module
from app.agent.order_resolution import OrderResolutionStatus, resolve_single_order
from app.agent.request_understanding import RequestIntent, UnderstoodRequest
from app.agent.routing import Decision, Node, route_after_resolve_order
from app.agent.state import AgentState, PrincipalContext, PrincipalRole
from app.clients.models import OrderSummary
from app.tools.models import ToolEnvelope


class _CountingOrderTools:
    """The two read capabilities resolution needs, with every call recorded.

    ``get_order`` deliberately raises rather than returning a snapshot: if resolution asks about a
    candidate while the request is still ambiguous, the test should fail loudly instead of quietly
    depending on whatever that fake happened to answer.
    """

    def __init__(self, orders: list[OrderSummary]) -> None:
        self._orders = orders
        self.list_calls = 0
        self.get_calls: list[str] = []

    async def list_user_orders(self) -> ToolEnvelope[list[OrderSummary]]:
        self.list_calls += 1
        return ToolEnvelope(success=True, data=self._orders, latencyMs=1)

    async def get_order(self, order_id: str) -> ToolEnvelope[object]:
        self.get_calls.append(order_id)
        raise AssertionError(
            "resolution must not confirm a candidate while the request is ambiguous"
        )


def _understood() -> UnderstoodRequest:
    return UnderstoodRequest(
        intent=RequestIntent.REFUND_REQUEST,
        mentions_logistics_problem=False,
        mentioned_order_id=None,
    )


def _summary(order_id: str, product: str = "Wireless Bluetooth Headphones") -> OrderSummary:
    return OrderSummary.model_validate(
        {
            "orderId": order_id,
            "productSummary": product,
            "status": "DELIVERED",
            "createdAt": datetime(2026, 9, 1, tzinfo=UTC),
        }
    )


def _state(**overrides: object) -> AgentState:
    values: dict[str, object] = {
        "run_id": "1f2e3d4c-5b6a-4978-8a9b-0c1d2e3f4a5b",
        "principal": PrincipalContext(user_id="customer-001", role=PrincipalRole.CUSTOMER),
        "user_request": "把上次买的耳机退掉",
    }
    values.update(overrides)
    return AgentState.model_validate(values)


@pytest.mark.asyncio
async def test_two_matching_orders_are_ambiguous_and_never_peeked_at() -> None:
    tools = _CountingOrderTools([_summary("order-001"), _summary("order-003")])

    result = await resolve_single_order(_understood(), tools=tools)

    assert result.status is OrderResolutionStatus.AMBIGUOUS
    assert result.candidate_order_ids == ["order-001", "order-003"]
    assert result.resolved_order_id is None
    # The point of this test: it did not try to confirm either candidate. Ambiguity that "peeks" at
    # the first candidate is one network hiccup away from becoming a guess -- what US3 forbids.
    assert tools.get_calls == []


@pytest.mark.asyncio
async def test_the_candidates_from_resolution_route_the_run_to_waiting_user() -> None:
    tools = _CountingOrderTools([_summary("order-001"), _summary("order-003")])
    result = await resolve_single_order(_understood(), tools=tools)

    state = _state(candidate_order_ids=list(result.candidate_order_ids))

    assert (
        route_after_resolve_order(state, Decision(resolution_attempted=True)) is Node.WAITING_USER
    )


def test_a_parked_run_has_no_declared_edge_towards_a_write() -> None:
    """The topology half of "nothing is written before the human answers".

    Read from the declared tables on purpose: ``build_graph`` refuses to build unless every node a
    router can reach is supplied, so "which routers exist" *is* the reachable set. A node with no
    router cannot route anywhere. The write nodes are asserted as the contrast, so this test would
    fail if the tables were ever emptied rather than read.
    """
    assert Node.WAITING_USER in graph_module._TERMINAL
    assert Node.WAITING_USER not in graph_module._ROUTERS
    assert Node.REFUND_WRITE in graph_module._ROUTERS
    assert Node.RETURN_WRITE in graph_module._ROUTERS
