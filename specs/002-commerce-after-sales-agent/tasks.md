# Tasks: CommerceAgent 企业电商售后执行与异常处置 Agent

**Input**: Design documents from `specs/002-commerce-after-sales-agent/`

**Prerequisites**: `plan.md`, `spec.md`, `research.md`, `data-model.md`, `contracts/`, `quickstart.md`, `.specify/memory/constitution.md`

**Organization**: Tasks are grouped by user story so each increment is independently testable. Tests are included because this feature explicitly requires deterministic business correctness, Agent Value Gate validation, safety evaluation, idempotency verification, and a versioned offline eval set.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel because it touches different files and does not depend on another unfinished task in the same phase.
- **[Story]**: Maps to the user story in `spec.md`.
- Every implementation task names the concrete file or directory it must change.

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Create the minimum runnable project skeleton. Do not add business features yet.

- [ ] T001 Create the planned root directories `commerce-backend/`, `agent-service/`, `web/`, `eval/`, `knowledge/policies/`, and `infra/` without adding unused microservice folders
- [ ] T002 Generate `commerce-backend/` with Spring Initializr using Java 21, Maven, Spring Boot 3.5.x, group `com.seventeen17`, artifact/name `commerce-backend`, package `com.seventeen17.commerceagent`, and dependencies Spring Web, Spring Security, Validation, Spring Data JPA, PostgreSQL Driver, Flyway Migration, Actuator and Testcontainers; keep generated Maven Wrapper files (`mvnw`, `mvnw.cmd`, `.mvn/`) and then verify `commerce-backend/pom.xml`
- [ ] T003 [P] Generate `agent-service/` with `uv init --python 3.13` (application package layout), then add FastAPI, Uvicorn, LangGraph, Pydantic Settings, httpx, PostgreSQL/async database support, pytest and pytest-asyncio in `agent-service/pyproject.toml`; keep `uv.lock` under version control once dependencies resolve
- [ ] T004 [P] Generate `web/` with Vite using the React + TypeScript template (`npm create vite@latest web -- --template react-ts`), install dependencies, and keep the generated TypeScript/Vite configuration as the baseline before adding project-specific UI code
- [ ] T005 Configure PostgreSQL with pgvector and logical `commerce`, `agent`, `policy`, and optional `eval` schemas in `infra/docker-compose.yml` plus non-secret examples in `.env.example`; Flyway in `commerce-backend` is the single V1 migration runner
- [ ] T006 [P] Configure Java formatting/static-analysis/test plugins in `commerce-backend/pom.xml` and Python lint/type-check settings in `agent-service/pyproject.toml`
- [ ] T007 [P] Add application configuration skeletons for dev/test/eval profiles in `commerce-backend/src/main/resources/application.yml`, `commerce-backend/src/test/resources/application-test.yml`, and `agent-service/app/config/settings.py`

**Checkpoint**: All three applications can start as empty shells and connect to the local PostgreSQL container.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Implement shared security, storage, trace, error and Agent-state foundations used by every story.

**CRITICAL**: No user-story business flow begins until this phase is complete.

