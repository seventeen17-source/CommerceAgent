"""PostgreSQL implementation of the run/checkpoint/trace store.

The one decision this module exists to get right
-----------------------------------------------
**Two requests must not resume the same interrupted checkpoint.** T017 states it as a hard
requirement, and it is not satisfied by "check the status and then update it" -- that is a TOCTOU
race, and the window is exactly as wide as the code between the two statements.

The sequence used here, in a single transaction:

1. ``SELECT ... FOR UPDATE`` -- takes a row lock. A second resume blocks here instead of reading.
2. Re-read ``status`` **and** ``version`` from the locked row.
3. Compare ``version`` with the version the caller read. Mismatch means someone wrote first.
4. Require the status to still be an interrupted one.
5. ``UPDATE ... WHERE run_id = %s AND version = %s`` and require exactly one row.

Step 1 alone is not enough, and that is the part worth understanding: a row lock only *serialises*
writers. Without step 3 the second request would block, wake up, and then write a state derived from
a checkpoint that no longer exists -- a fork, which is the failure the requirement names. The lock
makes the check race-free; the version comparison is what detects the staleness. The
``AND version = ?`` in step 5 is defence in depth: if the lock were ever released early (a different
isolation level, a caller that commits between statements), the update still cannot resurrect a
stale write.

``READ COMMITTED`` (PostgreSQL's default) is sufficient for this sequence. It is worth saying why,
because "use a stronger isolation level" is the usual reflex: at ``REPEATABLE READ`` the second
transaction would get a serialization failure *instead of* a clean refusal, and the caller would
have to distinguish an infrastructure error from "someone already claimed this resume" -- losing
exactly the information T017 asks the winner/loser split to preserve.

Everything else here is deliberately boring: parameterised SQL, one statement per intent, and JSON
serialised explicitly so the value checked by the secret guard is the value that is bound.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from psycopg.types.json import Jsonb

from app.agent.state import AgentState, RunStatus
from app.security.secrets import SensitiveStateError
from app.trace.checkpoint import (
    INTERRUPTED_STATUSES,
    TERMINAL_STATUSES,
    CheckpointRecord,
    ResumeRequest,
    RunRecord,
    ToolTraceRecord,
    Transition,
    validate_payload,
)
from app.trace.db import ConnectionFactory, transaction
from app.trace.errors import (
    IllegalRunTransitionError,
    ResumeRefusalReason,
    RunForbiddenError,
    RunNotFoundError,
    RunResumeConflictError,
    RunStoreError,
    RunVersionConflictError,
    TerminalRunError,
)

__all__ = ["PostgresRunStore", "RunStore", "allowed_transitions", "guard_error_code", "new_run_id"]

#: The run lifecycle. ``RUNNING`` may reach any waiting or terminal status; a waiting run may return
#: to ``RUNNING`` (that *is* the resume) or end without further work; terminal statuses have no
#: exits. Enforcing it in the store rather than trusting the graph means an illegal move fails here,
#: with a named error, instead of being persisted as a state nobody can interpret.
_TRANSITIONS: dict[RunStatus, frozenset[RunStatus]] = {
    RunStatus.RUNNING: frozenset(
        {
            RunStatus.RUNNING,
            RunStatus.WAITING_USER,
            RunStatus.WAITING_APPROVAL,
            *TERMINAL_STATUSES,
        }
    ),
    RunStatus.WAITING_USER: frozenset({RunStatus.RUNNING, *TERMINAL_STATUSES}),
    RunStatus.WAITING_APPROVAL: frozenset({RunStatus.RUNNING, *TERMINAL_STATUSES}),
    RunStatus.COMPLETED: frozenset(),
    RunStatus.ESCALATED: frozenset(),
    RunStatus.FAILED: frozenset(),
    RunStatus.SAFE_STOP: frozenset(),
}

#: Selected explicitly rather than ``SELECT *``: a new column must not silently change the shape of
#: every row mapping, and ``RETURNING`` needs the same list to stay in step.
_RUN_COLUMNS = (
    "run_id, user_id, status, version, intent, resolved_order_id, current_node, next_action, "
    "step_count, retry_count, state_json, final_action, error_code, model_name, model_temperature, "
    "prompt_version, input_tokens, output_tokens, started_at, completed_at, checkpoint_compacted_at"
)


def _run_columns() -> str:
    """The run column list, for splicing into a statement.

    A static identifier list, not a value: nothing here comes from a caller or a request. Every
    *value* in this module is bound as a parameter; the S608 heuristic cannot tell the two apart,
    which is why the two splicing call sites carry a one-line ``noqa`` each.
    """
    return _RUN_COLUMNS


#: The INSERT ... RETURNING that opens a run.
_INSERT_RUN = (
    "INSERT INTO agent.agent_runs ("
    " run_id, user_id, status, state_json, model_name, model_temperature,"
    " prompt_version, current_node, next_action,"
    " intent, resolved_order_id, step_count, retry_count"
    ") VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"
    " RETURNING " + _RUN_COLUMNS
)

#: The compare-and-swap write.
_UPDATE_RUN = (
    """
    UPDATE agent.agent_runs
    SET status = %s,
        version = %s,
        intent = %s,
        resolved_order_id = %s,
        current_node = COALESCE(%s, current_node),
        next_action = COALESCE(%s, next_action),
        final_action = COALESCE(%s, final_action),
        error_code = COALESCE(%s, error_code),
        step_count = %s,
        retry_count = %s,
        state_json = %s,
        completed_at = %s
    WHERE run_id = %s AND version = %s
    RETURNING """
    + _RUN_COLUMNS
)


def allowed_transitions(status: RunStatus) -> frozenset[RunStatus]:
    """The statuses reachable from ``status``. Exposed so a test can assert the table is total."""
    return _TRANSITIONS[status]


def new_run_id() -> UUID:
    """Mint a run id, so tests and the T018 endpoint cannot disagree on the format."""
    return uuid4()


def guard_error_code(error: SensitiveStateError) -> str:
    """Map the secret guard's failure onto a stable reason code for ``SAFE_STOP``.

    Kept next to the guard call sites so the mapping cannot be forgotten: every place that catches
    :class:`SensitiveStateError` records the field path and never the value.
    """
    return f"SENSITIVE_STATE_REJECTED:{error.path}"


def _as_utc(value: datetime | None) -> datetime | None:
    """Normalise a database timestamp to an aware UTC value.

    ``TIMESTAMPTZ`` comes back aware, but a naive value would compare unequal to an aware one and
    turn a retention cutoff into a silent no-op -- a bug that looks like "retention ran and did
    nothing".
    """
    if value is None:
        return None
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def _completion_time(*, status: RunStatus, previous: datetime | None) -> datetime | None:
    """When a run's ``completed_at`` is set, and when it is deliberately cleared.

    A terminal status requires a completion time (``V002``'s check constraint); a non-terminal one
    must not have one, because that is what retention keys on to decide a run's detail is safe to
    reclaim. An already-recorded time is preserved so re-writing a terminal run is idempotent.
    """
    if status not in TERMINAL_STATUSES:
        return None
    if previous is not None:
        return previous
    return datetime.now(UTC)


def _state_from_json(raw: Any) -> AgentState | None:
    """Rebuild the runtime state, or report that there is none.

    Two cases both mean "no state": absence, and the ``{}`` that retention writes when it reclaims a
    payload. Neither is handed to ``model_validate`` -- a compacted run must not be mistaken for a
    resumable one (see :class:`RunRecord.state`).
    """
    if not isinstance(raw, dict) or not raw:
        return None
    return AgentState.model_validate(raw)


def _timestamp(row: dict[str, Any], column: str) -> datetime:
    """Read a NOT NULL timestamp column, naming it in the failure rather than raising TypeError."""
    value = _as_utc(row[column])
    if value is None:
        raise RunStoreError(f"agent run {row['run_id']} has no {column}")
    return value


def _run_from_row(row: dict[str, Any], *, state: AgentState | None) -> RunRecord:
    """Map a row to a record, using a state the caller has already parsed and validated.

    Used on the write path, where the payload was just checked: re-parsing it would be a second
    validation of the same bytes, and two validations of one value is how the two drift apart.
    """
    return RunRecord(
        run_id=row["run_id"],
        user_id=row["user_id"],
        status=RunStatus(row["status"]),
        version=row["version"],
        intent=row["intent"],
        resolved_order_id=row["resolved_order_id"],
        current_node=row["current_node"],
        next_action=row["next_action"],
        step_count=row["step_count"],
        retry_count=row["retry_count"],
        state=state,
        final_action=row["final_action"],
        error_code=row["error_code"],
        model_name=row["model_name"],
        model_temperature=float(row["model_temperature"]),
        prompt_version=row["prompt_version"],
        input_tokens=row["input_tokens"],
        output_tokens=row["output_tokens"],
        started_at=_timestamp(row, "started_at"),
        completed_at=_as_utc(row["completed_at"]),
        checkpoint_compacted_at=_as_utc(row["checkpoint_compacted_at"]),
    )


def _row_to_run(row: dict[str, Any]) -> RunRecord:
    """Map a row to a record, parsing the payload from ``state_json``."""
    return _run_from_row(row, state=_state_from_json(row["state_json"]))


class RunStore:
    """Protocol-shaped base class documenting the store contract.

    A real ``typing.Protocol`` would be more idiomatic, but the contract is also implemented by test
    doubles, and an abstract base class gives those doubles a runtime-checkable common ancestor. The
    methods below raise ``NotImplementedError`` on purpose: a double that forgets one fails loudly
    instead of silently inheriting a no-op.
    """

    def create_run(
        self,
        *,
        state: AgentState,
        model_name: str,
        prompt_version: str,
        model_temperature: float = 0.0,
        current_node: str | None = None,
        next_action: str | None = None,
    ) -> RunRecord:
        raise NotImplementedError

    def get_run(self, run_id: UUID) -> RunRecord:
        raise NotImplementedError

    def get_run_for_owner(self, run_id: UUID, *, owner_id: str) -> RunRecord:
        raise NotImplementedError

    def transition(self, run_id: UUID, transition: Transition) -> RunRecord:
        raise NotImplementedError

    def resume(self, run_id: UUID, request: ResumeRequest) -> RunRecord:
        raise NotImplementedError

    def record_tool_trace(self, trace: ToolTraceRecord) -> None:
        raise NotImplementedError

    def list_tool_traces(self, run_id: UUID) -> list[ToolTraceRecord]:
        raise NotImplementedError

    def list_checkpoints(self, run_id: UUID) -> list[CheckpointRecord]:
        raise NotImplementedError


class PostgresRunStore(RunStore):
    """Run/checkpoint/trace persistence against ``agent.*`` (owned by this service).

    One instance per process; it holds no connection, only the factory, so it is safe to share and
    cannot pin a transaction open between calls.
    """

    def __init__(self, connection_factory: ConnectionFactory) -> None:
        self._connect = connection_factory

    # ---- creation --------------------------------------------------------------------------

    def create_run(
        self,
        *,
        state: AgentState,
        model_name: str,
        prompt_version: str,
        model_temperature: float = 0.0,
        current_node: str | None = None,
        next_action: str | None = None,
    ) -> RunRecord:
        """Insert the run row and its first checkpoint in one transaction.

        The guarded payload is produced *before* the connection is opened, so a credential in the
        state fails with a typed error and leaves no half-created run behind.

        The run id comes from ``state.run_id`` rather than being generated here. One id, one owner:
        a store that invented its own would leave the caller holding a state whose ``run_id``
        disagrees with the row it was just written to.

        The projection columns (``intent`` / ``resolved_order_id`` / ``step_count`` /
        ``retry_count``) are copied **from the state** here. Omitting them is what the first
        version of this method did, and it silently produced a run row that could not answer
        "which order is this run about?" -- those columns exist in both places precisely so the
        row can be queried without deserialising every payload.
        """
        payload = state.model_dump(mode="json")
        validate_payload(payload, "run.state_json")

        with self._connect() as connection, transaction(connection) as cursor:
            cursor.execute(
                _INSERT_RUN,
                (
                    state.run_id,
                    state.principal.user_id,
                    state.status.value,
                    Jsonb(payload),
                    model_name,
                    model_temperature,
                    prompt_version,
                    current_node,
                    next_action,
                    state.intent,
                    state.resolved_order_id,
                    state.step_count,
                    state.retry_count,
                ),
            )
            row = cursor.fetchone()
            if row is None:
                raise RunStoreError(f"INSERT ... RETURNING produced no row for run {state.run_id}")
            self._insert_checkpoint(
                cursor,
                run_id=state.run_id,
                version=1,
                status=state.status,
                current_node=current_node,
                next_action=next_action,
                step_count=state.step_count,
                retry_count=state.retry_count,
                reason_code=None,
                state_payload=payload,
            )
            return _run_from_row(row, state=state)

    # ---- reads -----------------------------------------------------------------------------

    def get_run(self, run_id: UUID) -> RunRecord:
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                "SELECT " + _run_columns() + " FROM agent.agent_runs WHERE run_id = %s",
                (run_id,),
            )
            row = cursor.fetchone()
        if row is None:
            raise RunNotFoundError(str(run_id))
        return _row_to_run(row)

    def get_run_for_owner(self, run_id: UUID, *, owner_id: str) -> RunRecord:
        """Read a run **scoped to its owner**, with no way to observe another principal's run.

        The owner is part of the SQL predicate rather than a check applied after the read. Two
        consequences, and both are the reason for doing it this way:

        1. A run belonging to someone else never enters this process. An ``if record.user_id !=
           owner`` check is equally correct about the answer and strictly worse about the exposure:
           it deserialises a stranger's ``state_json`` -- their order ids, their request text, their
           collected evidence -- into memory purely to decide whether to discard it.
        2. The query cannot be forgotten. There is no "read, then authorize" pair to keep in step,
           so a future endpoint cannot ship the read without the check.

        Because a miss is ambiguous by construction, the method disambiguates explicitly: it asks
        whether the row exists at all, and reports :class:`RunForbiddenError` only when it does.
        That costs one extra query on the failing path and keeps 403 versus 404 honest, which the
        published contract requires.
        """
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                "SELECT "
                + _run_columns()
                + " FROM agent.agent_runs WHERE run_id = %s AND user_id = %s",
                (run_id, owner_id),
            )
            row = cursor.fetchone()
            if row is not None:
                return _row_to_run(row)

            cursor.execute("SELECT 1 FROM agent.agent_runs WHERE run_id = %s", (run_id,))
            if cursor.fetchone() is None:
                raise RunNotFoundError(str(run_id))
        raise RunForbiddenError(run_id=str(run_id), owner_id=owner_id)

    def list_tool_traces(self, run_id: UUID) -> list[ToolTraceRecord]:
        """Every recorded tool call for a run, in step order.

        ``ORDER BY step_index`` rather than ``created_at``: the step index is the causal order, and
        two traces written in the same millisecond would otherwise come back arbitrarily ordered.
        """
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT run_id, step_index, tool_name, risk_level, status, trace_id, error_code,
                       retryable, latency_ms
                FROM agent.tool_executions
                WHERE run_id = %s
                ORDER BY step_index
                """,
                (run_id,),
            )
            rows = cursor.fetchall()
        return [
            ToolTraceRecord(
                run_id=row["run_id"],
                step_index=row["step_index"],
                tool_name=row["tool_name"],
                risk_level=row["risk_level"],
                status=row["status"],
                trace_id=row["trace_id"],
                error_code=row["error_code"],
                retryable=row["retryable"],
                latency_ms=row["latency_ms"],
            )
            for row in rows
        ]

    def list_checkpoints(self, run_id: UUID) -> list[CheckpointRecord]:
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT run_id, version, status, current_node, next_action, step_count, retry_count,
                       reason_code, state_json, created_at
                FROM agent.agent_checkpoints
                WHERE run_id = %s
                ORDER BY version
                """,
                (run_id,),
            )
            rows = cursor.fetchall()
        return [
            CheckpointRecord(
                run_id=row["run_id"],
                version=row["version"],
                status=RunStatus(row["status"]),
                current_node=row["current_node"],
                next_action=row["next_action"],
                step_count=row["step_count"],
                retry_count=row["retry_count"],
                reason_code=row["reason_code"],
                state=row["state_json"] or None,
                created_at=_timestamp(row, "created_at"),
            )
            for row in rows
        ]

    # ---- the CAS write path ------------------------------------------------------------------

    def transition(self, run_id: UUID, transition: Transition) -> RunRecord:
        """Move a run to a new status, refusing a stale snapshot instead of overwriting it."""
        with self._connect() as connection, transaction(connection) as cursor:
            locked = self._lock_run(cursor, run_id)
            from_status = RunStatus(locked["status"])

            if from_status in TERMINAL_STATUSES:
                raise TerminalRunError(run_id=str(run_id), status=from_status)

            if locked["version"] != transition.expected_version:
                raise RunVersionConflictError(
                    run_id=str(run_id),
                    expected_version=transition.expected_version,
                    actual_version=locked["version"],
                )

            if transition.status not in allowed_transitions(from_status):
                raise IllegalRunTransitionError(
                    run_id=str(run_id), from_status=from_status, to_status=transition.status
                )

            next_version = locked["version"] + 1
            refreshed, refreshed_state = self._apply_transition(
                cursor,
                run_id=run_id,
                expected_version=transition.expected_version,
                next_version=next_version,
                transition=transition,
                current=locked,
            )
            self._insert_checkpoint(
                cursor,
                run_id=run_id,
                version=next_version,
                status=transition.status,
                current_node=transition.current_node,
                next_action=transition.next_action,
                step_count=refreshed["step_count"],
                retry_count=refreshed["retry_count"],
                reason_code=transition.reason_code,
                state_payload=refreshed["state_json"],
            )
            return _run_from_row(refreshed, state=refreshed_state)

    def resume(self, run_id: UUID, request: ResumeRequest) -> RunRecord:
        """Claim the resume of an interrupted run, or explain why it was refused.

        The whole point of this method: after it returns, exactly one caller believes it owns the
        run. Every refusal carries a :class:`ResumeRefusalReason`, because "someone else got there
        first" and "your snapshot is stale, try again" demand different reactions -- one is a dead
        end, the other is a retry.
        """
        with self._connect() as connection, transaction(connection) as cursor:
            locked = self._lock_run(cursor, run_id)
            from_status = RunStatus(locked["status"])

            if from_status in TERMINAL_STATUSES:
                raise RunResumeConflictError(
                    run_id=str(run_id),
                    reason=ResumeRefusalReason.TERMINAL,
                    status=from_status,
                    expected_version=request.expected_version,
                    actual_version=locked["version"],
                )

            if locked["version"] != request.expected_version:
                raise RunResumeConflictError(
                    run_id=str(run_id),
                    reason=ResumeRefusalReason.ALREADY_CLAIMED,
                    status=from_status,
                    expected_version=request.expected_version,
                    actual_version=locked["version"],
                )

            if from_status not in INTERRUPTED_STATUSES:
                raise RunResumeConflictError(
                    run_id=str(run_id),
                    reason=ResumeRefusalReason.STATUS_NOT_WAITING,
                    status=from_status,
                    expected_version=request.expected_version,
                    actual_version=locked["version"],
                )

            checkpoint = self._lock_checkpoint(cursor, run_id, request.expected_version)
            state_payload = checkpoint["state_json"] if checkpoint is not None else None
            if not state_payload:
                raise RunResumeConflictError(
                    run_id=str(run_id),
                    reason=ResumeRefusalReason.CHECKPOINT_COMPACTED,
                    status=from_status,
                    expected_version=request.expected_version,
                    actual_version=locked["version"],
                )

            # The resume is itself a checkpoint: "this run continued, from version N, at this
            # node" is a fact a reviewer needs, and the record that the resume happened once.
            next_version = locked["version"] + 1
            transition = Transition(
                expected_version=request.expected_version,
                status=RunStatus.RUNNING,
                trigger="RESUME",
                current_node=request.current_node,
                next_action=request.next_action,
            )
            refreshed, refreshed_state = self._apply_transition(
                cursor,
                run_id=run_id,
                expected_version=request.expected_version,
                next_version=next_version,
                transition=transition,
                current=locked,
            )
            self._insert_checkpoint(
                cursor,
                run_id=run_id,
                version=next_version,
                status=RunStatus.RUNNING,
                current_node=request.current_node,
                next_action=request.next_action,
                step_count=refreshed["step_count"],
                retry_count=refreshed["retry_count"],
                reason_code=None,
                state_payload=refreshed["state_json"],
            )
            return _run_from_row(refreshed, state=refreshed_state)

    # ---- tool trace --------------------------------------------------------------------------

    def record_tool_trace(self, trace: ToolTraceRecord) -> None:
        """Persist one tool call: ``run_id + step_index + trace_id`` plus its outcome summary.

        The unique constraint on ``(run_id, step_index)`` is left to the database to enforce.
        Catching the ``UniqueViolation`` and translating it would add a branch the caller cannot act
        on -- a duplicate step index is a graph bug, and the integrity error is the honest report.
        """
        payload = trace.durable_payload(path="tool_trace")
        with self._connect() as connection, transaction(connection) as cursor:
            cursor.execute(
                """
                INSERT INTO agent.tool_executions (
                    run_id, step_index, tool_name, risk_level, input_summary, output_summary,
                    status, error_code, retryable, latency_ms, trace_id
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    trace.run_id,
                    trace.step_index,
                    trace.tool_name,
                    trace.risk_level.value,
                    Jsonb(payload["input_summary"]),
                    Jsonb(payload["output_summary"]),
                    trace.status.value,
                    trace.error_code,
                    trace.retryable,
                    trace.latency_ms,
                    trace.trace_id,
                ),
            )

    # ---- retention ---------------------------------------------------------------------------

    def compact_terminal_run(
        self, run_id: UUID, *, retain_state: bool, retain_tool_trace: bool
    ) -> bool:
        """Retire a terminal run's detail. Returns whether this call changed anything.

        Idempotent: the ``checkpoint_compacted_at IS NULL`` guard means a second call is a no-op, so
        a retention sweep that is interrupted and re-run cannot double-count or re-stamp. The marker
        is the point of the operation -- without it, "this run has no state" and "this run's state
        was reclaimed" would be indistinguishable, and only one of those is safe to ignore.
        """
        with self._connect() as connection, transaction(connection) as cursor:
            cursor.execute(
                """
                UPDATE agent.agent_runs
                SET state_json = CASE WHEN %s THEN state_json ELSE '{}'::jsonb END,
                    checkpoint_compacted_at = COALESCE(checkpoint_compacted_at, CURRENT_TIMESTAMP)
                WHERE run_id = %s
                  AND status = ANY(%s)
                  AND checkpoint_compacted_at IS NULL
                """,
                (retain_state, run_id, [status.value for status in TERMINAL_STATUSES]),
            )
            compacted = cursor.rowcount == 1

            cursor.execute(
                "DELETE FROM agent.tool_executions WHERE run_id = %s AND %s = FALSE",
                (run_id, retain_tool_trace),
            )
            if not retain_state:
                cursor.execute(
                    """
                    UPDATE agent.agent_checkpoints
                    SET state_json = '{}'::jsonb
                    WHERE run_id = %s AND state_json <> '{}'::jsonb
                    """,
                    (run_id,),
                )
            return compacted

    def delete_run(self, run_id: UUID) -> None:
        """Remove a run and everything that hangs off it (checkpoints and traces cascade).

        Used by tests and by an explicit operator request. Routine retention should *compact* rather
        than delete: the run row is the evidence that the run happened at all.
        """
        with self._connect() as connection, transaction(connection) as cursor:
            cursor.execute("DELETE FROM agent.agent_runs WHERE run_id = %s", (run_id,))

    # ---- internals ---------------------------------------------------------------------------

    def _lock_run(self, cursor: Any, run_id: UUID) -> dict[str, Any]:
        """Take the row lock and return the *current* row.

        ``FOR UPDATE`` is the serialisation point. Everything after it in the same transaction is
        protected from a concurrent writer, which is what makes the version comparison meaningful
        rather than merely optimistic.
        """
        cursor.execute(
            "SELECT " + _run_columns() + " FROM agent.agent_runs WHERE run_id = %s FOR UPDATE",
            (run_id,),
        )
        row = cursor.fetchone()
        if row is None:
            raise RunNotFoundError(str(run_id))
        return dict(row)

    def _lock_checkpoint(self, cursor: Any, run_id: UUID, version: int) -> dict[str, Any] | None:
        """The checkpoint the caller is resuming from, taken from the version it read.

        Reading it by ``version`` rather than by "newest" is the point: the caller's snapshot must
        resolve to one specific checkpoint, or "resume from what I read" has no referent.
        """
        cursor.execute(
            """
            SELECT run_id, version, status, state_json, step_count, retry_count
            FROM agent.agent_checkpoints
            WHERE run_id = %s AND version = %s
            FOR UPDATE
            """,
            (run_id, version),
        )
        row = cursor.fetchone()
        return dict(row) if row is not None else None

    def _apply_transition(
        self,
        cursor: Any,
        *,
        run_id: UUID,
        expected_version: int,
        next_version: int,
        transition: Transition,
        current: dict[str, Any],
    ) -> tuple[dict[str, Any], AgentState | None]:
        """Bind the new row values and execute the compare-and-swap UPDATE.

        Returns the refreshed row **and** the parsed state that was written with it, so the caller
        does not re-parse and re-validate the same bytes. Re-validating one value twice is how two
        supposedly-single rules drift apart -- the failure :mod:`app.security.secrets` exists to
        prevent.

        A field the caller left unset keeps its current value, so a transition does not silently
        erase ``intent`` or ``resolved_order_id`` -- the failure mode where every step wipes the
        previous step's findings.
        """
        state = _state_from_json(current["state_json"])
        status = transition.status
        intent: str | None = (
            transition.intent if transition.intent is not None else current["intent"]
        )
        resolved_order_id: str | None = (
            transition.resolved_order_id
            if transition.resolved_order_id is not None
            else current["resolved_order_id"]
        )
        step_count: int = (
            transition.step_count if transition.step_count is not None else current["step_count"]
        )
        retry_count: int = (
            transition.retry_count if transition.retry_count is not None else current["retry_count"]
        )

        payload = current["state_json"]
        written_state: AgentState | None = None
        if state is not None:
            # Row columns and payload are written in ONE statement from ONE dict, so the drift
            # data-model.md section 12 forbids ("row says COMPLETED, payload says RUNNING") is not
            # expressible here.
            written_state = state.model_copy(
                update={
                    "status": status,
                    "intent": intent,
                    "resolved_order_id": resolved_order_id,
                    "step_count": step_count,
                    "retry_count": retry_count,
                }
            )
            payload = written_state.model_dump(mode="json")
            validate_payload(payload, "run.state_json")

        # S608 is a false positive for the same reason as in ``create_run``.
        cursor.execute(
            _UPDATE_RUN,
            (
                status.value,
                next_version,
                intent,
                resolved_order_id,
                transition.current_node,
                transition.next_action,
                transition.final_action,
                transition.error_code,
                step_count,
                retry_count,
                Jsonb(payload),
                _completion_time(status=status, previous=current["completed_at"]),
                run_id,
                expected_version,
            ),
        )
        row = cursor.fetchone()
        if row is None:
            # Unreachable while the row lock above is held: it would mean the version moved between
            # the lock and this UPDATE. Kept as an explicit failure rather than an ``assert``
            # because silently returning a stale row is the one outcome this method exists to stop.
            raise RunStoreError(
                f"compare-and-swap on run {run_id} matched no row at version {expected_version}"
            )
        return dict(row), written_state

    def _insert_checkpoint(
        self,
        cursor: Any,
        *,
        run_id: UUID,
        version: int,
        status: RunStatus,
        current_node: str | None,
        next_action: str | None,
        step_count: int,
        retry_count: int,
        reason_code: str | None,
        state_payload: Any,
    ) -> None:
        cursor.execute(
            """
            INSERT INTO agent.agent_checkpoints (
                run_id, version, status, current_node, next_action, step_count, retry_count,
                reason_code, state_json
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                run_id,
                version,
                status.value,
                current_node,
                next_action,
                step_count,
                retry_count,
                reason_code,
                Jsonb(state_payload),
            ),
        )
