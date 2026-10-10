"""US1 Agent Tools backed by the typed Java CommerceClient."""

from __future__ import annotations

from collections.abc import Awaitable
from decimal import Decimal
from time import perf_counter

from pydantic import ValidationError

from app.clients.auth import AuthContext
from app.clients.commerce_client import CommerceCall, CommerceClient
from app.clients.errors import (
    CommerceApiError,
    CommerceTransportError,
    UnsafeRequestParameterError,
)
from app.clients.models import (
    AfterSalesStatus,
    ApprovalResult,
    CreateApprovalRequest,
    CreateRefundRequest,
    CreateReturnRequest,
    CreateTicketRequest,
    EligibilityDecision,
    EligibilityRequest,
    LogisticsSnapshot,
    OrderSnapshot,
    OrderSummary,
    RefundResult,
    ReturnResult,
    TicketResult,
)
from app.tools.models import ToolEnvelope

__all__ = ["CommerceTools"]


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
            request = EligibilityRequest.model_validate(
                {"orderId": order_id, "reasonCode": reason_code}
            )
        except ValidationError:
            return _invalid_parameter(started)

        return await _read_tool(
            self._client.check_eligibility(self._auth, request),
            started=started,
        )

    async def request_human_approval(
        self,
        *,
        run_id: str,
        order_id: str,
        action_type: str,
        amount: Decimal | None,
        risk_reason: str,
    ) -> ToolEnvelope[ApprovalResult]:
        """Create one authoritative PENDING approval request in Java.

        The signature deliberately has no status, approver, expiry, user id, token, or URL. The
        Agent can only submit the exact proposal it already received from Java eligibility; Java
        re-runs that decision and either returns a real ApprovalRequest or refuses the call.
        """
        started = perf_counter()
        try:
            request = CreateApprovalRequest.model_validate(
                {
                    "runId": run_id,
                    "orderId": order_id,
                    "actionType": action_type,
                    "amount": amount,
                    "riskReason": risk_reason,
                }
            )
            call = await self._client.create_approval(self._auth, request)
        except ValidationError:
            return _invalid_parameter(started)
        except UnsafeRequestParameterError as exc:
            return ToolEnvelope[ApprovalResult](
                success=False,
                errorCode=exc.error_code,
                retryable=False,
                latencyMs=_elapsed_ms(started),
            )
        except CommerceApiError as exc:
            return ToolEnvelope[ApprovalResult](
                success=False,
                errorCode=exc.error_code,
                retryable=exc.retryable,
                latencyMs=_elapsed_ms(started),
                traceId=exc.trace_id,
            )
        except CommerceTransportError:
            return ToolEnvelope[ApprovalResult](
                success=False,
                errorCode="WRITE_TIMEOUT_UNKNOWN",
                retryable=False,
                latencyMs=_elapsed_ms(started),
            )

        return ToolEnvelope[ApprovalResult](
            success=True,
            data=call.value,
            latencyMs=_elapsed_ms(started),
            traceId=call.trace_id,
        )

    async def create_support_ticket(
        self,
        *,
        run_id: str,
        order_id: str | None,
        category: str,
        reason_code: str,
        evidence_summary: str,
    ) -> ToolEnvelope[TicketResult]:
        """Create a Java-owned OPEN ticket once; never blindly retry unknown writes."""
        started = perf_counter()
        try:
            request = CreateTicketRequest.model_validate(
                {
                    "runId": run_id,
                    "orderId": order_id,
                    "category": category,
                    "reasonCode": reason_code,
                    "evidenceSummary": evidence_summary,
                }
            )
            call = await self._client.create_support_ticket(self._auth, request)
        except ValidationError:
            return _invalid_parameter(started)
        except UnsafeRequestParameterError as exc:
            return ToolEnvelope[TicketResult](
                success=False,
                errorCode=exc.error_code,
                retryable=False,
                latencyMs=_elapsed_ms(started),
            )
        except CommerceApiError as exc:
            return ToolEnvelope[TicketResult](
                success=False,
                errorCode=exc.error_code,
                retryable=False,
                latencyMs=_elapsed_ms(started),
                traceId=exc.trace_id,
            )
        except CommerceTransportError:
            return ToolEnvelope[TicketResult](
                success=False,
                errorCode="WRITE_TIMEOUT_UNKNOWN",
                retryable=False,
                latencyMs=_elapsed_ms(started),
            )
        return ToolEnvelope[TicketResult](
            success=True,
            data=call.value,
            latencyMs=_elapsed_ms(started),
            traceId=call.trace_id,
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
        """Attempt one protected refund write without performing any blind retry.

        A transport failure here means the business outcome is unknown: Java may already have
        committed. The Tool therefore returns WRITE_TIMEOUT_UNKNOWN with retryable=False. T031 must
        first call get_after_sales_status with the same idempotency key before deciding whether a
        same-key retry is safe.
        """
        started = perf_counter()
        try:
            request = CreateRefundRequest.model_validate(
                {
                    "orderId": order_id,
                    "reasonCode": reason_code,
                    "requestedAmount": requested_amount,
                    "approvalRequestId": approval_request_id,
                    "runId": run_id,
                }
            )
            call = await self._client.create_refund(
                self._auth,
                idempotency_key=idempotency_key,
                request=request,
            )
        except ValidationError:
            return _invalid_parameter(started)
        except UnsafeRequestParameterError as exc:
            return ToolEnvelope[RefundResult](
                success=False,
                errorCode=exc.error_code,
                retryable=False,
                latencyMs=_elapsed_ms(started),
            )
        except CommerceApiError as exc:
            return ToolEnvelope[RefundResult](
                success=False,
                errorCode=exc.error_code,
                retryable=exc.retryable,
                latencyMs=_elapsed_ms(started),
                traceId=exc.trace_id,
            )
        except CommerceTransportError:
            return ToolEnvelope[RefundResult](
                success=False,
                errorCode="WRITE_TIMEOUT_UNKNOWN",
                retryable=False,
                latencyMs=_elapsed_ms(started),
            )

        return ToolEnvelope[RefundResult](
            success=True,
            data=call.value,
            latencyMs=_elapsed_ms(started),
            traceId=call.trace_id,
        )

    async def create_return_request(
        self,
        *,
        order_id: str,
        reason_code: str,
        idempotency_key: str,
        run_id: str,
        return_method: str | None = None,
        approval_request_id: str | None = None,
    ) -> ToolEnvelope[ReturnResult]:
        """Attempt one protected return write without performing any blind retry.

        The envelope rule is identical to the refund tool's, and for the same reason: a transport
        failure means the return row may already exist, so this is reported as
        ``WRITE_TIMEOUT_UNKNOWN`` with ``retryable=False`` and the caller must read authoritative
        after-sales state (same key) before retrying.

        Note what the signature cannot express: an amount. A return never moves money, so "how much"
        is absent from the type rather than merely ignored -- the return row has no amount column
        either (V004).
        """
        started = perf_counter()
        try:
            request = CreateReturnRequest.model_validate(
                {
                    "orderId": order_id,
                    "reasonCode": reason_code,
                    "returnMethod": return_method,
                    "approvalRequestId": approval_request_id,
                    "runId": run_id,
                }
            )
            call = await self._client.create_return(
                self._auth,
                idempotency_key=idempotency_key,
                request=request,
            )
        except ValidationError:
            return _invalid_parameter(started)
        except UnsafeRequestParameterError as exc:
            return ToolEnvelope[ReturnResult](
                success=False,
                errorCode=exc.error_code,
                retryable=False,
                latencyMs=_elapsed_ms(started),
            )
        except CommerceApiError as exc:
            return ToolEnvelope[ReturnResult](
                success=False,
                errorCode=exc.error_code,
                retryable=exc.retryable,
                latencyMs=_elapsed_ms(started),
                traceId=exc.trace_id,
            )
        except CommerceTransportError:
            return ToolEnvelope[ReturnResult](
                success=False,
                errorCode="WRITE_TIMEOUT_UNKNOWN",
                retryable=False,
                latencyMs=_elapsed_ms(started),
            )

        return ToolEnvelope[ReturnResult](
            success=True,
            data=call.value,
            latencyMs=_elapsed_ms(started),
            traceId=call.trace_id,
        )


async def _read_tool[T](
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


def _invalid_parameter[T](started: float) -> ToolEnvelope[T]:
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
