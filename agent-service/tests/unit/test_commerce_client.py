"""Unit tests for the typed Java API client (T016 read / evaluation surface).

The client's job is not to make HTTP requests -- ``httpx`` does that. Its job is to make sure the
four invariants below hold for *every* endpoint without each tool having to remember them:

1. the caller's Bearer token is forwarded and never asserted as an identity;
2. the correlation id is generated here, so model output cannot supply it;
3. "the backend answered" and "no answer arrived" stay distinct exception types, because that is
   the only distinction that makes a retry safe or unsafe;
4. nothing leaves the process when a parameter cannot be sent safely.

Every test drives a real :class:`httpx.AsyncClient` against :class:`httpx.MockTransport`, so the
assertions are about the request that would actually have gone over the wire.
"""

from __future__ import annotations

import json
from decimal import Decimal
from typing import Any

import httpx
import pytest

from app.clients.auth import AuthContext
from app.clients.commerce_client import TRACE_ID_HEADER, CommerceClient
from app.clients.errors import (
    CommerceApiError,
    CommerceTransportError,
    UnsafeRequestParameterError,
)
from app.clients.models import EligibilityRequest
from app.config.settings import Settings

# A placeholder, not a credential: three base64url-shaped segments joined by dots. Named without a
# "token"/"password" root so ruff's hardcoded-secret rule (S105) stays enabled for real tests.
_FAKE_JWT = "header.payload.signature"
_AUTH = AuthContext(token=_FAKE_JWT)

_ORDER_SNAPSHOT: dict[str, Any] = {
    "orderId": "order-001",
    "status": "DELIVERED",
    "totalAmount": "199.90",
    "currency": "CNY",
    "items": [{"productId": "p-1", "productName": "Headphones", "quantity": 1}],
}

_ELIGIBILITY_DECISION: dict[str, Any] = {
    "eligible": True,
    "allowedAction": "REFUND_ONLY",
    "maxRefundAmount": "199.90",
    "approvalRequired": False,
    "ruleCode": "REFUND_DELIVERED_WITHIN_WINDOW",
    "ruleVersion": 3,
    "reasonCodes": ["SIGNED_RECENTLY"],
}


def _client(handler: Any, *, base_url: str = "http://commerce.test/api/v1") -> CommerceClient:
    """Build a client whose transport is fully scripted.

    A generous timeout is used on purpose: a test should only see a timeout when it raises one
    explicitly, never as an accident of a slow machine.
    """
    return CommerceClient(
        base_url=base_url, timeout_seconds=5.0, transport=httpx.MockTransport(handler)
    )


def _json_response(
    payload: Any, *, status_code: int = 200, headers: dict[str, str] | None = None
) -> httpx.Response:
    return httpx.Response(status_code, json=payload, headers=headers)


# ---- credential forwarding -----------------------------------------------------------------


@pytest.mark.asyncio
async def test_forwards_bearer_token_and_never_accepts_a_user_id() -> None:
    """Java resolves identity from the token; this client only forwards the credential."""
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(dict(request.headers))
        return _json_response({"userId": "customer-001", "role": "CUSTOMER"})

    async with _client(handler) as client:
        call = await client.get_principal(_AUTH)

    assert seen["authorization"] == f"Bearer {_FAKE_JWT}"
    assert call.value.user_id == "customer-001"
    # The client cannot assert an identity: no endpoint takes a user id.
    assert "userId" not in seen


@pytest.mark.asyncio
async def test_token_never_appears_in_the_error_text() -> None:
    """A timeout reason can reach a log line and the tool trace, so it must not carry the token."""

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("timed out", request=request)

    async with _client(handler) as client:
        with pytest.raises(CommerceTransportError) as exc_info:
            await client.get_principal(_AUTH)

    assert _FAKE_JWT not in str(exc_info.value)
    assert _FAKE_JWT not in repr(exc_info.value)


