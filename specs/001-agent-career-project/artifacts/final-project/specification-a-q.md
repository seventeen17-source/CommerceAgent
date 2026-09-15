# ProcurePilot — A–Q Final Project Specification

**Selected candidate**: C1 — Enterprise Procurement & Supplier Execution Agent  
**Selection source**: `../decisions/final-selection.md`  
**Status**: current design specification for the future implementation feature  
**Scope**: one procurement category, one request-to-approval/PO-draft workflow, stateful local enterprise system, controlled tool execution, evaluation-first reliability.  

## A. Project Positioning

ProcurePilot is an **enterprise execution Agent**, not a procurement chatbot. It turns an incomplete natural-language purchase need into a policy-checked, budget-aware, supplier-comparable, approval-ready business transaction while keeping deterministic business rules and risky writes outside model authority.

The project is designed to demonstrate the hiring signals most consistently supported by the 2026 early-career market sample: Tool/API integration, stateful workflow, backend engineering, enterprise-system integration, retrieval where justified, evaluation/observability, failure handling and safe writes.

## B. Enterprise Scenario

Primary user: employee/requester.  
Secondary users: procurement specialist and approver.

Core workflow:
1. requester describes a purchase need;
2. Agent detects missing blocking constraints;
3. Agent dynamically chooses supplier/quote/budget/policy evidence;
4. deterministic backend validates supplier eligibility, quote freshness, budget, permissions and state;
5. Agent compares only acceptable alternatives and explains tradeoffs;
6. backend creates one idempotent purchase request;
7. high-risk/high-value flow pauses for human approval;
8. approved flow may create one PO draft;
9. Agent verifies authoritative state before reporting success.

Detailed normal/failure cases: `scenarios.md`.

## C. Overall Architecture

```text
Minimal Web UI
      |
      v
Python Agent Service
(explicit state graph, model decisions, tool orchestration, eval hooks)
      |
      | typed HTTP tool calls first
      | optional MCP adapter later
      v
Java Spring Boot Business Backend
(domain rules, auth, transactions, idempotency, state machine)
      |
      v
PostgreSQL
(business state + audit + optional pgvector policy retrieval)
```

The two-service split is valid only because both sides have real responsibilities. If either becomes an empty wrapper, implementation should simplify rather than preserve architecture for resume keywords.

## D. Technology Selection and Tradeoffs

Full decision table: `technology-decisions.md`.

### Must
- Java + Spring Boot authoritative business backend.
- Python Agent service.
- Explicit state graph capability; LangGraph recommended but replaceable.
- Configurable LLM API.
- PostgreSQL.
- Small policy retrieval/RAG capability with citations.
- Structured Agent/tool/audit trace.
- Docker Compose reproducibility.

### Should
- minimal web UI;
- MCP adapter after base Tool/API contracts are proven;
- pgvector and/or hybrid retrieval if eval justifies it;
- CI and optional cloud deployment.

### Nice
- hosted tracing UI such as Langfuse/LangSmith only if trivial to add and data handling is acceptable.

### Reject from core
- Multi-Agent by default;
- Kubernetes;
- Kafka/message queue;
- Redis/cache without measured need;
- SFT/RLHF/Agentic RL;
- multiple real enterprise SaaS integrations;
- full admin/RBAC suite and decorative dashboards.

## E. Agent Architecture

State/graph details: `architecture-reliability-security.md`.

Core nodes:
`NormalizeRequest → ValidateRequiredFields → DecideNextEvidence → ExecuteReadTool/RetrievePolicy → ValidateEvidence → CompareAcceptableOptions → DeterministicPreflightChecks → CreateRequest → [RequestApproval/WAIT] → [CreatePODraft] → VerifyBusinessState → ComposeResult`.

Key rules:
- missing blocking fields cause clarification, not hallucinated defaults;
- next evidence/tool is chosen dynamically from task state;
- hard constraints are never delegated to free-form model judgment;
- all loops have a max-step/retry budget;
- read retries are bounded;
- ambiguous write outcomes are verified before retry;
- approval creates a pause/resume checkpoint;
- authoritative business state is re-read on resume;
- task/session state is sufficient; long-term user memory is not required.

