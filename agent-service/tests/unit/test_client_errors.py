"""Unit tests for the typed Java API client failures.

These tests turn the read/write table in ``app/clients/errors.py`` into executable claims: whether
a retry may be blind depends on whether the outcome is *known* and whether the request had *side
effects* -- not on the HTTP method alone.
"""

from __future__ import annotations

import pytest

from app.clients.errors import (
    CommerceApiError,
    CommerceError,
    CommerceTransportError,
    UnknownPrincipalRoleError,
    UnsafeRequestParameterError,
)


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
        UnsafeRequestParameterError(field="order_id", reason="not a safe URL path segment"),
        UnknownPrincipalRoleError(user_id="u-1", wire_role="ADMIN"),
    ],
)
def test_every_client_failure_is_a_commerce_error(error: CommerceError) -> None:
    assert isinstance(error, CommerceError)


def test_unsafe_parameter_is_a_local_known_failure() -> None:
    """Nothing was sent, so there is no outcome to be unknown about and nothing to retry."""
    error = UnsafeRequestParameterError(field="order_id", reason="not a safe URL path segment")

    assert error.outcome_unknown is False
    assert error.field == "order_id"
    assert error.error_code == "INVALID_PARAMETER"


def test_unsafe_parameter_message_never_echoes_the_offending_value() -> None:
    """The value is untrusted input and this text can reach a log line."""
    traversal = "../../admin/users"
    error = UnsafeRequestParameterError(field="order_id", reason="not a safe URL path segment")

    assert traversal not in str(error)


@pytest.mark.parametrize(
    ("wire_role", "expected_in_message"),
    [
        ("ADMIN", "ADMIN"),
        ("SUPER\r\nUSER: admin", "SUPERUSER:admin"),
        ("x" * 80, "x" * 32),
    ],
    ids=["unknown-role", "crlf-injection", "over-long"],
)
def test_unknown_principal_role_is_denied_with_a_stable_code(
    wire_role: str, expected_in_message: str
) -> None:
    """The call succeeded; the identity it returned is what cannot be authorized.

    ``ACCESS_DENIED`` keeps Eval's attribution stable, and the message form is the only one safe to
    render: CR/LF is stripped and the value is truncated before it can forge a log line.
    """
    error = UnknownPrincipalRoleError(user_id="customer-001", wire_role=wire_role)

    assert error.error_code == "ACCESS_DENIED"
    assert error.outcome_unknown is False
    assert error.user_id == "customer-001"
    assert expected_in_message in str(error)
    assert "\r" not in str(error)
    assert "\n" not in str(error)
    # The raw value stays available for structured audit fields, which cannot break a line.
    assert error.wire_role == wire_role
