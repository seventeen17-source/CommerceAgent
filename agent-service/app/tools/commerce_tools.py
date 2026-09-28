"""US1 Agent Tools backed by the typed Java CommerceClient."""

from __future__ import annotations

from time import perf_counter

from app.clients.auth import AuthContext
from app.clients.commerce_client import CommerceClient
from app.clients.errors import (
    CommerceApiError,
    CommerceTransportError,
    UnsafeRequestParameterError,
)
from app.clients.models import OrderSnapshot
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

    async def get_order(self, order_id: str) -> ToolEnvelope[OrderSnapshot]:
        """Return one ownership-validated authoritative order snapshot."""
        started = perf_counter()
        try:
            call = await self._client.get_order(self._auth, order_id)
        except CommerceApiError as exc:
            return ToolEnvelope[OrderSnapshot](
                success=False,
                errorCode=exc.error_code,
                retryable=exc.retryable,
                latencyMs=_elapsed_ms(started),
                traceId=exc.trace_id,
            )
        except UnsafeRequestParameterError as exc:
            return ToolEnvelope[OrderSnapshot](
                success=False,
                errorCode=exc.error_code,
                retryable=False,
                latencyMs=_elapsed_ms(started),
            )
        except CommerceTransportError as exc:
            return ToolEnvelope[OrderSnapshot](
                success=False,
                errorCode="DEPENDENCY_UNAVAILABLE",
                retryable=exc.blind_retry_allowed,
                latencyMs=_elapsed_ms(started),
            )

        return ToolEnvelope[OrderSnapshot](
            success=True,
            data=call.value,
            latencyMs=_elapsed_ms(started),
            traceId=call.trace_id,
        )


def _elapsed_ms(started: float) -> int:
    """Return non-negative whole milliseconds for the stable Tool envelope."""
    return max(0, int((perf_counter() - started) * 1000))
