"""Shared Tool-facing models for the CommerceAgent capability boundary."""

from __future__ import annotations

from enum import StrEnum
from pydantic import BaseModel, ConfigDict, Field, model_validator

__all__ = ["ToolEnvelope", "ToolRisk"]


class ToolRisk(StrEnum):
    """Deterministic risk metadata for registered Agent capabilities."""

    READ_PRIVACY_MEDIUM = "read_privacy_medium"
    HIGH_WRITE = "high_write"


class ToolEnvelope[T](BaseModel):
    """Stable result shape returned by every registered Agent Tool."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    success: bool
    data: T | None = None
    error_code: str | None = Field(default=None, alias="errorCode")
    retryable: bool = False
    latency_ms: int = Field(alias="latencyMs", ge=0)
    trace_id: str | None = Field(default=None, alias="traceId", min_length=8, max_length=128)

    @model_validator(mode="after")
    def _success_and_failure_are_disjoint(self) -> ToolEnvelope[T]:
        if self.success:
            if self.data is None:
                raise ValueError("successful tool result requires data")
            if self.error_code is not None:
                raise ValueError("successful tool result cannot carry errorCode")
            if self.retryable:
                raise ValueError("successful tool result cannot be retryable")
        else:
            if self.data is not None:
                raise ValueError("failed tool result cannot carry data")
            if self.error_code is None:
                raise ValueError("failed tool result requires errorCode")
        return self
