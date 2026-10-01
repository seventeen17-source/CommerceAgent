"""Unit tests for the durable seam between a graph invocation and the run row.

The store double here is not a recording stub: it enforces the one property the wrapper has to get
right, which is that every write is bound to the version the previous write produced. A stale
version is refused, so a wrapper that forgot to track the version would fail these tests instead of
silently losing an update.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import pytest

from app.agent.graph import CompiledGraph, GraphNode, GraphUpdate, build_graph
from app.agent.nodes import build_lifecycle_nodes
from app.agent.routing import Decision, Node, SafeStopReason, TerminalDecision
from app.agent.runtime import RunSession, drive_graph
from app.agent.state import AgentState, RunStatus, WriteIntent, WriteOutcome, WriteStatus, advance
from app.trace.checkpoint import RunRecord, Transition
from app.trace.errors import RunStoreError
from app.trace.store import RunStore


def make_state(**overrides: Any) -> AgentState:
    base: dict[str, Any] = {
        "run_id": uuid4(),
        "principal": {"user_id": "customer-001", "role": "CUSTOMER"},
        "user_request": "我的包裹卡在路上了，我要退款",
        "intent": None,
    }
    base.update(overrides)
    return AgentState.model_validate(base)


def make_record(state: AgentState) -> RunRecord:
    return RunRecord(
        run_id=state.run_id,
        user_id=state.principal.user_id,
        status=RunStatus.RUNNING,
        version=1,
        model_name="stub-model",
        prompt_version="stub-v1",
        started_at=datetime.now(UTC),
        state=state,
        step_count=state.step_count,
        retry_count=state.retry_count,
    )


class StrictRunStore(RunStore):
    """A store that refuses a write computed from a version that is no longer current."""

    def __init__(self, record: RunRecord) -> None:
        self.record = record
        self.checkpoints: list[tuple[str, str | None]] = []
        self.transitions: list[Transition] = []
        self.versions: list[int] = []

    def _accept(self, expected_version: int) -> None:
        if expected_version != self.record.version:
            raise AssertionError(
                f"stale version {expected_version} handed to the store "
                f"(current is {self.record.version})"
            )
        self.versions.append(expected_version)

    def checkpoint_state(
        self,
        run_id: UUID,
        *,
        expected_version: int,
        state: AgentState,
        current_node: str,
        next_action: str | None = None,
        reason_code: str | None = None,
    ) -> RunRecord:
        self._accept(expected_version)
        self.checkpoints.append((current_node, next_action))
        self.record = self.record.model_copy(
            update={
                "version": self.record.version + 1,
                "state": state,
                "current_node": current_node,
                "next_action": next_action,
                "step_count": state.step_count,
                "retry_count": state.retry_count,
            }
        )
        return self.record

    def transition(self, run_id: UUID, transition: Transition) -> RunRecord:
        self._accept(transition.expected_version)
        self.transitions.append(transition)
        self.record = self.record.model_copy(
            update={"version": self.record.version + 1, "status": transition.status}
        )
        return self.record


def stand_in(name: str) -> GraphNode:
    """A node that records nothing and changes nothing: only the wiring is under test here."""

    async def node(graph: Any) -> GraphUpdate:
        return GraphUpdate(state=graph["state"])

    node.__name__ = name
    return node


def two_step_graph() -> CompiledGraph:
    """understand → resolve_order → waiting_user: the shortest walk with a real terminal node."""

    async def understand(graph: Any) -> GraphUpdate:
        return GraphUpdate(state=advance(graph["state"], intent="REFUND_REQUEST"))

    async def resolve_order(graph: Any) -> GraphUpdate:
        # Two candidates is a question for the user, so this ends in WAITING_USER without evidence.
        state = advance(graph["state"], candidate_order_ids=["order-001", "order-002"])
        return GraphUpdate(state=state)

    nodes: dict[Node, GraphNode] = {
        Node.UNDERSTAND: understand,
        Node.RESOLVE_ORDER: resolve_order,
        Node.DECIDE_EVIDENCE: stand_in("decide_evidence"),
        Node.EXECUTE_EVIDENCE: stand_in("execute_evidence"),
        Node.CHECK_ELIGIBILITY: stand_in("check_eligibility"),
        Node.REFUND_WRITE: stand_in("refund_write"),
        Node.VERIFY: stand_in("verify"),
        **build_lifecycle_nodes(),
    }
    return build_graph(nodes)


class ScriptedGraph:
    """A graph that yields chunks the way the real one does, so a boundary rule can be pinned."""

    def __init__(self, chunks: list[dict[str, Any]]) -> None:
        self._chunks = chunks

    async def astream(self, value: Any, *, stream_mode: str) -> AsyncIterator[dict[str, Any]]:
        for chunk in self._chunks:
            yield chunk


@pytest.mark.asyncio
async def test_every_boundary_is_written_with_the_node_that_followed_it() -> None:
    """The boundary write is deferred by one step so ``next_action`` is a fact, not a guess."""
    state = make_state()
    store = StrictRunStore(make_record(state))
    session = RunSession(store, store.record)

    record = await drive_graph(two_step_graph(), session)

    assert store.checkpoints == [
        ("understand", "resolve_order"),
        ("resolve_order", "waiting_user"),
    ]
    assert store.versions == [1, 2, 3]
    assert record.status is RunStatus.WAITING_USER
    assert record.version == 4


@pytest.mark.asyncio
async def test_the_run_ends_through_a_transition_not_a_checkpoint() -> None:
    """``checkpoint_state`` refuses a status change, so the terminal write cannot be one."""
    state = make_state()
    store = StrictRunStore(make_record(state))
    session = RunSession(store, store.record)

    await drive_graph(two_step_graph(), session)

    assert [node for node, _ in store.checkpoints] == ["understand", "resolve_order"]
    assert len(store.transitions) == 1
    assert store.transitions[0].trigger == "TERMINAL"
    assert store.transitions[0].status is RunStatus.WAITING_USER


@pytest.mark.asyncio
async def test_a_graph_that_stops_without_a_terminal_decision_fails_loudly() -> None:
    state = make_state()
    store = StrictRunStore(make_record(state))
    session = RunSession(store, store.record)
    graph = ScriptedGraph([{Node.UNDERSTAND: {"state": state}}])

    with pytest.raises(RunStoreError, match="without a terminal decision"):
        await drive_graph(graph, session)  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_a_terminal_decision_in_a_scripted_chunk_is_honoured() -> None:
    """The driver reads the control-plane decision; it does not recompute the status itself."""
    state = make_state()
    store = StrictRunStore(make_record(state))
    session = RunSession(store, store.record)
    terminal = TerminalDecision(
        status=RunStatus.SAFE_STOP, reason=SafeStopReason.EVIDENCE_CONTEXT_MISSING
    )
    graph = ScriptedGraph(
        [
            {Node.UNDERSTAND: {"state": state}},
            {Node.SAFE_STOP: {"state": state, "decision": Decision(terminal=terminal)}},
        ]
    )

    record = await drive_graph(graph, session)  # type: ignore[arg-type]

    assert record.status is RunStatus.SAFE_STOP
    assert store.transitions[0].reason_code == SafeStopReason.EVIDENCE_CONTEXT_MISSING.value
    assert store.checkpoints == [("understand", "safe_stop")]


@pytest.mark.asyncio
async def test_the_intent_is_checkpointed_by_the_callback_t031_calls() -> None:
    state = make_state()
    store = StrictRunStore(make_record(state))
    session = RunSession(store, store.record)
    intent = WriteIntent(
        action="CREATE_REFUND_REQUEST",
        target_id="order-001",
        idempotency_key="0123456789abcdef",
        request_fingerprint="a" * 64,
    )

    moved = await session.persist_intent(state, intent, WriteOutcome(status=WriteStatus.PENDING))

    assert moved.write_intent == intent
    assert moved.write.status is WriteStatus.PENDING
    assert store.checkpoints == [(Node.REFUND_WRITE.value, None)]
    assert session.record.version == 2


@pytest.mark.asyncio
async def test_driving_an_already_terminal_run_is_refused() -> None:
    """Otherwise the walk would end at finalize reporting no decision, with a confusing message."""
    state = make_state()
    finished = make_record(state).model_copy(update={"status": RunStatus.COMPLETED})
    store = StrictRunStore(finished)
    session = RunSession(store, store.record)

    with pytest.raises(RunStoreError, match="already terminal"):
        await drive_graph(two_step_graph(), session)

    assert store.checkpoints == []


def test_finishing_names_the_protected_action_the_run_attempted() -> None:
    state = make_state()
    intent = WriteIntent(
        action="CREATE_REFUND_REQUEST",
        target_id="order-001",
        idempotency_key="0123456789abcdef",
        request_fingerprint="a" * 64,
    )
    store = StrictRunStore(make_record(advance(state, write_intent=intent)))
    session = RunSession(store, store.record)

    session.finish(TerminalDecision(status=RunStatus.COMPLETED), current_node=Node.FINALIZE.value)

    assert store.transitions[0].final_action == "CREATE_REFUND_REQUEST"
    assert store.transitions[0].reason_code is None


def test_finishing_without_an_attempted_action_claims_none() -> None:
    state = make_state()
    store = StrictRunStore(make_record(state))
    session = RunSession(store, store.record)

    session.finish(TerminalDecision(status=RunStatus.COMPLETED), current_node=Node.FINALIZE.value)

    assert store.transitions[0].final_action is None
