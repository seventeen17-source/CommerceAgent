# CommerceAgent Tool Contracts

Agent tools are business capabilities, not arbitrary HTTP access. The Python Agent may select a tool; Java business services remain authoritative for ownership, eligibility, amount, state transitions, approval and idempotency.

## Global tool envelope

All tools return a normalized envelope:

```json
{
  "success": true,
  "data": {},
  "errorCode": null,
  "retryable": false,
  "latencyMs": 42,
  "traceId": "..."
}
```

Global rules:
- no tool accepts arbitrary URLs, SQL or internal service names from model output;
- authentication principal is supplied by application context, not prompt text;
- read/write tools are separately registered and risk-labelled;
- every write carries `run_id` and stable idempotency context;
- write timeout recovery queries authoritative business state before any retry;
- validated parameters/results are traced with sensitive data minimized.

## T1 `list_user_orders`

Purpose: resolve ambiguous natural-language references to the authenticated user's recent orders.

Input:
- optional `created_after`
- optional `product_query`
- optional `status_filter`

Output:
- `order_id`
- product summary
- created timestamp
- fulfilment status

Risk: read / privacy medium.

Retry: one bounded retry for transient failure.

Forbidden: model-supplied arbitrary `user_id`.

## T2 `get_order`

Purpose: fetch authoritative order snapshot.

Input:
- `order_id`

Output:
- ownership-validated order status
- items/category
- amount/currency
- timestamps
- current after-sales state

Risk: read / privacy medium.

Errors: `ORDER_NOT_FOUND`, `ORDER_FORBIDDEN`, `DEPENDENCY_UNAVAILABLE`.

## T3 `get_logistics`

Purpose: fetch authoritative shipment state/events.

Input:
- `order_id`

Output:
- shipment status
- signed flag
- last meaningful event/time
- deterministic anomaly projection if available

Risk: read.

Retry: bounded transient retry.

Forbidden: inventing anomaly state when dependency is unavailable.

## T4 `policy_search`

Purpose: retrieve effective after-sales policy/SOP evidence.

Input:
- normalized query
- optional product category
- optional scenario tag
- effective date context

Output:
- document code/title/version
- section/chunk text
- effective metadata
- retrieval score
- citation id

Risk: read / untrusted text.

Boundary: retrieval may explain policy but never authorizes money/state changes.

## T5 `check_after_sales_eligibility`

Purpose: deterministic refund/return decision.

Input:
- `order_id`
- normalized reason code
- optional structured evidence references

Output:
- `eligible`
- `allowed_action`: `REFUND_ONLY | RETURN | RETURN_REFUND | MANUAL_REVIEW | DENY`
- `max_refund_amount`
- `approval_required`
- `rule_code`
- `rule_version`
- reason codes

Risk: critical read/decision.

Authority: Java backend.

Forbidden: model-provided eligibility or amount override.

## T6 `create_refund_request`

Purpose: create one validated refund request.

Input:
- `order_id`
- `reason_code`
- requested amount (must be bounded by server decision)
- `idempotency_key`
- optional approval reference/token

Output:
- refund request id
- accepted amount
- current status

Risk: high write.

Preconditions:
- authenticated owner;
- current order state valid;
- eligibility revalidated;
- amount valid;
- approval valid if required;
- no conflicting after-sales state.

Retry: never blind. Query status after ambiguous timeout; reuse same idempotency key only if safe.

Forbidden: cross-user refund, amount escalation, approval bypass.

## T7 `create_return_request`

Purpose: create validated return/return-refund workflow.

Input:
- `order_id`
- `reason_code`
- return method if applicable
- `idempotency_key`
- optional approval reference/token

Output:
- return request id
- state
- return deadline/instructions if applicable

Risk: write.

Preconditions: deterministic return eligibility, ownership, current state and window checks.

## T8 `create_support_ticket`

Purpose: safe escalation for unresolved/manual-review cases.

Input:
- optional `order_id`
- issue category
- structured evidence summary
- source/citation refs
- urgency

Output:
- ticket id
- status

Risk: medium write.

Automatic call: allowed when escalation is safer than continuing automation.

Forbidden: storing hidden chain-of-thought; only explicit evidence and structured reason codes.

## T9 `request_human_approval`

Purpose: create approval workflow for high-risk after-sales action.

Input:
- `run_id`
- `order_id`
- proposed action
- amount/risk summary
- evidence refs

Output:
- approval request id
- `PENDING`/`WAITING_APPROVAL` state

Risk: workflow write.

Forbidden: Agent self-approval or synthetic approval token.

## T10 `get_after_sales_status`

Purpose: verify writes and recover ambiguous outcomes.

Input:
- `order_id`
- optional refund/return/ticket id
- optional idempotency reference

Output:
- existing after-sales objects and statuses

Risk: read / privacy medium.

Use: mandatory before reissuing any write after timeout where commit success is unknown.

## Tool selection policy

The Agent may choose among registered tools based on evidence, but server-side checks always dominate. Tool selection must support at least these materially different paths:
- logistics anomaly → refund;
- delivered item → return;
- ambiguous order → clarification/no write;
- high-risk eligible action → approval;
- evidence unavailable/manual review → escalation/safe stop.
