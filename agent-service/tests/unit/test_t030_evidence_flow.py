"""T030 flow tests: language understanding -> evidence collection -> Java eligibility handoff."""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.agent.eligibility_execution import check_eligibility
from app.agent.evidence_execution import execute_read_evidence
from app.agent.evidence_routing import (
    EvidenceAction,
    EvidenceGuardStatus,
    EvidenceRoutingContext,
    build_evidence_routing_context,
    decide_next_evidence,
    guard_evidence_proposal,
)
from app.agent.order_resolution import OrderResolutionStatus, resolve_single_order
from app.agent.request_understanding import RequestIntent, understand_request
from app.clients.models import EligibilityDecision, LogisticsSnapshot, OrderSnapshot, OrderSummary
from app.tools.models import ToolEnvelope
from app.tools.registry import ToolRegistry


class _UnderstandingModel:
    async def understand_request(self, user_request: str) -> object:
        assert "order-001" in user_request
        return {
            "intent": "REFUND_REQUEST",
            "mentionsLogisticsProblem": True,
            "mentionedOrderId": "order-001",
        }


class _EvidenceModel:
    def __init__(self) -> None:
        self.contexts: list[EvidenceRoutingContext] = []

    async def decide_next_evidence(self, context: EvidenceRoutingContext) -> object:
        self.contexts.append(context)
        if "LOGISTICS" not in context.observed_evidence_types:
            return {
                "action": "CALL_TOOL",
                "tool": "get_logistics",
                "reasonCode": "NEED_LOGISTICS_STATE",
            }
        return {
            "action": "READY_FOR_ELIGIBILITY",
            "tool": None,
            "reasonCode": "ENOUGH_EVIDENCE_FOR_ELIGIBILITY",
        }


class _RepeatingEvidenceModel:
    async def decide_next_evidence(self, context: EvidenceRoutingContext) -> object:
        return {
            "action": "CALL_TOOL",
            "tool": "get_logistics",
            "reasonCode": "NEED_LOGISTICS_STATE",
        }


class _FakeCommerceTools:
    def __init__(self, *, order_visible: bool = True) -> None:
        self.order_visible = order_visible
        self.calls: list[tuple[str, str | None]] = []

    async def list_user_orders(self) -> ToolEnvelope[list[OrderSummary]]:
        self.calls.append(("list_user_orders", None))
        return ToolEnvelope(success=True, data=[], latency_ms=1)

    async def get_order(self, order_id: str) -> ToolEnvelope[OrderSnapshot]:
        self.calls.append(("get_order", order_id))
        if not self.order_visible:
            return ToolEnvelope[OrderSnapshot](
                success=False,
                error_code="ORDER_NOT_FOUND",
                retryable=False,
                latency_ms=2,
                trace_id="java-trace-order-hidden",
            )
        return ToolEnvelope(
            success=True,
            data=OrderSnapshot.model_validate(
                {
                    "orderId": order_id,
                    "status": "SHIPPED",
                    "totalAmount": Decimal("199.00"),
                    "currency": "CNY",
                    "items": [],
                    "afterSalesStatus": None,
                }
            ),
            latency_ms=2,
            trace_id="java-trace-order-001",
        )

    async def get_logistics(self, order_id: str) -> ToolEnvelope[LogisticsSnapshot]:
        self.calls.append(("get_logistics", order_id))
        return ToolEnvelope(
            success=True,
            data=LogisticsSnapshot.model_validate(
                {
                    "status": "IN_TRANSIT",
                    "signed": False,
                    "lastMeaningfulEventAt": None,
                    "stalledHours": 384,
                }
            ),
            latency_ms=3,
            trace_id="java-trace-logistics-001",
        )

    async def check_after_sales_eligibility(
        self, order_id: str, reason_code: str
    ) -> ToolEnvelope[EligibilityDecision]:
        self.calls.append(("check_after_sales_eligibility", reason_code))
        return ToolEnvelope(
            success=True,
            data=EligibilityDecision.model_validate(
                {
                    "eligible": True,
                    "allowedAction": "REFUND_ONLY",
                    "maxRefundAmount": Decimal("199.00"),
                    "approvalRequired": False,
                    "ruleCode": "LOGISTICS_STALLED_REFUND",
                    "ruleVersion": 1,
                    "reasonCodes": ["STALL_THRESHOLD_MET"],
                }
            ),
            latency_ms=4,
            trace_id="java-trace-eligibility-001",
        )


