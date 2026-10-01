"""Unit tests for the production assembly and the two rules ``/input`` adds.

No database and no network: the graph is assembled with a stub Tool layer, the Tool *registry* is
real (it is what checks that every registered capability is bound), and the request rules are
checked against the state model that owns the constraint.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.agent.routing import Node
from app.agent.state import AgentState, WriteIntent, WriteOutcome
from app.agent.wiring import build_agent_graph
from app.api.runs import _USER_REQUEST_MAX, GraphRunDriver, _merge_user_input
from app.config.settings import Settings
from app.tools import CommerceTools


async def unused_persist(
    state: AgentState, intent: WriteIntent, outcome: WriteOutcome
) -> AgentState:
    raise AssertionError("assembling the graph must not persist anything")


def make_state(**overrides: Any) -> AgentState:
    base: dict[str, Any] = {
        "run_id": uuid4(),
        "principal": {"user_id": "customer-001", "role": "CUSTOMER"},
        "user_request": "我的包裹卡在路上了，我要退款",
        "intent": None,
    }
    base.update(overrides)
    return AgentState.model_validate(base)


def test_the_production_graph_contains_every_node() -> None:
    """An incomplete node map raises in ``build_graph``, so this pins the assembled result."""

    graph = build_agent_graph(
        tools=CommerceTools(client=MagicMock(), auth=MagicMock()),
        model_client=MagicMock(),
        persist_intent=unused_persist,
    )

    assembled = {str(name) for name in graph.get_graph().nodes}
    assert {str(node) for node in Node} <= assembled


def test_the_request_cap_matches_the_state_model() -> None:
    """The constant is a copy, so this is the assertion that keeps it from drifting."""
    assert _USER_REQUEST_MAX == 4000
    make_state(user_request="x" * _USER_REQUEST_MAX)
    with pytest.raises(Exception, match="user_request"):
        make_state(user_request="x" * (_USER_REQUEST_MAX + 1))


def test_a_follow_up_is_appended_and_never_truncated() -> None:
    state = make_state(user_request="我要退款")

    merged = _merge_user_input(state, "补充：订单号 order-001")

    assert merged.startswith("我要退款")
    assert merged.endswith("补充：订单号 order-001")


def test_a_follow_up_that_does_not_fit_is_refused_rather_than_cut() -> None:
    state = make_state(user_request="x" * (_USER_REQUEST_MAX - 5))

    with pytest.raises(HTTPException) as refused:
        _merge_user_input(state, "y" * 100)

    assert refused.value.status_code == 422
    assert refused.value.detail == "USER_REQUEST_TOO_LONG"


_PLACEHOLDER_SECRET = "test-placeholder-not-a-real-secret"

_PLACEHOLDER_ISSUER = "test-issuer"


def test_the_real_driver_refuses_before_a_run_exists() -> None:
    """A run nobody can advance would be a RUNNING row that is not resumable by design."""
    driver = GraphRunDriver()

    with pytest.raises(HTTPException) as refused:
        driver.check(
            Settings(
                environment="test",
                commerce_jwt_issuer=_PLACEHOLDER_ISSUER,
                commerce_jwt_secret=_PLACEHOLDER_SECRET,
                # Named explicitly because Settings is a BaseSettings: without this the answer would
                # depend on whatever the environment happens to carry.
                model_api_key=None,
            )
        )

    assert refused.value.status_code == 503
    assert refused.value.detail == "MODEL_API_KEY_NOT_CONFIGURED"
