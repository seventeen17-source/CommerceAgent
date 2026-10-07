"""Retention policy for terminal runs: bounded growth without losing the evidence that matters.

The requirement T017 states is "terminal run detail must not grow without bound" **and** "a failed
run must still be locatable from its trace". Those pull in opposite directions, and the answer is
the policy in this module: what is reclaimed depends on *why* the run ended.

Two retention bands
-------------------
==============================  =============  =================  =====================
Run status                      Keep state     Keep tool traces   Why
==============================  =============  =================  =====================
``COMPLETED`` / ``ESCALATED``   7 days         no                 Outcome is on the run row;
                                                                  step detail is only
                                                                  interesting right after.
``FAILED`` / ``SAFE_STOP``      90 days        yes                The runs Eval and a human
                                                                  re-open; ``run_id +
                                                                  step_index + trace_id``
                                                                  is how a failure is
                                                                  followed to Java.
==============================  =============  =================  =====================

``RUNNING`` / ``WAITING_*`` are **never** touched, at any age. A waiting run is a resume target:
its checkpoint *is* the product, and reclaiming it turns a paused run into an unrecoverable one.
An old ``RUNNING`` row means a crashed executor, a staleness problem for an operator to resolve
explicitly -- not something a background sweep should silently delete.

Retention is not deletion
-------------------------
Compaction clears ``state_json`` and old traces and stamps ``checkpoint_compacted_at``. The run row
survives with its status, final action and error code, so "this run happened, and ended this way"
stays answerable forever while the bulky part does not. Deleting the row would destroy the trail
that decision 10 of ``research.md`` requires anyone cloning the repo to reconstruct.

Idempotence
-----------
Every operation is safe to re-run: compaction skips rows already stamped, so an interrupted sweep
can simply be repeated. That matters more than it sounds -- a retention job is exactly the kind of
thing that gets killed halfway and restarted, and a non-idempotent one double-counts or re-stamps.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

from app.agent.state import RunStatus
from app.trace.db import ConnectionFactory
from app.trace.store import PostgresRunStore

__all__ = [
    "FAILED_STATUSES",
    "CompactionDecision",
    "RetentionPolicy",
    "SweepResult",
    "sweep_terminal_runs",
]

#: Statuses whose detail is worth keeping longest.
FAILED_STATUSES = frozenset({RunStatus.FAILED, RunStatus.SAFE_STOP})

#: Statuses retention must never touch, listed explicitly so "not in the other two sets" is never
#: reason something is preserved.
_RESUMABLE_STATUSES = frozenset(
    {RunStatus.RUNNING, RunStatus.WAITING_USER, RunStatus.WAITING_APPROVAL}
)


@dataclass(frozen=True, slots=True)
class CompactionDecision:
    """The retention policy applied to one run status."""

    retain_state: bool
    retain_tool_trace: bool
    hours: int


@dataclass(frozen=True, slots=True)
class RetentionPolicy:
    """How long each band keeps its detail. Field names say *what is kept*, not "retention days".

    Java analogy: a ``@ConfigurationProperties`` bean, injected rather than read from a static
    field, so an Eval run can tighten the window and assert that cleanup actually happens.
    """

    completed_state_hours: int = 24 * 7
    failed_state_hours: int = 24 * 90
    failed_trace_hours: int = 24 * 90

    def __post_init__(self) -> None:
        if (
            self.completed_state_hours < 1
            or self.failed_state_hours < 1
            or self.failed_trace_hours < 1
        ):
            raise ValueError("retention windows must be at least one hour")

    def decision_for(self, status: RunStatus) -> CompactionDecision:
        """What to reclaim for one terminal status, or refuse for a non-terminal one.

        Refusing is the point: a policy that returned *some* decision for ``WAITING_APPROVAL`` would
        let a caller compact a run that still has a resume pending.
        """
        if status in _RESUMABLE_STATUSES:
            raise ValueError(f"{status} is not terminal: its checkpoint is a resume target")
        if status in FAILED_STATUSES:
            return CompactionDecision(
                retain_state=True, retain_tool_trace=True, hours=self.failed_state_hours
            )
        return CompactionDecision(
            retain_state=False, retain_tool_trace=False, hours=self.completed_state_hours
        )


@dataclass(frozen=True, slots=True)
class SweepResult:
    """What one sweep did. Reported as data so a caller (or an Eval case) can assert on it."""

    candidates: tuple[UUID, ...]
    compacted: tuple[UUID, ...]
    skipped: tuple[UUID, ...]


#: One statement with both cutoffs as parameters, rather than two round-trips: a sweep that ran two
#: queries could observe two different "now"s, which is how a boundary run gets compacted twice or
#: missed entirely.
_SELECT_CANDIDATES = """
    SELECT run_id, status
    FROM agent.agent_runs
    WHERE checkpoint_compacted_at IS NULL
      AND (
            (status = ANY(%(failed_statuses)s) AND started_at < %(failed_cutoff)s)
         OR (status = ANY(%(completed_statuses)s) AND started_at < %(completed_cutoff)s)
      )
    ORDER BY started_at
    LIMIT %(batch_size)s
"""


def sweep_terminal_runs(
    connection_factory: ConnectionFactory,
    *,
    policy: RetentionPolicy | None = None,
    now: datetime | None = None,
    batch_size: int = 500,
) -> SweepResult:
    """Compact terminal runs that are past their retention window.

    ``batch_size`` bounds one sweep on purpose: an unbounded ``UPDATE`` over a large history takes a
    long time under lock and turns a maintenance job into an outage. A caller that wants everything
    calls this repeatedly until it reports no candidates.

    ``now`` is injectable so a test can assert the boundary exactly ("a run started 8 days ago is
    eligible, one started 6 days ago is not") without sleeping or relying on the wall clock.
    """
    active_policy = policy or RetentionPolicy()
    reference = now or datetime.now(UTC)

    completed_cutoff = reference - timedelta(hours=active_policy.completed_state_hours)
    failed_cutoff = reference - timedelta(hours=active_policy.failed_state_hours)

    with connection_factory() as connection, connection.cursor() as cursor:
        cursor.execute(
            _SELECT_CANDIDATES,
            {
                "failed_statuses": [status.value for status in FAILED_STATUSES],
                "completed_statuses": [
                    status.value
                    for status in RunStatus
                    if status not in FAILED_STATUSES and status not in _RESUMABLE_STATUSES
                ],
                "failed_cutoff": failed_cutoff,
                "completed_cutoff": completed_cutoff,
                "batch_size": batch_size,
            },
        )
        candidates = [(row["run_id"], RunStatus(row["status"])) for row in cursor.fetchall()]

    store = PostgresRunStore(connection_factory)
    compacted: list[UUID] = []
    skipped: list[UUID] = []
    for run_id, status in candidates:
        decision = active_policy.decision_for(status)
        # A row can fall out of the candidate set between the SELECT and the UPDATE (a concurrent
        # resume, or a second sweep). Compaction is idempotent, so the honest report is "skipped".
        changed = store.compact_terminal_run(
            run_id,
            retain_state=decision.retain_state,
            retain_tool_trace=decision.retain_tool_trace,
        )
        (compacted if changed else skipped).append(run_id)

    return SweepResult(
        candidates=tuple(run_id for run_id, _ in candidates),
        compacted=tuple(compacted),
        skipped=tuple(skipped),
    )