- [ ] T008 Create initial Flyway schema for `commerce.users`, `commerce.orders`, `commerce.order_items`, `commerce.shipments`, `commerce.logistics_events`, `commerce.after_sales_rules`, `agent.agent_runs`, `agent.tool_executions`, and `commerce.audit_logs` in `commerce-backend/src/main/resources/db/migration/V001__core_schema.sql`; preserve schema/service ownership rules from `data-model.md`
- [ ] T009 [P] Implement shared JPA entities/repositories for User, Order, OrderItem, Shipment and LogisticsEvent in `commerce-backend/src/main/java/com/seventeen17/commerceagent/order/` and `commerce-backend/src/main/java/com/seventeen17/commerceagent/logistics/`; preserve immutable order ownership, optimistic `version`, and authoritative stored price/state rules from `data-model.md`
- [ ] T010 [P] Implement `AfterSalesRule` persistence with unique `rule_code`, version/effective dates, nullable logistics/return/amount/approval thresholds, `allowed_action`, and `active` fields in `commerce-backend/src/main/java/com/seventeen17/commerceagent/eligibility/`
- [ ] T011 Implement local JWT authentication and role-aware principal resolution in `commerce-backend/src/main/java/com/seventeen17/commerceagent/security/`; customer APIs MUST derive ownership from the authenticated principal and MUST NOT trust model-supplied user ids
- [ ] T012 [P] Implement stable API error envelope and error-code mapping matching `contracts/error-contracts.md` in `commerce-backend/src/main/java/com/seventeen17/commerceagent/common/error/`
- [ ] T013 [P] Implement business/security audit writer for structured events only—no hidden chain-of-thought and no raw auth token—in `commerce-backend/src/main/java/com/seventeen17/commerceagent/audit/`
- [ ] T014 Create dev/eval fixture loader with `customer-001`, `customer-002`, `approver-001`, deterministic orders/logistics/rules, and the reset endpoint defined by `contracts/eval-internal-api.md` in `commerce-backend/src/main/java/com/seventeen17/commerceagent/fixture/`; endpoint MUST be absent outside test/eval profiles
- [ ] T015 [P] Define explicit `AgentState` with run id, authenticated user context, intent, candidate/resolved order, evidence, eligibility, approval state, tool history, step/retry budgets, write/verification result and terminal status in `agent-service/app/agent/state.py`
- [ ] T016 [P] Implement typed Java API client base, auth-context propagation, timeout handling and common response validation in `agent-service/app/clients/commerce_client.py`; auth tokens/principal data MUST never be inserted into model prompts
- [ ] T017 Implement persistent Agent run/checkpoint repository and structured tool trace writer in `agent-service/app/trace/`; support `RUNNING`, `WAITING_USER`, `WAITING_APPROVAL`, `COMPLETED`, `ESCALATED`, `FAILED`, and `SAFE_STOP`
- [ ] T018 Implement FastAPI JWT verification, authenticated principal context, run-ownership authorization, and the run/status/event skeleton endpoints from `contracts/agent-api.openapi.yaml` in `agent-service/app/security/`, `agent-service/app/api/runs.py`, and `agent-service/app/main.py`; customers MUST NOT read/resume another user's run

**Checkpoint**: Foundation is ready; authenticated synthetic business state and resumable, owner-scoped Agent runs can be created and traced without any refund/return action yet.

---

## Phase 3: User Story 1 — 物流异常退款闭环 (Priority: P1) 🎯 MVP

**Goal**: A natural-language logistics-stalled complaint reaches a deterministic refund decision, creates exactly one refund request, verifies the write, and returns an auditable result.

**Independent Test**: Seed one `SHIPPED`, unsigned order with logistics stalled for 120 hours and a rule allowing a normal-value refund. One user request must result in exactly one `RefundRequest`, correct amount/rule code, verified final state, and complete run/tool trace.

### Tests for User Story 1

- [ ] T019 [P] [US1] Write Java tests for ownership-scoped order/logistics reads and logistics stall derivation in `commerce-backend/src/test/java/com/seventeen17/commerceagent/order/OrderLogisticsIntegrationTest.java`
- [ ] T020 [P] [US1] Write Java tests for deterministic eligibility and rejection of model-provided amount/eligibility overrides in `commerce-backend/src/test/java/com/seventeen17/commerceagent/eligibility/EligibilityServiceTest.java`
- [ ] T021 [P] [US1] Write Java integration tests for refund authorization, `amount <= deterministic eligibility result`, incompatible after-sales-state rejection, idempotency reuse, idempotency conflict and write-after-timeout verification behavior in `commerce-backend/src/test/java/com/seventeen17/commerceagent/refund/RefundIntegrationTest.java`
- [ ] T022 [P] [US1] Write Python graph/integration tests for the stalled-logistics happy path and unknown-write-result recovery in `agent-service/tests/integration/test_us1_logistics_refund.py`

### Implementation for User Story 1

