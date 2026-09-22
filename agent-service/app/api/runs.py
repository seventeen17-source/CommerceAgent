"""Run lifecycle endpoints (T018 skeleton): create, read, events, input, resume, trace.

"Skin and skeleton, not muscle"
-------------------------------
These endpoints really create runs, really read them back, and really enforce ownership. What they
do **not** do is run the Agent: there is no LLM call, no order lookup and no refund. Creating a run
today produces a ``RUNNING`` row with a state whose only content is the request and the principal;
T030 attaches the graph that advances it. The point of T018 is that the *plumbing* is real and
tested, so T030 adds behaviour to a working pipe instead of debugging plumbing and behaviour at
once.

Two different questions, two different status codes
---------------------------------------------------
Every endpoint here answers two independent questions, and conflating them is the mistake this
module is written to avoid:

* **"Are you allowed to touch this run?"** -- authorization. Owned by the principal, enforced by
  scoping the SQL to ``user_id`` (``get_run_for_owner``); a run belonging to someone else is a
  ``403``, and a run that does not exist is a ``404``.
* **"Can this run be advanced right now?"** -- state validity. Owned by the run lifecycle
  (``WAITING_USER`` can resume, ``COMPLETED`` cannot); a refusal is a ``409`` with a
  machine-readable reason.

The order matters: authorization is checked first, so a caller who does not own a run cannot learn
its status by watching 409 versus 200. That is why the store's owner-scoped read happens before any
transition attempt rather than relying on the transition's own guards.

Why ``ValueError`` from a UUID path parameter is caught explicitly
------------------------------------------------------------------
``/agent/runs/not-a-uuid`` must be a 404-shaped "no such run", not a 500. The contract types
``runId`` as a plain string, so a malformed id is a client error about a resource that cannot exist,
not a server fault.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field

from app.agent.state import AgentState, RunStatus
from app.security.dependencies import (
    AppSettings,
    AuthenticatedCall,
    authenticate,
    get_run_store,
)
from app.trace.checkpoint import ResumeRequest, RunRecord
from app.trace.errors import (
    IllegalRunTransitionError,
    RunForbiddenError,
    RunNotFoundError,
    RunResumeConflictError,
    RunStoreError,
    RunVersionConflictError,
    TerminalRunError,
)
from app.trace.store import new_run_id

if TYPE_CHECKING:
    from app.trace.store import RunStore

__all__ = ["router"]

#: Authentication is declared **at router level**, not per handler. A new endpoint added below is
#: therefore authenticated by default; forgetting the dependency is not an option that exists. This
#: is the compensating control for FastAPI having no built-in security filter chain.
router = APIRouter(
    prefix="/agent/runs",
    tags=["runs"],
    dependencies=[Depends(authenticate)],
)

AuthenticatedDep = Annotated[AuthenticatedCall, Depends(authenticate)]
StoreDep = Annotated["RunStore", Depends(get_run_store)]

#: Refusal reasons that mean "the caller's snapshot or the run's state does not allow this", as
#: opposed to "you may not touch this run". The contract publishes 409 for these.
_CONFLICT_REASONS = frozenset(
    {
        "ALREADY_CLAIMED",
        "VERSION_MISMATCH",
        "STATUS_NOT_WAITING",
        "TERMINAL",
        "CHECKPOINT_COMPACTED",
    }
)


class CreateRunRequest(BaseModel):
    """``POST /agent/runs`` body. ``extra="forbid"`` so a caller cannot smuggle an identity.

    There is deliberately no ``userId`` field. Principal identity comes from the verified JWT plus
    Java ``GET /me``; a body field named ``userId`` would be an authority inversion, and the way to
    prevent it is for the field not to exist.
    """

    model_config = ConfigDict(extra="forbid")

    message: str = Field(min_length=1, max_length=4000)


class RunInputRequest(BaseModel):
    """``POST /agent/runs/{runId}/input`` -- clarification text for a ``WAITING_USER`` run."""

    model_config = ConfigDict(extra="forbid")

    message: str = Field(min_length=1, max_length=4000)


class ResumeRunRequest(BaseModel):
    """``POST /agent/runs/{runId}/resume``.

    ``approval_request_id`` is a *reference*, never an assertion. The contract is explicit that
    resume must not trust approval status supplied by the caller: T049+ re-reads the authoritative
    approval record from Java before continuing. Accepting the id here records what the caller
    believes it is
    resuming, which is useful for the audit trail and useless as authority.
    """

    model_config = ConfigDict(extra="forbid")

    approval_request_id: str | None = Field(default=None, max_length=128)


class AgentRunView(BaseModel):
    """The response projection shared by every endpoint that returns a run.

    Built from a :class:`~app.trace.checkpoint.RunRecord`, and it deliberately omits
    ``state_json``: the raw payload contains the untrusted user request and the collected evidence,
    which no UI needs in order to render a run. What it exposes is the queryable projection --
    exactly the columns that exist on the row for this purpose.
    """

    model_config = ConfigDict(extra="forbid")

    run_id: str = Field(serialization_alias="runId")
    status: RunStatus
    intent: str | None = None
    resolved_order_id: str | None = Field(default=None, serialization_alias="resolvedOrderId")
    current_node: str | None = Field(default=None, serialization_alias="currentNode")
    next_action: str | None = Field(default=None, serialization_alias="nextAction")
    step_count: int = Field(serialization_alias="stepCount")
    final_action: str | None = Field(default=None, serialization_alias="finalAction")
    error_code: str | None = Field(default=None, serialization_alias="errorCode")
    version: int


class RunEvent(BaseModel):
    """One structured event on a run's timeline.

    T017 persists the durable half of this already (``agent.tool_executions`` plus the checkpoint
    history). T018 returns a *timeline built from those rows* rather than an in-memory event bus:
    a run that survives a process restart must still be explainable afterwards, which is the whole
    reason decision 10 of ``research.md`` puts the core trace in our own storage.
    """

    model_config = ConfigDict(extra="forbid")

    event_type: Literal[
        "STATE_TRANSITION",
        "TOOL_CALL",
        "TOOL_RESULT",
        "RETRY",
        "CLARIFICATION",
        "APPROVAL",
        "WRITE",
        "VERIFICATION",
        "ERROR",
    ] = Field(serialization_alias="eventType")
    node: str | None = None
    tool_name: str | None = Field(default=None, serialization_alias="toolName")
    status: str | None = None
    error_code: str | None = Field(default=None, serialization_alias="errorCode")
    latency_ms: int | None = Field(default=None, serialization_alias="latencyMs")
    summary: str | None = None
    timestamp: datetime


def _view(record: RunRecord) -> AgentRunView:
    return AgentRunView(
        run_id=str(record.run_id),
        status=record.status,
        intent=record.intent,
        resolved_order_id=record.resolved_order_id,
        current_node=record.current_node,
        next_action=record.next_action,
        step_count=record.step_count,
        final_action=record.final_action,
        error_code=record.error_code,
        version=record.version,
    )


def _parse_run_id(raw: str) -> UUID:
    """A malformed run id is a 404, not a 500."""
    try:
        return UUID(raw)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="RUN_NOT_FOUND") from exc


def _http_error_for(exc: Exception, run_id: str) -> HTTPException:
    """Map the store's typed failures onto the status the contract publishes.

    Written as one function so that every endpoint reports the same situation the same way. A second
    mapping is a second answer to "what does an unowned run look like".
    """
    if isinstance(exc, RunNotFoundError):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="RUN_NOT_FOUND")
    if isinstance(exc, RunForbiddenError):
        # 403 with a code distinct from the order-side failure: "this run is not yours" and "this
        # order is not yours" are different facts, and Eval attributes them to different failures.
        #
        # This deliberately diverges from the T019 order concealment rule (cross-owner order reads
        # collapse into 404 ORDER_NOT_FOUND). The reason is the identifier, not the endpoint shape:
        # run_id is a random UUIDv4, so confirming "this id exists" gives an attacker nothing they
        # could enumerate, while order ids are short and guessable (order-001). Concealment is a
        # cost/benefit call driven by id guessability, not a blanket rule.
        return HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="RUN_FORBIDDEN")
    if isinstance(exc, RunResumeConflictError):
        detail = exc.reason.value if exc.reason.value in _CONFLICT_REASONS else "RESUME_CONFLICT"
        return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=detail)
    if isinstance(exc, (RunVersionConflictError, IllegalRunTransitionError, TerminalRunError)):
        return HTTPException(status_code=status.HTTP_409_CONFLICT, detail="RUN_STATE_CONFLICT")
    if isinstance(exc, RunStoreError):  # pragma: no cover - defensive
        return HTTPException(status_code=status.HTTP_409_CONFLICT, detail="RUN_STATE_CONFLICT")
    raise exc


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_run(
    body: CreateRunRequest,
    call: AuthenticatedDep,
    store: StoreDep,
    settings: AppSettings,
) -> AgentRunView:
    """Create a run owned by the authenticated principal.

    Three things are worth noticing, because each one is a boundary rather than a detail:

    * ``run_id`` is minted here, not accepted from the body. A caller who could choose the id could
      choose a colliding one.
    * ``principal`` comes from ``call.principal`` -- Java's answer -- and never from the request.
      The request body has no identity field to get it from.
    * The safety budgets from ``settings`` are injected into the state at creation and then
      persisted with it. T015 required this explicitly: a restored checkpoint must keep the budgets
      it was created with, so reading today's config on resume cannot silently widen a run's
      allowance.
    """
    run_id = new_run_id()
    state = AgentState(
        run_id=run_id,
        principal=call.principal,
        user_request=body.message,
        max_steps=settings.agent_max_steps,
        max_retries=settings.agent_max_retries,
    )
    record = store.create_run(
        state=state,
        model_name=settings.model_name,
        prompt_version=_prompt_version(),
        model_temperature=settings.model_temperature,
        current_node="created",
        next_action="understand_request",
    )
    return _view(record)


@router.get("/{run_id}")
async def get_run(run_id: str, call: AuthenticatedDep, store: StoreDep) -> AgentRunView:
    """Read one run, if it is yours.

    Owner-scoped at the SQL level, so another principal's run is never read into this process.
    """
    record = _owned_run(store, run_id, call)
    return _view(record)


@router.get("/{run_id}/events")
async def list_events(run_id: str, call: AuthenticatedDep, store: StoreDep) -> list[RunEvent]:
    """The run's structured timeline, newest last.

    ``text/event-stream`` is what the contract advertises, but streaming is a transport choice that
    belongs with the UI work; returning the same events as JSON now keeps the *content* correct and
    the contract satisfiable, without shipping a half-built stream that no client consumes yet. The
    shape is what matters for T018: a client can render a timeline today.

    Completed the state transitions and the tool calls into one ordered list, because that is how a
    reviewer reads a failed run -- "it moved here, then it called this, then it failed".
    """
    record = _owned_run(store, run_id, call)
    events: list[RunEvent] = []

    for checkpoint in store.list_checkpoints(record.run_id):
        events.append(
            RunEvent(
                event_type="STATE_TRANSITION",
                node=checkpoint.current_node,
                status=checkpoint.status.value,
                summary=f"checkpoint v{checkpoint.version}",
                timestamp=checkpoint.created_at,
            )
        )
    for trace in store.list_tool_traces(record.run_id):
        events.append(
            RunEvent(
                event_type="TOOL_CALL",
                tool_name=trace.tool_name,
                status=trace.status.value,
                error_code=trace.error_code,
                latency_ms=trace.latency_ms,
                summary=f"step {trace.step_index} trace {trace.trace_id}",
                timestamp=record.started_at,
            )
        )

    events.sort(key=lambda event: event.timestamp)
    return events


@router.get("/{run_id}/trace")
async def get_trace(run_id: str, call: AuthenticatedDep, store: StoreDep) -> list[RunEvent]:
    """Alias of ``/events`` for the contract's separate ``/trace`` path.

    Kept as a separate handler rather than a redirect so the two can diverge later without a
    behavioural change hiding inside a 307: ``/trace`` is documented as the state/tool timeline,
    ``/events`` as the stream. Today they carry the same payload.
    """
    return await list_events(run_id, call, store)


@router.post("/{run_id}/input")
async def submit_input(
    run_id: str, body: RunInputRequest, call: AuthenticatedDep, store: StoreDep
) -> AgentRunView:
    """Supply clarification text to a ``WAITING_USER`` run.

    Today this resumes the run and records the input in the checkpoint; it does not yet *interpret*
    the text, because understanding belongs to T030's graph. What is real is the gate: only the
    owner may call it, and only a waiting run may be resumed.

    The status check is the store's, not this handler's. Two places deciding "is this run resumable"
    would be two answers, and the one in SQL is the one that holds under concurrency.
    """
    record = _owned_run(store, run_id, call)
    resumed = _resume(store, record, current_node="user_input_received", next_action=None)
    return _view(resumed)


@router.post("/{run_id}/resume")
async def resume_run(
    run_id: str, call: AuthenticatedDep, store: StoreDep, body: ResumeRunRequest | None = None
) -> AgentRunView:
    """Resume a checkpointed run after an external decision.

    ``body.approval_request_id`` is recorded as the caller's *claim* about what it is resuming. It
    is not authority: T049+ must re-read the authoritative approval record from Java before any
    sensitive write. Stated here because the temptation to trust it is exactly what the contract
    warns about, and the field's presence makes that temptation visible.
    """
    record = _owned_run(store, run_id, call)
    resumed = _resume(store, record, current_node="resumed", next_action=None)
    return _view(resumed)


def _owned_run(store: RunStore, raw_run_id: str, call: AuthenticatedCall) -> RunRecord:
    """Read a run the caller owns, or raise the status that says why not.

    Every handler goes through here. That is deliberate: authorization appears once, so it cannot be
    forgotten on one of six endpoints, and it always happens *before* any state reasoning.
    """
    run_id = _parse_run_id(raw_run_id)
    try:
        return store.get_run_for_owner(run_id, owner_id=call.principal.user_id)
    except (RunNotFoundError, RunForbiddenError) as exc:
        raise _http_error_for(exc, raw_run_id) from exc


def _resume(
    store: RunStore, record: RunRecord, *, current_node: str, next_action: str | None
) -> RunRecord:
    """Resume a run the caller already owns.

    A helper so ``/input`` and ``/resume`` cannot drift in how they build the request. Both pass the
    version the row currently holds, which is what makes the store's compare-and-swap refuse a
    racing resume instead of forking the run.
    """
    try:
        return store.resume(
            record.run_id,
            ResumeRequest(
                expected_version=record.version,
                current_node=current_node,
                next_action=next_action,
            ),
        )
    except (
        RunResumeConflictError,
        RunVersionConflictError,
        IllegalRunTransitionError,
        TerminalRunError,
        RunNotFoundError,
    ) as exc:
        raise _http_error_for(exc, str(record.run_id)) from exc


def _prompt_version() -> str:
    """The prompt/graph version recorded on every run.

    A literal for now: T030 introduces the graph whose version this should track. Recorded at
    creation rather than derived later because a run must be explainable by the configuration that
    produced it, not by whatever the configuration is when someone reads it.
    """
    return "t018-skeleton-v1"
