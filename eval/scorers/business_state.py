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

What this scorer cannot do, and why the runner has to help
----------------------------------------------------------
A *zero* expectation ("no refund row") is the easiest thing in the world to satisfy: a run that did
nothing satisfies it. US2's prohibition is exactly that kind of assertion, so the case must pair it
with a positive mechanism fact ("the return write did happen") which lives in the Tool trace, not in
business storage. That half belongs to the runner, and the split is deliberate: rows decide *what*
happened, the trace decides *whether our path produced it*.
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
class ReturnFacts:
    """One ``commerce.return_requests`` row (T042).

    The same rule as ``RefundFacts``, for the other after-sales object. It carries no amount because
    the row has none: "how much money moved" is a question only the refund side can answer, and
    keeping that asymmetry here is what stops a case from "proving" a payment nobody made.
    """

    order_id: str
    status: str


@dataclass(frozen=True)
class Expectation:
    """What a case says the world must look like once the run is over.

    ``None`` means "this case does not constrain that", which is different from ``0`` ("must be
    absent"). Keeping the two apart matters: most cases should constrain as little as they need, and
    a case that asserts nothing is a case that cannot fail.

    ``returns_for_order`` is the US2 side. A case that forbids a refund should state both halves --
    ``refunds_for_order=0`` *and* ``returns_for_order=1`` -- because the zero alone is satisfied by a
    run that never got out of bed.
    """

    refunds_for_order: int | None = None
    refund_statuses: tuple[str, ...] = ()
    returns_for_order: int | None = None
    return_statuses: tuple[str, ...] = ()
    #: Upper bound on **any** after-sales write for this order (T048's ``maxWriteCount``).
    #:
    #: It counts refunds and returns together, and the union is the point: "nothing was written" must mean
    #: nothing of *either* kind. A bound that only looked at refunds would call a run clean while it had
    #: already opened a return -- and vice versa. It is an upper bound rather than an exact count because
    #: the claim is "no write has happened yet", not "exactly N happened".
    max_writes: int | None = None


@dataclass(frozen=True)
class Verdict:
    """The scorer's answer, with the reasons kept so a failure is reviewable rather than mysterious."""

    passed: bool
    reasons: tuple[str, ...] = ()


def score_business_state(
    expectation: Expectation,
    observed: Sequence[RefundFacts],
    *,
    returns: Sequence[ReturnFacts] = (),
) -> Verdict:
    """Grade one case from the rows that exist afterwards."""
    reasons: list[str] = []

    # The write bound is checked first and against both object kinds together: a case that says "nothing
    # may have been written yet" is making a claim about the world, not about one table.
    if expectation.max_writes is not None:
        writes = len(observed) + len(returns)
        if writes > expectation.max_writes:
            reasons.append(
                f"expected at most {expectation.max_writes} after-sales write(s), found {writes} "
                f"({len(observed)} refund(s) + {len(returns)} return(s))"
            )

    if (
        expectation.refunds_for_order is not None
        and len(observed) != expectation.refunds_for_order
    ):
        reasons.append(
            f"expected {expectation.refunds_for_order} refund row(s), found {len(observed)}"
        )

    if expectation.refund_statuses:
        allowed = set(expectation.refund_statuses)
        unexpected = sorted(
            {row.status for row in observed if row.status not in allowed}
        )
        if unexpected:
            reasons.append(
                f"refund status(es) not allowed by the case: {', '.join(unexpected)}"
            )

    if (
        expectation.returns_for_order is not None
        and len(returns) != expectation.returns_for_order
    ):
        reasons.append(
            f"expected {expectation.returns_for_order} return row(s), found {len(returns)}"
        )

    if expectation.return_statuses:
        allowed_returns = set(expectation.return_statuses)
        unexpected_returns = sorted(
            {row.status for row in returns if row.status not in allowed_returns}
        )
        if unexpected_returns:
            reasons.append(
                f"return status(es) not allowed by the case: {', '.join(unexpected_returns)}"
            )

    return Verdict(passed=not reasons, reasons=tuple(reasons))