- [ ] T023 [P] [US1] Implement customer-scoped order list/detail endpoints from `commerce-api.openapi.yaml` in `commerce-backend/src/main/java/com/seventeen17/commerceagent/order/OrderController.java` and `OrderService.java`
- [ ] T024 [P] [US1] Implement order logistics endpoint and authoritative stall calculation in `commerce-backend/src/main/java/com/seventeen17/commerceagent/logistics/LogisticsController.java` and `LogisticsService.java`
- [ ] T025 [US1] Implement deterministic `EligibilityDecision` service returning `eligible`, `allowed_action`, `max_refund_amount`, `approval_required`, rule code/version and reason codes in `commerce-backend/src/main/java/com/seventeen17/commerceagent/eligibility/EligibilityService.java`
- [ ] T026 [US1] Add `commerce.refund_requests` schema with unique logical idempotency key per write scope and implement `RefundRequest` entity/repository in `commerce-backend/src/main/resources/db/migration/V002__refund_schema.sql` and `commerce-backend/src/main/java/com/seventeen17/commerceagent/refund/`
- [ ] T027 [US1] Implement transactional refund creation and status lookup in `commerce-backend/src/main/java/com/seventeen17/commerceagent/refund/RefundService.java`; revalidate ownership, current state, eligibility, amount and, when required, authoritative `approvalRequestId` binding/status immediately before every sensitive write
- [ ] T028 [US1] Expose refund and after-sales status endpoints with `Idempotency-Key` semantics from `commerce-api.openapi.yaml` in `commerce-backend/src/main/java/com/seventeen17/commerceagent/refund/RefundController.java`
- [ ] T029 [P] [US1] Implement typed tools `list_user_orders`, `get_order`, `get_logistics`, `check_after_sales_eligibility`, `create_refund_request`, and `get_after_sales_status` in `agent-service/app/tools/` with the common success/data/error_code/retryable/latency/trace envelope
- [ ] T030 [US1] Implement `understand_request`, unique-order resolution for the single-candidate path, `decide_next_evidence`, read-tool execution, evidence validation and `check_eligibility` nodes in `agent-service/app/agent/nodes/`
- [ ] T031 [US1] Implement write execution plus verify-after-write recovery so ambiguous refund timeouts call `get_after_sales_status` before any retry and reuse the same logical idempotency key in `agent-service/app/agent/nodes/execute_write.py` and `verify_business_state.py`
- [ ] T032 [US1] Wire the explicit LangGraph START → understand → resolve → evidence loop → eligibility → refund write → verify → finalize path with maximum step/retry budgets in `agent-service/app/agent/graph.py` and `agent-service/app/agent/routing.py`
- [ ] T033 [US1] Implement run creation/execution and final response serialization in `agent-service/app/api/runs.py`, returning business ids and verified facts rather than model-invented success claims
- [ ] T034 [US1] Build the minimal Customer Console showing chat input, current run status, resolved order, final result and collapsible tool timeline in `web/src/features/chat/`
- [ ] T035 [US1] Add versioned US1 eval fixtures/cases for normal logistics refund, duplicate submission and ambiguous timeout recovery in `eval/datasets/v1/dev/us1_logistics_refund.yaml` and scorer assertions in `eval/scorers/business_state.py`

**Checkpoint — Week 2 target**: One end-to-end request must visibly travel Web/API → Agent → Java tools → PostgreSQL → exactly one refund record → verified result + trace. Do not start MCP, dashboard polish or Multi-Agent work before this passes.

---

## Phase 4: User Story 2 — 已签收商品改走退货路径 (Priority: P1)

**Goal**: The same refund-like request must branch to return handling when order evidence shows the item was already delivered within the return window.

**Independent Test**: Seed a `DELIVERED` order delivered 3 days ago. The Agent must not create an unsigned-order refund; it must obtain return eligibility and create one `ReturnRequest`.

### Tests for User Story 2

- [ ] T036 [P] [US2] Write Java return eligibility/state/idempotency integration tests in `commerce-backend/src/test/java/com/seventeen17/commerceagent/returns/ReturnIntegrationTest.java`
- [ ] T037 [P] [US2] Write Python branching test proving `DELIVERED` evidence changes the next action from refund to return in `agent-service/tests/integration/test_us2_delivered_return.py`

### Implementation for User Story 2

- [ ] T038 [US2] Add `commerce.return_requests` schema with idempotency and allowed lifecycle states and implement entity/repository in `commerce-backend/src/main/resources/db/migration/V003__return_schema.sql` and `commerce-backend/src/main/java/com/seventeen17/commerceagent/returns/`
- [ ] T039 [US2] Extend deterministic eligibility rules for return window and `RETURN`/`RETURN_REFUND` actions in `commerce-backend/src/main/java/com/seventeen17/commerceagent/eligibility/EligibilityService.java`
- [ ] T040 [US2] Implement guarded return creation/status endpoints from the commerce contract in `commerce-backend/src/main/java/com/seventeen17/commerceagent/returns/ReturnService.java` and `ReturnController.java`; when approval is required, validate authoritative `approvalRequestId` exactly as refund writes do
- [ ] T041 [US2] Add `create_return_request` tool and route delivered evidence through return eligibility/write/verification in `agent-service/app/tools/return_tools.py`, `agent-service/app/agent/routing.py`, and `agent-service/app/agent/graph.py`
- [ ] T042 [US2] Add delivered/return-path eval cases and forbidden-direct-refund assertions in `eval/datasets/v1/dev/us2_delivered_return.yaml`

