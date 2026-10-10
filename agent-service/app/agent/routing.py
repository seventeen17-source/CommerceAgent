"""Deterministic routing and budget enforcement for the T032 graph.

The LLM proposes; this module constrains. Every edge is computed from authoritative ``AgentState``
facts plus, where a node produced one, the *validated* proposal - never from raw model text.

Three conventions keep this honest:

* Node names live in one enum, so a typo becomes an import-time failure instead of a node that can
  never be reached.
* Every refusal carries a machine-readable :class:`SafeStopReason`. ``SAFE_STOP`` means "continuing
  could cross a safety boundary"; ``RunStatus.FAILED`` is reserved for "our side could not execute".
  Collapsing the two would make an agent that correctly declined to move money look like an outage.
* **Node contract**: a node that cannot produce a legal next step declares *why* on the
  :class:`Decision` it returns. Routers never invent a reason, and a router that refuses without one
  is an incomplete routing table - the terminal node then raises instead of finishing quietly.
  Failing loud is deliberate here: a silent ``COMPLETED`` on a refused run is the one outcome that
  would look like success to everyone downstream.

The functions here are pure: they take a validated state (and optionally the current node's
proposal) and return a node name. ``graph.py`` adapts them to LangGraph's conditional edges, so this
module stays testable without building a graph.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Final

from pydantic import BaseModel, ConfigDict, model_validator

from app.agent.evidence_routing import (
    EvidenceAction,
    EvidenceGuardDecision,
    EvidenceGuardStatus,
)
from app.agent.request_understanding import RequestIntent
from app.agent.state import AgentState, RunStatus, VerificationStatus, WriteStatus

__all__ = [
    "MONEY_GRANTING_ACTIONS",
    "NON_WRITE_ACTIONS",
    "REFUND_PERMITTING_ACTIONS",
    "RETURN_PERMITTING_ACTIONS",
    "Decision",
    "HandoffReason",
    "Node",
    "SafeStopReason",
    "TerminalDecision",
    "budget_exhausted",
    "eligibility_handoff",
    "handoff_reason_for",
    "route_after_decision",
    "route_after_eligibility",
    "route_after_execute",
    "route_after_request_approval",
    "route_after_resolve_order",
    "route_after_understand",
    "route_after_write",
    "safe_stop_reason_for",
    "terminal_decision_for",
]


class Node(StrEnum):
    """Graph node names; also the return value of every ``route_*`` function."""

    UNDERSTAND = "understand"
    RESOLVE_ORDER = "resolve_order"
    DECIDE_EVIDENCE = "decide_evidence"
    EXECUTE_EVIDENCE = "execute_evidence"
    CHECK_ELIGIBILITY = "check_eligibility"
    REQUEST_APPROVAL = "request_approval"
    REFUND_WRITE = "refund_write"
    RETURN_WRITE = "return_write"
    VERIFY = "verify"
    FINALIZE = "finalize"
    WAITING_USER = "waiting_user"
    WAITING_APPROVAL = "waiting_approval"
    SAFE_STOP = "safe_stop"


class SafeStopReason(StrEnum):
    """Why the Agent deliberately refused to continue, or could not establish reality."""

    ORDER_UNRESOLVED = "ORDER_UNRESOLVED"
    EVIDENCE_CONTEXT_MISSING = "EVIDENCE_CONTEXT_MISSING"
    ELIGIBILITY_UNAVAILABLE = "ELIGIBILITY_UNAVAILABLE"
    ELIGIBILITY_UNKNOWN_ACTION = "ELIGIBILITY_UNKNOWN_ACTION"
    ELIGIBILITY_INCONSISTENT = "ELIGIBILITY_INCONSISTENT"
    ELIGIBILITY_APPROVAL_REQUIRED = "ELIGIBILITY_APPROVAL_REQUIRED"
    APPROVAL_REQUEST_FAILED = "APPROVAL_REQUEST_FAILED"
    APPROVAL_RESPONSE_INCONSISTENT = "APPROVAL_RESPONSE_INCONSISTENT"
    APPROVAL_STATE_UNVERIFIED = "APPROVAL_STATE_UNVERIFIED"
    APPROVAL_BINDING_MISMATCH = "APPROVAL_BINDING_MISMATCH"
    ELIGIBILITY_AMOUNT_UNBOUNDED = "ELIGIBILITY_AMOUNT_UNBOUNDED"
    WRITE_INTENT_NOT_DURABLE = "WRITE_INTENT_NOT_DURABLE"
    WRITE_FINGERPRINT_DRIFT = "WRITE_FINGERPRINT_DRIFT"
    BUDGET_EXHAUSTED = "BUDGET_EXHAUSTED"
    VERIFICATION_UNKNOWN = "VERIFICATION_UNKNOWN"


#: Java ``AllowedAction`` values (mirrors the V001 CHECK constraint). The wire value is an open
#: string on purpose - see the cross-service value policy in ``state.py`` - so a value we do not
#: recognise must safe-stop rather than be coerced into a known one.
#:
#: T041 moved ``RETURN_REFUND`` out of this set. "Return and refund" is no longer authorised by one
#: Java decision: ``POST /returns`` creates the return row, and moving money needs its own
#: authorisation (the refund write path only accepts ``REFUND_ONLY``). Treating it as
#: refund-permitting would keep routing it at a write Java refuses -- the "safe but impossible"
#: state US2 exists to remove.
REFUND_PERMITTING_ACTIONS: Final[frozenset[str]] = frozenset({"REFUND_ONLY"})
#: Actions the Agent executes on the **return** path (T041).
RETURN_PERMITTING_ACTIONS: Final[frozenset[str]] = frozenset({"RETURN", "RETURN_REFUND"})
#: Recognised actions that authorise no write at all.
NON_WRITE_ACTIONS: Final[frozenset[str]] = frozenset({"MANUAL_REVIEW", "DENY"})
#: Actions whose execution moves money. Only these require an authoritative amount bound: a pure
#: return carries no amount by contract, so a null one there is the normal shape, not a gap.
MONEY_GRANTING_ACTIONS: Final[frozenset[str]] = frozenset({"REFUND_ONLY", "RETURN_REFUND"})


class Decision(BaseModel):
    """Transient control-plane facts produced by the current node and consumed by the router.

    Deliberately **not** part of ``AgentState``: nothing here is a durable business fact, and
    persisting a model proposal next to authoritative facts is how a proposal starts looking like
    evidence. The durable equivalents are the run row's ``next_action`` and the Tool trace.
    """

    model_config = ConfigDict(extra="forbid")

    #: The authorization artifact itself, not a projection of it. Two nodes consume this: the router
    #: reads it to pick the next edge, and the execution node hands it to the Tool layer, which
    #: re-checks `status`. Copying its fields into a slimmer shape would mean rebuilding an
    #: authorization from memory before executing it - the reconstruction can drift from what was
    #: actually authorized, and nothing would notice.
    guard: EvidenceGuardDecision | None = None
    #: Set by the execution node when the evidence path it was working on is closed, because a read
    #: failed in a way a retry cannot fix. This is a **fact about that path**, not a routing
    #: decision: the node neither knows nor chooses where the run goes next. Mapping it to the
    #: eligibility handoff is ``route_after_decision``'s job, so changing where it leads is only a
    #: routing change.
    evidence_path_closed: bool = False
    #: Set by a node that failed transiently and still has budget: another attempt at *the same
    #: stage* is warranted. Also a fact, not a decision - and one mechanism for both stages, so
    #: "retry" cannot mean one thing here and something else there.
    retry_current_stage: bool = False
    #: Whether the node already asked Java to resolve an order. Without this flag "no order
    #: resolved" is indistinguishable from "resolution has not started yet", and the same
    #: state-derived rule would misfire at the understand edge.
    resolution_attempted: bool = False
    #: Declared by the node that detected a boundary condition itself (for example a write whose
    #: intent could not be persisted). Routers surface it; they never invent a reason of their own.
    safe_stop_reason: SafeStopReason | None = None
    #: The status this invocation leaves the run in, produced by the node that ends it. The node
    #: stops there: writing a status belongs to the wrapper, so the nodes that end a run hold no
    #: store and can be tested without a database. ``None`` means "this node is not ending the run",
    #: which is also what an already-terminal run reports - re-deriving its status would mean
    #: inventing the reason it stopped.
    terminal: TerminalDecision | None = None


class TerminalDecision(BaseModel):
    """The status one invocation leaves the run in, plus the reason when it is ``SAFE_STOP``.

    ``WAITING_USER`` ends the *invocation* while the run stays resumable, so "terminal" here means
    "this invocation has nothing left to do", not "this run can never move again".
    """

    model_config = ConfigDict(extra="forbid")

    status: RunStatus
    reason: SafeStopReason | None = None

    @model_validator(mode="after")
    def validate_reason_pairing(self) -> TerminalDecision:
        """Make the safety contract structural: no silent safe-stop, no reason on a clean end."""
        if self.status is RunStatus.SAFE_STOP and self.reason is None:
            raise ValueError("SAFE_STOP requires a machine-readable reason")
        if self.status is not RunStatus.SAFE_STOP and self.reason is not None:
            raise ValueError("only SAFE_STOP carries a safety reason")
        return self


class HandoffReason(StrEnum):
    """Which of the three ways the evidence stage ended. Recorded on the handoff token."""

    MODEL_SAID_ENOUGH = "MODEL_SAID_ENOUGH"
    EVIDENCE_PROPOSAL_DENIED = "EVIDENCE_PROPOSAL_DENIED"
    EVIDENCE_PATH_CLOSED = "EVIDENCE_PATH_CLOSED"


def handoff_reason_for(decision: Decision | None) -> HandoffReason:
    """Classify how evidence collection ended, from the control-plane facts alone."""
    if decision is not None and decision.evidence_path_closed:
        return HandoffReason.EVIDENCE_PATH_CLOSED
    guard = decision.guard if decision is not None else None
    if guard is not None and guard.action is EvidenceAction.READY_FOR_ELIGIBILITY:
        return HandoffReason.MODEL_SAID_ENOUGH
    return HandoffReason.EVIDENCE_PROPOSAL_DENIED


def eligibility_handoff(decision: Decision | None) -> EvidenceGuardDecision:
    """The routing layer's token for "evidence collection is over; ask Java".

    This is **not an authorization of a tool call** - nothing is being permitted to run. It is the
    token ``check_eligibility`` requires to prove the caller is at the eligibility stage, and it is
    produced by the routing layer because "the evidence stage is over, go to eligibility" *is* a
    routing decision. Producing it in the node would mean the node minting its own permission;
    producing it in the guard would mean the guard authorizing something nobody proposed.

    Rebuilding it from facts is safe, unlike rebuilding an authorization: the same facts always
    yield the same token, and the reason it carries is the provenance of the handoff rather than a
    permission - which is why the trace can tell "the model said it had enough" apart from "a read
    failed and we handed off with less".
    """
    return EvidenceGuardDecision(
        status=EvidenceGuardStatus.ALLOWED,
        action=EvidenceAction.READY_FOR_ELIGIBILITY,
        tool=None,
        reason_code=handoff_reason_for(decision).value,
    )


def budget_exhausted(state: AgentState) -> bool:
    """Whether the step budget is already spent.

    Checked at every edge *before* a node is entered, so a node can never start work whose result
    cannot be recorded. ``AgentState.validate_budgets`` remains the fail-closed backstop for states
    restored from a checkpoint written by an older, more permissive version.
    """
    return state.step_count >= state.max_steps


def safe_stop_reason_for(
    state: AgentState, decision: Decision | None = None
) -> SafeStopReason | None:
    """The single place that decides whether continuing would cross a safety boundary.

    Only facts that are meaningful regardless of the current stage are read here. Stage-specific
    refusals (for example "resolution ran and found nothing") arrive through ``decision``, so this
    function cannot misfire before that stage has run.
    """
    if budget_exhausted(state):
        return SafeStopReason.BUDGET_EXHAUSTED

    if decision is not None:
        if decision.safe_stop_reason is not None:
            return decision.safe_stop_reason
        if (
            decision.resolution_attempted
            and state.resolved_order_id is None
            # A zero match has its own answer (ask about the clue), so it must not be read here as
            # "resolution found nothing". The count test below only distinguishes the several-
            # candidates case, which is why the flag has to be checked alongside it.
            and not state.clue_matched_nothing
            and len(state.candidate_order_ids) < 2
        ):
            return SafeStopReason.ORDER_UNRESOLVED

    snapshot = state.eligibility
    if state.approval is not None and state.approval.status == "APPROVED":
        if not state.approval.binding_verified:
            return SafeStopReason.APPROVAL_STATE_UNVERIFIED
        if snapshot is not None and snapshot.approval_required:
            if not _verified_approval_matches_current_eligibility(state):
                return SafeStopReason.APPROVAL_BINDING_MISMATCH
    if snapshot is not None:
        action = snapshot.allowed_action
        if (
            action not in REFUND_PERMITTING_ACTIONS
            and action not in RETURN_PERMITTING_ACTIONS
            and action not in NON_WRITE_ACTIONS
        ):
            return SafeStopReason.ELIGIBILITY_UNKNOWN_ACTION
        if snapshot.eligible and action in NON_WRITE_ACTIONS:
            return SafeStopReason.ELIGIBILITY_INCONSISTENT
        if snapshot.eligible:
            # T054: budget belongs to the entire run (including HITL resume). A protected
            # write requires one step to issue the write and another to re-read Java authority.
            # Refuse BEFORE the write if that verification cannot fit. Approval creation is
            # not itself a refund/return; only reserve here when the next step can be a write.
            may_write = (
                not snapshot.approval_required
                or _verified_approval_matches_current_eligibility(state)
            )
            if (
                may_write
                and state.write_intent is None
                and state.write.status is WriteStatus.NOT_ATTEMPTED
                and action in REFUND_PERMITTING_ACTIONS | RETURN_PERMITTING_ACTIONS
                and state.step_count + 2 > state.max_steps
            ):
                return SafeStopReason.BUDGET_EXHAUSTED
            if action in MONEY_GRANTING_ACTIONS and snapshot.max_refund_amount is None:
                # Java is the money authority and it did not bound the amount. An unbounded write
                # is not something the Agent may decide for itself.
                return SafeStopReason.ELIGIBILITY_AMOUNT_UNBOUNDED
    return None


def route_after_understand(state: AgentState, decision: Decision | None = None) -> Node:
    """After request understanding: resolve the order, ask the user, or refuse.

    An unrecognised intent asks rather than guesses: with no goal we cannot tell which capability
    would even be appropriate, and inventing one is how an agent starts doing work nobody asked for.
    """
    if state.is_terminal:
        return Node.FINALIZE
    if safe_stop_reason_for(state, decision) is not None:
        return Node.SAFE_STOP
    if state.intent is None or state.intent == RequestIntent.UNKNOWN.value:
        return Node.WAITING_USER
    return Node.RESOLVE_ORDER


def route_after_resolve_order(state: AgentState, decision: Decision | None = None) -> Node:
    """After order resolution: continue, ask the user, or refuse.

    Several matching orders is a question for the user, not a ranking problem: picking "the most
    likely" order would let a guess decide whose refund is created. A clue that matched *nothing* is
    also a question, and a different one: the fallback list may hold a single order, and resolving
    that one would silently answer a question the clue never answered.
    """
    if state.is_terminal:
        return Node.FINALIZE
    if safe_stop_reason_for(state, decision) is not None:
        return Node.SAFE_STOP
    if state.resolved_order_id is not None:
        return Node.DECIDE_EVIDENCE
    if state.clue_matched_nothing:
        return Node.WAITING_USER
    if len(state.candidate_order_ids) >= 2:
        return Node.WAITING_USER
    # Unresolved with nothing to ask about: the node must have declared ORDER_UNRESOLVED. Refusing
    # here keeps the routing table total even if it did not.
    return Node.SAFE_STOP


def route_after_decision(state: AgentState, decision: Decision | None = None) -> Node:
    """After the evidence proposal and its guard: execute it, hand off, or refuse.

    A denied proposal ends *that tool call*, not the run: with less evidence the deterministic Java
    eligibility service still decides, and it is the authority. A read that failed in a way a retry
    cannot fix arrives here as a closed path and is handed off the same way, because one missing
    piece of evidence is not an outage. A missing proposal is different: there is no legal next step
    to invent, so the run refuses.
    """
    if state.is_terminal:
        return Node.FINALIZE
    if safe_stop_reason_for(state, decision) is not None:
        return Node.SAFE_STOP
    if decision is None:
        return Node.SAFE_STOP
    if decision.evidence_path_closed:
        return Node.CHECK_ELIGIBILITY
    guard = decision.guard
    if guard is None:
        return Node.SAFE_STOP
    if guard.action is EvidenceAction.CALL_TOOL:
        if guard.status is not EvidenceGuardStatus.ALLOWED:
            return Node.CHECK_ELIGIBILITY
        return Node.EXECUTE_EVIDENCE
    return Node.CHECK_ELIGIBILITY


def route_after_execute(state: AgentState, decision: Decision | None = None) -> Node:
    """After one evidence read: deliberate again, or take another run at the authorized read.

    A transient failure retries the action that was *already authorized* rather than asking the
    model again. The decision was "read logistics"; a 503 does not change it, and re-deliberating
    would spend a model call to possibly reach a different conclusion about the same missing fact.
    """
    if state.is_terminal:
        return Node.FINALIZE
    if safe_stop_reason_for(state, decision) is not None:
        return Node.SAFE_STOP
    if decision is not None and decision.retry_current_stage:
        return Node.EXECUTE_EVIDENCE
    return Node.DECIDE_EVIDENCE


def _verified_approval_matches_current_eligibility(state: AgentState) -> bool:
    approval = state.approval
    eligibility = state.eligibility
    if (
        approval is None
        or eligibility is None
        or not approval.binding_verified
        or approval.status != "APPROVED"
        or approval.run_id != state.run_id
        or approval.order_id != state.resolved_order_id
        or approval.action_type != eligibility.allowed_action
    ):
        return False
    return approval.amount == eligibility.max_refund_amount


def route_after_eligibility(state: AgentState, decision: Decision | None = None) -> Node:
    """After Java's eligibility decision: write, retry the question, or finish without writing."""
    if state.is_terminal:
        return Node.FINALIZE
    if safe_stop_reason_for(state, decision) is not None:
        return Node.SAFE_STOP
    if decision is not None and decision.retry_current_stage:
        return Node.CHECK_ELIGIBILITY
    snapshot = state.eligibility
    if snapshot is None:
        # Only reachable if a node failed without declaring why; the safe_stop node will refuse to
        # finish quietly, which is the intended outcome for an incomplete routing table.
        return Node.SAFE_STOP
    if snapshot.eligible and snapshot.approval_required:
        if _verified_approval_matches_current_eligibility(state):
            if snapshot.allowed_action in REFUND_PERMITTING_ACTIONS:
                return Node.REFUND_WRITE
            if snapshot.allowed_action in RETURN_PERMITTING_ACTIONS:
                return Node.RETURN_WRITE
            return Node.SAFE_STOP
        if state.approval is not None and state.approval.status == "APPROVED":
            return Node.SAFE_STOP
        return Node.REQUEST_APPROVAL
    if snapshot.eligible and snapshot.allowed_action in REFUND_PERMITTING_ACTIONS:
        return Node.REFUND_WRITE
    if snapshot.eligible and snapshot.allowed_action in RETURN_PERMITTING_ACTIONS:
        # T041: a delivered order inside its window is executed on the return path. Routing
        # ``RETURN_REFUND`` here rather than to the refund write is the whole point of US2: the two
        # halves of "return and refund" are separate authorised writes.
        return Node.RETURN_WRITE
    return Node.FINALIZE


