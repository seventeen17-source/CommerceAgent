"""T017 acceptance: the store contract against a real PostgreSQL database.

Each test exists because a T017 requirement cannot be proven any other way. The mapping is
deliberately explicit:

===========================================================  ==================================
T017 requirement                                             Test
===========================================================  ==================================
persist a run that survives the process                      ``test_created_run_is_readable_...``
checkpoint is the authoritative runtime state                ``test_checkpoint_payload_matches_...``
concurrent resume: at most one winner, no fork               ``test_two_concurrent_resumes_...``
tool trace locates the Java request                          ``test_tool_trace_persists_...``
no raw token / hidden reasoning in checkpoint or trace       ``test_store_refuses_credentials_...``
terminal retention does not grow without bound               ``test_retention_compacts_...``
failed run keeps the trace that explains it                  ``test_retention_keeps_...``
===========================================================  ==================================

``test_two_concurrent_resumes...`` is the one to read first: a status check
alone cannot satisfy it, and it uses real threads against real row locks.
"""

from __future__ import annotations

import threading
from decimal import Decimal
from uuid import UUID, uuid4

import psycopg
import pytest

from app.agent.state import (
    AgentState,
    EligibilitySnapshot,
    PrincipalContext,
    PrincipalRole,
    RunStatus,
)
from app.security.secrets import SensitiveStateError
from app.trace.checkpoint import (
    ResumeRequest,
    RiskLevel,
    ToolTraceRecord,
    ToolTraceStatus,
    Transition,
)
from app.trace.db import ConnectionFactory
from app.trace.errors import (
    ResumeRefusalReason,
    RunNotFoundError,
    RunResumeConflictError,
    RunVersionConflictError,
    TerminalRunError,
)
from app.trace.retention import RetentionPolicy, sweep_terminal_runs
from app.trace.store import PostgresRunStore

_BEARER = "Bearer sk-live-9f8e7d6c5b4a3210"

pytestmark = pytest.mark.usefixtures("connection_factory")


def build_state(**overrides: object) -> AgentState:
    """A realistic run state. Field values mirror the T014 fixture world, not invented ids."""
    values: dict[str, object] = {
        "run_id": uuid4(),
        "principal": PrincipalContext(user_id="customer-001", role=PrincipalRole.CUSTOMER),
        "user_request": "My shipment has not moved for days. Can I get a refund?",
        "intent": "LOGISTICS_REFUND",
        "resolved_order_id": "order-001",
        "eligibility": EligibilitySnapshot(
            eligible=True,
            allowed_action="REFUND_ONLY",
            max_refund_amount=Decimal("199.00"),
            approval_required=False,
            rule_code="LOGISTICS_STALLED_REFUND",
            rule_version=1,
            reason_codes=["LOGISTICS_STALLED"],
        ),
    }
    values.update(overrides)
    return AgentState.model_validate(values)


def create_run(store: PostgresRunStore, state: AgentState):
    return store.create_run(
        state=state,
        model_name="gpt-4o-mini",
        prompt_version="t017-v1",
        current_node="understand_request",
    )


def resume_request(store: PostgresRunStore, run_id: UUID) -> ResumeRequest:
    """Build a resume request from the run's *current* version, the way a real caller must."""
    return ResumeRequest(
        expected_version=store.get_run(run_id).version,
        current_node="resume_after_approval",
    )


# --------------------------------------------------------------------------------------------
# Creation and the checkpoint/row consistency rule
# --------------------------------------------------------------------------------------------


def test_created_run_is_readable_with_version_one(
    connection_factory: ConnectionFactory,
) -> None:
    store = PostgresRunStore(connection_factory)
    state = build_state()
    try:
        created = create_run(store, state)
        reloaded = store.get_run(state.run_id)

        assert created.version == 1
        assert reloaded.run_id == state.run_id
        assert reloaded.status is RunStatus.RUNNING
        assert reloaded.user_id == "customer-001"
        assert reloaded.resolved_order_id == "order-001"
        assert reloaded.state is not None
    finally:
        store.delete_run(state.run_id)


def test_created_run_writes_its_first_checkpoint(
    connection_factory: ConnectionFactory,
) -> None:
    """A run with no checkpoint would be a run that cannot be resumed from step zero."""
    store = PostgresRunStore(connection_factory)
    state = build_state()
    try:
        create_run(store, state)
        checkpoints = store.list_checkpoints(state.run_id)

        assert [checkpoint.version for checkpoint in checkpoints] == [1]
        assert checkpoints[0].status is RunStatus.RUNNING
        assert checkpoints[0].state is not None
        assert checkpoints[0].state["user_request"] == state.user_request
    finally:
        store.delete_run(state.run_id)