The design preserves the red-team Agent-value gate because S02–S05 require different next actions based on different missing evidence, policy and approval conditions.

## F. Tools

Authoritative contracts: `tool-contracts.md`.

Core tool set:
1. `supplier_search`
2. `quote_query`
3. `budget_check`
4. `policy_search`
5. `create_purchase_request`
6. `request_approval`
7. `create_po_draft`
8. `get_request_status`

Every write tool has server-side authorization, validation, state-transition checks and idempotency. Model/retrieval text never changes permission.

## G. RAG — Whether and Why

RAG is **used narrowly for unstructured procurement policy/SOP knowledge**.

Use retrieval for:
- approval policy passages;
- category restrictions;
- purchasing SOPs;
- supplier-policy text that needs citation/version awareness.

Do **not** use RAG for:
- supplier certification state;
- quote price/expiry/delivery date;
- budget balance;
- purchase-request status;
- approval status;
- user permission.

Those are structured authoritative facts returned through backend APIs/tools.

Retrieval records policy ID/version/effective date/chunk/citation and is evaluated for recall and citation correctness. Hybrid lexical+semantic retrieval is Should, not automatic Must.

## H. Java / Business Backend Responsibilities

The Java backend is not an empty language showcase. It owns:
- supplier and quotation domain state;
- budget checks/reservations if needed;
- purchase-request state machine;
- approval state;
- PO draft creation;
- authorization;
- parameter/schema validation;
- transactions and optimistic/version checks;
- idempotency and duplicate prevention;
- authoritative policy invariants that must never depend on prompt behavior;
- audit records and status verification.

The later implementation feature must define concrete REST/tool endpoints from these responsibilities.

## I. Database / Domain Model

Core entities:
- `user_account`
- `supplier`
- `quote`
- `budget_account`
- `purchase_request`
- `approval`
- `purchase_order_draft`
- `policy_document`
- `agent_run`
- `agent_step`
- `tool_execution`
- `audit_log`

Relationships and key fields are specified in `architecture-reliability-security.md`.

Important constraints:
- unique effective idempotency key per write intent;
- quote must be active and belong to selected supplier/item context;
- request/approval/PO transitions are state-machine checked;
- amount is recomputed from authoritative quote/business rules, not trusted from model text;
- requester cannot self-approve;
- write outcome is verified against authoritative state when response is uncertain.

## J. Evaluation

Full design: `evaluation-design.md`.

Core dataset target: **60 versioned cases**, initially planned as 40 dev / 20 frozen test.

Required metrics:
- task success rate;
- tool selection accuracy;
- parameter accuracy;
- policy compliance rate;
- unsafe effective action rate;
- retrieval recall;
- citation accuracy;
- average tool calls;
- p50/p95 end-to-end latency;
- token usage/cost.

Experiment sequence:
1. Baseline simple tool-calling loop;
2. V1 explicit state graph + typed tools + safety/retrieval/trace;
3. Optimized version changing one largest dev-set failure category at a time.

No metric in the resume may be written as achieved until a reproducible evaluation run exists.

## K. Observability

A `run_id` must reconstruct:
- user/task input and normalized facts;
- model/provider/config version;
- graph nodes visited;
- concise structured decision categories;
- each tool and normalized/redacted arguments;
- tool results/errors/retries/latency;
- retrieval policy IDs/versions/chunks/scores;
- token usage/cost estimate;
- human approval events;
- business-state transitions;
- final verified outcome.

Do not store or expose hidden chain-of-thought. Store only structured decision metadata needed for debugging and evaluation.

## L. Testing

Required layers:
- unit tests for domain validators/state transitions/idempotency;
- business API tests for auth, schema, transactions and stale versions;
- tool contract tests for success/error/retry/permission semantics;
- Agent integration tests for graph branches and HITL resume;
- offline evaluation over versioned cases;
- failure injection for timeout/unknown write/stale quote/retrieval failure;
- security tests for Prompt Injection, unauthorized action, parameter tampering and sensitive-data exposure.

