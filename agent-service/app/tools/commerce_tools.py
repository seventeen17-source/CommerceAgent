"""US1 Agent Tools backed by the typed Java CommerceClient."""

from __future__ import annotations

from collections.abc import Awaitable
from time import perf_counter
from typing import TypeVar

from pydantic import BaseModel, ValidationError

from app.clients.auth import AuthContext
from app.clients.commerce_client import CommerceCall, CommerceClient
from app.clients.errors import (
    CommerceApiError,
    CommerceTransportError,
    UnsafeRequestParameterError,
)
from app.clients.models import (
    AfterSalesStatus,
    EligibilityDecision,
    EligibilityRequest,
    LogisticsSnapshot,
    OrderSnapshot,
    OrderSummary,
)
from app.tools.models import ToolEnvelope

__all__ = ["CommerceTools"]

T = TypeVar("T")


class CommerceTools:
    """Authenticated Tool facade exposed to the Agent graph.

    The credential is bound by application code when this facade is created. It is intentionally
    absent from every public Tool argument so model output can never select a user, token, URL, or
    backend service.
    """

    def __init__(self, *, client: CommerceClient, auth: AuthContext) -> None:
        self._client = client
        self._auth = auth

    async def list_user_orders(self) -> ToolEnvelope[list[OrderSummary]]:
        """List orders for the authenticated customer only."""
        return await _read_tool(self._client.list_orders(self._auth))

    async def get_order(self, order_id: str) -> ToolEnvelope[OrderSnapshot]:
        """Return one ownership-validated authoritative order snapshot."""
        return await _read_tool(self._client.get_order(self._auth, order_id))

    async def get_logistics(self, order_id: str) -> ToolEnvelope[LogisticsSnapshot]:
        """Return authoritative logistics facts; never infer them in the Agent."""
        return await _read_tool(self._client.get_logistics(self._auth, order_id))

    async def check_after_sales_eligibility(
        self, order_id: str, reason_code: str
    ) -> ToolEnvelope[EligibilityDecision]:
        """Ask Java for a deterministic eligibility decision.

        The Tool accepts only evidence identifiers. It does not accept a proposed refund amount:
        Java owns the allowed amount and returns it in the decision.
        """
        started = perf_counter()
        try:
            request = EligibilityRequest(order_id=order_id, reason_code=reason_code)
        except ValidationError:
            return _invalid_parameter(started)

        return await _read_tool(
            self._client.check_eligibility(self._auth, request),
            started=started,
        )

    async def get_after_sales_status(
        self,
        order_id: str,
        *,
        idempotency_key: str | None = None,
    ) -> ToolEnvelope[AfterSalesStatus]:
        """Read authoritative after-sales state, optionally scoped to one logical write."""
        return await _read_tool(
            self._client.get_after_sales_status(
                self._auth,
                order_id,
                idempotency_key=idempotency_key,
            )
        )


async def _read_tool(
    operation: Awaitable[CommerceCall[T]],
    *,
    started: float | None = None,
) -> ToolEnvelope[T]:
    """Normalize one side-effect-free CommerceClient operation for the Agent graph.

    This is deliberately read/evaluation-only. The future refund write Tool must not reuse this
    helper because a transport failure on a write is an unknown business outcome, not permission to
    retry.
    """
    started_at = perf_counter() if started is None else started
    try:
        call = await operation
    except CommerceApiError as exc:
        return ToolEnvelope[T](
            success=False,
            errorCode=exc.error_code,
            retryable=exc.retryable,
            latencyMs=_elapsed_ms(started_at),
            traceId=exc.trace_id,
        )
    except UnsafeRequestParameterError as exc:
        return ToolEnvelope[T](
            success=False,
            errorCode=exc.error_code,
            retryable=False,
            latencyMs=_elapsed_ms(started_at),
        )
    except CommerceTransportError as exc:
        return ToolEnvelope[T](
            success=False,
            errorCode="DEPENDENCY_UNAVAILABLE",
            retryable=exc.blind_retry_allowed,
            latencyMs=_elapsed_ms(started_at),
        )

    return ToolEnvelope[T](
        success=True,
        data=call.value,
        latencyMs=_elapsed_ms(started_at),
        traceId=call.trace_id,
    )


def _invalid_parameter(started: float) -> ToolEnvelope[T]:
    """Fail closed on a Tool input that cannot form a contract request."""
    return ToolEnvelope[T](
        success=False,
        errorCode="INVALID_PARAMETER",
        retryable=False,
        latencyMs=_elapsed_ms(started),
    )


def _elapsed_ms(started: float) -> int:
    """Return non-negative whole milliseconds for the stable Tool envelope."""
    return max(0, int((perf_counter() - started) * 1000))