**Checkpoint**: US1 and US2 both pass with the same high-level user intent but materially different business paths.

---

## Phase 5: User Story 3 — 模糊订单澄清 (Priority: P1)

**Goal**: The Agent must stop and ask the user when multiple plausible orders exist; no write occurs before explicit resolution.

**Independent Test**: Seed two plausible earphone orders. The run enters `WAITING_USER`, refund/return write count remains 0, and the authenticated owner can resume the same run by selecting an order.

### Tests for User Story 3

- [ ] T043 [P] [US3] Write Python tests for multi-order ambiguity, zero writes before clarification, invalid clarification input, cross-user run-input denial, and resume-on-valid-order in `agent-service/tests/integration/test_us3_clarification.py`

### Implementation for User Story 3

- [ ] T044 [US3] Implement candidate-order scoring that can return `AMBIGUOUS_ORDER` without guessing and persist candidate ids in `agent-service/app/agent/nodes/resolve_order.py`
- [ ] T045 [US3] Implement LangGraph interrupt/checkpoint transition to `WAITING_USER` and resume validation in `agent-service/app/agent/nodes/ask_clarification.py` and `agent-service/app/agent/graph.py`
- [ ] T046 [US3] Implement `POST /api/v1/agent/runs/{runId}/input` with authenticated ownership and run-state validation in `agent-service/app/api/runs.py`
- [ ] T047 [US3] Add order-selection clarification UI and resume flow in `web/src/features/chat/ClarificationPanel.tsx`
- [ ] T048 [US3] Add ambiguity/clarification eval cases with explicit `max_write_count: 0` before resolution in `eval/datasets/v1/dev/us3_clarification.yaml`

**Checkpoint**: Ambiguous business objects are never guessed and only the authorized owner can resume the exact run after clarification.

---

## Phase 6: User Story 4 — 高风险售后人工审批 (Priority: P2)

**Goal**: Deterministic risk rules can stop a valid action at a Human-in-the-loop gate, and only an authorized approver can resume it.

**Independent Test**: Seed an eligible high-value action with `approval_required=true`. The Agent creates one pending approval and enters `WAITING_APPROVAL`; refund/return write count remains 0 until an approver approves.

### Tests for User Story 4

- [ ] T049 [P] [US4] Write Java approval transition/auth tests covering `PENDING → APPROVED|DENIED|EXPIRED`, terminal-state immutability, approval run/order/action/amount binding and non-approver denial in `commerce-backend/src/test/java/com/seventeen17/commerceagent/approval/ApprovalIntegrationTest.java`
- [ ] T050 [P] [US4] Write Python pause/resume tests proving the Agent cannot self-approve, fabricate approval state, or resume using another run's approval id in `agent-service/tests/integration/test_us4_human_approval.py`

### Implementation for User Story 4

- [ ] T051 [US4] Add `commerce.approval_requests` schema and implement ApprovalRequest entity/repository with terminal-state and run/order/action/amount binding fields in `commerce-backend/src/main/resources/db/migration/V004__approval_schema.sql` and `commerce-backend/src/main/java/com/seventeen17/commerceagent/approval/`
- [ ] T052 [US4] Implement create/list/decision approval endpoints from `commerce-api.openapi.yaml` with `APPROVER` authorization for list/decision and audit events in `commerce-backend/src/main/java/com/seventeen17/commerceagent/approval/ApprovalService.java` and `ApprovalController.java`
- [ ] T053 [US4] Implement `request_human_approval` tool returning authoritative `approvalRequestId` plus WAITING_APPROVAL checkpoint routing in `agent-service/app/tools/approval_tools.py` and `agent-service/app/agent/nodes/risk_gate.py`; Agent MUST NOT create or assert approval tokens/status
- [ ] T054 [US4] Implement owner-authorized Agent resume endpoint that re-reads authoritative Java approval state and verifies run/order/action/amount binding before continuing in `agent-service/app/api/runs.py`
- [ ] T055 [US4] Build Approval Center showing order/action/amount/risk reason/evidence and Approve/Deny controls in `web/src/features/approvals/`
- [ ] T056 [US4] Add high-risk approval, denied approval, cross-bound approval id and attempted self-approval eval cases in `eval/datasets/v1/dev/us4_approval.yaml`

