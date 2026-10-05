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
from typing import TYPE_CHECKING, Annotated, Literal, Protocol, cast
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, Field, SecretStr

from app.agent.routing import Node
from app.agent.runtime import RunSession, drive_graph
from app.agent.state import (
    AgentState,
    RunStatus,
    VerificationStatus,
    WriteStatus,
    advance,
)
from app.agent.wiring import build_agent_graph
from app.clients.commerce_client import CommerceClient
from app.config.settings import Settings
from app.llm.openai_compatible import OpenAICompatibleJsonClient
from app.security.dependencies import (
    AppSettings,
    AuthenticatedCall,
    authenticate,
    get_run_store,
)
from app.tools import CommerceTools
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

    Three fields come from the payload rather than the row, and they are the ones T033 exists for:
    ``verificationStatus`` and ``verifiedRefundRequestId`` say what authority *confirmed*, and
    ``finalMessage`` says it in words. The rule they share: **success is signed by
    ``VERIFIED_SUCCESS``**, never by a write response and never by a model claiming it.

    ``checkpointCompactedAt`` is published for the one ambiguity those payload fields would
    otherwise hide: ``null`` verification means either "nothing was verified" or "the payload was
    retired by retention", and only this timestamp tells the two apart.
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
    final_message: str | None = Field(default=None, serialization_alias="finalMessage")
    approval_request_id: str | None = Field(default=None, serialization_alias="approvalRequestId")
    verification_status: VerificationStatus | None = Field(
        default=None, serialization_alias="verificationStatus"
    )
    clarification: RunClarification | None = None
    verified_refund_request_id: str | None = Field(
        default=None, serialization_alias="verifiedRefundRequestId"
    )
    error_code: str | None = Field(default=None, serialization_alias="errorCode")
    version: int
    checkpoint_compacted_at: datetime | None = Field(
        default=None, serialization_alias="checkpointCompactedAt"
    )


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
    state = record.to_state()
    return AgentRunView(
        run_id=str(record.run_id),
        status=record.status,
        intent=record.intent,
        resolved_order_id=record.resolved_order_id,
        current_node=record.current_node,
        next_action=record.next_action,
        step_count=record.step_count,
        final_action=record.final_action,
        final_message=_final_message(record.status, state),
        approval_request_id=_approval_request_id(state),
        verification_status=state.verification.status if state is not None else None,
        clarification=_clarification_for(record.status, state),
        verified_refund_request_id=_verified_refund_request_id(state),
        error_code=record.error_code,
        version=record.version,
        checkpoint_compacted_at=record.checkpoint_compacted_at,
    )


#: Why a run is waiting for the customer, phrased so the customer can act on it. A Literal rather
#: than an enum because it crosses the API boundary as a plain string.
ClarificationKind = Literal["INTENT_UNKNOWN", "ORDER_AMBIGUOUS"]


class RunClarification(BaseModel):
    """What the customer has to supply before the run can continue.

    Customer-safe by construction: ``candidate_order_ids`` are the caller's own orders, resolved
    through ownership, so publishing them tells the customer nothing they could not already see.
    """

    model_config = ConfigDict(extra="forbid")

    kind: ClarificationKind
    candidate_order_ids: list[str] = Field(
        default_factory=list, serialization_alias="candidateOrderIds"
    )


def _clarification_for(status: RunStatus, state: AgentState | None) -> RunClarification | None:
    """What to ask the customer, derived from the facts the payload recorded.

    The routing decision is not stored, so this rebuilds the question from its inputs - and only
    from inputs that are facts: an unset/UNKNOWN intent, and the candidate orders the understanding
    step recorded. When neither explains the wait, it returns None rather than inventing a question,
    because a customer-facing prompt that might be wrong is worse than no prompt.
    """
    if status is not RunStatus.WAITING_USER or state is None:
        return None
    if state.intent is None or state.intent == "UNKNOWN":
        return RunClarification(kind="INTENT_UNKNOWN")
    if len(state.candidate_order_ids) >= 2:
        return RunClarification(
            kind="ORDER_AMBIGUOUS",
            candidate_order_ids=[str(order_id) for order_id in state.candidate_order_ids],
        )
    return None


def _approval_request_id(state: AgentState | None) -> str | None:
    """The authoritative approval reference, when this run ever had one (US4+)."""
    if state is None or state.approval is None:
        return None
    return state.approval.approval_request_id