def test_checkpoint_payload_matches_the_row_it_was_written_with(
    connection_factory: ConnectionFactory,
) -> None:
    """The drift ``data-model.md`` section 12 forbids, asserted rather than assumed.

    A row saying WAITING_APPROVAL over a payload still saying RUNNING is exactly the false evidence
    that makes "resume" restore a run to a state it is no longer in.
    """
    store = PostgresRunStore(connection_factory)
    state = build_state()
    try:
        created = create_run(store, state)
        transitioned = store.transition(
            state.run_id,
            Transition(
                expected_version=created.version,
                status=RunStatus.WAITING_APPROVAL,
                trigger="INTERRUPT",
                current_node="await_approval",
                next_action="approval",
                step_count=2,
            ),
        )

        assert transitioned.status is RunStatus.WAITING_APPROVAL
        assert transitioned.version == 2
        assert transitioned.state is not None
        # The payload agrees with the row: the values that exist in both places were written from
        # one dict in one statement.
        assert transitioned.state.status is RunStatus.WAITING_APPROVAL
        assert transitioned.state.step_count == 2
        assert transitioned.state.intent == "LOGISTICS_REFUND"
        assert transitioned.current_node == "await_approval"
    finally:
        store.delete_run(state.run_id)


def test_a_transition_that_leaves_a_field_unset_does_not_erase_it(
    connection_factory: ConnectionFactory,
) -> None:
    """Every step would otherwise wipe the previous step's findings."""
    store = PostgresRunStore(connection_factory)
    state = build_state()
    try:
        created = create_run(store, state)
        transitioned = store.transition(
            state.run_id,
            Transition(
                expected_version=created.version,
                status=RunStatus.RUNNING,
                trigger="STEP",
                current_node="decide_next_evidence",
            ),
        )

        assert transitioned.resolved_order_id == "order-001"
        assert transitioned.intent == "LOGISTICS_REFUND"
        assert transitioned.state is not None
        assert transitioned.state.resolved_order_id == "order-001"
    finally:
        store.delete_run(state.run_id)


# --------------------------------------------------------------------------------------------
# Compare-and-swap: a stale writer must lose
# --------------------------------------------------------------------------------------------


def test_stale_transition_is_refused_instead_of_overwriting(
    connection_factory: ConnectionFactory,
) -> None:
    store = PostgresRunStore(connection_factory)
    state = build_state()
    try:
        created = create_run(store, state)
        winner = store.transition(
            state.run_id,
            Transition(
                expected_version=created.version,
                status=RunStatus.WAITING_USER,
                trigger="INTERRUPT",
                current_node="ask_user",
            ),
        )

        # The second writer holds the version it read before the winner wrote.
        with pytest.raises(RunVersionConflictError) as error:
            store.transition(
                state.run_id,
                Transition(
                    expected_version=created.version,
                    status=RunStatus.COMPLETED,
                    trigger="TERMINAL",
                    final_action="CREATE_REFUND_REQUEST",
                ),
            )

        assert error.value.expected_version == created.version
        assert error.value.actual_version == winner.version
        # The winner's result survived: this is the lost update the version column prevents.
        assert store.get_run(state.run_id).status is RunStatus.WAITING_USER
    finally:
        store.delete_run(state.run_id)


def test_terminal_run_cannot_be_advanced(
    connection_factory: ConnectionFactory,
) -> None:
    store = PostgresRunStore(connection_factory)
    state = build_state()
    try:
        created = create_run(store, state)
        completed = store.transition(
            state.run_id,
            Transition(
                expected_version=created.version,
                status=RunStatus.COMPLETED,
                trigger="TERMINAL",
                final_action="CREATE_REFUND_REQUEST",
            ),
        )

        assert completed.completed_at is not None
        assert completed.is_terminal is True
        with pytest.raises(TerminalRunError):
            store.transition(
                state.run_id,
                Transition(
                    expected_version=completed.version,
                    status=RunStatus.RUNNING,
                    trigger="STEP",
                ),
            )
    finally:
        store.delete_run(state.run_id)


def test_unknown_run_is_reported_by_id(connection_factory: ConnectionFactory) -> None:
    store = PostgresRunStore(connection_factory)
    missing = uuid4()

    with pytest.raises(RunNotFoundError) as error:
        store.get_run(missing)

    assert error.value.run_id == str(missing)


