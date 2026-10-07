"""T043 (cross-layer half): a run parked on ambiguity must not have written anything.

The unit half (``tests/unit/test_us3_clarification.py``) pins the router: it parks the run, and
no declared edge leaves ``waiting_user``. This half drives the *real* client stack --
``CommerceTools`` over ``CommerceClient`` with an intercepted transport -- and asserts what the
authority actually saw: one read of the order list, and no write call of either kind.

Both halves are needed, for the reason US2 taught the hard way: an observed "nothing was written"
is also what a run that never started produces, so the mechanism must be pinned separately; and a
topology table is not evidence about the wire, so the wire must be pinned too.
"""

from __future__ import annotations

from datetime import UTC, datetime

import httpx
import pytest

from app.agent.order_resolution import OrderResolutionStatus, resolve_single_order
from app.agent.request_understanding import RequestIntent, UnderstoodRequest
from app.agent.routing import Decision, Node, route_after_resolve_order
from app.agent.state import AgentState, PrincipalContext, PrincipalRole
from app.clients.auth import AuthContext
from app.clients.commerce_client import CommerceClient
from app.tools.commerce_tools import CommerceTools

_AUTH = AuthContext(token="t043-local-token")  # noqa: S106 -- a fixture, not a credential


class _TwoOrderJava:
    """Java as the ambiguity case needs it: two orders, and every call recorded."""

    def __init__(self) -> None:
        self.calls: list[str] = []

    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self._handle)

    def _handle(self, request: httpx.Request) -> httpx.Response:
        self.calls.append(f"{request.method} {request.url.path}")
        if request.url.path == "/api/v1/orders":
            return httpx.Response(200, json=[_summary("order-001"), _summary("order-003")])
        # Anything else is a write, or a per-order read that only a *chosen* order justifies.
        # Failing here keeps the test from depending on a separate assertion to notice.
        return httpx.Response(500, json={"errorCode": "MUST_NOT_BE_REACHED"})

    def wrote_anything(self) -> bool:
        return any(call.startswith("POST ") for call in self.calls)


def _understood() -> UnderstoodRequest:
    return UnderstoodRequest(
        intent=RequestIntent.REFUND_REQUEST,
        mentions_logistics_problem=False,
        mentioned_order_id=None,
    )


def _summary(order_id: str) -> dict[str, str]:
    return {
        "orderId": order_id,
        "productSummary": "Wireless Bluetooth Headphones",
        "status": "DELIVERED",
        "createdAt": datetime(2026, 9, 1, tzinfo=UTC).isoformat(),
    }


def _state(**overrides: object) -> AgentState:
    values: dict[str, object] = {
        "run_id": "1f2e3d4c-5b6a-4978-8a9b-0c1d2e3f4a5b",
        "principal": PrincipalContext(user_id="customer-001", role=PrincipalRole.CUSTOMER),
        "user_request": "把上次买的耳机退掉",
    }
    values.update(overrides)
    return AgentState.model_validate(values)


@pytest.mark.asyncio
async def test_an_ambiguous_request_never_reaches_a_write_endpoint() -> None:
    java = _TwoOrderJava()
    client = CommerceClient(
        base_url="http://commerce.test/api/v1",
        timeout_seconds=5.0,
        transport=java.transport(),
    )
    tools = CommerceTools(client=client, auth=_AUTH)

    result = await resolve_single_order(_understood(), tools=tools)

    assert result.status is OrderResolutionStatus.AMBIGUOUS
    assert result.candidate_order_ids == ["order-001", "order-003"]
    assert result.resolved_order_id is None
    # The wire evidence: the list was read, nothing was written. Not "no refund endpoint" --
    # *no POST at all*, because US3 forbids either kind of write before the human answers.
    assert java.calls == ["GET /api/v1/orders"]
    assert not java.wrote_anything()

    state = _state(candidate_order_ids=list(result.candidate_order_ids))
    assert (
        route_after_resolve_order(state, Decision(resolution_attempted=True)) is Node.WAITING_USER
    )
