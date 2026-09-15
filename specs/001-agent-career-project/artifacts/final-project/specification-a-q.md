# CommerceAgent — E-commerce After-sales Execution & Exception Handling Agent

## A. Project positioning

CommerceAgent is an enterprise-style e-commerce after-sales execution Agent. It is not a FAQ chatbot. It receives an ambiguous customer goal, gathers evidence across order/logistics/policy systems, chooses the correct after-sales path, executes an allowlisted business action when permitted, escalates high-risk/uncertain cases, and returns an auditable result.

Primary demo task: “我买的耳机几天没收到，不想要了，帮我退款。”

## B. Enterprise scenario and target users

Target users:
- consumer requesting after-sales service;
- customer-service/after-sales operator reviewing exceptional cases;
- approver for high-risk refunds.

Pain point: after-sales handling often requires repeated cross-system checks and manual routing. The Agent reduces the orchestration burden, not the deterministic authority of the business system.

Core scope: refund, return, logistics anomaly and exception escalation only.

Out of scope: product recommendation, pre-sales QA, marketing, merchant operations, procurement, real payment rails, broad omnichannel support.

## C. Overall architecture

`Web/Chat UI → Python Agent Service → Tool Adapter → Java After-sales Backend → PostgreSQL`

Supporting capabilities:
- policy retrieval/RAG for unstructured policy knowledge;
- per-run Trace/Observability;
- offline Eval runner;
- Human-in-the-loop approval endpoint.

The Java backend is the source of truth for orders, logistics projections, eligibility, permissions, amounts, state transitions, idempotency and writes.

## D. Technology choices and tradeoffs

Recommended implementation baseline:
- **Java + Spring Boot — Must**: business domain, REST APIs, deterministic policy/eligibility, transactions, idempotency, audit.
- **Python + FastAPI — Must**: Agent orchestration, model SDK integration, eval runner.
- **State graph / explicit workflow — Must**: bounded, inspectable state transitions rather than open-ended ReAct loops.
- **PostgreSQL — Must**: deterministic business state and audit records.
- **RAG — Should, narrow use**: policy/SOP retrieval only.
- **MCP — Should after HTTP tools work**: demonstrate protocol standardization without making it an MVP dependency.
- **React/simple UI — Should**: enough to demo customer request, approval and trace; not a design-heavy frontend.
- **Docker Compose — Should**: reproducible local demo.
- **Redis/Kafka/Kubernetes/Multi-Agent/training — Reject for core** unless later evidence requires them.

## E. Agent architecture

State:
- `request_id`, `user_id`, `conversation_context`;
- resolved/ambiguous `order_id`;
- intent and reason;
- order snapshot;
- logistics snapshot;
- retrieved policy evidence;
- deterministic eligibility result;
- proposed action;
- risk/approval state;
- write result;
- verification result;
- step count, retries, errors and trace ids.

Core graph:

`START → ParseIntent → ResolveOrder → GatherEvidence → DecideNextStep → ToolCall → ValidateToolResult → EnoughEvidence? → EligibilityCheck → ChooseAction → RiskCheck → Approval? → CommitAction → VerifyBusinessState → FinalResponse → END`

Branches may return to `GatherEvidence`, ask the user for clarification, or terminate with escalation.

Hard limits:
- bounded max steps;
- bounded retries;
- no model-controlled arbitrary endpoint/URL;
- write tools only after deterministic authorization/eligibility checks;
- approval token required for configured high-risk writes.

## F. Tool inventory

Core tools:
1. `list_user_orders` — identify candidate orders.
2. `get_order` — fetch order/item/payment/fulfilment state.
3. `get_logistics` — fetch shipment events and anomaly projection.
4. `policy_search` — retrieve cited after-sales policy/SOP.
5. `check_after_sales_eligibility` — deterministic refund/return type, max amount and required approval.
6. `create_refund_request` — idempotent write.
7. `create_return_request` — idempotent write.
8. `create_support_ticket` — escalation/exception write.
9. `request_human_approval` — optional approval flow for high-risk cases.
10. `get_after_sales_status` — post-write verification/recovery.

## G. RAG decision

RAG is used only where the source is unstructured enterprise knowledge such as after-sales policy, category exceptions or SOP text.

RAG must not be used for:
- order state;
- logistics events;
- refundable amount;
- permissions;
- refund/return eligibility;
- after-sales state.

Those come from structured APIs/database-backed deterministic services.

If RAG is implemented:
- preserve document/version metadata;
- hybrid retrieval is preferred only if the corpus justifies it;
- return citations/source ids;
- evaluate retrieval recall and citation correctness separately from business-action success.

## H. Java/business-backend responsibilities

Java owns:
- user/order ownership and authorization;
- Order / Logistics / AfterSales domain models;
- refund/return eligibility rules;
- amount and threshold calculations;
- legal state transitions;
- idempotency keys and duplicate-write handling;
- approval validation;
- transaction boundaries;
- audit events;
- resettable synthetic state for eval cases.

The backend must be useful even if the LLM is removed; it is not an empty service created to display Java.

## I. Database/domain model