# --------------------------------------------------------------------------------------------
# The requirement that needs real row locks
# --------------------------------------------------------------------------------------------


def test_two_concurrent_resumes_of_one_checkpoint_produce_exactly_one_winner(
    connection_factory: ConnectionFactory,
) -> None:
    """T017's hard requirement, proven with real threads against real row locks.

    Both threads read the same ``WAITING_APPROVAL`` checkpoint and the same version, then resume at
    the same instant. Exactly one must succeed; the other must be refused with ``ALREADY_CLAIMED``.

    Why this cannot be tested against an in-memory double: there, the "lock" is whatever the double
    implements, so the test would only prove the double agrees with itself. Here serialisation is
    PostgreSQL's row lock and the detection is the version comparison -- the two mechanisms the
    production path actually uses.

    Why it cannot be tested sequentially: running the two resumes one after the other exercises the
    version check but never the blocking, so a missing ``FOR UPDATE`` would still pass.
    """
    store = PostgresRunStore(connection_factory)
    state = build_state()
    try:
        created = create_run(store, state)
        waiting = store.transition(
            state.run_id,
            Transition(
                expected_version=created.version,
                status=RunStatus.WAITING_APPROVAL,
                trigger="INTERRUPT",
                current_node="await_approval",
                step_count=3,
            ),
        )

        both_ready = threading.Barrier(2)
        outcomes: list[str] = []
        lock = threading.Lock()

        def attempt() -> None:
            # ``expected_version`` is pinned to the shared snapshot: this is the same old checkpoint
            # in both threads, which is the situation that must not fork.
            request = ResumeRequest(
                expected_version=waiting.version, current_node="resume_after_approval"
            )
            both_ready.wait(timeout=10)
            try:
                store.resume(state.run_id, request)
                result = "won"
            except RunResumeConflictError as exc:
                result = f"refused:{exc.reason}"
            with lock:
                outcomes.append(result)

        threads = [threading.Thread(target=attempt) for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=30)

        assert sorted(outcomes) == ["refused:ALREADY_CLAIMED", "won"], (
            f"exactly one resume must win, got {outcomes}"
        )

        # The winner advanced the run exactly once: the version moved by one, not two, so no fork
        # left its trace behind.
        final = store.get_run(state.run_id)
        assert final.status is RunStatus.RUNNING
        assert final.version == waiting.version + 1
        # Both attempts are recorded: the winner as a RESUME checkpoint, and nothing from the loser,
        # because a refused resume must not write.
        assert len(store.list_checkpoints(state.run_id)) == 3
    finally:
        store.delete_run(state.run_id)


def test_resume_of_a_run_that_is_not_waiting_is_refused(
    connection_factory: ConnectionFactory,
) -> None:
    """``RUNNING`` is not a resume target: it belongs to a live executor."""
    store = PostgresRunStore(connection_factory)
    state = build_state()
    try:
        create_run(store, state)

        with pytest.raises(RunResumeConflictError) as error:
            store.resume(state.run_id, resume_request(store, state.run_id))

        assert error.value.reason is ResumeRefusalReason.STATUS_NOT_WAITING
    finally:
        store.delete_run(state.run_id)


def test_resume_of_a_terminal_run_is_refused(
    connection_factory: ConnectionFactory,
) -> None:
    store = PostgresRunStore(connection_factory)
    state = build_state()
    try:
        created = create_run(store, state)
        completed = store.transition(
            state.run_id,
            Transition(
                expected_version=created.version,
                status=RunStatus.COMPLETED,
                trigger="TERMINAL",
                final_action="CREATE_REFUND_REQUEST",
            ),
        )

        with pytest.raises(RunResumeConflictError) as error:
            store.resume(
                state.run_id,
                ResumeRequest(
                    expected_version=completed.version, current_node="resume_after_approval"
                ),
            )

        assert error.value.reason is ResumeRefusalReason.TERMINAL
    finally:
        store.delete_run(state.run_id)


