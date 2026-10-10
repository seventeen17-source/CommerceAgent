"""Unit tests for the T032 routing table, budget guard and the validated state seam.

These are pure: no database, no model, no HTTP. The point is that every edge and every refusal is
decided by data we can construct exactly, so a regression in the safety policy fails here instead of
showing up as money moving.
"""

from __future__ import annotations

import re
from decimal import Decimal
from pathlib import Path
from typing import Any, TypedDict
from uuid import uuid4

import pytest
from langgraph.graph import END, START, StateGraph
from pydantic import ValidationError

from app.agent.evidence_routing import (
    EvidenceAction,
    EvidenceGuardDecision,
    EvidenceGuardStatus,
)
from app.agent.routing import (
    Decision,
    HandoffReason,
    Node,
    SafeStopReason,
    TerminalDecision,
    budget_exhausted,
    eligibility_handoff,
    handoff_reason_for,
    route_after_decision,
    route_after_eligibility,
    route_after_execute,
    route_after_resolve_order,
    route_after_understand,
    route_after_write,
    safe_stop_reason_for,
    terminal_decision_for,
)
from app.agent.state import AgentState, RunStatus, VerificationStatus, WriteStatus, advance

AGENT_DIR = Path(__file__).resolve().parents[2] / "app" / "agent"


class Walk(TypedDict):
    """Minimal graph state, used only by the langgraph interoperability test below.

    Module level on purpose: the module uses `from __future__ import annotations`, so langgraph
    resolves the schema's type hints against module globals. A class defined inside a test function
    is not reachable there and resolution fails with `NameError`.
    """

    trail: str


def make_state(**overrides: Any) -> AgentState:
    """A minimal valid state; tests override only the fact they are judging."""
    base: dict[str, Any] = {
        "run_id": uuid4(),
        "principal": {"user_id": "customer-001", "role": "CUSTOMER"},
        "user_request": "我的包裹卡在路上了，我要退款",
        "intent": "REFUND_REQUEST",
    }
    base.update(overrides)
    return AgentState.model_validate(base)


def make_eligibility(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "eligible": True,
        "allowed_action": "REFUND_ONLY",
        "max_refund_amount": Decimal("199.00"),
        "approval_required": False,
    }
    base.update(overrides)
    return base


def make_intent(**overrides: Any) -> dict[str, Any]:
    """A durable write intent, as T022 persists it before the request is sent."""
    base: dict[str, Any] = {
        "action": "CREATE_REFUND_REQUEST",
        "target_id": "order-001",
        "idempotency_key": "0123456789abcdef",
        "request_fingerprint": "a" * 64,
    }
    base.update(overrides)
    return base


class TestAdvance:
    """`advance()` is the only legal state mutation; it must validate, not just copy."""

    def test_applies_the_change_and_validates_nested_models(self) -> None:
        state = make_state()
        moved = advance(state, resolved_order_id="order-001", step_count=1)
        assert moved.resolved_order_id == "order-001"
        assert moved.step_count == 1
        assert moved.verification.status is VerificationStatus.NOT_RUN

    def test_leaves_the_original_untouched(self) -> None:
        state = make_state()
        advance(state, step_count=3)
        assert state.step_count == 0

    def test_refuses_to_exceed_the_step_budget(self) -> None:
        state = make_state(step_count=12, max_steps=12)
        with pytest.raises(ValidationError):
            advance(state, step_count=13)

    def test_refuses_an_undeclared_field(self) -> None:
        state = make_state()
        with pytest.raises(ValidationError):
            advance(state, ownership_verified=True)

    def test_rebuilds_through_validation_not_model_copy(self) -> None:
        """The difference is the whole reason `advance()` exists.

        `model_copy(update=...)` would have accepted the over-budget value silently, so a node using
        it would fail open on the budget, on `extra="forbid"` and on the credential scan.
        """
        state = make_state(step_count=12, max_steps=12)
        assert state.model_copy(update={"step_count": 13}).step_count == 13
        with pytest.raises(ValidationError):
            advance(state, step_count=13)


