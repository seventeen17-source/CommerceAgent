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

from app.agent.evidence_execution import EvidenceReadTools
from app.agent.evidence_routing import EvidenceDecisionModel
from app.agent.graph import GraphNode, GraphState, GraphUpdate
from app.agent.order_resolution import OrderReadTools, resolve_single_order
from app.agent.request_understanding import RequestUnderstandingModel, understand_request
from app.agent.routing import Decision, Node, SafeStopReason
from app.agent.state import AgentState, advance
from app.tools.registry import ToolRegistry

__all__ = ["GraphDeps", "build_read_nodes", "spend_one_step"]


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
