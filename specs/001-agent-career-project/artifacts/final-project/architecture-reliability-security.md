# ProcurePilot Architecture, Reliability & Security

## 1. Responsibility boundaries

### Minimal Web UI
Responsibilities:
- submit/clarify purchase task;
- show current Agent phase and requested human input;
- show supplier/quote evidence and citations;
- present approval action to authorized human;
- show final verified business state and run trace summary.

Non-responsibilities:
- no business-rule authority;
- no hidden tool permission logic;
- no direct database writes.

### Python Agent Service
Responsibilities:
- normalize user intent into task state;
- decide whether required information is missing;
- plan/select the next allowed read/check/tool action;
- use policy retrieval when unstructured knowledge is required;
- compare acceptable alternatives after deterministic facts are gathered;
- decide whether to ask user, stop, escalate or request approval;
- maintain bounded Agent state and step budget;
- emit model/tool/retrieval trace events.

Non-responsibilities:
- cannot authoritatively decide budget availability, supplier certification, approval outcome or transaction validity;
- cannot bypass backend permissions/state transitions;
- cannot write raw SQL to business state.

### Java Business Backend
Responsibilities:
- authoritative domain rules and validation;
- typed Tool/API endpoints;
- supplier/quote/budget/request/approval/PO state;
- transactions and relational constraints;
- authorization and least privilege;
- request/approval/PO state machine;
- idempotency and duplicate prevention;
- audit trail and server-side policy invariants;
- verify-after-write status reads.

### PostgreSQL
Responsibilities:
- persistent business state;
- unique/idempotency constraints;
- audit/event records;
- Agent-run/tool/retrieval metadata if a single database is simplest;
- optional policy vector embedding via pgvector.

## 2. Core business/domain model

### `user_account`
- `user_id`
- `role` (`requester`, `procurement`, `approver`, `admin_test_fixture`)
- `cost_center_scope`
- `active`

### `supplier`
- `supplier_id`
- `name`
- `status` (`certified`, `suspended`, `inactive`)
- `categories`
- `regions`
- `certification_valid_until`

### `quote`
- `quote_id`
- `supplier_id`
- `item_or_category_id`
- `quantity_min/max`
- `unit_price`, `currency`
- `promised_delivery_days/date`
- `valid_from`, `valid_until`
- `version`

### `budget_account`
- `cost_center_id`
- `currency`
- `available_amount`
- `reserved_amount`
- `version`

### `purchase_request`
- `request_id`
- `requester_id`
- normalized item/category requirements
- `quantity`
- `required_delivery_date`
- `cost_center_id`
- chosen `quote_id` or option set
- `amount`
- `status` (`draft`, `created`, `pending_approval`, `approved`, `rejected`, `po_drafted`, `cancelled`, `partial_failure`)
- `version`
- `idempotency_key`
- timestamps

### `approval`
- `approval_id`
- `request_id`
- `required_role`
- `status` (`pending`, `approved`, `rejected`)
- `actor_id`
- `reason`
- timestamps/version

### `purchase_order_draft`
- `po_draft_id`
- `request_id`
- `quote_id`
- `supplier_id`
- `amount/currency`
- `status`
- `idempotency_key`

### `policy_document`
- `policy_id`
- `version`
- effective dates
- category/type/access scope
- source text/chunks/citations

### `agent_run`
- `run_id`
- `user_id`
- `task_id/session_id`
- input hash/redacted input
- model/config version
- tool-contract version
- start/end/status
- token/latency totals
- final request/result refs

### `agent_step`
- `step_id`, `run_id`, sequence
- state/node name
- normalized decision category (not hidden chain-of-thought)
- tool/retrieval/model action ref
- timing/status/error

### `tool_execution`
- `tool_execution_id`, `run_id`
- tool/version
- redacted normalized args
- result/error class
- attempt/retry count
- idempotency key if applicable
- latency
- business-state refs

### `audit_log`
- actor/run/tool/request refs
- action type
- before/after state/version refs
- policy/permission decision
- timestamp

## 3. Business state machine

```text
DRAFT
  -> CREATED
       -> PENDING_APPROVAL
            -> APPROVED
            -> REJECTED
       -> APPROVED (only when policy explicitly allows no-human approval)
APPROVED
  -> PO_DRAFTED
Any write with ambiguous outcome
  -> verify authoritative state before retry
Unrecoverable inconsistency
  -> PARTIAL_FAILURE / manual review
```

Invalid transitions are rejected server-side even if the Agent requests them.

## 4. Agent state and graph

Minimal task state:
- user identity/scope;
- raw task + normalized requirements;
- missing blocking fields;
- gathered supplier/quote/budget/policy evidence refs;
- candidate acceptable options;
- current business request/approval/PO IDs;
- allowed tools;
- retry/step budgets;
- pending human input/approval;
- terminal status and verified output.

