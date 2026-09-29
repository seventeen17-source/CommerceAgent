"""T031 tests for authoritative verify-after-write behavior."""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.agent.state import VerificationStatus
from app.agent.verify_business_state import verify_refund_business_state
from app.clients.models import AfterSalesStatus, RefundResult
from app.tools.models import ToolEnvelope


class _FakeAfterSalesTools:
    def __init__(self, result: ToolEnvelope[AfterSalesStatus]) -> None:
        self.result = result
        self.calls: list[tuple[str, str | None]] = []

    async def get_after_sales_status(
        self,
        order_id: str,
        *,
        idempotency_key: str | None = None,
    ) -> ToolEnvelope[AfterSalesStatus]:
        self.calls.append((order_id, idempotency_key))
        return self.result


def _refund(refund_id: str = "refund-001") -> RefundResult:
    return RefundResult.model_validate(
        {
            "refundRequestId": refund_id,
            "status": "CREATED",
            "acceptedAmount": Decimal("199.00"),
        }
    )


def _status(*refunds: RefundResult) -> AfterSalesStatus:
    return AfterSalesStatus(refunds=list(refunds), returns=[])


@pytest.mark.asyncio
async def test_success_requires_authoritative_readback_bound_to_same_key() -> None:
    tools = _FakeAfterSalesTools(ToolEnvelope(success=True, data=_status(_refund()), latencyMs=3))

    result = await verify_refund_business_state(
        tools=tools,
        order_id="order-001",
        idempotency_key="t031_key_001",
        expected_refund_request_id="refund-001",
    )

    assert tools.calls == [("order-001", "t031_key_001")]
    assert result.status is VerificationStatus.VERIFIED_SUCCESS
    assert result.resource_id == "refund-001"
    assert result.details["refundStatus"] == "CREATED"
    assert result.details["acceptedAmount"] == "199.00"


@pytest.mark.asyncio
async def test_empty_authoritative_result_is_verified_failure_not_success() -> None:
    tools = _FakeAfterSalesTools(ToolEnvelope(success=True, data=_status(), latencyMs=2))

    result = await verify_refund_business_state(
        tools=tools,
        order_id="order-001",
        idempotency_key="t031_key_001",
    )

    assert result.status is VerificationStatus.VERIFIED_FAILURE
    assert result.resource_id is None
    assert result.details["reasonCode"] == "REFUND_NOT_FOUND_FOR_IDEMPOTENCY_KEY"


@pytest.mark.asyncio
async def test_failed_read_is_unknown_and_never_invented_as_failure() -> None:
    tools = _FakeAfterSalesTools(
        ToolEnvelope[AfterSalesStatus](
            success=False,
            errorCode="DEPENDENCY_UNAVAILABLE",
            retryable=True,
            latencyMs=4,
            traceId="trace-read-failure",
        )
    )

    result = await verify_refund_business_state(
        tools=tools,
        order_id="order-001",
        idempotency_key="t031_key_001",
    )

    assert result.status is VerificationStatus.UNKNOWN
    assert result.details["errorCode"] == "DEPENDENCY_UNAVAILABLE"
    assert result.details["retryable"] is True
    assert result.details["traceId"] == "trace-read-failure"


@pytest.mark.asyncio
async def test_refund_id_mismatch_safe_stops_as_unknown() -> None:
    tools = _FakeAfterSalesTools(
        ToolEnvelope(success=True, data=_status(_refund("refund-other")), latencyMs=2)
    )

    result = await verify_refund_business_state(
        tools=tools,
        order_id="order-001",
        idempotency_key="t031_key_001",
        expected_refund_request_id="refund-expected",
    )

    assert result.status is VerificationStatus.UNKNOWN
    assert result.details["reasonCode"] == "REFUND_ID_MISMATCH"
    assert result.details["expectedRefundRequestId"] == "refund-expected"
    assert result.details["authoritativeRefundRequestId"] == "refund-other"


@pytest.mark.asyncio
async def test_multiple_rows_for_one_key_safe_stop_as_unknown() -> None:
    tools = _FakeAfterSalesTools(
        ToolEnvelope(
            success=True,
            data=_status(_refund("refund-001"), _refund("refund-002")),
            latencyMs=2,
        )
    )

    result = await verify_refund_business_state(
        tools=tools,
        order_id="order-001",
        idempotency_key="t031_key_001",
    )

    assert result.status is VerificationStatus.UNKNOWN
    assert result.details["reasonCode"] == "MULTIPLE_REFUNDS_FOR_IDEMPOTENCY_KEY"
    assert result.details["refundCount"] == 2