def test_agent_modules_never_bypass_validation_with_model_copy() -> None:
    """Guard the seam at the source, with an explicit allowlist rather than a zero-tolerance grep.

    `model_copy(update=...)` skips every validator, so in a *graph node* it would silently disable
    the budget check, `extra="forbid"` and the credential scan. Every remaining site is listed here
    with its reason; any **new** occurrence - in `graph.py`, in `routing.py`, in a node module, or
    anywhere else under `app/` - fails this test, and so does an entry that is no longer needed.

    The pattern requires a leading dot so the counter-example quoted in `advance()`'s docstring is
    not matched.
    """
    allowed = {
        # Dev-only live harness for T031: builds intermediate states for the playground.
        "dev_t031.py",
        # Row columns are copied onto the payload on read - the row is the fresher fact, and this is
        # the single place that keeps the two from disagreeing.
        "checkpoint.py",
    }
    pattern = re.compile(r"\.model_copy\(")
    found = {
        path.name
        for path in AGENT_DIR.parent.rglob("*.py")
        if pattern.search(path.read_text(encoding="utf-8"))
    }
    assert not found - allowed, f"new unvalidated state copy: {found - allowed}"
    assert not allowed - found, f"allowlist is stale, remove: {allowed - found}"


class TestBudget:
    def test_spent_when_step_count_reaches_max_steps(self) -> None:
        assert budget_exhausted(make_state(step_count=12, max_steps=12)) is True
        assert budget_exhausted(make_state(step_count=11, max_steps=12)) is False

    def test_budget_exhaustion_is_a_safe_stop_not_a_failure(self) -> None:
        state = make_state(step_count=12, max_steps=12)
        assert route_after_understand(state) is Node.SAFE_STOP
        assert safe_stop_reason_for(state) is SafeStopReason.BUDGET_EXHAUSTED


class TestRouteAfterUnderstand:
    def test_running_state_goes_to_order_resolution(self) -> None:
        assert route_after_understand(make_state()) is Node.RESOLVE_ORDER

    @pytest.mark.parametrize("intent", ["UNKNOWN", None])
    def test_unrecognised_intent_asks_the_user_instead_of_guessing(
        self, intent: str | None
    ) -> None:
        """With no goal, no capability is obviously the right one - so we ask, not act."""
        assert route_after_understand(make_state(intent=intent)) is Node.WAITING_USER

    def test_terminal_state_goes_straight_to_finalize(self) -> None:
        state = make_state(status=RunStatus.SAFE_STOP)
        assert route_after_understand(state) is Node.FINALIZE


class TestRouteAfterResolveOrder:
    def test_resolved_order_continues_to_evidence(self) -> None:
        state = make_state(resolved_order_id="order-001")
        assert route_after_resolve_order(state) is Node.DECIDE_EVIDENCE

    def test_several_matching_orders_asks_the_user_instead_of_ranking_them(self) -> None:
        state = make_state(candidate_order_ids=["order-001", "order-002"])
        decision = Decision(resolution_attempted=True)
        assert route_after_resolve_order(state, decision) is Node.WAITING_USER

    def test_one_unconfirmed_clue_refuses_rather_than_guessing(self) -> None:
        state = make_state(candidate_order_ids=["order-001"])
        decision = Decision(resolution_attempted=True)
        assert route_after_resolve_order(state, decision) is Node.SAFE_STOP
        assert safe_stop_reason_for(state, decision) is SafeStopReason.ORDER_UNRESOLVED

    def test_nothing_to_ask_about_still_refuses(self) -> None:
        state = make_state()
        decision = Decision(resolution_attempted=True)
        assert route_after_resolve_order(state, decision) is Node.SAFE_STOP
        assert safe_stop_reason_for(state, decision) is SafeStopReason.ORDER_UNRESOLVED

    def test_unresolved_rule_does_not_misfire_before_resolution_runs(self) -> None:
        """The regression this test exists for: at the understand edge nothing is resolved yet."""
        state = make_state()
        assert route_after_understand(state) is Node.RESOLVE_ORDER
        assert safe_stop_reason_for(state) is None


def _tool_guard(status: EvidenceGuardStatus) -> EvidenceGuardDecision:
    """A guard decision about one evidence read, allowed or denied."""
    return EvidenceGuardDecision(
        status=status,
        action=EvidenceAction.CALL_TOOL,
        tool="get_logistics",
        reason_code="SAFE_EVIDENCE_READ_ALLOWED",
    )