Recommended nodes:

```text
START
 -> NormalizeRequest
 -> ValidateRequiredFields
    -> NeedClarification? -> WAIT_USER -> NormalizeRequest
 -> DecideNextEvidence
 -> ExecuteReadTool / RetrievePolicy
 -> ValidateEvidence
 -> EnoughEvidence?
    -> no -> DecideNextEvidence
 -> CompareAcceptableOptions
 -> DeterministicPreflightChecks
 -> NeedHumanApproval?
    -> yes -> CreateRequest -> RequestApproval -> WAIT_APPROVAL
    -> no  -> CreateRequest
 -> ApprovedAndPORequired?
    -> yes -> CreatePODraft
 -> VerifyBusinessState
 -> ComposeEvidenceBackedResult
 -> END
```

### Stop conditions
- terminal business state reached;
- explicit user cancellation;
- required information unavailable after clarification budget;
- tool retry budget exhausted;
- max Agent steps reached;
- security/policy denial requiring manual handling.

Initial target max steps: a configurable small bound such as 12–16; exact number must be determined from dev eval rather than treated as a resume achievement.

## 5. Retry and idempotency

- Safe read calls: at most one automatic transient retry in core.
- Write calls: never blind-retry after an unknown outcome; call status verification first.
- Every write tool requires an idempotency key generated from stable intent/run/action semantics.
- Database unique constraints enforce effective single write even if client/service retries.
- Agent retry counters live in explicit state and trace.

## 6. Checkpoints and Human-in-the-loop

Checkpoint/pause before:
- waiting for missing blocking user information;
- any policy-required approval;
- optional reviewer confirmation for high-risk PO draft if chosen in implementation.

Resume uses authoritative business state, not only serialized model memory. After resume, revalidate quote freshness and request/approval version before write.

## 7. Retrieval boundary

RAG corpus is restricted to unstructured procurement policy/standard operating procedure material.

Structured authoritative facts stay outside RAG:
- supplier certification;
- quote price/expiry/delivery;
- budget balance;
- request/approval/PO status;
- user permissions.

Retrieval requirements:
- policy/version/effective-date metadata;
- access filtering;
- chunk citation/source location;
- top-k candidates recorded in trace;
- conflicting-version detection;
- eval for recall and citation correctness.

## 8. Security model

### Prompt injection
- user/supplier/policy text is untrusted content;
- system/tool authorization is out-of-band and server-side;
- retrieved text cannot create permissions or change tool schemas;
- explicit adversarial eval cases.

### Authorization
- authenticated user identity passed separately from model-generated arguments;
- backend derives allowed cost center/role scope;
- requester cannot self-approve;
- procurement-only tools reject requester role;
- tool allowlist can be narrowed per run/state.

### Parameter validation
- schema/type/range/date/ID validation;
- quantity > 0;
- valid currency/cost center;
- quote belongs to supplier/request and is unexpired;
- amount recomputed from authoritative quote rather than trusted from model.

### Data minimization
- traces redact secrets and unnecessary personal/sensitive fields;
- model prompt receives only fields necessary for current decision;
- no credentials in model context.

### High-risk writes
- deterministic preconditions;
- least privilege;
- HITL where policy requires;
- idempotency;
- verify-after-write;
- immutable audit record.

## 9. Observability

One `run_id` must reconstruct:
- initial request and normalized task facts;
- model/provider/config identifier;
- graph nodes visited;
- tool names, normalized args, results/errors, retries and latency;
- retrieved policy IDs/versions/chunks/scores;
- approvals and human events;
- token usage/cost estimate;
- business-state transitions;
- final verified outcome.

Do not log hidden chain-of-thought. Record concise structured decision categories/reasons needed for debugging (for example `missing_required_field`, `budget_blocked`, `approval_required`, `retryable_read_timeout`).

## 10. Testing layers

- **Unit**: domain validators, state transitions, score/constraint predicates, idempotency-key logic.
- **Business API**: auth, schema validation, transactions, unique constraints, stale version/quote handling.
- **Tool contract**: every tool success/error/retry/permission path.
- **Agent integration**: graph branches and resume/HITL behavior against local backend.
- **Offline eval**: 60 versioned cases with deterministic scorers first.
- **Failure injection**: timeout, unknown write outcome, stale quote, duplicate request, unavailable retrieval, conflicting policy versions.
- **Security**: Prompt Injection, unauthorized role, parameter tampering, forbidden write, sensitive-data leakage checks.

## 11. Deployment boundary

Core reproducibility:
- Agent service;
- Java backend;
- PostgreSQL;
- optional minimal UI;
- local model API credential/config;
- Docker Compose.

Kubernetes, queues, Redis, service mesh and multi-region deployment are intentionally out of core scope.