# ---- correlation id ------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_generates_a_trace_id_per_call_and_reports_the_one_java_logged() -> None:
    """The id is created inside the client and returned so T017 can persist it."""
    sent: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        sent.append(request.headers[TRACE_ID_HEADER])
        return _json_response(_ORDER_SNAPSHOT, headers={TRACE_ID_HEADER: "java-trace-1"})

    async with _client(handler) as client:
        first = await client.get_order(_AUTH, "order-001")
        second = await client.get_order(_AUTH, "order-001")

    assert first.trace_id == "java-trace-1"
    assert second.trace_id == "java-trace-1"
    # Per call, not per client: two requests must never share a correlation id.
    assert len(set(sent)) == 2
    assert first.status_code == 200


@pytest.mark.asyncio
async def test_reflected_trace_id_cannot_forge_a_log_line() -> None:
    """The reflected header is remote input that lands in logs and in a 128-char DB column."""

    def handler(request: httpx.Request) -> httpx.Response:
        # httpx normalises a CRLF inside a header value; what must hold regardless is that the id we
        # accept is single-line and bounded, because that is the only shape safe to log and store.
        return _json_response(_ORDER_SNAPSHOT, headers={TRACE_ID_HEADER: "evil\r\nFAKE: yes"})

    async with _client(handler) as client:
        call = await client.get_order(_AUTH, "order-001")

    assert "\r" not in call.trace_id
    assert "\n" not in call.trace_id
    assert len(call.trace_id) <= 128


@pytest.mark.asyncio
async def test_over_long_reflected_trace_id_falls_back_to_the_generated_one() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return _json_response(_ORDER_SNAPSHOT, headers={TRACE_ID_HEADER: "x" * 200})

    async with _client(handler) as client:
        call = await client.get_order(_AUTH, "order-001")

    assert call.trace_id != "x" * 200
    assert len(call.trace_id) <= 128


# ---- parameter safety ----------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "order_id",
    [
        "../../admin/users",
        "order-001?status=PAID",
        "order-001#frag",
        "order-001/refunds",
        "order 001",
        "",
        "-leading-dash",
        "x" * 65,
    ],
)
async def test_unsafe_order_id_is_rejected_before_anything_is_sent(order_id: str) -> None:
    """Interpolating model output into a path is the URL form of SQL injection.

    The load-bearing assertion is ``calls == []``, not the exception type: a rejection that happened
    after the request left the process would already have leaked the traversal to Java.
    """
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return _json_response(_ORDER_SNAPSHOT)

    async with _client(handler) as client:
        with pytest.raises(UnsafeRequestParameterError) as exc_info:
            await client.get_order(_AUTH, order_id)

    assert calls == []
    assert exc_info.value.field == "order_id"
    assert exc_info.value.outcome_unknown is False
    if order_id:
        # The untrusted value is never interpolated into the message (empty is a substring of
        # anything, so the assertion would be vacuous for that case).
        assert order_id not in str(exc_info.value)


@pytest.mark.asyncio
async def test_real_order_id_shapes_are_accepted() -> None:
    """The charset must stay wide enough for the ids the seed data actually uses."""

    def handler(request: httpx.Request) -> httpx.Response:
        return _json_response({**_ORDER_SNAPSHOT, "orderId": request.url.path.rsplit("/", 1)[-1]})

    async with _client(handler) as client:
        for order_id in ("order-001", "demo-order-stalled-001", "ORD_2026.09"):
            call = await client.get_order(_AUTH, order_id)
            assert call.value.order_id == order_id


@pytest.mark.asyncio
async def test_logistics_endpoint_reuses_the_same_path_safety_rule() -> None:
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return _json_response({"status": "IN_TRANSIT", "signed": False})

    async with _client(handler) as client:
        with pytest.raises(UnsafeRequestParameterError):
            await client.get_logistics(_AUTH, "../orders/other")

    assert calls == []


# ---- answered vs did not answer ------------------------------------------------------------


