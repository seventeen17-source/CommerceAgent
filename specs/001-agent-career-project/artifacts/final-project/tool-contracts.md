# CommerceAgent Tool Contracts

All write tools are enforced by the business backend. The Agent may select and propose an action; it cannot bypass ownership, eligibility, amount, state-transition, approval or idempotency checks.

## T1 `list_user_orders`
- **Business function**: list recent orders belonging to the authenticated user for order disambiguation.
- **Input**: `user_id`, optional time/product filters.
- **Output**: minimal order summaries (`order_id`, product summary, created_at, fulfilment state).
- **Property**: read-only.
- **Risk**: low/medium privacy.
- **Authorization**: caller may only access own orders.
- **Timeout/retry**: short timeout; one bounded retry.
- **Forbidden**: arbitrary user id supplied by prompt text.

## T2 `get_order`
- **Business function**: fetch authoritative order/item/fulfilment state.
- **Input**: `user_id`, `order_id`.
- **Output**: normalized order snapshot, product category, amount, timestamps, after-sales state.
- **Property**: read-only.
- **Risk**: medium privacy.
- **Authorization**: server verifies ownership.
- **Error types**: not found, forbidden, unavailable.

## T3 `get_logistics`
- **Business function**: fetch shipment status and logistics events.
- **Input**: `user_id`, `order_id` or shipment id resolved server-side.
- **Output**: signed flag, current status, last meaningful event, anomaly projection if deterministically available.
- **Property**: read-only.
- **Risk**: low/medium.
- **Timeout/retry**: bounded retry; no fabricated state when unavailable.

## T4 `policy_search`
- **Business function**: retrieve relevant after-sales policy/SOP passages with version/effective metadata.
- **Input**: normalized query plus optional product category / scenario tags.
- **Output**: cited chunks, document id, version/effective date, retrieval score.
- **Property**: read-only retrieval.
- **Risk**: low.
- **Automatic call**: allowed.
- **Important boundary**: retrieved text can explain policy but cannot authorize a refund/return.
- **Error handling**: conflicting/stale versions trigger deterministic effective-policy resolution or escalation.

## T5 `check_after_sales_eligibility`
- **Business function**: deterministic decision service for refund/return path and constraints.
- **Input**: authenticated `user_id`, `order_id`, normalized reason, optional evidence references.
- **Output**: `eligible`, `allowed_action` (`REFUND_ONLY`, `RETURN`, `RETURN_REFUND`, `MANUAL_REVIEW`, `DENY`), `max_refund_amount`, `approval_required`, `policy_code`, reason codes.
- **Property**: read-only deterministic decision.
- **Risk**: high importance but non-writing.
- **Authorization**: server-side ownership and state checks.
- **Retry**: safe bounded retry.
- **Forbidden**: model-provided amount/policy override.

## T6 `create_refund_request`
- **Business function**: create one refund request after deterministic eligibility and required approval.
- **Input**: `user_id`, `order_id`, `reason_code`, requested amount bounded by eligibility result, `idempotency_key`, optional `approval_token`.
- **Output**: `refund_request_id`, state, accepted amount, timestamps.
- **Property**: high-risk write.
- **Automatic call**: allowed only for configured low-risk eligible cases; otherwise approval required.
- **Validation**: ownership, order state, eligibility, amount, prior after-sales state and approval checked server-side.
- **Idempotency**: same logical request/key returns existing result rather than duplicating.
- **Timeout**: ambiguous completion must be recovered with status query before retry.
- **Forbidden**: changing amount above server max; bypassing approval; refunding another user's order.

## T7 `create_return_request`
- **Business function**: create return/return-refund workflow for delivered goods.
- **Input**: `user_id`, `order_id`, reason, return method, `idempotency_key`, optional approval token.
- **Output**: `return_request_id`, state, return instructions if applicable.
- **Property**: write.
- **Validation**: deterministic eligibility/state/window/product constraints.
- **Idempotency**: required.
- **Forbidden**: using return path for ineligible category/order.

## T8 `create_support_ticket`
- **Business function**: escalate unresolved, unsupported or exceptional after-sales cases.
- **Input**: user/order references, issue category, evidence summary, source references, urgency.
- **Output**: ticket id/state.
- **Property**: controlled write.
- **Risk**: medium.
- **Automatic call**: allowed for safe escalation.
- **Idempotency**: duplicate logical incident should reuse/relate to existing ticket where possible.

## T9 `request_human_approval`
- **Business function**: request approval for configured high-risk after-sales action.
- **Input**: run id, proposed action, order id, amount/risk summary, evidence refs.
- **Output**: approval request id + `WAITING_APPROVAL` state; later approved/denied token/state.
- **Property**: workflow write, not money movement.
- **Risk**: medium/high.
- **Forbidden**: Agent self-approving.

## T10 `get_after_sales_status`
- **Business function**: verify refund/return/ticket state and recover ambiguous write outcomes.
- **Input**: authenticated user, order id and optional request/idempotency reference.
- **Output**: current after-sales object(s) and state.
- **Property**: read-only.
- **Risk**: medium privacy.
- **Use**: mandatory after ambiguous write timeout before any reissue.

## Global tool rules

1. Tool schemas are versioned and validated before dispatch.
2. Model text never becomes a raw URL, SQL statement or arbitrary internal service name.
3. Read and write tools are separated and visibly tagged.
4. Every write includes `run_id`, authenticated principal and idempotency key.
5. Business services re-check all permissions and preconditions; prompt instructions are not a security boundary.
6. Tool calls and sanitized parameters/results are recorded in the run trace.
7. Retry policy is operation-specific: read retries may be safe; writes require idempotency and ambiguous-completion recovery.