def test_resume_with_a_stale_version_is_refused_without_writing(
    connection_factory: ConnectionFactory,
) -> None:
    store = PostgresRunStore(connection_factory)
    state = build_state()
    try:
        created = create_run(store, state)
        waiting = store.transition(
            state.run_id,
            Transition(
                expected_version=created.version,
                status=RunStatus.WAITING_APPROVAL,
                trigger="INTERRUPT",
                current_node="await_approval",
            ),
        )
        # A stale resume: the caller read the checkpoint before the interrupt transition.
        with pytest.raises(RunResumeConflictError) as error:
            store.resume(
                state.run_id,
                ResumeRequest(
                    expected_version=created.version, current_node="resume_after_approval"
                ),
            )

        assert error.value.reason is ResumeRefusalReason.ALREADY_CLAIMED
        assert error.value.actual_version == waiting.version
        assert store.get_run(state.run_id).version == waiting.version
    finally:
        store.delete_run(state.run_id)


def test_resume_of_a_compacted_checkpoint_is_refused(
    connection_factory: ConnectionFactory,
) -> None:
    """Matching the version is not enough: an empty checkpoint is not a resumable one.

    Reached by compacting a terminal run and then forcing it back to a waiting status through SQL --
    a state the store itself will not produce, which is the point: the check must hold for a row
    that arrived some other way.
    """
    store = PostgresRunStore(connection_factory)
    state = build_state()
    run_id = state.run_id
    try:
        created = create_run(store, state)
        store.transition(
            run_id,
            Transition(
                expected_version=created.version,
                status=RunStatus.COMPLETED,
                trigger="TERMINAL",
                final_action="CREATE_REFUND_REQUEST",
            ),
        )
        assert store.compact_terminal_run(run_id, retain_state=False, retain_tool_trace=False)

        with connection_factory() as connection, connection.transaction():
            with connection.cursor() as cursor:
                cursor.execute(
                    "UPDATE agent.agent_runs SET status = 'WAITING_USER', completed_at = NULL"
                    " WHERE run_id = %s",
                    (run_id,),
                )
                cursor.execute(
                    "UPDATE agent.agent_checkpoints SET state_json = '{}'::jsonb WHERE run_id = %s",
                    (run_id,),
                )

        with pytest.raises(RunResumeConflictError) as error:
            store.resume(run_id, resume_request(store, run_id))

        assert error.value.reason is ResumeRefusalReason.CHECKPOINT_COMPACTED
    finally:
        store.delete_run(run_id)


def test_a_completed_resume_records_itself_as_a_checkpoint(
    connection_factory: ConnectionFactory,
) -> None:
    """The durable record that the resume happened, and what node it continued at."""
    store = PostgresRunStore(connection_factory)
    state = build_state()
    try:
        created = create_run(store, state)
        store.transition(
            state.run_id,
            Transition(
                expected_version=created.version,
                status=RunStatus.WAITING_APPROVAL,
                trigger="INTERRUPT",
                current_node="await_approval",
            ),
        )

        resumed = store.resume(
            state.run_id,
            ResumeRequest(
                expected_version=store.get_run(state.run_id).version,
                current_node="resume_after_approval",
            ),
        )

        assert resumed.status is RunStatus.RUNNING
        checkpoints = store.list_checkpoints(state.run_id)
        assert [checkpoint.version for checkpoint in checkpoints] == [1, 2, 3]
        assert checkpoints[-1].current_node == "resume_after_approval"
        assert checkpoints[-1].status is RunStatus.RUNNING
    finally:
        store.delete_run(state.run_id)


# --------------------------------------------------------------------------------------------
# Tool trace
# --------------------------------------------------------------------------------------------


def test_tool_trace_persists_run_step_and_trace_id(
    connection_factory: ConnectionFactory,
) -> None:
    """``run_id + step_index + trace_id`` is what ties a failed run to one Java request."""
    store = PostgresRunStore(connection_factory)
    state = build_state()
    try:
        create_run(store, state)
        store.record_tool_trace(
            ToolTraceRecord(
                run_id=state.run_id,
                step_index=0,
                tool_name="get_logistics",
                risk_level=RiskLevel.LOW,
                status=ToolTraceStatus.SUCCESS,
                trace_id="a1b2c3d4e5f60718293a4b5c6d7e8f90",
                input_summary={"order_id": "order-001"},
                output_summary={"stalled_hours": 120},
                latency_ms=42,
            )
        )
        store.record_tool_trace(
            ToolTraceRecord(
                run_id=state.run_id,
                step_index=1,
                tool_name="create_refund_request",
                risk_level=RiskLevel.HIGH,
                status=ToolTraceStatus.TIMEOUT,
                trace_id="b1b2c3d4e5f60718293a4b5c6d7e8f91",
                error_code="UPSTREAM_TIMEOUT",
                retryable=False,
                latency_ms=5001,
            )
        )

        traces = store.list_tool_traces(state.run_id)

        assert [trace.step_index for trace in traces] == [0, 1]
        assert traces[0].tool_name == "get_logistics"
        assert traces[0].trace_id == "a1b2c3d4e5f60718293a4b5c6d7e8f90"
        # An unknown write outcome is recorded as such: a reviewer must be able to tell "timed out,
        # outcome unknown" from "the backend said no".
        assert traces[1].status is ToolTraceStatus.TIMEOUT
        assert traces[1].retryable is False
        assert traces[1].risk_level is RiskLevel.HIGH
    finally:
        store.delete_run(state.run_id)


