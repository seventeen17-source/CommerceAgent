"""Unit tests for the T032 read-stage nodes and the assembled graph topology.

`build_graph` takes a node map, so these tests hand it the two real nodes plus recording stand-ins
for the stages that land in later steps. That makes the *path* the routers choose assertable - which
is the property worth pinning here: a node is cheap to re-read, a wrong edge is not.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import uuid4

import pytest

from app.agent.evidence_routing import (
    EvidenceAction,
    EvidenceGuardDecision,
    EvidenceGuardStatus,
)
from app.agent.graph import GraphNode, GraphState, GraphUpdate, build_graph
from app.agent.nodes import (
    GraphDeps,
    build_evidence_nodes,
    build_lifecycle_nodes,
    build_read_nodes,
    build_write_nodes,
)
from app.agent.order_resolution import OrderResolution, OrderResolutionStatus
from app.agent.request_understanding import UnderstoodRequest
from app.agent.routing import (
    Decision,
    Node,
    SafeStopReason,
    route_after_decision,
    route_after_eligibility,
)
from app.agent.state import (
    AgentState,
    RunStatus,
    VerificationStatus,
    WriteIntent,
    WriteOutcome,
    WriteStatus,
    advance,
)
from app.clients.models import (
    AfterSalesStatus,
    EligibilityDecision,
    LogisticsSnapshot,
    OrderSnapshot,
    OrderSummary,
    RefundResult,
)
from app.tools.models import ToolEnvelope
from app.tools.registry import ToolRegistry

TRACE = "trace-0001"


def make_state(**overrides: Any) -> AgentState:
    base: dict[str, Any] = {
        "run_id": uuid4(),
        "principal": {"user_id": "customer-001", "role": "CUSTOMER"},
        "user_request": "我的包裹卡在路上了，我要退款",
        "intent": "REFUND_REQUEST",
    }
    base.update(overrides)
    return AgentState.model_validate(base)


def make_order(order_id: str = "order-001") -> OrderSnapshot:
    return OrderSnapshot.model_validate(
        {
            "orderId": order_id,
            "status": "SHIPPED",
            "totalAmount": "199.00",
            "currency": "CNY",
            "items": [],
        }
    )


def make_summary(order_id: str) -> OrderSummary:
    return OrderSummary.model_validate(
        {
            "orderId": order_id,
            "productSummary": "无线耳机",
            "status": "SHIPPED",
            "createdAt": datetime(2026, 9, 1, tzinfo=UTC),
        }
    )


def ok_order(order_id: str) -> ToolEnvelope[OrderSnapshot]:
    return ToolEnvelope[OrderSnapshot](
        success=True, data=make_order(order_id), latency_ms=3, trace_id=TRACE
    )


class FakeUnderstanding:
    """Stand-in for the OpenAI-compatible adapter; returns whatever the test declares."""

    def __init__(
        self,
        *,
        intent: str = "REFUND_REQUEST",
        mentioned_order_id: str | None = None,
        mentions_logistics_problem: bool = True,
    ) -> None:
        self._output: dict[str, Any] = {
            "intent": intent,
            "mentions_logistics_problem": mentions_logistics_problem,
            "mentioned_order_id": mentioned_order_id,
        }

    async def understand_request(self, user_request: str) -> object:
        return self._output


class ConfirmedOrderTools:
    """One listed order, confirmed by Java ownership."""

    def __init__(self, order_id: str = "order-001") -> None:
        self._order_id = order_id

    async def list_user_orders(self) -> ToolEnvelope[list[OrderSummary]]:
        return ToolEnvelope[list[OrderSummary]](
            success=True, data=[make_summary(self._order_id)], latency_ms=2, trace_id=TRACE
        )

    async def get_order(self, order_id: str) -> ToolEnvelope[OrderSnapshot]:
        return ok_order(order_id)


class CatalogueOrderTools:
    """Several listed orders: the case that must ask the user instead of ranking them."""

    def __init__(self, order_ids: list[str]) -> None:
        self._order_ids = order_ids

    async def list_user_orders(self) -> ToolEnvelope[list[OrderSummary]]:
        return ToolEnvelope[list[OrderSummary]](
            success=True,
            data=[make_summary(order_id) for order_id in self._order_ids],
            latency_ms=2,
            trace_id=TRACE,
        )

    async def get_order(self, order_id: str) -> ToolEnvelope[OrderSnapshot]:
        return ok_order(order_id)


class RejectingOrderTools:
    """Java refuses the lookup - the cross-owner or missing-order case, both concealed as 404."""

    async def list_user_orders(self) -> ToolEnvelope[list[OrderSummary]]:
        raise AssertionError("this double is only used with a mentioned order id")

    async def get_order(self, order_id: str) -> ToolEnvelope[OrderSnapshot]:
        return ToolEnvelope[OrderSnapshot](
            success=False,
            error_code="ORDER_NOT_FOUND",
            retryable=False,
            latency_ms=2,
            trace_id=TRACE,
        )


class UnusedDependency:
    """Fails loudly if a read-stage node reaches for a later stage's capability."""

    async def decide_next_evidence(self, context: object) -> object:
        raise AssertionError("evidence routing must not run in this stage")

    async def get_logistics(self, order_id: str) -> object:
        raise AssertionError("evidence execution must not run in this stage")

    async def check_after_sales_eligibility(self, order_id: str, reason_code: str) -> object:
        raise AssertionError("eligibility must not run in this stage")

    async def request_human_approval(self, **kwargs: Any) -> object:
        raise AssertionError("approval creation must not run in this stage")

    async def create_refund_request(self, **kwargs: Any) -> object:
        raise AssertionError("a refund write must not run in this stage")

    async def get_after_sales_status(
        self, order_id: str, *, idempotency_key: str | None = None
    ) -> object:
        raise AssertionError("after-sales reads must not run in this stage")