class TestRouteAfterDecision:
    def test_allowed_tool_call_executes_the_evidence_read(self) -> None:
        decision = Decision(guard=_tool_guard(EvidenceGuardStatus.ALLOWED))
        assert route_after_decision(make_state(), decision) is Node.EXECUTE_EVIDENCE

    def test_denied_proposal_ends_collection_but_not_the_run(self) -> None:
        """Java is the eligibility authority; less evidence is its call to make, not ours."""
        decision = Decision(guard=_tool_guard(EvidenceGuardStatus.DENIED))
        assert route_after_decision(make_state(), decision) is Node.CHECK_ELIGIBILITY

    def test_ready_for_eligibility_hands_off(self) -> None:
        decision = Decision(
            guard=EvidenceGuardDecision(
                status=EvidenceGuardStatus.ALLOWED,
                action=EvidenceAction.READY_FOR_ELIGIBILITY,
                reason_code="READY_FOR_DETERMINISTIC_ELIGIBILITY",
            )
        )
        assert route_after_decision(make_state(), decision) is Node.CHECK_ELIGIBILITY

    def test_a_read_that_retrying_cannot_fix_hands_off_instead_of_failing(self) -> None:
        """One missing piece of evidence is not an outage: the run still reaches Java."""
        decision = Decision(
            guard=_tool_guard(EvidenceGuardStatus.ALLOWED),
            evidence_path_closed=True,
        )
        assert route_after_decision(make_state(), decision) is Node.CHECK_ELIGIBILITY

    def test_missing_proposal_refuses_instead_of_inventing_a_step(self) -> None:
        assert route_after_decision(make_state(), None) is Node.SAFE_STOP
        assert route_after_decision(make_state(), Decision()) is Node.SAFE_STOP

    def test_node_declared_reason_is_surfaced_verbatim(self) -> None:
        decision = Decision(safe_stop_reason=SafeStopReason.WRITE_FINGERPRINT_DRIFT)
        assert route_after_decision(make_state(), decision) is Node.SAFE_STOP
        assert (
            safe_stop_reason_for(make_state(), decision) is SafeStopReason.WRITE_FINGERPRINT_DRIFT
        )


class TestRouteAfterExecute:
    """One retry mechanism: a transient failure re-runs the read it already authorized."""

    def test_a_settled_attempt_goes_back_to_deliberation(self) -> None:
        decision = Decision(guard=_tool_guard(EvidenceGuardStatus.ALLOWED))
        assert route_after_execute(make_state(), decision) is Node.DECIDE_EVIDENCE

    def test_a_transient_failure_retries_the_same_authorized_read(self) -> None:
        decision = Decision(
            guard=_tool_guard(EvidenceGuardStatus.ALLOWED), retry_current_stage=True
        )
        assert route_after_execute(make_state(), decision) is Node.EXECUTE_EVIDENCE

    def test_budget_exhaustion_wins_over_a_retry_request(self) -> None:
        state = make_state(step_count=12, max_steps=12)
        decision = Decision(retry_current_stage=True)
        assert route_after_execute(state, decision) is Node.SAFE_STOP


class TestEligibilityHandoffToken:
    """The handoff token is produced by the layer that owns "where next", and by no other."""

    def test_the_model_having_enough_is_recorded_as_its_own_reason(self) -> None:
        decision = Decision(
            guard=EvidenceGuardDecision(
                status=EvidenceGuardStatus.ALLOWED,
                action=EvidenceAction.READY_FOR_ELIGIBILITY,
                reason_code="READY_FOR_DETERMINISTIC_ELIGIBILITY",
            )
        )
        assert handoff_reason_for(decision) is HandoffReason.MODEL_SAID_ENOUGH

    def test_a_denied_proposal_is_recorded_as_its_own_reason(self) -> None:
        decision = Decision(guard=_tool_guard(EvidenceGuardStatus.DENIED))
        assert handoff_reason_for(decision) is HandoffReason.EVIDENCE_PROPOSAL_DENIED

    def test_a_closed_path_outranks_the_proposal_that_was_denied_earlier(self) -> None:
        decision = Decision(
            guard=_tool_guard(EvidenceGuardStatus.ALLOWED), evidence_path_closed=True
        )
        assert handoff_reason_for(decision) is HandoffReason.EVIDENCE_PATH_CLOSED

    def test_the_token_satisfies_the_eligibility_precondition_and_carries_the_provenance(
        self,
    ) -> None:
        """`check_eligibility` requires ALLOWED + READY_FOR_ELIGIBILITY + no tool name."""
        token = eligibility_handoff(Decision(evidence_path_closed=True))
        assert token.status is EvidenceGuardStatus.ALLOWED
        assert token.action is EvidenceAction.READY_FOR_ELIGIBILITY
        assert token.tool is None
        assert token.reason_code == HandoffReason.EVIDENCE_PATH_CLOSED.value


