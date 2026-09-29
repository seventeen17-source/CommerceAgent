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

from app.agent.evidence_routing import EvidenceAction, EvidenceGuardStatus, EvidenceToolName
from app.agent.state import AgentState, RunStatus, VerificationStatus, WriteStatus

__all__ = [
    "NON_REFUND_ACTIONS",
    "REFUND_PERMITTING_ACTIONS",
    "Decision",
    "Node",
    "SafeStopReason",
    "TerminalDecision",
    "budget_exhausted",
    "route_after_decision",
    "route_after_eligibility",
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
    REFUND_WRITE = "refund_write"
    VERIFY = "verify"
    FINALIZE = "finalize"
    WAITING_USER = "waiting_user"
    SAFE_STOP = "safe_stop"


class SafeStopReason(StrEnum):
    """Why the Agent deliberately refused to continue, or could not establish reality."""

    ORDER_UNRESOLVED = "ORDER_UNRESOLVED"
    ELIGIBILITY_UNKNOWN_ACTION = "ELIGIBILITY_UNKNOWN_ACTION"
    ELIGIBILITY_INCONSISTENT = "ELIGIBILITY_INCONSISTENT"
    ELIGIBILITY_APPROVAL_REQUIRED = "ELIGIBILITY_APPROVAL_REQUIRED"
    ELIGIBILITY_AMOUNT_UNBOUNDED = "ELIGIBILITY_AMOUNT_UNBOUNDED"
    WRITE_INTENT_NOT_DURABLE = "WRITE_INTENT_NOT_DURABLE"
    WRITE_FINGERPRINT_DRIFT = "WRITE_FINGERPRINT_DRIFT"
    BUDGET_EXHAUSTED = "BUDGET_EXHAUSTED"
    VERIFICATION_UNKNOWN = "VERIFICATION_UNKNOWN"


#: Java ``AllowedAction`` values (mirrors the V001 CHECK constraint). The wire value is an open
#: string on purpose - see the cross-service value policy in ``state.py`` - so a value we do not
#: recognise must safe-stop rather than be coerced into a known one.
REFUND_PERMITTING_ACTIONS: Final[frozenset[str]] = frozenset({"REFUND_ONLY", "RETURN_REFUND"})
NON_REFUND_ACTIONS: Final[frozenset[str]] = frozenset({"RETURN", "MANUAL_REVIEW", "DENY"})


class Decision(BaseModel):
    """Transient control-plane facts produced by the current node and consumed by the router.

    Deliberately **not** part of ``AgentState``: nothing here is a durable business fact, and
    persisting a model proposal next to authoritative facts is how a proposal starts looking like
    evidence. The durable equivalents are the run row's ``next_action`` and the Tool trace.
    """

    model_config = ConfigDict(extra="forbid")

    action: EvidenceAction | None = None
    tool: EvidenceToolName | None = None
    guard_status: EvidenceGuardStatus | None = None
    #: Whether the node already asked Java to resolve an order. Without this flag "no order
    #: resolved" is indistinguishable from "resolution has not started yet", and the same
    #: state-derived rule would misfire at the understand edge.
    resolution_attempted: bool = False
    #: Declared by the node that detected a boundary condition itself (for example a write whose
    #: intent could not be persisted). Routers surface it; they never invent a reason of their own.
    safe_stop_reason: SafeStopReason | None = None


class TerminalDecision(BaseModel):
    """The lifecycle status a run ends on, plus the reason when it ends as ``SAFE_STOP``."""

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
            and len(state.candidate_order_ids) < 2
        ):
            return SafeStopReason.ORDER_UNRESOLVED

    snapshot = state.eligibility
    if snapshot is not None:
        action = snapshot.allowed_action
        if action not in REFUND_PERMITTING_ACTIONS and action not in NON_REFUND_ACTIONS:
            return SafeStopReason.ELIGIBILITY_UNKNOWN_ACTION
        if snapshot.eligible and action not in REFUND_PERMITTING_ACTIONS:
            return SafeStopReason.ELIGIBILITY_INCONSISTENT
        if snapshot.eligible and action in REFUND_PERMITTING_ACTIONS:
            if snapshot.approval_required:
                # US1 has no HITL wiring yet (T049). Refusing is the only safe reading of
                # "approval required": the alternative is moving money without the approval.
                return SafeStopReason.ELIGIBILITY_APPROVAL_REQUIRED
            if snapshot.max_refund_amount is None:
                # Java is the money authority and it did not bound the amount. An unbounded write
                # is not something the Agent may decide for itself.
                return SafeStopReason.ELIGIBILITY_AMOUNT_UNBOUNDED
    return None


def route_after_understand(state: AgentState, decision: Decision | None = None) -> Node:
    """After request understanding: resolve the order, or refuse."""
    if state.is_terminal:
        return Node.FINALIZE
    if safe_stop_reason_for(state, decision) is not None:
        return Node.SAFE_STOP
    return Node.RESOLVE_ORDER


def route_after_resolve_order(state: AgentState, decision: Decision | None = None) -> Node:
    """After order resolution: continue, ask the user, or refuse.

    Several matching orders is a question for the user, not a ranking problem: picking "the most
    likely" order would let a guess decide whose refund is created.
    """
    if state.is_terminal:
        return Node.FINALIZE
    if safe_stop_reason_for(state, decision) is not None:
        return Node.SAFE_STOP
    if state.resolved_order_id is not None:
        return Node.DECIDE_EVIDENCE
    if len(state.candidate_order_ids) >= 2:
        return Node.WAITING_USER
    # Unresolved with nothing to ask about: the node must have declared ORDER_UNRESOLVED. Refusing
    # here keeps the routing table total even if it did not.
    return Node.SAFE_STOP


def route_after_decision(state: AgentState, decision: Decision | None = None) -> Node:
    """After the evidence proposal and its guard: execute it, or end evidence collection.

    A denied proposal ends *that tool call*, not the run: with less evidence the deterministic Java
    eligibility service still decides, and it is the authority. A missing proposal is different -
    there is no legal next step to invent, so the run refuses.
    """
    if state.is_terminal:
        return Node.FINALIZE
    if safe_stop_reason_for(state, decision) is not None:
        return Node.SAFE_STOP
    if decision is None or decision.action is None:
        return Node.SAFE_STOP
    if decision.action is EvidenceAction.CALL_TOOL:
        if decision.guard_status is not EvidenceGuardStatus.ALLOWED:
            return Node.CHECK_ELIGIBILITY
        return Node.EXECUTE_EVIDENCE
    return Node.CHECK_ELIGIBILITY


def route_after_eligibility(state: AgentState, decision: Decision | None = None) -> Node:
    """After Java's eligibility decision: write, or finish without writing."""
    if state.is_terminal:
        return Node.FINALIZE
    if safe_stop_reason_for(state, decision) is not None:
        return Node.SAFE_STOP
    snapshot = state.eligibility
    if (
        snapshot is not None
        and snapshot.eligible
        and snapshot.allowed_action in REFUND_PERMITTING_ACTIONS
    ):
        return Node.REFUND_WRITE
    return Node.FINALIZE


def route_after_write(state: AgentState, decision: Decision | None = None) -> Node:
    """After the write attempt: always read authority back, unless nothing was ever sent."""
    if state.is_terminal:
        return Node.FINALIZE
    if safe_stop_reason_for(state, decision) is not None:
        return Node.SAFE_STOP
    if state.write.status is WriteStatus.NOT_ATTEMPTED:
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
