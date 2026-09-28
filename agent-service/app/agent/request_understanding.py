"""Structured output contract for T030 request understanding.

This module defines what the language-understanding step may say about untrusted user text.
It deliberately does not contain business authorization fields such as refund amount,
eligibility, approval, endpoint, URL, or user identity.

A mentioned order id is only a clue extracted from text. It is not an authoritative
``AgentState.resolved_order_id`` until a typed Tool reaches Java and ownership is confirmed.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from app.agent.state import Identifier

__all__ = ["RequestIntent", "UnderstoodRequest"]


class RequestIntent(StrEnum):
    """Intent values owned by the Python Agent orchestration layer."""

    REFUND_REQUEST = "REFUND_REQUEST"
    UNKNOWN = "UNKNOWN"


class UnderstoodRequest(BaseModel):
    """Narrow, non-authoritative interpretation of one user request.

    The model may identify the user's goal and extract an order-id-shaped clue. It may not
    decide whether the request is allowed, choose a refund amount, or select arbitrary backend
    capabilities.
    """

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    intent: RequestIntent
    mentions_logistics_problem: bool = Field(alias="mentionsLogisticsProblem")
    mentioned_order_id: Identifier | None = Field(default=None, alias="mentionedOrderId")