**Checkpoint**: No model or user prompt can turn a pending approval into an accepted business write.

---

## Phase 7: User Story 5 — 无法自动处理时安全转人工 (Priority: P2)

**Goal**: Missing/conflicting evidence, persistent dependency failure, manual-review eligibility and exhausted step budgets must end in escalation or safe stop rather than guessed business writes.

**Independent Test**: Make logistics unavailable beyond the retry budget or return `MANUAL_REVIEW`; the Agent creates a traceable support ticket (when appropriate) or safely stops, with zero unauthorized refund/return writes.

### Tests for User Story 5

- [ ] T057 [P] [US5] Write Python tests for retry budget, repeated-no-new-evidence loop prevention, dependency timeout, `MANUAL_REVIEW`, safe stop and escalation in `agent-service/tests/integration/test_us5_safe_escalation.py`
- [ ] T058 [P] [US5] Write Java support-ticket creation and ownership/audit tests in `commerce-backend/src/test/java/com/seventeen17/commerceagent/ticket/SupportTicketIntegrationTest.java`

### Implementation for User Story 5

- [ ] T059 [US5] Add `commerce.support_tickets` schema and implement SupportTicket entity/repository storing structured reason codes and evidence summaries but no hidden chain-of-thought in `commerce-backend/src/main/resources/db/migration/V005__support_ticket_schema.sql` and `commerce-backend/src/main/java/com/seventeen17/commerceagent/ticket/`
- [ ] T060 [US5] Implement guarded support-ticket creation endpoint in `commerce-backend/src/main/java/com/seventeen17/commerceagent/ticket/SupportTicketService.java` and `SupportTicketController.java`
- [ ] T061 [US5] Implement normalized retryability/error handling from `error-contracts.md`, no-new-evidence detection, max-step enforcement and `escalate_or_safe_stop` node in `agent-service/app/agent/nodes/` and `agent-service/app/tools/base.py`
- [ ] T062 [US5] Implement `create_support_ticket` tool and attach already-collected structured evidence/run id in `agent-service/app/tools/ticket_tools.py`
- [ ] T063 [US5] Add dependency failure, conflicting state, max-step and manual-review eval cases in `eval/datasets/v1/dev/us5_escalation.yaml`

**Checkpoint**: The safest valid outcome can be “do not write; escalate” and is scored as success when expected.

---

## Phase 8: User Story 6 — 售后规则检索与可解释结果 (Priority: P2)

**Goal**: Retrieve versioned policy/SOP text for explanation while keeping policy prose completely separate from deterministic financial authorization.

**Independent Test**: Retrieve an effective policy citation for a supported case; inject a malicious/expired/conflicting policy and prove it cannot change ownership, amount, eligibility, approval or tool permissions.

### Tests for User Story 6

- [ ] T064 [P] [US6] Write retrieval tests for effective-date filtering, citation metadata, expired/conflicting policy handling and prompt-injection text isolation in `agent-service/tests/integration/test_us6_policy_rag.py`

### Implementation for User Story 6

- [ ] T065 [US6] Add pgvector extension plus `policy.policy_documents`/`policy.policy_chunks` schema with document code, version, effective dates, section, checksum and embedding in `commerce-backend/src/main/resources/db/migration/V006__policy_rag_schema.sql`; Flyway creates schema, Python owns retrieval semantics/data access
- [ ] T066 [P] [US6] Create versioned synthetic AfterSalesPolicy documents for general refund, logistics exception, electronics return and digital-goods/manual-review examples in `knowledge/policies/`
- [ ] T067 [US6] Implement policy ingestion/chunking/embedding pipeline with deterministic document metadata in `agent-service/app/rag/ingest.py`
- [ ] T068 [US6] Implement metadata-filtered policy retrieval returning document code/version/effective date/section/score and conflict flags in `agent-service/app/rag/retriever.py`
- [ ] T069 [US6] Implement `policy_search` tool and final answer citation rendering while explicitly preventing retrieved text from modifying tool allowlists, auth, eligibility, amount or approval state in `agent-service/app/tools/policy_tools.py` and `agent-service/app/agent/nodes/finalize.py`
- [ ] T070 [US6] Add policy citation, expired-policy, conflict and retrieval-injection eval cases in `eval/datasets/v1/dev/us6_policy_rag.yaml`