def route_after_request_approval(state: AgentState, decision: Decision | None = None) -> Node:
    """After creating the authoritative approval: park the run or fail closed."""
    if state.is_terminal:
        return Node.FINALIZE
    if safe_stop_reason_for(state, decision) is not None:
        return Node.SAFE_STOP
    snapshot = state.approval
    if (
        snapshot is not None
        and snapshot.approval_request_id is not None
        and snapshot.status == "PENDING"
    ):
        return Node.WAITING_APPROVAL
    return Node.SAFE_STOP


def route_after_write(state: AgentState, decision: Decision | None = None) -> Node:
    """After the write attempt: read authority back, unless nothing was ever sent.

    Verification is scoped by the idempotency key, so it needs a durable intent to ask with. No
    intent means nothing was ever sent (T022) - which also means there is no question to ask, and no
    key to ask it with.
    """
    if state.is_terminal:
        return Node.FINALIZE
    if safe_stop_reason_for(state, decision) is not None:
        return Node.SAFE_STOP
    if state.write_intent is None or state.write.status is WriteStatus.NOT_ATTEMPTED:
        return Node.FINALIZE
    # Any attempted write is verified against Java, including one reported as succeeded: a write
    # response is not the final business fact.
    return Node.VERIFY


def terminal_decision_for(state: AgentState) -> TerminalDecision:
    """Map durable facts to the lifecycle status this run ends on.

    A verified outcome - success *or* failure - is a legitimate completion: the run reached a
    conclusion Java confirmed. An unconfirmable outcome is a ``SAFE_STOP``, and the reason keeps its
    trace: T017's retention keeps trace for ``SAFE_STOP`` for 90 days while ``COMPLETED`` is
    compacted after 7. When money may have moved and we cannot say so, that trace is the only thing
    that can be reconciled.
    """
    verification = state.verification.status
    if verification is VerificationStatus.VERIFIED_SUCCESS:
        return TerminalDecision(status=RunStatus.COMPLETED)
    if verification is VerificationStatus.VERIFIED_FAILURE:
        return TerminalDecision(status=RunStatus.COMPLETED)
    if verification is VerificationStatus.UNKNOWN:
        return TerminalDecision(
            status=RunStatus.SAFE_STOP, reason=SafeStopReason.VERIFICATION_UNKNOWN
        )
    if state.write.status is WriteStatus.UNKNOWN:
        return TerminalDecision(
            status=RunStatus.SAFE_STOP, reason=SafeStopReason.VERIFICATION_UNKNOWN
        )
    return TerminalDecision(status=RunStatus.COMPLETED)
