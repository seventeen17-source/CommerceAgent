"""T063 versioned, deterministic US5 safety eval (not a live Java/DB gate)."""

from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

import pytest

from app.agent.failure_policy import may_retry_read
from app.agent.nodes import build_lifecycle_nodes
from app.agent.routing import (
    Node,
    route_after_eligibility,
    safe_stop_reason_for,
    terminal_decision_for,
)
from app.agent.state import AgentState, RunStatus
from app.clients.models import TicketResult
from app.tools.models import ToolEnvelope

_DATASET = (
    Path(__file__).resolve().parents[3]
    / "eval"
    / "datasets"
    / "dev"
    / "us5_failure_recovery.json"
)
_DOCUMENT = json.loads(_DATASET.read_text(encoding="utf-8"))
CASES: list[dict[str, object]] = _DOCUMENT["cases"]


class ScriptedTickets:
    """Fake only the Java boundary; execute the production Agent lifecycle functions."""

    def __init__(self, response: dict[str, object]) -> None:
        self.response = response
        self.calls: list[dict[str, object]] = []

    async def create_support_ticket(self, **kwargs: object) -> ToolEnvelope[TicketResult]:
        self.calls.append(kwargs)
        if self.response["success"]:
            return ToolEnvelope[TicketResult](
                success=True,
                data=TicketResult(
                    ticketId=self.response["ticketId"], status=self.response["status"]
                ),
                latencyMs=3,
                traceId="eval-java-trace",
            )
        return ToolEnvelope[TicketResult](
            success=False,
            errorCode=self.response["errorCode"],
            retryable=False,
            latencyMs=3,
        )


def _state(case: dict[str, object]) -> AgentState:
    payload: dict[str, object] = {
        "run_id": uuid4(),
        "principal": {"user_id": "customer-001", "role": "CUSTOMER"},
        "user_request": "Please review this after-sales issue",
        "resolved_order_id": "order-001",
        "intent": "REFUND_REQUEST",
    }
    payload.update(case["state"])
    return AgentState.model_validate(payload)


@pytest.mark.parametrize("case", CASES, ids=[case["scenarioId"] for case in CASES])
@pytest.mark.asyncio
async def test_us5_failure_recovery_eval(case: dict[str, object]) -> None:
    expected = case["expect"]
    state = _state(case)
    traces: list[object] = []
    scripted = ScriptedTickets(case["toolResult"]) if "toolResult" in case else None
    lifecycle = build_lifecycle_nodes(scripted, traces.append)

    if case["category"] == "manual_review":
        assert route_after_eligibility(state) is Node.ESCALATE_OR_SAFE_STOP
        result = await lifecycle[Node.ESCALATE_OR_SAFE_STOP]({"state": state})
        state = result["state"]
        assert len(traces) == 1
        assert traces[0].tool_name == "create_support_ticket"
    elif case["category"] in {"max_step", "conflicting_state"}:
        assert route_after_eligibility(state) is Node.SAFE_STOP
    else:
        assert safe_stop_reason_for(state) is not None

    terminal = terminal_decision_for(state)
    # A budget/conflict refusal is a routing-level safe stop; terminal_decision_for
    # covers manual review and repeated-no-progress, not every control-plane refusal.
    reason = safe_stop_reason_for(state)
    if reason is not None:
        status = RunStatus.SAFE_STOP
        reason_code = reason.value
    else:
        status = terminal.status
        reason_code = terminal.reason.value if terminal.reason else None

    assert status.value == expected["terminalStatus"]
    assert reason_code == expected["reason"]
    assert (len(scripted.calls) if scripted is not None else 0) == expected["ticketCount"]
    assert not any(
        entry.tool_name in {"create_refund_request", "create_return_request"}
        for entry in state.tool_history
    )
    if status is RunStatus.ESCALATED:
        assert state.support_ticket_id is not None
    else:
        assert state.support_ticket_id is None


def test_us5_dataset_has_the_four_required_failure_families() -> None:
    assert _DOCUMENT["datasetVersion"] == "us5-t063-v1"
    assert _DOCUMENT["kind"] == "deterministic-agent-safety"
    assert {case["category"] for case in CASES} == {
        "dependency_failure",
        "conflicting_state",
        "max_step",
        "manual_review",
    }
    assert len({case["scenarioId"] for case in CASES}) == len(CASES)
    for case in CASES:
        assert case["expect"]["unsafeWriteCount"] == 0


def test_us5_failure_eval_detects_the_transient_retry_budget_boundary() -> None:
    case = next(x for x in CASES if x["scenarioId"] == "us5-dependency-retry-exhausted")
    state = _state(case)
    assert not may_retry_read(state.tool_history[-1], state)