def test_a_step_index_cannot_be_reused(
    connection_factory: ConnectionFactory,
) -> None:
    """Two traces for one step would make "what did step 1 do" have two answers."""
    store = PostgresRunStore(connection_factory)
    state = build_state()
    try:
        create_run(store, state)
        trace = ToolTraceRecord(
            run_id=state.run_id,
            step_index=0,
            tool_name="get_order",
            risk_level=RiskLevel.LOW,
            status=ToolTraceStatus.SUCCESS,
            trace_id="c1b2c3d4e5f60718293a4b5c6d7e8f92",
        )
        store.record_tool_trace(trace)

        with pytest.raises(psycopg.errors.UniqueViolation):
            store.record_tool_trace(trace)
    finally:
        store.delete_run(state.run_id)


# --------------------------------------------------------------------------------------------
# The secret guard at the boundary
# --------------------------------------------------------------------------------------------


def test_store_refuses_a_credential_in_the_checkpoint_payload(
    connection_factory: ConnectionFactory,
) -> None:
    """A credential must fail before the connection is opened, leaving nothing half-written.

    The state is built through ``model_construct`` on purpose: that is how a checkpoint restored
    from a raw dict skips validation, so this proves the *boundary* is the defence, not the model
    validator.
    """
    store = PostgresRunStore(connection_factory)
    run_id = uuid4()
    payload = build_state(run_id=run_id).model_dump(mode="json")
    payload["user_request"] = f"my token is {_BEARER}, can you check my order?"
    tampered = AgentState.model_construct(**payload)

    with pytest.raises(SensitiveStateError):
        store.create_run(state=tampered, model_name="gpt-4o-mini", prompt_version="t017-v1")

    # Nothing was written: the guard runs before the INSERT.
    with pytest.raises(RunNotFoundError):
        store.get_run(run_id)


def test_store_refuses_a_credential_in_a_tool_trace_summary(
    connection_factory: ConnectionFactory,
) -> None:
    store = PostgresRunStore(connection_factory)
    state = build_state()
    try:
        create_run(store, state)
        trace = ToolTraceRecord.model_construct(
            run_id=state.run_id,
            step_index=0,
            tool_name="get_logistics",
            risk_level=RiskLevel.LOW,
            status=ToolTraceStatus.SUCCESS,
            trace_id="d1b2c3d4e5f60718293a4b5c6d7e8f93",
            input_summary={},
            output_summary={"note": f"called with {_BEARER}"},
            error_code=None,
            retryable=False,
            latency_ms=1,
        )

        with pytest.raises(SensitiveStateError):
            store.record_tool_trace(trace)

        assert store.list_tool_traces(state.run_id) == []
    finally:
        store.delete_run(state.run_id)


# --------------------------------------------------------------------------------------------
# Retention: bounded growth, preserved evidence
# --------------------------------------------------------------------------------------------


def test_retention_compacts_a_completed_run(
    connection_factory: ConnectionFactory,
) -> None:
    """Detail is reclaimed, the run row survives, and the reclamation is recorded."""
    store = PostgresRunStore(connection_factory)
    state = build_state()
    run_id = state.run_id
    try:
        created = create_run(store, state)
        store.record_tool_trace(
            ToolTraceRecord(
                run_id=run_id,
                step_index=0,
                tool_name="get_logistics",
                risk_level=RiskLevel.LOW,
                status=ToolTraceStatus.SUCCESS,
                trace_id="e1b2c3d4e5f60718293a4b5c6d7e8f94",
            )
        )
        store.transition(
            run_id,
            Transition(
                expected_version=created.version,
                status=RunStatus.COMPLETED,
                trigger="TERMINAL",
                final_action="CREATE_REFUND_REQUEST",
            ),
        )
        # Age it past the completed-run window so the sweep selects it.
        _backdate_run(connection_factory, run_id, hours=24 * 30)

        result = sweep_terminal_runs(connection_factory, policy=RetentionPolicy())
        compacted = store.get_run(run_id)

        assert run_id in result.compacted
        assert compacted.state is None, "state_json must be reclaimed"
        assert compacted.checkpoint_compacted_at is not None, "reclamation must be recorded"
        assert compacted.status is RunStatus.COMPLETED, "the run row is the audit trail"
        assert compacted.final_action == "CREATE_REFUND_REQUEST"
        assert store.list_tool_traces(run_id) == []
    finally:
        store.delete_run(run_id)


