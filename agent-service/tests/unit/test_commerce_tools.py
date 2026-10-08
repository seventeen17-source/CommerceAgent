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
async def test_get_order_tool_maps_no_authoritative_answer_to_retryable_failure() -> None:
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
async def test_request_human_approval_sends_only_the_exact_proposal_and_wraps_authority() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(
            201,
            json={
                "approvalRequestId": "approval-001",
                "runId": "52000000-0000-4000-8000-000000000001",
                "orderId": "order-001",
                "actionType": "REFUND_ONLY",
                "amount": "399.00",
                "riskReason": "APPROVAL_REQUIRED_BY_AMOUNT",
                "status": "PENDING",
                "decidedBy": None,
                "decidedAt": None,
                "requestedAt": "2026-10-08T08:00:00Z",
                "expiresAt": "2026-10-09T08:00:00Z",
            },
            headers={TRACE_ID_HEADER: "java-trace-approval1"},
        )

    async with _client(handler) as client:
        result = await CommerceTools(client=client, auth=_AUTH).request_human_approval(
            run_id="52000000-0000-4000-8000-000000000001",
            order_id="order-001",
            action_type="REFUND_ONLY",
            amount=__import__("decimal").Decimal("399.00"),
            risk_reason="APPROVAL_REQUIRED_BY_AMOUNT",
        )

    assert result.success is True
    assert result.data is not None
    assert result.data.approval_request_id == "approval-001"
    assert result.data.status == "PENDING"
    body = seen[0].content.decode()
    assert '"status"' not in body
    assert '"decidedBy"' not in body
    assert '"runId":"52000000-0000-4000-8000-000000000001"' in body
    assert '"amount":"399.00"' in body


@pytest.mark.asyncio
async def test_request_human_approval_timeout_is_unknown_and_not_blind_retryable() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        raise httpx.ReadTimeout("timed out", request=request)

    async with _client(handler) as client:
        result = await CommerceTools(client=client, auth=_AUTH).request_human_approval(
            run_id="52000000-0000-4000-8000-000000000001",
            order_id="order-001",
            action_type="REFUND_ONLY",
            amount=__import__("decimal").Decimal("399.00"),
            risk_reason="APPROVAL_REQUIRED_BY_AMOUNT",
        )

    assert calls == 1
    assert result.success is False
    assert result.error_code == "WRITE_TIMEOUT_UNKNOWN"
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


@pytest.mark.asyncio
async def test_create_refund_request_wraps_success_without_retrying() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(
            200,
            json={
                "refundRequestId": "refund-001",
                "status": "CREATED",
                "acceptedAmount": "199.00",
            },
            headers={TRACE_ID_HEADER: "java-trace-refund1"},
        )

    async with _client(handler) as client:
        result = await CommerceTools(client=client, auth=_AUTH).create_refund_request(
            order_id="order-001",
            reason_code="LOGISTICS_DELAY",
            requested_amount=None,
            idempotency_key="refund_key_001",
            run_id="11111111-2222-4333-8444-555555555555",
        )

    assert result.success is True
    assert result.data is not None
    assert result.data.refund_request_id == "refund-001"
    assert result.trace_id == "java-trace-refund1"
    assert seen[0].headers["Idempotency-Key"] == "refund_key_001"


@pytest.mark.asyncio
async def test_create_refund_request_keeps_known_java_denial_non_retryable() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            409,
            json={
                "errorCode": "AMOUNT_EXCEEDS_ALLOWED",
                "message": "rejected",
                "retryable": False,
                "traceId": "java-trace-refund2",
            },
            headers={TRACE_ID_HEADER: "java-trace-refund2"},
        )

    async with _client(handler) as client:
        result = await CommerceTools(client=client, auth=_AUTH).create_refund_request(
            order_id="order-001",
            reason_code="LOGISTICS_DELAY",
            requested_amount=None,
            idempotency_key="refund_key_002",
            run_id="11111111-2222-4333-8444-555555555555",
        )

    assert result.success is False
    assert result.error_code == "AMOUNT_EXCEEDS_ALLOWED"
    assert result.retryable is False
    assert result.trace_id == "java-trace-refund2"


@pytest.mark.asyncio
async def test_create_refund_request_timeout_becomes_unknown_write_not_retryable() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        raise httpx.ReadTimeout("timed out", request=request)

    async with _client(handler) as client:
        result = await CommerceTools(client=client, auth=_AUTH).create_refund_request(
            order_id="order-001",
            reason_code="LOGISTICS_DELAY",
            requested_amount=None,
            idempotency_key="refund_key_003",
            run_id="11111111-2222-4333-8444-555555555555",
        )

    assert calls == 1
    assert result.success is False
    assert result.error_code == "WRITE_TIMEOUT_UNKNOWN"
    assert result.retryable is False
    assert result.trace_id is None


@pytest.mark.asyncio
async def test_create_refund_request_rejects_bad_key_before_http_call() -> None:
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(500)

    async with _client(handler) as client:
        result = await CommerceTools(client=client, auth=_AUTH).create_refund_request(
            order_id="order-001",
            reason_code="LOGISTICS_DELAY",
            requested_amount=None,
            idempotency_key="bad.key",
            run_id="11111111-2222-4333-8444-555555555555",
        )

    assert calls == []
    assert result.success is False
    assert result.error_code == "INVALID_PARAMETER"
    assert result.retryable is False
