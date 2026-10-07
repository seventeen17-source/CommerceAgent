"""Deterministic candidate filtering by a product clue (T044).

Why this is a separate, dependency-free module: the decision "which orders are candidates" must be a
*deterministic function* of (clue, order facts). The model extracts the clue; it never chooses the
object. Keeping that function away from the graph makes it testable on its own, and makes the one
thing reviewers ask -- "why were these the candidates?" -- answerable by reading one file.

The clue is untrusted input (it comes from a language model), so every rule here is conservative:
an unusable clue is treated as *no* clue, and a clue that matches nothing never widens the candidate
set -- it reports that it matched nothing, and the question gets broader instead.
"""

from __future__ import annotations

import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass

from app.clients.models import OrderSummary

#: How many candidates a clarification may show. A bound, not a safety property: the safety property
#: is that nothing is written before the human answers, whoever they end up choosing.
DEFAULT_CANDIDATE_CAP = 5

#: Clues that carry no information about *which* order is meant. Treated as "no clue" rather than as
#: a clue that happens to match many orders -- otherwise a request saying only "把那个东西退了"
#: would look like a successful filter.
_GENERIC_CLUES = ("", "东西", "商品", "物品", "订单", "那个", "这个", "买的东西")


def normalize(text: str) -> str:
    """Fold away differences that are not meaning: case, width, spaces, punctuation.

    ``NFKC`` is what turns full-width characters into their half-width forms, so a clue typed in a
    Chinese IME matches a product summary stored in ASCII, and vice versa.
    """
    folded = unicodedata.normalize("NFKC", text).casefold()
    return "".join(
        character
        for character in folded
        if not character.isspace() and not unicodedata.category(character).startswith("P")
    )


_GENERIC_NORMALIZED = frozenset(normalize(word) for word in _GENERIC_CLUES)


def is_informative_clue(hint: str | None) -> bool:
    """Whether the clue says anything about which order is meant."""
    if hint is None:
        return False
    normalized = normalize(hint)
    return bool(normalized) and normalized not in _GENERIC_NORMALIZED


def matches(hint: str, product_summary: str | None) -> bool:
    """Whether one order's product summary is described by the clue.

    Substring containment, after normalization: "耳机" is contained in "无线蓝牙耳机 Pro".
    Synonyms are the model's job when it produces the clue; this function stays a containment
    test on purpose, because a rule a reviewer cannot restate in one sentence is not auditable.
    """
    needle = normalize(hint)
    haystack = normalize(product_summary or "")
    if not needle or not haystack:
        return False
    return needle in haystack


@dataclass(frozen=True)
class CandidateSelection:
    """The candidates to ask about, and whether the clue turned out to match nothing."""

    candidate_order_ids: tuple[str, ...]
    #: ``True`` only when an *informative* clue matched no order at all. That case is why the caller
    #: must ask a broader question instead of pretending the filter worked.
    clue_matched_nothing: bool


def _newest_first(orders: Sequence[OrderSummary]) -> list[OrderSummary]:
    return sorted(orders, key=lambda order: order.created_at, reverse=True)


def select_candidates(
    hint: str | None,
    orders: Sequence[OrderSummary],
    *,
    cap: int = DEFAULT_CANDIDATE_CAP,
) -> CandidateSelection:
    """Filter, order and cap the orders a clarification may offer.

    Ordering is most-recent-first because "上次买的" is the common way people refer to an order, and
    the cap is applied *after* filtering, so an informative clue can never be crowded out by orders
    that do not match it.
    """
    if not is_informative_clue(hint):
        return CandidateSelection(
            candidate_order_ids=tuple(order.order_id for order in _newest_first(orders)[:cap]),
            clue_matched_nothing=False,
        )

    matched = [
        order for order in _newest_first(orders) if matches(hint or "", order.product_summary)
    ]
    if not matched:
        # Deliberately *not* falling back to every order: that would widen the set precisely when
        # the system knows least about what the customer meant.
        return CandidateSelection(
            candidate_order_ids=tuple(order.order_id for order in _newest_first(orders)[:cap]),
            clue_matched_nothing=True,
        )

    return CandidateSelection(
        candidate_order_ids=tuple(order.order_id for order in matched[:cap]),
        clue_matched_nothing=False,
    )
