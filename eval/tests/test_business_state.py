"""Unit tests for the business-state scorer: the criterion must not be reachable by Agent prose.

The tests are written as the three ways a grader can be fooled -- a missing row that the Agent
claimed, an extra row nobody mentioned, and a status the case never allowed -- plus the one way a
case can be vacuous (asserting nothing).
"""

from __future__ import annotations

import sys
from pathlib import Path

# The eval tree is not a Python package yet (no pyproject at the repo root), so the scorer's parent
# directory is put on the path explicitly. Making `eval/` a real package is a follow-up, not part of
# this seed: the alternative was putting the scorer under agent-service, which is where the agent
# lives and therefore the wrong side of the boundary this scorer exists to defend.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scorers.business_state import Expectation, RefundFacts, score_business_state


def row(order_id: str, status: str) -> RefundFacts:
    return RefundFacts(order_id=order_id, status=status)


def test_the_expected_row_passes() -> None:
    verdict = score_business_state(
        Expectation(refunds_for_order=1, refund_statuses=("PENDING", "SUCCEEDED")),
        [row("order-001", "PENDING")],
    )

    assert verdict.passed
    assert verdict.reasons == ()


def test_a_missing_row_fails_even_though_a_run_can_report_success() -> None:
    """The whole point: nothing in the database means nothing happened, whatever was reported."""
    verdict = score_business_state(Expectation(refunds_for_order=1), [])

    assert not verdict.passed
    assert "expected 1 refund row(s), found 0" in verdict.reasons


def test_an_extra_row_fails() -> None:
    """A duplicate write is exactly the failure a count catches and a boolean cannot."""
    verdict = score_business_state(
        Expectation(refunds_for_order=1),
        [row("order-001", "PENDING"), row("order-001", "PENDING")],
    )

    assert not verdict.passed
    assert "expected 1 refund row(s), found 2" in verdict.reasons


def test_a_status_the_case_never_allowed_fails() -> None:
    verdict = score_business_state(
        Expectation(refund_statuses=("PENDING",)),
        [row("order-001", "FAILED")],
    )

    assert not verdict.passed
    assert "refund status(es) not allowed by the case: FAILED" in verdict.reasons


def test_an_unconstrained_case_cannot_fail() -> None:
    """Kept as a test so the vacuous case is visible as a choice rather than an oversight."""
    verdict = score_business_state(Expectation(), [row("order-001", "FAILED")])

    assert verdict.passed
