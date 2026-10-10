"""Static contract tests for the T056 approval eval dataset."""

from __future__ import annotations

from pathlib import Path

import yaml


def _cases() -> list[dict[str, object]]:
    path = Path(__file__).resolve().parents[1] / "datasets" / "dev" / "us4_approval.yaml"
    return list((yaml.safe_load(path.read_text(encoding="utf-8")) or {})["cases"])


def test_all_four_required_approval_scenarios_exist() -> None:
    flows = {case["approvalFlow"] for case in _cases()}

    assert flows == {
        "pending-only",
        "deny-then-resume",
        "cross-bound-resume",
        "self-approval",
    }


def test_every_approval_case_forbids_after_sales_writes() -> None:
    for case in _cases():
        expect = case["expect"]
        assert expect["maxWriteCount"] == 0
        assert expect["approvalCount"] >= 1
        assert expect["approvalRequestIdRequired"] is True
        assert expect["approvalToolRequired"] is True
