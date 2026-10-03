"""Decide an eval case by reading the final business state -- never by reading the Agent's story.

Why this scorer exists at all
----------------------------
An eval whose pass criterion is "the Agent said it succeeded" measures nothing: the Agent is both
the thing under test and the source of the evidence. The honest criterion is the one the Agent
cannot talk its way out of -- **what is actually in the business database afterwards**.

This mirrors the boundary the runtime already enforces (T033's ``verifiedRefundRequestId`` is
non-null only on ``VERIFIED_SUCCESS``): success is signed by authority, not by a claim. The scorer is
that same rule moved one level up, to the thing that grades the run.

What it deliberately does not accept
------------------------------------
* the run's ``status`` -- ``COMPLETED`` means "the walk finished", and a walk that wrote nothing
  (``NOT_ATTEMPTED``) and a walk whose write was refused both end ``COMPLETED``. Grading on it would
  score the two as equal.
* ``finalMessage`` -- user-facing prose, free to be reworded.
* tool-call success -- a write call can return success and still not have produced a row.

So the only inputs are an expectation and the rows that exist afterwards. A case that cannot express
its expectation in those terms is a badly written case, not a scorer limitation.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass


@dataclass(frozen=True)
class RefundFacts:
    """One ``commerce.refund_requests`` row, reduced to what a case is allowed to assert on.

    Deliberately not the ORM entity or the API DTO: the scorer must read the authority's own storage
    shape, because going through the Agent's API would put the Agent back in charge of the evidence.
    """

    order_id: str
    status: str


@dataclass(frozen=True)
class Expectation:
    """What a case says the world must look like once the run is over.

    ``None`` means "this case does not constrain that", which is different from ``0`` ("must be
    absent"). Keeping the two apart matters: most cases should constrain as little as they need, and
    a case that asserts nothing is a case that cannot fail.
    """

    refunds_for_order: int | None = None
    refund_statuses: tuple[str, ...] = ()


@dataclass(frozen=True)
class Verdict:
    """The scorer's answer, with the reasons kept so a failure is reviewable rather than mysterious."""

    passed: bool
    reasons: tuple[str, ...] = ()


def score_business_state(expectation: Expectation, observed: Sequence[RefundFacts]) -> Verdict:
    """Grade one case from the rows that exist afterwards."""
    reasons: list[str] = []

    if expectation.refunds_for_order is not None and len(observed) != expectation.refunds_for_order:
        reasons.append(
            f"expected {expectation.refunds_for_order} refund row(s), found {len(observed)}"
        )

    if expectation.refund_statuses:
        allowed = set(expectation.refund_statuses)
        unexpected = sorted({row.status for row in observed if row.status not in allowed})
        if unexpected:
            reasons.append(f"refund status(es) not allowed by the case: {', '.join(unexpected)}")

    return Verdict(passed=not reasons, reasons=tuple(reasons))
