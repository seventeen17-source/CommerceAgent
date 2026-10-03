"""The runtime seam against a real database: version tracking and the two writes.

The wrapper's promise is about the *database*, not about Python: every write is bound to the version
the previous one produced, a payload snapshot cannot move a status, and the end of a run is a
transition. An in-memory double re-implements the version and the lock, so a test against one proves
only that the double agrees with itself - which is why these run against PostgreSQL and skip when no
database is reachable.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from typing import Any
from uuid import uuid4

import pytest

from app.agent.routing import Decision, Node, TerminalDecision
from app.agent.runtime import FAILED_RUN_ERROR_CODE, RunSession, drive_graph
from app.agent.state import (
    AgentState,
    PrincipalContext,
    PrincipalRole,
    RunStatus,
    WriteIntent,
    WriteOutcome,
    WriteStatus,
    advance,
)
from app.agent.tool_tracing import ToolCallFacts
from app.tools.models import ToolEnvelope, ToolRisk
from app.trace.checkpoint import RiskLevel, RunRecord, ToolTraceStatus
from app.trace.db import ConnectionFactory
from app.trace.errors import RunStoreError, RunVersionConflictError
from app.trace.store import PostgresRunStore

pytestmark = pytest.mark.usefixtures("connection_factory")


def build_state(**overrides: Any) -> AgentState:
    values: dict[str, Any] = {
        "run_id": uuid4(),
        "principal": PrincipalContext(user_id="customer-001", role=PrincipalRole.CUSTOMER),
        "user_request": "My shipment has not moved for days. Can I get a refund?",
        "intent": "LOGISTICS_REFUND",
        "resolved_order_id": "order-001",
    }
    values.update(overrides)
    return AgentState.model_validate(values)


def refund_intent() -> WriteIntent:
    return WriteIntent(
        action="CREATE_REFUND_REQUEST",
        target_id="order-001",
        idempotency_key="0123456789abcdef",
        request_fingerprint="a" * 64,
    )


@pytest.fixture
def store_and_run(
    connection_factory: ConnectionFactory,
) -> Iterator[tuple[PostgresRunStore, RunRecord]]:
    """A real store with one freshly created run, removed afterwards."""
    store = PostgresRunStore(connection_factory)
    record = store.create_run(
        state=build_state(),
        model_name="gpt-4o-mini",
        prompt_version="t032-e2e",
        current_node="created",
        next_action="understand_request",
    )
    try:
        yield store, record
    finally:
        store.delete_run(record.run_id)


class ScriptedGraph:
    """A graph that yields chunks the way the real one does, so the driver meets the real store."""

    def __init__(self, chunks: list[dict[str, Any]]) -> None:
        self._chunks = chunks

    async def astream(self, value: Any, *, stream_mode: str) -> AsyncIterator[dict[str, Any]]:
        for chunk in self._chunks:
            yield chunk


class FailingGraph:
    """A graph that blows up mid-invocation: the case the failure path exists for."""

    def __init__(self, error: Exception) -> None:
        self._error = error

    async def astream(self, value: Any, *, stream_mode: str) -> AsyncIterator[dict[str, Any]]:
        raise self._error
        yield {}  # unreachable, but this is what makes the method an async generator


def test_checkpointing_advances_the_version_and_keeps_the_row_in_step(
    store_and_run: tuple[PostgresRunStore, RunRecord],
) -> None:
    store, record = store_and_run
    session = RunSession(store, record)

    session.checkpoint(
        state=advance(session.state, step_count=1),
        current_node="understand",
        next_action="resolve_order",
    )
    session.checkpoint(
        state=advance(session.state, step_count=2),
        current_node="resolve_order",
        next_action="waiting_user",
    )

    stored = store.get_run(record.run_id)
    assert session.record.version == 3
    assert stored.version == 3
    assert stored.current_node == "resolve_order"
    assert stored.next_action == "waiting_user"
    assert stored.step_count == 2


def test_a_payload_snapshot_cannot_move_the_status(
    store_and_run: tuple[PostgresRunStore, RunRecord],
) -> None:
    """The guard T032 leans on: facts go through a checkpoint, lifecycle goes through transition."""
    store, record = store_and_run
    session = RunSession(store, record)

    with pytest.raises(RunStoreError):
        session.checkpoint(
            state=advance(session.state, status=RunStatus.SAFE_STOP),
            current_node="finalize",
        )

    assert store.get_run(record.run_id).status is RunStatus.RUNNING


def test_a_stale_version_is_refused_and_the_loser_changes_nothing(
    store_and_run: tuple[PostgresRunStore, RunRecord],
) -> None:
    """This is the database behind the 409: the second writer is told, not silently overwritten."""
    store, record = store_and_run
    winner = RunSession(store, record)
    loser = RunSession(store, record)

    winner.checkpoint(
        state=advance(winner.state, step_count=1),
        current_node="understand",
        next_action="resolve_order",
    )
    with pytest.raises(RunVersionConflictError):
        loser.checkpoint(
            state=advance(loser.state, step_count=9),
            current_node="understand",
            next_action="resolve_order",
        )

    stored = store.get_run(record.run_id)
    assert stored.step_count == 1
    assert stored.version == 2


@pytest.mark.asyncio
async def test_the_intent_is_readable_from_the_row_once_the_callback_returns(
    connection_factory: ConnectionFactory,
) -> None:
    """The money path depends on this: after the callback, the key outlives the process."""
    store = PostgresRunStore(connection_factory)
    record = store.create_run(
        state=build_state(),
        model_name="gpt-4o-mini",
        prompt_version="t032-e2e",
        current_node="created",
    )
    try:
        session = RunSession(store, record)
        intent = refund_intent()

        await session.persist_intent(
            session.state, intent, WriteOutcome(status=WriteStatus.PENDING)
        )

        payload = store.get_run(record.run_id).to_state()
        assert payload is not None
        assert payload.write_intent == intent
        assert payload.write.status is WriteStatus.PENDING
        assert payload.write_intent.idempotency_key == intent.idempotency_key
    finally:
        store.delete_run(record.run_id)


@pytest.mark.asyncio
async def test_driving_a_walk_ends_the_run_through_a_transition(
    store_and_run: tuple[PostgresRunStore, RunRecord],
) -> None:
    store, record = store_and_run
    session = RunSession(store, record)
    terminal = TerminalDecision(status=RunStatus.WAITING_USER)
    graph = ScriptedGraph(
        [
            {Node.UNDERSTAND: {"state": advance(session.state, step_count=1)}},
            {Node.WAITING_USER: {"state": session.state, "decision": Decision(terminal=terminal)}},
        ]
    )

    final = await drive_graph(graph, session)  # type: ignore[arg-type]

    stored = store.get_run(record.run_id)
    assert final.status is RunStatus.WAITING_USER
    assert stored.status is RunStatus.WAITING_USER
    assert stored.current_node == "waiting_user"
    # The run is resumable precisely because WAITING_USER is not terminal.
    assert stored.resumable is True


@pytest.mark.asyncio
async def test_a_failing_walk_leaves_a_failed_row_and_not_a_running_one(
    store_and_run: tuple[PostgresRunStore, RunRecord],
) -> None:
    """RUNNING belongs to a live executor, so a crashed run must not be left wearing it."""
    store, record = store_and_run
    session = RunSession(store, record)

    with pytest.raises(RuntimeError, match="the tool layer exploded"):
        await drive_graph(  # type: ignore[arg-type]
            FailingGraph(RuntimeError("the tool layer exploded")), session
        )

    stored = store.get_run(record.run_id)
    assert stored.status is RunStatus.FAILED
    assert stored.error_code == FAILED_RUN_ERROR_CODE


@pytest.mark.asyncio
async def test_a_finished_call_becomes_a_queryable_trace_row(
    store_and_run: tuple[PostgresRunStore, RunRecord],
) -> None:
    """The evidence row keeps the Tool's own latency and the backend's correlation id."""
    store, record = store_and_run
    session = RunSession(store, record)
    envelope = ToolEnvelope[Any].model_validate(
        {
            "success": True,
            "data": {"orderId": "order-001"},
            "latencyMs": 42,
            "traceId": "java-trace-0009",
        }
    )

    session.record_trace(
        ToolCallFacts(
            step_index=4,
            tool_name="create_refund_request",
            envelope=envelope,
            input_summary={"orderId": "order-001"},
        ),
        ToolRisk.HIGH_WRITE,
    )

    traces = store.list_tool_traces(record.run_id)
    assert len(traces) == 1
    stored = traces[0]
    assert stored.latency_ms == 42
    assert stored.trace_id == "java-trace-0009"
    assert stored.risk_level is RiskLevel.HIGH
    assert stored.status is ToolTraceStatus.SUCCESS
    assert stored.step_index == 4
    assert stored.input_summary == {"orderId": "order-001"}
    assert stored.output_summary == {}


@pytest.mark.asyncio
async def test_a_call_whose_backend_sent_no_id_is_still_findable(
    store_and_run: tuple[PostgresRunStore, RunRecord],
) -> None:
    """A local id has to be written, because an empty column cannot be told from a lost row."""
    store, record = store_and_run
    session = RunSession(store, record)
    envelope = ToolEnvelope[Any].model_validate(
        {"success": True, "data": {"orderId": "order-001"}, "latencyMs": 7}
    )

    session.record_trace(
        ToolCallFacts(step_index=1, tool_name="get_logistics", envelope=envelope),
        ToolRisk.READ_PRIVACY_MEDIUM,
    )

    stored = store.list_tool_traces(record.run_id)[0]
    assert stored.trace_id.startswith("local-")
    assert stored.output_summary == {"traceIdSource": "LOCAL"}
    assert stored.risk_level is RiskLevel.MEDIUM