class TestRouteAfterEligibility:
    def test_the_refund_only_action_reaches_the_refund_write_node(self) -> None:
        state = make_state(eligibility=make_eligibility(allowed_action="REFUND_ONLY"))
        assert route_after_eligibility(state) is Node.REFUND_WRITE

    @pytest.mark.parametrize("action", ["RETURN", "RETURN_REFUND"])
    def test_return_actions_reach_the_return_write_node(self, action: str) -> None:
        """T041: the US2 split, stated as routing rather than as prose.

        ``RETURN_REFUND`` used to reach the *refund* write node and be refused by Java (a delivered
        order is never granted a direct refund). The two halves of "return and refund" are separate,
        separately authorised writes now: the return goes here, and moving money needs its own
        authorisation. This assertion is the executable form of that change.
        """
        state = make_state(eligibility=make_eligibility(allowed_action=action))
        assert route_after_eligibility(state) is Node.RETURN_WRITE

    def test_a_retry_request_re_enters_eligibility_instead_of_finishing(self) -> None:
        """Without this the run would finish as COMPLETED on "Java could not answer"."""
        state = make_state()
        decision = Decision(retry_current_stage=True)
        assert route_after_eligibility(state, decision) is Node.CHECK_ELIGIBILITY

    def test_definitive_denial_finishes_without_writing(self) -> None:
        state = make_state(eligibility=make_eligibility(eligible=False, allowed_action="DENY"))
        assert route_after_eligibility(state) is Node.FINALIZE

    def test_manual_review_requires_explicit_safe_handoff_node(self) -> None:
        state = make_state(eligibility=make_eligibility(eligible=False, allowed_action="MANUAL_REVIEW"))
        assert route_after_eligibility(state) is Node.ESCALATE_OR_SAFE_STOP
        terminal = terminal_decision_for(state)
        assert terminal.status is RunStatus.SAFE_STOP
        assert terminal.reason is SafeStopReason.MANUAL_REVIEW_REQUIRED

    def test_unknown_java_action_refuses_instead_of_coercing_it(self) -> None:
        state = make_state(eligibility=make_eligibility(allowed_action="PARTIAL_REFUND"))
        assert route_after_eligibility(state) is Node.SAFE_STOP
        assert safe_stop_reason_for(state) is SafeStopReason.ELIGIBILITY_UNKNOWN_ACTION

    def test_eligible_with_a_non_write_action_is_treated_as_a_corrupt_decision(self) -> None:
        state = make_state(eligibility=make_eligibility(allowed_action="MANUAL_REVIEW"))
        assert route_after_eligibility(state) is Node.SAFE_STOP
        assert safe_stop_reason_for(state) is SafeStopReason.ELIGIBILITY_INCONSISTENT

    def test_approval_required_routes_to_the_hitl_request_node(self) -> None:
        state = make_state(eligibility=make_eligibility(approval_required=True))
        assert route_after_eligibility(state) is Node.REQUEST_APPROVAL
        assert safe_stop_reason_for(state) is None

    def test_an_unbounded_refund_amount_is_not_the_agents_decision(self) -> None:
        state = make_state(eligibility=make_eligibility(max_refund_amount=None))
        assert route_after_eligibility(state) is Node.SAFE_STOP
        assert safe_stop_reason_for(state) is SafeStopReason.ELIGIBILITY_AMOUNT_UNBOUNDED

    def test_a_pure_return_without_an_amount_is_not_an_unbounded_write(self) -> None:
        """A pure return carries no amount by contract, so "no amount" must not read as a gap.

        Getting this wrong would refuse every legitimate return with AMOUNT_UNBOUNDED -- a money
        rule applied to an action that never moves money.
        """
        state = make_state(
            eligibility=make_eligibility(allowed_action="RETURN", max_refund_amount=None)
        )
        assert route_after_eligibility(state) is Node.RETURN_WRITE
        assert safe_stop_reason_for(state) is None


class TestT054VerificationBudget:
    """Never spend the final step writing money when verification needs another step."""

    def test_refund_must_have_two_steps_left(self) -> None:
        state = make_state(
            step_count=11,
            max_steps=12,
            eligibility=make_eligibility(),
        )
        assert route_after_eligibility(state) is Node.SAFE_STOP
        assert safe_stop_reason_for(state) is SafeStopReason.BUDGET_EXHAUSTED

    def test_refund_and_verification_fit_exactly(self) -> None:
        state = make_state(
            step_count=10,
            max_steps=12,
            eligibility=make_eligibility(),
        )
        assert route_after_eligibility(state) is Node.REFUND_WRITE

    def test_approval_creation_is_not_rejected_as_a_refund_write(self) -> None:
        state = make_state(
            step_count=11,
            max_steps=12,
            eligibility=make_eligibility(approval_required=True),
        )
        assert route_after_eligibility(state) is Node.REQUEST_APPROVAL

    def test_approved_resume_must_reserve_verification_step(self) -> None:
        state = make_state(
            step_count=11,
            max_steps=12,
            resolved_order_id="order-001",
            eligibility=make_eligibility(
                max_refund_amount=Decimal("399.00"), approval_required=True
            ),
        )
        state = advance(
            state,
            approval={
                "approval_request_id": "approval-001",
                "status": "APPROVED",
                "binding_verified": True,
                "run_id": state.run_id,
                "order_id": "order-001",
                "action_type": "REFUND_ONLY",
                "amount": Decimal("399.00"),
            },
        )
        assert route_after_eligibility(state) is Node.SAFE_STOP
        assert safe_stop_reason_for(state) is SafeStopReason.BUDGET_EXHAUSTED

    def test_write_that_already_happened_can_still_route_to_verify(self) -> None:
        state = make_state(
            step_count=11,
            max_steps=12,
            eligibility=make_eligibility(),
            write={"status": WriteStatus.SUCCEEDED},
            write_intent=make_intent(),
        )
        assert route_after_write(state) is Node.VERIFY


