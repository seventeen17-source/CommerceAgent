"""T044 boundary cases for the deterministic product-clue filter.

The eight cases below are the ones the design record calls out; several of them exist because the
*obvious* implementation gets them wrong (widening the candidate set when a clue matches nothing,
treating a generic word as a clue, matching on an empty summary).
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.agent.product_matching import (
    DEFAULT_CANDIDATE_CAP,
    is_informative_clue,
    matches,
    normalize,
    select_candidates,
)
from app.clients.models import OrderSummary


def _order(order_id: str, product: str = "Synthetic item", day: int = 1) -> OrderSummary:
    return OrderSummary.model_validate(
        {
            "orderId": order_id,
            "productSummary": product,
            "status": "DELIVERED",
            "createdAt": datetime(2026, 9, day, tzinfo=UTC).isoformat(),
        }
    )


def test_a_clue_that_hits_one_order_narrows_to_it() -> None:
    orders = [_order("order-001", "无线蓝牙耳机 Pro"), _order("order-002", "运动水壶")]

    selection = select_candidates("耳机", orders)

    # One candidate is still a *candidate*: ownership is confirmed by the authority afterwards,
    # never inferred from the clue (T030's rule).
    assert selection.candidate_order_ids == ("order-001",)
    assert selection.clue_matched_nothing is False


def test_two_orders_with_the_same_product_both_stay_candidates() -> None:
    orders = [
        _order("order-001", "无线蓝牙耳机 Pro"),
        _order("order-003", "有线耳机 Basic", day=9),
    ]

    selection = select_candidates("耳机", orders)

    assert selection.candidate_order_ids == ("order-003", "order-001")
    assert selection.clue_matched_nothing is False


def test_a_clue_that_matches_nothing_is_reported_and_does_not_widen() -> None:
    orders = [_order("order-001", "运动水壶"), _order("order-002", "登山杖", day=9)]

    selection = select_candidates("耳机", orders)

    # The fallback list is the recent orders -- but the flag travels with it, so the caller asks a
    # broader question rather than pretending this was a successful filter.
    assert selection.candidate_order_ids == ("order-002", "order-001")
    assert selection.clue_matched_nothing is True


def test_no_clue_at_all_offers_the_recent_orders() -> None:
    orders = [_order("order-001", "运动水壶"), _order("order-002", "登山杖", day=9)]

    selection = select_candidates(None, orders)

    assert selection.candidate_order_ids == ("order-002", "order-001")
    assert selection.clue_matched_nothing is False


@pytest.mark.parametrize("hint", ["", "   ", "东西", "商品", "那个", "，，"])
def test_a_generic_clue_is_not_a_clue(hint: str) -> None:
    orders = [_order("order-001", "运动水壶")]

    selection = select_candidates(hint, orders)

    assert is_informative_clue(hint) is False
    assert selection.candidate_order_ids == ("order-001",)
    # Not "matched nothing": there was nothing to match, which is a different thing to say.
    assert selection.clue_matched_nothing is False


def test_an_empty_product_summary_is_never_a_match() -> None:
    orders = [_order("order-001", "")]

    selection = select_candidates("耳机", orders)

    assert matches("耳机", "") is False
    assert matches("耳机", None) is False
    assert selection.clue_matched_nothing is True


def test_the_cap_keeps_the_most_recent_and_filtering_runs_first() -> None:
    orders = [
        _order("order-001", "无线蓝牙耳机 Pro", day=1),
        _order("order-002", "耳机收纳盒", day=9),
        _order("order-003", "耳机线", day=5),
    ]

    selection = select_candidates("耳机", orders, cap=2)

    # Filtering before capping: the newest *matching* two, not "the newest two, filtered".
    assert selection.candidate_order_ids == ("order-002", "order-003")
    assert selection.clue_matched_nothing is False


def test_the_cap_is_applied_when_there_is_no_clue() -> None:
    orders = [_order(f"order-{day:03d}", day=day) for day in range(1, 9)]

    selection = select_candidates(None, orders)

    assert len(selection.candidate_order_ids) == DEFAULT_CANDIDATE_CAP
    assert selection.candidate_order_ids[0] == "order-008"


def test_normalization_folds_case_width_spaces_and_punctuation() -> None:
    orders = [_order("order-001", "Wireless Bluetooth Headphones")]

    # The full-width characters are the point of this test, hence the deliberate RUF001 suppression.
    fullwidth = "  Ｗｉｒｅｌｅｓｓ　Ｂｌｕｅｔｏｏｔｈ  "  # noqa: RUF001
    assert normalize(fullwidth) == "wirelessbluetooth"
    assert matches("Bluetooth Head-phones", "Wireless Bluetooth Headphones") is True
    # And the same clue with different casing still narrows to that order.
    assert select_candidates("BLUETOOTH", orders).candidate_order_ids == ("order-001",)


def test_equal_timestamps_keep_the_authoritys_own_order() -> None:
    """A tie is not a coin flip: the same input must always produce the same candidate list."""
    orders = [_order("order-001", "运动水壶", day=7), _order("order-002", "登山杖", day=7)]

    assert select_candidates(None, orders).candidate_order_ids == ("order-001", "order-002")
    assert select_candidates(None, list(reversed(orders))).candidate_order_ids == (
        "order-002",
        "order-001",
    )


def test_a_single_order_is_still_offered_as_the_only_candidate() -> None:
    orders = [_order("order-001", "运动水壶")]

    selection = select_candidates("耳机", orders)

    assert selection.candidate_order_ids == ("order-001",)