async def unused_persist(
    state: AgentState, intent: WriteIntent, outcome: WriteOutcome
) -> AgentState:
    raise AssertionError("no write intent may be persisted in this test")


def make_deps(*, understanding: Any, orders: Any) -> GraphDeps:
    unused = UnusedDependency()
    return GraphDeps(
        understanding=understanding,
        orders=orders,
        evidence_model=unused,
        evidence=unused,
        registry=ToolRegistry(),
        eligibility=unused,
        approvals=unused,
        writes=unused,
        after_sales=unused,
        persist_intent=unused_persist,
    )


def _recording(name: Node, implementation: GraphNode, trail: list[str]) -> GraphNode:
    async def node(graph: GraphState) -> GraphUpdate:
        trail.append(name.value)
        return await implementation(graph)

    return node


def _stand_in(name: Node, trail: list[str]) -> GraphNode:
    async def node(graph: GraphState) -> GraphUpdate:
        trail.append(name.value)
        return GraphUpdate(state=graph["state"], decision=Decision())

    return node


def assemble_read_graph(
    *,
    understanding: Any,
    orders: Any,
    decisions: list[Decision] | None = None,
) -> tuple[Any, list[str]]:
    """Assemble the real read nodes with recording stand-ins for the later stages."""
    trail: list[str] = []
    nodes: dict[Node, GraphNode] = {
        name: _recording(name, implementation, trail)
        for name, implementation in build_read_nodes(
            make_deps(understanding=understanding, orders=orders)
        ).items()
    }

    queue = list(decisions or [])

    async def decide_evidence(graph: GraphState) -> GraphUpdate:
        trail.append(Node.DECIDE_EVIDENCE.value)
        queued = queue.pop(0) if queue else Decision()
        return GraphUpdate(state=graph["state"], decision=queued)

    nodes[Node.DECIDE_EVIDENCE] = decide_evidence

    async def check_eligibility(graph: GraphState) -> GraphUpdate:
        """A stand-in has to satisfy the contract of the node it replaces.

        ``route_after_eligibility`` reads ``state.eligibility``, so a stub that left it unset would
        be modelling a node that cannot exist - and it would hide exactly the routing bug this
        stand-in is meant to expose. This one answers "not eligible", which ends the walk at
        ``finalize``.
        """
        trail.append(Node.CHECK_ELIGIBILITY.value)
        moved = advance(
            graph["state"],
            eligibility={"eligible": False, "allowed_action": "DENY", "approval_required": False},
        )
        return GraphUpdate(state=moved, decision=Decision())

    nodes[Node.CHECK_ELIGIBILITY] = check_eligibility
    for name in Node:
        nodes.setdefault(name, _stand_in(name, trail))

    return build_graph(nodes), trail


def allowed_tool_guard() -> EvidenceGuardDecision:
    """An authorized single evidence read."""
    return EvidenceGuardDecision(
        status=EvidenceGuardStatus.ALLOWED,
        action=EvidenceAction.CALL_TOOL,
        tool="get_logistics",
        reason_code="SAFE_EVIDENCE_READ_ALLOWED",
    )


def ready_guard() -> EvidenceGuardDecision:
    """The model's "enough evidence" proposal, as the guard authorizes it."""
    return EvidenceGuardDecision(
        status=EvidenceGuardStatus.ALLOWED,
        action=EvidenceAction.READY_FOR_ELIGIBILITY,
        reason_code="READY_FOR_DETERMINISTIC_ELIGIBILITY",
    )


def make_understood(order_id: str | None = "order-001") -> UnderstoodRequest:
    return UnderstoodRequest(
        intent="REFUND_REQUEST",
        mentions_logistics_problem=True,
        mentioned_order_id=order_id,
    )


