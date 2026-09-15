# CommerceAgent Technical Research

This document resolves the implementation-planning decisions for `002-commerce-after-sales-agent`.

## Decision 1 — Java 21 + Spring Boot 3.5.x for the business backend

**Decision**: Use Java 21 LTS with Spring Boot 3.5.x.

**Rationale**: The project needs substantial deterministic domain logic, transactions, authorization, idempotency and audit. Java is also aligned with the user's existing strength and the hiring evidence that repeatedly accepts Java/Python/Go for AI application/backend roles. Spring Boot 3.5.x is preferred over a major-version jump because ecosystem maturity matters more than novelty for an 8-week portfolio project.

**Alternatives considered**:
- Spring Boot 4.x: rejected for core because the project gains little interview value from a newer major line while accepting more compatibility churn.
- Python-only backend: rejected because it would remove an opportunity to demonstrate deep transactional backend engineering and underuse the user's strongest language.

## Decision 2 — Python 3.13 + FastAPI for Agent orchestration

**Decision**: Use Python 3.13 and FastAPI for the Agent service.

**Rationale**: Python has the strongest current Agent/evaluation ecosystem and directly addresses the user's weaker skill area. FastAPI provides typed request models and a simple async service surface without turning the service into a framework-heavy platform.

**Alternatives considered**:
- Java-only Agent: viable, but rejected because it reduces exposure to the Python Agent ecosystem that is common in current application-engineering roles.
- Flask/Django: no compelling advantage for this bounded Agent API.

## Decision 3 — Explicit LangGraph Graph API

**Decision**: Use LangGraph's explicit graph/state primitives rather than a black-box generic agent constructor.

**Rationale**: The product requires conditional branching, loops, clarification interrupts, Human-in-the-loop pause/resume, checkpointed execution and bounded recovery. These are workflow/state problems. The graph remains project-owned: state schema, nodes, edge conditions, stop rules and tool policies are explicit in repository code.

**Alternatives considered**:
- Open-ended ReAct loop: rejected because it weakens bounded execution, failure recovery and deterministic evaluation.
- Hand-written while-loop state machine: technically possible and useful for understanding, but LangGraph provides checkpoint/HITL runtime support with less boilerplate.
- Multi-Agent: rejected because the workflow does not require independently autonomous role agents.

## Decision 4 — Java modular monolith

**Decision**: Deploy one Java application with explicit domain modules.

**Rationale**: Order, logistics projection, eligibility, refund, return, approval, ticket and audit share transactional business state. Splitting them into network microservices would add service discovery, distributed transactions and failure modes without increasing the evidence the project is meant to demonstrate.

**Alternatives considered**:
- One microservice per domain: rejected as architecture theater for this scale.
- One undifferentiated package: rejected because module boundaries are valuable for interviews/testing even when deployment is monolithic.

## Decision 5 — PostgreSQL as the only core datastore

**Decision**: Use PostgreSQL for business state, Agent trace/checkpoint metadata, audit records and policy retrieval vectors via pgvector.

**Rationale**: A relational database is the authoritative store for transactional commerce state. Reusing PostgreSQL for a small policy corpus avoids introducing a separate vector database with no measured scale requirement.

**Alternatives considered**:
- Qdrant/Milvus/Elasticsearch: rejected for V1 because the corpus is small and the project is not a retrieval-platform benchmark.
- Redis as mandatory state store: rejected until a real shared-state/latency need is measured.

## Decision 6 — RAG only for unstructured policy/SOP

**Decision**: Use retrieval only for policy/SOP explanation and context. Order, logistics, amount, eligibility, approval and after-sales status always come from structured APIs.

**Rationale**: Business truth must remain deterministic, versioned and auditable. Vector retrieval is appropriate for prose policy but not for real-time transactional state.

**Alternatives considered**:
- Put all commerce data in a vector DB: rejected as incorrect authority modelling.
- No RAG at all: acceptable fallback if the policy corpus is too small; a direct versioned policy lookup can replace vector retrieval without changing business authority.

