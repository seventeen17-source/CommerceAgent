"""US5 failure taxonomy and deterministic no-progress circuit breaker.

Tool envelopes are untrusted external signals: retryable=true never authorizes a write retry.
The evidence and eligibility stages are side-effect-free, but even they may only retry
a known transient code within the persisted run's finite retry budget.

The present evidence loop has one authorized operation (get_logistics) with one resolved
order id; the eligibility loop likewise reuses the same order and fixed reason code.
For these narrowly scoped stages, two consecutive failed calls to the same tool are
unambiguously repeated attempts with no new evidence. Do not generalize this detector to
future tools with arbitrary parameter sets without adding request fingerprints to history.
"""

from __future__ import annotations

from typing import Final

from app.agent.state import AgentState, ToolHistoryEntry

__all__ = ["may_retry_read", "normalize_tool_error", "repeated_no_progress"]

#: Keep this list narrow: unrecognized remote codes must fail closed, not inherit a
#: model/provider-provided retryable flag as if it were an authorization.
_TRANSIENT_READ_CODES: Final[frozenset[str]] = frozenset(
    {"DEPENDENCY_TIMEOUT", "DEPENDENCY_UNAVAILABLE", "LOGISTICS_UNAVAILABLE"}
)
#: Stable non-retryable codes relevant to this Agent. Others remain visible in trace,
#: but collapse to INTERNAL_ERROR for this routing policy.
_KNOWN_FAILURE_CODES: Final[frozenset[str]] = _TRANSIENT_READ_CODES | frozenset(
    {
        "AUTH_REQUIRED",
        "ACCESS_DENIED",
        "ORDER_NOT_FOUND",
        "INVALID_PARAMETER",
        "MANUAL_REVIEW_REQUIRED",
        "APPROVAL_REQUIRED",
        "WRITE_TIMEOUT_UNKNOWN",
        "MAX_STEPS_EXCEEDED",
        "REPEATED_NO_PROGRESS",
        "POST_WRITE_VERIFICATION_FAILED",
        "TOOL_NOT_ALLOWED",
        "INTERNAL_ERROR",
    }
)
#: Both stages accept one fixed request per resolved order in the present graph.
_NO_PROGRESS_TOOLS: Final[frozenset[str]] = frozenset(
    {"get_logistics", "check_after_sales_eligibility"}
)


def normalize_tool_error(error_code: str | None) -> str:
    """Classify for branching without rewriting the original error recorded in trace."""
    if error_code in _KNOWN_FAILURE_CODES:
        return error_code
    return "INTERNAL_ERROR"


def may_retry_read(entry: ToolHistoryEntry, state: AgentState) -> bool:
    """Require an explicit known transient read failure AND remaining persisted budget."""
    return (
        not entry.success
        and entry.retryable
        and normalize_tool_error(entry.error_code) in _TRANSIENT_READ_CODES
        and state.retry_count < state.max_retries
    )


def repeated_no_progress(state: AgentState) -> bool:
    """Detect consecutive unsuccessful attempts of the same fixed-argument read.

    This never compares mutable model prose or JSON evidence values, and never counts
    successful calls as progress-free. A success must contribute evidence, so its handling
    remains with the evidence guard and Java eligibility validator.
    """
    if len(state.tool_history) < 2:
        return False
    previous, latest = state.tool_history[-2:]
    return (
        previous.tool_name == latest.tool_name
        and latest.tool_name in _NO_PROGRESS_TOOLS
        and not previous.success
        and not latest.success
        and previous.step_index < latest.step_index
    )
