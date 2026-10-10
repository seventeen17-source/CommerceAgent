"""Assemble the T032 graph for one real invocation.

The graph is a pure function of its dependencies, and this module is the one place where they are
built and bound: the caller's credential goes into the Tool layer, the model comes from settings,
and the only per-run piece is the session that persists the walk.

``CommerceTools`` is one authenticated facade for orders, evidence, eligibility,
approvals, protected writes, after-sales reads, and the manual support-ticket handoff.
They are all the same
authenticated HTTP facade, so the credential is bound in exactly one object - there is no second
place for it to leak from, and no second place for it to drift. That one object satisfies the six
narrow protocols through structural typing; mypy checks the wiring rather than a runtime cast.

Assembling per request is also on purpose. A shared graph object would have to hold one caller's
credential, which is the same mistake as caching a database connection with a user's permissions.
"""

from __future__ import annotations

from app.agent.graph import CompiledGraph, build_graph
from app.agent.nodes import (
    GraphDeps,
    PersistWriteIntent,
    build_approval_nodes,
    build_evidence_nodes,
    build_lifecycle_nodes,
    build_read_nodes,
    build_write_nodes,
)
from app.agent.openai_evidence_routing import OpenAICompatibleEvidenceDecisionModel
from app.agent.openai_request_understanding import OpenAICompatibleRequestUnderstandingModel
from app.agent.tool_tracing import TraceWriter, bind_risk
from app.llm.openai_compatible import OpenAICompatibleJsonClient
from app.tools import CommerceTools, ToolRegistry

__all__ = ["build_agent_graph"]


def build_agent_graph(
    *,
    tools: CommerceTools,
    model_client: OpenAICompatibleJsonClient,
    persist_intent: PersistWriteIntent,
    record_trace: TraceWriter,
) -> CompiledGraph:
    """Build the production graph: every dependency bound, every node present.

    Two dependencies come from the run rather than from the request, and both are required here so a
    production assembly cannot quietly go without them: ``persist_intent`` makes a write intent
    durable before the request that spends money is sent, and ``record_trace`` records every Tool
    call while its envelope still exists. Risk classification is bound below rather than asked of
    the call sites, because the registry is what knows it.
    """
    registry = ToolRegistry(tools=tools)
    deps = GraphDeps(
        understanding=OpenAICompatibleRequestUnderstandingModel(model_client),
        orders=tools,
        evidence_model=OpenAICompatibleEvidenceDecisionModel(model_client),
        evidence=tools,
        registry=registry,
        eligibility=tools,
        approvals=tools,
        writes=tools,
        after_sales=tools,
        persist_intent=persist_intent,
        record_trace=bind_risk(record_trace, registry),
    )
    return build_graph(
        {
            **build_read_nodes(deps),
            **build_evidence_nodes(deps),
            **build_approval_nodes(deps),
            **build_write_nodes(deps),
            **build_lifecycle_nodes(tools, deps.record_trace),
        }
    )
