"""Typed failures raised by the Agent run/checkpoint store.

The distinction that matters here is the same one ``app/clients/errors.py`` draws for HTTP: a
refusal the caller can act on versus one it cannot. For a store the acting cases are:

* :class:`RunNotFoundError` -- the run does not exist (an ownership bug, or a deleted run).
* :class:`RunVersionConflictError` -- someone else wrote first. The caller must re-read, never
  retry blindly: the state it computed came from a checkpoint that no longer exists.
* :class:`IllegalRunTransitionError` -- the requested status change is not part of the lifecycle.
  This is a bug in the graph, not a race, so it must never be retried.
* :class:`RunResumeConflictError` -- "that resume was already claimed, or the run is no longer in a
  resumable state". Separate from the generic version conflict because T017 requires *this* outcome
  to be provable: two requests resuming one ``WAITING_*`` checkpoint must produce exactly one
  winner, and the loser must be able to say why. ``reason`` is a small closed set, so a caller can
  branch on it without parsing text.
* :class:`TerminalRunError` -- the run is finished; no further transition is allowed.

Java analogy: these are the checked exceptions of a transactional repository. The analogy breaks on
what is checked: Python has no checked exceptions, so the guarantee that a caller *cannot* forget to
handle a conflict comes from the store never returning a half-applied write, not from the type
system.
"""

from __future__ import annotations

from enum import StrEnum

from app.agent.state import RunStatus

__all__ = [
    "IllegalRunTransitionError",
    "ResumeRefusalReason",
    "RunForbiddenError",
    "RunNotFoundError",
    "RunResumeConflictError",
    "RunStoreError",
    "RunVersionConflictError",
    "TerminalRunError",
]


class RunStoreError(Exception):
    """Base class for every failure raised by the run/checkpoint store."""


class RunForbiddenError(RunStoreError):
    """The run exists and belongs to a different principal.

    Separate from :class:`RunNotFoundError` on purpose, and the pair is a decision rather than an
    accident. Scoping the lookup by owner (T018) turns "someone else's run" into "no such run" at
    the SQL level, which is the safe default; but the *store* is also asked the question directly by
    callers that legitimately need to distinguish them (an operator view, an audit path, and the
    T018 API, which must return 403 -- the contract publishes a 403 for this endpoint).

    ``owner_id`` is the caller's own id as derived from the authenticated principal; the run's owner
    is deliberately not carried, because a value that lets a caller learn *whose* run an id belongs
    to is exactly the enumeration oracle the 404-shaped path exists to avoid.
    """

    def __init__(self, *, run_id: str, owner_id: str) -> None:
        super().__init__(f"agent run {run_id} is not owned by the requesting principal")
        self.run_id = run_id
        self.owner_id = owner_id


class RunNotFoundError(RunStoreError):
    """No run row exists for the requested id."""

    def __init__(self, run_id: str) -> None:
        super().__init__(f"agent run {run_id} does not exist")
        self.run_id = run_id


class RunVersionConflictError(RunStoreError):
    """The caller's snapshot is stale: the run moved on before this write.

    ``expected_version`` and ``actual_version`` are both reported because the caller has to re-read
    anyway, and knowing it lost by one version or by five says whether it was a race or a bug.
    """

    def __init__(self, *, run_id: str, expected_version: int, actual_version: int) -> None:
        super().__init__(f"agent run {run_id} is at version {actual_version},")
        self.run_id = run_id
        self.expected_version = expected_version
        self.actual_version = actual_version


class IllegalRunTransitionError(RunStoreError):
    """The requested status change is not part of the run lifecycle."""

    def __init__(self, *, run_id: str, from_status: RunStatus, to_status: RunStatus) -> None:
        super().__init__(f"agent run {run_id} cannot move from {from_status} to {to_status}")
        self.run_id = run_id
        self.from_status = from_status
        self.to_status = to_status


class TerminalRunError(RunStoreError):
    """The run is in a terminal status, so no resume or transition may proceed."""

    def __init__(self, *, run_id: str, status: RunStatus) -> None:
        super().__init__(f"agent run {run_id} is terminal ({status}) and cannot be advanced")
        self.run_id = run_id
        self.status = status


class ResumeRefusalReason(StrEnum):
    """The closed set of reasons a resume is refused.

    Enumerated because this service owns the set and must branch on every member; contrast with the
    *remote* value sets (``allowed_action``, approval ``status``), which stay open strings by the
    cross-service policy in ``app/agent/state.py``.
    """

    #: The caller's version is stale, but the run is still waiting. It must re-read, not resume.
    VERSION_MISMATCH = "VERSION_MISMATCH"
    #: A racing request already moved the run out of the status this caller read.
    ALREADY_CLAIMED = "ALREADY_CLAIMED"
    #: The run is waiting on a different interrupt than the caller assumed -- e.g. an approval was
    #: resolved while the caller held a stale snapshot, so the run is now WAITING_USER.
    STATUS_NOT_WAITING = "STATUS_NOT_WAITING"
    #: The run is finished.
    TERMINAL = "TERMINAL"
    #: Retention cleared the detailed payload, so there is no state to resume from. Matching the run
    #: version is not enough: an empty checkpoint is not a resumable checkpoint.
    CHECKPOINT_COMPACTED = "CHECKPOINT_COMPACTED"


class RunResumeConflictError(RunStoreError):
    """A resume request was refused, with a machine-readable reason.

    The loser of a resume race learns this instead of a generic conflict because the two are
    operationally different: a version conflict means "re-read and try again", while
    ``ALREADY_CLAIMED`` means "someone is already executing this run -- do not start a second
    graph".
    """

    def __init__(
        self,
        *,
        run_id: str,
        reason: ResumeRefusalReason,
        status: RunStatus | None = None,
        expected_version: int | None = None,
        actual_version: int | None = None,
    ) -> None:
        super().__init__(f"agent run {run_id} resume refused: {reason}")
        self.run_id = run_id
        self.reason = reason
        self.status = status
        self.expected_version = expected_version
        self.actual_version = actual_version
