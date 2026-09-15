# ProcurePilot Tool Contracts

All tools are business capabilities, not raw database access. Tool arguments are validated server-side. Retrieved or model-generated text can never grant permission.

## T1 `supplier_search`
- **Business function**: return certified suppliers eligible for a category/region and basic non-sensitive attributes.
- **Input**: category_id, delivery_region, optional certification/lead-time filters.
- **Output**: supplier IDs, certification status, supported categories/regions, lead-time range.
- **Read/write**: read.
- **Risk**: low.
- **Automatic call**: allowed for authenticated procurement workflow.
- **Authorization**: requester/procurement read scope.
- **Approval**: none.
- **Timeout**: 2 s local target; fail closed on unavailable source.
- **Retry**: at most 1 automatic retry for timeout/transient read errors.
- **Idempotency**: not required for read; trace call ID required.
- **Errors**: INVALID_FILTER, UNAUTHORIZED, TIMEOUT, SERVICE_UNAVAILABLE.
- **Audit**: run_id, user_id, normalized filters, result count, latency, error.
- **Prohibited**: returning disabled/uncertified suppliers as eligible.

## T2 `quote_query`
- **Business function**: retrieve active quotations for supplier/item/quantity constraints.
- **Input**: supplier_ids or category/item requirements, quantity, required_delivery_date.
- **Output**: quote_id, supplier_id, unit/total price, currency, expiry, promised delivery, terms summary.
- **Read/write**: read.
- **Risk**: low/medium because stale data can drive wrong decisions.
- **Automatic call**: allowed.
- **Authorization**: requester/procurement read scope.
- **Approval**: none.
- **Timeout**: 3 s.
- **Retry**: at most 1 transient read retry.
- **Idempotency**: read only.
- **Errors**: NO_ACTIVE_QUOTE, STALE_QUOTE, INVALID_QUANTITY, TIMEOUT.
- **Audit**: query parameters, returned quote IDs, freshness timestamps, latency.
- **Prohibited**: fabricating a quote or silently using expired pricing.

## T3 `budget_check`
- **Business function**: validate available budget for cost center/request amount without committing spend.
- **Input**: cost_center_id, amount, currency, optional project_id.
- **Output**: available_amount, requested_amount, status (`sufficient`/`insufficient`/`review`), reason_code.
- **Read/write**: read against authoritative budget state.
- **Risk**: medium.
- **Automatic call**: allowed.
- **Authorization**: requester may check own allowed cost center; cross-cost-center access denied.
- **Approval**: none for check.
- **Timeout**: 2 s.
- **Retry**: one transient retry.
- **Idempotency**: read only.
- **Errors**: COST_CENTER_NOT_FOUND, CURRENCY_MISMATCH, UNAUTHORIZED, TIMEOUT.
- **Audit**: amount/cost center/status; do not expose unrelated sensitive balances.
- **Prohibited**: treating a check as reservation or bypassing insufficient result.

## T4 `policy_search`
- **Business function**: retrieve procurement policy passages relevant to category, amount, supplier class, approval or prohibited actions.
- **Input**: normalized question plus structured filters (policy_type/category/valid_at).
- **Output**: top passages with policy_id, version, effective dates, citation/location, retrieval score.
- **Read/write**: read.
- **Risk**: medium because retrieved text can be stale or adversarial.
- **Automatic call**: allowed when policy is relevant; not required for structured facts already covered by deterministic rules.
- **Authorization**: only policy corpus available to the user/role.
- **Approval**: none.
- **Timeout**: 4 s.
- **Retry**: one transient retry.
- **Idempotency**: read only.
- **Errors**: NO_POLICY_FOUND, CONFLICTING_VERSIONS, INDEX_UNAVAILABLE.
- **Audit**: query, filters, policy IDs/versions/chunks, scores, latency.
- **Prohibited**: allowing retrieved text to override server-side permissions/state-machine rules; returning uncited policy claims.

