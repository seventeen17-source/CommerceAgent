# Implementation Plan: CommerceAgent 企业电商售后执行与异常处置 Agent

**Branch**: `002-commerce-after-sales-agent` | **Date**: 2026-09-15 | **Spec**: `specs/002-commerce-after-sales-agent/spec.md`

## Summary

Build a bounded e-commerce after-sales execution Agent that can resolve ambiguous customer intent, gather order/logistics/policy evidence, dynamically choose the next safe business capability, and execute refund/return/escalation flows only through deterministic business authorization. The implementation uses a React web UI, a Python Agent service with an explicit state graph, a Java modular-monolith business backend, PostgreSQL, policy-only RAG, structured traces, and a versioned offline eval harness.

## Technical Context

**Language/Version**: Java 21 LTS; Python 3.13; TypeScript 5.x

**Primary Dependencies**: Spring Boot 3.5.x, Spring Security, Spring Data JPA, Flyway, FastAPI, LangGraph Graph API, Pydantic, httpx, React, PostgreSQL, pgvector

**Storage**: One PostgreSQL instance with explicit logical ownership: `commerce` (Java authority), `agent` (Python Agent runtime/trace), `policy` (Python retrieval), and optional `eval` metadata. Flyway in the Java project is the single V1 migration authority for deterministic shared-database startup.

**Testing**: JUnit 5 + Spring Boot Test + Testcontainers; pytest + pytest-asyncio; contract tests; Playwright as Should

**Target Platform**: Linux containers / local Docker Compose

**Project Type**: Web application + Agent application with Java business backend and Python Agent service

**Performance Goals**: Correctness and safety first; report measured p50/p95 latency, tool-call count, and token usage rather than inventing fixed SLOs before measurement

**Constraints**: 6–8 week solo scope; synthetic/local contract-realistic commerce systems; no direct Agent access to authoritative commerce tables; server-side authorization and deterministic eligibility required for all state-changing actions; no broad omnichannel/pre-sales scope

**Scale/Scope**: One bounded after-sales domain, 6–10 Agent tools, 4 UI pages, at least 60 and target ~74 versioned eval cases

## Constitution Check

*GATE: Must pass before implementation and be re-checked after design changes.*

The project constitution is `.specify/memory/constitution.md` v1.0.0. This plan passes its non-negotiable rules as follows:

- **Deterministic Business Authority — PASS**: Java remains authoritative for ownership, auth, eligibility, amount, legal state transitions, approval validation, idempotency and transactional writes.
- **Safe, Idempotent, Verifiable Writes — PASS**: refund/return contracts require current-state revalidation, idempotency and post-write verification; ambiguous timeouts query authoritative status before retry.
- **Evidence-Dependent Agent Behavior — PASS**: explicit graph state/conditional routing plus the four-case Agent Value Gate force evidence-dependent branching.
- **Untrusted Inputs/Retrieval/Model Output — PASS**: tools are allowlisted; policy text is explanatory only; no arbitrary URL/SQL/service execution path exists.
- **Reproducible Tests/Eval/Trace — PASS**: story-specific tests, resettable fixtures, versioned datasets, structured traces and comparable baseline/V1 runs are planned.
- **Bounded Architecture/Scope — PASS**: one Java modular monolith, one Python Agent service, one web app, one PostgreSQL instance; no core microservices/Kafka/K8s/Multi-Agent/independent vector DB.

Any later design change that violates a constitution MUST requires a constitution amendment or a design rollback before implementation continues.

## Project Structure

### Documentation

```text
specs/002-commerce-after-sales-agent/
├── spec.md
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   ├── commerce-api.openapi.yaml
│   ├── agent-api.openapi.yaml
│   ├── tool-contracts.md
│   ├── error-contracts.md
│   └── eval-internal-api.md
└── tasks.md
```

### Source Code

```text
commerce-backend/
├── pom.xml
└── src/
    ├── main/java/.../commerceagent/
    │   ├── security/
    │   ├── order/
    │   ├── logistics/
    │   ├── eligibility/
    │   ├── refund/
    │   ├── returns/
    │   ├── approval/
    │   ├── ticket/
    │   ├── audit/
    │   └── fixture/
    └── test/

agent-service/
├── pyproject.toml
└── app/
    ├── api/
    ├── agent/
    │   ├── graph.py
    │   ├── state.py
    │   ├── routing.py
    │   └── nodes/
    ├── tools/
    ├── clients/
    ├── rag/
    ├── trace/
    └── config/

web/
└── src/
    ├── features/chat/
    ├── features/approvals/
    ├── features/runs/
    ├── features/eval/
    └── api/

eval/
├── datasets/
├── runner/
├── scorers/
├── baselines/
└── reports/

knowledge/
└── policies/

infra/
└── docker-compose.yml
```

