# CommerceAgent Data Model

This model separates authoritative commerce state, Agent execution state, retrieval knowledge, and audit/evaluation records.

## 1. User

Fields:
- `id` UUID/string primary key
- `username`
- `role` (`CUSTOMER`, `APPROVER`, `SUPPORT`)
- `status` (`ACTIVE`, `DISABLED`)
- `created_at`

Rules:
- customer-scoped APIs derive ownership from the authenticated principal, not model-supplied user ids;
- approver role is required for approval decisions.

## 2. Order

Fields:
- `id`
- `user_id` FK → User
- `status` (`PAID`, `SHIPPED`, `DELIVERED`, `CANCELLED`, `CLOSED`)
- `total_amount`
- `currency`
- `created_at`
- `shipped_at`
- `delivered_at`
- `after_sales_status`
- `version` optimistic-lock field

Rules:
- order ownership is immutable;
- illegal business-state transitions are rejected server-side;
- order state never comes from RAG/model memory.

## 3. OrderItem

Fields:
- `id`
- `order_id` FK → Order
- `product_id`
- `product_name`
- `product_category`
- `unit_price`
- `quantity`

Rules:
- price used for eligibility/refund amount is authoritative stored data.

## 4. Shipment

Fields:
- `id`
- `order_id` unique FK → Order
- `carrier`
- `tracking_number`
- `status`
- `last_event_at`
- `signed_at`
- `version`

Relationships:
- one Order → zero/one Shipment in V1;
- one Shipment → many LogisticsEvent.

## 5. LogisticsEvent

Fields:
- `id`
- `shipment_id` FK → Shipment
- `event_type`
- `description`
- `occurred_at`

Rules:
- events are append-oriented fixtures for the synthetic/local environment;
- business logic derives stall duration from authoritative timestamps.

## 6. AfterSalesRule

Structured executable business rule.

Fields:
- `id`
- `rule_code` unique
- `version`
- `product_category`
- `required_order_status`
- `logistics_stalled_hours` nullable
- `return_window_days` nullable
- `max_refund_amount` nullable
- `approval_threshold` nullable
- `allowed_action`
- `active`
- `effective_from`
- `effective_to`

Rules:
- used by deterministic eligibility service;
- never sourced from model output;
- may correspond to a human-readable AfterSalesPolicy document but is not the same entity.

## 7. EligibilityDecision

Value object / persisted audit snapshot as needed.

Fields:
- `decision_id`
- `order_id`
- `reason_code`
- `eligible`
- `allowed_action` (`REFUND_ONLY`, `RETURN`, `RETURN_REFUND`, `MANUAL_REVIEW`, `DENY`)
- `max_refund_amount`
- `approval_required`
- `rule_code`
- `rule_version`
- `reason_codes[]`
- `evaluated_at`

Rules:
- authoritative for a point-in-time decision but revalidated on sensitive writes;
- Agent cannot override any field.

## 8. RefundRequest

Fields:
- `id`
- `order_id` FK → Order
- `user_id` FK → User
- `reason_code`
- `amount`
- `status` (`CREATED`, `PROCESSING`, `COMPLETED`, `REJECTED`, `CANCELLED`)
- `idempotency_key`
- `eligibility_rule_code`
- `approval_request_id` nullable
- `run_id`
- `created_at`
- `updated_at`

Constraints:
- unique logical idempotency key per write scope;
- `amount` cannot exceed deterministic eligibility result;
- existing incompatible after-sales state blocks creation.

## 9. ReturnRequest

Fields:
- `id`
- `order_id`
- `user_id`
- `reason_code`
- `status` (`CREATED`, `WAITING_SHIPMENT`, `RECEIVED`, `REFUND_PENDING`, `COMPLETED`, `REJECTED`)
- `return_deadline`
- `idempotency_key`
- `approval_request_id` nullable
- `run_id`
- `created_at`
- `updated_at`

Constraints:
- uniqueness/idempotency equivalent to refund writes;
- creation requires deterministic return eligibility.

## 10. SupportTicket

Fields:
- `id`
- `user_id`
- `order_id` nullable
- `category`
- `reason`
- `evidence_summary`
- `status` (`OPEN`, `IN_PROGRESS`, `RESOLVED`, `CLOSED`)
- `run_id`
- `created_at`
- `updated_at`