## Decision 7 — HTTP/JSON first; MCP deferred

**Decision**: Tool adapters call typed Java HTTP/JSON APIs first. MCP is optional after the core flow works.

**Rationale**: The hiring signal behind MCP is reusable tool interoperability, not the protocol label by itself. The project should first prove tool schemas, auth, retry/idempotency and safe writes with a transparent contract.

**Alternatives considered**:
- MCP from day one: rejected because it risks turning protocol plumbing into a Week-1 dependency.

## Decision 8 — Local JWT fixtures, not full identity product

**Decision**: Use a minimal local JWT setup with seeded users/roles.

**Rationale**: Authorization is essential to demonstrate cross-user protection, but registration, password recovery, social login and account administration do not contribute to the project thesis.

**Alternatives considered**:
- `X-User-Id` header only: rejected because it makes authorization too toy-like.
- Full OAuth/OIDC provider: rejected as non-core scope.

## Decision 9 — Agent checkpoints and resume state persisted

**Decision**: Persist enough Agent execution/checkpoint state to support clarification/HITL resume and run reconstruction.

**Rationale**: `WAITING_USER` and `WAITING_APPROVAL` are first-class states; they cannot depend on an in-memory process surviving. The exact LangGraph checkpointer implementation may evolve, but resume semantics are Must.

**Alternatives considered**:
- Memory-only state: rejected because restart would break approval/clarification workflows and make recovery unconvincing.

## Decision 10 — Self-contained structured tracing

**Decision**: Keep core run/tool traces in project-owned storage; OpenTelemetry or external tracing platforms are optional enrichments.

**Rationale**: A reviewer cloning the repository must be able to inspect a failed run without requiring a paid SaaS. Trace data records explicit state transitions, tools, validated parameter summaries, errors, retries, approval and verification; hidden model chain-of-thought is neither required nor stored.

**Alternatives considered**:
- LangSmith-only/Langfuse-only: rejected as a hard dependency, though adapters may be added later.

## Decision 11 — Versioned eval cases in Git

**Decision**: Store eval case definitions in versioned YAML/JSON files and use deterministic scorers against resettable Java fixtures.

**Rationale**: The main correctness targets are business state, tool selection, parameters, forbidden actions, duplicate writes and safety. Most do not need an LLM judge. Versioning the dataset supports comparable Baseline/V1/Optimized runs.

**Alternatives considered**:
- Manual demo-only evaluation: rejected.
- LLM-as-judge as primary oracle: rejected for business/safety correctness; it may only supplement qualitative response scoring.

## Decision 12 — Docker Compose deployment

**Decision**: Core local deployment is Docker Compose for PostgreSQL, Java backend, Python Agent service and optional web UI.

**Rationale**: Reproducibility matters; cluster orchestration does not.

**Alternatives considered**:
- Kubernetes: rejected for core.
- Cloud-first deployment: deferred until the local evidence loop is stable.

## Decision 13 — Four thin frontend surfaces

**Decision**: Provide Customer Console, Approval Center, Run Trace and Eval Dashboard.

**Rationale**: Each page proves a distinct product capability. The project does not need a generic admin dashboard.

**Alternatives considered**:
- CLI only: workable for early implementation, but a thin web UI improves demonstration of HITL and traces.
- Large operations console: rejected.

## Decision 14 — Explicitly rejected technologies/features

Rejected from core unless later measurement changes the decision:
- Multi-Agent;
- Kafka/event-bus architecture;
- Kubernetes;
- mandatory Redis;
- independent vector database;
- model fine-tuning/RLHF;
- real payment gateway;
- broad customer-service/pre-sales/recommendation/marketing/procurement modules.

## Research exit verdict

No unresolved implementation-planning clarification remains that blocks Phase 1 design. Technology decisions remain revisitable through measured evidence, but the baseline stack and architectural boundaries are frozen strongly enough to generate the data model and contracts.
