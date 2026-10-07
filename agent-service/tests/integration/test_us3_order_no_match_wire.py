"""T044 (wire half): a clue that matches nothing reaches the customer as ``ORDER_NO_MATCH``.

The unit half (``tests/unit/test_order_no_match.py``) pins the resolution status, the routing table
and the clarification mapping. This half drives the *real* client stack -- ``CommerceTools`` over
``CommerceClient`` with an intercepted transport -- and asserts what the authority saw: one read of
the order list and no per-order read at all, which is the wire-level form of "the fallback order was
never treated as the answer".

Both halves are needed because "nothing was written" and "no candidate was confirmed" are also what
a run that never started produces; the mechanism has to be pinned separately from the observation.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import httpx
import pytest

from app.agent.order_resolution import OrderResolutionStatus, resolve_single_order
from app.agent.request_understanding import RequestIntent, UnderstoodRequest
from app.agent.routing import Decision, Node, route_after_resolve_order
from app.agent.state import AgentState, PrincipalContext, PrincipalRole, RunStatus
from app.api.runs import _clarification_for
from app.clients.auth import AuthContext
from app.clients.commerce_client import CommerceClient
from app.tools.commerce_tools import CommerceTools

_AUTH = AuthContext(token="t044-local-token")  # noqa: S106 -- a fixture, not a credential


class _OneOrderJava:
    """Java as the zero-match case needs it: a single order, and every call recorded."""

    def __init__(self) -> None:
        self.calls: list[str] = []

    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self._handle)

    def _handle(self, request: httpx.Request) -> httpx.Response:
        self.calls.append(f"{request.method} {request.url.path}")
        if request.url.path == "/api/v1/orders":
            return httpx.Response(200, json=[_summary("order-001")])
        # A per-order read or a write. Both are forbidden here: the clue matched no order, so there
        # is nothing to confirm and nothing to change before the customer answers.
        return httpx.Response(500, json={"errorCode": "MUST_NOT_BE_REACHED"})

    def wrote_anything(self) -> bool:
        return any(call.startswith("POST ") for call in self.calls)


def _understood() -> UnderstoodRequest:
    return UnderstoodRequest(
        intent=RequestIntent.REFUND_REQUEST,
        mentions_logistics_problem=False,
        mentioned_order_id=None,
        mentioned_product_hint="耳机",
    )


def _summary(order_id: str) -> dict[str, str]:
    return {
        "orderId": order_id,
        "productSummary": "Stainless Steel Water Bottle",
        "status": "DELIVERED",
        "createdAt": datetime(2026, 9, 1, tzinfo=UTC).isoformat(),
    }


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
async def test_a_clue_matching_no_order_never_reads_or_writes_the_fallback_order() -> None:
    java = _OneOrderJava()
    client = CommerceClient(
        base_url="http://commerce.test/api/v1",
        timeout_seconds=5.0,
        transport=java.transport(),
    )
    tools = CommerceTools(client=client, auth=_AUTH)

    result = await resolve_single_order(_understood(), tools=tools)

    assert result.status is OrderResolutionStatus.NO_MATCH
    assert result.candidate_order_ids == ["order-001"]
    assert result.clue_matched_nothing is True
    assert result.resolved_order_id is None
    # The wire evidence: the list was read and nothing else -- no GET of the fallback order, and no
    # POST of either kind, because the customer has not answered yet.
    assert java.calls == ["GET /api/v1/orders"]
    assert not java.wrote_anything()

    state = _state(
        candidate_order_ids=list(result.candidate_order_ids),
        clue_matched_nothing=result.clue_matched_nothing,
    )
    assert (
        route_after_resolve_order(state, Decision(resolution_attempted=True)) is Node.WAITING_USER
    )
    clarification = _clarification_for(RunStatus.WAITING_USER, state)

    assert clarification is not None
    assert clarification.kind == "ORDER_NO_MATCH"
    assert clarification.candidate_order_ids == ["order-001"]
