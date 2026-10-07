"""The "waiting for the customer" half of the state machine (T045).

Why this is a module and not a few lines inside the API router: "stop and ask" is a *state*, and
a state that is described in three places drifts. The API needs the customer-facing question,
the runtime needs "may I park here?", and the resume path needs "may I wake this run up?" --
all three are questions about the same facts, so they get answered from the same place.

Nothing here reads or writes a database, and no statuses are redefined: the status vocabulary
itself stays in ``app/trace/checkpoint.py`` (one truth per fact). This module is a pure function
of facts the caller already holds, which makes the waiting rules testable without a server.

The two halves of the wait, and where each is enforced
------------------------------------------------------
This module owns the *decisions*; the boundary owns the *enforcement*::

    ask    : clarification_for(...)          <- decided here; published by the run view
    resume : ownership, then state, then CAS <- order fixed here; enforced by store + API

**The resume order is part of the contract, not a detail.** Ownership comes first because HTTP
status codes are an information channel: checking the state of a run the caller does not own would
let them tell "exists and finished" (409) from "exists and is waiting" (403) -- a status oracle for
somebody else's run. It is also the difference between fail-closed and fail-open: a transition must
never be reachable before authorization.

**The version check is a conditional write, not a check.** ``UPDATE ... WHERE status =
'WAITING_USER' AND version = ?`` fuses "still waiting" and "still the version I read" into one
atomic statement; a read-compare-then-write leaves a TOCTOU gap in which two wake-ups both pass the
comparison and the later one silently overwrites the earlier one.

**Enforcement stays where it already is, and this module must not grow a second copy of it.**
Ownership lives in the API's owner-scoped read; status *and* version live inside the store's single
transaction (``SELECT ... FOR UPDATE``, compare, then ``UPDATE ... WHERE version = %s`` requiring
exactly one row). ``/input``'s own docstring gives the reason: "two places deciding 'is this run
resumable' would be two answers, and the one in SQL is the one that holds under concurrency". An
earlier draft of this note said the remaining work was to wire these checks in here; that was wrong,
and it is recorded because acting on it would have created the duplicate decider the design forbids.
**This module declares the rule; the store is its only enforcer.**
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

#: The published vocabulary, mirrored by the API Literal and the contract enum. Plain strings rather
#: than an enum because they cross the API boundary as strings -- one representation, not two.
ClarificationKindName = Literal["INTENT_UNKNOWN", "ORDER_AMBIGUOUS", "ORDER_NO_MATCH"]

INTENT_UNKNOWN: ClarificationKindName = "INTENT_UNKNOWN"
ORDER_AMBIGUOUS: ClarificationKindName = "ORDER_AMBIGUOUS"
ORDER_NO_MATCH: ClarificationKindName = "ORDER_NO_MATCH"


@dataclass(frozen=True)
class Clarification:
    """What the customer has to supply before this run can continue."""

    kind: ClarificationKindName
    candidate_order_ids: tuple[str, ...] = ()


def _as_ids(candidate_order_ids: Sequence[object]) -> tuple[str, ...]:
    return tuple(str(order_id) for order_id in candidate_order_ids)


def clarification_for(
    *,
    waiting_for_user: bool,
    intent: str | None,
    clue_matched_nothing: bool,
    candidate_order_ids: Sequence[object] = (),
) -> Clarification | None:
    """The question to publish, derived only from facts -- or ``None`` when nothing explains it.

    ``None`` is a real answer, not a failure: a customer-facing prompt that might be wrong is
    worse than no prompt, so a wait with no known reason publishes nothing instead of a guess.
    """
    if not waiting_for_user:
        return None
    if intent is None or intent == "UNKNOWN":
        return Clarification(kind=INTENT_UNKNOWN)
    if clue_matched_nothing:
        # Checked before the candidate count on purpose: a clue that matched nothing can still fall
        # back to several candidates, and answering "several orders look plausible" would describe a
        # ranking question when the truth is that not one of them matched what the customer named.
        return Clarification(kind=ORDER_NO_MATCH, candidate_order_ids=_as_ids(candidate_order_ids))
    if len(candidate_order_ids) >= 2:
        return Clarification(kind=ORDER_AMBIGUOUS, candidate_order_ids=_as_ids(candidate_order_ids))
    return None