def make_resolution(order_id: str = "order-001") -> OrderResolution:
    return OrderResolution(
        status=OrderResolutionStatus.RESOLVED,
        candidate_order_ids=[order_id],
        resolved_order_id=order_id,
        order=make_order(order_id),
    )


class FakeEvidenceModel:
    """Returns one fixed proposal; the narrow schema still validates it."""

    def __init__(self, proposal: dict[str, Any]) -> None:
        self._proposal = proposal

    async def decide_next_evidence(self, context: object) -> object:
        return self._proposal


class FakeEvidenceTools:
    """One logistics read, succeeding or failing exactly as the test declares."""

    def __init__(self, *, failure: str | None = None, retryable: bool = False) -> None:
        self._failure = failure
        self._retryable = retryable

    async def get_logistics(self, order_id: str) -> ToolEnvelope[LogisticsSnapshot]:
        if self._failure is not None:
            return ToolEnvelope[LogisticsSnapshot](
                success=False,
                error_code=self._failure,
                retryable=self._retryable,
                latency_ms=2,
                trace_id=TRACE,
            )
        return ToolEnvelope[LogisticsSnapshot](
            success=True,
            data=LogisticsSnapshot.model_validate(
                {"status": "IN_TRANSIT", "signed": False, "stalledHours": 96}
            ),
            latency_ms=2,
            trace_id=TRACE,
        )


def logistics_proposal() -> dict[str, Any]:
    return {"action": "CALL_TOOL", "tool": "get_logistics", "reasonCode": "NEED_LOGISTICS_STATE"}


def make_evidence_deps(*, model: Any, tools: Any) -> GraphDeps:
    unused = UnusedDependency()
    return GraphDeps(
        understanding=FakeUnderstanding(),
        orders=ConfirmedOrderTools("order-001"),
        evidence_model=model,
        evidence=tools,
        registry=ToolRegistry(),
        eligibility=unused,
        writes=unused,
        after_sales=unused,
        persist_intent=unused_persist,
    )


class TestUnderstandNode:
    @pytest.mark.asyncio
    async def test_records_the_order_clue_as_a_candidate_not_as_a_resolution(self) -> None:
        nodes = build_read_nodes(
            make_deps(understanding=FakeUnderstanding(mentioned_order_id="order-001"), orders=None)
        )
        update = await nodes[Node.UNDERSTAND]({"state": make_state()})

        assert update["state"].candidate_order_ids == ["order-001"]
        assert update["state"].resolved_order_id is None
        assert update["state"].intent == "REFUND_REQUEST"

    @pytest.mark.asyncio
    async def test_spends_exactly_one_step_of_budget(self) -> None:
        nodes = build_read_nodes(make_deps(understanding=FakeUnderstanding(), orders=None))
        update = await nodes[Node.UNDERSTAND]({"state": make_state()})

        assert update["state"].step_count == 1

    @pytest.mark.asyncio
    async def test_carries_the_interpretation_in_the_control_plane(self) -> None:
        nodes = build_read_nodes(
            make_deps(understanding=FakeUnderstanding(mentioned_order_id="order-001"), orders=None)
        )
        update = await nodes[Node.UNDERSTAND]({"state": make_state()})

        assert update["understood"] is not None
        assert update["understood"].mentioned_order_id == "order-001"


class TestResolveOrderNode:
    @pytest.mark.asyncio
    async def test_java_confirmation_is_what_sets_the_resolved_order(self) -> None:
        nodes = build_read_nodes(
            make_deps(
                understanding=FakeUnderstanding(mentioned_order_id="order-001"),
                orders=ConfirmedOrderTools("order-001"),
            )
        )
        understood = (await nodes[Node.UNDERSTAND]({"state": make_state()}))["understood"]
        update = await nodes[Node.RESOLVE_ORDER]({"state": make_state(), "understood": understood})

        assert update["state"].resolved_order_id == "order-001"
        assert update["decision"].resolution_attempted is True
        assert update["decision"].safe_stop_reason is None

    @pytest.mark.asyncio
    async def test_a_concealed_refusal_leaves_the_clue_but_resolves_nothing(self) -> None:
        nodes = build_read_nodes(
            make_deps(
                understanding=FakeUnderstanding(mentioned_order_id="order-002"),
                orders=RejectingOrderTools(),
            )
        )
        understood = (await nodes[Node.UNDERSTAND]({"state": make_state()}))["understood"]
        update = await nodes[Node.RESOLVE_ORDER]({"state": make_state(), "understood": understood})

        assert update["state"].resolved_order_id is None
        assert update["state"].candidate_order_ids == ["order-002"]

    @pytest.mark.asyncio
    async def test_refuses_when_no_interpretation_was_carried_into_this_invocation(self) -> None:
        """Resume without re-understanding must refuse rather than rebuild a fake interpretation."""
        nodes = build_read_nodes(make_deps(understanding=FakeUnderstanding(), orders=None))
        update = await nodes[Node.RESOLVE_ORDER]({"state": make_state()})

        assert update["decision"].safe_stop_reason is SafeStopReason.ORDER_UNRESOLVED


