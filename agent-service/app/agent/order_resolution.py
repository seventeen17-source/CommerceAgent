"""Single-candidate order resolution for T030.

Language extraction may suggest an order id, but only an ownership-validated Tool read may turn
that clue into resolved_order_id. Multiple candidates are never guessed; clarification is a
later user story (T043+).
"""

from __future__ import annotations

from enum import StrEnum
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.agent.request_understanding import UnderstoodRequest
from app.agent.state import Identifier
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
) -> OrderResolution:
    """Resolve one order without trusting a model-provided id as authority."""
    if understood.mentioned_order_id is not None:
        return await _confirm_candidate(understood.mentioned_order_id, tools=tools)

    listed = await tools.list_user_orders()
    if not listed.success:
        return OrderResolution(
            status=OrderResolutionStatus.UNRESOLVED,
            error_code=listed.errorCode,
            retryable=listed.retryable,
            trace_id=listed.traceId,
        )

    assert listed.data is not None
    candidate_ids = [order.order_id for order in listed.data]
    if not candidate_ids:
        return OrderResolution(status=OrderResolutionStatus.UNRESOLVED)
    if len(candidate_ids) > 1:
        return OrderResolution(
            status=OrderResolutionStatus.AMBIGUOUS,
            candidate_order_ids=candidate_ids,
        )

    return await _confirm_candidate(candidate_ids[0], tools=tools)


async def _confirm_candidate(order_id: str, *, tools: OrderReadTools) -> OrderResolution:
    confirmed = await tools.get_order(order_id)
    if not confirmed.success:
        return OrderResolution(
            status=OrderResolutionStatus.UNRESOLVED,
            candidate_order_ids=[order_id],
            error_code=confirmed.errorCode,
            retryable=confirmed.retryable,
            trace_id=confirmed.traceId,
        )

    assert confirmed.data is not None
    return OrderResolution(
        status=OrderResolutionStatus.RESOLVED,
        candidate_order_ids=[order_id],
        resolved_order_id=confirmed.data.order_id,
        order=confirmed.data,
        trace_id=confirmed.traceId,
    )
