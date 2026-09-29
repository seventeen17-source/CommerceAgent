"""Node implementations for the T032 graph: the interpret-and-resolve stage.

Each node does exactly three things: spend one step of budget, call one already-accepted capability,
and return a rebuilt state plus the control-plane facts the router needs. Nodes never retry, never
pick the next node, and never write durable state - persistence is the graph wrapper's job (T032
Step 3), so that it happens at node boundaries instead of inside business logic.

Nothing here is model-decided: the model's output is validated into a narrow schema before it
touches a field, and the only field it can influence is the untrusted `user_request` interpretation.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.agent.evidence_execution import EvidenceReadTools, execute_read_evidence
from app.agent.evidence_routing import (
    EvidenceDecisionModel,
    build_evidence_routing_context,
    decide_next_evidence,
    guard_evidence_proposal,
)
from app.agent.graph import GraphNode, GraphState, GraphUpdate
from app.agent.order_resolution import OrderReadTools, resolve_single_order
from app.agent.request_understanding import RequestUnderstandingModel, understand_request
from app.agent.routing import Decision, Node, SafeStopReason
from app.agent.state import AgentState, advance
from app.tools.registry import ToolRegistry

__all__ = ["GraphDeps", "build_evidence_nodes", "build_read_nodes", "spend_one_step"]


@dataclass(frozen=True, slots=True)
class GraphDeps:
    """Everything a read-stage node may call.

    Explicit rather than global so a node's reach is visible in one place, and so tests can pass
    doubles that fail loudly if a node touches a dependency its stage has no business touching.
    """

    understanding: RequestUnderstandingModel
    orders: OrderReadTools
    evidence_model: EvidenceDecisionModel
    evidence: EvidenceReadTools
    registry: ToolRegistry


def spend_one_step(state: AgentState) -> AgentState:
    """Charge the step budget for entering a node.

    Routers check the budget *before* entering, so this cannot exceed ``max_steps``. If it ever does
    - a restored state from an older, more permissive version, say - ``advance()`` raises instead of
    letting the run continue unbudgeted.
    """
    return advance(state, step_count=state.step_count + 1)


def build_read_nodes(deps: GraphDeps) -> dict[Node, GraphNode]:
    """Build the interpret-and-resolve nodes bound to ``deps``."""

    async def understand(graph: GraphState) -> GraphUpdate:
        """Interpret the request into a narrow schema and record the order-id clue, if any.

        ``mentioned_order_id`` lands in ``candidate_order_ids``, never in ``resolved_order_id``: a
        model-supplied id is a clue about which order to ask Java about, not authority over it.
        """
        state = spend_one_step(graph["state"])
        understood = await understand_request(state.user_request, model=deps.understanding)
        clue = understood.mentioned_order_id
        if clue is None:
            moved = advance(state, intent=understood.intent.value)
        else:
            moved = advance(
                state,
                intent=understood.intent.value,
                candidate_order_ids=[clue],
            )
        # The interpretation is carried in the control plane, not the payload: it is re-derived on
        # resume and must never sit next to authoritative facts as if it were one.
        return GraphUpdate(state=moved, decision=Decision(), understood=understood)

    async def resolve_order(graph: GraphState) -> GraphUpdate:
        """Ask Java which single order this request is about, or record why we cannot say."""
        state = spend_one_step(graph["state"])
        understood = graph.get("understood")
        if understood is None:
            # No interpretation in this invocation. Rebuilding one from the payload alone would mean
            # inventing the fields it does not carry, so the run refuses instead of guessing.
            return GraphUpdate(
                state=state,
                decision=Decision(
                    resolution_attempted=True,
                    safe_stop_reason=SafeStopReason.ORDER_UNRESOLVED,
                ),
                resolution=None,
            )

        resolution = await resolve_single_order(understood, tools=deps.orders)
        if resolution.resolved_order_id is None:
            moved = advance(state, candidate_order_ids=list(resolution.candidate_order_ids))
        else:
            moved = advance(
                state,
                candidate_order_ids=list(resolution.candidate_order_ids),
                resolved_order_id=resolution.resolved_order_id,
            )
        return GraphUpdate(
            state=moved,
            decision=Decision(resolution_attempted=True),
            resolution=resolution,
        )

    return {Node.UNDERSTAND: understand, Node.RESOLVE_ORDER: resolve_order}


def build_evidence_nodes(deps: GraphDeps) -> dict[Node, GraphNode]:
    """Build the evidence loop: propose one read, authorize it, execute it.

    The two nodes are split on purpose. ``decide_evidence`` touches the model and no business
    resource; ``execute_evidence`` touches Java and no model. Keeping them apart is what makes "what
    the model proposed" and "what was actually read" separately observable in the trace - merged
    into one node, a denied proposal and a failed read would look identical from outside.
    """

    async def decide_evidence(graph: GraphState) -> GraphUpdate:
        """Ask the model what evidence would help, then let the deterministic guard decide."""
        state = spend_one_step(graph["state"])
        understood = graph.get("understood")
        resolution = graph.get("resolution")
        order = resolution.order if resolution is not None else None
        if understood is None or order is None:
            # Routing needs the interpretation and the authoritative order snapshot, and both are
            # invocation control-plane facts. Rebuilding them here would mean calling a capability
            # that belongs to another node, so the run refuses instead of inventing context.
            return GraphUpdate(
                state=state,
                decision=Decision(safe_stop_reason=SafeStopReason.EVIDENCE_CONTEXT_MISSING),
            )

        context = build_evidence_routing_context(understood, order=order, evidence=state.evidence)
        proposal = await decide_next_evidence(context, model=deps.evidence_model)
        guard = guard_evidence_proposal(
            proposal,
            resolved_order_id=state.resolved_order_id,
            observed_evidence_types={item.evidence_type for item in state.evidence},
            registry=deps.registry,
        )
        return GraphUpdate(state=state, decision=Decision(guard=guard))

    async def execute_evidence(graph: GraphState) -> GraphUpdate:
        """Execute the authorized read, then report the facts the router needs.

        A failed read **never enters ``evidence``** - that slot holds observed facts, and a failure
        is not one. It is recorded in ``tool_history`` instead, so "we tried and it failed" stays
        visible without ever being mistaken for evidence.

        Which failures are worth another attempt comes from the failing layer, not from us: a
        ``retryable`` failure is transient and is retried while the run's retry budget allows, while
        anything else is Java's considered answer and no amount of retrying changes it.

        This node makes **no routing decision**. It reports two facts - whether the attempt
        succeeded, and whether this evidence path is now closed - and ``route_after_decision``
        decides where that leads. Only the router has to change if the topology does.
        """
        state = spend_one_step(graph["state"])
        decision = graph.get("decision")
        guard = decision.guard if decision is not None else None
        if guard is None or state.resolved_order_id is None:
            return GraphUpdate(
                state=state,
                decision=Decision(safe_stop_reason=SafeStopReason.EVIDENCE_CONTEXT_MISSING),
            )

        result = await execute_read_evidence(
            guard,
            resolved_order_id=state.resolved_order_id,
            step_index=state.step_count,
            tools=deps.evidence,
        )
        history = [*state.tool_history, result.history]
        if result.evidence is None:
            if result.history.retryable and state.retry_count < state.max_retries:
                # Consume the run's retry budget. The evidence slot is still empty, so a second
                # proposal for the same read will be authorized again.
                moved = advance(state, retry_count=state.retry_count + 1, tool_history=history)
                return GraphUpdate(state=moved, decision=Decision(guard=guard))
            moved = advance(state, tool_history=history)
            return GraphUpdate(
                state=moved,
                decision=Decision(guard=guard, evidence_path_closed=True),
            )

        moved = advance(
            state,
            tool_history=history,
            evidence=[*state.evidence, result.evidence],
        )
        return GraphUpdate(state=moved, decision=Decision(guard=guard))

    return {Node.DECIDE_EVIDENCE: decide_evidence, Node.EXECUTE_EVIDENCE: execute_evidence}
