"""T029 unit tests for the Tool envelope and capability allowlist."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.tools import REGISTERED_TOOL_NAMES, ToolEnvelope, ToolRegistry, ToolRisk


def test_us1_registry_exposes_only_the_six_declared_capabilities() -> None:
    assert REGISTERED_TOOL_NAMES == {
        "list_user_orders",
        "get_order",
        "get_logistics",
        "check_after_sales_eligibility",
        "create_refund_request",
        "get_after_sales_status",
    }


def test_refund_write_is_the_only_high_write_capability_in_us1() -> None:
    registry = ToolRegistry()
    risks = {registration.name: registration.risk for registration in registry.all()}

    assert risks["create_refund_request"] is ToolRisk.HIGH_WRITE
    assert all(
        risk is ToolRisk.READ_PRIVACY_MEDIUM
        for name, risk in risks.items()
        if name != "create_refund_request"
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
