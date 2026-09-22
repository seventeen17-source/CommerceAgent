"""Typed async client for the Java business API (read / evaluation / write surface).

T016 delivered the read/evaluation surface (``GET /me``, ``GET /orders``,
``GET /orders/{orderId}``, ``GET /orders/{orderId}/logistics``,
``POST /after-sales/eligibility``). T022 adds the first two write-surface calls: ``POST /refunds``
and ``GET /orders/{orderId}/after-sales``.

Six rules this module enforces once, instead of once per tool
--------------------------------------------------------------
1. **Forward a credential, never assert an identity.** Every call carries the caller's Bearer token
   (:class:`~app.clients.auth.AuthContext`); ``userId``/``role`` come back from Java. There is no
   ``user_id`` parameter here to get wrong.
2. **The trace id is generated per call, inside this module.** No public method accepts one, so
   model output cannot supply it. It is returned with the result so T017 can persist
   ``run_id + step_index + trace_id``.
3. **"Answered" and "did not answer" stay different types** -- see ``errors.py``.
4. **This client never retries.** ``retryable=true`` is not authority to retry: error-contracts rule
   1 gives every Tool a finite retry budget, and a retry loop in here would hide the unknown-outcome
   case from the only layer allowed to decide what to do about it.
5. **Ambient configuration cannot reroute the call.** The client is built with ``trust_env=False``,
   so no environment or OS-level proxy can silently put itself between the Agent and the one service
   allowed to state business facts -- and receive the forwarded Bearer token on the way.
6. **A state-changing call says so in its type.** ``request_is_safe=False`` on
   :meth:`CommerceClient.create_refund` is what makes a timeout there an *unknown outcome*
   instead of a free retry. Deriving that from ``method == "POST"`` would be wrong twice over: it
   would strip the retry budget from ``POST /after-sales/eligibility`` (side-effect free) and it
   would teach the next reader that an HTTP verb decides authorization.

Java analogy: a singleton ``RestClient`` bean -- one connection pool, lifecycle owned by the
application (here the FastAPI lifespan, T018), ``Authorization`` set per exchange rather than as a
default header, because that pool is shared by every user of this process. The analogy breaks on
identity: Spring hands a controller an already-resolved ``@AuthenticationPrincipal``; a *client* has
to forward the token and ask Java who it belongs to.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from types import TracebackType
from typing import TYPE_CHECKING, Any, Self
from uuid import uuid4

import httpx
from pydantic import BaseModel, ValidationError

from app.clients.auth import AuthContext
from app.clients.errors import (
    CommerceApiError,
    CommerceError,
    CommerceTransportError,
    UnsafeRequestParameterError,
)
from app.clients.models import (
    AfterSalesStatus,
    CreateRefundRequest,
    CurrentPrincipal,
    EligibilityDecision,
    EligibilityRequest,
    ErrorEnvelope,
    LogisticsSnapshot,
    OrderSnapshot,
    OrderSummary,
    RefundResult,
)

if TYPE_CHECKING:
    from app.config.settings import Settings

__all__ = ["TRACE_ID_HEADER", "CommerceCall", "CommerceClient"]

logger = logging.getLogger(__name__)

#: Correlation header. Java's ``TraceIdFilter`` uses the same name; T016 also tightens that filter
#: to accept an inbound id only after format/length validation, and to generate one otherwise.
TRACE_ID_HEADER = "X-Trace-Id"

#: Idempotency header, required by the contract on ``POST /refunds`` (and ``POST /returns``).
IDEMPOTENCY_KEY_HEADER = "Idempotency-Key"

#: ``commerce_api_base_url`` is the service root; the contract's server URL adds this prefix.
_API_PREFIX = "/api/v1"

#: Ids we generate are ``uuid4().hex``; this wider pattern is what we accept *back* from Java.
_TRACE_ID_PATTERN = re.compile(r"^[A-Za-z0-9._-]{8,128}$")

#: An interpolated path segment must start alphanumerically (so ``.`` and ``..`` are impossible) and
#: stay inside a charset that cannot express ``/``, ``?``, ``#`` or whitespace. 64 matches
#: ``commerce.orders.id``; ``order-001`` and ``demo-order-stalled-001`` both fit.
_PATH_SEGMENT_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")

#: The idempotency-key charset Java accepts (``Idempotency-Key`` is 8-128 of ``[A-Za-z0-9_-]``).
#: Mirrored here so a malformed key fails *before* the money endpoint is called. Dots are excluded
#: on the Java side precisely so that a JWT-shaped string cannot be stored as a key; keeping the
#: same charset here means that mistake is caught locally instead of becoming a 400 mid-run.
_IDEMPOTENCY_KEY_PATTERN = re.compile(r"^[A-Za-z0-9_-]{8,128}$")


def _safe_idempotency_key(value: str) -> str:
    """Reject an idempotency key this process must not send.

    The key identifies a money write *and* is persisted
    (``commerce.refund_requests.idempotency_key``, plus the Agent's own state). A key that Java
    would reject, or that could not be safely logged, is our bug and must fail before the request
    leaves the process.
    """
    if _IDEMPOTENCY_KEY_PATTERN.fullmatch(value) is None:
        raise UnsafeRequestParameterError(
            field="idempotency_key", reason="must be 8-128 characters of [A-Za-z0-9_-]"
        )
    return value


def _safe_path_segment(value: str, *, field: str) -> str:
    """Reject a value that could turn a path parameter into a different URL.

    The allowed charset needs no percent-encoding, so what is returned is exactly what is sent.
    """
    if _PATH_SEGMENT_PATTERN.fullmatch(value) is None:
        raise UnsafeRequestParameterError(field=field, reason="not a safe URL path segment")
    return value


def _validation_summary(exc: ValidationError) -> str:
    """Field paths and error types only -- never the offending values.

    ``str(ValidationError)`` echoes the input, and this text lands in logs and in the T017 tool
    trace. Order amounts, product names and user ids are business data, not diagnostics.
    """
    return ", ".join(
        f"{'.'.join(str(part) for part in error['loc'])}={error['type']}" for error in exc.errors()
    )


def _parse[T: BaseModel](payload: Any, model: type[T], *, path: str, request_is_safe: bool) -> T:
    """Validate one response body, or report that no authoritative answer arrived.

    A 200 that breaks the contract is treated as "no answer" rather than as a backend error: the
    payload cannot be trusted, so the caller must not act on it. ``T`` is constrained to
    ``BaseModel`` because this function calls ``model_validate`` on it: the bound is what makes
    that legal.
    """
    try:
        return model.model_validate(payload)
    except ValidationError as exc:
        # The cause is chained for local debugging only; the trace persists ``reason``, which is why
        # the summary above excludes input values.
        raise CommerceTransportError(
            reason=f"{path} response did not match {model.__name__}: {_validation_summary(exc)}",
            request_was_safe=request_is_safe,
        ) from exc


@dataclass(frozen=True)
class _RawResponse:
    payload: Any
    trace_id: str
    status_code: int


@dataclass(frozen=True)
class CommerceCall[T]:
    """One completed call: the validated value plus the facts T017 must persist.

    ``trace_id`` is part of the *success* path on purpose. ``agent.tool_executions`` stores
    ``run_id + step_index + trace_id`` so a failed run can be tied to one specific Java request, and
    the Tool envelope in ``contracts/tool-contracts.md`` reports ``traceId`` on success too. It is
    the id Java logged, which is why :meth:`CommerceClient._correlate` prefers the reflected header.
    """

    value: T
    trace_id: str
    status_code: int


class CommerceClient:
    """Long-lived, connection-pooling client for the Java business API.

    One instance per process, created at startup and closed at shutdown (T018 wires this to the
    FastAPI lifespan). The instance holds *no* credential: the token is a per-call argument, so a
    pooled connection can never carry one user's authorization into another user's request.
    """

    def __init__(
        self,
        *,
        base_url: str,
        timeout_seconds: float,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        """Create the client.

        ``timeout_seconds`` is applied to *every* phase (connect / read / write / pool) by passing a
        single float to :class:`httpx.Timeout`. That is deliberate: a phase left at its default can
        wait forever, and an unbounded wait is how a stalled dependency turns into an exhausted
        worker pool. ``transport`` exists so tests can inject :class:`httpx.MockTransport`.
        """
        self._http = httpx.AsyncClient(
            base_url=base_url,
            timeout=httpx.Timeout(timeout_seconds),
            transport=transport,
            # Fail closed on ambient routing: httpx would otherwise resolve a proxy from the
            # environment -- and on Windows `urllib.request.getproxies()` also reads the *registry*
            # proxy, so no HTTP_PROXY variable has to exist for a machine-level setting to take
            # over. Observed live on 2026-09-20: a system proxy at 127.0.0.1:7892 answered for
            # `http://localhost:8080`, received the user's Bearer token, and returned its own 502
            # outside the error contract. Reaching Java is the Agent's only authority channel, so a
            # proxy must be a deliberate choice here, not whatever the machine is configured with.
            # Cost, stated for whoever needs it: `trust_env=False` also stops httpx from honouring
            # SSL_CERT_FILE / SSL_CERT_DIR, so a private CA for an HTTPS Java endpoint has to be
            # passed explicitly instead of through the environment.
            trust_env=False,
        )

    @classmethod
    def from_settings(
        cls, settings: Settings, *, transport: httpx.AsyncBaseTransport | None = None
    ) -> Self:
        """Build the client from configuration.

        The configured base URL is the service root (``http://localhost:8080``) while the contract's
        server URL carries ``/api/v1``, so the prefix is joined here. The trailing slash is stripped
        first to keep the result stable if the environment variable ever gains one.
        """
        return cls(
            base_url=settings.commerce_api_base_url.rstrip("/") + _API_PREFIX,
            timeout_seconds=settings.commerce_api_timeout_seconds,
            transport=transport,
        )

    async def aclose(self) -> None:
        """Release the connection pool. Idempotent; called from the lifespan shutdown hook."""
        await self._http.aclose()

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        await self.aclose()

    # ---- read / evaluation surface ---------------------------------------------------------

    async def get_principal(self, auth: AuthContext) -> CommerceCall[CurrentPrincipal]:
        """``GET /me`` -- who Java says this token belongs to.

        The returned ``role`` is still the open wire string; call
        :func:`app.clients.identity.resolve_principal` to turn it into a ``PrincipalContext``.
        """
        return await self._request(
            "GET", "/me", auth, response_model=CurrentPrincipal, request_is_safe=True
        )

    async def list_orders(
        self,
        auth: AuthContext,
        *,
        product_query: str | None = None,
        status_filter: str | None = None,
    ) -> CommerceCall[list[OrderSummary]]:
        """``GET /orders`` -- the authenticated customer's orders.

        Ownership is enforced by Java from the token; both filters are optional and omitted rather
        than sent as empty strings, because an empty ``status`` is not the same as no filter.
        """
        params: dict[str, str] = {}
        if product_query is not None:
            params["productQuery"] = product_query
        if status_filter is not None:
            params["status"] = status_filter
        return await self._request_list(
            "GET",
            "/orders",
            auth,
            item_model=OrderSummary,
            request_is_safe=True,
            params=params or None,
        )

    async def get_order(self, auth: AuthContext, order_id: str) -> CommerceCall[OrderSnapshot]:
        """``GET /orders/{orderId}`` -- the authoritative order snapshot."""
        segment = _safe_path_segment(order_id, field="order_id")
        return await self._request(
            "GET", f"/orders/{segment}", auth, response_model=OrderSnapshot, request_is_safe=True
        )

    async def get_logistics(
        self, auth: AuthContext, order_id: str
    ) -> CommerceCall[LogisticsSnapshot]:
        """``GET /orders/{orderId}/logistics`` -- the authoritative logistics snapshot.

        A ``LOGISTICS_UNAVAILABLE`` envelope from here is a *known* failure: the dependency said it
        could not answer, which is not the same as inventing an anomaly state.
        """
        segment = _safe_path_segment(order_id, field="order_id")
        return await self._request(
            "GET",
            f"/orders/{segment}/logistics",
            auth,
            response_model=LogisticsSnapshot,
            request_is_safe=True,
        )

    async def check_eligibility(
        self, auth: AuthContext, request: EligibilityRequest
    ) -> CommerceCall[EligibilityDecision]:
        """``POST /after-sales/eligibility`` -- deterministic, side-effect free evaluation.

        ``request_is_safe=True`` despite the POST: nothing is committed, so an unknown outcome costs
        one wasted call. Deriving safety from the method instead would strip this read of its retry
        budget and, worse, would teach the next person to write ``method == "GET"`` for the T026
        write endpoints, where the answer must be ``False``. See the table in ``errors.py``.

        The body is built from a validated ``EligibilityRequest`` (``extra="forbid"``), so an
        undeclared field cannot ride along. Amounts are *not* sent: the backend computes
        ``maxRefundAmount`` and the Agent may not propose one.
        """
        return await self._request(
            "POST",
            "/after-sales/eligibility",
            auth,
            response_model=EligibilityDecision,
            request_is_safe=True,
            json_body=request.model_dump(by_alias=True, mode="json"),
        )

    # ---- write surface ---------------------------------------------------------------------

    async def create_refund(
        self,
        auth: AuthContext,
        *,
        idempotency_key: str,
        request: CreateRefundRequest,
    ) -> CommerceCall[RefundResult]:
        """``POST /refunds`` -- create (or replay) exactly one logical refund.

        ``request_is_safe=False`` is the whole point of this method's type: if no answer arrives,
        Java may or may not have committed, so **the caller must not simply call this again**. The
        authority layer for that decision is :mod:`app.agent.execute_write`, which reads
        ``GET /orders/{orderId}/after-sales`` first.

        The idempotency key travels as a header, not in the body, because it identifies *this
        logical request* rather than the business payload: two attempts at one refund share the
        key, and Java's conflict fingerprint deliberately excludes it. The key is shape-checked
        here so a malformed one never reaches the money endpoint -- nothing is sent at all.
        """
        key = _safe_idempotency_key(idempotency_key)
        return await self._request(
            "POST",
            "/refunds",
            auth,
            response_model=RefundResult,
            request_is_safe=False,
            json_body=request.model_dump(by_alias=True, mode="json"),
            extra_headers={IDEMPOTENCY_KEY_HEADER: key},
        )

    async def get_after_sales_status(
        self, auth: AuthContext, order_id: str
    ) -> CommerceCall[AfterSalesStatus]:
        """``GET /orders/{orderId}/after-sales`` -- did the write actually commit?

        This is the read half of unknown-outcome recovery, which is why it exists in the same change
        as the write. An **empty** ``refunds`` list is a positive statement ("no refund exists"),
        and that is the only thing that makes a same-key retry of a timed-out write safe.
        """
        segment = _safe_path_segment(order_id, field="order_id")
        return await self._request(
            "GET",
            f"/orders/{segment}/after-sales",
            auth,
            response_model=AfterSalesStatus,
            request_is_safe=True,
        )

    # ---- transport -------------------------------------------------------------------------

    async def _request[T: BaseModel](
        self,
        method: str,
        path: str,
        auth: AuthContext,
        *,
        response_model: type[T],
        request_is_safe: bool,
        json_body: dict[str, Any] | None = None,
        params: dict[str, str] | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> CommerceCall[T]:
        """Send one call and validate a single JSON object response against ``response_model``.

        ``response_model`` is a *type* parameter used at runtime, which is why it is keyword-only
        rather than inferred: every endpoint names its contract explicitly at the call site.

        ``extra_headers`` exists for contract-mandated headers such as ``Idempotency-Key``. It is a
        narrow channel: the caller cannot override ``Authorization`` or the correlation id through
        it (see :meth:`_send`).
        """
        raw = await self._send(
            method,
            path,
            auth,
            request_is_safe=request_is_safe,
            json_body=json_body,
            params=params,
            extra_headers=extra_headers,
        )
        return CommerceCall(
            value=_parse(raw.payload, response_model, path=path, request_is_safe=request_is_safe),
            trace_id=raw.trace_id,
            status_code=raw.status_code,
        )

    async def _request_list[T: BaseModel](
        self,
        method: str,
        path: str,
        auth: AuthContext,
        *,
        item_model: type[T],
        request_is_safe: bool,
        params: dict[str, str] | None = None,
    ) -> CommerceCall[list[T]]:
        """Send one call and validate a JSON array response, item by item.

        The array check is explicit rather than implicit in Pydantic: a ``{}`` where the contract
        declares ``[OrderSummary]`` would otherwise surface as a confusing model error. Item
        validation carries its index in ``path``, so a malformed third order is reported as
        ``/orders[2]`` and not as "some order was wrong".
        """
        raw = await self._send(
            method, path, auth, request_is_safe=request_is_safe, json_body=None, params=params
        )
        if not isinstance(raw.payload, list):
            raise CommerceTransportError(
                reason=(
                    f"{path} returned a JSON {type(raw.payload).__name__} "
                    "where the contract declares an array"
                ),
                request_was_safe=request_is_safe,
            )
        items = [
            _parse(item, item_model, path=f"{path}[{index}]", request_is_safe=request_is_safe)
            for index, item in enumerate(raw.payload)
        ]
        return CommerceCall(value=items, trace_id=raw.trace_id, status_code=raw.status_code)

    async def _send(
        self,
        method: str,
        path: str,
        auth: AuthContext,
        *,
        request_is_safe: bool,
        json_body: dict[str, Any] | None,
        params: dict[str, str] | None,
        extra_headers: dict[str, str] | None = None,
    ) -> _RawResponse:
        """Perform one HTTP call and normalise every way it can fail.

        Only :class:`httpx.TransportError` is caught. A misconfigured ``base_url`` raises
        :class:`httpx.InvalidURL`, which is *not* a transport error and is allowed to propagate: it
        is our bug, it fails on every call, and reporting it as "the backend's outcome is unknown"
        would hide a configuration error inside a retry budget.
        """
        sent_trace_id = uuid4().hex
        headers = {
            "Accept": "application/json",
            # The only place the raw token is unwrapped. It is set per call, never as a client
            # default header, because the pool is shared by every user of this process.
            "Authorization": f"Bearer {auth.token.get_secret_value()}",
            TRACE_ID_HEADER: sent_trace_id,
        }
        if extra_headers:
            # Contract headers only. Authorization and the correlation id are set above and must not
            # be replaceable by a caller: the credential comes from the authenticated context, and a
            # trace id accepted from outside would let model output choose the id we persist.
            forbidden = {"authorization", TRACE_ID_HEADER.lower()} & {
                name.lower() for name in extra_headers
            }
            if forbidden:
                raise UnsafeRequestParameterError(
                    field="extra_headers", reason="may not override authenticated headers"
                )
            headers.update(extra_headers)
        try:
            response = await self._http.request(
                method, path, headers=headers, json=json_body, params=params
            )
        except httpx.TimeoutException as exc:
            # TimeoutException subclasses TransportError, so this branch must come first: "it took
            # too long" and "it never connected" are the same unknown outcome, different diagnosis.
            raise CommerceTransportError(
                reason=f"{method} {path} timed out; no answer arrived, so the outcome is unknown",
                request_was_safe=request_is_safe,
            ) from exc
        except httpx.TransportError as exc:
            raise CommerceTransportError(
                reason=f"{method} {path} got no answer ({type(exc).__name__}); outcome unknown",
                request_was_safe=request_is_safe,
            ) from exc

        trace_id = self._correlate(response, sent_trace_id)
        if not response.is_success:
            raise self._failure(
                response,
                method=method,
                path=path,
                request_is_safe=request_is_safe,
                trace_id=trace_id,
            )
        try:
            payload = response.json()
        except ValueError as exc:
            raise CommerceTransportError(
                reason=(
                    f"{method} {path} returned HTTP {response.status_code} with a body that is not "
                    "valid JSON"
                ),
                request_was_safe=request_is_safe,
            ) from exc
        logger.debug(
            "commerce api %s %s -> %s trace_id=%s", method, path, response.status_code, trace_id
        )
        return _RawResponse(payload=payload, trace_id=trace_id, status_code=response.status_code)

    def _correlate(self, response: httpx.Response, sent_trace_id: str) -> str:
        """Prefer the id Java logged, so a persisted trace id can actually find that request.

        Java's ``TraceIdFilter`` always sets ``X-Trace-Id`` on the response. Until T016's Java-side
        change lands it generates its own id and ignores ours, so the two differ; afterwards the
        reflected id is ours. Preferring the reflected value keeps one id space in both worlds and
        matches ``ErrorEnvelope.traceId``, which is Java's.

        The reflected value is shape-checked before being trusted: it is remote input that ends up
        in our logs and in ``agent.tool_executions.trace_id`` (a 128-char column), so CR/LF would
        forge log lines and an over-long value would not fit.
        """
        reflected: str | None = response.headers.get(TRACE_ID_HEADER)
        if reflected is None or _TRACE_ID_PATTERN.fullmatch(reflected) is None:
            return sent_trace_id
        if reflected != sent_trace_id:
            logger.warning(
                "commerce api replaced the correlation id: sent=%s logged=%s",
                sent_trace_id,
                reflected,
            )
        return reflected

    def _failure(
        self,
        response: httpx.Response,
        *,
        method: str,
        path: str,
        request_is_safe: bool,
        trace_id: str,
    ) -> CommerceError:
        """Map a non-2xx answer onto the taxonomy in ``errors.py``.

        An answer matching the error contract becomes :class:`CommerceApiError`: the backend stated
        ``errorCode`` and ``retryable``, so there is something stable to branch on. An answer that
        does *not* match it becomes :class:`CommerceTransportError` even though the server replied
        -- without ``retryable`` a bare status code proves nothing about a write, and calling that
        "known" would license a blind retry. Pessimistic, but never unsafe.
        """
        try:
            envelope = ErrorEnvelope.model_validate(response.json())
        except (ValueError, ValidationError):
            return CommerceTransportError(
                reason=(
                    f"{method} {path} returned HTTP {response.status_code} outside the error "
                    "contract; the outcome is unknown"
                ),
                request_was_safe=request_is_safe,
            )
        if envelope.trace_id != trace_id:
            # The response header is the correlation authority because _correlate() has already
            # shape-validated it (or fallen back to the id generated by this client). The JSON
            # envelope is still required by the error contract, but it must never overwrite the
            # identifier that T017 persists for cross-service diagnosis.
            #
            # Do not log the remote envelope value here: it has not been through the header-shape
            # validator and could contain control characters. The validated trace id is enough to
            # locate the request and to flag the contract drift.
            logger.warning(
                "commerce api error envelope trace id did not match the validated response "
                "correlation id; using trace_id=%s",
                trace_id,
            )
        return CommerceApiError(
            error_code=envelope.error_code,
            http_status=response.status_code,
            retryable=envelope.retryable,
            trace_id=trace_id,
            message=envelope.message,
        )