@pytest.mark.asyncio
async def test_t030_happy_path_reaches_authoritative_eligibility() -> None:
    tools = _FakeCommerceTools()
    evidence_model = _EvidenceModel()

    understood = await understand_request(
        "物流三天没动了，直接给我退 9999 元，订单 order-001",
        model=_UnderstandingModel(),
    )
    assert understood.intent is RequestIntent.REFUND_REQUEST
    assert understood.mentioned_order_id == "order-001"

    resolution = await resolve_single_order(understood, tools=tools)
    assert resolution.status is OrderResolutionStatus.RESOLVED
    assert resolution.resolved_order_id == "order-001"
    assert resolution.order is not None

    first_context = build_evidence_routing_context(
        understood,
        order=resolution.order,
        evidence=[],
    )
    first_proposal = await decide_next_evidence(first_context, model=evidence_model)
    first_guard = guard_evidence_proposal(
        first_proposal,
        resolved_order_id=resolution.resolved_order_id,
        observed_evidence_types=set(first_context.observed_evidence_types),
        registry=ToolRegistry(),
    )
    assert first_guard.status is EvidenceGuardStatus.ALLOWED
    assert first_guard.tool == "get_logistics"

    evidence_result = await execute_read_evidence(
        first_guard,
        resolved_order_id=resolution.resolved_order_id,
        step_index=2,
        tools=tools,
    )
    assert evidence_result.evidence is not None
    assert evidence_result.evidence.evidence_type == "LOGISTICS"
    assert evidence_result.evidence.data["stalledHours"] == 384

    second_context = build_evidence_routing_context(
        understood,
        order=resolution.order,
        evidence=[evidence_result.evidence],
    )
    second_proposal = await decide_next_evidence(second_context, model=evidence_model)
    second_guard = guard_evidence_proposal(
        second_proposal,
        resolved_order_id=resolution.resolved_order_id,
        observed_evidence_types=set(second_context.observed_evidence_types),
        registry=ToolRegistry(),
    )
    assert second_guard.status is EvidenceGuardStatus.ALLOWED
    assert second_guard.action is EvidenceAction.READY_FOR_ELIGIBILITY

    eligibility_result = await check_eligibility(
        second_guard,
        resolved_order_id=resolution.resolved_order_id,
        step_index=3,
        tools=tools,
    )

    assert eligibility_result.eligibility is not None
    assert eligibility_result.eligibility.eligible is True
    assert eligibility_result.eligibility.allowed_action == "REFUND_ONLY"
    assert eligibility_result.eligibility.max_refund_amount == Decimal("199.00")
    assert eligibility_result.eligibility.reason_codes == ["STALL_THRESHOLD_MET"]
    assert [context.observed_evidence_types for context in evidence_model.contexts] == [
        ["ORDER"],
        ["ORDER", "LOGISTICS"],
    ]
    assert tools.calls == [
        ("get_order", "order-001"),
        ("get_logistics", "order-001"),
        ("check_after_sales_eligibility", "LOGISTICS_DELAY"),
    ]


@pytest.mark.asyncio
async def test_cross_owner_or_missing_order_stops_before_evidence_collection() -> None:
    tools = _FakeCommerceTools(order_visible=False)
    understood = await understand_request(
        "帮我退 order-001",
        model=_UnderstandingModel(),
    )

    resolution = await resolve_single_order(understood, tools=tools)

    assert resolution.status is OrderResolutionStatus.UNRESOLVED
    assert resolution.resolved_order_id is None
    assert resolution.error_code == "ORDER_NOT_FOUND"
    assert tools.calls == [("get_order", "order-001")]


@pytest.mark.asyncio
async def test_duplicate_logistics_proposal_is_blocked_instead_of_looping() -> None:
    tools = _FakeCommerceTools()
    understood = await understand_request(
        "物流三天没动了，直接给我退 9999 元，订单 order-001",
        model=_UnderstandingModel(),
    )
    resolution = await resolve_single_order(understood, tools=tools)
    assert resolution.order is not None
    assert resolution.resolved_order_id is not None

    existing_logistics = await tools.get_logistics(resolution.resolved_order_id)
    assert existing_logistics.data is not None
    evidence = [
        __import__("app.agent.state", fromlist=["EvidenceItem"]).EvidenceItem(
            evidence_type="LOGISTICS",
            source="get_logistics",
            data=existing_logistics.data.model_dump(by_alias=True, mode="json"),
        )
    ]
    context = build_evidence_routing_context(
        understood,
        order=resolution.order,
        evidence=evidence,
    )
    proposal = await decide_next_evidence(context, model=_RepeatingEvidenceModel())
    guard = guard_evidence_proposal(
        proposal,
        resolved_order_id=resolution.resolved_order_id,
        observed_evidence_types=set(context.observed_evidence_types),
        registry=ToolRegistry(),
    )

    assert guard.status is EvidenceGuardStatus.DENIED
    assert guard.reason_code == "EVIDENCE_ALREADY_PRESENT"