@pytest.mark.asyncio
async def test_error_envelope_becomes_a_known_failure_with_the_backend_retry_decision() -> None:
    """A 403 matching the error contract says "it did not happen" -- nothing is unknown."""
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return _json_response(
            {
                "errorCode": "ORDER_FORBIDDEN",
                "message": "Order is not accessible to the authenticated user",
                "retryable": False,
                "traceId": "trace-403",
                "details": {},
            },
            status_code=403,
            headers={TRACE_ID_HEADER: "trace-403"},
        )

    async with _client(handler) as client:
        with pytest.raises(CommerceApiError) as exc_info:
            await client.get_order(_AUTH, "order-001")

    error = exc_info.value
    assert error.error_code == "ORDER_FORBIDDEN"
    assert error.http_status == 403
    assert error.retryable is False
    assert error.trace_id == "trace-403"
    assert error.outcome_unknown is False
    assert error.blind_retry_allowed is False
    # Ownership was evaluated by Java against the forwarded token, not by us.
    assert seen[0].headers["authorization"] == f"Bearer {_FAKE_JWT}"


@pytest.mark.asyncio
async def test_error_uses_validated_response_header_trace_id_when_envelope_disagrees() -> None:
    """Persist the correlation id Java exposed in the response header, not a drifting JSON value."""

    def handler(request: httpx.Request) -> httpx.Response:
        return _json_response(
            {
                "errorCode": "ORDER_FORBIDDEN",
                "message": "Order is not accessible to the authenticated user",
                "retryable": False,
                "traceId": "different-envelope-trace",
            },
            status_code=403,
            headers={TRACE_ID_HEADER: "java-trace-403"},
        )

    async with _client(handler) as client:
        with pytest.raises(CommerceApiError) as exc_info:
            await client.get_order(_AUTH, "order-001")

    assert exc_info.value.trace_id == "java-trace-403"


@pytest.mark.asyncio
async def test_error_envelope_cannot_override_a_safe_correlation_id_with_control_text() -> None:
    """An error-body trace id is remote JSON and must not become persisted correlation metadata."""

    def handler(request: httpx.Request) -> httpx.Response:
        return _json_response(
            {
                "errorCode": "ORDER_FORBIDDEN",
                "retryable": False,
                "traceId": "evil\r\nFAKE: yes",
            },
            status_code=403,
            headers={TRACE_ID_HEADER: "java-trace-safe"},
        )

    async with _client(handler) as client:
        with pytest.raises(CommerceApiError) as exc_info:
            await client.get_order(_AUTH, "order-001")

    assert exc_info.value.trace_id == "java-trace-safe"
    assert "\r" not in exc_info.value.trace_id
    assert "\n" not in exc_info.value.trace_id


@pytest.mark.asyncio
async def test_retryable_envelope_keeps_the_backend_retry_decision() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return _json_response(
            {"errorCode": "UPSTREAM_UNAVAILABLE", "retryable": True, "traceId": "trace-503"},
            status_code=503,
        )

    async with _client(handler) as client:
        with pytest.raises(CommerceApiError) as exc_info:
            await client.get_logistics(_AUTH, "order-001")

    assert exc_info.value.blind_retry_allowed is True
    assert exc_info.value.outcome_unknown is False


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status_code", "body", "content_type"),
    [
        (500, {"detail": "boom"}, "application/json"),
        (502, "<html><body>Bad Gateway</body></html>", "text/html"),
        (500, {"errorCode": "INTERNAL_ERROR", "traceId": "t"}, "application/json"),
    ],
    ids=["json-without-contract", "html-error-page", "envelope-without-retryable"],
)
async def test_answer_outside_the_error_contract_is_treated_as_no_answer(
    status_code: int, body: Any, content_type: str
) -> None:
    """Without ``retryable`` a bare status code proves nothing, so the outcome stays unknown.

    The third case is the sharp one: the body *looks* like the contract but omits the one field that
    carries retry authority. Trusting the status code alone would license a blind retry of a write.
    """

    def handler(request: httpx.Request) -> httpx.Response:
        payload = body if isinstance(body, str) else json.dumps(body)
        return httpx.Response(status_code, content=payload, headers={"content-type": content_type})

    async with _client(handler) as client:
        with pytest.raises(CommerceTransportError) as exc_info:
            await client.get_order(_AUTH, "order-001")

    assert exc_info.value.outcome_unknown is True
    assert str(status_code) in exc_info.value.reason