class TestAssembledTopology:
    @pytest.mark.asyncio
    async def test_ready_for_eligibility_walk(self) -> None:
        graph, trail = assemble_read_graph(
            understanding=FakeUnderstanding(mentioned_order_id="order-001"),
            orders=ConfirmedOrderTools("order-001"),
            decisions=[Decision(guard=ready_guard())],
        )
        final = await graph.ainvoke({"state": make_state()})

        assert trail == [
            "understand",
            "resolve_order",
            "decide_evidence",
            "check_eligibility",
            "finalize",
        ]
        assert final["state"].resolved_order_id == "order-001"

    @pytest.mark.asyncio
    async def test_allowed_tool_call_loops_back_through_the_decision_node(self) -> None:
        graph, trail = assemble_read_graph(
            understanding=FakeUnderstanding(mentioned_order_id="order-001"),
            orders=ConfirmedOrderTools("order-001"),
            decisions=[
                Decision(guard=allowed_tool_guard()),
                Decision(guard=ready_guard()),
            ],
        )
        await graph.ainvoke({"state": make_state()})

        assert trail == [
            "understand",
            "resolve_order",
            "decide_evidence",
            "execute_evidence",
            "decide_evidence",
            "check_eligibility",
            "finalize",
        ]

    @pytest.mark.asyncio
    async def test_several_matching_orders_stop_at_waiting_user(self) -> None:
        graph, trail = assemble_read_graph(
            understanding=FakeUnderstanding(),
            orders=CatalogueOrderTools(["order-001", "order-002"]),
        )
        final = await graph.ainvoke({"state": make_state()})

        assert trail == ["understand", "resolve_order", "waiting_user"]
        assert final["state"].resolved_order_id is None

    @pytest.mark.asyncio
    async def test_unrecognised_intent_stops_at_waiting_user_before_any_tool_call(self) -> None:
        graph, trail = assemble_read_graph(
            understanding=FakeUnderstanding(intent="UNKNOWN"),
            orders=ConfirmedOrderTools("order-001"),
        )
        await graph.ainvoke({"state": make_state()})

        assert trail == ["understand", "waiting_user"]

    def test_incomplete_assembly_is_rejected_before_it_can_run(self) -> None:
        """A missing node must be a startup error, not a run that dies mid-flow."""
        with pytest.raises(ValueError, match="missing nodes"):
            build_graph({Node.UNDERSTAND: _stand_in(Node.UNDERSTAND, [])})


