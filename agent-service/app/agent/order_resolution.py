"""Single-candidate order resolution for T030.

Language extraction may suggest an order id, but only an ownership-validated Tool read may turn
that clue into resolved_order_id. Multiple candidates are never guessed; clarification is a
later user story (T043+).
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.agent.request_understanding import UnderstoodRequest
from app.agent.state import Identifier, ToolHistoryEntry
from app.agent.tool_tracing import TraceSink, report_tool_call
from app.clients.models import OrderSnapshot, OrderSummary
from app.tools.models import ToolEnvelope

__all__ = [
    "OrderReadTools",
    "OrderResolution",
    "OrderResolutionStatus",
    "resolve_single_order",
]


class OrderResolutionStatus(StrEnum):
    """Resolution states owned by the Agent orchestration layer."""

    RESOLVED = "RESOLVED"
    UNRESOLVED = "UNRESOLVED"
    AMBIGUOUS = "AMBIGUOUS"


class OrderResolution(BaseModel):
    """Result of resolving at most one authoritative order."""

    model_config = ConfigDict(extra="forbid")

    status: OrderResolutionStatus
    candidate_order_ids: list[Identifier] = Field(default_factory=list)
    resolved_order_id: Identifier | None = None
    order: OrderSnapshot | None = None
    error_code: str | None = Field(default=None, max_length=100)
    retryable: bool = False
    trace_id: str | None = Field(default=None, max_length=128)
    #: What was read, in order. Control-plane only - this model is never persisted - so it costs no
    #: payload bytes, and it is what lets the node put these reads into the run's own history.
    history: list[ToolHistoryEntry] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_resolution_shape(self) -> OrderResolution:
        if self.status is OrderResolutionStatus.RESOLVED:
            if self.resolved_order_id is None or self.order is None:
                raise ValueError("RESOLVED requires an authoritative order")
            if self.order.order_id != self.resolved_order_id:
                raise ValueError("resolved_order_id must match the authoritative order")
            if self.error_code is not None:
                raise ValueError("RESOLVED cannot carry an error_code")
        elif self.resolved_order_id is not None or self.order is not None:
            raise ValueError("only RESOLVED may carry an authoritative order")

        if self.status is OrderResolutionStatus.AMBIGUOUS and len(self.candidate_order_ids) < 2:
            raise ValueError("AMBIGUOUS requires at least two candidates")
        return self


class OrderReadTools(Protocol):
    """Only the two T029 read capabilities needed by order resolution."""

    async def list_user_orders(self) -> ToolEnvelope[list[OrderSummary]]:
        """List orders visible to the authenticated customer."""
        ...

    async def get_order(self, order_id: str) -> ToolEnvelope[OrderSnapshot]:
        """Read one order through Java ownership validation."""
        ...


async def resolve_single_order(
    understood: UnderstoodRequest,
    *,
    tools: OrderReadTools,
    step_index: int = 0,
    record_trace: TraceSink | None = None,
) -> OrderResolution:
    """Resolve one order without trusting a model-provided id as authority.

    Both reads are recorded, because both are Java requests a reviewer may need to correlate: a
    compact entry for the run's own history, and the envelope handed to ``record_trace`` while it
    still exists. Nothing here decides what a failure *means* - the caller routes; this reports.
    """
    if understood.mentioned_order_id is not None:
        return await _confirm_candidate(
            understood.mentioned_order_id,
            tools=tools,
            step_index=step_index,
            record_trace=record_trace,
        )

    listed = await tools.list_user_orders()
    listed_entry = _history_entry(
        step_index=step_index, tool_name="list_user_orders", result=listed
    )
    report_tool_call(
        record_trace,
        step_index=step_index,
        tool_name="list_user_orders",
        envelope=listed,
    )
    if not listed.success:
        return OrderResolution(
            status=OrderResolutionStatus.UNRESOLVED,
            error_code=listed.error_code,
            retryable=listed.retryable,
            trace_id=listed.trace_id,
            history=[listed_entry],
        )

    listed_orders = listed.data
    if listed_orders is None:
        raise ValueError("successful list_user_orders Tool result is missing data")
    candidate_ids = [order.order_id for order in listed_orders]
    if not candidate_ids:
        return OrderResolution(status=OrderResolutionStatus.UNRESOLVED, history=[listed_entry])
    if len(candidate_ids) > 1:
        return OrderResolution(
            status=OrderResolutionStatus.AMBIGUOUS,
            candidate_order_ids=candidate_ids,
            history=[listed_entry],
        )

    return await _confirm_candidate(
        candidate_ids[0],
        tools=tools,
        step_index=step_index + 1,
        record_trace=record_trace,
        prior_history=[listed_entry],
    )


async def _confirm_candidate(
    order_id: str,
    *,
    tools: OrderReadTools,
    step_index: int = 0,
    record_trace: TraceSink | None = None,
    prior_history: list[ToolHistoryEntry] | None = None,
) -> OrderResolution:
    leading = list(prior_history or [])
    confirmed = await tools.get_order(order_id)
    confirmed_entry = _history_entry(step_index=step_index, tool_name="get_order", result=confirmed)
    report_tool_call(
        record_trace,
        step_index=step_index,
        tool_name="get_order",
        envelope=confirmed,
    )
    if not confirmed.success:
        return OrderResolution(
            status=OrderResolutionStatus.UNRESOLVED,
            candidate_order_ids=[order_id],
            error_code=confirmed.error_code,
            retryable=confirmed.retryable,
            trace_id=confirmed.trace_id,
            history=[*leading, confirmed_entry],
        )

    confirmed_order = confirmed.data
    if confirmed_order is None:
        raise ValueError("successful get_order Tool result is missing data")
    return OrderResolution(
        status=OrderResolutionStatus.RESOLVED,
        candidate_order_ids=[order_id],
        resolved_order_id=confirmed_order.order_id,
        order=confirmed_order,
        trace_id=confirmed.trace_id,
        history=[*leading, confirmed_entry],
    )


def _history_entry(
    *,
    step_index: int,
    tool_name: str,
    result: ToolEnvelope[Any],
) -> ToolHistoryEntry:
    """The state-side sibling of a trace row: compact, and never a substitute for the row."""
    return ToolHistoryEntry(
        step_index=step_index,
        tool_name=tool_name,
        success=result.success,
        error_code=result.error_code,
        retryable=result.retryable,
        trace_id=result.trace_id,
    )
