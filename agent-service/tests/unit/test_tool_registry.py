"""T029 unit tests for the Tool envelope and capability allowlist."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.clients.auth import AuthContext
from app.clients.commerce_client import CommerceClient
from app.tools import REGISTERED_TOOL_NAMES, CommerceTools, ToolEnvelope, ToolRegistry, ToolRisk

_FAKE_JWT = "header.payload.signature"


def test_us1_registry_exposes_only_the_seven_declared_capabilities() -> None:
    assert REGISTERED_TOOL_NAMES == {
        "list_user_orders",
        "get_order",
        "get_logistics",
        "check_after_sales_eligibility",
        "create_refund_request",
        "create_return_request",
        "get_after_sales_status",
    }


def test_the_write_capabilities_are_exactly_the_refund_and_the_return() -> None:
    registry = ToolRegistry()
    risks = {registration.name: registration.risk for registration in registry.all()}

    # T041 added the second write capability. Listing them explicitly (rather than asserting
    # "at least one write exists") turns an accidental third write tool into a test failure.
    writes = {name for name, risk in risks.items() if risk is ToolRisk.HIGH_WRITE}
    assert writes == {"create_refund_request", "create_return_request"}
    assert all(
        risk is ToolRisk.READ_PRIVACY_MEDIUM for name, risk in risks.items() if name not in writes
    )


def test_registry_rejects_arbitrary_model_selected_capability() -> None:
    registry = ToolRegistry()

    with pytest.raises(ValueError, match="unregistered tool"):
        registry.get("POST http://internal/admin/refunds")


def test_success_envelope_uses_contract_field_names() -> None:
    result = ToolEnvelope[dict[str, str]](
        success=True,
        data={"orderId": "order-001"},
        latencyMs=12,
        traceId="trace-12345678",
    )

    assert result.model_dump(by_alias=True) == {
        "success": True,
        "data": {"orderId": "order-001"},
        "errorCode": None,
        "retryable": False,
        "latencyMs": 12,
        "traceId": "trace-12345678",
    }


@pytest.mark.parametrize(
    "payload",
    [
        {"success": True, "data": None, "latencyMs": 1},
        {"success": True, "data": {}, "errorCode": "SHOULD_NOT_EXIST", "latencyMs": 1},
        {"success": True, "data": {}, "retryable": True, "latencyMs": 1},
        {"success": False, "data": {}, "errorCode": "X", "latencyMs": 1},
        {"success": False, "data": None, "errorCode": None, "latencyMs": 1},
    ],
)
def test_envelope_rejects_ambiguous_success_failure_shapes(payload: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        ToolEnvelope[dict[str, str]].model_validate(payload)


@pytest.mark.asyncio
async def test_registry_resolves_only_explicit_bound_commerce_tool_methods() -> None:
    async with CommerceClient(
        base_url="http://commerce.test/api/v1", timeout_seconds=1.0
    ) as client:
        tools = CommerceTools(
            client=client,
            auth=AuthContext(token=_FAKE_JWT),
        )
        registry = ToolRegistry(tools=tools)

        assert registry.resolve("get_order").__self__ is tools
        assert registry.resolve("get_order").__name__ == "get_order"
        assert registry.resolve("create_refund_request").__self__ is tools
        assert registry.resolve("create_refund_request").__name__ == "create_refund_request"


def test_registry_cannot_resolve_unregistered_or_unbound_implementation() -> None:
    with pytest.raises(ValueError, match="unregistered tool"):
        ToolRegistry().resolve("__dict__")

    with pytest.raises(RuntimeError, match="not bound"):
        ToolRegistry().resolve("get_order")