High-risk writes receive independent safety acceptance criteria.

## M. Deployment

Core deployment target: local reproducible Docker Compose stack containing:
- Python Agent service;
- Java backend;
- PostgreSQL;
- optional minimal web UI;
- model API configuration.

Cloud deployment is Should after the local stack and eval are stable. Kubernetes is explicitly rejected for the core portfolio build.

## N. Security

Security boundary details: `architecture-reliability-security.md`.

Must cover:
- Prompt Injection in user/supplier/retrieved content;
- least-privilege tool allowlists;
- authenticated user identity separate from model-generated arguments;
- schema/range/ID/date validation;
- server-side policy and state-machine enforcement;
- no raw DB credentials/SQL for Agent;
- read/write tool separation;
- Human-in-the-loop approval;
- idempotent writes and verify-after-write;
- audit trail;
- trace redaction and data minimization.

Target unsafe **effective** write count in final safety test is zero; this is a target/acceptance threshold, not an achieved metric before implementation.

## O. 6–8 Week Roadmap

Detailed weekly plan is produced in US5 (`weekly-roadmap.md`). Required shape is already frozen:
- Week 1: domain/tool/eval contracts and thin fixtures;
- Week 2: one happy path + one controlled failure end-to-end;
- Week 3: reliability/security/idempotency/HITL;
- Week 4: 60-case dataset + Baseline/V1 comparable runs;
- Week 5: one attributable optimization from error analysis;
- Week 6: reproducible core demo/evidence ledger;
- Week 7: optional MCP/extra adversarial depth/one external adapter;
- Week 8: README/demo/interview rehearsal/final evidence audit.

Weeks 7–8 are never required to make the core demo work.

## P. Interview Knowledge Mapping

Detailed map is produced in US5 (`interview-map.md`). Must-have interview topics:
- why Agent rather than deterministic workflow;
- state graph / context / stop conditions;
- Tool contract design;
- Agent vs business-backend responsibility split;
- transaction/idempotency semantics;
- Human-in-the-loop;
- Prompt Injection and least privilege;
- RAG boundary and citations;
- offline eval design and leakage controls;
- trace/observability;
- retries and partial failure;
- why Multi-Agent/MCP/K8s are not automatic Musts.

The user must personally be able to reproduce simplified core state/tool/idempotency/eval logic without delegating conceptual understanding to AI coding.

## Q. Resume / README / Demo Outputs

US6 produces templates. Final implementation should eventually provide:
- Chinese resume project experience;
- evidence-backed bullet points only;
- architecture diagram;
- README with business problem, boundaries, quickstart, eval design/results and limitations;
- 60–90 second demo showing one normal flow and one controlled failure;
- trace/eval screenshots or tables tied to reproducible runs;
- explicit disclosure that enterprise data/system integration is local/synthetic unless a real adapter is actually connected.

No invented “accuracy improved X%”, latency reduction or production deployment claim is permitted.

---

## Core vs Deferred Scope

### Core / Must
- one purchase workflow;
- real persistent business state;
- Agent dynamic next-action/tool choice;
- deterministic backend authority;
- 8 tool contracts;
- approval/idempotency/verification;
- policy retrieval with citations;
- 60-case eval design;
- trace and failure/security coverage;
- reproducible local deployment.

### Deferred / Should
- minimal polished UI;
- MCP adapter;
- pgvector/hybrid retrieval refinement;
- one external adapter;
- cloud deployment/CI polish.

### Explicitly Not Doing
- broad procurement suite;
- Multi-Agent without measured need;
- long-term memory;
- RLHF/SFT;
- K8s/queue/cache architecture theater;
- multiple SaaS integrations;
- complete RBAC/admin UI;
- fabricated metrics.

## Design Acceptance

This specification is valid only while:
1. at least S02–S05 remain independently testable dynamic Agent decisions;
2. deterministic business authority remains outside the model;
3. Week-2 vertical slice requires no real ERP/vendor credential;
4. safety/eval/trace remain core rather than end-of-project polish;
5. the six-week core remains viable after deleting all Should/Nice work.
