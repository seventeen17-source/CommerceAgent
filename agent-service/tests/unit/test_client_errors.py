"""Unit tests for the typed Java API client failures.

These tests turn the read/write table in ``app/clients/errors.py`` into executable claims: whether
a retry may be blind depends on whether the outcome is *known* and whether the request had *side
effects* -- not on the HTTP method alone.
"""

from __future__ import annotations

import pytest

from app.clients.errors import CommerceApiError, CommerceError, CommerceTransportError


def test_api_error_exposes_envelope_fields() -> None:
    error = CommerceApiError(
        error_code="ORDER_FORBIDDEN",
        http_status=403,
        retryable=False,
        trace_id="trace-1",
        message="Order is not accessible to the authenticated user",
    )

    assert error.error_code == "ORDER_FORBIDDEN"
    assert error.http_status == 403
    assert error.trace_id == "trace-1"
    assert error.message == "Order is not accessible to the authenticated user"


def test_api_error_outcome_is_known() -> None:
    """The backend answered, therefore it did not commit."""
    error = CommerceApiError(error_code="INTERNAL_ERROR", http_status=500, retryable=False)

    assert error.outcome_unknown is False


def test_non_retryable_api_error_forbids_retry_even_for_a_safe_request() -> None:
    """A 403 on a GET stays forbidden no matter how often it is repeated."""
    error = CommerceApiError(error_code="ORDER_FORBIDDEN", http_status=403, retryable=False)

    assert error.blind_retry_allowed is False


def test_retryable_api_error_allows_retry_because_the_backend_answered() -> None:
    """A 503 means the write did not commit, so the outcome is known and a retry is safe."""
    error = CommerceApiError(error_code="UPSTREAM_UNAVAILABLE", http_status=503, retryable=True)

    assert error.blind_retry_allowed is True


def test_transport_error_outcome_is_unknown() -> None:
    error = CommerceTransportError(reason="read timeout", request_was_safe=True)

    assert error.outcome_unknown is True
    assert error.reason == "read timeout"


def test_transport_timeout_on_a_safe_request_may_be_retried() -> None:
    error = CommerceTransportError(reason="read timeout", request_was_safe=True)

    assert error.blind_retry_allowed is True


def test_transport_timeout_on_a_state_changing_request_must_not_be_retried_blindly() -> None:
    """This is the row that makes timeouts dangerous: the write may already have committed."""
    error = CommerceTransportError(reason="write timeout", request_was_safe=False)

    assert error.outcome_unknown is True
    assert error.blind_retry_allowed is False


@pytest.mark.parametrize(
    "error",
    [
        CommerceApiError(error_code="ORDER_FORBIDDEN", http_status=403, retryable=False),
        CommerceTransportError(reason="connection reset", request_was_safe=False),
    ],
)
def test_every_client_failure_is_a_commerce_error(error: CommerceError) -> None:
    assert isinstance(error, CommerceError)
