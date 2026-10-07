"""T042 unit tests for the US2 expectation vocabulary -- no service required.

The scorer is the only part of the eval stack that can be graded without a running world, and it is
the part that decides pass/fail. These tests pin the two ways a US2 case could lie:

* a **missing return row** passing because the refund side was empty (the false pass US2 cares about);
* a **prohibited refund row** being ignored because only the positive half was checked.
"""

from __future__ import annotations

import sys
from pathlib import Path

_EVAL_DIR = Path(__file__).resolve().parent.parent
if str(_EVAL_DIR) not in sys.path:
    sys.path.insert(0, str(_EVAL_DIR))

from scorers.business_state import (
    Expectation,
    RefundFacts,
    ReturnFacts,
    score_business_state,
)

_ORDER = "order-001"


def _return(status: str = "CREATED") -> ReturnFacts:
    return ReturnFacts(order_id=_ORDER, status=status)


def _refund(status: str = "CREATED") -> RefundFacts:
    return RefundFacts(order_id=_ORDER, status=status)


def test_one_return_and_no_refund_passes() -> None:
    verdict = score_business_state(
        Expectation(
            returns_for_order=1, return_statuses=("CREATED",), refunds_for_order=0
        ),
        [],
        returns=[_return()],
    )

    assert verdict.passed, verdict.reasons


def test_a_missing_return_row_fails_even_when_the_refund_side_is_empty() -> None:
    """The exact false pass this vocabulary exists to prevent: nothing happened, so the zero held."""
    verdict = score_business_state(
        Expectation(returns_for_order=1, refunds_for_order=0),
        [],
        returns=[],
    )

    assert not verdict.passed
    assert any("1 return row(s)" in reason for reason in verdict.reasons)


def test_a_refund_row_fails_the_forbidden_half() -> None:
    verdict = score_business_state(
        Expectation(returns_for_order=1, refunds_for_order=0),
        [_refund()],
        returns=[_return()],
    )

    assert not verdict.passed
    assert any("0 refund row(s)" in reason for reason in verdict.reasons)


def test_an_unconstrained_expectation_constrains_nothing() -> None:
    """``None`` is "this case does not say", which is different from ``0`` ("must be absent").

    Worth pinning because the difference is load-bearing: a case that forbids nothing can be satisfied
    by any world, and a reader must be able to tell that apart from a case that forbids something.
    """
    verdict = score_business_state(Expectation(), [_refund()], returns=[_return()])

    assert verdict.passed


def test_return_status_vocabulary_is_checked_like_the_refund_one() -> None:
    verdict = score_business_state(
        Expectation(returns_for_order=1, return_statuses=("CREATED",)),
        [],
        returns=[_return(status="COMPLETED")],
    )

    assert not verdict.passed
    assert any("return status(es) not allowed" in reason for reason in verdict.reasons)