def _verified_refund_request_id(state: AgentState | None) -> str | None:
    """The refund id authority confirmed -- and only then.

    A write response that named a refund id is not enough: the whole point of verify-after-write is
    that the response may be lost or may not describe what actually exists. So this field is null
    unless the verification outcome says the authority was read and agreed.
    """
    if state is None or state.verification.status is not VerificationStatus.VERIFIED_SUCCESS:
        return None
    return state.verification.resource_id


def _final_message(status: RunStatus, state: AgentState | None) -> str | None:
    """What happened, said only in terms the run can support.

    Every branch is derived from a terminal status or a verification outcome. No branch repeats a
    model's claim, because "the model said it worked" is not a fact this service may pass on -- and
    for a run whose payload retention has reclaimed, the honest answer is that the detail is gone
    rather than that nothing happened.
    """
    if status is RunStatus.RUNNING:
        return None
    if status is RunStatus.WAITING_USER:
        return "等待用户补充信息后继续。"
    if status is RunStatus.WAITING_APPROVAL:
        return "等待权威审批后继续。"
    if status is RunStatus.ESCALATED:
        return "已转人工处理。"
    if status is RunStatus.SAFE_STOP:
        return _safe_stop_message(state)
    if status is RunStatus.FAILED:
        return "执行失败，未完成。"
    return _completed_message(state)


def _safe_stop_message(state: AgentState | None) -> str:
    """What a stopped run may say about money -- which depends entirely on where it stopped.

    Two different facts share this status, and they must never share a sentence. A *refusal* (no
    evidence, eligibility unavailable) never reached a write, so saying no money moved is a fact. An
    *unconfirmable outcome* is the opposite: the write or the verification went UNKNOWN, which by
    definition means the request may have reached the business side. There, "nothing happened" is a
    lie with money behind it -- and the run's own trace is the only thing that can reconcile it.

    The retired-payload case gets its own sentence for the same reason: not knowing must not be
    rendered as either conclusion.
    """
    if state is None:
        return "处理已停止（该 run 的详细执行状态已按保留策略回收，无法从该记录确认资金处理明细）。"
    unconfirmable = state.verification.status in (
        VerificationStatus.UNKNOWN,
        VerificationStatus.PENDING,
    ) or state.write.status in (WriteStatus.UNKNOWN, WriteStatus.PENDING)
    if unconfirmable:
        return "处理已停止，但当前无法确认退款请求最终是否已提交。请勿重复发起，需要进一步核对。"
    if state.write_intent is None and state.write.status is WriteStatus.NOT_ATTEMPTED:
        return "处理已在安全边界内停止，未发起退款写入。"
    return "处理已停止；最终是否产生资金动作尚需核对。"