Core entities:
- `User`
- `Order`
- `OrderItem`
- `Shipment`
- `LogisticsEvent`
- `AfterSalesPolicyRef`
- `RefundRequest`
- `ReturnRequest`
- `SupportTicket`
- `ApprovalRequest`
- `AgentRun`
- `ToolExecution`
- `AuditLog`

Important constraints:
- after-sales writes reference a stable `order_id` and authenticated `user_id`;
- refund amount cannot exceed deterministic backend result;
- idempotency key is unique per logical write;
- illegal state transitions are rejected server-side;
- every write has an audit event.

## J. Evaluation

Design 60–80 versioned cases. Initial target distribution:
- 12 normal refund cases;
- 10 return/return-refund cases;
- 10 logistics-anomaly cases;
- 8 tool-selection cases;
- 6 parameter/identity/order-resolution cases;
- 6 timeout/retry/idempotency cases;
- 6 permission/Prompt-Injection/unsafe-action cases;
- 5 Human-in-the-loop/high-risk cases;
- 5 policy retrieval/citation cases;
- 6 mixed/partial-failure regression cases.

Metrics:
- task success rate;
- tool selection accuracy;
- tool parameter accuracy;
- business-state correctness;
- policy compliance rate;
- unsafe action rate;
- duplicate write rate;
- retrieval recall/citation accuracy where applicable;
- average tool calls;
- p50/p95 end-to-end latency;
- Token cost.

Run Baseline, V1 and one Optimized version on comparable data/tool permissions/budgets. No measured number may appear in resume materials until a real eval run exists.

## K. Observability

A single `run_id` must reconstruct:
- user request;
- parsed intent/order resolution;
- Agent state transitions;
- model calls and summarized rationale artifacts (not hidden chain-of-thought);
- tool name + validated parameters;
- tool response/error;
- retrieved policy chunk ids/citations;
- retries/timeouts;
- eligibility result;
- approval state;
- write result and post-write verification;
- latency, Token counts and final outcome.

## L. Testing

- Java unit tests for eligibility/state/idempotency rules.
- API tests for order/logistics/after-sales endpoints.
- Tool-contract tests for schema, auth and error mapping.
- Agent integration tests for state transitions and branching.
- Offline eval for full task cases.
- Fault injection for timeout, ambiguous completion, duplicate request, unavailable policy retrieval and stale logistics.
- Independent security tests for unauthorized refund and Prompt Injection.

## M. Deployment

Core target: local reproducible Docker Compose or equivalent simple process orchestration.

Suggested services:
- `commerce-backend`
- `agent-service`
- `postgres`
- optional simple UI

Cloud deployment is Should if time remains. Kubernetes is not core.

## N. Security

Threats and controls:
- **Prompt Injection** → tool allowlist, untrusted text treated as data, server-side permission/policy enforcement.
- **IDOR/order theft** → backend verifies order belongs to authenticated user.
- **Amount tampering** → refund amount computed/capped server-side.
- **Duplicate refund** → idempotency key + status recovery before retry.
- **Write timeout ambiguity** → query status before reissuing write.
- **High-risk refund** → explicit approval token.
- **Sensitive data** → minimize fields exposed to model/trace.
- **Unsafe tool choice** → deterministic preconditions and forbidden-action eval cases.

## O. 6+2 week roadmap

Week 1: domain/backend/tool contracts + first 10–15 eval cases.

Week 2: one happy path and one controlled failure complete `User → Agent → Tool → Business System → Result + Trace`.

Week 3: timeout, bounded retry, wrong tool/parameter, idempotency, injection/authorization, approval.

Week 4: freeze 60–80 versioned eval set; run Baseline and V1.

Week 5: optimize the largest measured error category only; rerun the same eval.

Week 6: reproducible full demo, failure recovery, trace/eval report, evidence ledger.

Week 7 optional: MCP adapter or second after-sales sub-scenario using the same core.

Week 8 optional: README, demo video, interview replay, resume evidence audit.

## P. Interview mapping

The user must be able to explain and simplified-reimplement:
- explicit Agent state graph and stop conditions;
- Tool Calling and parameter validation;
- why structured facts do not belong in RAG;
- deterministic eligibility vs LLM reasoning boundary;
- Java transaction/state-machine/idempotency design;
- timeout ambiguity recovery;
- Human-in-the-loop approval;
- Prompt Injection and authorization boundary;
- offline eval scorers and leakage controls;
- per-run tracing and error taxonomy.

## Q. Resume / README / Demo outputs

README should show:
1. business problem;
2. architecture and responsibility boundary;
3. one normal after-sales run;
4. one failure/unsafe run;
5. Trace screenshot/data;
6. Eval methodology and actual measured results when available;
7. synthetic-system boundary and limitations;
8. quickstart.

Demo target: 60–90 seconds. Start with a customer complaint, show dynamic evidence/tool choice, deterministic eligibility, safe write/approval, post-write verification and trace/eval evidence.

Resume claims remain templates until actual implementation and eval runs produce reproducible numbers.

## Final scope statement

The project succeeds only if it demonstrates that **the Agent chooses what to investigate and what business path to take, while the backend alone controls whether a money/state-changing action is legal**. If implementation becomes a fixed intent router calling one refund endpoint, the project fails its Agent-value gate and the design must be revisited.