class TestEvidenceNodes:
    """The evidence loop: one authorized read, and what a failed read is allowed to change."""

    def _context(self, *, evidence: list[dict[str, Any]] | None = None) -> GraphState:
        return {
            "state": make_state(resolved_order_id="order-001", evidence=evidence or []),
            "understood": make_understood(),
            "resolution": make_resolution(),
        }

    @pytest.mark.asyncio
    async def test_an_authorized_read_lands_evidence_and_a_trace_entry(self) -> None:
        nodes = build_evidence_nodes(
            make_evidence_deps(
                model=FakeEvidenceModel(logistics_proposal()), tools=FakeEvidenceTools()
            )
        )
        decided = await nodes[Node.DECIDE_EVIDENCE](self._context())
        executed = await nodes[Node.EXECUTE_EVIDENCE](
            {"state": decided["state"], "decision": decided["decision"]}
        )

        assert decided["decision"].guard is not None
        assert decided["decision"].guard.status is EvidenceGuardStatus.ALLOWED
        assert [item.evidence_type for item in executed["state"].evidence] == ["LOGISTICS"]
        assert executed["state"].tool_history[0].success is True
        assert executed["state"].retry_count == 0
        assert executed["decision"].evidence_path_closed is False

    @pytest.mark.asyncio
    async def test_a_transient_read_failure_retries_within_the_retry_budget(self) -> None:
        """A 503 is not a conclusion: it is retried, and it is not mislabelled a budget problem."""
        nodes = build_evidence_nodes(
            make_evidence_deps(
                model=FakeEvidenceModel(logistics_proposal()),
                tools=FakeEvidenceTools(failure="LOGISTICS_UNAVAILABLE", retryable=True),
            )
        )
        decided = await nodes[Node.DECIDE_EVIDENCE](self._context())
        executed = await nodes[Node.EXECUTE_EVIDENCE](
            {"state": decided["state"], "decision": decided["decision"]}
        )

        assert executed["state"].retry_count == 1
        assert executed["decision"].retry_current_stage is True
        assert executed["state"].evidence == []
        assert executed["state"].tool_history[0].retryable is True

    @pytest.mark.asyncio
    async def test_a_transient_failure_with_no_retry_budget_left_stops_collecting(self) -> None:
        nodes = build_evidence_nodes(
            make_evidence_deps(
                model=FakeEvidenceModel(logistics_proposal()),
                tools=FakeEvidenceTools(failure="LOGISTICS_UNAVAILABLE", retryable=True),
            )
        )
        context = self._context()
        context["state"] = make_state(resolved_order_id="order-001", retry_count=2, max_retries=2)
        decided = await nodes[Node.DECIDE_EVIDENCE](context)
        executed = await nodes[Node.EXECUTE_EVIDENCE](
            {"state": decided["state"], "decision": decided["decision"]}
        )

        assert executed["state"].retry_count == 2
        assert executed["decision"].evidence_path_closed is True
        assert (
            route_after_decision(executed["state"], executed["decision"]) is Node.CHECK_ELIGIBILITY
        )

    @pytest.mark.asyncio
    async def test_a_definitive_read_failure_does_not_spend_retry_budget(self) -> None:
        """`retryable=False` is the failing layer's answer; retrying cannot change it."""
        nodes = build_evidence_nodes(
            make_evidence_deps(
                model=FakeEvidenceModel(logistics_proposal()),
                tools=FakeEvidenceTools(failure="ORDER_NOT_FOUND", retryable=False),
            )
        )
        decided = await nodes[Node.DECIDE_EVIDENCE](self._context())
        executed = await nodes[Node.EXECUTE_EVIDENCE](
            {"state": decided["state"], "decision": decided["decision"]}
        )

        assert executed["state"].retry_count == 0
        assert executed["decision"].evidence_path_closed is True
        assert executed["state"].tool_history[0].error_code == "ORDER_NOT_FOUND"

    @pytest.mark.asyncio
    async def test_evidence_already_observed_is_denied_and_hands_off(self) -> None:
        """The guard looks at evidence that exists, so a second logistics read is refused."""
        nodes = build_evidence_nodes(
            make_evidence_deps(
                model=FakeEvidenceModel(logistics_proposal()), tools=FakeEvidenceTools()
            )
        )
        context = self._context(
            evidence=[{"evidence_type": "LOGISTICS", "source": "get_logistics"}]
        )
        decided = await nodes[Node.DECIDE_EVIDENCE](context)

        assert decided["decision"].guard is not None
        assert decided["decision"].guard.status is EvidenceGuardStatus.DENIED
        assert route_after_decision(decided["state"], decided["decision"]) is Node.CHECK_ELIGIBILITY

    @pytest.mark.asyncio
    async def test_missing_control_plane_context_refuses_instead_of_inventing_it(self) -> None:
        nodes = build_evidence_nodes(
            make_evidence_deps(
                model=FakeEvidenceModel(logistics_proposal()), tools=FakeEvidenceTools()
            )
        )
        update = await nodes[Node.DECIDE_EVIDENCE]({"state": make_state()})

        assert update["decision"].safe_stop_reason is SafeStopReason.EVIDENCE_CONTEXT_MISSING
        assert route_after_decision(update["state"], update["decision"]) is Node.SAFE_STOP


def make_write_intent() -> dict[str, Any]:
    """A durable write intent, as T022 persists it before the request is sent."""
    return {
        "action": "CREATE_REFUND_REQUEST",
        "target_id": "order-001",
        "idempotency_key": "0123456789abcdef",
        "request_fingerprint": "a" * 64,
    }


class FakeEligibilityTools:
    """Java's eligibility answer, or its absence."""

    def __init__(
        self,
        *,
        decision: dict[str, Any] | None = None,
        error_code: str | None = None,
        retryable: bool = False,
    ) -> None:
        self._decision = decision
        self._error_code = error_code
        self._retryable = retryable

    async def check_after_sales_eligibility(
        self, order_id: str, reason_code: str
    ) -> ToolEnvelope[EligibilityDecision]:
        if self._error_code is not None:
            return ToolEnvelope[EligibilityDecision](
                success=False,
                error_code=self._error_code,
                retryable=self._retryable,
                latency_ms=1,
                trace_id=TRACE,
            )
        payload = self._decision or {
            "eligible": True,
            "allowedAction": "REFUND_ONLY",
            "maxRefundAmount": "199.00",
            "approvalRequired": False,
        }
        return ToolEnvelope[EligibilityDecision](
            success=True,
            data=EligibilityDecision.model_validate(payload),
            latency_ms=1,
            trace_id=TRACE,
        )


