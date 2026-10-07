"""Explicit LangGraph assembly for the T032 runtime.

The graph owns control flow only: which node runs next, and when the run must stop. It does **not**
own business facts (Java does) and does **not** own durable state (``RunStore`` does). Each node
returns a rebuilt ``AgentState`` plus the invocation control-plane facts, and routing decides the
next edge from those same facts - never from model text.

``compile(checkpointer=None)`` is deliberate. LangGraph's own checkpointer would add a second answer
to "what is this run's state", alongside ``agent.agent_runs``, and the accepted T017 store already
owns that answer (row lock + ``expected_version`` CAS, owner scoping, retention). Durability here is
an explicit call at a node boundary, not a framework side effect.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
from typing import Any, Final, TypedDict, cast

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from app.agent.order_resolution import OrderResolution
from app.agent.request_understanding import UnderstoodRequest
from app.agent.routing import (
    Decision,
    Node,
    route_after_decision,
    route_after_eligibility,
    route_after_execute,
    route_after_resolve_order,
    route_after_understand,
    route_after_write,
)
from app.agent.state import AgentState

__all__ = ["CompiledGraph", "GraphNode", "GraphState", "GraphUpdate", "build_graph"]


class GraphState(TypedDict):
    """Channels the graph carries between nodes.

    ``state`` is the durable payload: every change goes through ``AgentState`` validation, so the
    model's own invariants keep applying inside the graph. The other three are **invocation
    control-plane** facts - they are re-derived on resume and never persisted, because persisting a
    model's interpretation next to authoritative facts is how an interpretation starts looking like
    evidence. What is durable about "where we are" is the run row's ``current_node`` /
    ``next_action`` / ``version``.
    """

    state: AgentState
    decision: Decision
    understood: UnderstoodRequest | None
    resolution: OrderResolution | None


class GraphUpdate(TypedDict, total=False):
    """The channels a node changed; LangGraph merges only the keys that are present."""

    state: AgentState
    decision: Decision
    understood: UnderstoodRequest | None
    resolution: OrderResolution | None


#: A node takes the accumulated graph state and returns the channels it changed.
GraphNode = Callable[[GraphState], Awaitable[GraphUpdate]]

#: A compiled graph over our channels: ``(state, context, input, output)``. Context is unused
#: because dependencies are injected through the ``build_*_nodes`` closures rather than a runtime
#: object, which keeps a node's reach visible in one place instead of looked up at call time.
type CompiledGraph = CompiledStateGraph[GraphState, None, GraphState, GraphState]

#: The router that owns each conditional edge: one place to read "which function decides this".
_ROUTERS: Final[dict[Node, Callable[[AgentState, Decision | None], Node]]] = {
    Node.UNDERSTAND: route_after_understand,
    Node.RESOLVE_ORDER: route_after_resolve_order,
    Node.DECIDE_EVIDENCE: route_after_decision,
    Node.EXECUTE_EVIDENCE: route_after_execute,
    Node.CHECK_ELIGIBILITY: route_after_eligibility,
    Node.REFUND_WRITE: route_after_write,
    Node.RETURN_WRITE: route_after_write,
}

#: Allowed targets per conditional edge. Declared explicitly rather than derived, so the topology is
#: readable and a router that returns something unexpected fails at compile time instead of
#: silently reaching a node the design never allowed.
_CONDITIONAL_TARGETS: Final[dict[Node, frozenset[Node]]] = {
    Node.UNDERSTAND: frozenset(
        {Node.RESOLVE_ORDER, Node.WAITING_USER, Node.SAFE_STOP, Node.FINALIZE}
    ),
    Node.RESOLVE_ORDER: frozenset(
        {Node.DECIDE_EVIDENCE, Node.WAITING_USER, Node.SAFE_STOP, Node.FINALIZE}
    ),
    Node.DECIDE_EVIDENCE: frozenset(
        {Node.EXECUTE_EVIDENCE, Node.CHECK_ELIGIBILITY, Node.SAFE_STOP, Node.FINALIZE}
    ),
    Node.EXECUTE_EVIDENCE: frozenset({Node.DECIDE_EVIDENCE, Node.EXECUTE_EVIDENCE, Node.SAFE_STOP}),
    Node.CHECK_ELIGIBILITY: frozenset(
        {
            Node.REFUND_WRITE,
            Node.RETURN_WRITE,
            Node.CHECK_ELIGIBILITY,
            Node.FINALIZE,
            Node.SAFE_STOP,
        }
    ),
    Node.REFUND_WRITE: frozenset({Node.VERIFY, Node.FINALIZE, Node.SAFE_STOP}),
    # T041: the return write leaves through the same doors as the refund write -- verification, a
    # quiet finish, or a refusal. It has no money to lose, but it still must never finish on the
    # strength of its own response alone, so VERIFY is on the edge list for exactly the same reason.
    Node.RETURN_WRITE: frozenset({Node.VERIFY, Node.FINALIZE, Node.SAFE_STOP}),
}

#: Nodes that end one invocation of the graph. ``waiting_user`` and ``safe_stop`` also end it: a
#: waiting run is resumed later by the API, and a refused run must not quietly continue.
_TERMINAL: Final[frozenset[Node]] = frozenset({Node.FINALIZE, Node.WAITING_USER, Node.SAFE_STOP})


def _edge(router: Callable[[AgentState, Decision | None], Node]) -> Callable[[GraphState], Node]:
    """Adapt a pure router to LangGraph's conditional-edge signature."""

    def decide(graph: GraphState) -> Node:
        return router(graph["state"], graph.get("decision"))

    return decide


def build_graph(nodes: Mapping[Node, GraphNode]) -> CompiledGraph:
    """Wire the topology around the supplied node implementations.

    Every node the routers can reach must be supplied, and an incomplete map is rejected up front.
    That is the point of taking the map as an argument: the assembly is data, so a missing node is a
    startup error rather than a run that dies halfway through a money-moving flow.
    """
    missing = sorted(node.value for node in Node if node not in nodes)
    if missing:
        raise ValueError(f"graph assembly is missing nodes: {missing}")

    graph = StateGraph(GraphState)
    for node, implementation in nodes.items():
        # langgraph types a node as a union of call-shape protocols whose contravariant parameter
        # mypy cannot infer from our plain `GraphNode` alias. `GraphNode` still constrains every
        # caller of this function; the cast is confined to this one framework call.
        graph.add_node(node, cast(Any, implementation))

    graph.add_edge(START, Node.UNDERSTAND)
    for source, router in _ROUTERS.items():
        graph.add_conditional_edges(
            source, _edge(router), {target: target for target in _CONDITIONAL_TARGETS[source]}
        )

    # The evidence loop is a conditional edge too: after a read the run either deliberates again or
    # retries the read it already authorized, and that choice belongs to a router, not to the node.
    # Verification never routes anywhere else: the terminal status is derived from the verified
    # facts by the finalize node, so success and failure leave through the same door.
    graph.add_edge(Node.VERIFY, Node.FINALIZE)

    for node in _TERMINAL:
        graph.add_edge(node, END)

    return graph.compile()
