"""Unit tests for the Java API response/request models.

The interesting cases are not the happy paths but the two forward-compatibility rules agreed for
T016: an unknown value in a *Java-owned* value set must reach the caller, and an additive field on
a remote response must not break parsing. Both are asserted here, because both are the kind of
decision that silently rots otherwise.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.clients.models import (
    CurrentPrincipal,
    EligibilityDecision,
    EligibilityRequest,
    ErrorEnvelope,
    LogisticsSnapshot,
    OrderSnapshot,
    OrderSummary,
)


def test_current_principal_parses_camel_case() -> None:
    principal = CurrentPrincipal.model_validate({"userId": "customer-001", "role": "CUSTOMER"})

    assert principal.user_id == "customer-001"
    assert principal.role == "CUSTOMER"


def test_unrecognised_principal_role_reaches_the_caller() -> None:
    """The identity layer, not the parser, decides what an unknown role means.

    Failing here would stop the run from being created at all: no SAFE_STOP, no reason code and no
    audit record. The value must survive so authorization can deny it explicitly.
    """
    principal = CurrentPrincipal.model_validate({"userId": "u-1", "role": "ADMIN"})

    assert principal.role == "ADMIN"


def test_models_accept_python_field_names_too() -> None:
    principal = CurrentPrincipal(user_id="customer-001", role="APPROVER")

    assert principal.user_id == "customer-001"


def test_order_summary_parses_created_at() -> None:
    summary = OrderSummary.model_validate(
        {
            "orderId": "O-1",
            "productSummary": "Wireless headphones",
            "status": "DELIVERED",
            "createdAt": "2026-09-01T10:00:00Z",
        }
    )

    assert summary.order_id == "O-1"
    assert summary.created_at.year == 2026


def test_order_snapshot_keeps_money_as_exact_decimal() -> None:
    """A float would carry binary rounding error into a refund decision."""
    snapshot = OrderSnapshot.model_validate(
        {
            "orderId": "O-1",
            "status": "DELIVERED",
            "totalAmount": 19.99,
            "currency": "CNY",
            "items": [{"productId": "P-1", "quantity": 2}],
            "afterSalesStatus": None,
        }
    )

    assert snapshot.total_amount == Decimal("19.99")
    assert snapshot.items[0].quantity == 2
    assert snapshot.items[0].product_name is None
    assert snapshot.after_sales_status is None


def test_logistics_snapshot_allows_null_timestamps() -> None:
    snapshot = LogisticsSnapshot.model_validate(
        {"status": "IN_TRANSIT", "signed": False, "lastMeaningfulEventAt": None, "stalledHours": 72}
    )

    assert snapshot.signed is False
    assert snapshot.stalled_hours == 72


def test_eligibility_decision_carries_the_deterministic_rule_identity() -> None:
    decision = EligibilityDecision.model_validate(
        {
            "eligible": True,
            "allowedAction": "REFUND_ONLY",
            "maxRefundAmount": 19.99,
            "approvalRequired": False,
            "ruleCode": "LOGISTICS_STALLED_REFUND",
            "ruleVersion": 1,
            "reasonCodes": ["LOGISTICS_STALLED"],
        }
    )

    assert decision.allowed_action == "REFUND_ONLY"
    assert decision.rule_version == 1
    assert decision.max_refund_amount == Decimal("19.99")


def test_unknown_java_owned_allowed_action_reaches_the_caller() -> None:
    """A strict enum here would turn an additive backend release into a parse failure.

    The value must survive so the caller can degrade to SAFE_STOP with a reason code, and Eval can
    tell 'the backend added a value' apart from 'the payload is corrupt'.
    """
    decision = EligibilityDecision.model_validate(
        {
            "eligible": True,
            "allowedAction": "PARTIAL_REFUND",
            "approvalRequired": True,
            "ruleCode": "LOGISTICS_STALLED_REFUND",
            "ruleVersion": 2,
        }
    )

    assert decision.allowed_action == "PARTIAL_REFUND"


def test_additive_response_field_is_tolerated() -> None:
    """Responses come from another service, so an added field must not fail the call."""
    principal = CurrentPrincipal.model_validate(
        {"userId": "customer-001", "role": "CUSTOMER", "loyaltyTier": "GOLD"}
    )

    assert principal.user_id == "customer-001"
    assert not hasattr(principal, "loyalty_tier")


def test_additive_request_field_is_rejected() -> None:
    """The request body is built here, so an undeclared field is our bug."""
    with pytest.raises(ValidationError):
        EligibilityRequest.model_validate(
            {"orderId": "O-1", "reasonCode": "LOGISTICS_STALLED", "extra": "nope"}
        )


def test_missing_required_field_is_rejected() -> None:
    with pytest.raises(ValidationError):
        EligibilityDecision.model_validate(
            {
                "eligible": True,
                "allowedAction": "REFUND_ONLY",
                "approvalRequired": False,
                "ruleCode": "LOGISTICS_STALLED_REFUND",
            }
        )


def test_rule_version_must_be_a_positive_integer() -> None:
    """The contract previously declared this as a string; the hardening fixed it to integer >= 1."""
    with pytest.raises(ValidationError):
        EligibilityDecision.model_validate(
            {
                "eligible": True,
                "allowedAction": "REFUND_ONLY",
                "approvalRequired": False,
                "ruleCode": "LOGISTICS_STALLED_REFUND",
                "ruleVersion": 0,
            }
        )


def test_error_envelope_parses_the_error_contract() -> None:
    envelope = ErrorEnvelope.model_validate(
        {
            "errorCode": "ORDER_FORBIDDEN",
            "message": "Order is not accessible to the authenticated user",
            "retryable": False,
            "traceId": "trace-1",
        }
    )

    assert envelope.error_code == "ORDER_FORBIDDEN"
    assert envelope.retryable is False
    assert envelope.trace_id == "trace-1"
    assert envelope.details == {}