def _completed_message(state: AgentState | None) -> str:
    if state is None:
        return "已完成（该 run 的 payload 已按保留策略回收，结果明细不再可得）。"
    if state.verification.status is VerificationStatus.VERIFIED_SUCCESS:
        refund_id = state.verification.resource_id
        if refund_id is None:
            return "退款已创建并通过权威校验。"
        return f"退款已创建并通过权威校验（{refund_id}）。"
    if state.verification.status is VerificationStatus.VERIFIED_FAILURE:
        return "权威状态确认没有这笔退款，未产生资金动作。"
    if state.verification.status in (VerificationStatus.UNKNOWN, VerificationStatus.PENDING):
        # PENDING is not "nothing happened" - a write may be in flight - so it belongs with UNKNOWN:
        # both mean the outcome is not established, and the message must not invent either answer.
        return "退款结果无法确认。"
    return "已完成，本次没有产生退款写入。"


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
    request: Request,
    call: AuthenticatedDep,
    store: StoreDep,
    settings: AppSettings,
) -> AgentRunView:
    """Create a run owned by the authenticated principal, then advance it.

    Three things are worth noticing, because each one is a boundary rather than a detail:

    * ``run_id`` is minted here, not accepted from the body. A caller who could choose the id could
      choose a colliding one.
    * ``principal`` comes from ``call.principal`` -- Java's answer -- and never from the request.
      The request body has no identity field to get it from.
    * The safety budgets from ``settings`` are injected into the state at creation and then
      persisted with it. T015 required this explicitly: a restored checkpoint must keep the budgets
      it was created with, so reading today's config on resume cannot silently widen a run's
      allowance.

    The driver is asked whether it can run **before** anything is written. Creating a run that
    nobody can advance would leave a ``RUNNING`` row that is not resumable by design -
    indistinguishable from work in progress - so a misconfigured deployment refuses the request
    instead. This is also the only entry point for a run's first step: the contract publishes no
    "execute" endpoint, so a run that is never advanced here never moves at all.
    """
    driver = _driver(request)
    driver.check(settings)

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
        next_action=_UNDERSTAND,
    )
    return _view(await driver.run(request, call, RunSession(store, record), settings))


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
    run_id: str,
    body: RunInputRequest,
    request: Request,
    call: AuthenticatedDep,
    store: StoreDep,
    settings: AppSettings,
) -> AgentRunView:
    """Supply clarification text to a ``WAITING_USER`` run, then advance it.

    The order of the first three steps is the design. The follow-up is merged and validated while
    the run is **still waiting**, because refusing afterwards would leave a claimed run with nothing
    to drive it - exactly the state the failure path exists to avoid. Only then is the run claimed,
    and the merged request is checkpointed before the graph reads it: the walk interprets the
    payload, so a clarification that lived only in this process would be invisible to the next
    resume.

    The status check is still the store's, not this handler's. Two places deciding "is this run
    resumable" would be two answers, and the one in SQL is the one that holds under concurrency.
    """
    record = _owned_run(store, run_id, call)
    driver = _driver(request)
    driver.check(settings)
    merged = _merge_user_input(_payload_of(record), body.message)
    resumed = _resume(store, record, current_node=Node.UNDERSTAND.value, next_action=_UNDERSTAND)
    session = RunSession(store, resumed)
    session.checkpoint(
        state=advance(session.state, user_request=merged),
        current_node=Node.UNDERSTAND.value,
        next_action=_UNDERSTAND,
    )
    return _view(await driver.run(request, call, session, settings))


@router.post("/{run_id}/resume")
async def resume_run(
    run_id: str,
    request: Request,
    call: AuthenticatedDep,
    store: StoreDep,
    settings: AppSettings,
    body: ResumeRunRequest | None = None,
) -> AgentRunView:
    """Resume a checkpointed run after an external decision, then advance it.

    ``body.approval_request_id`` is recorded as the caller's *claim* about what it is resuming. It
    is not authority: T049+ must re-read the authoritative approval record from Java before any
    sensitive write. Stated here because the temptation to trust it is exactly what the contract
    warns about, and the field's presence makes that temptation visible.
    """
    record = _owned_run(store, run_id, call)
    driver = _driver(request)
    driver.check(settings)
    resumed = _resume(
        store,
        record,
        current_node=record.current_node or Node.WAITING_USER.value,
        next_action=_UNDERSTAND,
    )
    return _view(await driver.run(request, call, RunSession(store, resumed), settings))


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


#: The node the walk starts at. Spelled the way ``create_run`` already spells it, so the two entry
#: points cannot disagree about what a freshly woken run is about to do.
#: The node a freshly claimed run will execute next. It is a *reference* to the graph's vocabulary
#: rather than a second literal: storing "understand_request" while the graph calls the node
#: "understand" makes the run row describe a graph that does not exist.
_UNDERSTAND = Node.UNDERSTAND.value

#: How a follow-up is appended to the original request. A visible marker rather than a bare
#: concatenation, so a reviewer reading the payload can tell what the user typed when.
_USER_INPUT_SEPARATOR = "\n\n[follow-up] "

#: The same cap ``AgentState.user_request`` declares. Duplicated deliberately: refusing with a clear
#: 422 needs the number *before* anything is constructed, and a behavioural test asserts that 4000
#: characters are accepted while 4001 are not, so the copy cannot drift unnoticed.
_USER_REQUEST_MAX = 4000


def _merge_user_input(state: AgentState, text: str) -> str:
    """Append clarification text to the request, or refuse when it would not fit.

    Truncating is not an option. A request cut in half is still a well-formed request to everything
    downstream, which is how a silent cut becomes a wrong answer that nobody can trace back.
    """
    merged = f"{state.user_request}{_USER_INPUT_SEPARATOR}{text}"
    if len(merged) > _USER_REQUEST_MAX:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="USER_REQUEST_TOO_LONG",
        )
    return merged


