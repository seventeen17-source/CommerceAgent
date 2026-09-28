"""Structured output contract for T030 request understanding.

This module defines what the language-understanding step may say about untrusted user text.
It deliberately does not contain business authorization fields such as refund amount,
eligibility, approval, endpoint, URL, or user identity.

A mentioned order id is only a clue extracted from text. It is not an authoritative
``AgentState.resolved_order_id`` until a typed Tool reaches Java and ownership is confirmed.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field

from app.agent.state import Identifier

__all__ = [
    "RequestIntent",
    "RequestUnderstandingModel",
    "UnderstoodRequest",
    "understand_request",
]


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


class RequestUnderstandingModel(Protocol):
    """Minimal model boundary used by the request-understanding step.

    The adapter receives only the user's natural-language request. Authentication, principal,
    Java business facts, and tool implementations stay outside the model boundary.
    """

    async def understand_request(self, user_request: str) -> object:
        """Return JSON-like structured output for one user request."""
        ...


async def understand_request(
    user_request: str,
    *,
    model: RequestUnderstandingModel,
) -> UnderstoodRequest:
    """Interpret untrusted language and validate the model structured output.

    This function intentionally does not mutate AgentState. T030 later decides how a validated
    language clue becomes a candidate order, while T032 owns graph-node state transitions.
    """

    raw_output = await model.understand_request(user_request)
    return UnderstoodRequest.model_validate(raw_output)
