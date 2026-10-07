"""T048 unit tests: the "nothing may have been written yet" expectation.

Why this needs its own vocabulary
---------------------------------
US3's whole promise is that a clarification happens *before* any after-sales write. Expressing that as
"refunds == 0" is not enough, for two separate reasons, and both are pinned below:

* it ignores the other object kind -- a run that opened a **return** would pass a refund-only zero;
* a zero is satisfied by a run that never got out of bed, which is why the runner pairs it with a
  mechanism assertion (the Tool trace). What this scorer can do is make the *result* half honest.
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


def test_no_write_at_all_satisfies_the_bound() -> None:
    verdict = score_business_state(Expectation(max_writes=0), [], returns=[])

    assert verdict.passed, verdict.reasons


def test_a_return_row_alone_breaks_the_zero_bound() -> None:
    """The case the refund-only version of this assertion would have missed."""
    verdict = score_business_state(
        Expectation(max_writes=0),
        [],
        returns=[ReturnFacts(order_id=_ORDER, status="CREATED")],
    )

    assert not verdict.passed
    assert any(
        "at most 0 after-sales write(s), found 1" in reason
        for reason in verdict.reasons
    )


def test_a_refund_row_alone_breaks_the_zero_bound() -> None:
    verdict = score_business_state(
        Expectation(max_writes=0),
        [RefundFacts(order_id=_ORDER, status="CREATED")],
        returns=[],
    )

    assert not verdict.passed
    assert any("1 refund(s) + 0 return(s)" in reason for reason in verdict.reasons)


def test_the_bound_is_an_upper_bound_and_counts_both_kinds_together() -> None:
    verdict = score_business_state(
        Expectation(max_writes=1),
        [RefundFacts(order_id=_ORDER, status="CREATED")],
        returns=[ReturnFacts(order_id=_ORDER, status="CREATED")],
    )

    assert not verdict.passed
    assert any("found 2" in reason for reason in verdict.reasons)


def test_an_absent_bound_constrains_nothing() -> None:
    """``None`` is "this case does not say", and it must stay distinguishable from ``0``."""
    verdict = score_business_state(Expectation(), [], returns=[])

    assert verdict.passed
