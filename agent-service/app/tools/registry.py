"""Deterministic Tool allowlist for US1."""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Final, Literal, cast

from app.tools.models import ToolRisk

__all__ = ["REGISTERED_TOOL_NAMES", "ToolRegistration", "ToolRegistry"]

ToolName = Literal[
    "list_user_orders",
    "get_order",
    "get_logistics",
    "check_after_sales_eligibility",
    "create_refund_request",
    "get_after_sales_status",
]


@dataclass(frozen=True, slots=True)
class ToolRegistration:
    """Immutable metadata for one capability exposed to the Agent."""

    name: ToolName
    risk: ToolRisk
    description: str


_REGISTRATIONS: Final[dict[ToolName, ToolRegistration]] = {
    "list_user_orders": ToolRegistration(
        name="list_user_orders",
        risk=ToolRisk.READ_PRIVACY_MEDIUM,
        description="List orders belonging to the authenticated customer.",
    ),
    "get_order": ToolRegistration(
        name="get_order",
        risk=ToolRisk.READ_PRIVACY_MEDIUM,
        description="Read one ownership-validated authoritative order snapshot.",
    ),
    "get_logistics": ToolRegistration(
        name="get_logistics",
        risk=ToolRisk.READ_PRIVACY_MEDIUM,
        description="Read authoritative logistics state for an owned order.",
    ),
    "check_after_sales_eligibility": ToolRegistration(
        name="check_after_sales_eligibility",
        risk=ToolRisk.READ_PRIVACY_MEDIUM,
        description="Ask Java for the deterministic after-sales eligibility decision.",
    ),
    "create_refund_request": ToolRegistration(
        name="create_refund_request",
        risk=ToolRisk.HIGH_WRITE,
        description="Create or replay one protected refund request using a stable idempotency key.",
    ),
    "get_after_sales_status": ToolRegistration(
        name="get_after_sales_status",
        risk=ToolRisk.READ_PRIVACY_MEDIUM,
        description="Read authoritative after-sales state, optionally scoped by idempotency key.",
    ),
}

REGISTERED_TOOL_NAMES: Final[frozenset[str]] = frozenset(_REGISTRATIONS)


class ToolRegistry:
    """Read-only lookup over the explicit US1 capability allowlist."""

    def __init__(self) -> None:
        self._registrations = MappingProxyType(_REGISTRATIONS)

    def get(self, name: str) -> ToolRegistration:
        """Return a registered capability or fail closed for arbitrary model output."""
        if name not in self._registrations:
            raise ValueError(f"unregistered tool: {name}")
        return self._registrations[cast(ToolName, name)]

    def all(self) -> tuple[ToolRegistration, ...]:
        """Return registrations in stable declaration order."""
        return tuple(self._registrations.values())