@pytest.mark.asyncio
async def test_timeout_on_the_eligibility_post_is_still_blind_retryable() -> None:
    """Safety comes from the operation's semantics, not from ``method == "GET"``.

    ``POST /after-sales/eligibility`` is a deterministic evaluation that commits nothing, so an
    unknown outcome costs one wasted call. Writing the decision at the call site instead of deriving
    it from the method is also what keeps the T026 write endpoints honest: there the same shape must
    say ``request_is_safe=False``.
    """

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("read timed out", request=request)

    async with _client(handler) as client:
        with pytest.raises(CommerceTransportError) as exc_info:
            await client.check_eligibility(
                _AUTH, EligibilityRequest(order_id="order-001", reason_code="NOT_RECEIVED")
            )

    error = exc_info.value
    assert error.outcome_unknown is True
    assert error.request_was_safe is True
    assert error.blind_retry_allowed is True


@pytest.mark.asyncio
async def test_connection_failure_is_an_unknown_outcome_not_a_known_failure() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    async with _client(handler) as client:
        with pytest.raises(CommerceTransportError) as exc_info:
            await client.list_orders(_AUTH)

    assert exc_info.value.outcome_unknown is True
    assert "ConnectError" in exc_info.value.reason


# ---- contract validation -------------------------------------------------------------------


@pytest.mark.asyncio
async def test_contract_violating_success_is_reported_without_leaking_values() -> None:
    """A 200 that breaks the contract means "no authoritative answer", not a value to act on.

    The reason names the offending *field and error type* only. ``str(ValidationError)`` would have
    echoed ``not-a-number`` -- and with it any amount, product name or user id -- into the tool
    trace and the logs.
    """

    def handler(request: httpx.Request) -> httpx.Response:
        return _json_response(
            {
                "orderId": "order-001",
                "status": "DELIVERED",
                "totalAmount": "not-a-number",
                "currency": "CNY",
            }
        )

    async with _client(handler) as client:
        with pytest.raises(CommerceTransportError) as exc_info:
            await client.get_order(_AUTH, "order-001")

    reason = exc_info.value.reason
    assert "OrderSnapshot" in reason
    assert "totalAmount" in reason
    # The request path is a caller-supplied, charset-validated identifier and is genuinely useful
    # for debugging; what must never be echoed is a value that came *out of* the response body.
    assert "/orders/order-001" in reason
    assert "not-a-number" not in reason
    assert "DELIVERED" not in reason
    assert "CNY" not in reason


@pytest.mark.asyncio
async def test_money_stays_decimal_end_to_end() -> None:
    """``199.90`` must survive the wire as an exact amount, not as a binary approximation."""

    def handler(request: httpx.Request) -> httpx.Response:
        return _json_response(_ORDER_SNAPSHOT)

    async with _client(handler) as client:
        call = await client.get_order(_AUTH, "order-001")

    assert call.value.total_amount == Decimal("199.90")
    assert str(call.value.total_amount) == "199.90"


@pytest.mark.asyncio
async def test_list_orders_omits_filters_that_were_not_asked_for() -> None:
    """An empty ``status`` is not the same as no filter, so absent means absent."""
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return _json_response(
            [
                {
                    "orderId": "order-001",
                    "productSummary": "Headphones",
                    "status": "DELIVERED",
                    "createdAt": "2026-09-01T10:00:00Z",
                }
            ]
        )

    async with _client(handler) as client:
        call = await client.list_orders(_AUTH)
        filtered = await client.list_orders(_AUTH, product_query="耳机", status_filter="DELIVERED")

    assert len(call.value) == 1
    assert call.value[0].order_id == "order-001"
    assert call.value[0].created_at.year == 2026
    assert dict(seen[0].url.params) == {}
    assert dict(seen[1].url.params) == {"productQuery": "耳机", "status": "DELIVERED"}
    # Two calls must not share a correlation id.
    assert filtered.trace_id != call.trace_id