def refund_result(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "refundRequestId": "refund-001",
        "status": "CREATED",
        "acceptedAmount": "199.00",
    }
    base.update(overrides)
    return base


class FakeRefundWriteTools:
    """A backend that answers however the test says, recording the call order."""

    def __init__(self, *, mode: str = "success", calls: list[str] | None = None) -> None:
        self._mode = mode
        self.calls: list[str] = calls if calls is not None else []

    async def create_refund_request(self, **kwargs: Any) -> ToolEnvelope[RefundResult]:
        self.calls.append("create_refund_request")
        if self._mode == "success":
            return ToolEnvelope[RefundResult](
                success=True,
                data=RefundResult.model_validate(refund_result()),
                latency_ms=1,
                trace_id=TRACE,
            )
        return ToolEnvelope[RefundResult](
            success=False,
            error_code="WRITE_TIMEOUT_UNKNOWN",
            retryable=False,
            latency_ms=1,
            trace_id=TRACE,
        )

    async def get_after_sales_status(
        self, order_id: str, *, idempotency_key: str | None = None
    ) -> ToolEnvelope[AfterSalesStatus]:
        self.calls.append("get_after_sales_status")
        refunds = [refund_result()] if self._mode == "recovered" else []
        return ToolEnvelope[AfterSalesStatus](
            success=True,
            data=AfterSalesStatus.model_validate({"refunds": refunds, "returns": []}),
            latency_ms=1,
            trace_id=TRACE,
        )


class FakeAfterSalesReads:
    """The authority's answer to "does a refund exist for this key?"."""

    def __init__(self, refunds: list[dict[str, Any]]) -> None:
        self._refunds = refunds
        self.keys: list[str | None] = []

    async def get_after_sales_status(
        self, order_id: str, *, idempotency_key: str | None = None
    ) -> ToolEnvelope[AfterSalesStatus]:
        self.keys.append(idempotency_key)
        return ToolEnvelope[AfterSalesStatus](
            success=True,
            data=AfterSalesStatus.model_validate({"refunds": self._refunds, "returns": []}),
            latency_ms=1,
            trace_id=TRACE,
        )


def make_write_deps(
    *,
    eligibility: Any = None,
    writes: Any = None,
    after_sales: Any = None,
    persist: Any = None,
    record_trace: Any = None,
) -> GraphDeps:
    unused = UnusedDependency()
    return GraphDeps(
        understanding=FakeUnderstanding(),
        orders=ConfirmedOrderTools("order-001"),
        evidence_model=unused,
        evidence=unused,
        registry=ToolRegistry(),
        eligibility=eligibility or unused,
        writes=writes or unused,
        after_sales=after_sales or unused,
        persist_intent=persist or unused_persist,
        record_trace=record_trace,
    )


def eligible_state(**overrides: Any) -> AgentState:
    base: dict[str, Any] = {
        "resolved_order_id": "order-001",
        "eligibility": {
            "eligible": True,
            "allowed_action": "REFUND_ONLY",
            "max_refund_amount": Decimal("199.00"),
            "approval_required": False,
        },
    }
    base.update(overrides)
    return make_state(**base)


