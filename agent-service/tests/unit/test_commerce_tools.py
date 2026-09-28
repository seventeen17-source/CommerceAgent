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