def _payload_of(record: RunRecord) -> AgentState:
    """The run's payload, or the status that says why there is none."""
    state = record.to_state()
    if state is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="RUN_CHECKPOINT_COMPACTED",
        )
    return state


def _client(request: Request) -> CommerceClient:
    """The shared Commerce HTTP client, or a 503 if this app was built without one."""
    client = getattr(request.app.state, "commerce_client", None)
    if client is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="COMMERCE_CLIENT_UNAVAILABLE",
        )
    return cast(CommerceClient, client)


def _model_api_key(settings: Settings) -> SecretStr:
    """The model credential, or the status that says why this request cannot be served.

    Called in two places on purpose. The driver's ``check`` needs it *before* a run exists, so a
    misconfigured deployment refuses the request instead of leaving a ``RUNNING`` row nobody will
    advance - and ``RUNNING`` is deliberately not resumable. ``run`` asks again rather than trusting
    that ``check`` was called first: a driver should not be correct only in the order someone else
    happens to use it.
    """
    if not settings.is_model_api_key_configured or settings.model_api_key is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="MODEL_API_KEY_NOT_CONFIGURED",
        )
    return settings.model_api_key


class RunDriver(Protocol):
    """How a run is advanced, as a seam rather than an inline call.

    Two methods rather than one, because the precondition has to be answerable in the one window
    where nothing has been written yet: between accepting a request and creating or claiming a run.
    Keeping the check on the driver also keeps it honest - only the real driver needs a model, so a
    test double has nothing to stub out and no configuration to pretend to have.
    """

    def check(self, settings: Settings) -> None:
        """Raise the HTTP status that explains why this driver cannot run right now."""
        ...

    async def run(
        self,
        request: Request,
        call: AuthenticatedCall,
        session: RunSession,
        settings: Settings,
    ) -> RunRecord:
        """Advance the run this session holds, and return the record it stopped on."""
        ...


class GraphRunDriver:
    """The production driver: assemble this request's graph and walk the run to its next stop.

    The walk is synchronous on purpose, and moving it to a worker later would change *where* this
    runs rather than what it guarantees: the caller already holds the version it claimed, so it is
    the only process allowed to write, and every write goes through the same compare-and-swap. What
    a synchronous walk buys today is that a failure reaches the caller instead of vanishing into a
    queue.

    The graph is assembled per request because the credential is per request. A shared graph would
    have to hold one caller's credential, which is the same mistake as sharing a database session
    that carries a user's permissions.
    """

    def check(self, settings: Settings) -> None:
        _model_api_key(settings)

    async def run(
        self,
        request: Request,
        call: AuthenticatedCall,
        session: RunSession,
        settings: Settings,
    ) -> RunRecord:
        tools = CommerceTools(client=_client(request), auth=call.auth)
        try:
            async with OpenAICompatibleJsonClient(
                base_url=settings.model_base_url,
                api_key=_model_api_key(settings),
                model_name=settings.model_name,
                temperature=settings.model_temperature,
                timeout_seconds=settings.model_timeout_seconds,
            ) as model_client:
                graph = build_agent_graph(
                    tools=tools,
                    model_client=model_client,
                    persist_intent=session.persist_intent,
                    record_trace=session.record_trace,
                )
                return await drive_graph(graph, session)
        except RunStoreError as exc:
            # A store refusal is a statement about this run's state - a stale version, someone else
            # holding it, a terminal status - so it maps to 409 rather than to a server fault.
            raise _http_error_for(exc, str(session.record.run_id)) from exc


def _driver(request: Request) -> RunDriver:
    """This app's run driver. Installed by ``create_app``, so its absence is a wiring fault."""
    driver = getattr(request.app.state, "run_driver", None)
    if driver is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="RUN_DRIVER_UNAVAILABLE",
        )
    return cast(RunDriver, driver)


def _prompt_version() -> str:
    """The prompt/graph version recorded on every run.

    A literal for now: T030 introduces the graph whose version this should track. Recorded at
    creation rather than derived later because a run must be explainable by the configuration that
    produced it, not by whatever the configuration is when someone reads it.
    """
    return "t032-us1-runtime-v1"