class TestEligibilityNode:
    @pytest.mark.asyncio
    async def test_java_decision_is_copied_never_computed(self) -> None:
        nodes = build_write_nodes(make_write_deps(eligibility=FakeEligibilityTools()))
        update = await nodes[Node.CHECK_ELIGIBILITY](
            {"state": make_state(resolved_order_id="order-001")}
        )

        assert update["state"].eligibility is not None
        assert update["state"].eligibility.allowed_action == "REFUND_ONLY"
        assert update["state"].tool_history[0].tool_name == "check_after_sales_eligibility"
        assert update["decision"].safe_stop_reason is None

    @pytest.mark.asyncio
    async def test_a_transient_failure_retries_the_same_question(self) -> None:
        nodes = build_write_nodes(
            make_write_deps(
                eligibility=FakeEligibilityTools(
                    error_code="ELIGIBILITY_UNAVAILABLE", retryable=True
                )
            )
        )
        update = await nodes[Node.CHECK_ELIGIBILITY](
            {"state": make_state(resolved_order_id="order-001")}
        )

        assert update["decision"].retry_current_stage is True
        assert update["state"].retry_count == 1
        assert update["state"].eligibility is None

    @pytest.mark.asyncio
    async def test_no_answer_and_no_budget_stops_instead_of_claiming_not_eligible(self) -> None:
        """Finishing here would report "not eligible" - a claim we cannot make."""
        nodes = build_write_nodes(
            make_write_deps(
                eligibility=FakeEligibilityTools(
                    error_code="ELIGIBILITY_UNAVAILABLE", retryable=True
                )
            )
        )
        state = make_state(resolved_order_id="order-001", retry_count=2, max_retries=2)
        update = await nodes[Node.CHECK_ELIGIBILITY]({"state": state})

        assert update["decision"].safe_stop_reason is SafeStopReason.ELIGIBILITY_UNAVAILABLE
        assert route_after_eligibility(update["state"], update["decision"]) is Node.SAFE_STOP

    @pytest.mark.asyncio
    async def test_a_finished_read_is_reported_to_the_trace_sink(self) -> None:
        """The seam has to reach the call site, or it is a parameter nobody uses."""
        reported: list[Any] = []
        nodes = build_write_nodes(
            make_write_deps(eligibility=FakeEligibilityTools(), record_trace=reported.append)
        )

        await nodes[Node.CHECK_ELIGIBILITY]({"state": make_state(resolved_order_id="order-001")})

        assert [facts.tool_name for facts in reported] == ["check_after_sales_eligibility"]
        expected_summary = {"orderId": "order-001", "reasonCode": "LOGISTICS_DELAY"}
        assert reported[0].input_summary == expected_summary
        assert reported[0].envelope.latency_ms == 1
        assert reported[0].step_index == 1

    @pytest.mark.asyncio
    async def test_no_sink_means_no_report_rather_than_a_crash(self) -> None:
        """The dev harnesses and these tests build the same nodes without a store."""
        nodes = build_write_nodes(make_write_deps(eligibility=FakeEligibilityTools()))

        update = await nodes[Node.CHECK_ELIGIBILITY](
            {"state": make_state(resolved_order_id="order-001")}
        )

        assert update["state"].eligibility is not None


class TestRefundWriteNode:
    @pytest.mark.asyncio
    async def test_the_intent_is_durable_before_the_request_is_sent(self) -> None:
        """The whole ordering, asserted as one list: persist first, then send."""
        order: list[str] = []
        writes = FakeRefundWriteTools(calls=order)

        async def persist(state: AgentState, intent: WriteIntent, outcome: WriteOutcome):
            order.append("persist_intent")
            return advance(state, write_intent=intent, write=outcome)

        nodes = build_write_nodes(make_write_deps(writes=writes, persist=persist))
        update = await nodes[Node.REFUND_WRITE]({"state": eligible_state()})

        assert order == ["persist_intent", "create_refund_request"]
        assert update["state"].write_intent is not None
        assert update["state"].write.status is WriteStatus.SUCCEEDED
        assert update["state"].write.resource_id == "refund-001"

    @pytest.mark.asyncio
    async def test_a_write_whose_intent_cannot_be_made_durable_sends_nothing(self) -> None:
        writes = FakeRefundWriteTools()

        async def failing_persist(state: AgentState, intent: WriteIntent, outcome: WriteOutcome):
            raise RuntimeError("the checkpoint store is unavailable")

        nodes = build_write_nodes(make_write_deps(writes=writes, persist=failing_persist))
        update = await nodes[Node.REFUND_WRITE]({"state": eligible_state()})

        assert writes.calls == []
        assert update["state"].write_intent is None
        assert update["decision"].safe_stop_reason is SafeStopReason.WRITE_INTENT_NOT_DURABLE

    @pytest.mark.asyncio
    async def test_an_unconfirmable_write_is_reported_as_unknown_not_success(self) -> None:
        writes = FakeRefundWriteTools(mode="unknown")
        nodes = build_write_nodes(make_write_deps(writes=writes))

        async def persist(state: AgentState, intent: WriteIntent, outcome: WriteOutcome):
            return advance(state, write_intent=intent, write=outcome)

        nodes = build_write_nodes(make_write_deps(writes=writes, persist=persist))
        update = await nodes[Node.REFUND_WRITE]({"state": eligible_state()})

        assert update["state"].write.status is WriteStatus.UNKNOWN
        assert update["state"].write_intent is not None
        assert update["state"].write.status is not WriteStatus.SUCCEEDED