**Checkpoint**: Policy RAG improves explanation/evidence but cannot authorize a business write.

---

## Phase 9: Polish & Cross-Cutting Validation

**Purpose**: Finish the evaluation, observability, reproducibility, UI and evidence needed for a job-ready project without widening product scope.

- [ ] T071 Build the CLI/file-first versioned eval runner that calls the reset contract in `contracts/eval-internal-api.md`, executes a run, captures final business state/tool trace/latency/token usage and emits machine-readable JSON results in `eval/runner/run_eval.py`
- [ ] T072 [P] Implement scorers for task success, tool selection, parameter correctness, policy compliance, unsafe actions, duplicate writes, retrieval recall/citation accuracy, average tool calls and latency/token summaries in `eval/scorers/`
- [ ] T073 Create the honest fixed-workflow baseline from the same tool contracts and permissions in `eval/baselines/fixed_workflow.py`; do not intentionally cripple it
- [ ] T074 Expand and freeze the dataset to at least 60 cases and target ~74 cases with separate dev/test manifests in `eval/datasets/v1/dev/`, `eval/datasets/v1/test/`, and `eval/datasets/v1/manifest.yaml`
- [ ] T075 Run Baseline and V1 on the same frozen configuration, generate error taxonomy and store raw/versioned reports in `eval/reports/`; do not publish improvement claims before these artifacts exist
- [ ] T076 Apply exactly one attributable optimization to the largest dev-set error category, rerun the comparable test set, and record before/after evidence in `eval/reports/optimization-1.md`
- [ ] T077 Build Run Trace and Eval Dashboard pages without hidden chain-of-thought exposure in `web/src/features/runs/` and `web/src/features/eval/`; Eval Dashboard reads generated machine-readable report artifacts from `eval/reports/` through a simple static/dev adapter rather than requiring a dedicated Eval HTTP service
- [ ] T078 Add cross-service contract validation for both OpenAPI files, `eval-internal-api.md`, and tool mappings in `agent-service/tests/contract/` and `commerce-backend/src/test/java/com/seventeen17/commerceagent/contract/`
- [ ] T079 Add adversarial end-to-end tests for cross-user commerce access, cross-user Agent run access, prompt injection, approval bypass/cross-binding, duplicate write, stale/unknown write result and invalid arbitrary tool/URL attempts in `eval/datasets/v1/test/security_regression.yaml`
- [ ] T080 Add CI workflow running Java tests, Python tests, frontend build and contract checks in `.github/workflows/ci.yml`
- [ ] T081 Complete Docker Compose clean-environment startup and seed/health checks in `infra/docker-compose.yml`, `commerce-backend/Dockerfile`, `agent-service/Dockerfile`, and `web/Dockerfile`
- [ ] T082 Execute every scenario in `specs/002-commerce-after-sales-agent/quickstart.md`, record pass/fail evidence and fix blockers before declaring the feature implementation-ready
- [ ] T083 Update root `README.md` with architecture, truthful local setup, 60–90 second demo path, measured eval results only, known limitations and explicit non-claims about real ERP/payment/production deployment

**Final Checkpoint**: Core product is reproducible from a clean clone, Agent Value Gate passes, unsafe writes are rejected by Java even under hostile model/user text, the frozen eval is reproducible, and all public metrics link to actual run artifacts.

---

## Dependencies & Execution Order

### Phase Dependencies

```text
Phase 1 Setup
   ↓
Phase 2 Foundational
   ↓
US1 Logistics Refund (MVP)
   ↓
US2 Delivered Return ─┐
US3 Clarification     ├─ can proceed independently after Foundation + shared US1 read/eligibility capabilities
US4 Approval          ┤
US5 Safe Escalation   ┤
US6 Policy RAG        ┘
   ↓
Phase 9 Polish / Frozen Eval / Reproducibility
```

### User Story Dependencies

