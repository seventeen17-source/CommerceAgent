"""T031 tests for the Tool-level refund write executor."""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.agent.execute_write import (
    UNKNOWN_OUTCOME_ERROR_CODE,
    RefundWriteIntent,
    execute_refund_write,
)
from app.agent.state import WriteIntent, WriteOutcome, WriteStatus
from app.clients.models import AfterSalesStatus, RefundResult
from app.tools.models import ToolEnvelope


class _FakeWriteTools:
    def __init__(
        self,
        *,
        writes: list[ToolEnvelope[RefundResult]],
        reads: list[ToolEnvelope[AfterSalesStatus]],
    ) -> None:
        self.writes = list(writes)
        self.reads = list(reads)
        self.write_keys: list[str] = []
        self.calls: list[str] = []

    async def create_refund_request(
        self,
        *,
        order_id: str,
        reason_code: str,
        requested_amount: Decimal | None,
        idempotency_key: str,
        run_id: str,
        approval_request_id: str | None = None,
    ) -> ToolEnvelope[RefundResult]:
        self.calls.append("write")
        self.write_keys.append(idempotency_key)
        return self.writes.pop(0)

    async def get_after_sales_status(
        self,
        order_id: str,
        *,
        idempotency_key: str | None = None,
    ) -> ToolEnvelope[AfterSalesStatus]:
        self.calls.append("read")
        return self.reads.pop(0)


def _intent() -> RefundWriteIntent:
    return RefundWriteIntent(
        run_id="9c2f5b6e-1a2b-4c3d-8e4f-5a6b7c8d9e0f",
        order_id="order-001",
        reason_code="LOGISTICS_DELAY",
        idempotency_key="t031_same_key_001",
    )


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


async def _persist(intent: WriteIntent, pending: WriteOutcome) -> None:
    assert intent.idempotency_key == "t031_same_key_001"
    assert pending.status is WriteStatus.PENDING


@pytest.mark.asyncio
async def test_tool_executor_success_records_write_history() -> None:
    tools = _FakeWriteTools(
        writes=[ToolEnvelope(success=True, data=_refund(), latencyMs=2, traceId="trace-write-001")],
        reads=[],
    )

    result = await execute_refund_write(
        tools=tools,
        intent=_intent(),
        persist_intent=_persist,
    )

    assert result.outcome.write_status is WriteStatus.SUCCEEDED
    assert result.outcome.resource_id == "refund-001"
    assert tools.calls == ["write"]
    assert [entry.tool_name for entry in result.history] == ["create_refund_request"]


@pytest.mark.asyncio
async def test_unknown_write_reads_authority_before_recovering() -> None:
    tools = _FakeWriteTools(
        writes=[
            ToolEnvelope[RefundResult](
                success=False, errorCode=UNKNOWN_OUTCOME_ERROR_CODE, retryable=False, latencyMs=5
            )
        ],
        reads=[ToolEnvelope(success=True, data=_status(_refund()), latencyMs=2)],
    )

    result = await execute_refund_write(
        tools=tools,
        intent=_intent(),
        persist_intent=_persist,
    )

    assert result.outcome.write_status is WriteStatus.SUCCEEDED
    assert result.outcome.recovered is True
    assert tools.calls == ["write", "read"]
    assert [entry.tool_name for entry in result.history] == [
        "create_refund_request",
        "get_after_sales_status",
    ]


@pytest.mark.asyncio
async def test_unknown_write_with_failed_read_stays_unknown_and_does_not_retry() -> None:
    tools = _FakeWriteTools(
        writes=[
            ToolEnvelope[RefundResult](
                success=False, errorCode=UNKNOWN_OUTCOME_ERROR_CODE, retryable=False, latencyMs=5
            )
        ],
        reads=[
            ToolEnvelope[AfterSalesStatus](
                success=False,
                errorCode="DEPENDENCY_UNAVAILABLE",
                retryable=True,
                latencyMs=2,
            )
        ],
    )

    result = await execute_refund_write(
        tools=tools,
        intent=_intent(),
        persist_intent=_persist,
    )

    assert result.outcome.write_status is WriteStatus.UNKNOWN
    assert result.outcome.error_code == UNKNOWN_OUTCOME_ERROR_CODE
    assert tools.calls == ["write", "read"]
    assert tools.write_keys == ["t031_same_key_001"]


@pytest.mark.asyncio
async def test_authoritative_empty_allows_only_same_key_retry() -> None:
    tools = _FakeWriteTools(
        writes=[
            ToolEnvelope[RefundResult](
                success=False, errorCode=UNKNOWN_OUTCOME_ERROR_CODE, retryable=False, latencyMs=5
            ),
            ToolEnvelope(success=True, data=_refund(), latencyMs=2),
        ],
        reads=[ToolEnvelope(success=True, data=_status(), latencyMs=2)],
    )

    result = await execute_refund_write(
        tools=tools,
        intent=_intent(),
        persist_intent=_persist,
        max_attempts=2,
    )

    assert result.outcome.write_status is WriteStatus.SUCCEEDED
    assert result.outcome.attempts == 2
    assert tools.calls == ["write", "read", "write"]
    assert tools.write_keys == ["t031_same_key_001", "t031_same_key_001"]
