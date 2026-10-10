"""T056 unit tests for exact approval authority-state scoring."""

from __future__ import annotations

import sys
from pathlib import Path

_EVAL_DIR = Path(__file__).resolve().parent.parent
if str(_EVAL_DIR) not in sys.path:
    sys.path.insert(0, str(_EVAL_DIR))

from scorers.business_state import (
    ApprovalExpectation,
    ApprovalFacts,
    score_approval_state,
)


def _approval(status: str, *, approval_id: str = "approval-1") -> ApprovalFacts:
    return ApprovalFacts(
        approval_id=approval_id,
        run_id="00000000-0000-0000-0000-000000000001",
        order_id="order-004",
        status=status,
    )


def test_one_pending_approval_passes() -> None:
    verdict = score_approval_state(
        ApprovalExpectation(count=1, status_counts=(("PENDING", 1),)),
        [_approval("PENDING")],
    )

    assert verdict.passed, verdict.reasons


def test_wrong_approval_count_fails() -> None:
    verdict = score_approval_state(
        ApprovalExpectation(count=1, status_counts=(("PENDING", 1),)),
        [],
    )

    assert not verdict.passed
    assert any("expected 1 approval row(s), found 0" in reason for reason in verdict.reasons)


def test_status_counts_are_exact_not_an_allowlist() -> None:
    verdict = score_approval_state(
        ApprovalExpectation(
            count=2,
            status_counts=(("PENDING", 1), ("APPROVED", 1)),
        ),
        [
            _approval("APPROVED", approval_id="approval-1"),
            _approval("APPROVED", approval_id="approval-2"),
        ],
    )

    assert not verdict.passed
    assert any("approval status counts differ" in reason for reason in verdict.reasons)
