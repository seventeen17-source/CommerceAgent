"""T030 tests for rebuilding minimal model context after new evidence arrives."""

from __future__ import annotations

from decimal import Decimal

from app.agent.evidence_routing import build_evidence_routing_context
from app.agent.request_understanding import RequestIntent, UnderstoodRequest
from app.agent.state import EvidenceItem
from app.clients.models import OrderSnapshot


def _understood() -> UnderstoodRequest:
    return UnderstoodRequest(
        intent=RequestIntent.REFUND_REQUEST,
        mentions_logistics_problem=True,
        mentioned_order_id="order-001",
    )


def _order() -> OrderSnapshot:
    return OrderSnapshot.model_validate(
        {
            "orderId": "order-001",
            "status": "SHIPPED",
            "totalAmount": Decimal("199.00"),
            "currency": "CNY",
            "items": [],
            "afterSalesStatus": None,
        }
    )


def test_first_round_context_contains_order_but_no_logistics_evidence() -> None:
    context = build_evidence_routing_context(
        _understood(),
        order=_order(),
        evidence=[],
    )

    assert context.observed_evidence_types == ["ORDER"]
    assert context.order_status == "SHIPPED"


def test_second_round_context_adds_logistics_after_authoritative_read() -> None:
    context = build_evidence_routing_context(
        _understood(),
        order=_order(),
        evidence=[
            EvidenceItem(
                evidence_type="LOGISTICS",
                source="get_logistics",
                data={
                    "status": "IN_TRANSIT",
                    "signed": False,
                    "stalledHours": 384,
                },
            )
        ],
    )

    assert context.observed_evidence_types == ["ORDER", "LOGISTICS"]


def test_context_does_not_expose_order_id_amount_or_user_identity() -> None:
    context = build_evidence_routing_context(
        _understood(),
        order=_order(),
        evidence=[],
    )

    dumped = context.model_dump(by_alias=True, mode="json")

    assert "orderId" not in dumped
    assert "totalAmount" not in dumped
    assert "userId" not in dumped
    assert dumped == {
        "intent": "REFUND_REQUEST",
        "mentionsLogisticsProblem": True,
        "orderStatus": "SHIPPED",
        "observedEvidenceTypes": ["ORDER"],
    }


def test_duplicate_evidence_types_are_collapsed_for_loop_progress() -> None:
    evidence = [
        EvidenceItem(evidence_type="LOGISTICS", source="get_logistics", data={"signed": False}),
        EvidenceItem(evidence_type="LOGISTICS", source="get_logistics", data={"signed": False}),
    ]

    context = build_evidence_routing_context(
        _understood(),
        order=_order(),
        evidence=evidence,
    )

    assert context.observed_evidence_types == ["ORDER", "LOGISTICS"]
