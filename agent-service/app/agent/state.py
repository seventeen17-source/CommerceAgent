"""Explicit Agent state for CommerceAgent orchestration.

This module defines the data that graph nodes may read and update while one Agent run is
executing. It deliberately contains no HTTP client, JWT, database, or LangGraph runtime code.

Security boundary:
- Keep only derived principal context (user_id / role), never a raw JWT or credential.
- Store verified business evidence and backend decisions as structured snapshots.
- Persisting/restoring this state is a T017 concern.
"""

from __future__ import annotations

from decimal import Decimal
from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class RunStatus(StrEnum):
    """Lifecycle status shared with the persisted AgentRun model."""

    RUNNING = "RUNNING"
    WAITING_USER = "WAITING_USER"
    WAITING_APPROVAL = "WAITING_APPROVAL"
    COMPLETED = "COMPLETED"
    ESCALATED = "ESCALATED"
    FAILED = "FAILED"
    SAFE_STOP = "SAFE_STOP"


class WriteStatus(StrEnum):
    """State of a business write attempt."""

    NOT_ATTEMPTED = "NOT_ATTEMPTED"
    PENDING = "PENDING"
    UNKNOWN = "UNKNOWN"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"


class VerificationStatus(StrEnum):
    """Result of authoritative write-after-read verification."""

    NOT_RUN = "NOT_RUN"
    PENDING = "PENDING"
    VERIFIED_SUCCESS = "VERIFIED_SUCCESS"
    VERIFIED_FAILURE = "VERIFIED_FAILURE"
    UNKNOWN = "UNKNOWN"


class PrincipalContext(BaseModel):
    """Authenticated identity facts derived by the security layer."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    user_id: str = Field(min_length=1, max_length=64)
    role: str = Field(min_length=1, max_length=32)


class EvidenceItem(BaseModel):
    """One structured, already-observed business fact used by the Agent."""

    model_config = ConfigDict(extra="forbid")

    evidence_type: str = Field(min_length=1, max_length=100)
    source: str = Field(min_length=1, max_length=100)
    data: dict[str, Any] = Field(default_factory=dict)


class EligibilitySnapshot(BaseModel):
    """Deterministic eligibility result returned by the Java backend."""

    model_config = ConfigDict(extra="forbid")

    eligible: bool
    allowed_action: str = Field(min_length=1, max_length=32)
    max_refund_amount: Decimal | None = None
    approval_required: bool
    rule_code: str | None = Field(default=None, max_length=100)
    rule_version: int | None = Field(default=None, ge=1)
    reason_codes: list[str] = Field(default_factory=list)


class ApprovalSnapshot(BaseModel):
    """Authoritative approval reference/state observed from the backend."""

    model_config = ConfigDict(extra="forbid")

    approval_request_id: str | None = Field(default=None, max_length=128)
    status: str | None = Field(default=None, max_length=32)


class ToolHistoryEntry(BaseModel):
    """Compact per-step Tool execution summary kept in Agent state."""

    model_config = ConfigDict(extra="forbid")

    step_index: int = Field(ge=0)
    tool_name: str = Field(min_length=1, max_length=100)
    success: bool
    error_code: str | None = Field(default=None, max_length=100)
    retryable: bool = False
    trace_id: str | None = Field(default=None, max_length=128)


class WriteOutcome(BaseModel):
    """Most recent state-changing action outcome."""

    model_config = ConfigDict(extra="forbid")

    status: WriteStatus = WriteStatus.NOT_ATTEMPTED
    action: str | None = Field(default=None, max_length=100)
    resource_id: str | None = Field(default=None, max_length=128)
    error_code: str | None = Field(default=None, max_length=100)


class VerificationOutcome(BaseModel):
    """Authoritative verification performed after a write attempt."""

    model_config = ConfigDict(extra="forbid")

    status: VerificationStatus = VerificationStatus.NOT_RUN
    resource_id: str | None = Field(default=None, max_length=128)
    details: dict[str, Any] = Field(default_factory=dict)


class AgentState(BaseModel):
    """Single explicit state object shared by all nodes of one Agent run."""

    model_config = ConfigDict(extra="forbid")

    run_id: UUID
    principal: PrincipalContext

    intent: str | None = Field(default=None, max_length=100)
    candidate_order_ids: list[str] = Field(default_factory=list)
    resolved_order_id: str | None = Field(default=None, max_length=64)

    evidence: list[EvidenceItem] = Field(default_factory=list)
    eligibility: EligibilitySnapshot | None = None
    approval: ApprovalSnapshot | None = None
    tool_history: list[ToolHistoryEntry] = Field(default_factory=list)

    step_count: int = Field(default=0, ge=0)
    max_steps: int = Field(default=12, ge=1)
    retry_count: int = Field(default=0, ge=0)
    max_retries: int = Field(default=2, ge=0)

    write: WriteOutcome = Field(default_factory=WriteOutcome)
    verification: VerificationOutcome = Field(default_factory=VerificationOutcome)
    status: RunStatus = RunStatus.RUNNING

    @model_validator(mode="after")
    def validate_budgets(self) -> AgentState:
        """Fail closed if a restored or mutated state already exceeds a safety budget."""
        if self.step_count > self.max_steps:
            raise ValueError("step_count cannot exceed max_steps")
        if self.retry_count > self.max_retries:
            raise ValueError("retry_count cannot exceed max_retries")
        return self

    @property
    def is_terminal(self) -> bool:
        """Whether no automatic graph execution should continue for this run."""
        return self.status in {
            RunStatus.COMPLETED,
            RunStatus.ESCALATED,
            RunStatus.FAILED,
            RunStatus.SAFE_STOP,
        }