class TestVerifyNode:
    @pytest.mark.asyncio
    async def test_verification_reads_the_same_key_and_reports_a_negative_honestly(self) -> None:
        reads = FakeAfterSalesReads([])
        nodes = build_write_nodes(make_write_deps(after_sales=reads))
        state = make_state(
            resolved_order_id="order-001",
            write_intent=make_write_intent(),
            write={"status": "UNKNOWN"},
        )
        update = await nodes[Node.VERIFY]({"state": state})

        assert reads.keys == ["0123456789abcdef"]
        assert update["state"].verification.status is VerificationStatus.VERIFIED_FAILURE

    @pytest.mark.asyncio
    async def test_verification_recognises_the_refund_the_key_identifies(self) -> None:
        reads = FakeAfterSalesReads([refund_result()])
        nodes = build_write_nodes(make_write_deps(after_sales=reads))
        state = make_state(
            resolved_order_id="order-001",
            write_intent=make_write_intent(),
            write={"status": "SUCCEEDED", "resource_id": "refund-001"},
        )
        update = await nodes[Node.VERIFY]({"state": state})

        assert update["state"].verification.status is VerificationStatus.VERIFIED_SUCCESS
        assert update["state"].verification.resource_id == "refund-001"

    @pytest.mark.asyncio
    async def test_verification_without_a_durable_intent_refuses_instead_of_guessing(self) -> None:
        nodes = build_write_nodes(make_write_deps(after_sales=FakeAfterSalesReads([])))
        update = await nodes[Node.VERIFY]({"state": eligible_state()})

        assert update["decision"].safe_stop_reason is SafeStopReason.WRITE_INTENT_NOT_DURABLE


class TestLifecycleNodes:
    """The nodes that end an invocation: no dependencies, so nothing here needs a store."""

    @pytest.mark.asyncio
    async def test_a_verified_result_ends_as_a_completion(self) -> None:
        nodes = build_lifecycle_nodes()
        state = make_state(verification={"status": VerificationStatus.VERIFIED_SUCCESS})
        update = await nodes[Node.FINALIZE]({"state": state})

        terminal = update["decision"].terminal
        assert terminal is not None
        assert terminal.status is RunStatus.COMPLETED
        assert terminal.reason is None

    @pytest.mark.asyncio
    async def test_an_unproven_verification_refuses_to_claim_success(self) -> None:
        """UNKNOWN means the fact was never established, so it must not read as a completion."""
        nodes = build_lifecycle_nodes()
        state = make_state(verification={"status": VerificationStatus.UNKNOWN})
        update = await nodes[Node.FINALIZE]({"state": state})

        terminal = update["decision"].terminal
        assert terminal is not None
        assert terminal.status is RunStatus.SAFE_STOP
        assert terminal.reason is SafeStopReason.VERIFICATION_UNKNOWN

    @pytest.mark.asyncio
    async def test_an_already_terminal_run_reports_no_new_decision(self) -> None:
        """Restating a status would mean inventing the reason it stopped."""
        nodes = build_lifecycle_nodes()
        state = make_state(status=RunStatus.COMPLETED)
        update = await nodes[Node.FINALIZE]({"state": state})

        assert update["decision"].terminal is None

    @pytest.mark.asyncio
    async def test_waiting_approval_requires_a_real_pending_reference(self) -> None:
        nodes = build_lifecycle_nodes()
        state = eligible_state(
            approval={"approval_request_id": "approval-001", "status": "PENDING"}
        )

        update = await nodes[Node.WAITING_APPROVAL]({"state": state})

        terminal = update["decision"].terminal
        assert terminal is not None
        assert terminal.status is RunStatus.WAITING_APPROVAL
        assert terminal.reason is None
        assert update["state"].is_terminal is False

    @pytest.mark.asyncio
    async def test_waiting_approval_refuses_a_missing_authoritative_reference(self) -> None:
        nodes = build_lifecycle_nodes()
        with pytest.raises(ValueError, match="PENDING authoritative approval reference"):
            await nodes[Node.WAITING_APPROVAL]({"state": eligible_state()})

    @pytest.mark.asyncio
    async def test_safe_stop_carries_the_reason_the_node_declared(self) -> None:
        nodes = build_lifecycle_nodes()
        decision = Decision(safe_stop_reason=SafeStopReason.WRITE_INTENT_NOT_DURABLE)
        update = await nodes[Node.SAFE_STOP]({"state": eligible_state(), "decision": decision})

        terminal = update["decision"].terminal
        assert terminal is not None
        assert terminal.reason is SafeStopReason.WRITE_INTENT_NOT_DURABLE

    @pytest.mark.asyncio
    async def test_reaching_safe_stop_without_a_reason_fails_loudly(self) -> None:
        """An incomplete routing table must not turn into a plausible-looking reason code."""
        nodes = build_lifecycle_nodes()

        with pytest.raises(ValueError, match="without a declared safety reason"):
            await nodes[Node.SAFE_STOP]({"state": make_state()})

    @pytest.mark.asyncio
    async def test_waiting_user_ends_the_invocation_but_not_the_run(self) -> None:
        nodes = build_lifecycle_nodes()
        update = await nodes[Node.WAITING_USER]({"state": make_state()})

        terminal = update["decision"].terminal
        assert terminal is not None
        assert terminal.status is RunStatus.WAITING_USER
        assert terminal.reason is None
        # The run stays resumable, which is the whole point of not calling it terminal.
        assert update["state"].is_terminal is False
