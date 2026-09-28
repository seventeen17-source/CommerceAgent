"""T029 executable examples for the first real Agent Tool."""

from __future__ import annotations

import httpx
import pytest

from app.clients.auth import AuthContext
from app.clients.commerce_client import TRACE_ID_HEADER, CommerceClient
from app.tools.commerce_tools import CommerceTools

_FAKE_JWT = "header.payload.signature"
_AUTH = AuthContext(token=_FAKE_JWT)


def _client(handler: object) -> CommerceClient:
    return CommerceClient(
        base_url="http://commerce.test/api/v1",
        timeout_seconds=5.0,
        transport=httpx.MockTransport(handler),  # type: ignore[arg-type]
    )


@pytest.mark.asyncio
async def test_get_order_tool_wraps_authoritative_success_in_tool_envelope() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(
            200,
            json={
                "orderId": "order-001",
                "status": "SHIPPED",
                "totalAmount": "199.00",
                "currency": "USD",
                "items": [],
            },
            headers={TRACE_ID_HEADER: "java-trace-1234"},
        )

    async with _client(handler) as client:
        tools = CommerceTools(client=client, auth=_AUTH)
        result = await tools.get_order("order-001")

    assert result.success is True
    assert result.error_code is None
    assert result.retryable is False
    assert result.data is not None
    assert result.data.order_id == "order-001"
    assert result.trace_id == "java-trace-1234"
    assert result.latency_ms >= 0
    assert seen[0].headers["authorization"] == f"Bearer {_FAKE_JWT}"


@pytest.mark.asyncio
async def test_get_order_tool_turns_java_error_into_stable_failure_envelope() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            404,
            json={
                "errorCode": "ORDER_NOT_FOUND",
                "message": "concealed",
                "retryable": False,
                "traceId": "java-trace-4040",
            },
            headers={TRACE_ID_HEADER: "java-trace-4040"},
        )

    async with _client(handler) as client:
        result = await CommerceTools(client=client, auth=_AUTH).get_order("order-404")

    assert result.success is False
    assert result.data is None
    assert result.error_code == "ORDER_NOT_FOUND"
    assert result.retryable is False
    assert result.trace_id == "java-trace-4040"


@pytest.mark.asyncio
async def test_get_order_tool_rejects_unsafe_model_argument_without_sending_request() -> None:
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(500)

    async with _client(handler) as client:
        result = await CommerceTools(client=client, auth=_AUTH).get_order("../admin")

    assert calls == []
    assert result.success is False
    assert result.error_code == "INVALID_PARAMETER"
    assert result.retryable is False
    assert result.trace_id is None


@pytest.mark.asyncio
async def test_get_order_tool_normalizes_no_authoritative_answer_as_retryable_dependency_failure() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timed out", request=request)

    async with _client(handler) as client:
        result = await CommerceTools(client=client, auth=_AUTH).get_order("order-001")

    assert result.success is False
    assert result.data is None
    assert result.error_code == "DEPENDENCY_UNAVAILABLE"
    assert result.retryable is True
    assert result.trace_id is None


@pytest.mark.asyncio
async def test_list_user_orders_uses_bound_identity_and_wraps_list() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(
            200,
            json=[
                {
                    "orderId": "order-001",
                    "productSummary": "Headphones",
                    "status": "SHIPPED",
                    "createdAt": "2026-09-01T10:00:00Z",
                }
            ],
            headers={TRACE_ID_HEADER: "java-trace-list1"},
        )

    async with _client(handler) as client:
        result = await CommerceTools(client=client, auth=_AUTH).list_user_orders()

    assert result.success is True
    assert result.data is not None
    assert result.data[0].order_id == "order-001"
    assert seen[0].headers["authorization"] == f"Bearer {_FAKE_JWT}"
    assert dict(seen[0].url.params) == {}


@pytest.mark.asyncio
async def test_get_logistics_returns_authoritative_stall_fact() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "status": "IN_TRANSIT",
                "signed": False,
                "lastMeaningfulEventAt": "2026-09-20T00:00:00Z",
                "stalledHours": 72,
            },
            headers={TRACE_ID_HEADER: "java-trace-log1"},
        )

    async with _client(handler) as client:
        result = await CommerceTools(client=client, auth=_AUTH).get_logistics("order-001")

    assert result.success is True
    assert result.data is not None
    assert result.data.stalled_hours == 72


@pytest.mark.asyncio
async def test_eligibility_tool_sends_only_order_and_reason_not_amount() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(
            200,
            json={
                "eligible": True,
                "allowedAction": "REFUND_ONLY",
                "maxRefundAmount": "199.00",
                "approvalRequired": False,
                "ruleCode": "LOGISTICS_STALLED_REFUND",
                "ruleVersion": 1,
                "reasonCodes": ["LOGISTICS_STALLED"],
            },
            headers={TRACE_ID_HEADER: "java-trace-elig1"},
        )

    async with _client(handler) as client:
        result = await CommerceTools(client=client, auth=_AUTH).check_after_sales_eligibility(
            "order-001", "LOGISTICS_DELAY"
        )

    assert result.success is True
    assert result.data is not None
    assert str(result.data.max_refund_amount) == "199.00"
    body = seen[0].content.decode()
    assert '"orderId":"order-001"' in body
    assert '"reasonCode":"LOGISTICS_DELAY"' in body
    assert "requestedAmount" not in body


@pytest.mark.asyncio
async def test_eligibility_tool_rejects_empty_reason_before_http_call() -> None:
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(500)

    async with _client(handler) as client:
        result = await CommerceTools(client=client, auth=_AUTH).check_after_sales_eligibility(
            "order-001", ""
        )

    assert calls == []
    assert result.success is False
    assert result.error_code == "INVALID_PARAMETER"
    assert result.retryable is False


@pytest.mark.asyncio
async def test_after_sales_status_passes_exact_logical_idempotency_key() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(
            200,
            json={
                "refunds": [
                    {
                        "refundRequestId": "refund-001",
                        "status": "CREATED",
                        "acceptedAmount": "199.00",
                    }
                ],
                "returns": [],
            },
            headers={TRACE_ID_HEADER: "java-trace-after1"},
        )

    async with _client(handler) as client:
        result = await CommerceTools(client=client, auth=_AUTH).get_after_sales_status(
            "order-001", idempotency_key="refund_key_001"
        )

    assert result.success is True
    assert result.data is not None
    assert result.data.refunds[0].refund_request_id == "refund-001"
    assert seen[0].url.params["idempotencyKey"] == "refund_key_001"