Rules:
- safe escalation may create a ticket even when refund/return is not allowed;
- do not store hidden chain-of-thought, only explicit evidence summaries and structured reason codes.

## 11. ApprovalRequest

Fields:
- `id`
- `run_id`
- `order_id`
- `action_type`
- `amount` nullable
- `risk_reason`
- `status` (`PENDING`, `APPROVED`, `DENIED`, `EXPIRED`)
- `requested_at`
- `decided_at` nullable
- `decided_by` nullable
- `approval_token_hash` nullable

Transitions:
- `PENDING → APPROVED | DENIED | EXPIRED`
- terminal states cannot return to `PENDING`.

Rules:
- Agent cannot set `APPROVED`;
- only authorized approver endpoint can transition the record.

## 12. AgentRun

Fields:
- `run_id`
- `user_id`
- `status` (`RUNNING`, `WAITING_USER`, `WAITING_APPROVAL`, `COMPLETED`, `ESCALATED`, `FAILED`, `SAFE_STOP`)
- `intent`
- `resolved_order_id` nullable
- `current_node`
- `next_action` nullable
- `step_count`
- `retry_count`
- `final_action` nullable
- `error_code` nullable
- `model_name`
- `input_tokens`
- `output_tokens`
- `started_at`
- `completed_at` nullable

Rules:
- persisted enough to resume clarification/approval flows;
- business truth is referenced, not duplicated as authoritative state.

## 13. ToolExecution

Fields:
- `id`
- `run_id` FK → AgentRun
- `step_index`
- `tool_name`
- `risk_level`
- `input_summary`
- `output_summary`
- `status` (`SUCCESS`, `ERROR`, `TIMEOUT`, `DENIED`)
- `error_code` nullable
- `retryable`
- `latency_ms`
- `trace_id`
- `created_at`

Rules:
- sensitive fields are redacted/minimized;
- no raw auth token stored.

## 14. AuditLog

Fields:
- `id`
- `actor_type` (`USER`, `AGENT`, `APPROVER`, `SYSTEM`)
- `actor_id`
- `action`
- `resource_type`
- `resource_id`
- `run_id` nullable
- `result`
- `metadata_json`
- `created_at`

Rules:
- key write/auth decisions create an audit event;
- append-oriented from application perspective.

## 15. PolicyDocument

Fields:
- `id`
- `document_code`
- `title`
- `version`
- `category`
- `effective_from`
- `effective_to`
- `checksum`
- `source_path`
- `active`

Constraints:
- `(document_code, version)` unique.

## 16. PolicyChunk

Fields:
- `id`
- `document_id` FK → PolicyDocument
- `section`
- `content`
- `embedding`
- `metadata_json`

Rules:
- retrieval returns parent document/version/effective metadata;
- retrieved text cannot directly authorize a write.

## 17. EvalCase / EvalRun / EvalCaseResult

### EvalCase
- `case_id`
- `dataset_version`
- `dataset_split`
- `category`
- `user_task`
- fixture/reset identifier
- expected tool/action predicates
- forbidden actions
- expected business-state predicates
- tags

Definitions should live in versioned Git files; optional DB metadata may index them.

### EvalRun
- `eval_run_id`
- `dataset_version`
- `system_version` (`BASELINE`, `V1`, `OPTIMIZED`)
- `model_config`
- `started_at`
- `completed_at`

### EvalCaseResult
- `eval_run_id`
- `case_id`
- `run_id`
- task/tool/parameter/state/safety scorer results
- latency/token/tool-call counts
- failure taxonomy

## Relationship Summary

```text
User 1---* Order 1---* OrderItem
              |
              0..1 Shipment 1---* LogisticsEvent
              |
              * RefundRequest
              * ReturnRequest
              * SupportTicket
              * ApprovalRequest

AgentRun 1---* ToolExecution
AgentRun --- Refund/Return/Ticket/Approval via run_id

PolicyDocument 1---* PolicyChunk

AfterSalesRule -> EligibilityDecision -> guarded write
```

## Critical State Rules

1. `AgentRun` state is not business authorization.
2. `EligibilityDecision` is deterministic and is revalidated for sensitive writes.
3. `WAITING_APPROVAL` prevents refund/return creation until approval is valid.
4. Timeout after a write never implies failure; status is queried before retry.
5. Same logical idempotency key cannot create more than one logical refund/return.
6. Retrieval documents and Agent prose never change Order/Refund/Return state directly.