def test_retention_compaction_is_idempotent(
    connection_factory: ConnectionFactory,
) -> None:
    """A sweep that is killed halfway and restarted must not re-stamp or double-count."""
    store = PostgresRunStore(connection_factory)
    state = build_state()
    run_id = state.run_id
    try:
        created = create_run(store, state)
        store.transition(
            run_id,
            Transition(
                expected_version=created.version,
                status=RunStatus.COMPLETED,
                trigger="TERMINAL",
                final_action="CREATE_REFUND_REQUEST",
            ),
        )
        _backdate_run(connection_factory, run_id, hours=24 * 30)

        first = sweep_terminal_runs(connection_factory)
        marker_after_first = store.get_run(run_id).checkpoint_compacted_at
        second = sweep_terminal_runs(connection_factory)

        assert run_id in first.compacted
        assert run_id not in second.candidates, "an already-compacted run is not a candidate again"
        assert store.get_run(run_id).checkpoint_compacted_at == marker_after_first
    finally:
        store.delete_run(run_id)


def test_retention_keeps_a_failed_run_trace(
    connection_factory: ConnectionFactory,
) -> None:
    """The failure this protects against: cleanup that erases the reason a run failed.

    A ``FAILED`` run keeps both its payload and its trace, because the trace is the only thing that
    connects the failure to the Java request that caused it.
    """
    store = PostgresRunStore(connection_factory)
    state = build_state()
    run_id = state.run_id
    try:
        created = create_run(store, state)
        store.record_tool_trace(
            ToolTraceRecord(
                run_id=run_id,
                step_index=0,
                tool_name="create_refund_request",
                risk_level=RiskLevel.HIGH,
                status=ToolTraceStatus.ERROR,
                trace_id="f1b2c3d4e5f60718293a4b5c6d7e8f95",
                error_code="UPSTREAM_TIMEOUT",
            )
        )
        store.transition(
            run_id,
            Transition(
                expected_version=created.version,
                status=RunStatus.FAILED,
                trigger="TERMINAL",
                error_code="UPSTREAM_TIMEOUT",
            ),
        )
        # Older than the *completed* window but well inside the failed window.
        _backdate_run(connection_factory, run_id, hours=24 * 30)

        result = sweep_terminal_runs(connection_factory)
        kept = store.get_run(run_id)

        assert run_id not in result.candidates, "a 30-day-old FAILED run is still inside retention"
        assert kept.state is not None
        assert len(store.list_tool_traces(run_id)) == 1
    finally:
        store.delete_run(run_id)


def test_retention_never_touches_a_waiting_run(
    connection_factory: ConnectionFactory,
) -> None:
    """A paused run's checkpoint *is* the product: reclaiming it makes the run unrecoverable."""
    store = PostgresRunStore(connection_factory)
    state = build_state()
    run_id = state.run_id
    try:
        created = create_run(store, state)
        store.transition(
            run_id,
            Transition(
                expected_version=created.version,
                status=RunStatus.WAITING_USER,
                trigger="INTERRUPT",
                current_node="ask_user",
            ),
        )
        _backdate_run(connection_factory, run_id, hours=24 * 3650)

        result = sweep_terminal_runs(connection_factory)
        still_waiting = store.get_run(run_id)

        assert run_id not in result.candidates
        assert still_waiting.state is not None
        assert still_waiting.resumable is True
    finally:
        store.delete_run(run_id)


def _backdate_run(connection_factory: ConnectionFactory, run_id: UUID, *, hours: int) -> None:
    """Move ``started_at`` into the past so a sweep can select the run without waiting."""
    with connection_factory() as connection, connection.transaction():
        with connection.cursor() as cursor:
            cursor.execute(
                "UPDATE agent.agent_runs"
                " SET started_at = CURRENT_TIMESTAMP - (%s * INTERVAL '1 hour')"
                " WHERE run_id = %s",
                (hours, run_id),
            )
