from __future__ import annotations

from typing import Any, Literal, TypedDict


RunStatus = Literal[
    "RUNNING",
    "WAITING_USER",
    "WAITING_APPROVAL",
    "COMPLETED",
    "ESCALATED",
    "FAILED",
    "SAFE_STOP",
]


class ToolCallRecord(TypedDict, total=False):
    step: int
    tool_name: str
    success: bool
    error_code: str | None
    retryable: bool
    latency_ms: int
    trace_id: str | None


class AgentState(TypedDict, total=False):
    run_id: str
    user_id: str
    user_message: str
    intent: str | None
    candidate_order_ids: list[str]
    resolved_order_id: str | None
    order_snapshot: dict[str, Any] | None
    logistics_snapshot: dict[str, Any] | None
    policy_evidence: list[dict[str, Any]]
    eligibility: dict[str, Any] | None
    next_action: str | None
    approval_request_id: str | None
    approval_status: str | None
    write_result: dict[str, Any] | None
    verification_result: dict[str, Any] | None
    tool_history: list[ToolCallRecord]
    evidence: dict[str, Any]
    step_count: int
    retry_count: int
    status: RunStatus
    error_code: str | None
    final_message: str | None
