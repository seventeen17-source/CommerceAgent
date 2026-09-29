"""Authoritative verify-after-write node logic for T031.

A successful write response is not the final business fact. This module reads the Java-owned
after-sales state scoped by the durable idempotency key, then produces a VerificationOutcome.
It deliberately does not retry writes; execute_write.py owns retry/recovery policy and T032 will own
graph routing.
"""

from __future__ import annotations

from typing import Protocol

from app.agent.state import VerificationOutcome, VerificationStatus
from app.clients.models import AfterSalesStatus
from app.tools.models import ToolEnvelope

__all__ = ["AfterSalesReadTools", "verify_refund_business_state"]


class AfterSalesReadTools(Protocol):
    """Read-only Tool capability needed by the verification node."""

    async def get_after_sales_status(
        self,
        order_id: str,
        *,
        idempotency_key: str | None = None,
    ) -> ToolEnvelope[AfterSalesStatus]:
        """Read Java authoritative after-sales state."""
        ...


async def verify_refund_business_state(
    *,
    tools: AfterSalesReadTools,
    order_id: str,
    idempotency_key: str,
    expected_refund_request_id: str | None = None,
) -> VerificationOutcome:
    """Verify one logical refund by reading authority, never by trusting the write response alone.

    The read is scoped by the same durable idempotency key used for the write. An empty refund list
    is a known negative fact. A failed read is UNKNOWN because the Agent cannot establish reality.
    If a direct write response supplied a refund id, the authoritative row must match it.
    """
    result = await tools.get_after_sales_status(
        order_id,
        idempotency_key=idempotency_key,
    )
    if not result.success:
        return VerificationOutcome(
            status=VerificationStatus.UNKNOWN,
            details={
                "errorCode": result.error_code or "AFTER_SALES_READ_FAILED",
                "retryable": result.retryable,
                "traceId": result.trace_id,
            },
        )

    authoritative = result.data
    if authoritative is None:
        raise ValueError("successful after-sales Tool result is missing data")

    if not authoritative.refunds:
        return VerificationOutcome(
            status=VerificationStatus.VERIFIED_FAILURE,
            details={"reasonCode": "REFUND_NOT_FOUND_FOR_IDEMPOTENCY_KEY"},
        )

    if len(authoritative.refunds) != 1:
        return VerificationOutcome(
            status=VerificationStatus.UNKNOWN,
            details={
                "reasonCode": "MULTIPLE_REFUNDS_FOR_IDEMPOTENCY_KEY",
                "refundCount": len(authoritative.refunds),
            },
        )

    refund = authoritative.refunds[0]
    if (
        expected_refund_request_id is not None
        and refund.refund_request_id != expected_refund_request_id
    ):
        return VerificationOutcome(
            status=VerificationStatus.UNKNOWN,
            details={
                "reasonCode": "REFUND_ID_MISMATCH",
                "expectedRefundRequestId": expected_refund_request_id,
                "authoritativeRefundRequestId": refund.refund_request_id,
            },
        )

    return VerificationOutcome(
        status=VerificationStatus.VERIFIED_SUCCESS,
        resource_id=refund.refund_request_id,
        details={
            "refundStatus": refund.status,
            "acceptedAmount": str(refund.accepted_amount),
        },
    )
