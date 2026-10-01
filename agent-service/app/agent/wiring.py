"""Assemble the T032 graph for one real invocation.

The graph is a pure function of its dependencies, and this module is the one place where they are
built and bound: the caller's credential goes into the Tool layer, the model comes from settings,
and the only per-run piece is the session that persists the walk.

``CommerceTools`` deliberately fills five of the nine dependencies. Orders, evidence, eligibility,
the refund write and the after-sales read are all the same authenticated HTTP client, so the
credential is bound in exactly one object - there is no second place for it to leak from, and no
second place for it to drift. That one object satisfies five protocols is checked by mypy rather
than asserted here.

Assembling per request is also on purpose. A shared graph object would have to hold one caller's
credential, which is the same mistake as caching a database connection with a user's permissions.
"""

from __future__ import annotations

from app.agent.graph import CompiledGraph, build_graph
from app.agent.nodes import (
    GraphDeps,
    PersistWriteIntent,
    build_evidence_nodes,
    build_lifecycle_nodes,
    build_read_nodes,
    build_write_nodes,
)
from app.agent.openai_evidence_routing import OpenAICompatibleEvidenceDecisionModel
from app.agent.openai_request_understanding import OpenAICompatibleRequestUnderstandingModel
from app.llm.openai_compatible import OpenAICompatibleJsonClient
from app.tools import CommerceTools, ToolRegistry

__all__ = ["build_agent_graph"]


def build_agent_graph(
    *,
    tools: CommerceTools,
    model_client: OpenAICompatibleJsonClient,
    persist_intent: PersistWriteIntent,
) -> CompiledGraph:
    """Build the production graph: every dependency bound, every node present.

    ``persist_intent`` is the one dependency that comes from the run rather than from the request:
    it is the seam that makes a write intent durable before the request that spends money is sent,
    so it has to be bound to the session that owns this run's version.
    """
    deps = GraphDeps(
        understanding=OpenAICompatibleRequestUnderstandingModel(model_client),
        orders=tools,
        evidence_model=OpenAICompatibleEvidenceDecisionModel(model_client),
        evidence=tools,
        registry=ToolRegistry(tools=tools),
        eligibility=tools,
        writes=tools,
        after_sales=tools,
        persist_intent=persist_intent,
    )
    return build_graph(
        {
            **build_read_nodes(deps),
            **build_evidence_nodes(deps),
            **build_write_nodes(deps),
            **build_lifecycle_nodes(),
        }
    )
