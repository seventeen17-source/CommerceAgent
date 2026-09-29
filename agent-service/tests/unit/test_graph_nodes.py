"""Unit tests for the T032 read-stage nodes and the assembled graph topology.

`build_graph` takes a node map, so these tests hand it the two real nodes plus recording stand-ins
for the stages that land in later steps. That makes the *path* the routers choose assertable - which
is the property worth pinning here: a node is cheap to re-read, a wrong edge is not.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import pytest

from app.agent.evidence_routing import (
    EvidenceAction,
    EvidenceGuardDecision,
    EvidenceGuardStatus,
)
from app.agent.graph import GraphNode, GraphState, GraphUpdate, build_graph
from app.agent.nodes import GraphDeps, build_evidence_nodes, build_read_nodes
from app.agent.order_resolution import OrderResolution, OrderResolutionStatus
from app.agent.request_understanding import UnderstoodRequest
from app.agent.routing import Decision, Node, SafeStopReason, route_after_decision
from app.agent.state import AgentState, advance
from app.clients.models import LogisticsSnapshot, OrderSnapshot, OrderSummary
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


def make_deps(*, understanding: Any, orders: Any) -> GraphDeps:
    unused = UnusedDependency()
    return GraphDeps(
        understanding=understanding,
        orders=orders,
        evidence_model=unused,
        evidence=unused,
        registry=ToolRegistry(),
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
    return GraphDeps(
        understanding=FakeUnderstanding(),
        orders=ConfirmedOrderTools("order-001"),
        evidence_model=model,
        evidence=tools,
        registry=ToolRegistry(),
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