class TestRouteAfterWrite:
    def test_a_write_that_was_never_attempted_finishes_without_verification(self) -> None:
        state = make_state(write={"status": WriteStatus.NOT_ATTEMPTED})
        assert route_after_write(state) is Node.FINALIZE

    def test_an_outcome_without_a_durable_intent_has_no_key_to_verify_with(self) -> None:
        """T022: no intent means nothing was ever sent, so there is nothing to read back."""
        state = make_state(write={"status": WriteStatus.FAILED, "error_code": "INTERNAL_ERROR"})
        assert route_after_write(state) is Node.FINALIZE

    @pytest.mark.parametrize("status", [WriteStatus.SUCCEEDED, WriteStatus.UNKNOWN])
    def test_any_attempted_write_is_verified_against_java(self, status: WriteStatus) -> None:
        state = make_state(write={"status": status}, write_intent=make_intent())
        assert route_after_write(state) is Node.VERIFY


class TestTerminalDecision:
    def test_verified_success_and_verified_failure_are_both_completions(self) -> None:
        for status in (VerificationStatus.VERIFIED_SUCCESS, VerificationStatus.VERIFIED_FAILURE):
            decision = terminal_decision_for(make_state(verification={"status": status}))
            assert decision.status is RunStatus.COMPLETED
            assert decision.reason is None

    def test_unconfirmable_outcome_safe_stops_and_keeps_its_trace(self) -> None:
        state = make_state(verification={"status": VerificationStatus.UNKNOWN})
        decision = terminal_decision_for(state)
        assert decision.status is RunStatus.SAFE_STOP
        assert decision.reason is SafeStopReason.VERIFICATION_UNKNOWN

    def test_unknown_write_without_verification_still_cannot_claim_success(self) -> None:
        state = make_state(write={"status": WriteStatus.UNKNOWN})
        decision = terminal_decision_for(state)
        assert decision.status is RunStatus.SAFE_STOP
        assert decision.reason is SafeStopReason.VERIFICATION_UNKNOWN

    def test_safe_stop_without_a_reason_is_impossible_to_construct(self) -> None:
        with pytest.raises(ValidationError):
            TerminalDecision(status=RunStatus.SAFE_STOP)

    def test_a_clean_end_cannot_carry_a_safety_reason(self) -> None:
        with pytest.raises(ValidationError):
            TerminalDecision(status=RunStatus.COMPLETED, reason=SafeStopReason.BUDGET_EXHAUSTED)


class TestLangGraphIntegration:
    """Pin the routing vocabulary against the installed langgraph.

    `Node` is a `StrEnum`, and the conditional-edge path map is keyed by it. That is only safe if
    the installed langgraph treats the members as the strings they subclass - so the assumption is
    checked here rather than discovered in the graph on the day the framework changes.
    """

    def test_strenum_node_names_and_conditional_edges_are_dispatched(self) -> None:
        def first(state: Walk) -> dict[str, Any]:
            return {"trail": state["trail"] + "|understand"}

        def second(state: Walk) -> dict[str, Any]:
            return {"trail": state["trail"] + "|finalize"}

        def pick_next(state: Walk) -> Node:
            return Node.FINALIZE

        graph = StateGraph(Walk)
        graph.add_node(Node.UNDERSTAND, first)
        graph.add_node(Node.FINALIZE, second)
        graph.add_edge(START, Node.UNDERSTAND)
        graph.add_conditional_edges(Node.UNDERSTAND, pick_next, {Node.FINALIZE: Node.FINALIZE})
        graph.add_edge(Node.FINALIZE, END)

        assert graph.compile().invoke({"trail": "start"})["trail"] == "start|understand|finalize"
