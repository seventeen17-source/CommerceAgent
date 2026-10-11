"""T063-live: the US5 live-gate dataset and its scorer must not be able to pass vacuously.

Two things are checked here, and they are different risks:

1. **The scorer's arithmetic.** A ticket count, a status and a reason code are three separate
   claims; a scorer that let any one slide would grade a ticket that a human never sees.
2. **The dataset's shape.** The two US5 scenarios are defined by opposite ticket expectations (a
   dependency failure must produce *none*, a manual review exactly *one*). If a later edit relaxed
   either of them, both cases would still run and still report "pass" -- the quiet failure this
   repository has hit repeatedly.
"""

from __future__ import annotations

import sys
from pathlib import Path

import yaml

_EVAL_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_EVAL_DIR))

from scorers.business_state import (  # noqa: E402
    SupportTicketExpectation,
    SupportTicketFacts,
    score_support_ticket_state,
)

_DATASET = _EVAL_DIR / "datasets" / "dev" / "us5_live_gate.yaml"


def _ticket(
    status: str = "OPEN", reason_code: str = "MANUAL_REVIEW_REQUIRED"
) -> SupportTicketFacts:
    return SupportTicketFacts(
        ticket_id="ticket-1",
        run_id="run-1",
        order_id="order-001",
        status=status,
        reason_code=reason_code,
    )


def _cases() -> dict[str, dict[str, object]]:
    document = yaml.safe_load(_DATASET.read_text(encoding="utf-8"))
    return {str(case["scenarioId"]): case for case in document["cases"]}


def test_one_open_ticket_with_the_expected_reason_passes() -> None:
    verdict = score_support_ticket_state(
        SupportTicketExpectation(count=1, status="OPEN", reason_code="MANUAL_REVIEW_REQUIRED"),
        [_ticket()],
    )
    assert verdict.passed, verdict.reasons


def test_a_missing_ticket_fails_even_when_the_run_says_escalated() -> None:
    verdict = score_support_ticket_state(SupportTicketExpectation(count=1, status="OPEN"), [])
    assert not verdict.passed
    assert any("support ticket row" in reason for reason in verdict.reasons)


def test_a_closed_ticket_is_not_a_handoff() -> None:
    """The status is exact on purpose: a closed ticket reaches no human."""
    verdict = score_support_ticket_state(
        SupportTicketExpectation(count=1, status="OPEN"), [_ticket(status="CLOSED")]
    )
    assert not verdict.passed
    assert any("CLOSED" in reason for reason in verdict.reasons)


def test_a_different_reason_code_fails_even_with_the_right_count() -> None:
    """A ticket filed under some other reason is a different decision, not a formatting detail."""
    verdict = score_support_ticket_state(
        SupportTicketExpectation(count=1, reason_code="MANUAL_REVIEW_REQUIRED"),
        [_ticket(reason_code="SOMETHING_ELSE")],
    )
    assert not verdict.passed
    assert any("SOMETHING_ELSE" in reason for reason in verdict.reasons)


def test_zero_tickets_is_satisfied_only_by_zero_rows() -> None:
    assert score_support_ticket_state(SupportTicketExpectation(count=0), []).passed
    assert not score_support_ticket_state(SupportTicketExpectation(count=0), [_ticket()]).passed


def test_unconstrained_expectation_constrains_nothing() -> None:
    """``None`` means "this case says nothing", which is not the same as ``0``."""
    assert score_support_ticket_state(SupportTicketExpectation(), [_ticket()]).passed


def test_the_dataset_covers_the_two_spec_scenarios() -> None:
    cases = _cases()
    assert set(cases) == {
        "us5-live-dependency-unavailable",
        "us5-live-manual-review-escalated",
    }


def test_the_two_scenarios_expect_opposite_ticket_outcomes() -> None:
    """This is the assertion that makes the pair meaningful.

    A dependency failure that invented a ticket would be an unsafe decision (nobody triaged it), and
    a manual review that produced none would be a silent drop. Stating both halves here means a
    future edit cannot quietly make the two cases agree.
    """
    cases = _cases()
    dependency = cases["us5-live-dependency-unavailable"]["expect"]
    manual = cases["us5-live-manual-review-escalated"]["expect"]

    assert dependency["supportTicketCount"] == 0
    assert manual["supportTicketCount"] == 1
    assert manual["supportTicketStatus"] == "OPEN"

    # The audit half travels with the ticket half: an escalation that leaves no committed audit is
    # not accountable, and an audit without a ticket would be a claim about a row that does not exist.
    assert dependency["supportTicketAuditCount"] == 0
    assert manual["supportTicketAuditCount"] == 1

    # Both worlds must forbid the money movement, whatever else they say.
    for expect in (dependency, manual):
        assert expect["maxWriteCount"] == 0
        assert expect["refundsForOrder"] == 0
        assert expect["returnsForOrder"] == 0


def test_the_failure_case_states_a_safe_stop_reason_set() -> None:
    """``SAFE_STOP`` alone is not a behaviour: the recorded reason is what makes it reviewable.

    Two safe endings are legitimate for a dependency that keeps failing -- stop after two identical
    failures, or stop when the retry budget runs out -- so the case names both rather than grading an
    implementation detail. What it must not accept is *no* recorded reason: an unexplained stop is
    indistinguishable from a crash, and US5's whole claim is that this stop was a decision.
    """
    reasons = _cases()["us5-live-dependency-unavailable"]["expect"]["terminalReasonIn"]
    assert "REPEATED_NO_PROGRESS" in reasons
    assert "BUDGET_EXHAUSTED" in reasons


def test_every_case_names_the_mechanism_it_requires() -> None:
    """Rows alone cannot tell "nothing was written" from "nothing was ever attempted"."""
    for scenario_id, case in _cases().items():
        expect = case["expect"]
        assert expect.get("toolCallRequired"), f"{scenario_id} names no required Tool call"
        assert expect.get("toolCallForbidden"), f"{scenario_id} forbids no Tool call"


def test_the_failure_case_forbids_inventing_a_ticket() -> None:
    expect = _cases()["us5-live-dependency-unavailable"]["expect"]
    assert "create_support_ticket" in expect["toolCallForbidden"]
    assert "get_logistics" in expect["toolCallRequired"]


def test_both_cases_reset_the_same_writable_world() -> None:
    """Different failure routes, same physical world -- otherwise "no refund" proves nothing."""
    cases = _cases()
    dependency = cases["us5-live-dependency-unavailable"]
    manual = cases["us5-live-manual-review-escalated"]

    assert dependency["orderId"] == manual["orderId"]
    assert dependency["user"] == manual["user"]
    assert dependency["caseId"] != manual["caseId"]
