"""Response and request models for the Java business API (read / evaluation surface).

Naming: Python attributes are ``snake_case`` and the wire format is ``camelCase``, so every field
carries an alias. ``populate_by_name=True`` also lets tests and internal callers use the Python
name.

Why ``extra="ignore"`` here while ``AgentState`` uses ``extra="forbid"``
-----------------------------------------------------------------------
``app/agent/state.py`` uses ``extra="forbid"`` because *this* service builds that object: an
undeclared field there is a bug or an injection attempt and must fail loudly. These models describe
*another* service's responses, so the same setting would do the opposite of what we want -- a
backend that adds a field would turn a healthy response into a parse failure. Remote additive
changes are tolerated here; the forward-compatibility policy is applied by the caller instead.

Validation still happens, but on *shape* rather than on *value*: ``allowed_action`` is constrained
to a non-empty bounded string while its value set stays open, because that set is owned by Java
(``AllowedAction.java`` + the V001 CHECK constraint). An unknown value must reach the caller so it
can degrade to ``SAFE_STOP`` with a reason code, exactly as the cross-service value policy in
``app/agent/state.py`` requires. A strict enum here would turn a benign additive backend rollout
into an unparseable response.

``PrincipalRole`` is the one value set taken as a strict enum, imported rather than re-declared so
there is only one copy. That follows T015's explicit decision that the principal role is a set this
service owns and must branch on exhaustively for authorization.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.agent.state import PrincipalRole

__all__ = [
    "CurrentPrincipal",
    "EligibilityDecision",
    "EligibilityRequest",
    "ErrorEnvelope",
    "LogisticsSnapshot",
    "OrderItem",
    "OrderSnapshot",
    "OrderSummary",
]

# Responses come from Java: tolerate additive fields rather than failing the call.
_RESPONSE = ConfigDict(extra="ignore", populate_by_name=True)
# Requests are built here: an undeclared field is our bug and must fail loudly.
_REQUEST = ConfigDict(extra="forbid", populate_by_name=True)


class CurrentPrincipal(BaseModel):
    """``GET /me`` -- authoritative identity resolved by Java from the verified JWT subject."""

    model_config = _RESPONSE

    user_id: str = Field(alias="userId", min_length=1, max_length=64)
    role: PrincipalRole


class OrderSummary(BaseModel):
    """``GET /orders`` -- one row of the authenticated customer's order list."""

    model_config = _RESPONSE

    order_id: str = Field(alias="orderId", min_length=1, max_length=64)
    product_summary: str = Field(alias="productSummary")
    status: str
    created_at: datetime = Field(alias="createdAt")


class OrderItem(BaseModel):
    """One line item inside an order snapshot.

    Every property is optional in the contract, so every field here is optional too: the client
    must not invent a stricter requirement than the authority publishes.
    """

    model_config = _RESPONSE

    product_id: str | None = Field(default=None, alias="productId")
    product_name: str | None = Field(default=None, alias="productName")
    product_category: str | None = Field(default=None, alias="productCategory")
    quantity: int | None = None


class OrderSnapshot(BaseModel):
    """``GET /orders/{orderId}`` -- authoritative order snapshot."""

    model_config = _RESPONSE

    order_id: str = Field(alias="orderId", min_length=1, max_length=64)
    status: str
    # Money is Decimal, never float: binary floating point cannot represent 0.10 exactly and this
    # value can end up in a refund decision.
    total_amount: Decimal = Field(alias="totalAmount")
    currency: str = Field(min_length=3, max_length=3)
    items: list[OrderItem] = Field(default_factory=list)
    after_sales_status: str | None = Field(default=None, alias="afterSalesStatus")


class LogisticsSnapshot(BaseModel):
    """``GET /orders/{orderId}/logistics`` -- authoritative logistics snapshot."""

    model_config = _RESPONSE

    status: str
    signed: bool
    last_meaningful_event_at: datetime | None = Field(default=None, alias="lastMeaningfulEventAt")
    stalled_hours: int | None = Field(default=None, alias="stalledHours")


class EligibilityRequest(BaseModel):
    """``POST /after-sales/eligibility`` request body.

    This endpoint uses POST but is a deterministic, side-effect free evaluation, not a write.
    """

    model_config = _REQUEST

    order_id: str = Field(alias="orderId", min_length=1, max_length=64)
    reason_code: str = Field(alias="reasonCode", min_length=1, max_length=100)


class EligibilityDecision(BaseModel):
    """``POST /after-sales/eligibility`` -- deterministic eligibility decision.

    ``allowed_action`` is Java-owned and deliberately an open string; see the module docstring.
    """

    model_config = _RESPONSE

    eligible: bool
    allowed_action: str = Field(alias="allowedAction", min_length=1, max_length=32)
    max_refund_amount: Decimal | None = Field(default=None, alias="maxRefundAmount")
    approval_required: bool = Field(alias="approvalRequired")
    rule_code: str = Field(alias="ruleCode", min_length=1, max_length=100)
    rule_version: int = Field(alias="ruleVersion", ge=1)
    reason_codes: list[str] = Field(default_factory=list, alias="reasonCodes")


class ErrorEnvelope(BaseModel):
    """The machine-readable error body every endpoint returns on failure.

    ``retryable`` is a statement by the backend that the request did not take effect and may be
    repeated. It is never authority to retry without a budget: see
    ``contracts/error-contracts.md``.
    """

    model_config = _RESPONSE

    error_code: str = Field(alias="errorCode", min_length=1, max_length=100)
    message: str = Field(default="")
    retryable: bool
    trace_id: str = Field(alias="traceId", min_length=1, max_length=128)
    details: dict[str, object] = Field(default_factory=dict)