@pytest.mark.asyncio
async def test_list_orders_rejects_an_object_where_the_contract_declares_an_array() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return _json_response({"orders": []})

    async with _client(handler) as client:
        with pytest.raises(CommerceTransportError) as exc_info:
            await client.list_orders(_AUTH)

    assert "declares an array" in exc_info.value.reason


@pytest.mark.asyncio
async def test_list_orders_names_the_malformed_item() -> None:
    """ "Some order was wrong" is not actionable; ``/orders[1]`` is."""

    def handler(request: httpx.Request) -> httpx.Response:
        return _json_response(
            [
                {
                    "orderId": "order-001",
                    "productSummary": "Headphones",
                    "status": "DELIVERED",
                    "createdAt": "2026-09-01T10:00:00Z",
                },
                {"orderId": "order-002", "status": "DELIVERED"},
            ]
        )

    async with _client(handler) as client:
        with pytest.raises(CommerceTransportError) as exc_info:
            await client.list_orders(_AUTH)

    reason = exc_info.value.reason
    assert "/orders[1]" in reason
    assert "productSummary" in reason


# ---- eligibility request body --------------------------------------------------------------


@pytest.mark.asyncio
async def test_eligibility_sends_contract_field_names_and_no_amount() -> None:
    """The backend computes ``maxRefundAmount``; the Agent must not propose one."""
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return _json_response(_ELIGIBILITY_DECISION)

    async with _client(handler) as client:
        call = await client.check_eligibility(
            _AUTH, EligibilityRequest(order_id="order-001", reason_code="NOT_RECEIVED")
        )

    request = seen[0]
    assert request.method == "POST"
    assert json.loads(request.content) == {"orderId": "order-001", "reasonCode": "NOT_RECEIVED"}
    assert request.headers["content-type"].startswith("application/json")
    assert call.value.eligible is True
    assert call.value.allowed_action == "REFUND_ONLY"
    assert call.value.max_refund_amount == Decimal("199.90")
    assert call.value.rule_version == 3
    assert call.value.reason_codes == ["SIGNED_RECENTLY"]


# ---- configuration -------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_from_settings_joins_the_contract_path_prefix() -> None:
    """``commerce_api_base_url`` is the service root; the contract's server URL adds ``/api/v1``."""
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return _json_response({"userId": "customer-001", "role": "CUSTOMER"})

    settings = Settings(commerce_api_base_url="http://localhost:8080/")
    transport = httpx.MockTransport(handler)
    async with CommerceClient.from_settings(settings, transport=transport) as client:
        await client.get_principal(_AUTH)

    assert str(seen[0].url) == "http://localhost:8080/api/v1/me"


@pytest.mark.asyncio
async def test_ambient_proxy_configuration_cannot_reroute_the_authority_channel(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``trust_env=False`` is a security decision, not a convenience.

    httpx resolves proxies from the environment, and on Windows that resolution also reads the
    *registry* proxy -- so no ``HTTP_PROXY`` variable has to exist for a machine-level setting to
    put itself between the Agent and Java and receive the forwarded Bearer token. That is what
    happened on the first live run of this client: a system proxy answered ``502`` outside the
    error contract.

    ``trust_env`` is httpx's public property, so this pins the decision without depending on how
    httpx happens to store proxy mounts.
    """
    monkeypatch.setenv("HTTP_PROXY", "http://127.0.0.1:9")

    async with CommerceClient(
        base_url="http://commerce.test/api/v1", timeout_seconds=1.0
    ) as client:
        assert client._http.trust_env is False
