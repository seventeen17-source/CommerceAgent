# CommerceAgent Architecture, Reliability & Security

## 1. Responsibility split

### UI
- collect customer request and authentication context;
- display clarification, action summary, approval/waiting state and final result;
- provide a separate simple approval view for configured high-risk cases;
- never decide eligibility or permissions.

### Python Agent Service
Owns:
- intent understanding;
- order-context resolution;
- explicit Agent state graph;
- evidence sufficiency checks;
- dynamic Tool/API selection;
- policy retrieval orchestration;
- deciding clarification vs refund vs return vs escalation based on authoritative tool results;
- bounded retry/stop logic;
- final evidence-grounded response;
- eval/trace emission.

Does not own:
- order ownership;
- refund amount;
- legal state transition;
- approval authority;
- idempotent write guarantee.

### Java After-sales Backend
Owns:
- User/Order/Shipment/AfterSales domain data;
- authorization and ownership checks;
- deterministic refund/return eligibility;
- amount calculation and limits;
- legal state transitions;
- idempotency;
- transactions;
- approval validation;
- refund/return/ticket persistence;
- audit log;
- eval-state reset fixture APIs used only in test profile.

### PostgreSQL
Stores business state, after-sales records, approval/audit data and optionally normalized trace metadata. Model-generated prose is never the source of truth for a financial/business state.

### Policy Retrieval
Stores/version-controls unstructured policy/SOP documents. Retrieval is advisory/evidentiary; backend eligibility remains authoritative.

## 2. Suggested logical architecture

```text
Customer UI
    |
    v
Agent API (Python/FastAPI)
    |
    |-- State Graph / LLM
    |-- Tool Adapter
    |-- Policy Retrieval
    |-- Trace + Eval hooks
    |
    v
After-sales API (Java/Spring Boot)
    |-- Order Service
    |-- Logistics Projection
    |-- Eligibility Service
    |-- Refund/Return Service
    |-- Ticket Service
    |-- Approval Service
    |-- Audit Service
    |
    v
PostgreSQL
```

HTTP/JSON is the MVP Tool transport. MCP may be layered later without changing business semantics.

## 3. Agent state machine

Recommended nodes:
1. `parse_request`
2. `resolve_order`
3. `gather_evidence`
4. `decide_next_step`
5. `execute_read_tool`
6. `validate_tool_result`
7. `check_evidence_sufficiency`
8. `check_eligibility`
9. `choose_after_sales_action`
10. `risk_check`
11. `wait_for_approval` (conditional)
12. `execute_write`
13. `verify_business_state`
14. `finalize_response`
15. `escalate_or_fail_safe`

Looping is allowed only between evidence/decision/read-tool nodes with a bounded step count.

## 4. Stop and circuit-breaker rules

Stop safely when:
- max Agent steps exceeded;
- same tool/parameter combination repeats without new evidence;
- required system remains unavailable after bounded retries;
- order identity remains ambiguous;
- deterministic eligibility denies automatic action;
- policy versions cannot be resolved and backend cannot supply an authoritative result;
- approval is denied/expired;
- post-write state cannot be verified.

A safe stop may create a support ticket if that is permitted and useful; otherwise return a transparent handoff response.

## 5. Retry strategy

### Read tools
Allow short bounded retries for transient network/service errors.

### Write tools
Never blindly retry after timeout. Use:
1. stable idempotency key;
2. query `get_after_sales_status`;
3. if state confirms success, return existing result;
4. if state confirms no write and retry is safe, retry with same key;
5. if ambiguous remains, escalate instead of risking duplicate refund.

## 6. Human-in-the-loop

HITL is required for configured high-risk conditions such as:
- amount above threshold;
- exceptional/manual-review eligibility;
- unusual policy override request;
- other risk rule defined by the backend.

The Agent creates an approval request and enters `WAITING_APPROVAL`. It cannot self-approve or synthesize an approval token.

## 7. Security boundaries

### Authentication / authorization
- UI/session establishes authenticated user.
- Tool adapter never trusts a user id/order id solely because the model emitted it.
- Java backend validates ownership for every user-scoped operation.

### Prompt Injection
Untrusted user/policy/product/logistics text cannot change:
- tool allowlist;
- authenticated principal;
- approval threshold;
- refund amount;
- backend policy rules.

Instructions embedded in retrieved content are treated as data, not executable authority.

### Parameter validation
Use strict schemas/enums/ranges. The backend recomputes sensitive fields such as amount and eligibility rather than accepting model-calculated authority.

### Read/write separation
Write tools are distinct, visibly risk-labeled and guarded by preconditions. A read tool can never be promoted to arbitrary execution through free-form arguments.

### Least privilege
Agent service gets only APIs needed for the after-sales workflow. No database superuser or arbitrary SQL tool in core.

### Sensitive data
Expose only fields necessary for after-sales handling. Avoid full payment credentials or unnecessary PII in prompts/traces.

## 8. Idempotency model

Every logical refund/return write uses a stable idempotency key derived from the logical action context, not regenerated on every retry.

Backend uniqueness and state checks guarantee:
- repeated identical request returns prior result;
- conflicting duplicate action fails explicitly;
- a timeout cannot silently create two refunds.

## 9. Observability

Per `run_id`, record:
- request metadata;
- resolved intent/order id;
- state-node transitions;
- model name/config and token usage;
- tool name and sanitized validated parameters;
- tool result/error/latency;
- policy chunk ids/version/citations;
- deterministic eligibility result;
- retries and circuit-breaker events;
- approval request/result;
- write id/idempotency key hash/reference;
- verification result;
- final outcome and error taxonomy.

Do not log private hidden chain-of-thought. Log explicit state, decisions as structured labels/reasons suitable for debugging, and externally verifiable evidence.

## 10. Evaluation architecture

A test profile can reset the Java backend to a known synthetic business state per case. The eval runner invokes the Agent with a user task and checks:
- calls/parameters against predicates;
- forbidden actions;
- final DB/API state;
- citations/facts;
- run trace;
- latency/token metrics.

This makes most scoring deterministic and avoids relying on an LLM judge for safety/business correctness.

## 11. Reliability scenarios required before core completion

- logistics timeout;
- eligibility service temporary failure;
- refund write timeout after possible commit;
- duplicate user submission;
- wrong/ambiguous order;
- stale policy retrieval;
- Prompt Injection;
- unauthorized cross-user order id;
- approval pending/denied;
- final verification mismatch.

## 12. Explicit non-goals

Core does not require:
- microservices decomposition beyond justified Java/Python split;
- Kafka/event bus;
- Redis unless measured need emerges;
- Kubernetes;
- multi-region deployment;
- Multi-Agent orchestration;
- model fine-tuning/RLHF;
- real payment gateway integration.

The engineering depth must come from safe execution, failure recovery, deterministic authority, evaluation and observability—not component count.
