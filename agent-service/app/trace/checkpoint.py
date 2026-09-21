"""Checkpoint records: the object a run is resumed from, and the guard that makes it safe to store.

Two things live here, and they belong together because they are the same decision seen twice:

1. **The records** -- :class:`RunRecord`, :class:`CheckpointRecord`, :class:`ToolTraceRecord`,
   :class:`Transition`, :class:`ResumeRequest`. Their field sets mirror ``agent.agent_runs`` /
   ``agent.agent_checkpoints`` / ``agent.tool_executions`` from ``V001``/``V002``. They are *not*
   the ORM: nothing here reads a connection, and the SQL lives in :mod:`app.trace.store`.

2. **The fail-closed guard on everything durable.** :meth:`RunRecord` and :meth:`ToolTraceRecord`
   re-run :func:`app.security.secrets.validate_persistable` on their own JSON form, and the store
   runs it a second time on the exact payload it binds into SQL. T017 requires that raw tokens and
   hidden reasoning cannot enter a checkpoint or a trace; the reason this is asserted at *both*
   points is documented in :mod:`app.security.secrets`, and the short version is that a checkpoint
   restored from a raw dict never passes through a model at all.

Why the run row and the checkpoint are two objects
--------------------------------------------------
``data-model.md`` section 12 makes ``status`` / ``intent`` / ``resolved_order_id`` / ``step_count``
/ ``retry_count`` deliberately present in both places: the row is the *queryable projection* (find
every ``WAITING_APPROVAL`` run), the checkpoint payload is the *authoritative runtime state*. T017
must write both in one transaction -- a row saying ``COMPLETED`` over a payload still saying
``RUNNING`` is false evidence. :meth:`RunRecord.to_state` is the one place that projection is built,
so the two cannot be assembled by hand at different call sites.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, field_validator

from app.agent.state import AgentState, RunStatus
from app.security.secrets import validate_persistable

__all__ = [
    "INTERRUPTED_STATUSES",
    "TERMINAL_STATUSES",
    "CheckpointRecord",
    "RiskLevel",
    "RunRecord",
    "ToolTraceRecord",
    "ToolTraceStatus",
    "Transition",
    "TriggerKind",
    "validate_payload",
]

#: Statuses from which no automatic work continues. Mirrors ``AgentState.is_terminal``; defined here
#: too so a query can be written without constructing a state, and asserted equal by a test rather
#: than by hope.
TERMINAL_STATUSES = frozenset(
    {RunStatus.COMPLETED, RunStatus.ESCALATED, RunStatus.FAILED, RunStatus.SAFE_STOP}
)

#: Statuses that mean "paused, waiting for an external decision", which are the only legal resume
#: entry points.
INTERRUPTED_STATUSES = frozenset({RunStatus.WAITING_USER, RunStatus.WAITING_APPROVAL})

#: Correlation ids are written by this service, not typed by a user, so they can be held to a strict
#: shape. This matters twice over: ``trace_id`` must stay inside the guard's *allowed* set (a dotted
#: id is not a credential), and the same string reaches log lines, where CR/LF would forge entries.
#: Mirrors the shape ``app.clients.commerce_client`` accepts, because that returned id is stored.
_TRACE_ID_PATTERN = r"^[A-Za-z0-9._-]{8,128}$"

#: Why a checkpoint exists. Kept explicit rather than inferred from ``status``: "the run was
#: created", "a node finished a step", and "a human resumed it" all produce a checkpoint, and an
#: operator asking "how did this run get here" needs to tell them apart.
TriggerKind = Literal["CREATED", "STEP", "RESUME", "INTERRUPT", "TERMINAL"]


class RiskLevel(StrEnum):
    """Tool risk classification. Mirrors the V001 check constraint on ``tool_executions``."""

    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class ToolTraceStatus(StrEnum):
    """How one tool call ended. Mirrors the V001 check constraint."""

    SUCCESS = "SUCCESS"
    ERROR = "ERROR"
    TIMEOUT = "TIMEOUT"
    DENIED = "DENIED"


def validate_payload(payload: dict[str, Any], path: str) -> None:
    """Guard a JSON payload that is about to be bound into an INSERT or UPDATE.

    Public so the store can call it on the serialized form *it* is about to write, without importing
    a private helper. Raises :class:`app.security.secrets.SensitiveStateError`, which the caller
    turns into ``SAFE_STOP`` plus a reason code -- never into a redacted write.
    """
    validate_persistable(payload, path)


class RunRecord(BaseModel):
    """One ``agent.agent_runs`` row: the queryable projection of a run, plus its CAS token.

    ``version`` is the compare-and-swap token added by ``V002``. It is part of the record rather
    than a store-internal detail on purpose: a caller that read a run must pass the version back,
    hiding it would make the stale-write check impossible to express.
    """

    model_config = ConfigDict(extra="forbid")

    run_id: UUID
    user_id: str = Field(min_length=1, max_length=64)
    status: RunStatus
    version: int = Field(ge=1)

    intent: str | None = Field(default=None, max_length=100)
    resolved_order_id: str | None = Field(default=None, max_length=64)
    current_node: str | None = Field(default=None, max_length=100)
    next_action: str | None = Field(default=None, max_length=100)

    step_count: int = Field(default=0, ge=0)
    retry_count: int = Field(default=0, ge=0)

    # ``None`` once retention has reclaimed the payload. Deliberately not defaulted to an empty
    # ``AgentState``: "no state because it was retired" and "an empty state" are different facts,
    # and collapsing them would let ``resume`` treat a compacted run as resumable.
    state: AgentState | None = None

    final_action: str | None = Field(default=None, max_length=100)
    error_code: str | None = Field(default=None, max_length=100)

    model_name: str = Field(min_length=1, max_length=100)
    model_temperature: float = Field(default=0.0, ge=0)
    prompt_version: str = Field(min_length=1, max_length=64)
    input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)

    started_at: datetime
    completed_at: datetime | None = None
    checkpoint_compacted_at: datetime | None = None

    # ---- derived facts ---------------------------------------------------------------------

    @property
    def is_terminal(self) -> bool:
        """Whether no automatic execution (and no resume) may continue for this run."""
        return self.status in TERMINAL_STATUSES

    @property
    def resumable(self) -> bool:
        """Whether a request may pick this run up from where it stopped.

        Only an *interrupted* run is resumable, and only while its payload still exists.
        ``RUNNING`` is not resumable: a run in that state belongs to a live executor, and treating
        it as a resume target is how two graphs end up driving one run.
        """
        return self.status in INTERRUPTED_STATUSES and self.state is not None

    def to_state(self) -> AgentState | None:
        """Rebuild the authoritative runtime state, with the row's shared columns enforced.

        The five columns that exist in both places are copied from the **row** onto the payload
        here. That direction is deliberate: the row is what a CAS write just succeeded against, so
        if the two ever disagree the row is the fresher fact. Doing it in one place means a node
        cannot persist a payload whose ``status`` contradicts the row it was written with.

        Returns ``None`` when retention has reclaimed the payload -- see :attr:`state`.
        """
        if self.state is None:
            return None
        return self.state.model_copy(
            update={
                "status": self.status,
                "intent": self.intent,
                "resolved_order_id": self.resolved_order_id,
                "step_count": self.step_count,
                "retry_count": self.retry_count,
            }
        )

    def durable_state(self) -> dict[str, Any]:
        """The exact JSON that goes into ``state_json``: row columns applied, then guarded.

        A compacted run writes ``{}``: the row keeps a well-formed JSONB value without claiming to
        hold a state it no longer has.
        """
        state = self.to_state()
        if state is None:
            return {}
        payload = state.model_dump(mode="json")
        validate_payload(payload, "run.state_json")
        return payload


class Transition(BaseModel):
    """A requested move to a new run status, bound to the version it was computed from.

    ``expected_version`` is required, not optional. An update without it is a blind overwrite, which
    is precisely the lost-update bug the version column exists to prevent -- so the type makes the
    unsafe call impossible to write rather than merely discouraged.

    ``trigger`` is required for the same reason: it is stored on the checkpoint, and "this run moved
    because a step finished" versus "because a human resumed it" is the difference between a normal
    lifecycle and an interrupt being resolved. A default would silently mislabel half of them.
    """

    model_config = ConfigDict(extra="forbid")

    expected_version: int = Field(ge=1)
    status: RunStatus
    trigger: TriggerKind
    current_node: str | None = Field(default=None, max_length=100)
    next_action: str | None = Field(default=None, max_length=100)
    final_action: str | None = Field(default=None, max_length=100)
    error_code: str | None = Field(default=None, max_length=100)
    intent: str | None = Field(default=None, max_length=100)
    resolved_order_id: str | None = Field(default=None, max_length=64)
    step_count: int | None = Field(default=None, ge=0)
    retry_count: int | None = Field(default=None, ge=0)
    reason_code: str | None = Field(default=None, max_length=100)


class ResumeRequest(BaseModel):
    """A request to continue an interrupted run from its newest checkpoint."""

    model_config = ConfigDict(extra="forbid")

    expected_version: int = Field(ge=1)
    current_node: str = Field(min_length=1, max_length=100)
    next_action: str | None = Field(default=None, max_length=100)


class CheckpointRecord(BaseModel):
    """One ``agent.agent_checkpoints`` row: what the runtime state was at a point in time.

    ``state`` is ``None`` when retention has cleared the detailed payload. That is not the same
    as an empty state: the row records *that the payload was retired*, so "no state" and "state was
    deleted" stay distinguishable -- a distinction an audit trail cannot do without.
    """

    model_config = ConfigDict(extra="forbid")

    run_id: UUID
    version: int = Field(ge=1)
    status: RunStatus
    current_node: str | None = Field(default=None, max_length=100)
    next_action: str | None = Field(default=None, max_length=100)
    step_count: int = Field(default=0, ge=0)
    retry_count: int = Field(default=0, ge=0)
    reason_code: str | None = Field(default=None, max_length=100)
    state: dict[str, Any] | None = None
    created_at: datetime


class ToolTraceRecord(BaseModel):
    """One ``agent.tool_executions`` row: the cross-service evidence for a single tool call.

    ``run_id + step_index + trace_id`` is the tuple T017 requires so a failed run can be tied to one
    specific Java request. ``input_summary`` / ``output_summary`` are *summaries*: they carry the
    structured facts a reviewer needs (which order, which error code), never a raw payload and never
    a credential -- enforced by the guard below rather than by convention.
    """

    model_config = ConfigDict(extra="forbid")

    run_id: UUID
    step_index: int = Field(ge=0)
    tool_name: str = Field(min_length=1, max_length=100)
    risk_level: RiskLevel
    status: ToolTraceStatus
    trace_id: str = Field(min_length=1, max_length=128, pattern=_TRACE_ID_PATTERN)
    input_summary: dict[str, Any] = Field(default_factory=dict)
    output_summary: dict[str, Any] = Field(default_factory=dict)
    error_code: str | None = Field(default=None, max_length=100)
    retryable: bool = False
    latency_ms: int = Field(default=0, ge=0)

    @field_validator("input_summary", "output_summary")
    @classmethod
    def reject_sensitive_summary(
        cls, value: dict[str, Any], info: ValidationInfo
    ) -> dict[str, Any]:
        """Summaries are written per step, so this is the hot path for an accidental token copy.

        Guarding here as well as at the store is not redundancy for its own sake: the store guard
        cannot name *which* tool produced the offending value, and "the trace write failed" is much
        worse than "get_logistics's output contained a credential".
        """
        validate_payload(value, f"tool_trace.{info.field_name}")
        return value

    def durable_payload(self, *, path: str) -> dict[str, Any]:
        """The exact JSON bound into SQL, guarded before it can be written."""
        payload = self.model_dump(mode="json")
        validate_payload(payload, path)
        return payload