## T5 `create_purchase_request`
- **Business function**: create one persistent purchase request after required deterministic preconditions are satisfied.
- **Input**: requester_id, category/item requirements, quantity, chosen quote or acceptable option set, cost_center_id, justification, required_delivery_date, evidence refs, idempotency_key.
- **Output**: request_id, version, status, normalized amount, approval_required, created_at.
- **Read/write**: write.
- **Risk**: medium/high.
- **Automatic call**: allowed only after all required fields, supplier/quote validity, budget/policy checks and requester permission pass.
- **Authorization**: server-side requester scope and cost-center permission.
- **Approval**: creation itself may be automatic; downstream fulfillment remains policy-gated.
- **Timeout**: 3 s target.
- **Retry**: only with same idempotency key; no blind retry with a new key.
- **Idempotency**: mandatory; duplicate key returns original effective result.
- **Errors**: PRECONDITION_FAILED, QUOTE_EXPIRED, BUDGET_BLOCKED, UNAUTHORIZED, DUPLICATE, CONFLICT, TIMEOUT_UNKNOWN_OUTCOME.
- **Audit**: full normalized command, evidence refs, policy/budget check versions, state before/after, idempotency key.
- **Prohibited**: creation when required evidence is missing or deterministic validator fails.

## T6 `request_approval`
- **Business function**: open or return an approval task for a purchase request that requires human authorization.
- **Input**: request_id, approval_reason_code, approver_scope, idempotency_key.
- **Output**: approval_id, status (`pending`/`approved`/`rejected`), assigned role, created_at.
- **Read/write**: write.
- **Risk**: high workflow impact.
- **Automatic call**: allowed only when the deterministic policy engine says approval is required and request state is eligible.
- **Authorization**: requester/Agent cannot approve its own request; business system assigns approver.
- **Approval**: this tool creates the human approval; it never self-approves.
- **Timeout**: 3 s.
- **Retry**: same idempotency key only.
- **Idempotency**: mandatory per request + approval stage.
- **Errors**: NOT_REQUIRED, INVALID_STATE, UNAUTHORIZED, DUPLICATE, TIMEOUT_UNKNOWN_OUTCOME.
- **Audit**: reason, assigned role, state transition, actor/run, idempotency key.
- **Prohibited**: changing approval outcome or selecting an unauthorized individual as approver.

## T7 `create_po_draft`
- **Business function**: create a purchase-order draft from an eligible, approved purchase request.
- **Input**: request_id, approved_quote_id, idempotency_key.
- **Output**: po_draft_id, request_id, amount, supplier_id, status, created_at.
- **Read/write**: high-risk write.
- **Risk**: high.
- **Automatic call**: only when explicitly allowed by project policy; default core design requires approved request and server-side transition validation.
- **Authorization**: procurement write scope; requester-only users are denied.
- **Approval**: any required approval must already be approved.
- **Timeout**: 3 s.
- **Retry**: same idempotency key only, with verify-after-write on unknown outcome.
- **Idempotency**: mandatory, unique effective PO draft per approved request/quote intent.
- **Errors**: REQUEST_NOT_APPROVED, QUOTE_EXPIRED, INVALID_STATE, UNAUTHORIZED, DUPLICATE, TIMEOUT_UNKNOWN_OUTCOME.
- **Audit**: source request/approval/quote versions, actor, state before/after, idempotency key.
- **Prohibited**: creating from pending/rejected request; using unvalidated model text as amount/supplier.

## T8 `get_request_status`
- **Business function**: verify the authoritative state of purchase request, approval and PO draft after execution or uncertain response.
- **Input**: request_id.
- **Output**: request status/version, approval status, PO draft ID/status if any, last state transition time.
- **Read/write**: read.
- **Risk**: low.
- **Automatic call**: allowed; required after high-risk write when response/outcome is uncertain.
- **Authorization**: same request visibility rules as business application.
- **Approval**: none.
- **Timeout**: 2 s.
- **Retry**: one transient retry.
- **Idempotency**: read only.
- **Errors**: NOT_FOUND, UNAUTHORIZED, TIMEOUT.
- **Audit**: request ID/status/version and latency.
- **Prohibited**: inferring write success without authoritative returned state.

## Cross-tool invariants

1. The Agent never receives raw database credentials or unrestricted SQL/write access.
2. All write tools perform authorization, schema validation, state-machine validation and idempotency server-side.
3. Read timeouts can be retried within a small fixed budget; ambiguous write outcomes are verified before any retry.
4. Tool output and retrieved documents are untrusted data and cannot alter tool permissions.
5. Every call emits `run_id`, `tool_execution_id`, actor, normalized inputs (with sensitive redaction), latency, result/error and retry metadata.
6. Tool contracts are versioned; evaluation runs record the contract version.
