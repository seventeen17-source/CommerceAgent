"""Deterministic Tool allowlist and implementation binding for US1."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Final, Literal, cast

from app.tools.commerce_tools import CommerceTools
from app.tools.models import ToolEnvelope, ToolRisk

__all__ = [
    "REGISTERED_TOOL_NAMES",
    "BoundTool",
    "ToolRegistration",
    "ToolRegistry",
]

ToolName = Literal[
    "list_user_orders",
    "get_order",
    "get_logistics",
    "check_after_sales_eligibility",
    "request_human_approval",
    "create_refund_request",
    "create_return_request",
    "get_after_sales_status",
]

BoundTool = Callable[..., Awaitable[ToolEnvelope[Any]]]


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
    "request_human_approval": ToolRegistration(
        name="request_human_approval",
        risk=ToolRisk.HIGH_WRITE,
        description="Create one authoritative PENDING human approval request for the exact proposal.",
    ),
    "create_refund_request": ToolRegistration(
        name="create_refund_request",
        risk=ToolRisk.HIGH_WRITE,
        description="Create or replay one protected refund request using a stable idempotency key.",
    ),
    # T041. Risk stays HIGH_WRITE rather than earning a new level: the trace table's ``risk_level``
    # vocabulary is LOW/MEDIUM/HIGH, so a "medium write" would be recorded indistinguishably from a
    # read. The money/non-money distinction is carried where it is actually load-bearing -- the node
    # (``RETURN_WRITE`` vs ``REFUND_WRITE``), this name, and a request type with no amount field.
    "create_return_request": ToolRegistration(
        name="create_return_request",
        risk=ToolRisk.HIGH_WRITE,
        description="Create or replay one protected return request using a stable idempotency key.",
    ),
    "get_after_sales_status": ToolRegistration(
        name="get_after_sales_status",
        risk=ToolRisk.READ_PRIVACY_MEDIUM,
        description="Read authoritative after-sales state, optionally scoped by idempotency key.",
    ),
}

REGISTERED_TOOL_NAMES: Final[frozenset[str]] = frozenset(_REGISTRATIONS)


class ToolRegistry:
    """Read-only allowlist plus deterministic name-to-implementation binding.

    This class answers only two questions:
    1. Is this capability registered?
    2. Which bound CommerceTools method implements it?

    It deliberately does NOT answer "may this tool run in the current AgentState?". Eligibility,
    evidence prerequisites, approval state and graph routing remain T030/T032 responsibilities.
    """

    def __init__(self, *, tools: CommerceTools | None = None) -> None:
        self._registrations = MappingProxyType(_REGISTRATIONS)
        self._tools = tools

    def get(self, name: str) -> ToolRegistration:
        """Return registered metadata or fail closed for arbitrary model output."""
        if name not in self._registrations:
            raise ValueError(f"unregistered tool: {name}")
        return self._registrations[cast(ToolName, name)]

    def resolve(self, name: str) -> BoundTool:
        """Resolve a registered name to its already-authenticated Tool implementation.

        Binding is explicit rather than based on arbitrary attribute lookup. A model-produced string
        can select only one of these eight predeclared capabilities; it can never name an arbitrary
        method, URL, service or SQL statement.
        """
        registration = self.get(name)
        if self._tools is None:
            raise RuntimeError("tool implementations are not bound")

        implementations: dict[ToolName, BoundTool] = {
            "list_user_orders": self._tools.list_user_orders,
            "get_order": self._tools.get_order,
            "get_logistics": self._tools.get_logistics,
            "check_after_sales_eligibility": self._tools.check_after_sales_eligibility,
            "request_human_approval": self._tools.request_human_approval,
            "create_refund_request": self._tools.create_refund_request,
            "create_return_request": self._tools.create_return_request,
            "get_after_sales_status": self._tools.get_after_sales_status,
        }
        return implementations[registration.name]

    def all(self) -> tuple[ToolRegistration, ...]:
        """Return registrations in stable declaration order."""
        return tuple(self._registrations.values())
