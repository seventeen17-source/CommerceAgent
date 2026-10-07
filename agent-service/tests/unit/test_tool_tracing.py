"""Unit tests for the three decisions the tool-trace row depends on.

Each test pins a decision that would otherwise be invisible in the row itself: the latency comes
from the Tool rather than from nothing, a missing correlation id is labelled instead of invented,
and an unknown tool is treated as riskier rather than safer.
"""

from __future__ import annotations

import re
from typing import Any
from uuid import uuid4

from app.agent.tool_tracing import ToolCallFacts, build_trace_record, risk_level_for, status_for
from app.tools.models import ToolEnvelope, ToolRisk
from app.trace.checkpoint import RiskLevel, ToolTraceStatus

TRACE_ID_PATTERN = re.compile(r"^[A-Za-z0-9._-]{8,128}$")


def envelope(**overrides: Any) -> ToolEnvelope[Any]:
    """A realistic successful Tool result: Java answered, with a correlation id and a latency."""
    values: dict[str, Any] = {
        "success": True,
        "data": {"orderId": "order-001"},
        "latencyMs": 137,
        "traceId": "java-trace-0001",
    }
    values.update(overrides)
    return ToolEnvelope[Any].model_validate(values)


def facts(**overrides: Any) -> ToolCallFacts:
    values: dict[str, Any] = {
        "step_index": 3,
        "tool_name": "get_logistics",
        "envelope": envelope(),
        "input_summary": {"orderId": "order-001"},
    }
    values.update(overrides)
    return ToolCallFacts(**values)


def record(**overrides: Any):
    values: dict[str, Any] = {"run_id": uuid4(), "facts": facts(), "risk": None}
    values.update(overrides)
    return build_trace_record(**values)


def test_the_latency_is_the_tools_measurement_and_not_a_default() -> None:
    """A zero here would read as "instant" in the trace table, which is a claim nobody made."""
    assert record().latency_ms == 137


def test_a_backend_correlation_id_is_kept_as_it_arrived() -> None:
    built = record()

    assert built.trace_id == "java-trace-0001"
    assert built.output_summary == {}


def test_a_missing_correlation_id_is_labelled_rather_than_invented() -> None:
    """An absent id and "no id was returned" are different facts; the row has to keep that."""
    built = record(facts=facts(envelope=envelope(traceId=None)))

    assert built.trace_id.startswith("local-")
    assert TRACE_ID_PATTERN.match(built.trace_id) is not None
    assert built.output_summary == {"traceIdSource": "LOCAL"}


def test_each_locally_minted_id_is_distinct() -> None:
    missing = facts(envelope=envelope(traceId=None))

    assert record(facts=missing).trace_id != record(facts=missing).trace_id


def test_an_unknown_tool_is_riskier_not_safer() -> None:
    assert risk_level_for(ToolRisk.HIGH_WRITE) is RiskLevel.HIGH
    assert risk_level_for(ToolRisk.READ_PRIVACY_MEDIUM) is RiskLevel.MEDIUM
    assert risk_level_for(None) is RiskLevel.HIGH
    assert record(risk=None).risk_level is RiskLevel.HIGH


def test_an_unknown_write_outcome_is_a_timeout_rather_than_an_error() -> None:
    """The request may still be in flight, so "ERROR" would state something we do not know."""
    unknown = envelope(success=False, data=None, errorCode="WRITE_TIMEOUT_UNKNOWN", retryable=False)

    assert status_for(unknown) is ToolTraceStatus.TIMEOUT
    built = record(facts=facts(envelope=unknown))
    assert built.status is ToolTraceStatus.TIMEOUT
    assert built.retryable is False
    assert built.error_code == "WRITE_TIMEOUT_UNKNOWN"


def test_a_plain_failure_is_an_error_and_a_success_is_a_success() -> None:
    rejected = envelope(success=False, data=None, errorCode="ORDER_NOT_FOUND")

    assert status_for(rejected) is ToolTraceStatus.ERROR
    assert status_for(envelope()) is ToolTraceStatus.SUCCESS


def test_the_call_site_supplies_the_summary_it_can_actually_vouch_for() -> None:
    built = record(facts=facts(input_summary={"orderId": "order-002", "reasonCode": "LOGISTICS"}))

    assert built.input_summary == {"orderId": "order-002", "reasonCode": "LOGISTICS"}
    assert built.step_index == 3
    assert built.tool_name == "get_logistics"
