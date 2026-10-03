"""Turn one Tool call into the row T017 keeps as cross-service evidence.

The row is built **where the call happened**, from the envelope the Tool actually returned. Nothing
here reconstructs a call from Agent state afterwards: state keeps a compact summary, and a summary
is exactly the wrong input for evidence. A latency that was never measured would be written as zero
and a missing correlation id would have to be invented - and invented evidence is worse than absent
evidence, because it can be reconciled against.

`input_summary` is passed in rather than derived, because only the call site knows which order it
asked about. It must never carry a credential: `ToolTraceRecord` guards both summaries and raises
rather than redacting, so a mistake fails closed at construction.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID, uuid4

from app.tools.models import ToolEnvelope, ToolRisk
from app.tools.registry import ToolRegistry
from app.trace.checkpoint import RiskLevel, ToolTraceRecord, ToolTraceStatus

__all__ = [
    "ToolCallFacts",
    "TraceSink",
    "TraceWriter",
    "bind_risk",
    "build_trace_record",
    "report_tool_call",
    "risk_level_for",
    "status_for",
]

#: Java's normalized "we do not know whether it happened" code (T029). It is a TIMEOUT rather than
#: an ERROR because the request may still be in flight on the other side.
_UNKNOWN_OUTCOME_ERROR_CODE = "WRITE_TIMEOUT_UNKNOWN"

#: Prefix for a correlation id minted here. Self-describing on purpose: a reader of the trace table
#: can tell "this call has no cross-service link" from "we recorded a link", which a random id that
#: merely looked plausible could not tell them.
_LOCAL_TRACE_PREFIX = "local-"

#: Machine-readable companion to the prefix, for anything that selects rows rather than reads them.
_TRACE_SOURCE_KEY = "traceIdSource"
_LOCAL_TRACE_SOURCE = "LOCAL"

#: A tool name the registry does not know is treated as HIGH. Overstating risk produces a review
#: prompt; understating it produces false reassurance, so the fallback is the loud one.
_UNKNOWN_TOOL_RISK = RiskLevel.HIGH


@dataclass(frozen=True)
class ToolCallFacts:
    """What a call site knows the moment a Tool returns: which call, and what came back.

    Deliberately facts rather than a finished record. The run id belongs to the caller's session,
    and the risk classification belongs to the registry - neither is knowledge the call site has.
    """

    step_index: int
    tool_name: str
    envelope: ToolEnvelope[Any]
    input_summary: dict[str, Any] = field(default_factory=dict)


#: How a call site reports one finished Tool call. Synchronous because the store's writer is, and a
#: sink that cannot block is one fewer thing to reason about on the money path.
#:
#: Call sites do **not** classify risk: the registry owns that, so a signature asking them for it
#: would be asking for knowledge they do not have.
type TraceSink = Callable[[ToolCallFacts], None]

#: The session-side counterpart: facts plus the classification the registry supplied.
type TraceWriter = Callable[[ToolCallFacts, ToolRisk | None], None]


def report_tool_call(
    sink: TraceSink | None,
    *,
    step_index: int,
    tool_name: str,
    envelope: ToolEnvelope[Any],
    input_summary: dict[str, Any] | None = None,
) -> None:
    """Report one finished call, or do nothing when no sink is wired.

    Optional on purpose: the modules that call Tools are also used by the dev harnesses and by unit
    tests, and "no sink" must mean "no trace row" rather than "crash". Production always wires one -
    ``build_agent_graph`` will not build without it.
    """
    if sink is None:
        return
    sink(
        ToolCallFacts(
            step_index=step_index,
            tool_name=tool_name,
            envelope=envelope,
            input_summary=input_summary or {},
        )
    )


def bind_risk(writer: TraceWriter, registry: ToolRegistry) -> TraceSink:
    """Turn a session-side writer into the sink a call site needs.

    An unregistered tool name classifies as ``None``, which the risk mapper already turns into HIGH.
    It deliberately does not propagate the registry's refusal: refusing to *classify* a call must
    not turn into refusing to *record* it, because the record is what a reviewer would use to find
    out that something unregistered was called at all.
    """

    def sink(facts: ToolCallFacts) -> None:
        try:
            risk: ToolRisk | None = registry.get(facts.tool_name).risk
        except ValueError:
            risk = None
        writer(facts, risk)

    return sink


def risk_level_for(risk: ToolRisk | None) -> RiskLevel:
    """Map registered tool risk onto the trace table's vocabulary, failing closed."""
    if risk is ToolRisk.HIGH_WRITE:
        return RiskLevel.HIGH
    if risk is ToolRisk.READ_PRIVACY_MEDIUM:
        return RiskLevel.MEDIUM
    return _UNKNOWN_TOOL_RISK


def status_for(envelope: ToolEnvelope[Any]) -> ToolTraceStatus:
    """How the call ended, from the envelope alone.

    ``DENIED`` is never produced here: a denied call never reached the Tool layer, so it has no
    envelope to read. That is a separate report from the place that did the denying.
    """
    if envelope.success:
        return ToolTraceStatus.SUCCESS
    if envelope.error_code == _UNKNOWN_OUTCOME_ERROR_CODE:
        return ToolTraceStatus.TIMEOUT
    return ToolTraceStatus.ERROR


def build_trace_record(
    *,
    run_id: UUID,
    facts: ToolCallFacts,
    risk: ToolRisk | None,
) -> ToolTraceRecord:
    """Build the evidence row for one finished call.

    ``latency_ms`` is the Tool's own measurement and ``trace_id`` is the backend's correlation id
    when it gave one. When it did not, this mints a local id and says so in the output summary
    rather than leaving the column empty: an absent id and "no id was returned" are different facts,
    and the trace table is where that difference has to survive.
    """
    envelope = facts.envelope
    output_summary: dict[str, Any] = {}
    if envelope.trace_id is None:
        output_summary[_TRACE_SOURCE_KEY] = _LOCAL_TRACE_SOURCE

    return ToolTraceRecord(
        run_id=run_id,
        step_index=facts.step_index,
        tool_name=facts.tool_name,
        risk_level=risk_level_for(risk),
        status=status_for(envelope),
        trace_id=envelope.trace_id or f"{_LOCAL_TRACE_PREFIX}{uuid4().hex}",
        input_summary=facts.input_summary,
        output_summary=output_summary,
        error_code=envelope.error_code,
        retryable=envelope.retryable,
        latency_ms=envelope.latency_ms,
    )