- **US1**: First business slice; depends only on Setup + Foundational.
- **US2**: Reuses shared order/eligibility/verification capabilities introduced in US1 but is independently testable with a delivered fixture.
- **US3**: Reuses order-list capability but introduces its own WAITING_USER interrupt/resume contract.
- **US4**: Reuses eligibility outcome but introduces a separate authoritative approval domain and WAITING_APPROVAL resume contract.
- **US5**: Reuses common error envelope/tool runner but is independently testable by forcing dependencies/manual review.
- **US6**: Can be implemented after Foundation in parallel with other P2 stories because RAG is explanatory context, not a prerequisite for authorization.

### Within Each User Story

1. Write the story-specific tests and confirm they fail for the intended missing behavior.
2. Implement deterministic Java domain/state rules before exposing state-changing tools.
3. Implement typed Python tools before graph routing uses them.
4. Add/modify graph nodes and edges.
5. Add the minimum UI necessary for the story.
6. Add deterministic eval cases and verify final business state.
7. Stop at the checkpoint and validate the story independently before proceeding.

---

## Parallel Opportunities

- T003/T004/T006/T007 can run in parallel after T001.
- T009/T010/T012/T013/T015/T016 can run in parallel once database/config skeletons exist.
- Story test tasks marked `[P]` can be authored together before implementation.
- After US1 establishes shared read/eligibility contracts, US2–US6 can be developed in parallel by separate developers; for a solo project, execute in listed priority order.
- Policy document authoring T066 can run in parallel with policy schema/retriever work.
- Eval scorer T072, dashboard T077 and CI T080 can proceed in parallel after core run/trace schemas stabilize.

### Parallel Example: US1

```text
T019 Order/logistics tests
T020 Eligibility tests
T021 Refund/idempotency tests
T022 Agent integration tests

Then, once their required contracts are understood:
T023 Order API
T024 Logistics API
T029 Python read/write tool wrappers
```

### Parallel Example: US4

```text
T049 Java approval transition/auth tests
T050 Python HITL pause/resume tests

After the approval contract is stable:
T052 Java approval endpoints
T053 Agent approval tool/risk gate
T055 Approval Center UI
```

---

## Implementation Strategy

### MVP First — stop after US1

1. Complete Setup.
2. Complete Foundational.
3. Complete US1 only.
4. Run the US1 independent test plus duplicate/timeout tests.
5. Demonstrate one real DB write and one full structured trace.
6. If this is not convincing, fix the core boundary before adding return/RAG/HITL/UI polish.

### Agent Value Gate — complete by US2/US3/US4

Run the same refund-like request against these seeded states:

```text
A: SHIPPED + logistics stalled → refund
B: DELIVERED within window     → return
C: two plausible orders        → clarification
D: high-risk eligible action   → WAITING_APPROVAL
```

PASS only if evidence changes the next tool/action and all writes remain Java-authorized. If all cases collapse into a fixed refund router, stop and redesign instead of adding frameworks.

### Incremental Delivery

- **Increment 1**: US1 → real end-to-end refund slice.
- **Increment 2**: US2 + US3 → prove dynamic business branching and clarification.
- **Increment 3**: US4 + US5 → prove enterprise safety/HITL/failure handling.
- **Increment 4**: US6 → add bounded policy RAG/citations.
- **Increment 5**: freeze eval, compare baseline/V1, make one attributable optimization, package demo.

### Scope Guard

The following are intentionally absent from this task list unless a later measured need justifies a new feature/spec: Multi-Agent decomposition, Kafka, Kubernetes, Redis as core state, independent vector DB, real payment gateway, real Taobao/JD integration, merchant marketing, pre-sales recommendation, broad omnichannel customer service, model fine-tuning, and decorative admin CRUD.

---

## Notes

- `.specify/memory/constitution.md` is authoritative; tasks that conflict with a MUST rule require design correction before implementation.
- Every state-changing task must preserve the deterministic Agent/backend authority boundary defined in `plan.md`.
- Do not expose raw SQL, arbitrary URLs/internal endpoints or database credentials as Agent tools.
- Do not persist or display hidden chain-of-thought; trace structured decisions, evidence references, tool inputs/outputs, reason codes and state transitions only.
- Do not mark an eval/resume/latency/safety metric as achieved in README or resume material until a reproducible report exists.
- Commit after each task or small logical group so regressions can be bisected.