**Structure Decision**: Java is a modular monolith owning domain rules, transactions and state; Python owns Agent state/orchestration, RAG, tool adapters and eval; React is a thin demonstration/operations UI. PostgreSQL is the only core datastore. HTTP/JSON is the initial inter-service contract; MCP is deferred to a later Should-level adapter.

## Database Boundary Decision

One PostgreSQL instance is used for reproducibility, not to erase service boundaries.

- Java application code owns and accesses authoritative `commerce` tables.
- Python application code owns `agent` runtime/trace and `policy` retrieval data.
- Python MUST NOT query/write `commerce` tables directly; it uses typed Java APIs.
- Flyway in `commerce-backend` is the single V1 migration runner for all logical schemas so a clean clone has one deterministic migration sequence.
- Eval fixture reset is a Java-only internal endpoint available only under test/eval profiles because authoritative commerce state belongs to Java.

## Architecture Decisions

### Java modular monolith
Selected instead of multiple microservices. The project needs deep business correctness more than distributed-systems ceremony. Modules remain explicit but deploy together.

### Java + Python split
Selected only because each runtime has a non-trivial responsibility: Java owns business invariants and safe writes; Python owns explicit Agent graph, tool orchestration, RAG and eval. If either side degrades into a pass-through proxy, collapse the split.

### LangGraph Graph API
Selected because the feature genuinely needs explicit state, conditional edges, loops, checkpoints, interrupts and Human-in-the-loop resume. The implementation must still expose its own state schema and routing decisions rather than hiding the workflow behind a generic agent factory.

### PostgreSQL + pgvector
Selected to avoid an unnecessary standalone vector database. Structured commerce truth remains relational; pgvector is used only for unstructured policy retrieval.

### HTTP first, MCP later
Typed HTTP/JSON is the core contract. MCP is a Week-7/Should adapter only after tool semantics, auth and retries are already correct.

### Eval is CLI/file-first
The core eval runner is not a public service. It resets fixtures through the eval-only internal Java contract, executes Agent runs, computes scorers, and writes versioned machine-readable reports under `eval/reports/`. The Eval Dashboard reads generated report artifacts; a dedicated Eval HTTP API is deferred unless a later requirement justifies it.

## Phase 0 — Research Outputs

`research.md` freezes Java/Spring/Python versions, Agent orchestration choice, storage/RAG approach, inter-service protocol, authentication approach, checkpoint strategy, observability strategy, eval format, deployment boundary, and rejected technologies.

## Phase 1 — Design Outputs

`data-model.md` defines commerce, after-sales, Agent trace and policy entities plus state transitions, logical schema ownership, and unique/idempotency constraints.

`contracts/commerce-api.openapi.yaml` defines Java business APIs used by tools, including authoritative approval listing/decision and approval-record validation references.

`contracts/agent-api.openapi.yaml` defines authenticated Web-to-Agent run, event, clarification and resume interfaces with run ownership requirements.

`contracts/tool-contracts.md` maps Agent tools to business contracts, risk levels, retry semantics and authorization rules.

`contracts/error-contracts.md` defines stable error codes and Agent handling semantics.

`contracts/eval-internal-api.md` defines the eval-only deterministic fixture-reset contract.

`quickstart.md` proves the Agent Value Gate with seeded refund-like cases that branch to refund, return, clarification and approval, plus one safety/failure case.

## Post-Design Constitution Re-check

PASS only if:

1. no Agent path can bypass deterministic ownership/eligibility/approval checks;
2. no write tool can create duplicate logical refunds/returns under retry/timeout;
3. Agent state and business state are separately modelled and service authority remains explicit despite one physical database;
4. policy RAG cannot become a source of financial authorization;
5. Agent API endpoints enforce authentication and run ownership;
6. approval is referenced by authoritative `approvalRequestId`, never model-generated approval status/token;
7. quickstart demonstrates evidence-dependent branching;
8. implementation scope remains bounded to after-sales execution.

## Complexity Tracking

No constitution violation is currently justified. Microservices, Multi-Agent, Kafka, Kubernetes, Redis-as-core, independent vector DB, full admin/RBAC product, real payment gateway and broad commerce features remain rejected unless later measured evidence requires them.
